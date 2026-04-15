# pipeline.py
import os
import threading
import time
from queue import Queue
import sys

from node import Node
from detect_connections import detect_connections
from detect_nodes import detect_nodes
from template_library import TemplateLibrary
from drawer import draw_map
from grabber import switch_window, screenshot, do_drag_move, move_mouse, mock_switch_window, mock_move_screen, \
    mock_screenshot, DragListener, MockDragListener
from pathfinder import run_pathfinder
from process_map import Finalizer
from path_converter import get_path
from settings import Settings

"""
Full process (may be outdated a bit):
    Grabber switches window
    Grabber takes screenshot
    Pipeline gives screenshot to detect_nodes [2nd thread], then waits
    Detect_nodes finishes, return nodes
    Pipeline passes nodes to grabber and detect_connections [3rd thread]
    Repeat until end detected:
        Grabber moves cursor to last node position, drags minimap to first node position, takes screenshot
        Pipeline passes screenshot to detect_nodes [2nd thread]
        Grabber moves cursor to previous last node position, hoping it is close to next last node position
        Pipeline waits for 2nd thread to finish
        Pipeline passes nodes to grabber and detect_connections [3rd thread]
    Pipeline waits until 3rd thread finishes
    Pipeline sends finished map to Pathfinder, then to Drawer
    Grabber switches window
    Pipeline returns full map, best path and image
    
    All of those threads may still be running on one core, so this was less useful that I thought it would be,
     but it at least allows for mouse movement while processing detect_nodes 
"""


def check_end(nodes, last_nodes):
    """
    Requires 2 sets of nodes, must be called before duplicate check.
    Reason: checking for boss directly is.. complicated, so this method checks instead if two subsequent screenshots ends
    with a column of rests.
    """
    if (last_nodes is None or len(last_nodes) <= 2
            or nodes is None or len(nodes) <= 2):
        return False
    # strong check, <6 columns, single screenshot is enough
    non_empty_columns, _ = check_node_output_quality(nodes)
    if non_empty_columns < 6 and nodes[-1].type == "RE" and (
            nodes[-2].type == "RE" or  # same column must be rest
            abs(nodes[-2].x - nodes[-1].x) > 10):  # other column
        if Settings.testmode:
            print("[Testmode] Check end returned with strong check")
        return True
    # weak check, needs two screenshots
    nodes_last_column = []
    last_col_idx = nodes[-1].col
    no_index_x = 0
    len_dif = 0
    if last_col_idx is None:  # nodes may come before rowcol assignment
        no_index_x = nodes[-1].x
    for n in nodes:
        if last_col_idx and n.col == last_col_idx:
            nodes_last_column.append(n)
            len_dif += 1
        elif abs(no_index_x - n.x) < 10:
            nodes_last_column.append(n)
            len_dif += 1
    last_col_idx = last_nodes[-1].col
    for n in last_nodes:
        if n.col == last_col_idx:
            nodes_last_column.append(n)
            len_dif -= 1
    if len_dif != 0:  # different len of last column -> not the same picture
        return False
    for n in nodes_last_column:
        if n.type != "RE":
            return False
    print("[Testmode] Check end returned with weak check")
    return True


def check_duplicates(nodes, last_nodes):
    if nodes is None or last_nodes is None:
        return False
    if len(nodes) != len(last_nodes):
        return False
    duplicates = 0
    for n1 in nodes:
        for n2 in last_nodes:
            if Node.is_duplicate(n1, n2):
                duplicates += 1
                break
    if duplicates == len(nodes):
        return True
    return False


def check_node_output_quality(nodes):
    c1, c2, c3, c4, c5, c6, c7, c8, c9 = [], [], [], [], [], [], [], [], []
    columns = [c1, c2, c3, c4, c5, c6, c7, c8, c9]
    non_normals = 0
    for node in nodes:
        placed = False
        if node.type != "NO":
            non_normals += 1
        for c in columns:
            if len(c) == 0 or abs(c[0].x - node.x) < 10:
                c.append(node)
                placed = True
                break
        if not placed:
            raise IOError("Got more columns that excepted max, stopping")
    non_empty_columns = 0
    for c in columns:
        if len(c) > 0:
            non_empty_columns += 1
    return non_empty_columns, non_normals


class DetectResult:
    def __init__(self):
        self.lock = threading.Lock()
        self.ready_step = -1
        self.nodes = None


