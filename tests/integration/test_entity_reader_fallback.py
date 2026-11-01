"""Fallback entities in EntityReader: BLE sensor down, Wi-Fi twin takes over."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.solarbalance.adapters.entity_reader import EntityReader
from custom_components.solarbalance.core.models import BatteryRole, Device, MpptRole


def _state(value: object) -> SimpleNamespace:
    now = dt_util.utcnow()
    return SimpleNamespace(state=str(value), attributes={}, last_updated=now, last_reported=now)


def _device() -> Device:
    return Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=1.9,
            max_charge_power_w=1000,
            max_discharge_power_w=1000,
            soc_entity="sensor.soc_ble",
            extra_soc_entities=("sensor.soc_wifi",),
            power_entity="sensor.p",
            controllable=False,
        ),
        mppt=MpptRole(
            peak_power_w=800,
            power_entity="sensor.pv_ble",
            fallback_power_entities=("sensor.pv_wifi",),
        ),
    )


def _reader(states: dict[str, SimpleNamespace]) -> EntityReader:
    return EntityReader(MagicMock(), [_device()], [], state_getter=lambda eid: states.get(eid))


@pytest.mark.parametrize(
    ("states", "expected_soc"),
    [
        ({"sensor.soc_ble": _state(60), "sensor.soc_wifi": _state(58)}, 60.0),
        ({"sensor.soc_ble": _state("unavailable"), "sensor.soc_wifi": _state(58)}, 58.0),
        ({"sensor.soc_wifi": _state(58)}, 58.0),
    ],
)
def test_soc_falls_back_when_primary_unavailable(
    states: dict[str, SimpleNamespace], expected_soc: float
) -> None:
    reader = _reader({**states, "sensor.p": _state(0)})
    batt = reader._read_batteries()[0]
    assert batt.soc_pct == expected_soc
    assert batt.available is True


def test_battery_unavailable_when_every_soc_candidate_is_down() -> None:
    reader = _reader({"sensor.soc_ble": _state("unavailable"), "sensor.p": _state(0)})
    assert reader._read_batteries()[0].available is False


@pytest.mark.parametrize(
    ("states", "expected_w", "expected_available"),
    [
        # Both links up: primary only — the Wi-Fi twin must not be added on top.
        ({"sensor.pv_ble": _state(300), "sensor.pv_wifi": _state(310)}, 300.0, True),
        ({"sensor.pv_ble": _state("unavailable"), "sensor.pv_wifi": _state(310)}, 310.0, True),
        ({"sensor.pv_ble": _state("unavailable")}, 0.0, False),
    ],
)
def test_mppt_falls_back_only_when_primary_unavailable(
    states: dict[str, SimpleNamespace], expected_w: float, expected_available: bool
) -> None:
    mppt = _reader(states)._read_mppts()[0]
    assert mppt.power_w == expected_w
    assert mppt.available is expected_available
