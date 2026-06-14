"""Integration tests for mode-driven coordinator wiring (storm reserve, etc.)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_BACKUP_RESERVE_SOC_PCT,
    CONF_HC_PRICE,
    CONF_HP_PRICE,
    CONF_TARIFF_TYPE,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import BatteryRole, Device, HemsMode


def _stream_device() -> Device:
    return Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=3.9,
            max_charge_power_w=1200,
            max_discharge_power_w=2300,
            soc_entity="sensor.stream_soc",
            power_entity="sensor.stream_power",
            soc_min_pct=10,
            soc_max_pct=95,
            controllable=True,
            active_control_enabled=True,
            discharge_power_setpoint_entity="number.stream_discharge",
            reserve_soc_setpoint_entity="number.stream_reserve",
        ),
    )


def _make_coordinator(hass: HomeAssistant, **cfg: Any) -> SolarBalanceCoordinator:
    data = {CONF_BACKUP_RESERVE_SOC_PCT: 20, **cfg}
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, [_stream_device()], [], [])


@pytest.mark.asyncio
async def test_reserve_setpoint_raised_in_storm(hass: HomeAssistant) -> None:
    coord = _make_coordinator(hass)

    coord._mode = HemsMode.STORM
    # Storm raises the device reserve to the storm target (clamped to soc_max=95).
    assert coord._reserve_setpoints() == {"stream": 95.0}

    coord._mode = HemsMode.NORMAL
    # Outside storm it tracks the configured backup reserve.
    assert coord._reserve_setpoints() == {"stream": 20.0}


@pytest.mark.asyncio
async def test_reserve_setpoint_absent_without_entity(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BACKUP_RESERVE_SOC_PCT: 20})
    entry.add_to_hass(hass)
    device = Device(
        name="nobackup",
        battery=BatteryRole(
            capacity_kwh=3.9,
            max_charge_power_w=1200,
            max_discharge_power_w=2300,
            soc_entity="sensor.soc",
            power_entity="sensor.power",
        ),
    )
    coord = SolarBalanceCoordinator(hass, entry, [device], [], [])
    coord._mode = HemsMode.STORM
    assert coord._reserve_setpoints() == {}  # no reserve entity → nothing to write


@pytest.mark.asyncio
async def test_ui_tariff_hc_hp(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TARIFF_TYPE: "hc_hp", CONF_HC_PRICE: 0.18, CONF_HP_PRICE: 0.30},
    )
    entry.add_to_hass(hass)
    coord = SolarBalanceCoordinator(hass, entry, [], [], [])
    assert coord.tariff_time_varying is True
    night = datetime(2026, 6, 14, 1, 0, tzinfo=UTC)  # 03:00 Paris → HC
    day = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)  # midday → HP
    assert coord._tariff.current_import_price(night) == 0.18
    assert coord._tariff.current_import_price(day) == 0.30


@pytest.mark.asyncio
async def test_tariff_misconfig_falls_back_to_flat(hass: HomeAssistant) -> None:
    # tariff_type=tempo without a colour entity must NOT crash setup → flat.
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TARIFF_TYPE: "tempo"})
    entry.add_to_hass(hass)
    coord = SolarBalanceCoordinator(hass, entry, [], [], [])
    assert coord.tariff_time_varying is False  # degraded to flat
    assert coord.current_import_price is not None


@pytest.mark.asyncio
async def test_spot_hourly_prices(hass: HomeAssistant) -> None:
    from custom_components.solarbalance.const import CONF_SPOT_PRICE_ENTITY, CONF_TARIFF_TYPE
    raw = [
        {"start": "2026-06-14T10:00:00+00:00", "end": "2026-06-14T11:00:00+00:00", "value": 0.12},
        {"start": "2026-06-14T11:00:00+00:00", "end": "2026-06-14T12:00:00+00:00", "value": 0.40},
    ]
    hass.states.async_set("sensor.spot", "0.30", {"raw_today": raw})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TARIFF_TYPE: "spot", CONF_SPOT_PRICE_ENTITY: "sensor.spot"},
    )
    entry.add_to_hass(hass)
    coord = SolarBalanceCoordinator(hass, entry, [], [], [])
    t10 = datetime(2026, 6, 14, 10, 30, tzinfo=UTC)
    t11 = datetime(2026, 6, 14, 11, 30, tzinfo=UTC)
    t13 = datetime(2026, 6, 14, 13, 30, tzinfo=UTC)  # no raw entry → current state
    assert coord._tariff.current_import_price(t10) == 0.12
    assert coord._tariff.current_import_price(t11) == 0.40
    assert coord._tariff.current_import_price(t13) == 0.30
