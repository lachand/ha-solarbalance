"""Integration tests for the SolarBalance coordinator setup."""

from datetime import UTC, datetime
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
from custom_components.solarbalance.core.models import (
    BatteryState,
    HemsMode,
    Snapshot,
    StrategyKind,
)

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


def _snap_with_cloud(grid_w: float, *, cloud_stale: bool) -> Snapshot:
    return Snapshot(
        timestamp=datetime(2026, 7, 2, 8, 0, tzinfo=UTC),
        grid_power_w=grid_w,
        batteries=(
            BatteryState(device_name="stream", soc_pct=50.0, power_w=0.0, available=True),
            BatteryState(
                device_name="cloud",
                soc_pct=30.0,
                power_w=0.0,
                available=True,
                stale=cloud_stale,
                stale_reason="soc" if cloud_stale else None,
                stale_age_s=400.0 if cloud_stale else None,
            ),
        ),
        mppts=(),
        inverters=(),
        loads=(),
    )


@pytest.mark.asyncio
async def test_baseline_floored_and_flagged_on_cloud_timeout(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A stale cloud battery discharging makes the raw baseline negative; the display
    value is floored at max(0, talon - 50) and flagged as a cloud timeout, not a mapping
    error. A plausible baseline is tracked verbatim."""
    from types import SimpleNamespace

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    coordinator._controllable_battery_names = frozenset({"stream"})
    coordinator._baseline_est = SimpleNamespace(talon_w=200.0)  # floor = 200 - 50 = 150
    coordinator._baseline_display_w = None  # fresh (setup already ran a few ticks)

    # Raw baseline = grid + pv - battery - loads = -400 → below the 150 floor, cloud stale.
    coordinator._update_baseline_display(_snap_with_cloud(-400.0, cloud_stale=True))
    assert coordinator.baseline_cloud_timeout is True
    assert coordinator.baseline_display_w == pytest.approx(150.0, abs=1.0)  # floored, not -400

    # Plausible baseline (grid +300) → tracked as-is, no cloud-timeout flag.
    coordinator._update_baseline_display(_snap_with_cloud(300.0, cloud_stale=True))
    assert coordinator.baseline_cloud_timeout is False
    assert coordinator.baseline_display_w == pytest.approx(300.0, abs=1.0)

    # Negative baseline WITHOUT a stale cloud → genuine mapping case, not flagged as timeout.
    coordinator._update_baseline_display(_snap_with_cloud(-400.0, cloud_stale=False))
    assert coordinator.baseline_cloud_timeout is False
