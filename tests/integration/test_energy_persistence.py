"""Integration test: daily energy counters persist across coordinator reloads."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_TICK_INTERVAL_S,
    CONF_ZERO_INJECTION_ENABLED,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator

_ENTRY_DATA: dict[str, Any] = {CONF_TICK_INTERVAL_S: 10, CONF_ZERO_INJECTION_ENABLED: True}


@pytest.mark.asyncio
async def test_daily_energy_persists_across_instances(hass: HomeAssistant) -> None:
    """A new coordinator instance restores the previously saved daily counters."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)

    first = SolarBalanceCoordinator(hass, entry, [], [], [])
    first._energy.restore(day=dt_util.now().date(), pv_kwh=4.2, grid_import_kwh=1.3)
    await first._store.async_save(first._persisted_state())

    # Simulate an integration reload: a fresh coordinator over the same store.
    second = SolarBalanceCoordinator(hass, entry, [], [], [])
    assert second._energy.pv_kwh == 0.0  # fresh before restore
    await second.async_restore()
    assert second._energy.pv_kwh == pytest.approx(4.2)
    assert second._energy.grid_import_kwh == pytest.approx(1.3)


@pytest.mark.asyncio
async def test_restore_without_store_is_noop(hass: HomeAssistant) -> None:
    """Restoring with no persisted data leaves the counters at zero."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    entry.add_to_hass(hass)
    coordinator = SolarBalanceCoordinator(hass, entry, [], [], [])
    await coordinator.async_restore()
    assert coordinator._energy.pv_kwh == 0.0
    assert coordinator._energy.grid_import_kwh == 0.0
