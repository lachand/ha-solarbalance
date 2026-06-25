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
    CONF_PV_DROP_COMPENSATION_ENABLED,
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
        c.data["value"] for c in number_calls if c.data.get("entity_id") == "number.batt_charge"
    ]
    assert charge_writes and charge_writes[-1] > 0

    # The remaining surplus turned the load on.
    assert any("switch.water_heater" in (c.data.get("entity_id") or "") for c in turn_on_calls)


@pytest.mark.asyncio
async def test_curtails_inverter_when_fleet_near_full_and_exporting(hass: HomeAssistant) -> None:
    """A near-full controllable fleet that keeps exporting must curtail the inverter.

    At 94 % (soc_max 95 %) the balancer still "allocates" the surplus, so the
    unallocated residual is ~0. Curtailment must engage on the near-full signal,
    otherwise the export persists forever (the bug this guards against).
    """
    devices = [
        Device(
            name="stream",
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=3000,
                max_discharge_power_w=3000,
                soc_entity="sensor.stream_soc",
                power_entity="sensor.stream_power",
                soc_max_pct=95,
                controllable=True,
                active_control_enabled=True,
                charge_power_setpoint_entity="number.stream_charge",
                discharge_power_setpoint_entity="number.stream_discharge",
            ),
            mppt=MpptRole(
                peak_power_w=3000,
                power_entity="sensor.stream_pv",
                active_control_enabled=True,
                power_limit_setpoint_entity="number.stream_pv_limit",
            ),
        ),
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid_power")]
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, [], None, None)

    # Near-full (94% is within 2% of the 95% ceiling) and exporting 500 W, PV 1500 W.
    hass.states.async_set("sensor.grid_power", "-500")
    hass.states.async_set("sensor.stream_pv", "1500")
    hass.states.async_set("sensor.stream_soc", "94")
    hass.states.async_set("sensor.stream_power", "0")

    number_calls = async_mock_service(hass, "number", "set_value")

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    # The inverter output limit was lowered below its 3000 W peak.
    assert coordinator.diagnostics.pv_limit_w < 3000
    limit_writes = [
        c.data["value"] for c in number_calls if c.data.get("entity_id") == "number.stream_pv_limit"
    ]
    assert limit_writes and limit_writes[-1] < 3000


@pytest.mark.asyncio
async def test_near_full_has_release_hysteresis(hass: HomeAssistant) -> None:
    """Once near-full engages, a SoC dipping just under the margin must not release it
    (which would flip the PV limit / no-charge floor and hunt). It stays latched until
    the SoC drops a further hysteresis band."""
    devices = [
        Device(
            name="stream",
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=3000,
                max_discharge_power_w=3000,
                soc_entity="sensor.stream_soc",
                power_entity="sensor.stream_power",
                soc_max_pct=95,
                controllable=True,
                active_control_enabled=True,
                charge_power_setpoint_entity="number.stream_charge",
                discharge_power_setpoint_entity="number.stream_discharge",
            ),
            mppt=MpptRole(
                peak_power_w=3000,
                power_entity="sensor.stream_pv",
                active_control_enabled=True,
                power_limit_setpoint_entity="number.stream_pv_limit",
            ),
        ),
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid_power")]
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, [], None, None)
    hass.states.async_set("sensor.grid_power", "-500")  # exporting
    hass.states.async_set("sensor.stream_pv", "1500")
    hass.states.async_set("sensor.stream_soc", "94")  # within 2% of 95 → engage
    hass.states.async_set("sensor.stream_power", "0")
    async_mock_service(hass, "number", "set_value")
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    assert coordinator._curtail_near_full is True

    # SoC dips to 92% — below the 2% engage margin (93) but within the 3% release
    # hysteresis (90): the latch must hold (no flip → no hunting).
    hass.states.async_set("sensor.stream_soc", "92")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._curtail_near_full is True


