# pathfinder.py
import json
from typing import Dict, List, Tuple, Optional, Union
from score_table import ScoreTable
from path_converter import get_path
from node import Node
from score_config import SEASONS


def load_map(path: str):
    with open(path, "r") as f:
        data = json.load(f)

    if "nodes" not in data or "edges" not in data:
        raise ValueError(f"Invalid map file: missing keys in {path}")

    nodes = {d["id"]: Node.from_dict(d) for d in data["nodes"]}
    edges = [(a, b) for a, b in data["edges"]]
    return nodes, edges


def build_forward_graph(nodes: Dict[str, Node], edges: List[Tuple[str, str]]):
    graph = {nid: [] for nid in nodes}

    for a, b in edges:
        if a not in nodes or b not in nodes:
            continue
        na = nodes[a]
        nb = nodes[b]

        if nb.col > na.col:
            graph[a].append(b)
        elif na.col > nb.col:
            graph[b].append(a)

    return graph


def score_node(node: Node, score_table: ScoreTable):
    ntype = node.type
    modifier = node.modifier
    table = score_table.table

    if modifier:
        complex_key = f"{ntype}{modifier}"
        if complex_key in table:
            return table[complex_key].value
    if ntype in table:
        return table[ntype].value

    return 0


def dfs_best_path(nodes, graph, score_table):
    start_nodes = [nid for nid, nd in nodes.items() if nd.col == 0]
    best_path: Optional[List[str]] = None
    best_score = float("-inf")
    encounter_ranges = {key: [99, -99] for key in score_table.table}
    current_counts = {key: 0 for key in score_table.table}
    enc_trash_list = []

    def dfs(current, path, score):
        nonlocal best_path, best_score

        key = nodes[current].label()
        if key not in encounter_ranges:
            enc_trash_list.append(key)
            encounter_ranges[key] = [0, 0]
            current_counts[key] = 0
        current_counts[key] += 1
        next_nodes = graph.get(current, [])

        if not next_nodes:
            for k, v in current_counts.items():
                if k in encounter_ranges:
                    if v < encounter_ranges[k][0]:
                        encounter_ranges[k][0] = v
                    if v > encounter_ranges[k][1]:
                        encounter_ranges[k][1] = v

            if score > best_score:
                best_path = path.copy()
                best_score = score
            current_counts[key] -= 1  # this path is done, subtract last score and go up
            return

        for nxt in next_nodes:
            dfs(nxt, path + [nxt], score + score_node(nodes[nxt], score_table))
        current_counts[key] -= 1

    for start_id in start_nodes:
        dfs(start_id, [start_id], score_node(nodes[start_id], score_table))

    for t in enc_trash_list:
        encounter_ranges.pop(t, None)

    return best_path, int(best_score), encounter_ranges


def count_encounters(path, nodes):
    counts = {}

    for nid in path:
        key = nodes[nid].label()
        counts[key] = counts.get(key, 0) + 1

    ordered_counts = {}
    for key in ScoreTable().table.keys():
        ordered_counts[key] = counts.get(key, 0)
    return ordered_counts


def run_pathfinder(
        map_data: Union[dict, str],
        score_table: Optional[ScoreTable] = None):
    """
    Compute the best path for given map data or from file.
    Returns best_path, encounter_ranges, encounter_counts.
    """

    if score_table is None:
        score_table = ScoreTable()

    save_json = False
    if isinstance(map_data, str):
        nodes, edges = load_map(map_data)
        save_json = True
    else:
        nodes = {d["id"]: Node.from_dict(d) for d in map_data["nodes"]}
        edges = [(a, b) for a, b in map_data["edges"]]

    graph = build_forward_graph(nodes, edges)
    best_path, best_value, encounter_ranges = dfs_best_path(nodes, graph, score_table)

    if best_path is None:
        raise RuntimeError("No valid path found.")

    encounter_counts = count_encounters(best_path, nodes)

    # filter out non-season mods
    active_keys = SEASONS[score_table.active_season].active_scores
    encounter_ranges = {
        k: v for k, v in encounter_ranges.items()
        if k in active_keys
    }
    encounter_counts = {
        k: v for k, v in encounter_counts.items()
        if k in active_keys
    }

    if save_json:
        with open(map_data, "r") as f:
            existing = json.load(f)
        existing["best_path"] = best_path
        with open(map_data, "w") as f:
            json.dump(existing, f, indent=2)

    return best_path, encounter_ranges, encounter_counts


if __name__ == "__main__":
    best_path, encounter_ranges, encounter_counts = run_pathfinder(get_path(["Example_scan_result", "merged_map.json"]))
    print("Best path:", best_path)
    print("Encounter ranges | min-max across all possible paths:")
    for e in encounter_ranges:
        print(f"{e}: {encounter_ranges.get(e)}")
    print("Encounter counts | nodes contained in current best path:")
    for e in encounter_counts:
        print(f"{e}: {encounter_counts.get(e)}")
