# detect_nodes.py
import os
import cv2
import numpy as np
from PIL.Image import Image

from data.node import Node
from utils.path_converter import get_path
from processing.template_library import TemplateLibrary, TEMPLATE_NODE_PORTAL_FULL_W
from data.settings import Settings
from data.score_table import ScoreTable  # MUST CONTAIN EVERY VALID COMBINATION OF NODE+MODIFIER

"""
Detects nodes on provided screenshot based on templates from TemplateLibrary
"""
# trim params
TRIM_TOP_PX = 120
TRIM_RIGHT_PX = 150
TRIM_LEFT_PX = 150
# color verify params
ALL_CHANNELS_COLOR_MAX_DIFF = 50
SINGLE_COLOR_MAX_DIFF = 10
MAX_LIGHTING_GAIN = 1.25
MIN_LIGHTING_GAIN = 0.75


# validate shape matches against color channels
def _color_verify(map_bgr, tmpl_bgr, mask_idx, x, y, template_name, color_second_pass_cache, debug=False,
                  color_max_diff=SINGLE_COLOR_MAX_DIFF):
    h, w, _ = tmpl_bgr.shape
    patch = map_bgr[y:y + h, x:x + w]
    if patch.shape[:2] != (h, w):
        return False

    # cache template avg
    cache_key = template_name
    if cache_key not in color_second_pass_cache:
        tmpl_pixels = tmpl_bgr[mask_idx]
        tmpl_avg = tmpl_pixels.mean(axis=0)
        color_second_pass_cache[cache_key] = tmpl_avg

    tmpl_avg = color_second_pass_cache[cache_key]
    probe_pixels = patch[mask_idx]
    probe_avg = probe_pixels.mean(axis=0)

    # lighting gain, to fix darkening towards bottom
    num = float(np.dot(probe_avg, tmpl_avg))
    den = float(np.dot(tmpl_avg, tmpl_avg))
    if den <= 1e-6:
        return False
    k = num / den
    k = float(np.clip(k, MIN_LIGHTING_GAIN, MAX_LIGHTING_GAIN))
    tmpl_corrected = tmpl_avg * k

    abs_diff = np.abs(probe_avg - tmpl_corrected)
    max_diff = float(abs_diff.max())

    passed = bool(np.all(abs_diff <= color_max_diff))

    if debug:
        print(
            f"[COLORV] {template_name} | "
            f"tmpl_avg(B,G,R)=({tmpl_avg[0]:4.1f},{tmpl_avg[1]:4.1f},{tmpl_avg[2]:4.1f}) "
            f"probe_avg=({probe_avg[0]:4.1f},{probe_avg[1]:4.1f},{probe_avg[2]:4.1f}) "
            f"gain={k:3.2f} "
            f"corr_diff=({abs_diff[0]:3.1f},{abs_diff[1]:3.1f},{abs_diff[2]:3.1f}) "
            f"max={max_diff:.1f} "
            f"{'PASS' if passed else 'REJECT'}"
        )
    return passed


def _load_map_image(map_fragment):
    if isinstance(map_fragment, str):
        img = cv2.imread(map_fragment, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to read image from path: {map_fragment}")
        return img

    if isinstance(map_fragment, np.ndarray):
        return map_fragment

    if isinstance(map_fragment, Image):
        bgr = np.array(map_fragment)
        return cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR)

    raise TypeError(f"map_fragment must be a path, numpy or PIL.Image, not {type(map_fragment)}")


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


def _trim_map(map_img, trim):
    top = trim["top_detect"]
    left = trim["left_detect"]
    right = trim["right_detect"]

    gray = cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY)
    gray_trim = gray[top:, left:-right]
    bgr_trim = map_img[top:, left:-right]
    return gray_trim, bgr_trim


