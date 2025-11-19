# process_map.py
import json
import os

from detect_connections import detect_connections
from path_converter import get_path

MAX_VERTICAL_ROWS = 5
HORIZONTAL_OFFSETS = [0, -1, -2, -3]
ROW_Y_TOLERANCE = 16

"""
Combines map fragment info (nodes, edges) into complete map
"""


def initialize_global_nodes():
    return {}


def print_map_grid(map_data, label):
    print(f"\n--- {label} ---")

    nodes = list(map_data.values()) if type(map_data) is dict else map_data
    if not nodes:
        print("[empty]")
        return

    rows = sorted({n.row for n in nodes})
    cols = sorted({n.col for n in nodes})

    for r in rows:
        row_cells = []
        for c in cols:
            node = next((n for n in nodes if n.row == r and n.col == c), None)
            if node is None:
                row_cells.append(".")
            else:
                if node.modifier:
                    row_cells.append(f"{node.type}+{node.modifier}")
                else:
                    row_cells.append(f"{node.type}")
        print(" ".join(f"{cell:8}" for cell in row_cells))


def normalize_fragment_rows(global_nodes, frag_nodes):
    # If nothing global yet → no alignment needed
    if not global_nodes:
        return frag_nodes

    new_global_nodes = list(global_nodes.values())
    accepted_rows = []
    global_needs_correcting = False

    for g in new_global_nodes:
        if not accepted_rows:
            accepted_rows.append(g.y)
            continue
        matched = False
        for yval in accepted_rows:
            if abs(g.y - yval) <= ROW_Y_TOLERANCE:
                g.y = yval
                matched = True
                break
        if not matched:
            accepted_rows.append(g.y)

    for f in frag_nodes:
        if not accepted_rows:
            accepted_rows.append(f.y)
            continue
        matched = False
        for yval in accepted_rows:
            if abs(f.y - yval) <= ROW_Y_TOLERANCE:
                f.y = yval
                matched = True
                break
        if not matched:
            accepted_rows.append(f.y)
            global_needs_correcting = True

    accepted_rows.sort()
    if global_needs_correcting:
        for g in new_global_nodes:
            for row, yval in enumerate(accepted_rows):
                if g.y == yval:
                    g.row = row
                    break
        # global usually quickly reaches 5 rows so this should rarely trigger on later fragments
        global_nodes.clear()
        try_merge(global_nodes, new_global_nodes, [])

    for f in frag_nodes:
        for row, yval in enumerate(accepted_rows):
            if f.y == yval:
                f.row = row
                break

    return frag_nodes


def try_merge(global_nodes, frag_nodes, frag_edges):
    if not global_nodes:
        for n in frag_nodes:
            global_nodes[(n.col, n.row)] = n
        return True, frag_edges

    global_anchor_col = max(c for (c, r) in global_nodes)
    frag_anchor_col = min(n.col for n in frag_nodes)

    for dh in HORIZONTAL_OFFSETS:
        conflict = False
        overlap = 0  # not sure if still needed
        frag_to_add = []
        frag_to_correct_edges = []

        # first stage: check for matches and create lists to add and correct
        for f in frag_nodes:
            new_global_col = global_anchor_col + (f.col - frag_anchor_col) + dh
            key = (new_global_col, f.row)

            if key in global_nodes:
                if (global_nodes[key].type != f.type
                        or (global_nodes[key].type == f.type and global_nodes[key].modifier != f.modifier)):
                    conflict = True
                    break
                overlap += 1
                frag_to_correct_edges.append((f, new_global_col))
            else:
                frag_to_add.append((f, new_global_col))

        if conflict or overlap == 0:
            continue

        # second stage: add to global, correct edges
        for f in frag_to_add:
            f[0].col = f[1]
            key = (f[0].col, f[0].row)
            global_nodes[key] = f[0]

        # edges from fragment
        corrected_edges = []
        for edge in frag_edges:
            start_id, end_id = edge
            start_found = None
            end_found = None
            for node in frag_to_correct_edges:  # should be small so can be loopy
                if node[0].id == start_id:
                    start_found = node
                if node[0].id == end_id:
                    end_found = node
                if start_found and end_found:
                    break
            if start_found and end_found:  # fully contained, skip
                continue
            if start_found:  # last column, correct
                start_id = global_nodes[(start_found[1], start_found[0].row)].id
                corrected_edge = (start_id, end_id)
                corrected_edges.append(corrected_edge)
                continue
            if end_found:  # should be contained? no idea, correct for now and check if it looks ok
                end_id = global_nodes[(end_found[1], end_found[0].row)].id
                corrected_edge = (start_id, end_id)
                corrected_edges.append(corrected_edge)
                continue
            corrected_edges.append(edge)  # new node, keep
        return True, corrected_edges
    return False, frag_edges


