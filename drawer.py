import json
import os
from typing import List, Optional, Union
from path_converter import get_path

import cv2
import numpy as np

GRID = 70
ICON_SCALE = 0.35


def load_map(path: str):
    """Load nodes and edges from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)
    nodes = {n["id"]: n for n in data["nodes"]}
    edges = data["edges"]
    return nodes, edges, data


def load_icon(folder: str, key: Optional[str]):
    """Load PNG icon from folder based on a prefix match."""
    if not key:
        return None
    key = key.upper()
    for file in os.listdir(folder):
        if not file.lower().endswith(".png"):
            continue
        name = os.path.splitext(file)[0].lower()
        if name.startswith(key.lower()):
            return cv2.imread(os.path.join(folder, file), cv2.IMREAD_UNCHANGED)
    return None


def paste_icon_exact(dst: np.ndarray, icon: np.ndarray, px: int, py: int):
    """Paste icon (with alpha) onto RGBA destination image."""
    H, W = icon.shape[:2]
    if px >= dst.shape[1] or py >= dst.shape[0] or px + W <= 0 or py + H <= 0:
        return

    x1c = max(0, px)
    y1c = max(0, py)
    x2c = min(dst.shape[1], px + W)
    y2c = min(dst.shape[0], py + H)

    icon_crop = icon[y1c - py:y2c - py, x1c - px:x2c - px]
    roi = dst[y1c:y2c, x1c:x2c]

    if icon_crop.shape[2] == 4:
        b, g, r, a = cv2.split(icon_crop)
        icon_rgb = cv2.merge([b, g, r]).astype(float)
        alpha = a.astype(float) / 255.0
        alpha = np.repeat(alpha[:, :, np.newaxis], 3, axis=2)
        roi[:, :, :3] = roi[:, :, :3] * (1 - alpha) + icon_rgb * alpha
        roi[:, :, 3] = np.clip(roi[:, :, 3] + a, 0, 255)
    else:
        roi[:, :, :3] = icon_crop
        roi[:, :, 3] = 255


def make_tiled_background(img_path: str, height, width) -> np.ndarray:
    """
    Create a symmetric 4-quadrant tile background from the input image,
    then fill the requested (H, W) size, centered.
    Returns an RGBA uint8 image.
    """
    base = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if base is None:
        raise ValueError(f"Cannot load background image: {img_path}")

    # Ensure RGBA
    if base.shape[2] == 3:
        b, g, r = cv2.split(base)
        a = np.full((base.shape[0], base.shape[1]), 255, dtype=np.uint8)
        base = cv2.merge([b, g, r, a])

    # Step 1: vertical mirror → join
    v_mirror = cv2.flip(base, 0)
    top_bottom = np.concatenate((base, v_mirror), axis=0)

    # Step 2: horizontal mirror of the above → join
    h_mirror = cv2.flip(top_bottom, 1)
    quad = np.concatenate((top_bottom, h_mirror), axis=1)

    # Now tile to fill target area centered
    qh, qw = quad.shape[:2]
    out = np.zeros((height, width, 4), dtype=np.uint8)

    cy = height // 2
    cx = width // 2

    # Determine the tile region to copy so that center of tile aligns with center of output
    y0 = cy - qh // 2
    x0 = cx - qw // 2

    for yy in range(0, height, qh):
        for xx in range(0, width, qw):
            y1 = yy + qh
            x1 = xx + qw

            ys = max(yy, 0)
            xs = max(xx, 0)
            ye = min(y1, height)
            xe = min(x1, width)

            out[ys:ye, xs:xe] = quad[ys - yy:ye - yy, xs - xx:xe - xx]

    return out


def draw_map(
        map_data: Union[str, dict],
        best_path: Optional[List[str]] = None,
        output_path: str = None,
) -> np.ndarray:
    """
    Render a map visualization with optional best path overlay.
    Accepts either a dict (pipeline) or a file path (offline).
    """

    encounter_icon_dir = get_path(["Images", "Encounter"])
    modifier_icon_dir = get_path(["Images", "Modifier_1920"])
    if isinstance(map_data, str):
        nodes, edges, _ = load_map(map_data)
    else:
        nodes = {n["id"]: n for n in map_data["nodes"]}
        edges = map_data["edges"]

    if best_path:
        path_edges = set((best_path[i], best_path[i + 1]) for i in range(len(best_path) - 1))
        path_edges |= set((b, a) for (a, b) in path_edges)
    else:
        path_edges = set()

    cols = [n["col"] for n in nodes.values()]
    rows = [n["row"] for n in nodes.values()]
    min_col, max_col = min(cols), max(cols)
    min_row, max_row = min(rows), max(rows)

    col_shift = -min_col + 1
    row_shift = -min_row + 1

    width = (max_col - min_col + 2) * GRID
    height = (max_row - min_row + 2) * GRID
    canvas = np.zeros((height, width, 4), dtype=np.uint8)

    node_render_info = {}

    # Draw base nodes
    for n in nodes.values():
        c = n["col"] + col_shift
        r = n["row"] + row_shift
        x = c * GRID
        y = r * GRID

        icon = load_icon(encounter_icon_dir, n.get("type"))
        if icon is not None:
            h, w = icon.shape[:2]
            Wn = max(1, int(w * ICON_SCALE))
            Hn = max(1, int(h * ICON_SCALE))
            icon_scaled = cv2.resize(icon, (Wn, Hn), interpolation=cv2.INTER_AREA)
            px = x - Wn // 2
            py = y - Hn // 2
            paste_icon_exact(canvas, icon_scaled, px, py)
        else:
            Wn = Hn = GRID // 2

        node_render_info[n["id"]] = (x, y, Wn, Hn)

    # Draw edges (black first, green for path after)
    second_pass = []
    for id1, id2 in edges:
        if id1 not in node_render_info or id2 not in node_render_info:
            continue

        x1, y1, W1, H1 = node_render_info[id1]
        x2, y2, W2, H2 = node_render_info[id2]

        start = (int(x1 + W1 / 2), int(y1))
        end = (int(x2 - W2 / 2), int(y2))

        if (id1, id2) in path_edges:
            second_pass.append((start, end, (0, 255, 0, 255), 4))
        else:
            cv2.line(canvas, start, end, (0, 0, 0, 255), 3)

    for start, end, color, thickness in second_pass:
        cv2.line(canvas, start, end, color, thickness)

    # Draw modifiers
    for n in nodes.values():
        mod = n.get("modifier")
        if not mod:
            continue

        x, y, Wn, Hn = node_render_info[n["id"]]
        mod_icon = load_icon(modifier_icon_dir, mod)
        if mod_icon is None:
            continue

        Hm, Wm = mod_icon.shape[:2]
        Wm = max(1, int(Wm * ICON_SCALE))
        Hm = max(1, int(Hm * ICON_SCALE))
        mod_icon = cv2.resize(mod_icon, (Wm, Hm), interpolation=cv2.INTER_AREA)

        px = int(x + Wn // 2 - Wm)
        py = int(y - Hm - 5)
        paste_icon_exact(canvas, mod_icon, px, py)
    background_path = get_path(["Images", "background_img.png"])
    background = make_tiled_background(background_path, height, width)

    fg = canvas
    bg = background

    # Alpha composite fg over bg
    alpha = fg[:, :, 3].astype(float) / 255.0
    alpha3 = np.repeat(alpha[:, :, None], 3, axis=2)

    out = bg.copy()
    out[:, :, :3] = bg[:, :, :3] * (1 - alpha3) + fg[:, :, :3] * alpha3
    out[:, :, 3] = 255

    canvas = out

    if output_path is not None:
        cv2.imwrite(output_path, canvas)
        print(f"Saved combined preview: {output_path}")

    return canvas


# ----- STANDALONE MODE -----
if __name__ == "__main__":
    with open(get_path(["Example_scan_result", "merged_map.json"]), "r") as f:
        data = json.load(f)
    best_path = data.get("best_path", None)
    draw_map(data, best_path, get_path(["Example_scan_result", "merged_map.png"]))
