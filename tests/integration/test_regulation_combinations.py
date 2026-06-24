"""Characterisation tests for the regulation pipeline (option combinations).

These pin the *current* aggregate fleet target (``diagnostics.fleet_target_w``)
for a set of option combinations, so the upcoming extraction of the clamp pipeline
into a pure function is provably behaviour-preserving. They assert robust
invariants (sign / bound / differential), not brittle exact values.
"""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.solarbalance import COORDINATOR_KEY, YAML_CONFIG_KEY
from custom_components.solarbalance.const import (
    CONF_ACTIVE_CONTROL_ENABLED,
    CONF_MAX_RAMP_W,
    CONF_NO_BATTERY_EXPORT,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import BatteryRole, Device, Meter, MeterKind

_BASE: dict[str, Any] = {
    CONF_ZERO_INJECTION_ENABLED: True,
    CONF_ZERO_INJECTION_SETPOINT_W: 0,
    CONF_ACTIVE_CONTROL_ENABLED: True,
    CONF_MAX_RAMP_W: 0,  # no slew: reach the full target on the first tick
}


def _stream(soc: int = 50) -> Device:
    return Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2300,
            max_discharge_power_w=2300,
            soc_entity="sensor.stream_soc",
            power_entity="sensor.stream_power",
            controllable=True,
            active_control_enabled=True,
            charge_power_setpoint_entity="number.stream_charge",
            discharge_power_setpoint_entity="number.stream_discharge",
        ),
    )


def _jackery() -> Device:
    return Device(
        name="jackery",
        battery=BatteryRole(
            capacity_kwh=2.0,
            max_charge_power_w=1000,
            max_discharge_power_w=1000,
            soc_entity="sensor.jackery_soc",
            power_entity="sensor.jackery_power",
            controllable=False,
        ),
    )


_METERS = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid_power")]


async def _run(
    hass: HomeAssistant,
    devices: list[Device],
    states: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> SolarBalanceCoordinator:
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, _METERS, [], None, None)
    for key, value in states.items():
        hass.states.async_set(key, str(value))
    async_mock_service(hass, "number", "set_value")
    entry = MockConfigEntry(domain=DOMAIN, data={**_BASE, **(options or {})})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]


@pytest.mark.asyncio
async def test_surplus_charges_the_fleet(hass: HomeAssistant) -> None:
    coord = await _run(
        hass,
        [_stream(soc=50)],
        {"sensor.stream_soc": 50, "sensor.stream_power": 0, "sensor.grid_power": -800},
    )
    assert coord.diagnostics.fleet_target_w > 0  # exporting → charge


@pytest.mark.asyncio
async def test_deficit_discharges_the_fleet(hass: HomeAssistant) -> None:
    coord = await _run(
        hass,
        [_stream(soc=50)],
        {"sensor.stream_soc": 50, "sensor.stream_power": 0, "sensor.grid_power": 800},
    )
    assert coord.diagnostics.fleet_target_w < 0  # importing → discharge


@pytest.mark.asyncio
async def test_no_battery_export_caps_discharge_vs_default(hass: HomeAssistant) -> None:
    # A discharging fleet that would push the grid into export: no_battery_export
    # must not discharge more than the default (it clamps the export away).
    states = {"sensor.stream_soc": 50, "sensor.stream_power": -1000, "sensor.grid_power": -300}
    default = await _run(hass, [_stream(soc=50)], states)
    capped = await _run(hass, [_stream(soc=50)], states, {CONF_NO_BATTERY_EXPORT: True})
    assert capped.diagnostics.fleet_target_w >= default.diagnostics.fleet_target_w
