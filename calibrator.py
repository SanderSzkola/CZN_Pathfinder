from detect_nodes import detect_nodes, detect_nodes_with_preview, _load_map_image
from template_library import TemplateLibrary, TEMPLATE_RES
from settings import Settings

CALIBRATION_FILE = "calibration_result.json"


def check_calibration_done(log=lambda msg: None):
    if not Settings.calibrated():
        log("Please perform calibration first.")
        return False
    return True


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

    if non_normal_nodes > 2:
        Settings.screenshot_scale = screenshot_scale
        Settings.template_scale = template_scale
        Settings.threshold = threshold
        Settings.save()
        saved = True
    else:
        saved = False
    if log:
        log(f"Calibrator: {len(nodes)} matches, including {non_normal_nodes} other than NO \n"
            f"template scale {template_scale}, screenshot scale {screenshot_scale}, "
            f"threshold {threshold:5.3f} "
            f"(~{int(w):4d}x{int(h):4d})\n"
            f"{'Calibration result saved' if saved else 'Calibration result discarded'}")

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
