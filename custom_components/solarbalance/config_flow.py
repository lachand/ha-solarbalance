"""Config flow for SolarBalance."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_PV_FORECAST_ENTITY,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TICK_INTERVAL_S,
    CONF_WEATHER_WARNING_ENTITY,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DEFAULT_PHASES,
    DEFAULT_TICK_INTERVAL_S,
    DEFAULT_ZERO_INJECTION_HYSTERESIS_W,
    DOMAIN,
)
from .core.models import StrategyKind

_LOGGER = logging.getLogger(__name__)

_DEFAULT_PRIORITIES = [
    StrategyKind.SELF_CONSUMPTION.value,
    StrategyKind.COST_MIN.value,
    StrategyKind.BACKUP.value,
    StrategyKind.LONGEVITY.value,
    StrategyKind.PEAK_SHAVING.value,
    StrategyKind.REVENUE_MAX.value,
]


def _main_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_TICK_INTERVAL_S, default=d.get(CONF_TICK_INTERVAL_S, DEFAULT_TICK_INTERVAL_S)
            ): vol.All(int, vol.Range(min=5, max=60)),
            vol.Optional(
                CONF_ZERO_INJECTION_ENABLED,
                default=d.get(CONF_ZERO_INJECTION_ENABLED, True),
            ): bool,
            vol.Optional(
                CONF_ZERO_INJECTION_SETPOINT_W,
                default=d.get(CONF_ZERO_INJECTION_SETPOINT_W, 0),
            ): vol.Coerce(int),
            vol.Optional(
                CONF_ZERO_INJECTION_HYSTERESIS_W,
                default=d.get(
                    CONF_ZERO_INJECTION_HYSTERESIS_W, DEFAULT_ZERO_INJECTION_HYSTERESIS_W
                ),
            ): vol.All(int, vol.Range(min=0)),
            vol.Optional(
                CONF_PHASES, default=d.get(CONF_PHASES, DEFAULT_PHASES)
            ): vol.In([1, 3]),
            vol.Optional(
                CONF_SUBSCRIBED_POWER_KVA,
                default=d.get(CONF_SUBSCRIBED_POWER_KVA, 6),
            ): vol.All(int, vol.Range(min=3, max=36)),
            vol.Optional(
                CONF_PV_FORECAST_ENTITY,
                default=d.get(CONF_PV_FORECAST_ENTITY, ""),
            ): str,
            vol.Optional(
                CONF_WEATHER_WARNING_ENTITY,
                default=d.get(CONF_WEATHER_WARNING_ENTITY, ""),
            ): str,
        }
    )


class SolarBalanceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user-driven setup of SolarBalance."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Initial step — global parameters.

        Device declarations live in YAML (denser, versionable).
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Normalise empty strings to None for optional entity selectors.
            for key in (CONF_PV_FORECAST_ENTITY, CONF_WEATHER_WARNING_ENTITY):
                if user_input.get(key) == "":
                    user_input[key] = None
            user_input.setdefault(CONF_PRIORITIES, _DEFAULT_PRIORITIES)
            return self.async_create_entry(title="SolarBalance", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_main_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        return SolarBalanceOptionsFlow(config_entry)


class SolarBalanceOptionsFlow(OptionsFlow):
    """Allow changing global parameters after initial setup."""

    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            for key in (CONF_PV_FORECAST_ENTITY, CONF_WEATHER_WARNING_ENTITY):
                if user_input.get(key) == "":
                    user_input[key] = None
            return self.async_create_entry(title="", data=user_input)

        current = dict(self._entry.options or self._entry.data)
        return self.async_show_form(
            step_id="init",
            data_schema=_main_schema(current),
        )
