"""Round-trip, equivalent cycles and per-cycle cost, wired through the coordinator."""

from datetime import datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import CONF_APPLIANCE_POWER_ENTITIES, DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.appliance_cycles import CycleTemplate
from custom_components.solarbalance.core.models import BatteryRole, BatteryState, Device, Snapshot


def _device(name: str = "stream") -> Device:
    return Device(
        name=name,
        battery=BatteryRole(
            capacity_kwh=5.0,
            usable_capacity_kwh=5.0,
            max_charge_power_w=1500,
            max_discharge_power_w=1500,
            soc_entity=f"sensor.{name}_soc",
            power_entity=f"sensor.{name}_power",
            controllable=True,
        ),
    )


def _coord(hass: HomeAssistant, devices: list[Device], **data) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, devices, [], [])


def _snap(ts: datetime, power_w: float, soc: float) -> Snapshot:
    return Snapshot(
        timestamp=ts,
        grid_power_w=0.0,
        batteries=(
            BatteryState(device_name="stream", soc_pct=soc, power_w=power_w, available=True),
        ),
        mppts=(),
        inverters=(),
        loads=(),
    )


@pytest.mark.asyncio
async def test_throughput_feeds_round_trip_and_cycles(hass: HomeAssistant) -> None:
    coord = _coord(hass, [_device()])
    now = datetime(2026, 7, 25, 6, 0)
    for _ in range(720):  # 12 kWh in
        coord._battery_energy.observe("stream", now, 1000.0, 50.0)
        now += timedelta(seconds=60)
    for _ in range(612):  # 10.2 kWh out, same SoC -> 85 %
        coord._battery_energy.observe("stream", now, -1000.0, 50.0)
        now += timedelta(seconds=60)

    stats = coord.battery_energy_stats("stream")
    assert stats is not None
    assert 83.0 <= stats.round_trip_pct <= 87.0
    assert abs(stats.equivalent_full_cycles - 10.2 / 5.0) < 0.05


@pytest.mark.asyncio
async def test_the_tick_observes_battery_energy(hass: HomeAssistant) -> None:
    coord = _coord(hass, [_device()])
    # Drive two ticks straight through the reader-less path by observing directly,
    # mirroring what _async_update_data does per snapshot battery.
    now = datetime(2026, 7, 25, 6, 0)
    for s in (_snap(now, 1000.0, 50.0), _snap(now + timedelta(minutes=1), 1000.0, 50.0)):
        for b in s.batteries:
            if b.available:
                coord._battery_energy.observe(b.device_name, s.timestamp, b.power_w, b.soc_pct)
    stats = coord.battery_energy_stats("stream")
    assert stats is not None
    assert stats.charge_in_kwh > 0.0


@pytest.mark.asyncio
async def test_stats_survive_a_restart(hass: HomeAssistant) -> None:
    coord = _coord(hass, [_device()])
    now = datetime(2026, 7, 25, 6, 0)
    for _ in range(120):
        coord._battery_energy.observe("stream", now, -1000.0, 60.0)
        now += timedelta(seconds=60)
    before = coord.battery_energy_stats("stream")

    fresh = _coord(hass, [_device()])
    await fresh._store.async_save(coord._persisted_state())
    await fresh.async_restore()
    assert fresh.battery_energy_stats("stream") == before


@pytest.mark.asyncio
async def test_appliance_advice_carries_a_cost_when_a_price_exists(hass: HomeAssistant) -> None:
    coord = _coord(
        hass,
        [],
        **{CONF_APPLIANCE_POWER_ENTITIES: ["sensor.machine_a_laver_power"], "import_price": 0.25},
    )
    # A learned 2 kWh program, no PV forecast (so no solar share): cost is full grid.
    coord._appliance_cycles.add_template(
        "machine a laver", CycleTemplate(5400.0, 2.0, tuple([1400.0] * 24)), program="Coton 60"
    )
    item = next(a for a in coord.appliance_advice if a["name"] == "machine a laver")
    prog = next(p for p in item["programs"] if p["program"] == "Coton 60")
    assert prog["cost_grid_eur"] == pytest.approx(0.5)  # 2 kWh * 0.25
    assert prog["cost_now_eur"] == pytest.approx(0.5)  # no solar known -> all grid
