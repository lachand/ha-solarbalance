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
    CONF_AUTOTUNE_ENABLED,
    CONF_BACKUP_RESERVE_SOC_PCT,
    CONF_BASELINE_WINDOW_END_H,
    CONF_BASELINE_WINDOW_START_H,
    CONF_DRY_RUN,
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
    CONF_OVERLOAD_PROTECTION_ENABLED,
    CONF_PHASES,
    CONF_PREDICTIVE_CONTROL_ENABLED,
    CONF_PRIORITIES,
    CONF_PV_FORECAST_ENTITY,
    CONF_PV_FORECAST_TOMORROW_ENTITY,
    CONF_SOC_EQUALISER_ADAPTIVE_CADENCE,
    CONF_SOC_EQUALISER_CADENCE_TICKS,
    CONF_SOC_EQUALISER_DEADBAND_PCT,
    CONF_SOC_EQUALISER_ENABLED,
    CONF_SOC_EQUALISER_KP_W_PER_PCT,
    CONF_SOC_EQUALISER_MAX_W,
    CONF_SOC_EQUALISER_MIN_PV_W,
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
    CONF_WEATHER_MIN_LEVEL,
    CONF_WEATHER_PHENOMENA,
    CONF_WEATHER_WARNING_ENTITY,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_KP,
    CONF_ZERO_INJECTION_SETPOINT_W,
    CONF_ZI_SETTLE_MIN_DROP_W,
    CONF_ZI_SETTLE_TICKS,
    DEFAULT_AUTOTUNE_ENABLED,
    DEFAULT_BACKUP_RESERVE_SOC_PCT,
    DEFAULT_BASELINE_WINDOW_END_H,
    DEFAULT_BASELINE_WINDOW_START_H,
    DEFAULT_DRY_RUN,
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
    DEFAULT_OVERLOAD_PROTECTION_ENABLED,
    DEFAULT_PHASES,
    DEFAULT_SOC_EQUALISER_ADAPTIVE_CADENCE,
    DEFAULT_SOC_EQUALISER_CADENCE_TICKS,
    DEFAULT_SOC_EQUALISER_DEADBAND_PCT,
    DEFAULT_SOC_EQUALISER_KP_W_PER_PCT,
    DEFAULT_SOC_EQUALISER_MAX_W,
    DEFAULT_SOC_EQUALISER_MIN_PV_W,
    DEFAULT_SOC_EQUALISER_PROBE_STEP_W,
    DEFAULT_SPOT_MARKUP,
    DEFAULT_TARIFF_TYPE,
    DEFAULT_TEMPO_RED_PREP_SOC_PCT,
    DEFAULT_TICK_INTERVAL_S,
    DEFAULT_VACATION_SOC_MAX_PCT,
    DEFAULT_WEATHER_MIN_LEVEL,
    DEFAULT_ZERO_INJECTION_HYSTERESIS_W,
    DEFAULT_ZERO_INJECTION_KP,
    DEFAULT_ZI_SETTLE_MIN_DROP_W,
    DEFAULT_ZI_SETTLE_TICKS,
    DOMAIN,
)
from .core.models import StrategyKind
from .core.weather import PHENOMENA

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


