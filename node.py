class Node:
    """
    - id : 4-digit string "SSNN" (SS = screenshot index, NN = order in screenshot)
    - x, y : screen coordinates (int)
    - type : string abbreviation for node type
    - modifier : optional string or None
    - row, col : logical placement (assigned later)
    """

    __slots__ = ("id", "x", "y", "type", "modifier", "row", "col")

    def __init__(self, x, y, node_type, modifier=None, node_id=None):
        if node_id is None:
            raise ValueError("Node must be created with a stable id.")
        self.id = node_id
        self.x = int(x)
        self.y = int(y)
        self.type = node_type
        self.modifier = modifier
        self.row = None
        self.col = None

    def label(self):
        if self.modifier:
            return f"{self.type}{self.modifier}"
        return self.type

    def as_dict(self):
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "type": self.type,
            "modifier": self.modifier,
            "row": self.row,
            "col": self.col,
        }

    @staticmethod
    def from_dict(d):
        n = Node(
            d["x"], d["y"], d["type"], d.get("modifier"),
            node_id=d["id"]
        )
        n.row = d.get("row")
        n.col = d.get("col")
        return n

    @staticmethod
    def is_duplicate(n1: "Node", n2: "Node"):
        if (n1.type == n2.type and
                ((n1.modifier is None and n2.modifier is None) or
                 (n1.modifier is not None and n2.modifier is not None and n1.modifier == n2.modifier)) and
                abs(n1.x - n2.x) <= 10 and
                abs(n1.y - n2.y) <= 10):
            return True
        return False

    def __repr__(self):
        return (f"Node(id={self.id!r}, type={self.type!r}, "
                f"x={self.x}, y={self.y}, row={self.row}, col={self.col})")
