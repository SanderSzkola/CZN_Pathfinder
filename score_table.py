import json
from typing import Dict
from path_converter import get_path

class ScoreTable:
    def __init__(
        self,
        NO: int = -10,
        EL: int = 2,
        EV: int = 4,
        RE: int = 0,
        WA: int = 0,
        RESH: int = 3,
        NOOR: int = -10,
        ELOR: int = 2
    ):
        self.table: Dict[str, int] = {
            "NO": NO,
            "EL": EL,
            "EV": EV,
            "RE": RE,
            "WA": WA,
            "RESH": RESH,
            "NOOR": NOOR,
            "ELOR": ELOR,
        }

    @staticmethod
    def export(scoretable: "ScoreTable", filename: str = "ScoreTable.json") -> None:
        filename = get_path(filename)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(scoretable.table, f, indent=2)

    @staticmethod
    def import_(filename: str = "ScoreTable.json") -> "ScoreTable":
        filename = get_path(filename)
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ScoreTable(
            NO=data.get("NO", -10),
            EL=data.get("EL", 2),
            EV=data.get("EV", 4),
            RE=data.get("RE", 0),
            WA=data.get("WA", 0),
            RESH=data.get("RESH", 3),
            NOOR=data.get("NOOR", -10),
            ELOR=data.get("ELOR", 2),
        )