class ExceptionThread(threading.Thread):
    def run(self):
        self.exc_info = None
        try:
            super().run()
        except Exception:
            self.exc_info = sys.exc_info()


def worker_nodes(detect_q: Queue,
                 result: DetectResult,
                 templates,
                 screenshot_scale,
                 threshold):
    while True:
        item = detect_q.get()
        if item is None:
            break

        step, img = item
        nodes = detect_nodes(img, templates, step, screenshot_scale=screenshot_scale, threshold=threshold)
        with result.lock:
            result.ready_step = step
            result.nodes = nodes

        detect_q.task_done()


def worker_connections(
        queue: Queue,
        finalizer: Finalizer,
        templates,
        print_grid: bool = False,
        log=lambda msg: None):
    while True:
        item = queue.get()
        if item is None:
            return

        img, nodes = item
        try:
            nodes_conn, edges_conn, meta = detect_connections(img, templates, nodes)
            finalizer.add_fragment(nodes_conn, edges_conn, print_grid)
        except Exception as e:
            print(
                f"[conn-worker] FATAL error while processing fragment:\n{e}")  # gui log already prints it, no need to log twice
            raise
        finally:
            queue.task_done()


def prepare_clean_folder(base_name: str, log):
    folder = get_path(base_name)
    os.makedirs(folder, exist_ok=True)

    leftovers = os.listdir(folder)
    if leftovers:
        log(f"Deleting {len(leftovers)} old screenshots from {base_name} folder")
        for f in leftovers:
            if f.endswith("png") or f.endswith("json"):
                try:
                    os.remove(os.path.join(folder, f))
                except OSError:
                    log(f"Failed to delete {f}")

    return folder


def run_auto_pipeline(max_steps=15, save_folder=None, print_grid=False, log=lambda msg: None):
    finalizer = Finalizer()
    templates = TemplateLibrary()
    templates.scale_templates(Settings.template_scale)
    last_nodes = None
    step = 0

    # always log last result, to make it easier for randoms to send useful bug report
    if save_folder is None:
        save_folder = prepare_clean_folder("Last_scan_result", log)

    log("Starting scanning process")
    switch_window(step)

    # screenshot now restricted to game area, returns game screen + top left corner pos
    _, game_window_corner_offset = screenshot(save_folder, step)

    # connections worker
    work_q = Queue()
    conn_worker = ExceptionThread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid, log),
        daemon=True
    )
    conn_worker.start()

    # node detection worker
    detect_q = Queue(maxsize=1)
    detect_result = DetectResult()
    node_worker = ExceptionThread(
        target=worker_nodes,
        args=(detect_q, detect_result, templates, Settings.screenshot_scale, Settings.threshold),
        daemon=True
    )
    node_worker.start()

    if save_folder is not None:
        os.makedirs(save_folder, exist_ok=True)

    duplicates = 0
    while step <= max_steps:
        img, game_window_corner_offset = screenshot(save_folder, step)
        detect_q.put((step, img))
        # skip movement if end MAY BE here, but not confirmed yet
        if last_nodes is not None and last_nodes[-1].modifier != "SH" and last_nodes[-2].modifier != "SH":
            move_mouse(last_nodes[-1], game_window_corner_offset)
        # wait for node detection to complete
        while True:
            with detect_result.lock:
                ready = (detect_result.ready_step == step)
                if ready:
                    nodes = detect_result.nodes
                    break
            time.sleep(0.01)

        non_empty_columns, non_normals = check_node_output_quality(nodes)
        if len(nodes) == 0:
            switch_window(1)
            raise IOError(f"step_{step}: Nothing detected, is map visible?")
        if non_normals <= 2 and len(nodes) <= 4:
            switch_window(1)
            raise IOError(
                f"step_{step}: {len(nodes)}n / {non_normals}o nodes detected, too low. Is your map fully visible? Did you perform calibration?")

        if step <= max_steps:
            log(f"Step {step}, expected 3~6; {len(nodes)}n / {non_normals}o nodes detected")
        else:
            log(f"Step {step}, something is definitely wrong, consider making bug report")
            raise IOError("Auto scanner failed")
        should_end = False
        if check_end(nodes, last_nodes):
            should_end = True
        if conn_worker.exc_info:  # stop queue when error
            exc_type, exc_value, exc_tb = conn_worker.exc_info
            raise exc_value.with_traceback(exc_tb)
        # anti duplicate check
        is_duplicate = False
        if check_duplicates(nodes, last_nodes):
            is_duplicate = True
            if not should_end:
                log(f"Step {step} discarded as duplicate, that should not happen. Is map being dragged correctly? "
                    f"Is game opened in windowed state, not fullscreen? Is script run as admin?")
                if duplicates >= 3:
                    raise IOError(f"3rd duplicate, something is very broken, stopping...")
                duplicates += 1
                step += 1
                continue

        # send nodes result to connection worker
        if not is_duplicate:
            work_q.put((img, nodes))
        step += 1
        if should_end:
            break

        do_drag_move(nodes[-1], nodes[0], game_window_corner_offset)
        last_nodes = nodes
        if conn_worker.exc_info:  # stop queue when error
            exc_type, exc_value, exc_tb = conn_worker.exc_info
            raise exc_value.with_traceback(exc_tb)

    # Finish workers
    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)
    if conn_worker.exc_info:
        exc_type, exc_value, exc_tb = conn_worker.exc_info
        raise exc_value.with_traceback(exc_tb)

    detect_q.put(None)
    node_worker.join(timeout=1.0)
    if node_worker.exc_info:
        exc_type, exc_value, exc_tb = node_worker.exc_info
        raise exc_value.with_traceback(exc_tb)

    log("Scanning done")

    json_path = os.path.join(save_folder, "merged_map.json") if save_folder else None
    map_obj = finalizer.finalize(json_path)
    path, encounter_ranges, encounter_counts = run_pathfinder(map_obj)
    image_path = os.path.join(save_folder, "merged_map.png") if save_folder else None
    image = draw_map(map_obj,
                     path,
                     output_path=image_path,
                     encounter_ranges=encounter_ranges,
                     encounter_counts=encounter_counts)

    switch_window(step)

    return map_obj, path, image


