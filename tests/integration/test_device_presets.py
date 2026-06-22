"""Device-preset wizard: defaults + entity auto-detection when adding a device."""

from unittest.mock import MagicMock

from custom_components.solarbalance.config_flow import (
    BatteryMpptSubentryFlowHandler,
    BatterySubentryFlowHandler,
    _battery_input_to_device,
)
from custom_components.solarbalance.yaml_loader import build_device_from_dict

# A realistic EcoFlow STREAM (ef_60605) entity set, as exposed by the BLE integration.
_STREAM_IDS = [
    "select.ef_60605_energy_strategy",
    "sensor.ef_60605_battery_level",
    "sensor.ef_60605_battery_power",
    "sensor.ef_60605_cell_temperature",
    "sensor.ef_60605_pv_power_total",
    "number.ef_60605_charging_power_limit",
    "number.ef_60605_base_load_power",
    "number.ef_60605_backup_reserve",
]


def _hass_with(entity_ids: list[str]) -> MagicMock:
    hass = MagicMock()
    hass.states.async_entity_ids = lambda domain: [
        e for e in entity_ids if e.startswith(f"{domain}.")
    ]
    hass.states.get = lambda eid: object() if eid in entity_ids else None
    return hass


def _handler(cls: type, entity_ids: list[str]):
    h = cls()
    h.hass = _hass_with(entity_ids)
    return h


def test_stream_preset_autodetects_entities_and_options() -> None:
    h = _handler(BatteryMpptSubentryFlowHandler, _STREAM_IDS)
    d = h._preset_defaults("stream")
    # Name derived from the discovered device prefix.
    assert d["name"] == "EcoFlow STREAM 60605"
    # Battery entities auto-mapped from the ef_60605 prefix.
    assert d["soc_entity"] == "sensor.ef_60605_battery_level"
    assert d["power_entity"] == "sensor.ef_60605_battery_power"
    assert d["charge_power_setpoint_entity"] == "number.ef_60605_charging_power_limit"
    assert d["discharge_power_setpoint_entity"] == "number.ef_60605_base_load_power"
    assert d["mode_setpoint_entity"] == "select.ef_60605_energy_strategy"
    assert d["reserve_soc_setpoint_entity"] == "number.ef_60605_backup_reserve"
    # Mode-switch options for the STREAM protocol.
    assert d["charge_mode_option"] == "scheduled"
    assert d["discharge_mode_option"] == "self_powered"
    assert d["active_control_enabled"] is True
    # MPPT role nested for the battery+mppt schema.
    assert d["roles"]["mppt"]["power_entity"] == "sensor.ef_60605_pv_power_total"
    assert d["roles"]["mppt"]["peak_power_w"] == 2000


def test_generic_preset_is_blank() -> None:
    h = _handler(BatteryMpptSubentryFlowHandler, _STREAM_IDS)
    assert h._preset_defaults("generic") == {}


def test_stream_preset_without_entities_keeps_static_defaults() -> None:
    # No STREAM entities present → no prefix, no entity fields, generic name.
    h = _handler(BatteryMpptSubentryFlowHandler, ["sensor.shelly_3em_power"])
    d = h._preset_defaults("stream")
    assert d["name"] == "EcoFlow STREAM"
    assert "soc_entity" not in d
    assert d["charge_mode_option"] == "scheduled"  # static default still applied


def test_battery_preset_builds_a_valid_device() -> None:
    # The battery-kind preset defaults are the flat form keys → assembling and
    # building them yields a valid device (entities resolved, active control OK).
    h = _handler(BatterySubentryFlowHandler, _STREAM_IDS)
    defaults = h._preset_defaults("stream")
    device = _battery_input_to_device(defaults)
    build_device_from_dict(device)  # must not raise
    assert device["roles"]["battery"]["mode_setpoint_entity"] == "select.ef_60605_energy_strategy"