@pytest.mark.asyncio
async def test_cloud_charge_signal_is_smoothed_across_ticks(hass: HomeAssistant) -> None:
    """A cloud battery's charge bursts are EMA-smoothed before the cloud guards.

    A single burst tick must move the smoothed signal by only ~alpha (≈0.2), not the
    full value, so a 30 s Jackery blip cannot chop the fleet (the morning-yoyo fix).
    """
    devices = [
        Device(
            name="stream",
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=2300,
                max_discharge_power_w=2300,
                soc_entity="sensor.stream_soc",
                power_entity="sensor.stream_power",
                controllable=True,
                active_control_enabled=True,
                discharge_power_setpoint_entity="number.stream_discharge",
            ),
        ),
        Device(
            name="jackery",
            battery=BatteryRole(
                capacity_kwh=2.0,
                max_charge_power_w=1000,
                max_discharge_power_w=1000,
                soc_entity="sensor.jackery_soc",
                power_entity="sensor.jackery_power",
                controllable=False,
            ),
        ),
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid_power")]
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, [], None, None)
    hass.states.async_set("sensor.grid_power", "0")
    hass.states.async_set("sensor.stream_soc", "50")
    hass.states.async_set("sensor.stream_power", "0")
    hass.states.async_set("sensor.jackery_soc", "60")
    hass.states.async_set("sensor.jackery_power", "0")  # not charging at setup

    async_mock_service(hass, "number", "set_value")
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    assert coordinator._nc_charge_smoothed_w == pytest.approx(0.0, abs=1.0)

    # One burst tick: the EMA must damp 600 W down to ~0.2*600, not jump to 600.
    hass.states.async_set("sensor.jackery_power", "600")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert 0.0 < coordinator._nc_charge_smoothed_w < 600.0
    assert coordinator._nc_charge_smoothed_w == pytest.approx(120.0, abs=25.0)


