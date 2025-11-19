# pathfinder.py
import json
from typing import Dict, List, Tuple, Optional
from score_table import ScoreTable
from path_converter import get_path


def load_map(path: str) -> Tuple[Dict[str, dict], List[Tuple[str, str]]]:
    """Load node and edge data from a JSON map file."""
    with open(path, "r") as f:
        data = json.load(f)

    if "nodes" not in data or "edges" not in data:
        raise ValueError(f"Invalid map file: missing keys in {path}")

    nodes = {n["id"]: n for n in data["nodes"]}
    edges = data["edges"]
    return nodes, edges


def build_forward_graph(nodes: Dict[str, dict], edges: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """Build directional adjacency list based on node column positions."""
    graph = {nid: [] for nid in nodes}

    for a, b in edges:
        if a not in nodes or b not in nodes:
            continue
        if nodes[b]["col"] > nodes[a]["col"]:
            graph[a].append(b)
        elif nodes[a]["col"] > nodes[b]["col"]:
            graph[b].append(a)

    return graph


def score_node(node: dict, score_table: ScoreTable) -> int:
    """Return a numeric score for a node based on its type/modifier."""
    ntype = node.get("type")
    modifier = node.get("modifier")
    complex_modifier = f"{ntype}{modifier}" if modifier else None
    table = score_table.table
    if modifier and complex_modifier in table:
        return table[complex_modifier]
    if modifier and modifier in table:
        return table[modifier]
    if ntype and ntype in table:
        return table[ntype]
    return 0


def dfs_best_path(
        nodes: Dict[str, dict],
        graph: Dict[str, List[str]],
        score_table: ScoreTable
) -> Tuple[Optional[List[str]], int]:
    """Perform DFS to find the highest-scoring path."""
    start_nodes = [nid for nid, nd in nodes.items() if nd["col"] == 0]

    best_path = None
    best_score = float("-inf")

    def dfs(current: str, path: List[str], score: int):
        nonlocal best_path, best_score

        next_nodes = graph.get(current, [])
        if not next_nodes:
            if score > best_score:
                best_path = list(path)
                best_score = score
            return

        for nxt in next_nodes:
            nd = nodes[nxt]
            dfs(nxt, path + [nxt], score + score_node(nd, score_table))

    for start_id in start_nodes:
        start_score = score_node(nodes[start_id], score_table)
        dfs(start_id, [start_id], start_score)

    return best_path, int(best_score)


def extract_edges_from_path(path: List[str]) -> List[Tuple[str, str]]:
    """Convert an ordered node path to an edge list."""
    if not path or len(path) < 2:
        return []
    return [(path[i], path[i + 1]) for i in range(len(path) - 1)]


def run_pathfinder(
        map_data: dict | str,
        score_table: Optional[ScoreTable] = None,
) -> Tuple[List[str], int]:
    """
    Compute the best path for given map data or from file.
    When save_to_file=True, writes 'best_path' into the map file.
    """

    if score_table is None:
        score_table = ScoreTable()

    save_json = False
    if type(map_data) is str:
        nodes, edges = load_map(map_data)
        save_json = True
    else:  # assume dict was passed
        nodes = {n["id"]: n for n in map_data["nodes"]}
        edges = map_data["edges"]

    graph = build_forward_graph(nodes, edges)
    best_path, best_value = dfs_best_path(nodes, graph, score_table)

    if best_path is None:
        raise RuntimeError("No valid path found.")

    if save_json:
        with open(map_data, "r") as f:
            existing = json.load(f)
        existing["best_path"] = best_path
        with open(map_data, "w") as f:
            json.dump(existing, f, indent=2)

    return best_path, best_value


if __name__ == "__main__":
    best_path, total_score = run_pathfinder(get_path(["Example_scan_result", "merged_map.json"]))
    print("Best path nodes:", best_path)
    print("Best path edges:", extract_edges_from_path(best_path))
    print("Total score:", total_score)
