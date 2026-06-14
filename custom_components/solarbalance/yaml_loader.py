"""Parse the YAML ``solarbalance:`` block into core dataclasses.

Device and load declarations live in ``configuration.yaml`` (not in the
Config Flow), giving power-users a dense, versionable format.

Schema overview — see SPECIFICATIONS §5 and examples/config/.
"""

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv

from .core.forecast import ForecastConfig, ForecastUnit
from .core.models import (
    BatteryRole,
    Chemistry,
    DeadlineConstraint,
    Device,
    InverterRole,
    Load,
    LoadControlType,
    LoadStep,
    Meter,
    MeterKind,
    MpptRole,
    PowerSignConvention,
    TimeWindow,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voluptuous helpers
# ---------------------------------------------------------------------------

_CHEMISTRY = vol.In([c.value for c in Chemistry])
_SIGN_CONVENTION = vol.In([c.value for c in PowerSignConvention])
_METER_KIND = vol.In([k.value for k in MeterKind])
_LOAD_CONTROL = vol.In([c.value for c in LoadControlType])
_HHMM = vol.Match(r"^([01]\d|2[0-3]):[0-5]\d$", msg="Must be HH:MM (e.g. 06:00)")
# Strict entity_id (requires a domain, e.g. number.x) for control/write entities,
# so a typo like "ef_60605_backup_reserve" is rejected at load instead of failing
# silently every tick.
_ENTITY = cv.entity_id

# ---------------------------------------------------------------------------
# Role sub-schemas
# ---------------------------------------------------------------------------

_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Required("capacity_kwh"): vol.Coerce(float),
        vol.Required("max_charge_power_w"): vol.Coerce(int),
        vol.Required("max_discharge_power_w"): vol.Coerce(int),
        vol.Required("soc_entity"): str,
        vol.Optional("power_entity"): str,
        vol.Optional("charge_power_entity"): str,
        vol.Optional("discharge_power_entity"): str,
        vol.Optional("temperature_entity"): str,
        vol.Optional("cycles_entity"): str,
        vol.Optional("soc_min_pct", default=10): vol.All(int, vol.Range(0, 100)),
        vol.Optional("soc_max_pct", default=95): vol.All(int, vol.Range(0, 100)),
        vol.Optional("chemistry", default=Chemistry.LIFEPO4.value): _CHEMISTRY,
        vol.Optional(
            "power_sign_convention", default=PowerSignConvention.CHARGE_POSITIVE.value
        ): _SIGN_CONVENTION,
        vol.Optional("usable_capacity_kwh"): vol.Coerce(float),
        vol.Optional("controllable", default=True): bool,
        vol.Optional("active_control_enabled", default=False): bool,
        vol.Optional("discharge_power_setpoint_entity"): _ENTITY,
        vol.Optional("charge_power_setpoint_entity"): _ENTITY,
        vol.Optional("mode_setpoint_entity"): _ENTITY,
        vol.Optional("reserve_soc_setpoint_entity"): _ENTITY,
        vol.Optional("ac_charge_limit_w"): vol.Coerce(int),
    }
)

_MPPT_SCHEMA = vol.Schema(
    {
        vol.Required("peak_power_w"): vol.Coerce(int),
        vol.Required("power_entity"): str,
        vol.Optional("daily_energy_entity"): str,
        vol.Optional("voltage_entity"): str,
        vol.Optional("current_entity"): str,
        vol.Optional("feeds", default=[]): [str],
        vol.Optional("active_control_enabled", default=False): bool,
        vol.Optional("power_limit_setpoint_entity"): _ENTITY,
    }
)

_INVERTER_SCHEMA = vol.Schema(
    {
        vol.Required("nominal_power_w"): vol.Coerce(int),
        vol.Required("ac_output_power_entity"): str,
        vol.Optional("ac_input_power_entity"): str,
        vol.Optional("eps_capable", default=False): bool,
        vol.Optional("eps_active_entity"): str,
        vol.Optional("eps_circuits", default=[]): [str],
        vol.Optional("temperature_entity"): str,
    }
)

_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Optional("roles"): {
            vol.Optional("battery"): _BATTERY_SCHEMA,
            vol.Optional("mppt"): _MPPT_SCHEMA,
            vol.Optional("inverter"): _INVERTER_SCHEMA,
        },
    }
)

