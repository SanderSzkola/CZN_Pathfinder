import json
import os
from typing import List, Optional, Union

import cv2
import numpy as np

from path_converter import get_path

GRID = 70
ICON_SCALE = 0.35
MODIFIER_Y_OFFSET = -4


def load_map(path: str):
    with open(path, "r") as f:
        data = json.load(f)
    nodes = {n["id"]: n for n in data["nodes"]}
    edges = data["edges"]
    return nodes, edges, data


def load_icon(folder: str, key: Optional[str]):
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


def paste_icon(dst: np.ndarray, icon: np.ndarray, px: int, py: int):
    h, w = icon.shape[:2]

    if px >= dst.shape[1] or py >= dst.shape[0] or px + w <= 0 or py + h <= 0:
        return

    x1 = max(0, px)
    y1 = max(0, py)
    x2 = min(dst.shape[1], px + w)
    y2 = min(dst.shape[0], py + h)

    icon_crop = icon[y1 - py:y2 - py, x1 - px:x2 - px]
    roi = dst[y1:y2, x1:x2]

    if icon_crop.shape[2] == 4:
        b, g, r, a = cv2.split(icon_crop)
        rgb = cv2.merge([b, g, r]).astype(float)
        alpha = (a.astype(float) / 255.0)[:, :, None]
        alpha3 = np.repeat(alpha, 3, axis=2)

        roi[:, :, :3] = roi[:, :, :3] * (1 - alpha3) + rgb * alpha3
        roi[:, :, 3] = np.clip(roi[:, :, 3] + a, 0, 255)
    else:
        roi[:, :, :3] = icon_crop
        roi[:, :, 3] = 255


def make_tiled_background(path: str, height: int, width: int):
    base = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if base is None:
        raise ValueError(f"Cannot load background image: {path}")

    if base.shape[2] == 3:
        b, g, r = cv2.split(base)
        a = np.full((base.shape[0], base.shape[1]), 255, dtype=np.uint8)
        base = cv2.merge([b, g, r, a])

    v_mirror = cv2.flip(base, 0)
    tb = np.concatenate((base, v_mirror), axis=0)

    h_mirror = cv2.flip(tb, 1)
    quad = np.concatenate((tb, h_mirror), axis=1)

    qh, qw = quad.shape[:2]
    out = np.zeros((height, width, 4), dtype=np.uint8)

    for yy in range(0, height, qh):
        for xx in range(0, width, qw):
            ys = max(yy, 0)
            xs = max(xx, 0)
            ye = min(yy + qh, height)
            xe = min(xx + qw, width)

            out[ys:ye, xs:xe] = quad[ys - yy:ye - yy, xs - xx:xe - xx]

    return out


def _scale_icon(icon: np.ndarray):
    ih, iw = icon.shape[:2]
    w = max(1, int(iw * ICON_SCALE))
    h = max(1, int(ih * ICON_SCALE))
    return cv2.resize(icon, (w, h), interpolation=cv2.INTER_AREA), w, h


def _collect_path_edges(path: List[str]):
    forward = {(path[i], path[i + 1]) for i in range(len(path) - 1)}
    backward = {(b, a) for (a, b) in forward}
    return forward | backward


