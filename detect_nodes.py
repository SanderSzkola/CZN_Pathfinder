import os
from datetime import datetime
import cv2
import numpy as np
from PIL.Image import Image
from scipy.ndimage import maximum_filter

from node import Node
from path_converter import get_path
from template_library import TemplateLibrary

"""
Detects nodes on provided screenshot based on templates from TemplateLibrary
"""
TRIM_TOP_PX = 120
TRIM_RIGHT_PX = 120


def color_verify(map_img, tmpl_rgb, mask_idx, x, y):
    h, w, _ = tmpl_rgb.shape
    patch = map_img[y:y + h, x:x + w]
    if patch.shape[:2] != (h, w):
        return False

    diff = cv2.absdiff(patch, tmpl_rgb)
    diff = diff[mask_idx]
    return float(np.mean(diff)) < 45


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
    gray = cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY)
    gray_trim = gray[top:, :-right]
    rgb_trim = map_img[top:, :-right]
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
        local_max = (res == maximum_filter(res, size=neigh))

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
            if best_dist < (130 * screenshot_scale) ** 2:
                best.modifier = mod
                #print(f"Mod {mod} assigned to {best.type} with distance {best_dist}")
            else:
                #print(f"Mod {mod} with distance {best_dist} DISCARDED")
                pass


def _preview(map_img, nodes, map_fragment):
    preview = map_img.copy()
    for node in nodes:
        cv2.putText(
            preview,
            node.label(),
            (node.x, node.y),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (128, 255, 0),
            3,
            cv2.LINE_AA,
        )

    if isinstance(map_fragment, str):
        base = get_path(map_fragment.split(".")[:-1])
        cv2.imwrite(f"{base}_nodes_preview.png", preview)
    else:
        now = datetime.now().strftime("%H%M%S")
        cv2.imwrite(get_path(f"nodes_preview_{now}.png"), preview)


def detect_nodes(screenshot_str_or_img,
                 templates: TemplateLibrary,
                 screenshot_index=0,
                 create_preview=False,
                 threshold=0.98,
                 screenshot_scale=1.0):
    screenshot = _load_map_image(screenshot_str_or_img)
    if screenshot_scale != 1.0:
        h, w = screenshot.shape[:2]
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
    deduplicate_area = int((50 * screenshot_scale)) ** 2
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

    # restore original screen coordinates
    # needed for top and left trim, bottom and right have no influence
    top_offset = int(TRIM_TOP_PX * screenshot_scale)
    for node in nodes:
        node.x = int(node.x / screenshot_scale)
        node.y = int(node.y / screenshot_scale)
        node.y += top_offset

    if create_preview:
        _preview(screenshot, nodes, screenshot_str_or_img)

    nodes.sort(key=lambda n: n.x)

    return nodes


if __name__ == "__main__":
    from calibrator import validate_calibration, perform_calibration  # here bc ide yells about circular dependency
    templates = TemplateLibrary()
    folder = get_path(["Test_scans","Map_live_test_dumpsite_3"])
    # folder = get_path(["Test_scans", "Map_small_res_1"])

    # SINGLE
    path = os.path.join(folder, "map_frag_0.png")
    # perform_calibration(templates, path)  # DO NOT CALIBRATE ON FIRST SCREENSHOT, need more nodes, pick 3rd or something
    screenshot_scale, threshold, calibration_status = validate_calibration(templates, path, log=lambda msg: print(msg))
    nodes = detect_nodes(path, templates, create_preview=True, screenshot_scale=screenshot_scale, threshold=threshold)
    for n in nodes:
        print(n)
    print(f"Total nodes: {len(nodes)}")

    # FOLDER
    # path = os.path.join(folder, "map_frag_4.png")
    # screenshot_scale, threshold, calibration_status = validate_calibration(templates, path, log=lambda msg: print(msg))
    # for f in os.listdir(folder):
    #     if f.split('.')[0].endswith("preview") or f.startswith("merged"):
    #         continue
    #     if f.split('.')[1] != "png":
    #         continue
    #     path = os.path.join(folder, f)
    #     nodes = detect_nodes(path, templates, create_preview=True, screenshot_scale=screenshot_scale, threshold=threshold)
    #     print(f"{f} done, {len(nodes)} obj detected")
