# score_table.py
import json
from typing import Dict
from pathlib import Path

from path_converter import get_path
from score_config import ScoreItem, DEFAULT_VALUES

DEFAULT_PATH = "ScoreTable.json"


class ScoreTable:
    _path: Path | None = None
    _loaded: bool = False

    table: Dict[str, ScoreItem] = DEFAULT_VALUES.copy()
    active_season: str = "s3"

    @classmethod
    def _ensure_path(cls):
        if cls._path is None:
            cls._path = Path(get_path(DEFAULT_PATH))

    @classmethod
    def load(cls):
        if cls._loaded:
            return

        cls._ensure_path()
        if not cls._path.exists():
            cls.save()
            cls._loaded = True
            return

        with cls._path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        cls.table = cls.from_dict(data.get("table", {}))
        if not cls.table:
            cls.table = DEFAULT_VALUES.copy()
        cls.active_season = data.get("active_season", "s3")
        cls._loaded = True

    @classmethod
    def save(cls):
        cls._ensure_path()

        data = {
            "table": cls.to_dict(),
            "active_season": cls.active_season,
        }

        cls._path.parent.mkdir(parents=True, exist_ok=True)

        with cls._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def to_dict(cls):
        return {
            k: {
                "value": v.value,
                "big_scale": v.big_scale,
                "enabled": v.enabled,
            }
            for k, v in cls.table.items()
        }

    @staticmethod
    def from_dict(data: dict) -> Dict[str, ScoreItem]:
        return {
            k: ScoreItem(
                value=v["value"],
                big_scale=v.get("big_scale", False),
                enabled=v.get("enabled", True),
            )
            for k, v in data.items()
        }


ScoreTable.load()
