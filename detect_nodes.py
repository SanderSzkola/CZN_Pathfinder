import os
from datetime import datetime

import cv2
import numpy as np
from PIL.Image import Image

from node import Node
from path_converter import get_path

"""
Handles loading template images and providing them for node/modifier detection.
"""


class TemplateLibrary:
    def __init__(self, encounter_dir="Encounter_minimal_1920", modifier_dir="Modifier_1920"):
        self.node_templates = self._load_templates(get_path(["Images", encounter_dir]))
        self.modifier_templates = self._load_templates(get_path(["Images", modifier_dir]))

    @staticmethod
    def _load_templates(directory):
        templates = {}
        if not os.path.isdir(directory):
            return templates

        for file in os.listdir(directory):
            if file.lower().endswith(".png"):
                name = os.path.splitext(file)[0]
                path = os.path.join(directory, file)
                templates[name] = TemplateLibrary.load_template(path)

        return templates

    @staticmethod
    def load_template(path):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(path)

        has_alpha = img.shape[2] == 4

        if has_alpha:
            b, g, r, a = cv2.split(img)
            rgb = cv2.merge([b, g, r])
            gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
            mask = (a > 0).astype(np.uint8) * 255

            ys, xs = np.where(mask > 0)
            y0, y1 = ys.min(), ys.max()
            x0, x1 = xs.min(), xs.max()

            gray = gray[y0:y1 + 1, x0:x1 + 1]
            rgb = rgb[y0:y1 + 1, x0:x1 + 1]
            mask = mask[y0:y1 + 1, x0:x1 + 1]

        else:
            rgb = img[:, :, :3]
            gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
            mask = np.ones_like(gray, dtype=np.uint8) * 255

        return gray, mask, rgb


def color_verify(map_img, tmpl_rgb, mask, x, y):
    h, w, _ = tmpl_rgb.shape
    patch = map_img[y:y + h, x:x + w]
    if patch.shape[:2] != (h, w):
        return False

    diff = cv2.absdiff(patch, tmpl_rgb)
    diff = diff[mask == 255]
    return float(np.mean(diff)) < 50


def _load_map_image(map_fragment):
    if isinstance(map_fragment, str):
        img = cv2.imread(map_fragment, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to read image from path: {map_fragment}")
        return img

    if isinstance(map_fragment, Image):
        rgb = np.array(map_fragment)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    raise TypeError("map_fragment must be a path or PIL.Image")


def _trim_map(map_img, top=120, right=120):
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

    for label, (tmpl_gray, mask, tmpl_rgb) in templates.items():
        h, w = tmpl_gray.shape

        res = cv2.matchTemplate(
            map_gray,
            tmpl_gray,
            cv2.TM_CCORR_NORMED,
            mask=mask
        )

        ys, xs = np.where(res >= threshold)
        if ys.size == 0:
            continue

        pts = list(zip(xs, ys))
        pts.sort(key=lambda p: res[p[1], p[0]], reverse=True)

        taken = _non_max_suppression(pts, res.shape, w, h)
        abbrev = label[:2].upper()

        for (x, y) in taken:
            if not color_verify(map_rgb, tmpl_rgb, mask, x, y):
                continue

            score = float(res[y, x])
            cx = x + w // 2
            cy = y + h // 2
            candidates.append((cx, cy, abbrev, score))

    return candidates


def _assign_modifiers(nodes, modifier_hits):
    for mx, my, mod, _ in modifier_hits:
        best = None
        best_dist = float("inf")
        for node in nodes:
            d = (mx - node.x) ** 2 + (my - node.y) ** 2
            if d < best_dist:
                best = node
                best_dist = d
        if best is not None:
            best.modifier = mod


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


def detect_nodes(map_fragment, templates: TemplateLibrary, screenshot_index=0,
                 create_preview=False, threshold=0.98):
    map_img = _load_map_image(map_fragment)
    map_gray, map_rgb_trimmed = _trim_map(map_img)

    node_candidates = _detect_templates(map_gray, map_rgb_trimmed, templates.node_templates, threshold)
    node_candidates.sort(key=lambda c: c[3], reverse=True)

    nodes = []
    counter = 0

    # deduplicate nodes
    for cx, cy, t, score in node_candidates:
        keep = True
        for n in nodes:
            if (cx - n.x) ** 2 + (cy - n.y) ** 2 < 2500:
                keep = False
                break

        if keep:
            node_id = f"{screenshot_index:02d}{counter:02d}"
            counter += 1
            nodes.append(Node(cx, cy, t, node_id=node_id))

    # detect modifiers
    modifier_hits = _detect_templates(map_gray, map_rgb_trimmed, templates.modifier_templates, threshold)
    _assign_modifiers(nodes, modifier_hits)

    # restore original screen Y coordinate
    top_offset = 120
    for node in nodes:
        node.y += top_offset

    if create_preview:
        _preview(map_img, nodes, map_fragment)

    nodes.sort(key=lambda n: n.x)

    # remove waypoint false positive
    shops = sum(1 for n in nodes[-4:] if n.type == "RE" and n.modifier == "SH")
    waypoints = sum(1 for n in nodes[-4:] if n.type == "WA")

    if waypoints == 1 and shops >= 2:
        nodes = nodes[:-1]

    return nodes


def pick_template_set(first_img, template_sets):
    """
    template_sets: list of (resolution, encounter_dir, modifier_dir)
    returns: best TemplateLibrary, nodes to maybe reuse, resolution
    """
    best = None
    best_count = -1
    nodes = None
    best_resolution = ""

    for resolution, enc_dir, mod_dir in template_sets:
        templates = TemplateLibrary(encounter_dir=enc_dir, modifier_dir=mod_dir)
        temp_nodes = detect_nodes(first_img, templates, screenshot_index=0)
        count = len(temp_nodes)
        if count > best_count:
            best_count = count
            best = templates
            nodes = temp_nodes
            best_resolution = resolution

    return best, nodes, best_resolution


if __name__ == "__main__":
    templates = TemplateLibrary()
    folder = get_path("Example_scan_result")

    # SINGLE
    path = os.path.join(folder, "map_frag_0.png")
    nodes = detect_nodes(path, templates, create_preview=True)
    for n in nodes:
        print(n)
    print(f"Total nodes: {len(nodes)}")

    # FOLDER
    # for f in os.listdir(folder):
    #     if f.split('.')[0].endswith("preview") or f.startswith("merged"):
    #         continue
    #     if f.split('.')[1] != "png":
    #         continue
    #     path = os.path.join(folder, f)
    #     detections = len(detect_nodes(path, templates, create_preview=True))
    #     print(f"{f} done, {detections} obj detected")

    # TESTS
    # templates = TemplateLibrary(encounter_dir="Encounter")
    # print("Normal icon:")
    # for f in os.listdir(folder):
    #     if f.split('.')[0].endswith("preview") or f.startswith("merged"):
    #         continue
    #     path = os.path.join(folder, f)
    #     detections = len(detect_nodes(path, templates, create_preview=False))
    #     print(f"{f} done, {detections} obj detected")
    #
    # templates = TemplateLibrary(encounter_dir="Encounter_minimal")
    # print("Center part only")
    # for f in os.listdir(folder):
    #     if f.split('.')[0].endswith("preview") or f.startswith("merged"):
    #         continue
    #     path = os.path.join(folder, f)
    #     detections = len(detect_nodes(path, templates, create_preview=True))
    #     print(f"{f} done, {detections} obj detected")
