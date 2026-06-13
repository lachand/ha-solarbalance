"""End-to-end test: one real coordinator tick drives the full control chain.

Configures a PDL meter, a controllable battery (active control) and a PV
inverter + an on/off load, seeds entity states for an export situation, runs a
tick and asserts the chain produced the expected writes: the battery is told to
charge (zero-injection soaks up the export) and the surplus turns the load on.
"""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.solarbalance import COORDINATOR_KEY, YAML_CONFIG_KEY
from custom_components.solarbalance.const import (
    CONF_ACTIVE_CONTROL_ENABLED,
    CONF_LOAD_CONTROL_ENABLED,
    CONF_MAX_RAMP_W,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import (
    BatteryRole,
    Device,
    Load,
    LoadControlType,
    Meter,
    MeterKind,
    MpptRole,
)

_ENTRY_DATA: dict[str, Any] = {
    CONF_ZERO_INJECTION_ENABLED: True,
    CONF_ZERO_INJECTION_SETPOINT_W: 0,
    CONF_ACTIVE_CONTROL_ENABLED: True,
    CONF_LOAD_CONTROL_ENABLED: True,
    CONF_MAX_RAMP_W: 0,  # disable slew so the first tick reaches the full target
}


def _config() -> tuple[list[Device], list[Meter], list[Load]]:
    devices = [
        Device(
            name="batt",
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=3000,
                max_discharge_power_w=3000,
                soc_entity="sensor.batt_soc",
                power_entity="sensor.batt_power",
                controllable=True,
                active_control_enabled=True,
                charge_power_setpoint_entity="number.batt_charge",
                discharge_power_setpoint_entity="number.batt_discharge",
            ),
        ),
        Device(name="pv", mppt=MpptRole(peak_power_w=3000, power_entity="sensor.pv_power")),
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid_power")]
    loads = [
        Load(
            name="wh",
            control_type=LoadControlType.ON_OFF,
            priority=1,
            nominal_power_w=500,
            switch_entity="switch.water_heater",
            actual_power_entity="sensor.wh_power",
        )
    ]
    return devices, meters, loads


@pytest.mark.asyncio
async def test_full_tick_charges_battery_and_runs_load_on_export(hass: HomeAssistant) -> None:
    devices, meters, loads = _config()
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, loads, None, None)

    # Export situation: PV 2000 W, grid -1500 W (exporting), battery idle at 50%.
    hass.states.async_set("sensor.grid_power", "-1500")
    hass.states.async_set("sensor.pv_power", "2000")
    hass.states.async_set("sensor.batt_soc", "50")
    hass.states.async_set("sensor.batt_power", "0")
    hass.states.async_set("sensor.wh_power", "0")
    hass.states.async_set("switch.water_heater", "off")

    number_calls = async_mock_service(hass, "number", "set_value")
    turn_on_calls = async_mock_service(hass, "homeassistant", "turn_on")

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    snap = coordinator.data
    assert snap is not None
    assert snap.grid_power_w == -1500
    assert snap.pv_total_w == 2000

    # Zero-injection soaks up the export → fleet target is a positive (charge) power.
    assert coordinator.diagnostics.fleet_target_w > 0

    # The battery charge setpoint was written (> 0 W) to its number entity.
    charge_writes = [
        c.data["value"]
        for c in number_calls
        if c.data.get("entity_id") == "number.batt_charge"
    ]
    assert charge_writes and charge_writes[-1] > 0

    # The remaining surplus turned the load on.
    assert any(
        "switch.water_heater" in (c.data.get("entity_id") or "") for c in turn_on_calls
    )