def _non_max_suppression(points, shape, w, h):
    taken = []
    occupied = np.zeros(shape, dtype=np.uint8)
    for (x, y) in points:
        if occupied[y, x] == 1:
            continue
        taken.append((x, y))
        y0 = max(0, y - h // 2)
        y1 = y + h // 2
        x0 = max(0, x - w // 2)
        x1 = x + w // 2
        occupied[y0:y1, x0:x1] = 1
    return taken


def _detect_templates(map_gray, map_bgr, templates, threshold):
    candidates = []
    color_second_pass_cache = {}

    for label, (tmpl_gray, mask, tmpl_bgr, mask_idx) in templates.items():
        # handle glow as addition to normal node
        if label == "normal_glow":
            continue

        # the most expensive part, keep template num to minimum!
        h, w = tmpl_gray.shape
        res = cv2.matchTemplate(
            map_gray,
            tmpl_gray,
            cv2.TM_CCORR_NORMED,
            mask=mask
        )

        # local max filter; neighborhood size ~ template size / 2
        neigh = max(1, max(h // 2, w // 2))
        dilated = cv2.dilate(res, np.ones((neigh, neigh), dtype=np.float32))
        local_max = (res == dilated)

        cand_mask = (res >= threshold) & local_max
        ys, xs = np.where(cand_mask)
        if ys.size == 0:
            continue

        scores = res[ys, xs]
        order = np.argsort(scores)[::-1]
        xs = xs[order]
        ys = ys[order]

        pts = list(zip(xs, ys))
        taken = _non_max_suppression(pts, res.shape, w, h)
        abbrev = label[:2].upper()

        for (x, y) in taken:
            if not _color_verify(
                    map_bgr=map_bgr,
                    tmpl_bgr=tmpl_bgr,
                    mask_idx=mask_idx,
                    x=x,
                    y=y,
                    template_name=label,
                    color_second_pass_cache=color_second_pass_cache,
            ):
                if label != "normal":
                    continue
                label_g = "normal_glow"
                _, _, tmpl_bgr_g, mask_idx_g = templates[label_g]
                if not _color_verify(
                        map_bgr=map_bgr,
                        tmpl_bgr=tmpl_bgr_g,
                        mask_idx=mask_idx_g,
                        x=x,
                        y=y,
                        template_name=label_g,
                        color_second_pass_cache=color_second_pass_cache,
                        color_max_diff=SINGLE_COLOR_MAX_DIFF * 2,
                ):
                    continue

            score = float(res[y, x])
            cx = x + w // 2
            cy = y + h // 2
            candidates.append((cx, cy, abbrev, score))

    return candidates


def _assign_modifiers(nodes, modifier_hits, screenshot_scale):
    for mx, my, mod, _ in modifier_hits:
        best = None
        best_dist = float("inf")
        for node in nodes:
            d = (mx - node.x) ** 2 + (my - node.y) ** 2
            if d < best_dist:
                best = node
                best_dist = d
        if best is not None:
            if best_dist < (130 / screenshot_scale) ** 2:
                if (best.type + mod) in ScoreTable.current():
                    best.modifier = mod
                    # print(f"Mod {mod} assigned to {best.type} with distance {best_dist}")
            else:
                # print(f"Mod {mod} with distance {best_dist} DISCARDED")
                pass


def detect_nodes(screenshot_str_or_img,
                 templates: TemplateLibrary,
                 screenshot_index=0,
                 threshold=0.98,
                 screenshot_scale=1.0,
                 filter_fringe=True):
    screenshot = _load_map_image(screenshot_str_or_img)
    if Settings.testmode:
        print(
            f"[Testmode] "
            f"Detect nodes step {screenshot_index}; screenshot_scale = {screenshot_scale}, thresh = {threshold}, "
            f"templates_scale = {templates.last_scale}")
    h, w = screenshot.shape[:2]
    if screenshot_scale != 1.0:
        scaled_screenshot = cv2.resize(
            screenshot,
            (int(w * screenshot_scale), int(h * screenshot_scale)),
            interpolation=cv2.INTER_AREA,
        )
    else:
        scaled_screenshot = screenshot

    template_scale = templates.last_scale
    trim = get_trim(screenshot_scale, template_scale)
    map_gray_trimmed, map_bgr_trimmed = _trim_map(scaled_screenshot, trim)

    # look only for active mods
    active_nodes = set()
    active_mods = set()
    for key in ScoreTable.current():
        active_nodes.add(key[:2])
        if len(key) > 2:
            active_mods.add(key[2:4])
    node_templates = {
        k: v
        for k, v in templates.node_templates_scaled.items()
        if k[:2].upper() in active_nodes or k[:2].upper() == "WA"
    }
    modifier_templates = {
        k: v
        for k, v in templates.modifier_templates_scaled.items()
        if k[:2].upper() in active_mods
    }

    node_candidates = _detect_templates(map_gray_trimmed, map_bgr_trimmed, node_templates, threshold)
    node_candidates.sort(key=lambda c: c[3], reverse=True)

    nodes = []
    counter = 0

    # deduplicate nodes
    deduplicate_area = int((50 / screenshot_scale)) ** 2
    for cx, cy, t, score in node_candidates:
        keep = True
        for n in nodes:
            if (cx - n.x) ** 2 + (cy - n.y) ** 2 < deduplicate_area:
                keep = False
                break

        if keep:
            node_id = f"{screenshot_index:02d}{counter:02d}"
            counter += 1
            nodes.append(Node(cx, cy, t, node_id=node_id))

    # detect modifiers
    modifier_hits = _detect_templates(map_gray_trimmed, map_bgr_trimmed, modifier_templates, threshold)
    _assign_modifiers(nodes, modifier_hits, screenshot_scale)

    h, w = map_bgr_trimmed.shape[:2]
    top_offset = trim["top"]
    left_offset = trim["left"]
    for node in nodes:
        if node.x <= trim["fringe_left_soft"] * screenshot_scale or node.x >= w - trim["fringe"] * screenshot_scale:
            node.is_fringe = True
        node.x = int(node.x / screenshot_scale) + left_offset
        node.y = int(node.y / screenshot_scale) + top_offset

    nodes.sort(key=lambda n: n.x)
    # random waypoint fix, probably not needed now
    # if len(nodes) > 2 and nodes[-1].type == "WA" and nodes[-2].type != "WA" and abs(nodes[-1].x - nodes[-2].x) > 10:
    #     nodes = nodes[:-1]
    if filter_fringe:
        nodes = [n for n in nodes if not n.is_fringe]
    return nodes


if __name__ == "__main__":
    from processing.calibrator import perform_calibration_exact  # needed only here for quick testing
    from front.unified_preview import UnifiedPreview

    map_folder = get_path(["Test_scans", "Last_scan_result_1080_pathCoveredByTunnel"])
    # maps = ["map_frag_02.png", ]
    maps = os.listdir(map_folder)
    templates = TemplateLibrary()
    preview = UnifiedPreview(None)
    preview.enable_nodes_preview()
    preview.enable_trim_overlay()
    screenshot_scale = 1.0
    for i, map_name in enumerate(maps):
        name, ext = map_name.split('.')
        if name.endswith("preview") or name.startswith("merged") or not ext.endswith("png"):
            i -= 1
            continue
        map_path = os.path.join(map_folder, map_name)
        if i == 0:
            screenshot_scale, _ = perform_calibration_exact(screenshot=map_path, log=lambda msg: print(msg))
            templates.scale_templates(Settings.template_scale)
        nodes = detect_nodes(map_path, templates, screenshot_scale=screenshot_scale, filter_fringe=False)
        print(f"Detected {len(nodes)} nodes")
        preview.base_img = _load_map_image(map_path)
        preview.set_nodes(nodes)
        # preview.draw_mod_assign_range = True
        preview.save(get_path([map_folder, f"{name}_nodes_preview.png"]))
        print(f"{map_name} done")
    print("Done.")
