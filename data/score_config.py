# score_config.py
from dataclasses import dataclass, field


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


@dataclass
class ModLimit:
    mod: str  # mod only, like SH, not RESH
    full_name: str | None = None
    seasons: list[str] = field(default_factory=list)
    limit: int = 0

    def __post_init__(self):
        if not self.full_name:
            self.full_name = self.mod


CURRENT_SEASON = "s4"  # REMEMBER TO UPDATE ON NEW SEASON
DEFAULT_VALUES = {          # additive, so RESH = RE + RESH
    "NO": ScoreItem(-5),    # normal
    "NOOR": ScoreItem(1),   # orb of chaos
    "NOPE": ScoreItem(6),   # persona
    "NODE": ScoreItem(6),   # desire
    "NOTR": ScoreItem(40, big_scale=True),  # trail of the husk
    "EL": ScoreItem(-2),    # elite
    "ELOR": ScoreItem(1),
    "ELPE": ScoreItem(6),
    "ELDE": ScoreItem(6),
    "ELTR": ScoreItem(40, big_scale=True),
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
        "NOTR",
        "EL",
        "ELOR",
        "ELDE",
        "ELTR",
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
        "NOTR"
        "EL",
        "ELOR",
        "ELPE",
        "ELDE",
        "ELTR"
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
    "SH": ModLimit("SH", "Shop", ["s12", "s3", "s4"], 2),
    "PE": ModLimit("PE", "Persona", ["s3"], 5),
    "DE": ModLimit("DE", "Desire", ["s4"], 4),
}
