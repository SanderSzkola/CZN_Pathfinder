import json
from typing import Dict
from path_converter import get_path


class ScoreTable:
    def __init__(
            self,
            NO: int = -7,
            NOOR: int = -7,
            EL: int = 2,
            ELOR: int = 2,
            RE: int = 0,
            RESH: int = 4,
            EV: int = 3,
    ):
        self.table: Dict[str, int] = {
            "NO": NO,
            "NOOR": NOOR,
            "EL": EL,
            "ELOR": ELOR,
            "RE": RE,
            "RESH": RESH,
            "EV": EV,
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
            NO=data.get("NO", -7),
            EL=data.get("EL", 2),
            EV=data.get("EV", 3),
            RE=data.get("RE", 0),
            RESH=data.get("RESH", 4),
            NOOR=data.get("NOOR", -7),
            ELOR=data.get("ELOR", 2),
        )
