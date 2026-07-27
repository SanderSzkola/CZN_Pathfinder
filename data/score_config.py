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
    def __init__(self, mod: str, seasons=None, limit: int = 0):
        self.mod = mod  # mod only, like SH, not RESH
        self.seasons = [] if seasons is None else seasons
        self.limit = limit


CURRENT_SEASON = "s4"  # REMEMBER TO UPDATE ON NEW SEASON
DEFAULT_VALUES = {
    "NO": ScoreItem(-7),                    # normal
    "NOOR": ScoreItem(-10),                 # orb of chaos
    "NOPE": ScoreItem(8),                   # persona
    "NODE": ScoreItem(7),                   # desire
    "EL": ScoreItem(2),                     # elite
    "ELOR": ScoreItem(2),
    "ELPE": ScoreItem(8),
    "ELDE": ScoreItem(7),
    "RE": ScoreItem(-10),                   # rest
    "RESH": ScoreItem(4),                   # shop
    "EV": ScoreItem(9),                     # event
    "EVTU": ScoreItem(40, big_scale=True),  # dimensional tunnel
    "EVME": ScoreItem(40, big_scale=True),  # memory of embers
    "EVDI": ScoreItem(40, big_scale=True),  # director's script
    "EVDE": ScoreItem(10, merge_group=1),
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
