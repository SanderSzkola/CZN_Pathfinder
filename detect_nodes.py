# detect_nodes.py
import os
from datetime import datetime
import cv2
import numpy as np
from PIL.Image import Image

from node import Node
from path_converter import get_path
from template_library import TemplateLibrary
from settings import Settings
from score_table import ScoreTable

"""
Detects nodes on provided screenshot based on templates from TemplateLibrary
"""
TRIM_TOP_PX = 120
TRIM_RIGHT_PX = 120
TRIM_LEFT_PX = 120
COLOR_MAX_DIFF = 50
FRINGE_SAFETY_MARGIN = 120 + TRIM_RIGHT_PX  # this close to map edge means it still should be marked, but discarded after preview
SCORE_TABLE = ScoreTable().table  # MUST CONTAIN EVERY VALID COMBINATION OF NODE+MODIFIER


def color_verify(map_img, tmpl_rgb, mask_idx, x, y):
    h, w, _ = tmpl_rgb.shape
    patch = map_img[y:y + h, x:x + w]
    if patch.shape[:2] != (h, w):
        return False

    diff = cv2.absdiff(patch, tmpl_rgb)
    diff = diff[mask_idx]
    return float(np.mean(diff)) < COLOR_MAX_DIFF


def _load_map_image(map_fragment):
    if isinstance(map_fragment, str):
        img = cv2.imread(map_fragment, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to read image from path: {map_fragment}")
        return img

    if isinstance(map_fragment, np.ndarray):
        return map_fragment

    if isinstance(map_fragment, Image):
        rgb = np.array(map_fragment)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    raise TypeError(f"map_fragment must be a path, numpy or PIL.Image, not {type(map_fragment)}")


def _trim_map(map_img, scale):
    top = int(TRIM_TOP_PX * scale)
    right = int(TRIM_RIGHT_PX * scale)
    left = int(TRIM_LEFT_PX * scale)

    gray = cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY)
    gray_trim = gray[top:, left:-right]
    rgb_trim = map_img[top:, left:-right]
    return gray_trim, rgb_trim


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


def _detect_templates(map_gray, map_rgb, templates, threshold):
    candidates = []

    for label, (tmpl_gray, mask, tmpl_rgb, mask_idx) in templates.items():
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
            if not color_verify(map_rgb, tmpl_rgb, mask_idx, x, y):
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
                if (best.type + mod) in SCORE_TABLE:
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

    map_gray_trimmed, map_rgb_trimmed = _trim_map(scaled_screenshot, screenshot_scale)

    node_candidates = _detect_templates(map_gray_trimmed, map_rgb_trimmed, templates.node_templates_scaled, threshold)
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
    threshold -= 0.005  # mod detection fails way too often; TODO: maybe replace mod images?
    modifier_hits = _detect_templates(map_gray_trimmed, map_rgb_trimmed, templates.modifier_templates_scaled, threshold)
    _assign_modifiers(nodes, modifier_hits, screenshot_scale)

    top_offset = int(TRIM_TOP_PX)
    left_offset = int(TRIM_LEFT_PX)
    fringe_safety_margin = int(FRINGE_SAFETY_MARGIN * Settings.get_scale())
    for node in nodes:
        node.x = int(node.x / screenshot_scale) + left_offset
        node.y = int(node.y / screenshot_scale) + top_offset
        if node.x <= fringe_safety_margin / 4 or node.x >= w - fringe_safety_margin:
            node.is_fringe = True

    nodes.sort(key=lambda n: n.x)
    # random waypoint fix is back :(
    if len(nodes) > 2 and nodes[-1].type == "WA" and nodes[-2].type != "WA" and abs(nodes[-1].x - nodes[-2].x) > 10:
        nodes = nodes[:-1]
    if filter_fringe:
        nodes = [n for n in nodes if not n.is_fringe]
    return nodes


if __name__ == "__main__":
    from calibrator import perform_calibration_exact  # needed only here for quick testing
    from unified_preview import UnifiedPreview

    map_folder = get_path(["Test_scans", "Last_scan_result_1080_pathCoveredByTunnel"])
    # maps = ["map_frag_02.png", ]
    maps = os.listdir(map_folder)
    templates = TemplateLibrary()
    preview = UnifiedPreview(None)
    preview.enable_nodes_preview()
    preview.enable_trim_overlay()
    for i, map_name in enumerate(maps):
        name, ext = map_name.split('.')
        if name.endswith("preview") or name.startswith("merged") or not ext.endswith("png"):
            i -= 1
            continue
        map_path = os.path.join(map_folder, map_name)
        if i == 0:
            perform_calibration_exact(screenshot=map_path, log=lambda msg: print(msg))
            templates.scale_templates(Settings.template_scale)
        nodes = detect_nodes(map_path, templates, filter_fringe=False)
        preview.base_img = _load_map_image(map_path)
        preview.set_nodes(nodes)
        preview.save(get_path([map_folder, f"{name}_nodes_preview.png"]))
        print(f"{map_name} done")
    print("Done.")
