# score_config.py
from dataclasses import dataclass


@dataclass
class ScoreItem:
    value: int
    big_scale: bool = False
    enabled: bool = True
    merge_group: int = 0  # only merge nodes under common mod if this key matches


class Season:
    def __init__(self, name: str, active_scores: list[str]):
        self.name = name
        self.active_scores = set(active_scores)


class ModLimit:
    def __init__(self, mod: str, full_name: str | None = None, seasons=None, limit: int = 0):
        self.mod = mod  # mod only, like SH, not RESH
        self.full_name = full_name if full_name is not None and len(full_name) > 0 else mod
        self.seasons = [] if seasons is None else seasons
        self.limit = limit


CURRENT_SEASON = "s4"  # REMEMBER TO UPDATE ON NEW SEASON
DEFAULT_VALUES = {
    "NO": ScoreItem(-5),    # normal
    "NOOR": ScoreItem(0),   # orb of chaos
    "NOPE": ScoreItem(6),   # persona
    "NODE": ScoreItem(6),   # desire
    "EL": ScoreItem(-3),    # elite
    "ELOR": ScoreItem(0),
    "ELPE": ScoreItem(6),
    "ELDE": ScoreItem(6),
    "RE": ScoreItem(-4),    # rest
    "RESH": ScoreItem(6),   # shop
    "EV": ScoreItem(4),     # event
    "EVTU": ScoreItem(40, big_scale=True),  # dimensional tunnel
    "EVME": ScoreItem(40, big_scale=True),  # memory of embers
    "EVDI": ScoreItem(40, big_scale=True),  # director's script
    "EVDE": ScoreItem(2, merge_group=1),
}

SEASONS = {
    "s12": Season("Season 1-2", [
        "NO",
        "NOOR",
        "EL",
        "ELOR",
        "RE",
        "RESH",
        "EV",
        "EVTU",
        "EVME",
    ]),
    "s3": Season("Season 3", [
        "NO",
        "NOPE",
        "EL",
        "ELPE",
        "RE",
        "RESH",
        "EV",
        "EVDI"
    ]),
    "s4": Season("Season 4", [
        "NO",
        "NOOR",
        "NODE",
        "EL",
        "ELOR",
        "ELDE",
        "RE",
        "RESH",
        "EV",
        "EVDE",
    ]),
    "s*": Season("All", [
        "NO",
        "NOOR",
        "NOPE",
        "NODE",
        "EL",
        "ELOR",
        "ELPE",
        "ELDE",
        "RE",
        "RESH",
        "EV",
        "EVTU",
        "EVME",
        "EVDI",
        "EVDE",
    ]),
    "sortie": Season("Sortie", [
        "NO",
        "NOOR",
        "EL",
        "ELOR",
        "RE",
        "RESH",
        "EV",
    ]),
}

DEFAULT_LIMITS = {
    "SH": ModLimit("SH", "Shop", ["s12", "s3", "s4"], 3),
    "PE": ModLimit("PE", "Persona", ["s3"], 5),
    "DE": ModLimit("DE", "Desire", ["s4"], 4),
}
