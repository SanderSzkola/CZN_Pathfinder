# unified_preview.py
import cv2
import numpy as np

from settings import Settings
from detect_connections import load_icon_map
from detect_nodes import FRINGE_SAFETY_MARGIN, TRIM_RIGHT_PX, TRIM_TOP_PX, TRIM_LEFT_PX

CORRIDOR_ALPHA = 0.07

class UnifiedPreview:
    def __init__(self, base_img):
        if base_img is not None:
            self.base_img = base_img.copy()
        self.scale = Settings.get_scale()

        self.dim_background = False
        self.draw_corridors = False
        self.draw_nodes_text = False
        self.draw_fringe_marks = False
        self.draw_node_icons = False
        self.draw_trim_overlay = False
        self.draw_mod_assign_range = False

        self.nodes = []
        self.edges = []
        self.corridor_debug = []
        self._icon_map = None

    def set_nodes(self, nodes):
        self.nodes = nodes

    def set_connections(self, edges, corridor_debug):
        self.edges = edges
        self.corridor_debug = corridor_debug

    def enable_nodes_preview(self, text=True, fringe=True):
        self.draw_nodes_text = text
        self.draw_fringe_marks = fringe

    def enable_connections_preview(self, corridors=True, icons=True, dim=True):
        self.draw_corridors = corridors
        self.draw_node_icons = icons
        self.dim_background = dim

    def enable_trim_overlay(self, enable=True):
        self.draw_trim_overlay = enable

    def _draw_corridors(self, img):
        overlay = img.copy()

        for (x1, y1, x2, y2, h), ok in sorted(
                self.corridor_debug, key=lambda item: item[1]
        ):
            angle = np.arctan2(y2 - y1, x2 - x1)
            nx, ny = -np.sin(angle) * h, np.cos(angle) * h

            pts = np.array([
                (x1 + nx, y1 + ny),
                (x2 + nx, y2 + ny),
                (x2 - nx, y2 - ny),
                (x1 - nx, y1 - ny)
            ], dtype=np.int32)

            color = (0, 255, 0) if ok else (0, 0, 255)
            temp = overlay.copy()
            cv2.fillPoly(temp, [pts], color)

            alpha = CORRIDOR_ALPHA * (3 if ok else 1)
            overlay = cv2.addWeighted(temp, alpha, overlay, 1 - alpha, 0)

            edge = overlay.copy()
            alpha = min(alpha * 1.5, 1.0)
            cv2.polylines(edge, [pts], True, color, 1, cv2.LINE_AA)
            overlay = cv2.addWeighted(edge, alpha, overlay, 1 - alpha, 0)

        return overlay

    def _draw_icons(self, img):
        if self._icon_map is None:
            self._icon_map = load_icon_map()

        for n in self.nodes:
            type_icon = self._icon_map.get(n.type)
            if type_icon is None:
                continue

            mod_icon = None
            if n.modifier is not None:
                mod_icon = self._icon_map.get(n.modifier)

            if self.scale != 1.0:
                type_icon = cv2.resize(
                    type_icon,
                    (int(type_icon.shape[1] * self.scale),
                     int(type_icon.shape[0] * self.scale)),
                    interpolation=cv2.INTER_AREA,
                )
                if mod_icon is not None:
                    mod_icon = cv2.resize(
                        mod_icon,
                        (int(mod_icon.shape[1] * self.scale),
                         int(mod_icon.shape[0] * self.scale)),
                        interpolation=cv2.INTER_AREA,
                    )

            if type_icon.shape[2] == 4:
                cut_x = type_icon.shape[1] // 2
                type_icon = type_icon.copy()
                type_icon[:, cut_x:, 3] = 0

            th, tw = type_icon.shape[:2]
            mh, mw = mod_icon.shape[:2] if mod_icon is not None else (0, 0)
            cx, cy = int(n.x), int(n.y)
            tx = cx - tw // 2
            ty = cy - th // 2

            if (tx < 0 or ty < 0 or
                    tx + tw > img.shape[1] or
                    ty + th > img.shape[0]
            ):
                continue

            # draw type icon
            roi = img[ty:ty + th, tx:tx + tw]
            if type_icon.shape[2] == 4:
                mask = type_icon[:, :, 3].astype(bool)
                roi[mask] = type_icon[:, :, :3][mask]
            else:
                roi[:] = type_icon[:, :, :3]

            # modifier, drawn on top
            if mod_icon is None:
                continue
            mx = cx - mw // 2
            my = ty - mh

            if (mx < 0 or my < 0 or
                    mx + mw > img.shape[1] or
                    my + mh > img.shape[0]
            ):
                continue

            roi = img[my:my + mh, mx:mx + mw]
            if mod_icon.shape[2] == 4:
                mask = mod_icon[:, :, 3].astype(bool)
                roi[mask] = mod_icon[:, :, :3][mask]
            else:
                roi[:] = mod_icon[:, :, :3]

        return img

    def _draw_node_text(self, img):
        for n in self.nodes:
            x = n.x - 40
            y = n.y + 15

            cv2.putText(
                img, n.label(), (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5 * self.scale,
                (0, 0, 0),
                int(7 * self.scale),
                cv2.LINE_AA
            )
            cv2.putText(
                img, n.label(), (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5 * self.scale,
                (80, 240, 0),
                int(4 * self.scale),
                cv2.LINE_AA
            )

        return img

    def _draw_fringe_marks(self, img):
        s = self.scale
        size = int(28 * s)
        thickness_bg = int(8 * s)
        thickness_fg = int(6 * s)

        for n in self.nodes:
            if not n.is_fringe:
                continue

            cx, cy = int(n.x), int(n.y)

            p1 = (cx - size, cy - size)
            p2 = (cx + size, cy + size)
            p3 = (cx - size, cy + size)
            p4 = (cx + size, cy - size)
            cv2.line(img, p1, p2, (0, 0, 0), thickness_bg, cv2.LINE_AA)
            cv2.line(img, p3, p4, (0, 0, 0), thickness_bg, cv2.LINE_AA)
            cv2.line(img, p1, p2, (0, 90, 190), thickness_fg, cv2.LINE_AA)
            cv2.line(img, p3, p4, (0, 90, 190), thickness_fg, cv2.LINE_AA)

        return img

    def _apply_overlay(self, img, mask, color_bgr, alpha_value):
        h, w = img.shape[:2]
        overlay = np.zeros((h, w, 4), dtype=np.uint8)

        step = 40
        for x in range(-h, w + h, step):
            cv2.line(
                overlay,
                (x, 0),
                (x + h, h),
                (*color_bgr, alpha_value),
                9,
                cv2.LINE_AA,
            )

        overlay[:, :, 3] *= (mask // 255)

        bg = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        alpha = overlay[:, :, 3:4] / 255.0
        bg[:, :, :3] = (1.0 - alpha) * bg[:, :, :3] + alpha * overlay[:, :, :3]

        return cv2.cvtColor(bg, cv2.COLOR_BGRA2BGR)

    def _draw_trim(self, img):
        h, w = img.shape[:2]

        s = self.scale
        top = int(TRIM_TOP_PX * s)
        left = int(TRIM_LEFT_PX * s)
        right = int(TRIM_RIGHT_PX * s)
        fringe = int(FRINGE_SAFETY_MARGIN * s * 0.9)  # slightly reduced so it does not obscure very close nodes

        # soft discard
        fringe_mask = np.zeros((h, w), dtype=np.uint8)
        rx0 = max(0, w - (right + fringe))
        rx1 = max(0, w - right)
        if rx1 > rx0:
            fringe_mask[top:h, rx0:rx1] = 255

        lx0 = min(w, left)
        lx1 = min(w, int(left + fringe / 4))
        if lx1 > lx0:
            fringe_mask[top:h, lx0:lx1] = 255

        # hard delete
        hard_mask = np.zeros((h, w), dtype=np.uint8)
        hard_mask[0:top, :] = 255
        hard_mask[top:h, 0:left] = 255
        hard_mask[top:h, w - right:w] = 255

        img = self._apply_overlay(
            img,
            fringe_mask,
            color_bgr=(255, 255, 0),
            alpha_value=70,
        )

        img = self._apply_overlay(
            img,
            hard_mask,
            color_bgr=(0, 192, 255),
            alpha_value=90,
        )

        return img

    def _draw_mod_assign_range(self, img):
        radius = int(130 * self.scale)
        thickness_bg = int(4 * self.scale)
        thickness_fg = int(2 * self.scale)

        for n in self.nodes:
            cx, cy = int(n.x), int(n.y)

            cv2.circle(
                img,
                (cx, cy),
                radius,
                (0, 0, 0),
                thickness_bg,
                cv2.LINE_AA,
            )

            cv2.circle(
                img,
                (cx, cy),
                radius,
                (255, 200, 0),
                thickness_fg,
                cv2.LINE_AA,
            )

        return img

    def render(self):
        img = self.base_img.copy()

        if self.dim_background:
            img = (img.astype(np.float32) * 0.6).astype(np.uint8)

        if self.draw_trim_overlay:
            img = self._draw_trim(img)

        if self.draw_corridors:
            img = self._draw_corridors(img)

        if self.draw_node_icons:
            img = self._draw_icons(img)

        if self.draw_nodes_text:
            img = self._draw_node_text(img)

        if self.draw_fringe_marks:
            img = self._draw_fringe_marks(img)

        if self.draw_mod_assign_range:
            img = self._draw_mod_assign_range(img)

        return img

    def apply_settings(self):
        self.dim_background = Settings.preview_dim_background
        self.draw_corridors = Settings.preview_draw_corridors
        self.draw_nodes_text = Settings.preview_draw_nodes_text
        self.draw_fringe_marks = Settings.preview_draw_fringe_marks
        self.draw_node_icons = Settings.preview_draw_node_icons
        self.draw_trim_overlay = Settings.preview_draw_trim_overlay

    def save(self, filename):
        cv2.imwrite(filename, self.render())
