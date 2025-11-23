# pipeline.py
import os
import threading
import time
from queue import Queue

from detect_connections import detect_connections
from detect_nodes import detect_nodes, pick_template_set
from drawer import draw_map
from grabber import switch_window, screenshot, do_drag_move, move_mouse, mock_switch_window, mock_move_screen, \
    mock_screenshot
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


def check_end(nodes, last_nodes):  # TODO: think about better method, this could fail in some strange maps
    if (last_nodes is None or len(last_nodes) <= 2
            or nodes is None or len(nodes) <= 2):
        return False
    this_frag_only = False
    two_frags_combined_guess = False
    if (nodes[-1].modifier == "SH" and
            nodes[-2].modifier == "SH" and
            (len(nodes) == 2 or nodes[-3].modifier == "SH")
    ):
        this_frag_only = True
    if (nodes[-1].modifier == "SH" and
            nodes[-2].modifier == "SH" and
            last_nodes[-1].modifier == "SH" and
            last_nodes[-2].modifier == "SH"):
        two_frags_combined_guess = True

    return this_frag_only or two_frags_combined_guess


def worker_connections(queue: Queue, finalizer: Finalizer, templates, print_grid: bool = False):
    while True:
        item = queue.get()
        if item is None:
            break

        img, nodes = item
        nodes_conn, edges_conn, _ = detect_connections(img, templates, nodes)
        finalizer.add_fragment(nodes_conn, edges_conn, print_grid)
        queue.task_done()


class DetectResult:  # why are you a class? check later
    def __init__(self):
        self.lock = threading.Lock()
        self.ready_step = -1
        self.nodes = None


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


def run_auto_pipeline(max_steps=30, save_folder=None, print_grid=False, log=lambda msg: None,
                      score_table: ScoreTable = None):
    finalizer = Finalizer()
    last_nodes = None
    step = 0

    # always log last result, to make it easier for randoms to send useful bug report
    if save_folder is None:
        save_folder = get_path("Last_scan_result")
        os.makedirs(save_folder, exist_ok=True)
        leftovers = os.listdir(save_folder)
        if len(leftovers) > 0:
            log(f"Deleting {len(leftovers)} old screenshots form Last_scan_result folder")
            for f in leftovers:
                os.remove(os.path.join(save_folder, f))

    log("Starting scanning process")
    switch_window(step)

    # TODO: rewrite this so those nodes can be used
    img = screenshot(save_folder, step)
    templates, initial_nodes, resolution = pick_template_set(img, TEMPLATE_SETS)
    if len(initial_nodes) == 0:
        raise IOError(f"Step {step}: Nothing detected, is map visible?")
    log(f"Matched template: {resolution}, with {len(initial_nodes)} matches")

    # connections worker
    work_q = Queue()
    conn_worker = threading.Thread(
        target=worker_connections,
        args=(work_q, finalizer, templates, print_grid),
        daemon=True
    )
    conn_worker.start()

    # node detection worker
    detect_q = Queue(maxsize=1)
    detect_result = DetectResult()
    node_worker = threading.Thread(
        target=worker_nodes,
        args=(detect_q, detect_result, templates),
        daemon=True
    )
    node_worker.start()

    if save_folder is not None:
        os.makedirs(save_folder, exist_ok=True)

    while step < max_steps:
        log(f"Step {step}, expected 5~10")
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

        # send nodes result to connection worker
        work_q.put((img, nodes))

        if check_end(nodes, last_nodes):
            break

        do_drag_move(nodes[-1], nodes[0])
        last_nodes = nodes
        step += 1

    # Finish workers
    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)

    detect_q.put(None)
    node_worker.join(timeout=1.0)

    log("Scanning done")

    json_path = os.path.join(save_folder, "merged_map.json") if save_folder else None
    map_obj = finalizer.finalize(json_path)
    path, score, encounter_counts = run_pathfinder(map_obj, score_table)
    image_path = os.path.join(save_folder, "merged_map.png") if save_folder else None
    image = draw_map(map_obj, path, output_path=image_path, encounter_counts=encounter_counts)

    switch_window(step)

    return map_obj, path, image


def run_offline_pipeline(max_steps=30, save_folder=None, print_grid=False, log=lambda msg: None,
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
    conn_worker = threading.Thread(
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

        work_q.put((img, nodes))
        if check_end(nodes, last_nodes):
            break
        if len(nodes) >= 2:
            mock_move_screen(nodes[-1], nodes[0])
        last_nodes = nodes
        step += 1

    work_q.join()
    work_q.put(None)
    conn_worker.join(timeout=1.0)

    if step == 0:
        raise IOError("There were no valid map images in this folder..? Scan returned nothing.")

    log("Scanning done")
    json_path = os.path.join(save_folder, "merged_map.json") if save_folder else None
    map_obj = finalizer.finalize(json_path)
    path, score, encounter_counts = run_pathfinder(map_obj, score_table)
    image_path = os.path.join(save_folder, "merged_map.png") if save_folder else None
    image = draw_map(map_obj, path, output_path=image_path, encounter_counts=encounter_counts)

    mock_switch_window()

    return map_obj, path, image


if __name__ == "__main__":
    run_offline_pipeline(max_steps=20, save_folder=get_path("Example_scan_result"), print_grid=False,
                         log=lambda msg: print(msg))
