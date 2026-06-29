"""Tests for the entity watchdog (critical / monitored / optional + edge logging)."""

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.solarbalance.adapters.watchdog import EntityWatchdog


def _hass(states: dict[str, object]) -> MagicMock:
    hass = MagicMock()
    hass.states.get = lambda eid: states.get(eid)
    return hass


def _fresh(value: str = "100") -> SimpleNamespace:
    return SimpleNamespace(state=value, last_updated=datetime.now(UTC))


def _old(value: str = "100") -> SimpleNamespace:
    return SimpleNamespace(state=value, last_updated=datetime.now(UTC) - timedelta(seconds=600))


def test_optional_unavailable_is_not_a_fault() -> None:
    # A micro-inverter off at night reports "unavailable" — expected, not stale.
    states = {"sensor.pdl": _fresh(), "sensor.mppt": _fresh("unavailable")}
    r = EntityWatchdog(_hass(states)).check(["sensor.pdl"], [], ["sensor.mppt"])
    assert r.is_degraded is False
    assert "sensor.mppt" not in r.stale_entities


def test_optional_missing_is_not_a_fault() -> None:
    # The device dropped off the bus entirely (state None) — still expected for optional.
    r = EntityWatchdog(_hass({"sensor.pdl": _fresh()})).check(["sensor.pdl"], [], ["sensor.mppt"])
    assert r.stale_entities == []
    assert r.is_degraded is False


def test_optional_frozen_value_is_flagged() -> None:
    # Present with a numeric value but not updating = a stuck sensor → flagged.
    states = {"sensor.pdl": _fresh(), "sensor.mppt": _old("500")}
    r = EntityWatchdog(_hass(states)).check(["sensor.pdl"], [], ["sensor.mppt"])
    assert "sensor.mppt" in r.stale_entities
    assert r.is_degraded is False  # optional never degrades


def test_critical_stale_triggers_degraded() -> None:
    r = EntityWatchdog(_hass({"sensor.pdl": _old()})).check(["sensor.pdl"], [], [])
    assert r.is_degraded is True
    assert "sensor.pdl" in r.critical_stale


def test_off_optional_is_logged_once_not_every_tick(caplog) -> None:
    states = {"sensor.pdl": _fresh(), "sensor.mppt": _fresh("unavailable")}
    wd = EntityWatchdog(_hass(states))
    logger = "custom_components.solarbalance.adapters.watchdog"
    with caplog.at_level(logging.INFO, logger=logger):
        wd.check(["sensor.pdl"], [], ["sensor.mppt"])
        wd.check(["sensor.pdl"], [], ["sensor.mppt"])
        wd.check(["sensor.pdl"], [], ["sensor.mppt"])
    assert caplog.text.count("off (expected") == 1  # edge-triggered: once, not per tick
