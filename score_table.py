# score_table.py
import json
import os.path
from typing import Dict
from path_converter import get_path
from score_config import ScoreItem, DEFAULT_VALUES

DEFAULT_PATH = "ScoreTable.json"


class ScoreTable:
    def __init__(self, **overrides: ScoreItem):
        self.table: Dict[str, ScoreItem] = DEFAULT_VALUES.copy()
        self.table.update(overrides)
        self.active_season = "s3"

    @staticmethod
    def export(scoretable: "ScoreTable", filename: str = DEFAULT_PATH) -> None:
        filename = get_path(filename)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(scoretable.to_dict(), f, indent=2)

    @staticmethod
    def import_(filename: str = DEFAULT_PATH) -> "ScoreTable":
        filename = get_path(filename)
        if not os.path.exists(filename):
            return ScoreTable()

        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        parsed = ScoreTable.from_dict(data)
        st = ScoreTable()
        st.table = parsed
        return st

    def to_dict(self):
        return {
            k: {
                "value": v.value,
                "big_scale": v.big_scale,
            }
            for k, v in self.table.items()
        }

    @staticmethod
    def from_dict(data: dict) -> Dict[str, ScoreItem]:
        return {
            k: ScoreItem(
                value=v["value"],
                big_scale=v.get("big_scale", False),
            )
            for k, v in data.items()
        }

    @staticmethod
    def check_file_exists(filename: str = DEFAULT_PATH) -> bool:
        filename = get_path(filename)
        return os.path.exists(filename)
