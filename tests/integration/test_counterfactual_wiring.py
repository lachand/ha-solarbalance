"""The counterfactual, wired: the shadow gets the real fleet's hardware and its day."""

from datetime import date, datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import BatteryRole, Device


def _device(name: str = "stream", *, controllable: bool = True) -> Device:
    return Device(
        name=name,
        battery=BatteryRole(
            capacity_kwh=4.0,
            max_charge_power_w=1200,
            max_discharge_power_w=1500,
            soc_entity=f"sensor.{name}_soc",
            power_entity=f"sensor.{name}_power",
            soc_min_pct=10,
            soc_max_pct=90,
            controllable=controllable,
        ),
    )


def _coordinator(hass: HomeAssistant, devices: list[Device]) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, devices, [], [])


@pytest.mark.asyncio
async def test_the_shadow_gets_the_soc_span_not_the_raw_capacity(hass: HomeAssistant) -> None:
    """It must not be handed a battery the real fleet is forbidden to empty.

    The real fleet may swing 10-90 % of its *usable* 3.8 kWh (4 kWh nameplate less
    the chemistry's reserve) = 3.04 kWh, and the stored figure it is compared
    against is measured on that same span. Giving the shadow the nameplate 4 kWh
    would make every real system look worse than it is.
    """
    coord = _coordinator(hass, [_device()])
    expected = 0.8 * _device().battery.effective_usable_capacity_kwh
    assert coord._counterfactual.usable_capacity_kwh == pytest.approx(expected)
    assert coord._counterfactual.max_charge_w == pytest.approx(1200.0)
    assert coord._counterfactual.max_discharge_w == pytest.approx(1500.0)


@pytest.mark.asyncio
async def test_uncontrollable_batteries_are_not_in_the_shadow(hass: HomeAssistant) -> None:
    """The comparison is about what SolarBalance steers, not what happens to sit nearby."""
    coord = _coordinator(hass, [_device(), _device("cloud", controllable=False)])
    solo = _coordinator(hass, [_device()])
    assert coord._counterfactual.usable_capacity_kwh == pytest.approx(
        solo._counterfactual.usable_capacity_kwh
    )


@pytest.mark.asyncio
async def test_a_fleet_with_no_controllable_battery_compares_nothing(
    hass: HomeAssistant,
) -> None:
    coord = _coordinator(hass, [_device("cloud", controllable=False)])
    assert coord._counterfactual.usable_capacity_kwh == 0.0
    assert coord.counterfactual.savings_eur == 0.0


@pytest.mark.asyncio
async def test_the_running_day_is_persisted_and_restored(hass: HomeAssistant) -> None:
    coord = _coordinator(hass, [_device()])
    start = datetime(2026, 7, 24, 10, 0)
    for i in range(30):
        coord._counterfactual.update(
            now=start + timedelta(minutes=i),
            local_date=date(2026, 7, 24),
            pv_w=1500.0,
            grid_w=-1100.0,  # exporting a surplus the shadow would have stored
            battery_w=0.0,
            stored_kwh=1.0,
            import_price=0.25,
            export_price=0.05,
        )
    before = coord.counterfactual
    assert before.savings_eur < 0.0

    fresh = _coordinator(hass, [_device()])
    await fresh._store.async_save(coord._persisted_state())
    await fresh.async_restore()
    assert fresh.counterfactual == before


@pytest.mark.asyncio
async def test_a_restart_does_not_bill_the_gap_to_either_scenario(hass: HomeAssistant) -> None:
    coord = _coordinator(hass, [_device()])
    start = datetime(2026, 7, 24, 10, 0)
    for i in range(10):
        coord._counterfactual.update(
            now=start + timedelta(minutes=i),
            local_date=date(2026, 7, 24),
            pv_w=1500.0,
            grid_w=-1100.0,
            battery_w=0.0,
            stored_kwh=1.0,
            import_price=0.25,
            export_price=0.05,
        )
    before = coord.counterfactual

    fresh = _coordinator(hass, [_device()])
    await fresh._store.async_save(coord._persisted_state())
    await fresh.async_restore()
    # HA came back three hours later; nothing was measured in between.
    fresh._counterfactual.update(
        now=start + timedelta(hours=3),
        local_date=date(2026, 7, 24),
        pv_w=1500.0,
        grid_w=-1100.0,
        battery_w=0.0,
        stored_kwh=2.0,
        import_price=0.25,
        export_price=0.05,
    )
    after = fresh.counterfactual
    assert after.actual_export_kwh == before.actual_export_kwh
    assert after.naive_import_kwh == before.naive_import_kwh
