import math
import os

import cv2
import numpy as np
from PIL.Image import Image

from detect_nodes import TemplateLibrary


PX_TOLERANCE = 16
CORRIDOR_HALF = 16
CORRIDOR_OFFSET = 10
THRESHOLD = 128
CONNECTION_WHITE_RATIO = 0.05
ORIENTATION_ANGLE_DEG = 20


# ------------------------------------------------------------
# Image handling
# ------------------------------------------------------------

def _ensure_gray(map_fragment):
    if isinstance(map_fragment, str):
        img = cv2.imread(map_fragment, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to read image from path: {map_fragment}")
    elif isinstance(map_fragment, Image):
        img = np.array(map_fragment)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    else:
        img = map_fragment

    return img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ------------------------------------------------------------
# Node grouping
# ------------------------------------------------------------

def _group_columns(nodes):
    xs = sorted(n.x for n in nodes)
    columns = []

    for x in xs:
        if not any(abs(c - x) <= PX_TOLERANCE for c in columns):
            columns.append(x)

    columns.sort()

    col_assign = {}
    for n in nodes:
        best_col = None
        best_dist = float("inf")
        for ci, cx in enumerate(columns):
            d = abs(n.x - cx)
            if d < best_dist:
                best_dist = d
                best_col = ci
        col_assign[n] = best_col

    for n in nodes:
        n.col = col_assign[n]

    return columns, col_assign


def _group_rows(nodes):
    ys = sorted(n.y for n in nodes)
    bands = []

    for y in ys:
        if not any(abs(b - y) <= PX_TOLERANCE for b in bands):
            bands.append(y)

    bands.sort()

    for n in nodes:
        best_row = None
        best_dist = float("inf")
        for ri, ry in enumerate(bands):
            d = abs(n.y - ry)
            if d < best_dist:
                best_row = ri
                best_dist = d
        n.row = best_row

    return nodes


# ------------------------------------------------------------
# Corridor extraction and orientation
# ------------------------------------------------------------

def _corridor_patch(map_gray, n1, n2):
    mx = int((n1.x + n2.x) * 0.5)
    my = int((n1.y + n2.y) * 0.5) + CORRIDOR_OFFSET
    r = CORRIDOR_HALF

    y1 = max(0, my - r)
    y2 = min(map_gray.shape[0], my + r)
    x1 = max(0, mx - r)
    x2 = min(map_gray.shape[1], mx + r)

    return map_gray[y1:y2, x1:x2], mx, my


def _corridor_orientation(patch_bin):
    ys, xs = np.where(patch_bin == 1)
    if xs.size < 3:
        return None

    try:
        a, _ = np.polyfit(xs, ys, 1)
    except Exception:
        return None

    angle = math.degrees(math.atan(a))

    if abs(angle) <= ORIENTATION_ANGLE_DEG:
        return "same"
    return "down" if a > 0 else "up"


# ------------------------------------------------------------
# Edge crossing detection
# ------------------------------------------------------------

def _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    def orient(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    o1 = orient(x1, y1, x2, y2, x3, y3)
    o2 = orient(x1, y1, x2, y2, x4, y4)
    o3 = orient(x3, y3, x4, y4, x1, y1)
    o4 = orient(x3, y3, x4, y4, x2, y2)

    return (o1 * o2 < 0) and (o3 * o4 < 0)


# ------------------------------------------------------------
# Main detection
# ------------------------------------------------------------

def detect_connections(map_fragment, templates, nodes=None, screenshot_index=0):
    map_img, map_gray = _ensure_gray(map_fragment)

    if nodes is None:
        from detect_nodes import detect_nodes
        nodes = detect_nodes(
            map_fragment,
            templates,
            screenshot_index=screenshot_index,
            create_preview=False
        )

    columns, _ = _group_columns(nodes)
    nodes = _group_rows(nodes)
    nodes.sort(key=lambda n: (n.col, n.row, n.y))

    col_buckets = {}
    for n in nodes:
        col_buckets.setdefault(n.col, []).append(n)

    edges_raw = []
    corridor_debug = []

    for n in nodes:
        next_col = n.col + 1
        if next_col not in col_buckets:
            continue

        for m in col_buckets[next_col]:
            patch, mx, my = _corridor_patch(map_gray, n, m)
            if patch.size == 0:
                continue

            patch_bin = (patch >= THRESHOLD).astype(np.uint8)
            white_ratio = float(np.mean(patch_bin == 1))

            if white_ratio < CONNECTION_WHITE_RATIO:
                corridor_debug.append((mx, my, False))
                continue

            orientation = _corridor_orientation(patch_bin)
            if orientation is None:
                corridor_debug.append((mx, my, False))
                continue

            dy = m.y - n.y
            if abs(dy) <= PX_TOLERANCE:
                expected = "same"
            elif dy > 0:
                expected = "down"
            else:
                expected = "up"

            accepted = (orientation == expected)
            corridor_debug.append((mx, my, accepted))

            if accepted:
                row_jump = abs(n.row - m.row)
                edges_raw.append((n, m, row_jump, white_ratio))

    # ------------------------------------------------------------
    # Crossing cleanup
    # ------------------------------------------------------------

    edges_final = edges_raw.copy()
    changed = True

    while changed:
        changed = False
        to_remove = None

        for i in range(len(edges_final)):
            n1, m1, j1, w1 = edges_final[i]

            for j in range(i + 1, len(edges_final)):
                n2, m2, j2, w2 = edges_final[j]

                if n1.col != n2.col or m1.col != m2.col:
                    continue

                reversed_order = (
                    (n1.row < n2.row and m1.row > m2.row) or
                    (n1.row > n2.row and m1.row < m2.row)
                )

                if reversed_order:
                    if j1 > j2:
                        to_remove = i
                    elif j2 > j1:
                        to_remove = j
                    else:
                        to_remove = i if w1 < w2 else j

                    changed = True
                    break

            if changed:
                break

        if changed:
            edges_final.pop(to_remove)

    edges = [(n.id, m.id) for n, m, _, _ in edges_final]
    return nodes, edges, corridor_debug


# ------------------------------------------------------------
# Preview rendering
# ------------------------------------------------------------

def render_preview(map_name, nodes, edges, corridor_debug):
    base = cv2.imread(map_name, cv2.IMREAD_COLOR)
    overlay = (base.astype(np.float32) * 0.1).astype(np.uint8)

    node_by_id = {n.id: n for n in nodes}

    for mx, my, accepted in corridor_debug:
        offset = 1 if accepted else -1
        r = CORRIDOR_HALF
        x1 = mx - r + offset
        y1 = my - r + offset
        x2 = mx + r + offset
        y2 = my + r + offset

        color = (0, 255, 0) if accepted else (0, 0, 255)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

    for id1, id2 in edges:
        if id1 in node_by_id and id2 in node_by_id:
            n = node_by_id[id1]
            m = node_by_id[id2]
            cv2.line(overlay, (n.x, n.y), (m.x, m.y), (255, 255, 255), 2)

    result = cv2.addWeighted(base, 0.2, overlay, 0.8, 0)

    type_to_file = {}
    for file in os.listdir("Encounter"):
        if file.lower().endswith(".png"):
            name = os.path.splitext(file)[0].lower()
            type_to_file[name[:2].upper()] = os.path.join("Encounter", file)

    for n in nodes:
        if n.type not in type_to_file:
            continue

        icon = cv2.imread(type_to_file[n.type], cv2.IMREAD_UNCHANGED)
        if icon is None:
            continue

        if icon.shape[2] == 4:
            b, g, r, a = cv2.split(icon)
            icon_rgb = cv2.merge([b, g, r])
            mask = a.astype(bool)
        else:
            icon_rgb = icon
            mask = None

        h, w = icon_rgb.shape[:2]
        x1 = n.x - w // 2
        y1 = n.y - h // 2

        if x1 < 0 or y1 < 0 or x1 + w > result.shape[1] or y1 + h > result.shape[0]:
            continue

        roi = result[y1:y1 + h, x1:x1 + w]

        if mask is not None:
            roi[mask] = icon_rgb[mask]
        else:
            roi[:] = icon_rgb

    cv2.imwrite(f"{map_name.split('.')[0]}_connections_preview.png", result)



if __name__ == "__main__":
    map_folder = "Map_gui_test_1/"
    maps = {"map_frag_0.png",}
    #maps = os.listdir(map_folder)
    templates = TemplateLibrary("Encounter_minimal")
    for i, map_name in enumerate(maps):
        name, ext = map_name.split('.')
        if name.endswith("preview") or name.startswith("merged") or not ext.endswith("png"):
            continue
        map_path = map_folder + map_name
        nodes, edges, corridor_debug = detect_connections(map_path, templates, screenshot_index=i)
        render_preview(map_path, nodes, edges, corridor_debug)
        print(f"{map_name} done")
    print("Done.")
