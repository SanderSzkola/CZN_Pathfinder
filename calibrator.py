import os
import json

from detect_nodes import detect_nodes, detect_nodes_with_preview, _load_map_image
from template_library import TemplateLibrary, TEMPLATE_RES

CALIBRATION_FILE = "calibration_result.json"


def check_calibration_file_exists(log=lambda msg: None):
    if not os.path.isfile(CALIBRATION_FILE):
        log("Calibration file not found. Perform calibration first.")
        return False
    return True


def validate_calibration(templates, screenshot, log=lambda msg: None):
    scr = _load_map_image(screenshot)
    tw, th = TEMPLATE_RES

    if not os.path.isfile(CALIBRATION_FILE):
        raise IOError("Calibration file not found. Perform calibration first.")

    try:
        with open(CALIBRATION_FILE, "r") as f:
            data = json.load(f)
        test_scale = float(data.get("template_scale"))
        screenshot_scale = float(data.get("screenshot_scale"))
        threshold = float(data.get("threshold"))
        templates.scale_templates(test_scale)

        # validate, resolution may have changed
        nodes = detect_nodes(scr, templates, screenshot_scale=screenshot_scale, threshold=threshold)
        non_normal_nodes = 0  # normals match way too often, validate if really correct
        for n in nodes:
            if n.type != "NO":
                non_normal_nodes += 1

        log(f"Calibrator: {len(nodes)} matches, including {non_normal_nodes} other than NO, "
            f"cache loaded with template scale {test_scale} and screenshot scale {screenshot_scale}, "
            f"threshold {threshold:5.3f} "
            f"(~{int(tw * test_scale / screenshot_scale):4d}x{int(th * test_scale / screenshot_scale):4d})")
        if len(nodes) > 4 and non_normal_nodes > 0:
            return screenshot_scale, threshold, True
        else:  # not enough matches, warn
            log(f"Result below good nodes amount, has your setup changed? Consider recalibrating.")
            return screenshot_scale, threshold, False

    except Exception as e:
        raise IOError(f"Unpredicted calibrator error: {e}")


def perform_calibration_exact(screenshot, log=lambda msg: None, template_scale=None,
                              threshold=None):
    templates = TemplateLibrary()
    screenshot_scale, template_scale_t, threshold_t, w, h = get_initial_params(templates, screenshot)
    template_scale = template_scale_t if template_scale is None else template_scale
    threshold = threshold_t if threshold is None else threshold

    templates.scale_templates(template_scale)
    nodes, preview = detect_nodes_with_preview(screenshot, templates, screenshot_scale=screenshot_scale,
                                               threshold=threshold)

    non_normal_nodes = 0  # normals match way too often, validate if really correct
    for n in nodes:
        if n.type != "NO":
            non_normal_nodes += 1
    if log:
        log(f"Calibrator: {len(nodes)} matches, including {non_normal_nodes} other than NO, "
            f"cache loaded with template scale {template_scale} and screenshot scale {screenshot_scale}, "
            f"threshold {threshold:5.3f} "
            f"(~{int(w):4d}x{int(h):4d})")

    with open(CALIBRATION_FILE, "w") as f:
        json.dump({
            "template_scale": template_scale,
            "screenshot_scale": screenshot_scale,
            "threshold": threshold,
        }, f, indent=2)

    return screenshot_scale, threshold, preview


def get_initial_params(templates, screenshot):
    raw = _load_map_image(screenshot)
    h, w = raw.shape[:2]
    tw, th = TEMPLATE_RES

    if w > tw or h > th:
        screenshot_scale = 0.5
        scr_w = w // 2
        scr_h = h // 2
    else:
        screenshot_scale = 1.0
        scr_w, scr_h = w, h

    scale_w = scr_w / tw
    scale_h = scr_h / th

    template_scale = round(scale_w + 0.001, 3)
    template_scale = min(template_scale, 1.0)
    if templates is not None:
        templates.scale_templates(template_scale)
    threshold = 0.98

    return screenshot_scale, template_scale, threshold, w, h
