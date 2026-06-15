"""Coordinator-level tests for anti-yoyo settle, grid-only force charge, per-load state."""

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance import COORDINATOR_KEY
from custom_components.solarbalance.const import (
    CONF_LOAD_CONTROL_ENABLED,
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TICK_INTERVAL_S,
    DOMAIN,
)
from custom_components.solarbalance.core.controllers.load_dispatch import LoadCommand
from custom_components.solarbalance.core.models import StrategyKind

_LOAD = ConfigSubentryData(
    subentry_type="load", title="voiture", unique_id=None,
    data={"name": "voiture", "control_type": "on_off", "priority": 5,
          "interruptible": True, "switch_entity": "switch.borne", "nominal_power_w": 2000},
)


@pytest.fixture
async def coord(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10, CONF_PHASES: 1, CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_LOAD_CONTROL_ENABLED: True,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
        subentries_data=[_LOAD],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]


async def test_anti_yoyo_settle_arms_on_load_drop(coord) -> None:
    """Dropping a big load arms the settle window with that power as feed-forward."""
    # Baseline tick: the load is on at 2000 W.
    coord._update_load_settle((LoadCommand(load_name="voiture", on=True, power_w=2000),))
    assert not coord._settle_state.active
    # Next tick: the load is dropped → settle armed for the configured ticks.
    coord._update_load_settle((LoadCommand(load_name="voiture", on=False),))
    assert coord._settle_state.active
    assert coord._settle_state.ticks_remaining == coord._zi_settle_ticks
    assert coord._settle_state.feedforward_w == pytest.approx(2000.0)


async def test_grid_only_force_charge_offset(coord) -> None:
    """The grid-only offset tracks the forced load's measured power (battery spared)."""
    from types import SimpleNamespace

    def snap(actual: float):
        return SimpleNamespace(loads=(SimpleNamespace(name="voiture", actual_power_w=actual),))

    assert coord._force_charge_grid_offset_w(snap(0.0)) == 0.0
    coord.request_force_charge_load("voiture")
    # Not drawing yet → no offset (no pre-charge from grid).
    assert coord._force_charge_grid_offset_w(snap(0.0)) == 0.0
    # Drawing 1400 W → offset matches the measured draw.
    assert coord._force_charge_grid_offset_w(snap(1400.0)) == pytest.approx(1400.0)
    # Clamped to nominal (2000 W) even if the meter overshoots.
    assert coord._force_charge_grid_offset_w(snap(5000.0)) == pytest.approx(2000.0)
    coord.cancel_force_charge_load("voiture")
    assert coord._force_charge_grid_offset_w(snap(1400.0)) == 0.0


async def test_load_status_reflects_overrides(coord) -> None:
    coord._last_load_commands = {"voiture": LoadCommand(load_name="voiture", on=True)}
    assert coord.load_status("voiture") == "actif"
    coord.request_force_charge_load("voiture")
    assert coord.load_status("voiture") == "charge forcée"
    coord.cancel_force_charge_load("voiture")
    coord._last_load_commands = {"voiture": LoadCommand(load_name="voiture", on=False)}
    assert coord.load_status("voiture") == "inactif"
