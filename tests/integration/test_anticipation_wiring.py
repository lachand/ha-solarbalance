"""Integration tests for the anticipatory-curtailment wiring in the coordinator.

Focus: the sink budget must count **every** battery that can still absorb — the
non-controllable (cloud) one included — plus the commandable loads, and nothing that
is merely observed. Getting this wrong either brakes the array while a sink still had
room (wasted solar) or brakes too late (the export transient the feature exists for).
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_ANTICIPATORY_CURTAILMENT_ENABLED,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.controllers.anticipation import (
    SINK_CLOUD_BATTERY,
    SINK_CONTROLLABLE_BATTERY,
    SINK_LOAD,
)
from custom_components.solarbalance.core.models import (
    BatteryRole,
    BatteryState,
    Device,
    Load,
    LoadControlType,
    LoadState,
    MpptRole,
    Snapshot,
)


def _stream() -> Device:
    return Device(
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
        mppt=MpptRole(
            peak_power_w=2000,
            power_entity="sensor.bk_power",
            power_limit_setpoint_entity="number.bk_limit",
            active_control_enabled=True,
        ),
    )


def _cloud() -> Device:
    return Device(
        name="cloud",
        battery=BatteryRole(
            capacity_kwh=2.0,
            max_charge_power_w=800,
            max_discharge_power_w=800,
            soc_entity="sensor.cloud_soc",
            power_entity="sensor.cloud_power",
            soc_min_pct=10,
            soc_max_pct=100,
            controllable=False,
        ),
    )


def _ev() -> Load:
    return Load(
        name="ev",
        control_type=LoadControlType.ON_OFF,
        priority=1,
        nominal_power_w=1400,
        switch_entity="switch.ev",
    )


def _coordinator(hass: HomeAssistant, **cfg: Any) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ANTICIPATORY_CURTAILMENT_ENABLED: True, **cfg}
    )
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, [_stream(), _cloud()], [], [_ev()])


def _snapshot(
    *,
    stream_soc: float = 50.0,
    cloud_soc: float = 40.0,
    cloud_stale: bool = False,
    ev_draw_w: float = 0.0,
) -> Snapshot:
    return Snapshot(
        timestamp=datetime(2026, 7, 3, 12, 0, tzinfo=UTC),
        grid_power_w=0.0,
        batteries=(
            BatteryState(device_name="stream", soc_pct=stream_soc, power_w=0.0, available=True),
            BatteryState(
                device_name="cloud",
                soc_pct=cloud_soc,
                power_w=0.0,
                available=True,
                stale=cloud_stale,
            ),
        ),
        mppts=(),
        inverters=(),
        loads=(LoadState(name="ev", actual_power_w=ev_draw_w),),
    )


@pytest.mark.asyncio
async def test_sink_budget_counts_the_cloud_battery_and_the_loads(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    sinks = coord._collect_sinks(_snapshot(), charge_caps={"stream": 1200.0})
    by_kind = {s.kind: s for s in sinks}

    assert by_kind[SINK_CONTROLLABLE_BATTERY].absorb_w == 1200.0
    # The cloud battery cannot be commanded, but it is still soaking surplus — it must
    # count, or we would pre-curtail solar it would have absorbed.
    assert by_kind[SINK_CLOUD_BATTERY].name == "cloud"
    assert by_kind[SINK_CLOUD_BATTERY].absorb_w == 800.0
    assert by_kind[SINK_LOAD].absorb_w == 1400.0


@pytest.mark.asyncio
async def test_a_full_battery_is_no_longer_a_sink(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    sinks = coord._collect_sinks(
        _snapshot(stream_soc=100.0, cloud_soc=100.0), charge_caps={"stream": 1200.0}
    )
    assert [s.kind for s in sinks] == [SINK_LOAD]  # only the EV can still take power


@pytest.mark.asyncio
async def test_a_stale_cloud_battery_is_not_banked_on(hass: HomeAssistant) -> None:
    # We cannot trust its SoC/power, so we must not assume it will absorb anything —
    # assuming it would is exactly how the brake ends up firing too late.
    coord = _coordinator(hass)
    sinks = coord._collect_sinks(_snapshot(cloud_stale=True), charge_caps={"stream": 1200.0})
    assert SINK_CLOUD_BATTERY not in {s.kind for s in sinks}


@pytest.mark.asyncio
async def test_a_load_already_drawing_only_offers_its_spare_power(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    sinks = coord._collect_sinks(_snapshot(ev_draw_w=1000.0), charge_caps={"stream": 1200.0})
    load = next(s for s in sinks if s.kind == SINK_LOAD)
    assert load.absorb_w == 400.0  # 1400 nominal - 1000 already drawn


@pytest.mark.asyncio
async def test_disabled_by_default_keeps_curtailment_reactive(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coord = SolarBalanceCoordinator(hass, entry, [_stream(), _cloud()], [], [_ev()])
    assert coord._anticipation_enabled is False

    result = coord._evaluate_anticipation(_snapshot(), charge_caps={"stream": 1200.0})
    assert result.active is False
    assert result.preemptive_limit_w is None  # nothing handed to the curtailment brake
    assert result.reason == "disabled"
