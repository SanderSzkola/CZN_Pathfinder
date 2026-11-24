# detect_nodes.py
import os
import cv2
import numpy as np
from PIL.Image import Image

from data.node import Node
from data.score_table import ScoreTable  # MUST CONTAIN EVERY VALID COMBINATION OF NODE+MODIFIER
from data.score_config import PASSTHROUGH_NODES
from data.settings import Settings
from processing.template_library import TemplateLibrary, TEMPLATE_NODE_PORTAL_FULL_W
from utils.path_converter import get_path

"""
Detects nodes on provided screenshot based on templates from TemplateLibrary
"""
# trim params
TRIM_TOP_PX = 120
TRIM_RIGHT_PX = 150
TRIM_LEFT_PX = 150
# color verify params
MAX_LIGHTING_GAIN = 1.25
MIN_LIGHTING_GAIN = 0.75
TEMPLATE_LEVELS = [255, 50, 15]  # purest form of magic numbers, it just works™
IMAGE_LEVELS = [255, 90, 20]
SHAPE_GRAY_THRESHOLDS = [180, 130, 80]
COLOR_MAX_DIFF = 15


# validate shape matches against color channels
def _verify_template_color(
        screenshot_bgr,
        template,
        template_name,
        x,
        y,
        template_color_cache,
        color_max_diff=COLOR_MAX_DIFF,
        debug=False,
):
    _, _, template_bgr, template_mask_indices = template
    template_height, template_width, _ = template_bgr.shape
    screenshot_patch = screenshot_bgr[
        y:y + template_height,
        x:x + template_width,
    ]
    if screenshot_patch.shape[:2] != (template_height, template_width):
        return False

    # cache template avg
    if template_name not in template_color_cache:
        template_pixels = template_bgr[template_mask_indices]
        template_color_cache[template_name] = template_pixels.mean(axis=0)

    template_average = template_color_cache[template_name]
    screenshot_pixels = screenshot_patch[template_mask_indices]
    screenshot_average = screenshot_pixels.mean(axis=0)

    # lighting gain, to fix darkening towards bottom
    numerator = float(np.dot(screenshot_average, template_average))
    denominator = float(np.dot(template_average, template_average))
    if denominator <= 1e-6:
        return False

    lighting_gain = numerator / denominator
    lighting_gain = float(np.clip(
        lighting_gain,
        MIN_LIGHTING_GAIN,
        MAX_LIGHTING_GAIN,
    ))
    corrected_template_average = template_average * lighting_gain

    channel_differences = np.abs(
        screenshot_average - corrected_template_average
    )
    max_channel_difference = float(channel_differences.max())
    passed = bool(np.all(channel_differences <= color_max_diff))

    if debug:
        print(
            f"[COLORV] {template_name} | "
            f"tmpl_avg(B,G,R)=({template_average[0]:4.1f},{template_average[1]:4.1f},{template_average[2]:4.1f}) "
            f"probe_avg=({screenshot_average[0]:4.1f},{screenshot_average[1]:4.1f},{screenshot_average[2]:4.1f}) "
            f"gain={lighting_gain:3.2f} "
            f"corr_diff=({channel_differences[0]:3.1f},{channel_differences[1]:3.1f},{channel_differences[2]:3.1f}) "
            f"max={max_channel_difference:.1f} "
            f"{'PASS' if passed else 'REJECT'}"
        )
    return passed


def threshold_gray(gray_image, levels, screenshot_index=-1):
    height = gray_image.shape[0]
    grayscale_values = gray_image.astype(np.int16)

    threshold_adjustment = np.zeros((height, 1), dtype=np.int16)
    if height > 100:  # image only, templates are smaller
        threshold_adjustment[int(height * 0.75):] += -20  # counter image darkening at the bottom
        if screenshot_index == 0:
            width = gray_image.shape[1]
            threshold_adjustment[:int(width * 0.3)] += 40  # counter glow beam

    conditions = [
        grayscale_values > (threshold + threshold_adjustment)
        for threshold in SHAPE_GRAY_THRESHOLDS
    ]
    return np.select(conditions, levels, default=0).astype(np.uint8)


