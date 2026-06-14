"""Cumulative month/year savings accumulation."""

from datetime import date

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance import COORDINATOR_KEY
from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TICK_INTERVAL_S,
    DOMAIN,
)
from custom_components.solarbalance.core.models import StrategyKind


@pytest.fixture
async def coordinator(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10, CONF_PHASES: 1, CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]


async def test_savings_accumulate_and_reset_on_rollover(coordinator) -> None:
    c = coordinator
    c._accumulate_savings(date(2026, 1, 10), 1.5)
    c._accumulate_savings(date(2026, 1, 20), 2.0)
    assert c.savings_month_eur == 3.5
    assert c.savings_year_eur == 3.5

    # New month: month total resets, year keeps accumulating.
    c._accumulate_savings(date(2026, 2, 5), 1.0)
    assert c.savings_month_eur == 1.0
    assert c.savings_year_eur == 4.5

    # New year: both reset.
    c._accumulate_savings(date(2027, 1, 3), 0.7)
    assert c.savings_month_eur == 0.7
    assert c.savings_year_eur == 0.7
