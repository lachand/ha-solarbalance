"""Tests for the pure Météo-France weather-alert interpreter."""

import pytest

from custom_components.solarbalance.core.weather import (
    level_rank,
    normalize_phenomenon,
    weather_warning_active,
)

# Realistic attribute shape from sensor.<dept>_weather_alert.
_ALL_GREEN = {
    "Canicule": "Vert",
    "Vent violent": "Vert",
    "Pluie-Inondation": "Vert",
    "Orages": "Vert",
    "Neige-Verglas": "Vert",
    "Inondation": "Vert",
    "attribution": "Météo-France",
}


def test_normalize_strips_case_accents_separators() -> None:
    assert normalize_phenomenon("Neige-Verglas") == "neigeverglas"
    assert normalize_phenomenon("Vent violent") == "ventviolent"
    assert normalize_phenomenon("Vagues-Submersion") == "vaguessubmersion"


@pytest.mark.parametrize(
    ("value", "rank"),
    [("Vert", 0), ("Jaune", 1), ("Orange", 2), ("Rouge", 3), ("red", 3), ("???", None)],
)
def test_level_rank(value: str, rank: int | None) -> None:
    assert level_rank(value) == rank


def test_all_green_is_not_active() -> None:
    assert weather_warning_active(_ALL_GREEN, watched=[], min_rank=2) is False


def test_watched_phenomenon_at_orange_triggers() -> None:
    attrs = {**_ALL_GREEN, "Vent violent": "Orange"}
    assert weather_warning_active(attrs, watched=["ventviolent"], min_rank=2) is True


def test_unwatched_phenomenon_is_ignored() -> None:
    # Canicule orange but not watched -> no warning (the user's exact ask).
    attrs = {**_ALL_GREEN, "Canicule": "Orange"}
    watched = ["ventviolent", "orages", "neigeverglas", "inondation", "pluieinondation"]
    assert weather_warning_active(attrs, watched=watched, min_rank=2) is False


def test_min_level_threshold_excludes_yellow() -> None:
    attrs = {**_ALL_GREEN, "Orages": "Jaune"}
    assert weather_warning_active(attrs, watched=["orages"], min_rank=2) is False
    assert weather_warning_active(attrs, watched=["orages"], min_rank=1) is True


def test_empty_watch_means_any_phenomenon() -> None:
    attrs = {**_ALL_GREEN, "Inondation": "Rouge"}
    assert weather_warning_active(attrs, watched=[], min_rank=2) is True


def test_non_phenomenon_attributes_never_trigger() -> None:
    # A stray attribute that happens to read "orange" must not trigger.
    assert weather_warning_active({"some_label": "orange"}, watched=[], min_rank=2) is False
