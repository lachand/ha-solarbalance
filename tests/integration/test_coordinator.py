"""Integration tests for the SolarBalance coordinator setup."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance import COORDINATOR_KEY
from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TICK_INTERVAL_S,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import HemsMode, StrategyKind

_BASE_ENTRY_DATA: dict[str, Any] = {
    CONF_TICK_INTERVAL_S: 10,
    CONF_ZERO_INJECTION_ENABLED: True,
    CONF_ZERO_INJECTION_SETPOINT_W: 0,
    CONF_ZERO_INJECTION_HYSTERESIS_W: 50,
    CONF_PHASES: 1,
    CONF_SUBSCRIBED_POWER_KVA: 6,
    CONF_PRIORITIES: [k.value for k in StrategyKind],
}


@pytest.fixture
async def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and set up a SolarBalance config entry with no YAML devices."""
    entry = MockConfigEntry(domain=DOMAIN, data=_BASE_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_coordinator_created_after_setup(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Entry setup should instantiate a SolarBalanceCoordinator."""
    assert DOMAIN in hass.data
    assert config_entry.entry_id in hass.data[DOMAIN]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    assert isinstance(coordinator, SolarBalanceCoordinator)


@pytest.mark.asyncio
async def test_coordinator_default_mode_is_normal(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """After first refresh, coordinator should be in NORMAL mode."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    assert coordinator.mode is HemsMode.NORMAL


@pytest.mark.asyncio
async def test_unload_entry_removes_coordinator(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Unloading the entry should remove the coordinator from hass.data."""
    assert config_entry.entry_id in hass.data[DOMAIN]
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.entry_id not in hass.data.get(DOMAIN, {})
