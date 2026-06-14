"""Config flow for SolarBalance."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTIVE_CONTROL_ENABLED,
    CONF_BACKUP_RESERVE_SOC_PCT,
    CONF_BASELINE_WINDOW_END_H,
    CONF_BASELINE_WINDOW_START_H,
    CONF_EVENING_SHED_ENABLED,
    CONF_EVENING_SHED_MIN_POWER_W,
    CONF_EXPORT_PRICE,
    CONF_FORECAST_SAFETY_FACTOR,
    CONF_GRID_FILTER_SAMPLES,
    CONF_HC_END,
    CONF_HC_PRICE,
    CONF_HC_START,
    CONF_HP_PRICE,
    CONF_IMPORT_PRICE,
    CONF_LOAD_CONTROL_ENABLED,
    CONF_MAX_RAMP_W,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_PHASES,
    CONF_PREDICTIVE_CONTROL_ENABLED,
    CONF_PRIORITIES,
    CONF_PV_FORECAST_ENTITY,
    CONF_PV_FORECAST_TOMORROW_ENTITY,
    CONF_SOC_EQUALISER_DEADBAND_PCT,
    CONF_SOC_EQUALISER_ENABLED,
    CONF_SOC_EQUALISER_KP_W_PER_PCT,
    CONF_SOC_EQUALISER_MAX_W,
    CONF_SOC_EQUALISER_PROBE_STEP_W,
    CONF_SPOT_MARKUP,
    CONF_SPOT_PRICE_ENTITY,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TARIFF_TYPE,
    CONF_TEMPO_COLOR_ENTITY,
    CONF_TEMPO_COLOR_TOMORROW_ENTITY,
    CONF_TEMPO_RED_PREP_ENABLED,
    CONF_TEMPO_RED_PREP_SOC_PCT,
    CONF_TICK_INTERVAL_S,
    CONF_VACATION_SOC_MAX_PCT,
    CONF_WEATHER_WARNING_ENTITY,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_KP,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DEFAULT_BACKUP_RESERVE_SOC_PCT,
    DEFAULT_BASELINE_WINDOW_END_H,
    DEFAULT_BASELINE_WINDOW_START_H,
    DEFAULT_EVENING_SHED_MIN_POWER_W,
    DEFAULT_EXPORT_PRICE,
    DEFAULT_FORECAST_SAFETY_FACTOR,
    DEFAULT_GRID_FILTER_SAMPLES,
    DEFAULT_HC_END,
    DEFAULT_HC_PRICE,
    DEFAULT_HC_START,
    DEFAULT_HP_PRICE,
    DEFAULT_IMPORT_PRICE,
    DEFAULT_MAX_RAMP_W,
    DEFAULT_PHASES,
    DEFAULT_SOC_EQUALISER_DEADBAND_PCT,
    DEFAULT_SOC_EQUALISER_KP_W_PER_PCT,
    DEFAULT_SOC_EQUALISER_MAX_W,
    DEFAULT_SOC_EQUALISER_PROBE_STEP_W,
    DEFAULT_SPOT_MARKUP,
    DEFAULT_TARIFF_TYPE,
    DEFAULT_TEMPO_RED_PREP_SOC_PCT,
    DEFAULT_TICK_INTERVAL_S,
    DEFAULT_VACATION_SOC_MAX_PCT,
    DEFAULT_ZERO_INJECTION_HYSTERESIS_W,
    DEFAULT_ZERO_INJECTION_KP,
    DOMAIN,
)
from .core.models import StrategyKind

_LOGGER = logging.getLogger(__name__)

# Optional entity selectors whose empty string is normalised to None.
_OPTIONAL_ENTITY_KEYS = (
    CONF_PV_FORECAST_ENTITY,
    CONF_PV_FORECAST_TOMORROW_ENTITY,
    CONF_WEATHER_WARNING_ENTITY,
    CONF_TEMPO_COLOR_ENTITY,
    CONF_TEMPO_COLOR_TOMORROW_ENTITY,
    CONF_SPOT_PRICE_ENTITY,
)

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
                CONF_MAX_RAMP_W,
                default=d.get(CONF_MAX_RAMP_W, DEFAULT_MAX_RAMP_W),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional(
                CONF_GRID_FILTER_SAMPLES,
                default=d.get(CONF_GRID_FILTER_SAMPLES, DEFAULT_GRID_FILTER_SAMPLES),
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(
                CONF_ZERO_INJECTION_KP,
                default=d.get(CONF_ZERO_INJECTION_KP, DEFAULT_ZERO_INJECTION_KP),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
            vol.Optional(
                CONF_PHASES, default=d.get(CONF_PHASES, DEFAULT_PHASES)
            ): vol.In([1, 3]),
            vol.Optional(
                CONF_SUBSCRIBED_POWER_KVA,
                default=d.get(CONF_SUBSCRIBED_POWER_KVA, 6),
            ): vol.All(int, vol.Range(min=3, max=36)),
            vol.Optional(
                CONF_BACKUP_RESERVE_SOC_PCT,
                default=d.get(CONF_BACKUP_RESERVE_SOC_PCT, DEFAULT_BACKUP_RESERVE_SOC_PCT),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_BASELINE_WINDOW_START_H,
                default=d.get(CONF_BASELINE_WINDOW_START_H, DEFAULT_BASELINE_WINDOW_START_H),
            ): vol.All(int, vol.Range(min=0, max=23)),
            vol.Optional(
                CONF_BASELINE_WINDOW_END_H,
                default=d.get(CONF_BASELINE_WINDOW_END_H, DEFAULT_BASELINE_WINDOW_END_H),
            ): vol.All(int, vol.Range(min=0, max=23)),
            vol.Optional(
                CONF_PV_FORECAST_ENTITY,
                default=d.get(CONF_PV_FORECAST_ENTITY, ""),
            ): str,
            vol.Optional(
                CONF_PV_FORECAST_TOMORROW_ENTITY,
                default=d.get(CONF_PV_FORECAST_TOMORROW_ENTITY, ""),
            ): str,
            vol.Optional(
                CONF_FORECAST_SAFETY_FACTOR,
                default=d.get(CONF_FORECAST_SAFETY_FACTOR, DEFAULT_FORECAST_SAFETY_FACTOR),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            vol.Optional(
                CONF_WEATHER_WARNING_ENTITY,
                default=d.get(CONF_WEATHER_WARNING_ENTITY, ""),
            ): str,
            vol.Optional(
                CONF_ACTIVE_CONTROL_ENABLED,
                default=d.get(CONF_ACTIVE_CONTROL_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_LOAD_CONTROL_ENABLED,
                default=d.get(CONF_LOAD_CONTROL_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_EVENING_SHED_ENABLED,
                default=d.get(CONF_EVENING_SHED_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_PREDICTIVE_CONTROL_ENABLED,
                default=d.get(CONF_PREDICTIVE_CONTROL_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_NOTIFICATIONS_ENABLED,
                default=d.get(CONF_NOTIFICATIONS_ENABLED, True),
            ): bool,
            vol.Optional(
                CONF_TEMPO_RED_PREP_ENABLED,
                default=d.get(CONF_TEMPO_RED_PREP_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_TEMPO_RED_PREP_SOC_PCT,
                default=d.get(CONF_TEMPO_RED_PREP_SOC_PCT, DEFAULT_TEMPO_RED_PREP_SOC_PCT),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_VACATION_SOC_MAX_PCT,
                default=d.get(CONF_VACATION_SOC_MAX_PCT, DEFAULT_VACATION_SOC_MAX_PCT),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_EVENING_SHED_MIN_POWER_W,
                default=d.get(CONF_EVENING_SHED_MIN_POWER_W, DEFAULT_EVENING_SHED_MIN_POWER_W),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional(
                CONF_IMPORT_PRICE,
                default=d.get(CONF_IMPORT_PRICE, DEFAULT_IMPORT_PRICE),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(
                CONF_EXPORT_PRICE,
                default=d.get(CONF_EXPORT_PRICE, DEFAULT_EXPORT_PRICE),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            # --- Tariff (UI alternative to the YAML tariff: block) ---
            vol.Optional(
                CONF_TARIFF_TYPE,
                default=d.get(CONF_TARIFF_TYPE, DEFAULT_TARIFF_TYPE),
            ): vol.In(["flat", "hc_hp", "tempo", "spot"]),
            vol.Optional(CONF_HC_START, default=d.get(CONF_HC_START, DEFAULT_HC_START)): str,
            vol.Optional(CONF_HC_END, default=d.get(CONF_HC_END, DEFAULT_HC_END)): str,
            vol.Optional(
                CONF_HC_PRICE, default=d.get(CONF_HC_PRICE, DEFAULT_HC_PRICE)
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(
                CONF_HP_PRICE, default=d.get(CONF_HP_PRICE, DEFAULT_HP_PRICE)
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(
                CONF_TEMPO_COLOR_ENTITY, default=d.get(CONF_TEMPO_COLOR_ENTITY, "")
            ): str,
            vol.Optional(
                CONF_TEMPO_COLOR_TOMORROW_ENTITY,
                default=d.get(CONF_TEMPO_COLOR_TOMORROW_ENTITY, ""),
            ): str,
            vol.Optional(
                CONF_SPOT_PRICE_ENTITY, default=d.get(CONF_SPOT_PRICE_ENTITY, "")
            ): str,
            vol.Optional(
                CONF_SPOT_MARKUP, default=d.get(CONF_SPOT_MARKUP, DEFAULT_SPOT_MARKUP)
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(
                CONF_SOC_EQUALISER_ENABLED,
                default=d.get(CONF_SOC_EQUALISER_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_SOC_EQUALISER_MAX_W,
                default=d.get(CONF_SOC_EQUALISER_MAX_W, DEFAULT_SOC_EQUALISER_MAX_W),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional(
                CONF_SOC_EQUALISER_KP_W_PER_PCT,
                default=d.get(
                    CONF_SOC_EQUALISER_KP_W_PER_PCT, DEFAULT_SOC_EQUALISER_KP_W_PER_PCT
                ),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(
                CONF_SOC_EQUALISER_DEADBAND_PCT,
                default=d.get(
                    CONF_SOC_EQUALISER_DEADBAND_PCT, DEFAULT_SOC_EQUALISER_DEADBAND_PCT
                ),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_SOC_EQUALISER_PROBE_STEP_W,
                default=d.get(
                    CONF_SOC_EQUALISER_PROBE_STEP_W, DEFAULT_SOC_EQUALISER_PROBE_STEP_W
                ),
            ): vol.All(vol.Coerce(float), vol.Range(min=1)),
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
            for key in _OPTIONAL_ENTITY_KEYS:
                if user_input.get(key) == "":
                    user_input[key] = None
            user_input.setdefault(CONF_PRIORITIES, _DEFAULT_PRIORITIES)
            return self.async_create_entry(title="SolarBalance", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_main_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        return SolarBalanceOptionsFlow(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: Any
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Device/equipment types addable from the UI via 'Add'."""
        return {"battery": BatterySubentryFlowHandler}