def run_offline_pipeline(max_steps=20, save_folder=None, print_grid=False, log=lambda msg: None):
    if save_folder is None:
        raise ValueError("run_offline_pipeline requires save_folder with images")

    all_files = sorted(os.listdir(save_folder))
    screenshots = [
        s for s in all_files
        if not s.startswith("merged") and not s.split(".")[0].endswith("preview")]
    if not screenshots:
        raise IOError("No valid images found for offline pipeline")

    step = 0
    last_nodes = None
    templates = TemplateLibrary()
    templates.scale_templates(Settings.template_scale)

    log("Starting scanning process [folder based - no game / mouse interaction]")
    mock_switch_window()

    finalizer = Finalizer()
    work_q = Queue()
    conn_worker = ExceptionThread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid, log),
        daemon=True)
    conn_worker.start()

    for s in screenshots:
        if step >= max_steps:
            break

        img = mock_screenshot(os.path.join(save_folder, s))
        nodes = detect_nodes(img, templates, step, screenshot_scale=Settings.screenshot_scale,
                             threshold=Settings.threshold)

        if len(nodes) == 0:
            raise IOError(f"Step {step}: Nothing detected, is map visible?")
        non_empty_columns, non_normals = check_node_output_quality(nodes)
        if non_normals <= 2 and len(nodes) <= 4:
            raise IOError(f"Step {step}: {len(nodes)}n / {non_normals}o nodes detected, too low")
        log(f"Step {step} from screenshot {s}: {len(nodes)}n / {non_normals}o nodes detected")

        should_end = check_end(nodes, last_nodes)
        is_duplicate = False
        if check_duplicates(nodes, last_nodes):
            is_duplicate = True
            if not should_end:
                log(f"Step {step} discarded as duplicate")
                step += 1
                continue

        if conn_worker.exc_info:  # stop queue when error
            exc_type, exc_value, exc_tb = conn_worker.exc_info
            raise exc_value.with_traceback(exc_tb)

        if not is_duplicate:
            work_q.put((img, nodes))
        last_nodes = nodes
        step += 1

        if should_end:
            break
        if len(nodes) >= 2:
            mock_move_screen(nodes[-1], nodes[0])
        if conn_worker.exc_info:  # stop queue when error
            exc_type, exc_value, exc_tb = conn_worker.exc_info
            raise exc_value.with_traceback(exc_tb)

    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)
    if conn_worker.exc_info:  # check again after queue is done
        exc_type, exc_value, exc_tb = conn_worker.exc_info
        raise exc_value.with_traceback(exc_tb)

    if step == 0:
        raise IOError("There were no valid map images in this folder..? Scan returned nothing.")

    log("Scanning done")
    json_path = os.path.join(save_folder, "merged_map.json")
    map_obj = finalizer.finalize(json_path)
    path, encounter_ranges, encounter_counts = run_pathfinder(map_obj)
    image_path = os.path.join(save_folder, "merged_map.png")
    image = draw_map(map_obj,
                     path,
                     output_path=image_path,
                     encounter_ranges=encounter_ranges,
                     encounter_counts=encounter_counts)

    mock_switch_window()

    return map_obj, path, image