_METER_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("kind"): _METER_KIND,
        vol.Required("power_entity"): str,
        vol.Optional("phases", default=1): vol.All(int, vol.In([1, 3])),
        vol.Optional("per_phase_zi", default=False): bool,
        vol.Optional("power_l1_entity"): str,
        vol.Optional("power_l2_entity"): str,
        vol.Optional("power_l3_entity"): str,
        vol.Optional("daily_import_energy_entity"): str,
        vol.Optional("daily_export_energy_entity"): str,
    }
)

_TIME_WINDOW_SCHEMA = vol.Schema(
    {
        vol.Required("start"): _HHMM,
        vol.Required("end"): _HHMM,
    }
)

_DEADLINE_SCHEMA = vol.Schema(
    {
        vol.Required("kwh_required"): vol.Coerce(float),
        vol.Required("before_time"): _HHMM,
    }
)

_STEP_SCHEMA = vol.Schema(
    {
        vol.Required("level"): vol.Coerce(int),
        vol.Required("power_w"): vol.Coerce(int),
    }
)

_LOAD_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("control_type"): _LOAD_CONTROL,
        vol.Required("priority"): vol.All(int, vol.Range(min=1)),
        vol.Optional("interruptible", default=True): bool,
        vol.Optional("min_on_duration_s", default=0): vol.Coerce(int),
        vol.Optional("min_off_duration_s", default=0): vol.Coerce(int),
        vol.Optional("max_daily_runtime_s"): vol.Coerce(int),
        vol.Optional("max_daily_energy_kwh"): vol.Coerce(float),
        vol.Optional("time_window"): _TIME_WINDOW_SCHEMA,
        vol.Optional("deadline_constraint"): _DEADLINE_SCHEMA,
        # on_off fields
        vol.Optional("nominal_power_w"): vol.Coerce(int),
        vol.Optional("switch_entity"): _ENTITY,
        # stepped fields
        vol.Optional("steps", default=[]): [_STEP_SCHEMA],
        vol.Optional("level_entity"): _ENTITY,
        # modulating fields
        vol.Optional("min_power_w"): vol.Coerce(int),
        vol.Optional("max_power_w"): vol.Coerce(int),
        vol.Optional("step_w", default=1): vol.Coerce(int),
        vol.Optional("power_set_entity"): _ENTITY,
        vol.Optional("actual_power_entity"): _ENTITY,
        # EV fast-charge assist
        vol.Optional("fast_charge", default=False): bool,
        vol.Optional("min_charge_w"): vol.Coerce(int),
        vol.Optional("assist_floor_soc_pct"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional("pause_when_inefficient", default=True): bool,
    }
)

_FORECAST_HOUR_SCHEMA = vol.Schema(
    {
        vol.Required("hour"): vol.All(int, vol.Range(min=0)),
        vol.Required("entity"): str,
    }
)

_FORECAST_SCHEMA = vol.Schema(
    {
        vol.Optional("unit", default=ForecastUnit.W.value): vol.In([u.value for u in ForecastUnit]),
        vol.Required("hours"): [_FORECAST_HOUR_SCHEMA],
    }
)

_TARIFF_SLOT_SCHEMA = vol.Schema(
    {
        vol.Required("start"): _HHMM,
        vol.Required("end"): _HHMM,
        vol.Required("price"): vol.Coerce(float),
    }
)

_TEMPO_PRICE_SCHEMA = vol.Schema(
    {
        vol.Required("hc"): vol.Coerce(float),
        vol.Required("hp"): vol.Coerce(float),
    }
)

_TARIFF_SCHEMA = vol.Schema(
    {
        vol.Optional("type", default="flat"): vol.In(["flat", "hc_hp", "tempo", "spot"]),
        vol.Optional("export_price"): vol.Coerce(float),
        vol.Optional("import_price"): vol.Coerce(float),  # flat
        vol.Optional("slots", default=[]): [_TARIFF_SLOT_SCHEMA],  # hc_hp
        vol.Optional("color_entity"): _ENTITY,  # tempo (today's colour)
        vol.Optional("color_tomorrow_entity"): _ENTITY,  # tempo (tomorrow, for red-day prep)
        vol.Optional("prices"): {vol.In(["blue", "white", "red"]): _TEMPO_PRICE_SCHEMA},  # tempo
        # spot (EPEX / Nordpool): a sensor giving the current price + a markup.
        vol.Optional("price_entity"): _ENTITY,
        vol.Optional("markup"): vol.Coerce(float),
        vol.Optional("price_cap"): vol.Coerce(float),
        vol.Optional("price_floor"): vol.Coerce(float),
    }
)