class SolarBalanceOptionsFlow(OptionsFlow):
    """Allow changing global parameters after initial setup."""

    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            for key in _OPTIONAL_ENTITY_KEYS:
                if user_input.get(key) == "":
                    user_input[key] = None
            return self.async_create_entry(title="", data=user_input)

        current = dict(self._entry.options or self._entry.data)
        return self.async_show_form(
            step_id="init",
            data_schema=_main_schema(current),
        )


# ---------------------------------------------------------------------------
# Device/load configuration via the UI (config subentries)
# ---------------------------------------------------------------------------


def _num(min_v=None, max_v=None, step=None, unit=None):
    cfg = selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX)
    if min_v is not None:
        cfg["min"] = min_v
    if max_v is not None:
        cfg["max"] = max_v
    if step is not None:
        cfg["step"] = step
    if unit is not None:
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(cfg)


def _entity(*domains):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


def _battery_subentry_schema(d: dict[str, Any]) -> vol.Schema:
    from .core.models import Chemistry, PowerSignConvention

    return vol.Schema(
        {
            vol.Required("name", default=d.get("name", "")): selector.TextSelector(),
            vol.Required("capacity_kwh", default=d.get("capacity_kwh")): _num(
                0.1, step=0.1, unit="kWh"
            ),
            vol.Required("max_charge_power_w", default=d.get("max_charge_power_w")): _num(
                0, step=50, unit="W"
            ),
            vol.Required(
                "max_discharge_power_w", default=d.get("max_discharge_power_w")
            ): _num(0, step=50, unit="W"),
            vol.Required("soc_entity", default=d.get("soc_entity")): _entity("sensor"),
            vol.Optional("power_entity", default=d.get("power_entity", "")): _entity("sensor"),
            vol.Optional(
                "temperature_entity", default=d.get("temperature_entity", "")
            ): _entity("sensor"),
            vol.Optional("cycles_entity", default=d.get("cycles_entity", "")): _entity("sensor"),
            vol.Optional("soc_min_pct", default=d.get("soc_min_pct", 10)): _num(0, 100, 1, "%"),
            vol.Optional("soc_max_pct", default=d.get("soc_max_pct", 95)): _num(0, 100, 1, "%"),
            vol.Optional(
                "usable_capacity_kwh", default=d.get("usable_capacity_kwh", "")
            ): _num(0, step=0.1, unit="kWh"),
            vol.Optional(
                "chemistry", default=d.get("chemistry", Chemistry.LIFEPO4.value)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[c.value for c in Chemistry], translation_key="chemistry"
                )
            ),
            vol.Optional(
                "power_sign_convention",
                default=d.get("power_sign_convention", PowerSignConvention.CHARGE_POSITIVE.value),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[c.value for c in PowerSignConvention],
                    translation_key="power_sign_convention",
                )
            ),
            vol.Optional(
                "controllable", default=d.get("controllable", True)
            ): selector.BooleanSelector(),
            vol.Optional(
                "active_control_enabled", default=d.get("active_control_enabled", False)
            ): selector.BooleanSelector(),
            vol.Optional(
                "charge_power_setpoint_entity",
                default=d.get("charge_power_setpoint_entity", ""),
            ): _entity("number", "input_number"),
            vol.Optional(
                "discharge_power_setpoint_entity",
                default=d.get("discharge_power_setpoint_entity", ""),
            ): _entity("number", "input_number"),
            vol.Optional(
                "mode_setpoint_entity", default=d.get("mode_setpoint_entity", "")
            ): _entity("select", "input_select"),
            vol.Optional(
                "reserve_soc_setpoint_entity",
                default=d.get("reserve_soc_setpoint_entity", ""),
            ): _entity("number", "input_number"),
            vol.Optional(
                "ac_charge_limit_w", default=d.get("ac_charge_limit_w", "")
            ): _num(0, step=50, unit="W"),
        }
    )