@pytest.mark.asyncio
async def test_pv_drop_detected_and_compensated(hass: HomeAssistant) -> None:
    """A sudden PV drop sets the diagnostic and (opt-in) makes the fleet discharge."""
    devices = [
        Device(
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
            mppt=MpptRole(peak_power_w=3000, power_entity="sensor.stream_pv"),
        ),
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid_power")]
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, [], None, None)
    # PV covering the house: grid ~0, fleet idle.
    hass.states.async_set("sensor.grid_power", "0")
    hass.states.async_set("sensor.stream_pv", "2000")
    hass.states.async_set("sensor.stream_soc", "50")
    hass.states.async_set("sensor.stream_power", "0")

    async_mock_service(hass, "number", "set_value")
    entry = MockConfigEntry(
        domain=DOMAIN, data={**_ENTRY_DATA, CONF_PV_DROP_COMPENSATION_ENABLED: True}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    assert coordinator.diagnostics.pv_drop_w == 0.0  # steady → no drop

    # Cloud: PV collapses, the house now imports.
    hass.states.async_set("sensor.stream_pv", "200")
    hass.states.async_set("sensor.grid_power", "1800")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.diagnostics.pv_drop_w > 0.0  # drop detected
    assert coordinator.diagnostics.fleet_target_w < 0.0  # fleet told to discharge


@pytest.mark.asyncio
async def test_dry_run_computes_but_never_writes(hass: HomeAssistant) -> None:
    """In dry-run the engine decides (fleet target set) but writes nothing."""
    devices, meters, loads = _config()
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, loads, None, None)

    hass.states.async_set("sensor.grid_power", "-1500")  # export → would charge + run load
    hass.states.async_set("sensor.pv_power", "2000")
    hass.states.async_set("sensor.batt_soc", "50")
    hass.states.async_set("sensor.batt_power", "0")
    hass.states.async_set("sensor.wh_power", "0")
    hass.states.async_set("switch.water_heater", "off")

    number_calls = async_mock_service(hass, "number", "set_value")
    turn_on_calls = async_mock_service(hass, "homeassistant", "turn_on")

    entry = MockConfigEntry(domain=DOMAIN, data={**_ENTRY_DATA, "dry_run": True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    # The decision is still computed (battery would charge on the export)...
    assert coordinator.diagnostics.fleet_target_w > 0
    # ...but nothing was written to hardware.
    assert not number_calls
    assert not turn_on_calls


@pytest.mark.asyncio
async def test_full_tick_force_charge_is_grid_backed(hass: HomeAssistant) -> None:
    """A forced load draws from the grid; the battery is not discharged to feed it."""
    devices, meters, loads = _config()
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, loads, None, None)

    # Night, no PV: the load (wh) already draws its 500 W, so the grid carries
    # house + load. Battery idle at 50 %.
    hass.states.async_set("sensor.grid_power", "800")  # 300 house + 500 load
    hass.states.async_set("sensor.pv_power", "0")
    hass.states.async_set("sensor.batt_soc", "50")
    hass.states.async_set("sensor.batt_power", "0")
    hass.states.async_set("sensor.wh_power", "500")
    hass.states.async_set("switch.water_heater", "on")

    async_mock_service(hass, "number", "set_value")
    async_mock_service(hass, "homeassistant", "turn_on")

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    coordinator.request_force_charge_load("wh")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Grid-only feed-forward cancels the load's 500 W: the battery still discharges
    # to cover the ~300 W house, but NOT the load — so the target is well above the
    # -480 W (0.6 * 800) it would be if the loop tried to zero the full grid import.
    target = coordinator.diagnostics.fleet_target_w
    assert -300.0 < target <= 0.0


@pytest.mark.asyncio
async def test_full_tick_off_peak_load_not_turned_on(hass: HomeAssistant) -> None:
    """An off-peak-only load is not switched on outside a cheap window, even on surplus."""
    devices, meters, loads = _config()
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, loads, None, None)

    # Big export → dispatch would normally turn the load on.
    hass.states.async_set("sensor.grid_power", "-1500")
    hass.states.async_set("sensor.pv_power", "2000")
    hass.states.async_set("sensor.batt_soc", "50")
    hass.states.async_set("sensor.batt_power", "0")
    hass.states.async_set("sensor.wh_power", "0")
    hass.states.async_set("switch.water_heater", "off")

    async_mock_service(hass, "number", "set_value")
    turn_on_calls = async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")

    # Flat tariff above the cheap threshold (0.15) → never a cheap window.
    entry = MockConfigEntry(domain=DOMAIN, data={**_ENTRY_DATA, "import_price": 0.30})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    turn_on_calls.clear()  # ignore the initial setup tick
    coordinator.set_off_peak_only("wh", True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Despite the surplus, the off-peak guard keeps the load off.
    assert not any("switch.water_heater" in (c.data.get("entity_id") or "") for c in turn_on_calls)
    assert coordinator.load_status("wh") == "off_peak_wait"


@pytest.mark.asyncio
async def test_full_tick_force_charge_turns_switch_on(hass: HomeAssistant) -> None:
    """Force-charge turns the load on even with no surplus."""
    devices, meters, loads = _config()
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, loads, None, None)

    hass.states.async_set("sensor.grid_power", "300")  # importing, no surplus
    hass.states.async_set("sensor.pv_power", "0")
    hass.states.async_set("sensor.batt_soc", "50")
    hass.states.async_set("sensor.batt_power", "0")
    hass.states.async_set("sensor.wh_power", "0")
    hass.states.async_set("switch.water_heater", "off")

    async_mock_service(hass, "number", "set_value")
    turn_on_calls = async_mock_service(hass, "homeassistant", "turn_on")

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    coordinator.request_force_charge_load("wh")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert any("switch.water_heater" in (c.data.get("entity_id") or "") for c in turn_on_calls)
    assert coordinator.load_status("wh") == "force_charge"


@pytest.mark.asyncio
async def test_anti_yoyo_freezes_zi_over_consecutive_ticks(hass: HomeAssistant) -> None:
    """While settling, the ZI loop is frozen: the one-shot feed-forward then 0."""
    from custom_components.solarbalance.core.controllers.load_settle import SettleState

    devices, meters, loads = _config()
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, loads, None, None)

    hass.states.async_set("sensor.grid_power", "1000")  # importing → PI would react
    hass.states.async_set("sensor.pv_power", "0")
    hass.states.async_set("sensor.batt_soc", "50")
    hass.states.async_set("sensor.batt_power", "0")
    hass.states.async_set("sensor.wh_power", "0")
    hass.states.async_set("switch.water_heater", "off")
    async_mock_service(hass, "number", "set_value")
    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    coordinator._settle_state = SettleState(ticks_remaining=2, feedforward_w=500.0)

    # Tick 1: ZI frozen, correction = the one-shot feed-forward (not the PI value).
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.diagnostics.zero_injection_correction_w == pytest.approx(500.0)
    assert coordinator._settle_state.ticks_remaining == 1

    # Tick 2: still frozen, feed-forward exhausted (0), window about to close.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.diagnostics.zero_injection_correction_w == pytest.approx(0.0)
    assert coordinator._settle_state.ticks_remaining == 0
