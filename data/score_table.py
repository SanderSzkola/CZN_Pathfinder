# score_table.py
import json
from copy import deepcopy
from pathlib import Path
from typing import Dict

from data.score_config import ScoreItem, DEFAULT_VALUES, SEASONS, CURRENT_SEASON
from utils.path_converter import get_path

DEFAULT_PATH = "ScoreTable.json"
TABLES_PER_SEASON = 2


class ScoreTable:
    _path: Path | None = None
    _loaded: bool = False

    tables: Dict[str, Dict[int, Dict[str, ScoreItem]]] = {}
    active_season: str = CURRENT_SEASON
    active_table: int = 1

    @classmethod
    def current(cls) -> Dict[str, ScoreItem]:
        cls._ensure_loaded()
        return cls.tables[cls.active_season][cls.active_table]

    @classmethod
    def get(cls, season: str, table: int = 1) -> Dict[str, ScoreItem]:
        cls._ensure_loaded()
        return cls.tables[season][table]

    @classmethod
    def default_table_for(cls, season_key: str) -> Dict[str, ScoreItem]:
        active = SEASONS[season_key].active_scores
        return {
            k: deepcopy(v)
            for k, v in DEFAULT_VALUES.items()
            if k in active
        }

    @classmethod
    def get_key(cls) -> str:
        cls._ensure_loaded()
        return f"{cls.active_season}:{cls.active_table}"

    @classmethod
    def _ensure_loaded(cls):
        if not cls._loaded:
            if not cls.load():
                cls._create_defaults()
                cls._loaded = True

    @classmethod
    def _ensure_path(cls):
        if cls._path is None:
            cls._path = Path(get_path(DEFAULT_PATH))

    @classmethod
    def load(cls):
        cls._ensure_path()
        if not cls._path.exists():
            return False

        with cls._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        raw_tables = data.get("tables", {})

        # Backwards compatibility with the old season - score_key format
        for season_key, season_data in raw_tables.items():
            if season_data and isinstance(next(iter(season_data.values())), dict) \
                    and "value" in next(iter(season_data.values())):
                raw_tables[season_key] = {"1": season_data}

        cls.tables = {}
        for season_key in SEASONS:
            cls.tables[season_key] = {}
            season_data = raw_tables.get(season_key, {})
            for table_index in range(1, TABLES_PER_SEASON + 1):
                loaded = season_data.get(str(table_index), {})
                defaults = cls.default_table_for(season_key)
                cls.tables[season_key][table_index] = {
                    key: cls.from_dict({key: loaded[key]})[key]
                    if key in loaded else deepcopy(default)
                    for key, default in defaults.items()
                }

        loaded_season = data.get("active_season", CURRENT_SEASON)
        cls.active_season = (
            loaded_season if loaded_season in SEASONS else CURRENT_SEASON
        )
        loaded_table = data.get("active_table", 1)
        cls.active_table = (
            loaded_table if loaded_table in range(1, TABLES_PER_SEASON + 1) else 1
        )
        cls._loaded = True
        return True

    @classmethod
    def _create_defaults(cls):
        cls.tables = {
            season: {
                table_index: cls.default_table_for(season)
                for table_index in range(1, TABLES_PER_SEASON + 1)
            }
            for season in SEASONS
        }

    @classmethod
    def save(cls):
        cls._ensure_path()
        data = {
            "active_season": cls.active_season,
            "active_table": cls.active_table,
            "tables": {
                season: {
                    str(table_index): cls.to_dict(table)
                    for table_index, table in season_tables.items()
                }
                for season, season_tables in cls.tables.items()
            }
        }
        cls._path.parent.mkdir(parents=True, exist_ok=True)
        with cls._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def to_dict(table: Dict[str, ScoreItem]) -> dict:
        return {
            k: {
                "value": v.value,
                "big_scale": v.big_scale,
                "enabled": v.enabled,
                "merge_group": v.merge_group,
            }
            for k, v in table.items()
        }

    @staticmethod
    def from_dict(data: dict) -> Dict[str, ScoreItem]:
        return {
            k: ScoreItem(
                value=v["value"],
                big_scale=v.get("big_scale", False),
                enabled=v.get("enabled", True),
                merge_group=v.get("merge_group", 0),
            )
            for k, v in data.items()
        }