def run_halfauto_pipeline(max_steps=20, save_folder=None, print_grid=False, log=lambda msg: None):
    if save_folder is None:
        save_folder = prepare_clean_folder("Last_scan_result", log)
    else:
        os.makedirs(save_folder, exist_ok=True)
    log("Starting scanning process [half-auto]")

    templates = TemplateLibrary()
    templates.scale_templates(Settings.template_scale)
    screenshot_q = Queue()
    detect_q = Queue(maxsize=1)
    work_q = Queue()
    finalizer = Finalizer()
    detect_result = DetectResult()
    listener = DragListener(  # TEST: change to mock
        screenshot_q=screenshot_q,
        save_folder=save_folder,
        log=log
    )
    listener.start()
    log("Waiting for first screenshot...")
    data = screenshot_q.get()
    if data is None:
        raise IOError("Scanner stopped by user")
    step, img = data
    last_nodes = None

    node_worker = ExceptionThread(
        target=worker_nodes,
        args=(detect_q, detect_result, templates, Settings.screenshot_scale, Settings.threshold),
        daemon=True)
    node_worker.start()

    conn_worker = ExceptionThread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid, log),
        daemon=True)
    conn_worker.start()

    detect_q.put((step, img))

    while step < max_steps:
        while True:
            with detect_result.lock:
                if detect_result.ready_step == step:
                    nodes = detect_result.nodes
                    break
            time.sleep(0.01)

        if len(nodes) == 0:
            listener.stop()
            raise IOError(f"Step {step}: Nothing detected, is map visible?")

        non_empty_columns, non_normals = check_node_output_quality(nodes)

        if non_normals <= 2 and len(nodes) <= 4:
            listener.stop()
            raise IOError(f"Step {step}: {len(nodes)}n / {non_normals}o nodes detected, too low. Is map fully visible? "
                          f"Have you performed calibration?")

        log(f"Step {step}, expected 3~6; {len(nodes)}n / {non_normals}o nodes detected")

        should_end = check_end(nodes, last_nodes)
        is_duplicate = False
        if check_duplicates(nodes, last_nodes):
            is_duplicate = True
            if not should_end:
                log(f"Step {step} discarded as duplicate")
                step += 1
                continue

        if not is_duplicate:
            work_q.put((img, nodes))

        last_nodes = nodes
        step += 1

        if should_end:
            log(f"Step {step - 1}: end detected, stopping capture")
            listener.stop()
            try:
                screenshot_q.put_nowait(None)
            except Exception:
                pass
            break

        data = screenshot_q.get()
        if data is None:
            break

        step, img = data
        detect_q.put((step, img))

    listener.stop()

    detect_q.put(None)
    node_worker.join(timeout=1.0)
    if node_worker.exc_info:
        exc_type, exc_value, exc_tb = node_worker.exc_info
        raise exc_value.with_traceback(exc_tb)

    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)
    if conn_worker.exc_info:
        exc_type, exc_value, exc_tb = conn_worker.exc_info
        raise exc_value.with_traceback(exc_tb)

    log("Scanning done")

    json_path = os.path.join(save_folder, "merged_map.json")
    map_obj = finalizer.finalize(json_path)
    path, encounter_ranges, encounter_counts = run_pathfinder(map_obj)
    image_path = os.path.join(save_folder, "merged_map.png")
    image = draw_map(map_obj,
                     path,
                     output_path=image_path,
                     encounter_ranges=encounter_ranges,
                     encounter_counts=encounter_counts)

    return map_obj, path, image


def get_game_screenshot(log):
    try:
        switch_window(0)
        scr, _ = screenshot()
        switch_window(1)
        return scr
    except Exception as e:
        log(e)
    return None


if __name__ == "__main__":
    run_offline_pipeline(save_folder=get_path("Example_scan_result"), print_grid=False,
                         log=lambda msg: print(msg))
