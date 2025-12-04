import os
import cv2
import numpy as np

from path_converter import get_path


class TemplateLibrary:
    def __init__(self, encounter_dir="Encounter_minimal_1920", modifier_dir="Modifier_1920", scale=1.0):
        # original set loaded once from disk, do not change
        self.node_templates = self._load_templates(get_path(["Images", encounter_dir]))
        self.modifier_templates = self._load_templates(get_path(["Images", modifier_dir]))
        # scaled set
        self.node_templates_scaled = {}
        self.modifier_templates_scaled = {}
        self.scale_templates(scale)

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

    def scale_templates(self, scale: float):
        if scale == 1.0:
            self.node_templates_scaled = self.node_templates.copy()
            self.modifier_templates_scaled = self.modifier_templates.copy()
            return
        self.node_templates_scaled.clear()
        self.modifier_templates_scaled.clear()

        def scale_one(t):
            gray, mask, rgb = t
            h, w = gray.shape
            new_w = int(w * scale)
            new_h = int(h * scale)
            if new_w < 2 or new_h < 2:
                return None

            gray_s = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            mask_s = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            rgb_s = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            return gray_s, mask_s, rgb_s

        for k, v in self.node_templates.items():
            s = scale_one(v)
            if s:
                self.node_templates_scaled[k] = s

        for k, v in self.modifier_templates.items():
            s = scale_one(v)
            if s:
                self.modifier_templates_scaled[k] = s
