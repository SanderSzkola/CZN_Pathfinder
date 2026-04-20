# score_config.py
from dataclasses import dataclass


@dataclass
class ScoreItem:
    value: int
    big_scale: bool = False
    enabled: bool = True


class Season:
    def __init__(self, name: str, active_scores: list[str]):
        self.name = name
        self.active_scores = set(active_scores)


DEFAULT_VALUES = {
    "NO": ScoreItem(-7),
    "NOOR": ScoreItem(-10),
    "NOPE": ScoreItem(8),
    "EL": ScoreItem(2),
    "ELOR": ScoreItem(2),
    "ELPE": ScoreItem(8),
    "RE": ScoreItem(-10),
    "RESH": ScoreItem(4),
    "EV": ScoreItem(9),
    "EVTU": ScoreItem(40, True),
    "EVME": ScoreItem(40, True),
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
    ]),
    "s*": Season("All", [
        "NO",
        "NOOR",
        "NOPE",
        "EL",
        "ELOR",
        "ELPE",
        "RE",
        "RESH",
        "EV",
        "EVTU",
        "EVME",
    ]),
}
