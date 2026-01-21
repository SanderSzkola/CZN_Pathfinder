# detect_connections.py
import os
import cv2
import numpy as np
from PIL.Image import Image

from detect_nodes import TemplateLibrary
from path_converter import get_path
from settings import Settings

PX_TOLERANCE = 16
CORRIDOR_HALF = 6
CORRIDOR_OFFSET = 14
THRESHOLD = 128
MIN_CORRIDOR_FILL = 0.50
ANGLE_MERGE_DEG = 10


# ------------------------------------------------------------
# Node grouping
# ------------------------------------------------------------

def group_columns(nodes):
    columns = []
    for x in sorted(n.x for n in nodes):
        if not any(abs(x - cx) <= PX_TOLERANCE for cx in columns):
            columns.append(x)

    for n in nodes:
        n.col = min(range(len(columns)), key=lambda i: abs(n.x - columns[i]))


def group_rows(nodes):
    rows = []
    for y in sorted(n.y for n in nodes):
        if not any(abs(y - ry) <= PX_TOLERANCE for ry in rows):
            rows.append(y)

    for n in nodes:
        n.row = min(range(len(rows)), key=lambda i: abs(n.y - rows[i]))


# ------------------------------------------------------------
# Icon loading & geometry
# ------------------------------------------------------------

def load_icon_map():
    base_paths = [get_path(["Images", "Encounter"]), get_path(["Images", "Modifier_1920"])]
    icons = {}
    for base in base_paths:
        for file in os.listdir(base):
            if not file.lower().endswith(".png"):
                continue
            key = os.path.splitext(file)[0][:2].upper()
            icons[key] = cv2.imread(os.path.join(base, file), cv2.IMREAD_UNCHANGED)

    return icons


def node_edge_point(node, icons, direction):
    icon = icons.get(node.type)
    if icon is None:
        return node.x, node.y

    w = int(icon.shape[1] * Settings.get_scale())
    dx = (w // 2) * direction
    return int(node.x + dx), int(node.y) + int(CORRIDOR_OFFSET * Settings.get_scale())


def ensure_gray(map_fragment):
    if isinstance(map_fragment, str):
        img = cv2.imread(map_fragment, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to read image: {map_fragment}")
    elif isinstance(map_fragment, Image):
        img = cv2.cvtColor(np.array(map_fragment), cv2.COLOR_RGB2BGR)
    else:
        img = map_fragment

    return img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ------------------------------------------------------------
# Corridor
# ------------------------------------------------------------

def extract_corridor(map_gray, n1, n2, icons):
    x1, y1 = node_edge_point(n1, icons, +1)
    x2, y2 = node_edge_point(n2, icons, -1)

    dx, dy = x2 - x1, y2 - y1
    length = float(np.hypot(dx, dy))
    if length < 5:
        return None

    angle = np.degrees(np.arctan2(dy, dx))
    cx, cy = int((x1 + x2) * 0.5), int((y1 + y2) * 0.5)

    rot = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    rotated = cv2.warpAffine(
        map_gray,
        rot,
        (map_gray.shape[1], map_gray.shape[0]),
        flags=cv2.INTER_LINEAR
    )

    half_h = CORRIDOR_HALF
    x1r, x2r = int(cx - length * 0.5), int(cx + length * 0.5)
    y1r, y2r = int(cy - half_h), int(cy + half_h)

    patch = rotated[y1r:y2r, x1r:x2r]
    if patch.size == 0:
        return None

    debug_geom = (x1, y1, x2, y2, half_h)
    return patch, length, debug_geom


def extract_line_components(bin_patch):
    components = []
    num, labels, _, _ = cv2.connectedComponentsWithStats(bin_patch, connectivity=8)

    for lbl in range(1, num):
        ys, xs = np.where(labels == lbl)
        if xs.size < 5:
            continue

        pts = np.column_stack((xs, ys)).astype(np.float32)
        mean = pts.mean(axis=0)
        pts -= mean

        cov = np.cov(pts, rowvar=False)
        eigvals, eigvecs = np.linalg.eig(cov)
        axis = eigvecs[:, np.argmax(eigvals)]

        angle = np.degrees(np.arctan2(axis[1], axis[0]))
        proj = pts @ axis
        length = proj.max() - proj.min()

        components.append((length, angle))

    return components


def merge_longest_lines(components):
    if not components:
        return 0.0

    components.sort(key=lambda x: x[0], reverse=True)
    if len(components) == 1:
        return components[0][0]

    (l1, a1), (l2, a2) = components[:2]
    da = abs((a1 - a2 + 180) % 360 - 180)

    return l1 + l2 if da <= ANGLE_MERGE_DEG else l1


def segments_intersect(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    return (
            orient(a, b, c) * orient(a, b, d) < 0 and
            orient(c, d, a) * orient(c, d, b) < 0
    )


# ------------------------------------------------------------
# Main detection
# ------------------------------------------------------------

def detect_connections(map_fragment, templates, nodes=None, screenshot_index=0):
    _, map_gray = ensure_gray(map_fragment)
    icons = load_icon_map()

    if nodes is None:
        from detect_nodes import detect_nodes
        nodes = detect_nodes(
            map_fragment,
            templates,
            screenshot_index=screenshot_index,
            screenshot_scale=Settings.screenshot_scale,
            threshold=Settings.threshold
        )

    group_columns(nodes)
    group_rows(nodes)
    nodes.sort(key=lambda n: (n.col, n.row))

    columns = {}
    for n in nodes:
        columns.setdefault(n.col, []).append(n)

    edges_raw = []
    corridor_debug = []

    for n in nodes:
        if n.col + 1 not in columns:
            continue

        for m in columns[n.col + 1]:
            result = extract_corridor(map_gray, n, m, icons)
            if result is None:
                continue

            patch, corridor_len, geom = result
            bin_patch = (patch >= THRESHOLD).astype(np.uint8)

            components = extract_line_components(bin_patch)
            eff_len = merge_longest_lines(components)
            fill = eff_len / corridor_len

            accepted = fill >= MIN_CORRIDOR_FILL
            corridor_debug.append((geom, accepted))

            if accepted:
                edges_raw.append((n, m, abs(n.row - m.row), fill))

    edges = edges_raw[:]
    changed = True

    while changed:
        changed = False
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                n1, m1, j1, w1 = edges[i]
                n2, m2, j2, w2 = edges[j]

                if n1.col != n2.col:
                    continue

                if not segments_intersect(
                        (n1.x, n1.y), (m1.x, m1.y),
                        (n2.x, n2.y), (m2.x, m2.y)
                ):
                    continue

                remove = i if (j1 > j2 or (j1 == j2 and w1 < w2)) else j
                edges.pop(remove)
                changed = True
                break
            if changed:
                break

    return nodes, [(n.id, m.id) for n, m, _, _ in edges], corridor_debug


if __name__ == "__main__":
    from calibrator import perform_calibration_exact  # needed only here for quick testing
    from unified_preview import UnifiedPreview

    map_folder = get_path(["Test_scans", "Last_scan_result_1080_pathCoveredByTunnel"])
    # maps = ["map_frag_02.png", ]
    maps = os.listdir(map_folder)
    templates = TemplateLibrary()
    preview = UnifiedPreview(None)
    preview.enable_connections_preview()
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
        nodes, edges, corridor_debug = detect_connections(map_path, templates, screenshot_index=i)
        preview.base_img = ensure_gray(map_path)[0]
        preview.set_nodes(nodes)
        preview.set_connections(edges, corridor_debug)
        preview.save(get_path([map_folder, f"{name}_connections_preview.png"]))
        print(f"{map_name} done")
    print("Done.")
