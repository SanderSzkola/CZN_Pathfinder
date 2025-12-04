import os
import cv2
import json

from detect_nodes import detect_nodes, _load_map_image

CALIBRATION_FILE = "calibration_result.json"


def calibrate(templates, screenshot, log=lambda msg: None):
    raw = _load_map_image(screenshot)
    h, w = raw.shape[:2]

    if w > 1920 or h > 1080:  # highest set of template res, scale down any higher, DO NOT SCALE UP TEMPLATES
        screenshot_scale = 0.5
        scr = cv2.resize(raw, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    else:
        screenshot_scale = 1.0
        scr = raw

    # try cached result first
    if os.path.isfile(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, "r") as f:
                data = json.load(f)
            test_scale = float(data.get("template_scale"))
            screenshot_scale = float(data.get("screenshot_scale", screenshot_scale))
            templates.scale_templates(test_scale)
            # validate, resolution may have changed
            nodes = detect_nodes(scr, templates, screenshot_scale=screenshot_scale)
            if len(nodes) > 5:
                log(f"Calibrator: {len(nodes)} matches, cache loaded")
                return screenshot_scale
            else:
                log(f"Calibrator: {len(nodes)} matches, too low, cache discarded, recalibrating")
        except Exception:
            pass
    else:
        log(f"Calibrator: calibration_result.json not found, starting calibration, it may take a while")

    # full scan 0.50 -> 1.00, should cover anything from small up to 4k, (double 1080p?)
    scales = [round(0.50 + i * 0.05, 2) for i in range(11)]
    best_scale = 1.0
    best_count = -1

    for test_scale in scales:
        templates.scale_templates(test_scale)
        nodes = detect_nodes(scr, templates, screenshot_scale=screenshot_scale)
        count = len(nodes)
        log(f"scale: {test_scale}, matches: {count}")
        if count >= best_count:
            best_scale = test_scale
            best_count = count

    if best_count == 0:
        raise IOError("Calibrator failed. Is minimap visible? Is game in windowed mode?")
    templates.scale_templates(best_scale)

    with open(CALIBRATION_FILE, "w") as f:
        json.dump({
            "template_scale": best_scale,
            "screenshot_scale": screenshot_scale
        }, f, indent=2)
    log(f"Calibrator: {best_count} matches, for template scale {best_scale} and screenshot scale {screenshot_scale}")
    return screenshot_scale
