"""Integration tests for the SolarBalance config flow."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PV_FORECAST_ENTITY,
    CONF_SOC_EQUALISER_DEADBAND_PCT,
    CONF_SOC_EQUALISER_ENABLED,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TARIFF_TYPE,
    CONF_TEMPO_COLOR_ENTITY,
    CONF_TICK_INTERVAL_S,
    CONF_WEATHER_WARNING_ENTITY,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DOMAIN,
)

_VALID_USER_INPUT: dict[str, Any] = {
    CONF_TICK_INTERVAL_S: 10,
    CONF_ZERO_INJECTION_ENABLED: True,
    CONF_ZERO_INJECTION_SETPOINT_W: 0,
    CONF_ZERO_INJECTION_HYSTERESIS_W: 50,
    CONF_PHASES: 1,
    CONF_SUBSCRIBED_POWER_KVA: 6,
    CONF_PV_FORECAST_ENTITY: "",
    CONF_WEATHER_WARNING_ENTITY: "",
}


@pytest.mark.asyncio
async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    """A valid user step should create a config entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_VALID_USER_INPUT
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "SolarBalance"
    data = result2["data"]
    assert data[CONF_TICK_INTERVAL_S] == 10
    # Empty strings normalised to None for optional entity fields.
    assert data.get(CONF_PV_FORECAST_ENTITY) is None
    assert data.get(CONF_WEATHER_WARNING_ENTITY) is None


@pytest.mark.asyncio
async def test_options_flow_menu_section_saves_and_merges(hass: HomeAssistant) -> None:
    """The options menu edits one section while preserving the other options."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**_VALID_USER_INPUT, CONF_SUBSCRIBED_POWER_KVA: 9},
        options={CONF_SUBSCRIBED_POWER_KVA: 9, CONF_PHASES: 1},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert "general" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "general"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_TICK_INTERVAL_S: 20}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Edited value applied; an untouched option from before is preserved.
    assert entry.options[CONF_TICK_INTERVAL_S] == 20
    assert entry.options[CONF_SUBSCRIBED_POWER_KVA] == 9


@pytest.mark.asyncio
async def test_options_tariff_wizard_routes_to_type_substep(hass: HomeAssistant) -> None:
    """Choosing a tariff type advances to that type's detail sub-step, then saves."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data=_VALID_USER_INPUT, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tariff"}
    )
    assert result["step_id"] == "tariff"

    # Pick Tempo → must show the Tempo detail step (not save yet).
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_TARIFF_TYPE: "tempo"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "tariff_tempo"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_TEMPO_COLOR_ENTITY: ""}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TARIFF_TYPE] == "tempo"
    assert entry.options.get(CONF_TEMPO_COLOR_ENTITY) is None


@pytest.mark.asyncio
async def test_options_general_wizard_shows_equaliser_substep(hass: HomeAssistant) -> None:
    """Enabling the equaliser reveals its tuning sub-step before saving."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data=_VALID_USER_INPUT, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    assert result["step_id"] == "general"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SOC_EQUALISER_ENABLED: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "general_eq"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SOC_EQUALISER_DEADBAND_PCT: 3.0}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SOC_EQUALISER_ENABLED] is True
    assert entry.options[CONF_SOC_EQUALISER_DEADBAND_PCT] == 3.0


@pytest.mark.asyncio
async def test_config_flow_aborts_when_already_configured(hass: HomeAssistant) -> None:
    """A second config flow attempt should abort with single_instance_allowed."""
    # First setup — succeeds
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_VALID_USER_INPUT)

    # Second attempt — must abort
    result2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "single_instance_allowed"
