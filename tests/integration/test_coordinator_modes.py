"""Integration tests for mode-driven coordinator wiring (storm reserve, etc.)."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import CONF_BACKUP_RESERVE_SOC_PCT, DOMAIN
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
