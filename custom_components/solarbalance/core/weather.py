"""Pure helpers to interpret a Météo-France weather-alert entity.

The Météo-France ``sensor.<dept>_weather_alert`` entity exposes one attribute per
phenomenon (e.g. "Vent violent", "Orages", "Canicule") whose value is the colour
level ("Vert"/"Jaune"/"Orange"/"Rouge"). This module turns a watched-phenomena
selection + a minimum level into a single "warning active" boolean, tolerant to
casing/separator/accent differences and to the English colour names.

Pure module -- no Home Assistant imports.
"""

import unicodedata
from collections.abc import Iterable, Mapping

# Colour level -> rank. 0 = none, 1 = yellow, 2 = orange, 3 = red.
_LEVEL_RANK: dict[str, int] = {
    "vert": 0,
    "green": 0,
    "jaune": 1,
    "yellow": 1,
    "orange": 2,
    "rouge": 3,
    "red": 3,
}

# Canonical (normalised) phenomenon keys the Météo-France integration exposes.
PHENOMENA: tuple[str, ...] = (
    "canicule",
    "grandfroid",
    "ventviolent",
    "orages",
    "neigeverglas",
    "inondation",
    "pluieinondation",
    "vaguessubmersion",
    "avalanches",
)


def normalize_phenomenon(name: str) -> str:
    """Lower-case and strip accents/separators for tolerant matching."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(ch for ch in stripped.lower() if ch.isalnum())


def level_rank(value: str) -> int | None:
    """Rank of a colour level string, or ``None`` if unrecognised."""
    return _LEVEL_RANK.get(normalize_phenomenon(value))


def weather_warning_active(
    attributes: Mapping[str, object],
    *,
    watched: Iterable[str],
    min_rank: int,
) -> bool:
    """True if any watched phenomenon attribute is at or above ``min_rank``.

    Args:
        attributes: The weather-alert entity's attributes (phenomenon -> colour).
        watched: Normalised phenomenon keys to consider; empty = all phenomena.
        min_rank: Minimum colour rank that triggers (1 yellow, 2 orange, 3 red).

    Non-phenomenon attributes (friendly_name, attribution, ...) are ignored.
    """
    watched_set = {normalize_phenomenon(w) for w in watched}
    for key, value in attributes.items():
        nk = normalize_phenomenon(key)
        if nk not in PHENOMENA:
            continue
        if watched_set and nk not in watched_set:
            continue
        rank = level_rank(str(value))
        if rank is not None and rank >= min_rank:
            return True
    return False
