# pathfinder.py
import json
from typing import Dict, List, Tuple, Union

from data.node import Node
from data.score_config import SEASONS
from data.score_table import ScoreTable
from data.settings import Settings


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


def dfs_all_paths(nodes, graph):
    # pure structure, no score
    start_nodes = [nid for nid, nd in nodes.items() if nd.col == 0]
    all_paths = []

    def dfs(current, path):
        nxt = graph.get(current, [])
        if not nxt:
            all_paths.append(path.copy())
            return
        for child in nxt:
            dfs(child, path + [child])

    for start in start_nodes:
        dfs(start, [start])

    return all_paths


def build_limit_dict():
    season = ScoreTable.active_season
    return {
        limit.mod: {
            "count": 0,
            "limit": limit.limit,
        }
        for limit in Settings.mod_limits.values()
        if season in limit.seasons
    }


def node_scores(node: Node):
    table = ScoreTable.current()
    base = table.get(node.type)
    base_score = base.value if base else 0
    if not node.modifier:
        return base_score, None

    key = f"{node.type}{node.modifier}"
    mod = table.get(key)
    if mod is None:
        return base_score, None
    return base_score, mod.value


def evaluate_path(path, nodes, limits):
    # take single path, analyze all variations of accept vs ignore mod, return best one
    table = ScoreTable.current()
    initial_state = (
        path,  # original path
        0,  # current index
        0,  # primary score, mod > node, used outside, changes depending on where mod were applied
        0,  # secondary score, just node, tiebreaker, stable
        0,  # row changes, tiebreaker, stable
        0,  # quality, by how much mods influence the path, sort by this
        limits,  # mod counters
    )
    states = [initial_state]
    finished = []

    while states:
        (
            original_path,
            index,
            score,
            secondary,
            row_changes,
            quality,
            mod_counts,
        ) = states.pop()

        if index >= len(original_path):
            finished.append((
                original_path,
                score,
                secondary,
                row_changes,
                quality,
            ))
            continue

        node = nodes[original_path[index]]

        next_row_changes = row_changes
        if index > 0:
            prev = nodes[original_path[index - 1]]
            if prev.row != node.row:
                next_row_changes += 1

        # base score, only for modless nodes or limited
        base_score, mod_score = node_scores(node)
        if node.modifier is None or node.modifier in mod_counts:
            states.append((
                original_path,
                index + 1,
                score + base_score,
                secondary + base_score,
                next_row_changes,
                quality,
                mod_counts,
            ))

        # mod score
        if mod_score is None:
            continue
        key = f"{node.type}{node.modifier}"
        if key not in table:
            continue

        next_counts = mod_counts.copy()
        if key in next_counts:
            counter = next_counts[key].copy()
            counter["count"] += 1
            if counter["count"] > counter["limit"]:
                continue
            next_counts[key] = counter
        quality += base_score - mod_score

        states.append((
            original_path,
            index + 1,
            score + base_score + mod_score,
            secondary + base_score,
            next_row_changes,
            quality,
            next_counts,
        ))

    if not finished:
        return None
    finished.sort(
        key=lambda x: (
            x[4],  # quality
            x[1],  # total score
        ),
        reverse=True,
    )
    return finished[0]


def count_encounters(path, nodes):
    counts = {}

    for nid in path:
        key = nodes[nid].label()
        base_key_from_mod = key[:2] if len(key) > 2 else None
        counts[key] = counts.get(key, 0) + 1
        if base_key_from_mod is not None:
            counts[base_key_from_mod] = counts.get(base_key_from_mod, 0) + 1

    ordered_counts = {}
    for key in ScoreTable.current():
        ordered_counts[key] = counts.get(key, 0)
    return ordered_counts


def count_encounter_ranges(paths, nodes):
    ranges = {
        key: [99, -99]
        for key in ScoreTable.current()
    }

    for path in paths:
        counts = {}
        for nid in path:
            key = nodes[nid].label()
            base_key_from_mod = key[:2] if len(key) > 2 else None
            counts[key] = counts.get(key, 0) + 1
            if base_key_from_mod is not None:
                counts[base_key_from_mod] = counts.get(base_key_from_mod, 0) + 1

        for key in ranges:
            value = counts.get(key, 0)
            if value < ranges[key][0]:
                ranges[key][0] = value
            if value > ranges[key][1]:
                ranges[key][1] = value

    return ranges


def run_pathfinder(map_data: Union[dict, str]):
    """
    Compute the best path for given map data or from file.
    Returns best_path, encounter_ranges, encounter_counts.
    """
    save_json = False
    if isinstance(map_data, str):
        nodes, edges = load_map(map_data)
        save_json = True
    else:
        nodes = {d["id"]: Node.from_dict(d) for d in map_data["nodes"]}
        edges = [(a, b) for a, b in map_data["edges"]]

    graph = build_forward_graph(nodes, edges)
    all_paths = dfs_all_paths(nodes, graph)
    if not all_paths:
        raise RuntimeError("No valid path found.")

    limits = build_limit_dict()
    best = None
    for path in all_paths:
        result = evaluate_path(path, nodes, limits)
        if result is None:
            continue
        if best is None:
            best = result
            continue

        # primary mod, secondary node, row changes
        if (result[1], result[2], -result[3]) > (best[1], best[2], -best[3],):
            best = result
    if best is None:
        raise RuntimeError("No valid path satisfies modifier limits.")

    best_path = best[0]
    encounter_ranges = count_encounter_ranges(all_paths, nodes)
    encounter_counts = count_encounters(best_path, nodes)

    # filter out non-season mods
    active_keys = SEASONS[ScoreTable.active_season].active_scores
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