def _load_map_image(map_fragment):
    if isinstance(map_fragment, str):
        image = cv2.imread(map_fragment, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to read image from path: {map_fragment}")
        return image

    if isinstance(map_fragment, np.ndarray):
        return map_fragment

    if isinstance(map_fragment, Image):
        image_rgb = np.array(map_fragment)
        return cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

    raise TypeError(
        f"map_fragment must be a path, numpy or PIL.Image, not {type(map_fragment)}"
    )


def get_trim(screenshot_scale, template_scale):
    combined_scale = template_scale / screenshot_scale
    fringe_margin = int(TEMPLATE_NODE_PORTAL_FULL_W * 0.9 * combined_scale)

    return {
        "top_detect": int(TRIM_TOP_PX * template_scale),
        "left_detect": int(TRIM_LEFT_PX * template_scale),
        "right_detect": int(TRIM_RIGHT_PX * template_scale),
        "top": int(TRIM_TOP_PX * combined_scale),
        "left": int(TRIM_LEFT_PX * combined_scale),
        "right": int(TRIM_RIGHT_PX * combined_scale),
        "fringe": fringe_margin,
        "fringe_left_soft": fringe_margin // 4,
    }


def _trim_map(map_image, trim):
    top = trim["top_detect"]
    left = trim["left_detect"]
    right = trim["right_detect"]

    grayscale_image = cv2.cvtColor(map_image, cv2.COLOR_BGR2GRAY)
    grayscale_region = grayscale_image[top:, left:-right]
    color_region = map_image[top:, left:-right]
    return grayscale_region, color_region


def _get_active_templates(templates):
    # look only for active mods
    active_node_types = set()
    active_modifier_types = set()

    for combination in ScoreTable.current():
        active_node_types.add(combination[:2])
        if len(combination) > 2:
            active_modifier_types.add(combination[2:4])

    passthrough_node_types = PASSTHROUGH_NODES.get(
        ScoreTable.active_season,
        PASSTHROUGH_NODES["default"],
    )

    node_templates = {
        name: template
        for name, template in templates.node_templates_scaled.items()
        if name[:2].upper() in active_node_types
           or name[:2].upper() in passthrough_node_types
    }
    modifier_templates = {
        name: template
        for name, template in templates.modifier_templates_scaled.items()
        if name[:2].upper() in active_modifier_types
    }

    return node_templates, modifier_templates


def _non_max_suppression(points, result_shape, template_width, template_height):
    taken = []
    occupied = np.zeros(result_shape, dtype=np.uint8)

    for x, y in points:
        if occupied[y, x] == 1:
            continue
        taken.append((x, y))

        y_start = max(0, y - template_height // 2)
        y_end = y + template_height // 2
        x_start = max(0, x - template_width // 2)
        x_end = x + template_width // 2
        occupied[y_start:y_end, x_start:x_end] = 1

    return taken


def _detect_templates(
        screenshot_gray,
        screenshot_bgr,
        templates,
        screenshot_index,
        threshold=Settings.threshold,
        color_max_diff=COLOR_MAX_DIFF,
        debug=False,
):
    detected_candidates = []
    template_color_cache = {}
    color_passed_count = 0
    glow_passed_count = 0
    color_rejected_count = 0

    thresholded_screenshot = threshold_gray(screenshot_gray, IMAGE_LEVELS, screenshot_index)

    for template_name, template in templates.items():
        if template_name.endswith("_glow"):
            continue

        template_gray, mask, _, _ = template
        template_height, template_width = template_gray.shape
        thresholded_template = threshold_gray(template_gray, TEMPLATE_LEVELS)

        match_scores = cv2.matchTemplate(
            thresholded_screenshot,
            thresholded_template,
            cv2.TM_SQDIFF_NORMED,
            mask=mask,
        )

        neighborhood_size = max(
            1,
            template_height // 2,
            template_width // 2,
        )
        eroded_scores = cv2.erode(
            match_scores,
            np.ones((neighborhood_size, neighborhood_size), dtype=np.uint8),
        )
        local_minima = match_scores == eroded_scores
        candidate_mask = (match_scores <= threshold) & local_minima
        candidate_y, candidate_x = np.where(candidate_mask)
        if candidate_y.size == 0:
            continue

        candidate_scores = match_scores[candidate_y, candidate_x]
        score_order = np.argsort(candidate_scores)
        candidate_x = candidate_x[score_order]
        candidate_y = candidate_y[score_order]

        candidate_positions = _non_max_suppression(
            list(zip(candidate_x, candidate_y)),
            match_scores.shape,
            template_width,
            template_height,
        )

        node_type = template_name[:2].upper()
        glow_template_name = f"{template_name}_glow"
        glow_template = templates.get(glow_template_name)

        for x, y in candidate_positions:
            center_x = x + template_width // 2
            center_y = y + template_height // 2
            match_score = float(match_scores[y, x])

            # First pass: normal color verification
            color_ok = _verify_template_color(
                screenshot_bgr=screenshot_bgr,
                template=template,
                template_name=template_name,
                x=x,
                y=y,
                template_color_cache=template_color_cache,
                color_max_diff=color_max_diff,
                debug=debug
            )

            if color_ok:
                color_passed_count += 1
            # Second pass: glow color verification, only leftmost screenshot could ever glow
            elif screenshot_index == 0 and glow_template is not None:
                color_ok = _verify_template_color(
                    screenshot_bgr=screenshot_bgr,
                    template=glow_template,
                    template_name=glow_template_name,
                    x=x,
                    y=y,
                    template_color_cache=template_color_cache,
                    color_max_diff=color_max_diff * 2,
                    debug=debug,
                )

                if color_ok:
                    glow_passed_count += 1

            if not color_ok:
                color_rejected_count += 1
                continue

            detected_candidates.append((
                center_x,
                center_y,
                node_type,
                match_score,
            ))

    if debug or Settings.testmode:
        print(
            f"[DetectNodes] passed:{color_passed_count:2d}, "
            f"glowPassed:{glow_passed_count:2d}, "
            f"rejected:{color_rejected_count}"
        )

    return detected_candidates


def _create_nodes(node_candidates, screenshot_index, screenshot_scale):
    node_candidates.sort(key=lambda candidate: candidate[3], reverse=False)

    nodes = []
    # deduplicate nodes
    deduplicate_distance_squared = int(50 / screenshot_scale) ** 2

    for center_x, center_y, node_type, _match_score in node_candidates:
        is_duplicate = any(
            (center_x - node.x) ** 2 + (center_y - node.y) ** 2
            < deduplicate_distance_squared
            for node in nodes
        )
        if is_duplicate:
            continue

        node_id = f"{screenshot_index:02d}{len(nodes):02d}"
        nodes.append(Node(center_x, center_y, node_type, node_id=node_id))

    return nodes


def _assign_modifiers(nodes, modifier_hits, screenshot_scale):
    valid_combinations = ScoreTable.current()

    for modifier_x, modifier_y, modifier_type, _match_score in modifier_hits:
        nearest_node = None
        nearest_distance_squared = float("inf")

        for node in nodes:
            distance_squared = (
                    (modifier_x - node.x) ** 2
                    + (modifier_y - node.y) ** 2
            )
            if distance_squared < nearest_distance_squared:
                nearest_node = node
                nearest_distance_squared = distance_squared

        if nearest_node is None:
            continue

        if nearest_distance_squared >= (130 / screenshot_scale) ** 2:
            # print(f"Mod {modifier_type} with distance {nearest_distance_squared} DISCARDED")
            continue

        if (nearest_node.type + modifier_type) in valid_combinations:
            nearest_node.modifier = modifier_type
            # print(f"Mod {modifier_type} assigned to {nearest_node.type} with distance {nearest_distance_squared}")


def _restore_node_coordinates(nodes, trimmed_image_shape, trim, screenshot_scale):
    _, trimmed_width = trimmed_image_shape[:2]
    top_offset = trim["top"]
    left_offset = trim["left"]

    for node in nodes:
        if (
                node.x <= trim["fringe_left_soft"] * screenshot_scale
                or node.x >= trimmed_width - trim["fringe"] * screenshot_scale
        ):
            node.is_fringe = True

        node.x = int(node.x / screenshot_scale) + left_offset
        node.y = int(node.y / screenshot_scale) + top_offset


def detect_nodes(
        screenshot_str_or_img,
        templates: TemplateLibrary,
        screenshot_index=0,
        threshold=Settings.threshold,
        screenshot_scale=1.0,
        filter_fringe=True,
):
    screenshot = _load_map_image(screenshot_str_or_img)
    if Settings.testmode:
        print(
            f"[DetectNodes] "
            f"step {screenshot_index}; screenshot_scale = {screenshot_scale}, "
            f"thresh = {threshold}, templates_scale = {templates.last_scale}"
        )

    screenshot_height, screenshot_width = screenshot.shape[:2]
    if screenshot_scale != 1.0:
        screenshot = cv2.resize(
            screenshot,
            (
                int(screenshot_width * screenshot_scale),
                int(screenshot_height * screenshot_scale),
            ),
            interpolation=cv2.INTER_AREA,
        )

    trim = get_trim(screenshot_scale, templates.last_scale)
    screenshot_gray, screenshot_bgr = _trim_map(screenshot, trim)
    node_templates, modifier_templates = _get_active_templates(templates)

    node_candidates = _detect_templates(
        screenshot_gray,
        screenshot_bgr,
        node_templates,
        screenshot_index,
        threshold=threshold,
        color_max_diff=COLOR_MAX_DIFF,
    )
    nodes = _create_nodes(
        node_candidates,
        screenshot_index,
        screenshot_scale,
    )

    # detect modifiers
    modifier_candidates = _detect_templates(
        screenshot_gray,
        screenshot_bgr,
        modifier_templates,
        screenshot_index,
        threshold=threshold,
        color_max_diff=COLOR_MAX_DIFF,
    )
    _assign_modifiers(nodes, modifier_candidates, screenshot_scale)

    _restore_node_coordinates(
        nodes,
        screenshot_bgr.shape,
        trim,
        screenshot_scale,
    )

    nodes.sort(key=lambda node: node.x)
    # random waypoint fix, probably not needed now
    # if len(nodes) > 2 and nodes[-1].type == "WA" and nodes[-2].type != "WA" and abs(nodes[-1].x - nodes[-2].x) > 10:
    #     nodes = nodes[:-1]
    if filter_fringe:
        nodes = [node for node in nodes if not node.is_fringe]
    if Settings.testmode:
        print(f"[DetectNodes] final count:{len(nodes)}")

    return nodes


def _run_test_preview():
    from processing.calibrator import perform_or_validate_calibration  # needed only here for quick testing
    from front.unified_preview import UnifiedPreview

    map_folder = get_path(["Test_scans", "Last_scan_result_1080_pathCoveredByTunnel"])
    templates = TemplateLibrary()
    preview = UnifiedPreview(None)
    preview.enable_nodes_preview()
    preview.enable_trim_overlay()
    screenshot_scale = 1.0

    valid_map_names = []
    for map_name in os.listdir(map_folder):
        name, extension = os.path.splitext(map_name)
        if name.endswith("preview") or name.startswith("merged") or extension != ".png":
            continue
        valid_map_names.append((map_name, name))

    for screenshot_index, (map_name, name) in enumerate(valid_map_names):
        map_path = os.path.join(map_folder, map_name)

        if screenshot_index == 0:
            screenshot_scale, _ = perform_or_validate_calibration(
                screenshot=map_path,
                log=lambda message: print(message),
            )
            templates.scale_templates(Settings.template_scale)

        nodes = detect_nodes(
            map_path,
            templates,
            screenshot_index=screenshot_index,
            screenshot_scale=screenshot_scale,
            filter_fringe=False,
        )

        preview.base_img = _load_map_image(map_path)
        preview.set_nodes(nodes)
        # preview.draw_mod_assign_range = True
        preview.save(get_path([map_folder, f"{name}_nodes_preview.png"]))
        print(f"{map_name} done")

    print("Done.")


if __name__ == "__main__":
    _run_test_preview()
