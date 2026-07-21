"""The capture_debug service: dump the rolling tick history to JSONL for replay."""

import json
import os

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import BatteryRole, Device


def _coordinator(hass: HomeAssistant) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    device = Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=4.0,
            max_charge_power_w=1200,
            max_discharge_power_w=1200,
            soc_entity="sensor.stream_soc",
            power_entity="sensor.stream_power",
            soc_min_pct=10,
            soc_max_pct=100,
            controllable=True,
        ),
    )
    return SolarBalanceCoordinator(hass, entry, [device], [], [])


def _rec(t: str, bind: str = "base", grid: float = 0.0) -> dict:
    return {"t": t, "bind": bind, "grid": grid, "per": {"stream": -100.0}}


@pytest.mark.asyncio
async def test_capture_writes_valid_jsonl(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    coord._tick_history.append(_rec("2026-07-21T10:00:00+02:00", grid=195.0))
    coord._tick_history.append(_rec("2026-07-21T10:00:10+02:00", "no_charge_floor", -30.0))

    res = await coord.capture_debug()

    assert res["ticks"] == 2
    assert res["from"] == "2026-07-21T10:00:00+02:00"
    assert res["to"] == "2026-07-21T10:00:10+02:00"
    assert os.path.isfile(res["path"])
    with open(res["path"], encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    assert len(rows) == 2
    assert rows[1]["bind"] == "no_charge_floor"


@pytest.mark.asyncio
async def test_capture_minutes_keeps_only_the_recent_window(hass: HomeAssistant) -> None:
    from homeassistant.util import dt as dt_util

    coord = _coordinator(hass)
    now = dt_util.now()
    coord._tick_history.append(_rec((now.replace(microsecond=0)).isoformat()))
    old = now.replace(microsecond=0).replace(year=2020)
    coord._tick_history.appendleft(_rec(old.isoformat()))

    res = await coord.capture_debug(minutes=30)
    assert res["ticks"] == 1  # the 2020 record is dropped


@pytest.mark.asyncio
async def test_capture_empty_buffer_is_a_noop(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    res = await coord.capture_debug()
    assert res == {"path": None, "ticks": 0, "from": None, "to": None}


@pytest.mark.asyncio
async def test_ring_buffer_is_bounded(hass: HomeAssistant) -> None:
    from custom_components.solarbalance.coordinator import _TICK_HISTORY_MAXLEN

    coord = _coordinator(hass)
    for i in range(_TICK_HISTORY_MAXLEN + 50):
        coord._tick_history.append(_rec(f"2026-07-21T10:00:{i % 60:02d}+02:00"))
    assert len(coord._tick_history) == _TICK_HISTORY_MAXLEN