SOLARBALANCE_SCHEMA = vol.Schema(
    {
        vol.Optional("devices", default=[]): [_DEVICE_SCHEMA],
        vol.Optional("meters", default=[]): [_METER_SCHEMA],
        vol.Optional("loads", default=[]): [_LOAD_SCHEMA],
        vol.Optional("forecast"): _FORECAST_SCHEMA,
        vol.Optional("tariff"): _TARIFF_SCHEMA,
    }
)


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------


def _build_battery_role(raw: Mapping[str, Any]) -> BatteryRole:
    return BatteryRole(
        capacity_kwh=raw["capacity_kwh"],
        max_charge_power_w=raw["max_charge_power_w"],
        max_discharge_power_w=raw["max_discharge_power_w"],
        soc_entity=raw["soc_entity"],
        power_entity=raw.get("power_entity"),
        charge_power_entity=raw.get("charge_power_entity"),
        discharge_power_entity=raw.get("discharge_power_entity"),
        temperature_entity=raw.get("temperature_entity"),
        cycles_entity=raw.get("cycles_entity"),
        soc_min_pct=raw["soc_min_pct"],
        soc_max_pct=raw["soc_max_pct"],
        chemistry=Chemistry(raw["chemistry"]),
        power_sign_convention=PowerSignConvention(raw["power_sign_convention"]),
        usable_capacity_kwh=raw.get("usable_capacity_kwh"),
        controllable=raw["controllable"],
        active_control_enabled=raw["active_control_enabled"],
        discharge_power_setpoint_entity=raw.get("discharge_power_setpoint_entity"),
        charge_power_setpoint_entity=raw.get("charge_power_setpoint_entity"),
        mode_setpoint_entity=raw.get("mode_setpoint_entity"),
        reserve_soc_setpoint_entity=raw.get("reserve_soc_setpoint_entity"),
        ac_charge_limit_w=raw.get("ac_charge_limit_w"),
    )


def _build_mppt_role(raw: Mapping[str, Any]) -> MpptRole:
    return MpptRole(
        peak_power_w=raw["peak_power_w"],
        power_entity=raw["power_entity"],
        daily_energy_entity=raw.get("daily_energy_entity"),
        voltage_entity=raw.get("voltage_entity"),
        current_entity=raw.get("current_entity"),
        feeds=tuple(raw.get("feeds", [])),
        active_control_enabled=raw["active_control_enabled"],
        power_limit_setpoint_entity=raw.get("power_limit_setpoint_entity"),
    )


def _build_inverter_role(raw: Mapping[str, Any]) -> InverterRole:
    return InverterRole(
        nominal_power_w=raw["nominal_power_w"],
        ac_output_power_entity=raw["ac_output_power_entity"],
        ac_input_power_entity=raw.get("ac_input_power_entity"),
        eps_capable=raw.get("eps_capable", False),
        eps_active_entity=raw.get("eps_active_entity"),
        eps_circuits=tuple(raw.get("eps_circuits", [])),
        temperature_entity=raw.get("temperature_entity"),
    )


def _build_device(raw: Mapping[str, Any]) -> Device:
    roles = raw.get("roles", {})
    return Device(
        name=raw["name"],
        battery=_build_battery_role(roles["battery"]) if "battery" in roles else None,
        mppt=_build_mppt_role(roles["mppt"]) if "mppt" in roles else None,
        inverter=_build_inverter_role(roles["inverter"]) if "inverter" in roles else None,
    )


def _build_meter(raw: Mapping[str, Any]) -> Meter:
    return Meter(
        name=raw["name"],
        kind=MeterKind(raw["kind"]),
        power_entity=raw["power_entity"],
        phases=raw.get("phases", 1),
        per_phase_zi=raw.get("per_phase_zi", False),
        power_l1_entity=raw.get("power_l1_entity"),
        power_l2_entity=raw.get("power_l2_entity"),
        power_l3_entity=raw.get("power_l3_entity"),
        daily_import_energy_entity=raw.get("daily_import_energy_entity"),
        daily_export_energy_entity=raw.get("daily_export_energy_entity"),
    )


