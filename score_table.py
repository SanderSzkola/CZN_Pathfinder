# score_table.py
import json
import os.path
from typing import Dict
from path_converter import get_path

DEFAULT_PATH = "ScoreTable.json"

DEFAULT_VALUES: Dict[str, int] = {
    "NO": -7,
    "NOOR": -7,
    "NOPE": 10,
    "EL": 2,
    "ELOR": 2,
    "ELPE": 10,
    "EV": 3,
    "EVTU": 30,
    "EVME": 30,
    "RE": -10,
    "RESH": 4,
}


class ScoreTable:
    def __init__(self, **overrides: int):
        self.table: Dict[str, int] = DEFAULT_VALUES.copy()
        self.table.update(overrides)

    @staticmethod
    def export(scoretable: "ScoreTable", filename: str = DEFAULT_PATH) -> None:
        filename = get_path(filename)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(scoretable.table, f, indent=2)

    @staticmethod
    def import_(filename: str = DEFAULT_PATH) -> "ScoreTable":
        filename = get_path(filename)
        if not os.path.exists(filename):
            return ScoreTable()

        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ScoreTable(**data)

    @staticmethod
    def check_file_exists(filename: str = DEFAULT_PATH) -> bool:
        filename = get_path(filename)
        return os.path.exists(filename)