class Finalizer:
    def __init__(self):
        self.global_nodes = initialize_global_nodes()
        self.edges = set()
        self.step = 0

    def add_fragment(self, nodes, edges, print_grid=False):
        frag_nodes = normalize_fragment_rows(self.global_nodes, nodes)

        result, corrected_edges = try_merge(self.global_nodes, frag_nodes, edges)
        if not result:
            print("Merge failed, grid state:")
            print_map_grid(self.global_nodes, f"GLOBAL step {self.step}")
            print_map_grid(nodes, f"FRAGMENT step {self.step}")
            raise IOError(f"Finalizer.add_fragment failed at step {self.step}")

        for edge in corrected_edges:
            self.edges.add(edge)

        self.validate_nodes()
        self.validate_edges()

        if print_grid:
            print_map_grid(nodes, f"FRAGMENT step {self.step}")
            print_map_grid(self.global_nodes, f"GLOBAL step {self.step}")

        self.step += 1

    def get_map(self):
        nodes = [n.as_dict() for n in self.global_nodes.values()]
        edges = sorted(self.edges)
        return {"nodes": nodes, "edges": edges}

    def finalize(self, output_path: str = None):
        out = self.get_map()
        if output_path:
            with open(output_path, "w") as f:
                json.dump(out, f, indent=2)
        return out

    def validate_nodes(self):
        keys = list(self.global_nodes.keys())
        values = list(self.global_nodes.values())
        misplaced = []
        for i in range(0, len(keys)):
            col, row = keys[i]
            node = values[i]
            if node.col != col or node.row != row:
                misplaced.append(((col, row), node))
        if misplaced:
            print(f"Step {self.step}, {len(misplaced)} misplaced nodes found:")
            for m in misplaced:
                print(f"dict key: {m[0]}, node position: ({m[1].col}, {m[1].row}), id: {m[1].id}")
            raise ValueError(f"Finalizer.validate: Misplaced nodes after step {self.step}")

    def validate_edges(self):
        missing_edge_ids = []
        global_node_ids = {}
        for node in self.global_nodes.values():
            global_node_ids[node.id] = node
        for edge in self.edges:
            id1, id2 = edge
            if id1 not in global_node_ids:
                missing_edge_ids.append((id1, (id1, id2)))
            if id2 not in global_node_ids:
                missing_edge_ids.append((id2, (id1, id2)))
        if len(missing_edge_ids) > 0:
            print(f"Step {self.step}, {len(missing_edge_ids)} missing edges found:")
            for id in missing_edge_ids:
                print(id)
            raise ValueError(f"Finalizer.validate: Missing edges after step {self.step}")


def main(folder, templates):
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
    if not files:
        print("No images.")
        return

    F = Finalizer()
    for i, fn in enumerate(files):
        path = os.path.join(folder, fn)
        nodes, edges, _ = detect_connections(path, templates, screenshot_index=i)
        F.add_fragment(nodes, edges, False)

    F.finalize(os.path.join(folder, "merged_map.json"))


if __name__ == "__main__":
    from detect_nodes import TemplateLibrary

    templates = TemplateLibrary()
    main(get_path("Example_scan_result"), templates)