def _build_load(raw: Mapping[str, Any]) -> Load:
    tw_raw = raw.get("time_window")
    time_window = TimeWindow(start=tw_raw["start"], end=tw_raw["end"]) if tw_raw else None

    dl_raw = raw.get("deadline_constraint")
    deadline = (
        DeadlineConstraint(kwh_required=dl_raw["kwh_required"], before_time=dl_raw["before_time"])
        if dl_raw
        else None
    )

    steps = tuple(LoadStep(level=s["level"], power_w=s["power_w"]) for s in raw.get("steps", []))

    return Load(
        name=raw["name"],
        control_type=LoadControlType(raw["control_type"]),
        priority=raw["priority"],
        interruptible=raw.get("interruptible", True),
        min_on_duration_s=raw.get("min_on_duration_s", 0),
        min_off_duration_s=raw.get("min_off_duration_s", 0),
        max_daily_runtime_s=raw.get("max_daily_runtime_s"),
        max_daily_energy_kwh=raw.get("max_daily_energy_kwh"),
        time_window=time_window,
        deadline_constraint=deadline,
        nominal_power_w=raw.get("nominal_power_w"),
        switch_entity=raw.get("switch_entity"),
        steps=steps,
        level_entity=raw.get("level_entity"),
        min_power_w=raw.get("min_power_w"),
        max_power_w=raw.get("max_power_w"),
        step_w=raw.get("step_w", 1),
        power_set_entity=raw.get("power_set_entity"),
        actual_power_entity=raw.get("actual_power_entity"),
        fast_charge=raw.get("fast_charge", False),
        min_charge_w=raw.get("min_charge_w"),
        assist_floor_soc_pct=raw.get("assist_floor_soc_pct"),
        pause_when_inefficient=raw.get("pause_when_inefficient", True),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _build_forecast(raw: Mapping[str, Any]) -> ForecastConfig:
    return ForecastConfig(
        unit=ForecastUnit(raw["unit"]),
        hour_entities=tuple((h["hour"], h["entity"]) for h in raw["hours"]),
    )


def parse_yaml_config(
    raw: Mapping[str, Any],
) -> tuple[list[Device], list[Meter], list[Load], ForecastConfig | None, dict[str, Any] | None]:
    """Validate and convert the ``solarbalance:`` YAML block.

    Args:
        raw: The ``solarbalance:`` dict from ``configuration.yaml``.

    Returns:
        Tuple of (devices, meters, loads, forecast, tariff_spec). ``forecast`` and
        ``tariff_spec`` are ``None`` when their blocks are not declared; the
        tariff spec is returned raw (validated) for the coordinator to build with
        HA access (the Tempo colour entity needs runtime reads).

    Raises:
        `homeassistant.exceptions.ConfigEntryError` on schema validation errors.
    """
    try:
        validated = SOLARBALANCE_SCHEMA(dict(raw))
    except vol.Invalid as exc:
        raise ConfigEntryError(f"SolarBalance YAML configuration error: {exc}") from exc

    devices: list[Device] = []
    for raw_device in validated["devices"]:
        try:
            devices.append(_build_device(raw_device))
        except (ValueError, KeyError) as exc:
            raise ConfigEntryError(
                f"SolarBalance: invalid device {raw_device.get('name', '?')!r}: {exc}"
            ) from exc

    meters: list[Meter] = []
    for raw_meter in validated["meters"]:
        try:
            meters.append(_build_meter(raw_meter))
        except (ValueError, KeyError) as exc:
            raise ConfigEntryError(
                f"SolarBalance: invalid meter {raw_meter.get('name', '?')!r}: {exc}"
            ) from exc

    loads: list[Load] = []
    for raw_load in validated["loads"]:
        try:
            loads.append(_build_load(raw_load))
        except (ValueError, KeyError) as exc:
            raise ConfigEntryError(
                f"SolarBalance: invalid load {raw_load.get('name', '?')!r}: {exc}"
            ) from exc

    forecast: ForecastConfig | None = None
    if "forecast" in validated:
        try:
            forecast = _build_forecast(validated["forecast"])
        except (ValueError, KeyError) as exc:
            raise ConfigEntryError(f"SolarBalance: invalid forecast block: {exc}") from exc

    tariff_spec: dict[str, Any] | None = validated.get("tariff")

    _LOGGER.info(
        "SolarBalance YAML: %d device(s), %d meter(s), %d load(s), forecast=%s, tariff=%s",
        len(devices),
        len(meters),
        len(loads),
        "yes" if forecast else "no",
        tariff_spec.get("type") if tariff_spec else "flat",
    )
    return devices, meters, loads, forecast, tariff_spec
