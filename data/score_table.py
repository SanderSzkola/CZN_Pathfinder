# score_table.py
import json
from copy import deepcopy
from pathlib import Path
from typing import Dict

from data.score_config import ScoreItem, ModLimit, DEFAULT_VALUES, SEASONS, CURRENT_SEASON
from utils.path_converter import get_path

DEFAULT_PATH = "ScoreTable.json"


class ScoreTable:
    _path: Path | None = None
    _loaded: bool = False

    tables: Dict[str, Dict[str, ScoreItem]] = {}
    active_season: str = CURRENT_SEASON
    mod_limits: list[ModLimit] = []

    @classmethod
    def current(cls) -> Dict[str, ScoreItem]:
        if not cls._loaded:
            cls._create_defaults()
            cls._loaded = True

        return cls.tables.setdefault(cls.active_season, cls.default_table_for(cls.active_season))

    @classmethod
    def default_table_for(cls, season_key: str) -> Dict[str, ScoreItem]:
        active = SEASONS[season_key].active_scores

        return {
            k: deepcopy(v)
            for k, v in DEFAULT_VALUES.items()
            if k in active
        }

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
        cls.tables = {
            season: cls.from_dict(table_data)
            for season, table_data in data.get("tables", {}).items()
        }
        loaded_season = data.get("active_season", CURRENT_SEASON)
        cls.active_season = loaded_season if loaded_season in SEASONS else CURRENT_SEASON
        cls.mod_limits = cls.mod_limits_from_dict(data.get("mod_limits", []))
        # todo: temp, do a proper editor later
        if not cls.mod_limits:
            desire_mod_limit = ModLimit("DE", "s4", 4)
            cls.mod_limits.append(desire_mod_limit)

        # ensure all entries exist
        for season_key in SEASONS:
            defaults = cls.default_table_for(season_key)
            loaded = cls.tables.get(season_key, {})

            cls.tables[season_key] = {
                key: loaded.get(key, deepcopy(default))
                for key, default in defaults.items()
            }

        cls._loaded = True
        return True

    @classmethod
    def _create_defaults(cls):
        cls.tables = {
            season_key: cls.default_table_for(season_key)
            for season_key in SEASONS
        }

    @classmethod
    def save(cls):
        cls._ensure_path()
        data = {
            "active_season": cls.active_season,
            "mod_limits": cls.mod_limits_to_dict(cls.mod_limits),
            "tables": {
                season: cls.to_dict(table)
                for season, table in cls.tables.items()
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
    def mod_limits_to_dict(mod_limits: list[ModLimit]) -> list[dict]:
        return [
            {
                "mod": limit.mod,
                "seasons": limit.seasons,
                "limit": limit.limit,
            }
            for limit in mod_limits
        ]

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

    @staticmethod
    def mod_limits_from_dict(data: list[dict]) -> list[ModLimit]:
        return [
            ModLimit(
                mod=item["mod"],
                seasons=list(item.get("seasons", [])),
                limit=item.get("limit", 0),
            )
            for item in data
        ]
