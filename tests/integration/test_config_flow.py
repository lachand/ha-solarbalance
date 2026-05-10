"""Integration tests for the SolarBalance config flow."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PV_FORECAST_ENTITY,
    CONF_SUBSCRIBED_POWER_KVA,
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
async def test_config_flow_aborts_when_already_configured(hass: HomeAssistant) -> None:
    """A second config flow attempt should abort with single_instance_allowed."""
    # First setup — succeeds
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_VALID_USER_INPUT)

    # Second attempt — must abort
    result2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "single_instance_allowed"
