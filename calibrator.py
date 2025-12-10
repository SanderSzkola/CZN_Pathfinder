import os
import cv2
import json
import time

from detect_nodes import detect_nodes, _load_map_image

CALIBRATION_FILE = "calibration_result.json"
TEMPLATE_RES = (1920, 1080)


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


def perform_calibration(templates, screenshot, log=lambda msg: None):
    start_time = time.time()
    raw = _load_map_image(screenshot)
    h, w = raw.shape[:2]
    tw, th = TEMPLATE_RES

    if w > tw or h > th:  # highest set of template res, scale down any higher, DO NOT SCALE UP TEMPLATES
        screenshot_scale = 0.5
        scr = cv2.resize(raw, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    else:
        screenshot_scale = 1.0
        scr = raw

    # full scan 0.50 -> 1.00, should cover anything from small up to 4k, (double 1080p?)
    scales = [round(0.50 + i * 0.05, 2) for i in range(11)]
    scales.append(0.667)  # 1280×720, 2560×1440
    scales.append(0.834)  # 1600x900
    scales.sort()

    best_scale = 1.0
    best_count_nodes = -1
    best_count_modifiers = -1
    best_threshold = 0.98
    thresholds = [0.98, 0.975, 0.97]  # lower thresh starts to take 3-5x more time as 0.98, stop at 0.97

    for threshold in thresholds:
        for test_scale in scales:
            templates.scale_templates(test_scale)
            nodes = detect_nodes(scr, templates, screenshot_scale=screenshot_scale, threshold=threshold)

            count_nodes = len(nodes)
            count_modifiers = 0
            for n in nodes:
                if n.modifier is not None:
                    count_modifiers += 1

            better = False
            if count_modifiers > best_count_modifiers:  # mods are hard to detect, highest priority
                better = True
            elif count_modifiers == best_count_modifiers and count_nodes > best_count_nodes:  # may be better, or false-positive, trust it for now
                better = True
            elif (
                    count_modifiers == best_count_modifiers and count_nodes == best_count_nodes  # upgrade res if still the same threshold
                    and threshold == best_threshold):
                better = True

            if better:
                best_scale = test_scale
                best_count_nodes = count_nodes
                best_count_modifiers = count_modifiers
                best_threshold = threshold

            log(f"scale: {test_scale:4.2f}, matches: {count_nodes:2d} nodes and {count_modifiers:2d} modifiers, "
                f"threshold {threshold:5.3f} "
                f"(~{int(tw * test_scale / screenshot_scale):4d}x{int(th * test_scale / screenshot_scale):4d}){'^^' if better else ''}")

    if best_count_nodes == 0:
        raise IOError("Calibrator failed. Is minimap visible? Is game in windowed mode?")

    templates.scale_templates(best_scale)

    with open(CALIBRATION_FILE, "w") as f:
        json.dump({
            "template_scale": best_scale,
            "screenshot_scale": screenshot_scale,
            "threshold": best_threshold,
        }, f, indent=2)

    log(f"Done, took {(time.time() - start_time):3.1f}s")
    log(f"Calibrator: {best_count_nodes} matches, for template scale {best_scale:4.2f} and screenshot scale "
        f"{screenshot_scale:3.1f}, threshold {best_threshold:5.3f}"
        f" (~{int(tw * best_scale / screenshot_scale)}x{int(th * best_scale / screenshot_scale)})")

    return screenshot_scale, best_threshold, True


def perform_calibration_exact(templates, screenshot, log=lambda msg: None):
    raw = _load_map_image(screenshot)
    h, w = raw.shape[:2]
    tw, th = TEMPLATE_RES

    if w > tw or h > th:
        screenshot_scale = 0.5
        scr_w = w // 2
        scr_h = h // 2
        scr = cv2.resize(raw, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    else:
        screenshot_scale = 1.0
        scr = raw
        scr_w, scr_h = w, h

    scale_w = scr_w / tw
    scale_h = scr_h / th

    if abs(scale_w - scale_h) > 0.02:
        log(f"Calibrator: aspect ratio mismatch: {scr_w}×{scr_h}")

    template_scale = round(scale_w + 0.001, 3)
    template_scale = min(template_scale, 1.0)
    templates.scale_templates(template_scale)
    threshold = 0.975

    with open(CALIBRATION_FILE, "w") as f:
        json.dump({
            "template_scale": template_scale,
            "screenshot_scale": screenshot_scale,
            "threshold": threshold,
        }, f, indent=2)

    log(f"Calibrator (exact): screenshot_scale={screenshot_scale}, template_scale={template_scale}")

    return validate_calibration(templates, screenshot, log)
