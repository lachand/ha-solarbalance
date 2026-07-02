"""Battery staleness detection in EntityReader (SoC and power sources)."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.util import dt as dt_util

from custom_components.solarbalance.adapters.entity_reader import EntityReader
from custom_components.solarbalance.core.models import BatteryRole, Device


def _cloud_device() -> Device:
    return Device(
        name="cloud",
        battery=BatteryRole(
            capacity_kwh=2.0,
            max_charge_power_w=1000,
            max_discharge_power_w=1000,
            soc_entity="sensor.soc",
            power_entity="sensor.pow",
            soc_min_pct=10,
            controllable=False,
        ),
    )


def _state(value: object, age_s: float) -> SimpleNamespace:
    return SimpleNamespace(
        state=str(value),
        attributes={},
        last_updated=dt_util.utcnow() - timedelta(seconds=age_s),
    )


def _reader(states: dict[str, SimpleNamespace]) -> EntityReader:
    return EntityReader(
        MagicMock(),
        [_cloud_device()],
        [],
        state_getter=lambda eid: states.get(eid),
    )


def test_stale_soc_flags_battery_even_when_power_is_fresh() -> None:
    # The user's Jackery case: SoC entity timed out (age > 300 s) while power kept
    # updating. The equaliser steers on SoC, so this must be flagged stale.
    reader = _reader({"sensor.soc": _state(34, 400), "sensor.pow": _state(-100, 5)})
    batt = reader._read_batteries()[0]
    assert batt.available is True  # SoC still reports a (frozen) value
    assert batt.stale is True


def test_fresh_battery_is_not_stale() -> None:
    reader = _reader({"sensor.soc": _state(34, 10), "sensor.pow": _state(-100, 5)})
    batt = reader._read_batteries()[0]
    assert batt.stale is False


def test_stale_power_still_flags_when_soc_fresh() -> None:
    # Original behaviour preserved: an old power source alone marks stale.
    reader = _reader({"sensor.soc": _state(34, 10), "sensor.pow": _state(-100, 400)})
    batt = reader._read_batteries()[0]
    assert batt.stale is True