def _general_fields(d: dict[str, Any]) -> dict[Any, Any]:
    """Régulation, sécurité et comportements (hors tarif/prévision)."""
    return {
        vol.Optional(
            CONF_TICK_INTERVAL_S, default=d.get(CONF_TICK_INTERVAL_S, DEFAULT_TICK_INTERVAL_S)
        ): vol.All(int, vol.Range(min=5, max=60)),
        vol.Optional(
            CONF_ZERO_INJECTION_ENABLED, default=d.get(CONF_ZERO_INJECTION_ENABLED, True)
        ): bool,
        vol.Optional(
            CONF_ZERO_INJECTION_SETPOINT_W, default=d.get(CONF_ZERO_INJECTION_SETPOINT_W, 0)
        ): vol.Coerce(int),
        vol.Optional(
            CONF_ZERO_INJECTION_HYSTERESIS_W,
            default=d.get(CONF_ZERO_INJECTION_HYSTERESIS_W, DEFAULT_ZERO_INJECTION_HYSTERESIS_W),
        ): vol.All(int, vol.Range(min=0)),
        vol.Optional(CONF_MAX_RAMP_W, default=d.get(CONF_MAX_RAMP_W, DEFAULT_MAX_RAMP_W)): vol.All(
            vol.Coerce(int), vol.Range(min=0)
        ),
        vol.Optional(
            CONF_GRID_FILTER_SAMPLES,
            default=d.get(CONF_GRID_FILTER_SAMPLES, DEFAULT_GRID_FILTER_SAMPLES),
        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(
            CONF_ZI_SETTLE_TICKS, default=d.get(CONF_ZI_SETTLE_TICKS, DEFAULT_ZI_SETTLE_TICKS)
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional(
            CONF_ZI_SETTLE_MIN_DROP_W,
            default=d.get(CONF_ZI_SETTLE_MIN_DROP_W, DEFAULT_ZI_SETTLE_MIN_DROP_W),
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_ZERO_INJECTION_KP, default=d.get(CONF_ZERO_INJECTION_KP, DEFAULT_ZERO_INJECTION_KP)
        ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=2.0)),
        vol.Optional(CONF_PHASES, default=d.get(CONF_PHASES, DEFAULT_PHASES)): vol.In([1, 3]),
        vol.Optional(
            CONF_SUBSCRIBED_POWER_KVA, default=d.get(CONF_SUBSCRIBED_POWER_KVA, 6)
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
            CONF_WEATHER_WARNING_ENTITY, default=d.get(CONF_WEATHER_WARNING_ENTITY, "")
        ): _entity("binary_sensor", "sensor"),
        vol.Optional(
            CONF_WEATHER_PHENOMENA, default=d.get(CONF_WEATHER_PHENOMENA, list(PHENOMENA))
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(PHENOMENA),
                multiple=True,
                translation_key="weather_phenomena",
            )
        ),
        vol.Optional(
            CONF_WEATHER_MIN_LEVEL,
            default=d.get(CONF_WEATHER_MIN_LEVEL, DEFAULT_WEATHER_MIN_LEVEL),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["jaune", "orange", "rouge"],
                translation_key="weather_min_level",
            )
        ),
        vol.Optional(
            CONF_ACTIVE_CONTROL_ENABLED, default=d.get(CONF_ACTIVE_CONTROL_ENABLED, False)
        ): bool,
        vol.Optional(
            CONF_LOAD_CONTROL_ENABLED, default=d.get(CONF_LOAD_CONTROL_ENABLED, False)
        ): bool,
        vol.Optional(CONF_DRY_RUN, default=d.get(CONF_DRY_RUN, DEFAULT_DRY_RUN)): bool,
        vol.Optional(
            CONF_EVENING_SHED_ENABLED, default=d.get(CONF_EVENING_SHED_ENABLED, False)
        ): bool,
        vol.Optional(
            CONF_OVERLOAD_PROTECTION_ENABLED,
            default=d.get(CONF_OVERLOAD_PROTECTION_ENABLED, DEFAULT_OVERLOAD_PROTECTION_ENABLED),
        ): bool,
        vol.Optional(
            CONF_PREDICTIVE_CONTROL_ENABLED, default=d.get(CONF_PREDICTIVE_CONTROL_ENABLED, False)
        ): bool,
        vol.Optional(
            CONF_NOTIFICATIONS_ENABLED, default=d.get(CONF_NOTIFICATIONS_ENABLED, True)
        ): bool,
        vol.Optional(
            CONF_TEMPO_RED_PREP_ENABLED, default=d.get(CONF_TEMPO_RED_PREP_ENABLED, False)
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
            CONF_SOC_EQUALISER_ENABLED, default=d.get(CONF_SOC_EQUALISER_ENABLED, False)
        ): bool,
        vol.Optional(
            CONF_SOC_EQUALISER_MAX_W,
            CONF_SOC_EQUALISER_MIN_PV_W,
            default=d.get(CONF_SOC_EQUALISER_MAX_W, DEFAULT_SOC_EQUALISER_MAX_W),
        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(
            CONF_SOC_EQUALISER_KP_W_PER_PCT,
            default=d.get(CONF_SOC_EQUALISER_KP_W_PER_PCT, DEFAULT_SOC_EQUALISER_KP_W_PER_PCT),
        ): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(
            CONF_SOC_EQUALISER_DEADBAND_PCT,
            default=d.get(CONF_SOC_EQUALISER_DEADBAND_PCT, DEFAULT_SOC_EQUALISER_DEADBAND_PCT),
        ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(
            CONF_SOC_EQUALISER_PROBE_STEP_W,
            default=d.get(CONF_SOC_EQUALISER_PROBE_STEP_W, DEFAULT_SOC_EQUALISER_PROBE_STEP_W),
        ): vol.All(vol.Coerce(float), vol.Range(min=1)),
        vol.Optional(
            CONF_SOC_EQUALISER_MIN_PV_W,
            default=d.get(CONF_SOC_EQUALISER_MIN_PV_W, DEFAULT_SOC_EQUALISER_MIN_PV_W),
        ): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(
            CONF_SOC_EQUALISER_CADENCE_TICKS,
            default=d.get(CONF_SOC_EQUALISER_CADENCE_TICKS, DEFAULT_SOC_EQUALISER_CADENCE_TICKS),
        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(
            CONF_SOC_EQUALISER_ADAPTIVE_CADENCE,
            default=d.get(
                CONF_SOC_EQUALISER_ADAPTIVE_CADENCE, DEFAULT_SOC_EQUALISER_ADAPTIVE_CADENCE
            ),
        ): bool,
        vol.Optional(
            CONF_AUTOTUNE_ENABLED,
            default=d.get(CONF_AUTOTUNE_ENABLED, DEFAULT_AUTOTUNE_ENABLED),
        ): bool,
    }


def _forecast_fields(d: dict[str, Any]) -> dict[Any, Any]:
    """Prévision PV (entités Solcast / Forecast.Solar + marge de sécurité)."""
    return {
        vol.Optional(CONF_PV_FORECAST_ENTITY, default=d.get(CONF_PV_FORECAST_ENTITY, "")): _entity(
            "sensor"
        ),
        vol.Optional(
            CONF_PV_FORECAST_TOMORROW_ENTITY, default=d.get(CONF_PV_FORECAST_TOMORROW_ENTITY, "")
        ): _entity("sensor"),
        vol.Optional(
            CONF_FORECAST_SAFETY_FACTOR,
            default=d.get(CONF_FORECAST_SAFETY_FACTOR, DEFAULT_FORECAST_SAFETY_FACTOR),
        ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
    }


def _tariff_fields(d: dict[str, Any]) -> dict[Any, Any]:
    """Tarif (alternative UI au bloc YAML tariff:) et prix d'import/export."""
    return {
        vol.Optional(
            CONF_IMPORT_PRICE, default=d.get(CONF_IMPORT_PRICE, DEFAULT_IMPORT_PRICE)
        ): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(
            CONF_EXPORT_PRICE, default=d.get(CONF_EXPORT_PRICE, DEFAULT_EXPORT_PRICE)
        ): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(
            CONF_TARIFF_TYPE, default=d.get(CONF_TARIFF_TYPE, DEFAULT_TARIFF_TYPE)
        ): vol.In(["flat", "hc_hp", "tempo", "spot"]),
        vol.Optional(CONF_HC_START, default=d.get(CONF_HC_START, DEFAULT_HC_START)): str,
        vol.Optional(CONF_HC_END, default=d.get(CONF_HC_END, DEFAULT_HC_END)): str,
        vol.Optional(CONF_HC_PRICE, default=d.get(CONF_HC_PRICE, DEFAULT_HC_PRICE)): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional(CONF_HP_PRICE, default=d.get(CONF_HP_PRICE, DEFAULT_HP_PRICE)): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional(CONF_TEMPO_COLOR_ENTITY, default=d.get(CONF_TEMPO_COLOR_ENTITY, "")): _entity(
            "sensor"
        ),
        vol.Optional(
            CONF_TEMPO_COLOR_TOMORROW_ENTITY, default=d.get(CONF_TEMPO_COLOR_TOMORROW_ENTITY, "")
        ): _entity("sensor"),
        vol.Optional(CONF_SPOT_PRICE_ENTITY, default=d.get(CONF_SPOT_PRICE_ENTITY, "")): _entity(
            "sensor"
        ),
        vol.Optional(
            CONF_SPOT_MARKUP, default=d.get(CONF_SPOT_MARKUP, DEFAULT_SPOT_MARKUP)
        ): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }


def _main_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Full single-form schema (initial setup); options are split into sections."""
    d = defaults or {}
    return vol.Schema({**_general_fields(d), **_forecast_fields(d), **_tariff_fields(d)})


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
        """Return the options flow handler for this entry."""
        return SolarBalanceOptionsFlow(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: Any
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Device/equipment types addable from the UI via 'Add'."""
        return {
            "battery": BatterySubentryFlowHandler,
            "mppt": MpptSubentryFlowHandler,
            "battery_mppt": BatteryMpptSubentryFlowHandler,
            "load": LoadSubentryFlowHandler,
            "meter": MeterSubentryFlowHandler,
        }


class SolarBalanceOptionsFlow(OptionsFlow):
    """Edit global parameters after setup, grouped into sections via a menu."""

    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu (sections)."""
        return self.async_show_menu(step_id="init", menu_options=["general", "forecast", "tariff"])

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the regulation & behaviour section."""
        return await self._section("general", _general_fields, user_input)

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the PV-forecast section."""
        return await self._section("forecast", _forecast_fields, user_input)

    async def async_step_tariff(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the tariff & prices section."""
        return await self._section("tariff", _tariff_fields, user_input)

    async def _section(
        self,
        step_id: str,
        fields_fn: Any,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Show one section's form and merge it into the existing options on submit."""
        current = dict(self._entry.options or self._entry.data)
        if user_input is not None:
            merged = {**current, **user_input}
            for key in _OPTIONAL_ENTITY_KEYS:
                if merged.get(key) == "":
                    merged[key] = None
            return self.async_create_entry(title="", data=merged)
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema(fields_fn(current)))


# ---------------------------------------------------------------------------
# Device/load configuration via the UI (config subentries)
# ---------------------------------------------------------------------------


class _OptionalNumberSelector(selector.NumberSelector):
    """Number selector that accepts an empty value instead of raising.

    Mirrors :class:`_OptionalEntitySelector`: an empty optional number field
    ("expected float for ...") must not block saving the form. Empty becomes
    "no value"; the input assemblers drop it so the builder applies the field's
    default, and a missing *required* number still fails the builder cleanly.
    """

    def __call__(self, data: Any) -> Any:
        if data in (None, ""):
            return ""
        return super().__call__(data)


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
    return _OptionalNumberSelector(cfg)


class _OptionalEntitySelector(selector.EntitySelector):
    """Entity selector that accepts an empty value instead of raising.

    A bare ``EntitySelector`` rejects ``""``/``None`` ("Entity is neither a
    valid entity ID nor a valid UUID"), which blocks saving a form that simply
    leaves an *optional* entity blank. This treats empty as "no value" so the
    form validates; required fields stay enforced because the input assemblers
    drop empty values, so a missing required entity still fails the builder
    with a friendly error rather than a hard selector crash.
    """

    def __call__(self, data: Any) -> Any:
        if data in (None, "", []):
            return ""
        return super().__call__(data)


def _entity(*domains):
    return _OptionalEntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


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
            vol.Required("max_discharge_power_w", default=d.get("max_discharge_power_w")): _num(
                0, step=50, unit="W"
            ),
            vol.Required("soc_entity", default=d.get("soc_entity")): _entity("sensor"),
            vol.Optional("power_entity", default=d.get("power_entity", "")): _entity("sensor"),
            vol.Optional("charge_power_entity", default=d.get("charge_power_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional(
                "discharge_power_entity", default=d.get("discharge_power_entity", "")
            ): _entity("sensor"),
            vol.Optional("temperature_entity", default=d.get("temperature_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional("cycles_entity", default=d.get("cycles_entity", "")): _entity("sensor"),
            vol.Optional("soc_min_pct", default=d.get("soc_min_pct", 10)): _num(0, 100, 1, "%"),
            vol.Optional("soc_max_pct", default=d.get("soc_max_pct", 95)): _num(0, 100, 1, "%"),
            vol.Optional("usable_capacity_kwh", default=d.get("usable_capacity_kwh", "")): _num(
                0, step=0.1, unit="kWh"
            ),
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
            vol.Optional("ac_charge_limit_w", default=d.get("ac_charge_limit_w", "")): _num(
                0, step=50, unit="W"
            ),
        }
    )


# Keys that hold a battery-role value (the rest, like name, are device-level).
_BATTERY_ROLE_KEYS = (
    "capacity_kwh",
    "max_charge_power_w",
    "max_discharge_power_w",
    "soc_entity",
    "power_entity",
    "charge_power_entity",
    "discharge_power_entity",
    "temperature_entity",
    "cycles_entity",
    "soc_min_pct",
    "soc_max_pct",
    "usable_capacity_kwh",
    "chemistry",
    "power_sign_convention",
    "controllable",
    "active_control_enabled",
    "charge_power_setpoint_entity",
    "discharge_power_setpoint_entity",
    "mode_setpoint_entity",
    "reserve_soc_setpoint_entity",
    "ac_charge_limit_w",
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


def _battery_flat(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten a stored battery device dict back to the form's flat field shape."""
    flat = {k: v for k, v in data.items() if k != "roles"}
    flat.update(data.get("roles", {}).get("battery", {}))
    return flat


class _EquipmentSubentryFlow(ConfigSubentryFlow):
    """Shared add + reconfigure flow for an equipment subentry.

    Subclasses define how UI input maps to the stored dict (``_to_data``), how
    to validate it (``_build``), the form schema (``_schema``), and how a stored
    dict is flattened back to form defaults (``_prefill``). Both ``user`` (add)
    and ``reconfigure`` (edit) steps reuse the same validation; reconfigure
    updates the existing subentry in place instead of creating a new one.
    """

    _error_key = "invalid_device"

    def _to_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _build(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        raise NotImplementedError

    def _prefill(self, data: dict[str, Any]) -> dict[str, Any]:
        return dict(data)

    def _error_key_for(self, exc: Exception) -> str:
        """Map a build/validation exception to a form error key (overridable)."""
        return self._error_key

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._show("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._show("reconfigure", user_input)

    async def _show(self, step_id: str, user_input: dict[str, Any] | None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"reason": ""}
        defaults: dict[str, Any] = user_input or {}
        if user_input is not None:
            try:
                data = self._to_data(user_input)
                self._build(data)
            except (vol.Invalid, ValueError, KeyError) as exc:
                _LOGGER.warning("Invalid %s subentry: %s", self._subentry_type, exc)
                errors["base"] = self._error_key_for(exc)
                placeholders["reason"] = str(exc)
            else:
                title = str(user_input["name"])
                if step_id == "reconfigure":
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        title=title,
                        data=data,
                    )
                return self.async_create_entry(title=title, data=data)
        elif step_id == "reconfigure":
            defaults = self._prefill(self._get_reconfigure_subentry().data)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._schema(defaults),
            errors=errors,
            description_placeholders=placeholders,
        )


class _DeviceSubentryFlow(_EquipmentSubentryFlow):
    """Equipment flow whose stored dict is a device (battery / mppt / both)."""

    _error_key = "invalid_device"

    def _build(self, data: dict[str, Any]) -> None:
        from .yaml_loader import build_device_from_dict

        build_device_from_dict(data)


def _battery_error_key(exc: Exception, default: str) -> str:
    """Map a battery build error to a specific form error key for clearer UX."""
    msg = str(exc)
    if "either power_entity or both" in msg:
        return "battery_no_power"
    if "active_control_enabled requires at least one" in msg:
        return "battery_active_no_setpoint"
    if "active_control_enabled requires controllable" in msg:
        return "battery_active_needs_controllable"
    return default


class BatterySubentryFlowHandler(_DeviceSubentryFlow):
    """Add or reconfigure a battery device from the UI."""

    def _to_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return _battery_input_to_device(user_input)

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return _battery_subentry_schema(defaults)

    def _prefill(self, data: dict[str, Any]) -> dict[str, Any]:
        return _battery_flat(data)

    def _error_key_for(self, exc: Exception) -> str:
        return _battery_error_key(exc, self._error_key)


def _parse_steps(text: str) -> list[dict[str, int]]:
    """Parse a 'level:power, level:power' string into stepped-load steps."""
    steps: list[dict[str, int]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        level_s, sep, power_s = part.partition(":")
        if not sep:
            raise ValueError(f"step {part!r} must be 'level:power_w'")
        steps.append({"level": int(level_s.strip()), "power_w": int(power_s.strip())})
    return steps


_LOAD_FLAT_KEYS = (
    "name",
    "control_type",
    "priority",
    "interruptible",
    "switch_entity",
    "actual_power_entity",
    "nominal_power_w",
    "level_entity",
    "power_set_entity",
    "min_power_w",
    "max_power_w",
    "fast_charge",
    "min_charge_w",
    "assist_floor_soc_pct",
    "pause_when_inefficient",
    "min_on_duration_s",
    "min_off_duration_s",
)


def _load_subentry_schema(d: dict[str, Any]) -> vol.Schema:
    from .core.models import LoadControlType

    steps_default = (
        ", ".join(f"{s['level']}:{s['power_w']}" for s in d.get("steps", []))
        if d.get("steps")
        else d.get("steps_text", "")
    )
    dl = d.get("deadline_constraint") or {}
    tw = d.get("time_window") or {}
    return vol.Schema(
        {
            vol.Required("name", default=d.get("name", "")): selector.TextSelector(),
            vol.Required(
                "control_type", default=d.get("control_type", LoadControlType.ON_OFF.value)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[c.value for c in LoadControlType], translation_key="load_control_type"
                )
            ),
            vol.Optional("priority", default=d.get("priority", 5)): _num(1, 99, 1),
            vol.Optional(
                "interruptible", default=d.get("interruptible", True)
            ): selector.BooleanSelector(),
            vol.Optional("switch_entity", default=d.get("switch_entity", "")): _entity(
                "switch", "input_boolean"
            ),
            vol.Optional("actual_power_entity", default=d.get("actual_power_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional("nominal_power_w", default=d.get("nominal_power_w", "")): _num(
                0, step=50, unit="W"
            ),
            vol.Optional("level_entity", default=d.get("level_entity", "")): _entity(
                "number", "input_number", "select", "input_select"
            ),
            vol.Optional("steps", default=steps_default): selector.TextSelector(),
            vol.Optional("power_set_entity", default=d.get("power_set_entity", "")): _entity(
                "number", "input_number"
            ),
            vol.Optional("min_power_w", default=d.get("min_power_w", "")): _num(
                0, step=50, unit="W"
            ),
            vol.Optional("max_power_w", default=d.get("max_power_w", "")): _num(
                0, step=50, unit="W"
            ),
            vol.Optional("min_on_duration_s", default=d.get("min_on_duration_s", 0)): _num(
                0, step=30, unit="s"
            ),
            vol.Optional("min_off_duration_s", default=d.get("min_off_duration_s", 0)): _num(
                0, step=30, unit="s"
            ),
            vol.Optional(
                "fast_charge", default=d.get("fast_charge", False)
            ): selector.BooleanSelector(),
            vol.Optional("min_charge_w", default=d.get("min_charge_w", "")): _num(
                0, step=50, unit="W"
            ),
            vol.Optional("assist_floor_soc_pct", default=d.get("assist_floor_soc_pct", "")): _num(
                0, 100, 1, "%"
            ),
            vol.Optional(
                "pause_when_inefficient", default=d.get("pause_when_inefficient", True)
            ): selector.BooleanSelector(),
            vol.Optional("deadline_kwh", default=dl.get("kwh_required", "")): _num(
                0, step=0.5, unit="kWh"
            ),
            vol.Optional(
                "deadline_before", default=dl.get("before_time", "")
            ): selector.TextSelector(),
            vol.Optional("window_start", default=tw.get("start", "")): selector.TextSelector(),
            vol.Optional("window_end", default=tw.get("end", "")): selector.TextSelector(),
        }
    )


def _load_input_to_dict(user_input: dict[str, Any]) -> dict[str, Any]:
    """Assemble UI input into a load dict (shape consumed by _build_load)."""
    load: dict[str, Any] = {}
    for key in _LOAD_FLAT_KEYS:
        val = user_input.get(key)
        if val in (None, ""):
            continue
        load[key] = val
    steps_text = (user_input.get("steps") or "").strip()
    if steps_text:
        load["steps"] = _parse_steps(steps_text)
    req = user_input.get("deadline_kwh")
    before = (user_input.get("deadline_before") or "").strip()
    if req not in (None, "") and before:
        load["deadline_constraint"] = {"kwh_required": req, "before_time": before}
    w_start = (user_input.get("window_start") or "").strip()
    w_end = (user_input.get("window_end") or "").strip()
    if w_start and w_end:
        load["time_window"] = {"start": w_start, "end": w_end}
    return load


class LoadSubentryFlowHandler(_EquipmentSubentryFlow):
    """Add or reconfigure a controllable load from the UI."""

    _error_key = "invalid_load"

    def _to_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return _load_input_to_dict(user_input)

    def _build(self, data: dict[str, Any]) -> None:
        from .yaml_loader import build_load_from_dict

        build_load_from_dict(data)

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return _load_subentry_schema(defaults)


def _mppt_subentry_schema(d: dict[str, Any]) -> vol.Schema:
    roles = d.get("roles", {})
    m = roles.get("mppt", d)  # accept flat or device-shaped defaults
    return vol.Schema(
        {
            vol.Required("name", default=d.get("name", "")): selector.TextSelector(),
            vol.Required("peak_power_w", default=m.get("peak_power_w")): _num(0, step=50, unit="W"),
            vol.Required("power_entity", default=m.get("power_entity")): _entity("sensor"),
            vol.Optional("daily_energy_entity", default=m.get("daily_energy_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional(
                "active_control_enabled", default=m.get("active_control_enabled", False)
            ): selector.BooleanSelector(),
            vol.Optional(
                "power_limit_setpoint_entity", default=m.get("power_limit_setpoint_entity", "")
            ): _entity("number", "input_number"),
        }
    )


_MPPT_ROLE_KEYS = (
    "peak_power_w",
    "power_entity",
    "daily_energy_entity",
    "active_control_enabled",
    "power_limit_setpoint_entity",
)


def _mppt_input_to_device(user_input: dict[str, Any]) -> dict[str, Any]:
    mppt: dict[str, Any] = {}
    for key in _MPPT_ROLE_KEYS:
        val = user_input.get(key)
        if val in (None, ""):
            continue
        mppt[key] = val
    return {"name": user_input["name"], "roles": {"mppt": mppt}}


class MpptSubentryFlowHandler(_DeviceSubentryFlow):
    """Add or reconfigure a PV inverter / MPPT from the UI."""

    def _to_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return _mppt_input_to_device(user_input)

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return _mppt_subentry_schema(defaults)


def _meter_subentry_schema(d: dict[str, Any]) -> vol.Schema:
    from .core.models import MeterKind

    return vol.Schema(
        {
            vol.Required("name", default=d.get("name", "")): selector.TextSelector(),
            vol.Required(
                "kind", default=d.get("kind", MeterKind.PDL.value)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[k.value for k in MeterKind], translation_key="meter_kind"
                )
            ),
            vol.Required("power_entity", default=d.get("power_entity")): _entity("sensor"),
            vol.Optional("phases", default=str(d.get("phases", 1))): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["1", "3"])
            ),
            vol.Optional(
                "per_phase_zi", default=d.get("per_phase_zi", False)
            ): selector.BooleanSelector(),
            vol.Optional("power_l1_entity", default=d.get("power_l1_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional("power_l2_entity", default=d.get("power_l2_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional("power_l3_entity", default=d.get("power_l3_entity", "")): _entity(
                "sensor"
            ),
            vol.Optional(
                "daily_import_energy_entity", default=d.get("daily_import_energy_entity", "")
            ): _entity("sensor"),
            vol.Optional(
                "daily_export_energy_entity", default=d.get("daily_export_energy_entity", "")
            ): _entity("sensor"),
        }
    )


_METER_KEYS = (
    "name",
    "kind",
    "power_entity",
    "per_phase_zi",
    "power_l1_entity",
    "power_l2_entity",
    "power_l3_entity",
    "daily_import_energy_entity",
    "daily_export_energy_entity",
)


def _meter_input_to_dict(user_input: dict[str, Any]) -> dict[str, Any]:
    meter: dict[str, Any] = {}
    for key in _METER_KEYS:
        val = user_input.get(key)
        if val in (None, ""):
            continue
        meter[key] = val
    # phases is a string from the select; coerce to int for the schema.
    if user_input.get("phases") not in (None, ""):
        meter["phases"] = int(user_input["phases"])
    return meter


class MeterSubentryFlowHandler(_EquipmentSubentryFlow):
    """Add or reconfigure a power meter (PDL/PV/consumption) from the UI."""

    _error_key = "invalid_meter"

    def _to_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return _meter_input_to_dict(user_input)

    def _build(self, data: dict[str, Any]) -> None:
        from .yaml_loader import build_meter_from_dict

        build_meter_from_dict(data)

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return _meter_subentry_schema(defaults)

    def _prefill(self, data: dict[str, Any]) -> dict[str, Any]:
        # ``phases`` is stored as int but the select options are strings.
        prefill = dict(data)
        if "phases" in prefill:
            prefill["phases"] = str(prefill["phases"])
        return prefill


def _battery_mppt_subentry_schema(d: dict[str, Any]) -> vol.Schema:
    """Battery fields + (prefixed) MPPT fields for a combined device."""
    m = d.get("roles", {}).get("mppt", {})
    fields = dict(_battery_subentry_schema(d).schema)
    fields.update(
        {
            vol.Required("mppt_peak_power_w", default=m.get("peak_power_w")): _num(
                0, step=50, unit="W"
            ),
            vol.Required("mppt_power_entity", default=m.get("power_entity")): _entity("sensor"),
            vol.Optional(
                "mppt_daily_energy_entity", default=m.get("daily_energy_entity", "")
            ): _entity("sensor"),
            vol.Optional(
                "mppt_active_control_enabled", default=m.get("active_control_enabled", False)
            ): selector.BooleanSelector(),
            vol.Optional(
                "mppt_power_limit_setpoint_entity",
                default=m.get("power_limit_setpoint_entity", ""),
            ): _entity("number", "input_number"),
        }
    )
    return vol.Schema(fields)


_MPPT_PREFIXED = {
    "mppt_peak_power_w": "peak_power_w",
    "mppt_power_entity": "power_entity",
    "mppt_daily_energy_entity": "daily_energy_entity",
    "mppt_active_control_enabled": "active_control_enabled",
    "mppt_power_limit_setpoint_entity": "power_limit_setpoint_entity",
}


def _battery_mppt_input_to_device(user_input: dict[str, Any]) -> dict[str, Any]:
    device = _battery_input_to_device(user_input)
    mppt: dict[str, Any] = {}
    for src, dst in _MPPT_PREFIXED.items():
        val = user_input.get(src)
        if val in (None, ""):
            continue
        mppt[dst] = val
    device["roles"]["mppt"] = mppt
    return device


class BatteryMpptSubentryFlowHandler(_DeviceSubentryFlow):
    """Add or reconfigure a device that is both a battery and a PV inverter."""

    def _to_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return _battery_mppt_input_to_device(user_input)

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return _battery_mppt_subentry_schema(defaults)

    def _prefill(self, data: dict[str, Any]) -> dict[str, Any]:
        # Flatten the battery role to top-level fields, keep roles.mppt for the
        # prefixed MPPT fields the schema reads from ``roles.mppt``.
        prefill = _battery_flat(data)
        prefill["roles"] = {"mppt": data.get("roles", {}).get("mppt", {})}
        return prefill

    def _error_key_for(self, exc: Exception) -> str:
        return _battery_error_key(exc, self._error_key)