def draw_map(
        map_data: Union[str, dict],
        best_path: Optional[List[str]] = None,
        output_path: str = None,
        encounter_ranges: Optional[dict] = None,
        encounter_counts: Optional[dict] = None,
):
    encounter_dir = get_path(["Images", "Encounter"])
    modifier_dir = get_path(["Images", "Modifier_1600"])

    if isinstance(map_data, str):
        nodes, edges, _ = load_map(map_data)
    else:
        nodes = {n["id"]: n for n in map_data["nodes"]}
        edges = map_data["edges"]

    path_edges = _collect_path_edges(best_path) if best_path else set()

    cols = [n["col"] for n in nodes.values()]
    rows = [n["row"] for n in nodes.values()]
    min_col, max_col = min(cols), max(cols)
    min_row, max_row = min(rows), max(rows)

    col_shift = -min_col + 1
    row_shift = -min_row + 1

    width = (max_col - min_col + 2) * GRID
    height = (max_row - min_row + 3) * GRID
    canvas = np.zeros((height, width, 4), dtype=np.uint8)

    node_info = {}

    # draw nodes
    for n in nodes.values():
        cx = (n["col"] + col_shift) * GRID
        cy = (n["row"] + row_shift) * GRID

        icon = load_icon(encounter_dir, n.get("type"))
        if icon is not None:
            icon_scaled, w, h = _scale_icon(icon)
            px = cx - w // 2
            py = cy - h // 2
            paste_icon(canvas, icon_scaled, px, py)
        else:
            w = h = GRID // 2

        node_info[n["id"]] = (cx, cy, w, h)

    # draw edges
    highlight_edges = []
    for a, b in edges:
        if a not in node_info or b not in node_info:
            continue

        x1, y1, w1, h1 = node_info[a]
        x2, y2, w2, h2 = node_info[b]

        start = (int(x1 + w1 / 2), int(y1))
        end = (int(x2 - w2 / 2), int(y2))

        if (a, b) in path_edges:
            highlight_edges.append((start, end))
        else:
            cv2.line(canvas, start, end, (0, 0, 0, 255), 3)

    for start, end in highlight_edges:
        cv2.line(canvas, start, end, (50, 200, 0, 255), 4)

    # modifiers
    for n in nodes.values():
        mod_key = n.get("modifier")
        if not mod_key:
            continue

        cx, cy, w, h = node_info[n["id"]]
        icon = load_icon(modifier_dir, mod_key)
        if icon is None:
            continue

        icon_scaled, mw, mh = _scale_icon(icon)
        px = int(cx + w // 2 - mw)
        py = int(cy - mh + MODIFIER_Y_OFFSET)
        paste_icon(canvas, icon_scaled, px, py)

    # encounter counts
    if encounter_counts:
        row_extra = (max_row - min_row + 2)
        y_grid = row_extra * GRID

        items = list(encounter_counts.items())
        col_positions = [i * 2 + 1 for i in range(len(items))]

        for (key, count), col in zip(items, col_positions):
            x_grid = col * GRID
            enc_key = key[:2]
            mod_key = key[2:] or None

            enc_icon = load_icon(encounter_dir, enc_key)
            if enc_icon is not None:
                enc_scaled, ew, eh = _scale_icon(enc_icon)
            else:
                ew = eh = 0
                enc_scaled = None

            px = x_grid - ew // 2
            py = y_grid - eh // 2

            if enc_scaled is not None:
                paste_icon(canvas, enc_scaled, px, py)
            else:
                cv2.rectangle(canvas,
                              (x_grid - 10, y_grid - 10),
                              (x_grid + 10, y_grid + 10),
                              (0, 0, 0, 255), 2)

            if mod_key:
                mod_icon = load_icon(modifier_dir, mod_key)
                if mod_icon is not None:
                    mod_scaled, mw, mh = _scale_icon(mod_icon)
                    mod_px = x_grid + (ew // 2) - mw
                    mod_py = y_grid - mh + MODIFIER_Y_OFFSET
                    paste_icon(canvas, mod_scaled, mod_px, mod_py)

            # write text
            tx = x_grid + ew // 2 + 4
            ty = y_grid + eh // 4 + 2
            font = cv2.FONT_HERSHEY_PLAIN
            scale = 1.5
            thick = 2
            count_str = str(count)
            min_v, max_v = encounter_ranges[key]
            range_str = f"[{min_v},{max_v}]"

            cv2.putText(canvas, count_str, (tx, ty),
                        font, scale, (50, 200, 0, 255), thick, cv2.LINE_AA)
            w_count = cv2.getTextSize(count_str, font, scale, thick)[0][0]
            x2 = tx + w_count + 4
            cv2.putText(canvas, range_str, (x2, ty),
                        font, scale, (0, 0, 0, 255), thick, cv2.LINE_AA)

    # compose with background
    pad = GRID // 2
    fg = canvas[pad:-pad]

    bg_path = get_path(["Images", "background_img.png"])
    bg = make_tiled_background(bg_path, height - GRID, width)

    bar_h = GRID  # grey bar on bottom
    bar_y0 = bg.shape[0] - bar_h
    gray = np.array([64, 64, 64], dtype=np.float32)
    alpha_bar = 0.67
    bg[bar_y0:, :, :3] = (
            bg[bar_y0:, :, :3].astype(np.float32) * (1 - alpha_bar)
            + gray * alpha_bar
    ).astype(np.uint8)

    alpha = fg[:, :, 3].astype(float) / 255.0
    alpha3 = np.repeat(alpha[:, :, None], 3, axis=2)

    out = bg.copy()
    out[:, :, :3] = bg[:, :, :3] * (1 - alpha3) + fg[:, :, :3] * alpha3
    out[:, :, 3] = 255

    if output_path:
        cv2.imwrite(output_path, out)

    return out


if __name__ == "__main__":
    path = get_path(["Example_scan_result", "merged_map.json"])
    with open(path, "r") as f:
        data = json.load(f)
    best_path = data.get("best_path")
    draw_map(data, best_path, get_path(["Example_scan_result", "merged_map.png"]))
    print("Done")
