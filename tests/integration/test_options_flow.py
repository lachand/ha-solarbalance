"""Options flow: sectioned menu (general / forecast / tariff)."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TARIFF_TYPE,
    CONF_TICK_INTERVAL_S,
    DOMAIN,
)
from custom_components.solarbalance.core.models import StrategyKind


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    e = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10, CONF_PHASES: 1, CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
    )
    e.add_to_hass(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def test_options_menu_then_tariff_section_merges(hass, entry) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert set(result["menu_options"]) == {"general", "forecast", "tariff"}

    # Pick the tariff section.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tariff"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "tariff"

    # Submit it; the section is merged into the entry options.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TARIFF_TYPE: "hc_hp"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TARIFF_TYPE] == "hc_hp"
