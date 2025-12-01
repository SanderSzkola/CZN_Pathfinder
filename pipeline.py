# pipeline.py
import os
import threading
import time
from queue import Queue

from node import Node
from detect_connections import detect_connections
from detect_nodes import detect_nodes, pick_template_set
from drawer import draw_map
from grabber import switch_window, screenshot, do_drag_move, move_mouse, mock_switch_window, mock_move_screen, \
    mock_screenshot, DragListener, MockDragListener
from pathfinder import run_pathfinder
from process_map import Finalizer
from score_table import ScoreTable
from path_converter import get_path

"""
Full process:
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

TEMPLATE_SETS = [
    ("1600x900", "Encounter_minimal_1600", "Modifier_1600"),
    ("1920x1080", "Encounter_minimal_1920", "Modifier_1920"),
]

'''
Requires 2 sets of nodes, must be called before duplicate check.
Reason: checking for boss directly is.. complicated, so this method checks instead if two subsequent screenshots ends
with a column of shops.
'''


def check_end(nodes, last_nodes):
    if (last_nodes is None or len(last_nodes) <= 2
            or nodes is None or len(nodes) <= 2):
        return False
    nodes_last_column = []
    last_col_idx = nodes[-1].col
    no_index_x = 0
    if last_col_idx is None:  # nodes may come before rowcol assignment
        no_index_x = nodes[-1].x
    for n in nodes:
        if last_col_idx and n.col == last_col_idx:
            nodes_last_column.append(n)
        elif abs(no_index_x - n.x) < 10:
            nodes_last_column.append(n)
    last_col_idx = last_nodes[-1].col
    for n in last_nodes:
        if n.col == last_col_idx:
            nodes_last_column.append(n)
    for n in nodes_last_column:
        if n.modifier is None or n.modifier != "SH":
            return False
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


def worker_connections(queue: Queue, finalizer: Finalizer, templates, print_grid: bool = False):
    while True:
        item = queue.get()
        if item is None:
            break

        img, nodes = item
        nodes_conn, edges_conn, _ = detect_connections(img, templates, nodes)
        finalizer.add_fragment(nodes_conn, edges_conn, print_grid)
        queue.task_done()


class DetectResult:
    def __init__(self):
        self.lock = threading.Lock()
        self.ready_step = -1
        self.nodes = None


class ExceptionThread(threading.Thread):
    def run(self):
        self.exception = None
        try:
            super().run()
        except Exception as e:
            self.exception = e


def worker_nodes(detect_q: Queue, result: DetectResult, templates):
    while True:
        item = detect_q.get()
        if item is None:
            break

        step, img = item
        nodes = detect_nodes(img, templates, step)
        with result.lock:
            result.ready_step = step
            result.nodes = nodes

        detect_q.task_done()


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


def run_auto_pipeline(max_steps=15, save_folder=None, print_grid=False, log=lambda msg: None,
                      score_table: ScoreTable = None):
    finalizer = Finalizer()
    last_nodes = None
    step = 0

    # always log last result, to make it easier for randoms to send useful bug report
    if save_folder is None:
        save_folder = prepare_clean_folder("Last_scan_result", log)

    log("Starting scanning process")
    switch_window(step)

    # TODO: rewrite this so those nodes can be used
    img = screenshot(save_folder, step)
    templates, initial_nodes, resolution = pick_template_set(img, TEMPLATE_SETS)
    if len(initial_nodes) == 0:
        raise IOError(f"Step {step}: Nothing detected, is map visible?")
    log(f"Matched template: {resolution}, with {len(initial_nodes)} matches")
    if len(initial_nodes) <= 4:
        raise IOError(f"Node count too low, is map fully visible?")

    # connections worker
    work_q = Queue()
    conn_worker = ExceptionThread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid),
        daemon=True
    )
    conn_worker.start()

    # node detection worker
    detect_q = Queue(maxsize=1)
    detect_result = DetectResult()
    node_worker = ExceptionThread(
        target=worker_nodes,
        args=(detect_q, detect_result, templates),
        daemon=True
    )
    node_worker.start()

    if save_folder is not None:
        os.makedirs(save_folder, exist_ok=True)

    while step <= max_steps:
        if step <= max_steps - 5:
            log(f"Step {step}, expected 5~10")
        elif step <= max_steps:
            log(f"Step {step}, expected 5~10, something may be broken")
        else:
            log(f"Step {step}, something is definitely wrong, consider making bug report")
            raise IOError("Auto scanner failed")
        img = screenshot(save_folder, step)
        detect_q.put((step, img))
        if last_nodes is not None:
            move_mouse(last_nodes[-1])
        # wait for node detection to complete
        while True:
            with detect_result.lock:
                ready = (detect_result.ready_step == step)
                if ready:
                    nodes = detect_result.nodes
                    break
            time.sleep(0.01)

        if len(nodes) == 0:
            switch_window(1)
            raise IOError(f"step_{step}: Nothing detected, is map visible?")
        if check_end(nodes, last_nodes):
            break
        # anti duplicate check
        if check_duplicates(nodes, last_nodes):
            log(f"Step {step} discarded as duplicate, that should not happen. Is map being dragged correctly? Is game opened in windowed state, not fullscreen? Is script run as admin?")
            step += 1
            continue

        # send nodes result to connection worker
        work_q.put((img, nodes))

        do_drag_move(nodes[-1], nodes[0])
        last_nodes = nodes
        step += 1

    # Finish workers
    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)
    if conn_worker.exception:
        raise conn_worker.exception

    detect_q.put(None)
    node_worker.join(timeout=1.0)
    if node_worker.exception:
        raise node_worker.exception

    log("Scanning done")

    json_path = os.path.join(save_folder, "merged_map.json") if save_folder else None
    map_obj = finalizer.finalize(json_path)
    path, encounter_ranges, encounter_counts = run_pathfinder(map_obj, score_table)
    image_path = os.path.join(save_folder, "merged_map.png") if save_folder else None
    image = draw_map(map_obj,
                     path,
                     output_path=image_path,
                     encounter_ranges=encounter_ranges,
                     encounter_counts=encounter_counts)

    switch_window(step)

    return map_obj, path, image


def run_offline_pipeline(max_steps=20, save_folder=None, print_grid=False, log=lambda msg: None,
                         score_table: ScoreTable = None):
    if save_folder is None:
        raise ValueError("run_offline_pipeline requires save_folder with images")

    # Collect screenshots
    all_files = sorted(os.listdir(save_folder))
    screenshots = [
        s for s in all_files
        if not s.startswith("merged") and not s.split(".")[0].endswith("preview")]
    if not screenshots:
        raise IOError("No valid images found for offline pipeline")

    step = 0
    last_nodes = None

    log("Starting scanning process [folder based - no game / mouse interaction]")
    mock_switch_window()
    first_img = mock_screenshot(os.path.join(save_folder, screenshots[0]))
    templates, initial_nodes, resolution = pick_template_set(first_img, TEMPLATE_SETS)
    if len(initial_nodes) == 0:
        raise IOError(f"Step {step}: Nothing detected, is map visible?")
    log(f"Matched template: {resolution}, with {len(initial_nodes)} matches")

    finalizer = Finalizer()
    work_q = Queue()
    conn_worker = ExceptionThread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid),
        daemon=True)
    conn_worker.start()

    for s in screenshots:
        if step >= max_steps:
            break

        log(f"Step {step}, processing {s}")

        img = mock_screenshot(os.path.join(save_folder, s))
        nodes = detect_nodes(img, templates, step)

        if len(nodes) == 0:
            raise IOError(f"Step {step}: Nothing detected, is map visible?")
        if check_end(nodes, last_nodes):
            break
        # anti duplicate check
        if check_duplicates(nodes, last_nodes):
            log(f"Step {step} discarded as duplicate, that should not happen. Is map being dragged correctly? Is game opened in windowed state, not fullscreen? Is script run as admin?")
            step += 1
            continue

        work_q.put((img, nodes))

        if len(nodes) >= 2:
            mock_move_screen(nodes[-1], nodes[0])
        last_nodes = nodes
        step += 1

    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)
    if conn_worker.exception:
        raise conn_worker.exception

    if step == 0:
        raise IOError("There were no valid map images in this folder..? Scan returned nothing.")

    log("Scanning done")
    json_path = os.path.join(save_folder, "merged_map.json") if save_folder else None
    map_obj = finalizer.finalize(json_path)
    path, encounter_ranges, encounter_counts = run_pathfinder(map_obj, score_table)
    image_path = os.path.join(save_folder, "merged_map.png") if save_folder else None
    image = draw_map(map_obj,
                     path,
                     output_path=image_path,
                     encounter_ranges=encounter_ranges,
                     encounter_counts=encounter_counts)

    mock_switch_window()

    return map_obj, path, image


def run_halfauto_pipeline(max_steps=20, save_folder=None, print_grid=False, log=lambda msg: None,
                          score_table: ScoreTable = None):
    if save_folder is None:
        save_folder = prepare_clean_folder("Last_scan_result", log)
    else:
        os.makedirs(save_folder, exist_ok=True)
    log("Starting scanning process [half-auto]")

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
    templates, nodes, resolution = pick_template_set(img, TEMPLATE_SETS)
    if len(nodes) == 0:
        listener.stop()
        raise IOError(f"Step {step}: Nothing detected, is map visible?")
    log(f"Matched template: {resolution}, with {len(nodes)} matches")
    if len(nodes) <= 4:
        listener.stop()
        raise IOError("Node count too low, is map fully visible?")

    node_worker = ExceptionThread(
        target=worker_nodes,
        args=(detect_q, detect_result, templates),
        daemon=True)
    node_worker.start()

    conn_worker = ExceptionThread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid),
        daemon=True)
    conn_worker.start()

    detect_q.put((step, img))
    last_nodes = None
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
        if check_end(nodes, last_nodes):
            break
        # anti duplicate check
        if check_duplicates(nodes, last_nodes):
            log(f"Step {step} discarded as duplicate, that should not happen. Is map being dragged correctly? Is game opened in windowed state, not fullscreen? Is script run as admin?")
            step += 1
            continue

        work_q.put((img, nodes))

        last_nodes = nodes
        data = screenshot_q.get()
        if data is None:
            break
        step, img = data
        log(f"Step {step}, expected 5~10")
        detect_q.put((step, img))

    listener.stop()

    detect_q.put(None)
    node_worker.join(timeout=1.0)
    if node_worker.exception:
        raise node_worker.exception

    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)
    if conn_worker.exception:
        raise conn_worker.exception

    log("Scanning done")

    json_path = os.path.join(save_folder, "merged_map.json")
    map_obj = finalizer.finalize(json_path)
    path, encounter_ranges, encounter_counts = run_pathfinder(map_obj, score_table)
    image_path = os.path.join(save_folder, "merged_map.png")
    image = draw_map(map_obj,
                     path,
                     output_path=image_path,
                     encounter_ranges=encounter_ranges,
                     encounter_counts=encounter_counts)

    return map_obj, path, image


if __name__ == "__main__":
    run_offline_pipeline(save_folder=get_path("Example_scan_result"), print_grid=False,
                         log=lambda msg: print(msg))