# Keys that hold a battery-role value (the rest, like name, are device-level).
_BATTERY_ROLE_KEYS = (
    "capacity_kwh", "max_charge_power_w", "max_discharge_power_w", "soc_entity",
    "power_entity", "temperature_entity", "cycles_entity", "soc_min_pct", "soc_max_pct",
    "usable_capacity_kwh", "chemistry", "power_sign_convention", "controllable",
    "active_control_enabled", "charge_power_setpoint_entity", "discharge_power_setpoint_entity",
    "mode_setpoint_entity", "reserve_soc_setpoint_entity", "ac_charge_limit_w",
)


def _battery_input_to_device(user_input: dict[str, Any]) -> dict[str, Any]:
    """Assemble UI input into a device dict (shape consumed by _build_device)."""
    battery: dict[str, Any] = {}
    for key in _BATTERY_ROLE_KEYS:
        val = user_input.get(key)
        if val in (None, ""):
            continue
        battery[key] = val
    return {"name": user_input["name"], "roles": {"battery": battery}}


class BatterySubentryFlowHandler(ConfigSubentryFlow):
    """Add or reconfigure a battery device from the UI."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Collect the battery fields, validate, and create the subentry."""
        from .yaml_loader import build_device_from_dict

        errors: dict[str, str] = {}
        if user_input is not None:
            device = _battery_input_to_device(user_input)
            try:
                build_device_from_dict(device)
            except (vol.Invalid, ValueError, KeyError) as exc:
                _LOGGER.warning("Invalid battery subentry: %s", exc)
                errors["base"] = "invalid_device"
            else:
                return self.async_create_entry(title=str(user_input["name"]), data=device)
        return self.async_show_form(
            step_id="user", data_schema=_battery_subentry_schema(user_input or {}), errors=errors
        )
