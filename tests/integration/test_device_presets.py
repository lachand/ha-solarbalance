"""Device-preset wizard: defaults + entity auto-detection when adding a device."""

from unittest.mock import MagicMock

from custom_components.solarbalance.config_flow import (
    _PRESETS,
    BatteryMpptSubentryFlowHandler,
    BatterySubentryFlowHandler,
    MpptSubentryFlowHandler,
    _battery_input_to_device,
)
from custom_components.solarbalance.yaml_loader import build_device_from_dict

# A realistic EcoFlow STREAM (ef_xxxxxx) entity set, as exposed by the BLE integration.
_STREAM_IDS = [
    "select.ef_xxxxxx_energy_strategy",
    "sensor.ef_xxxxxx_battery_level",
    "sensor.ef_xxxxxx_battery_power",
    "sensor.ef_xxxxxx_cell_temperature",
    "sensor.ef_xxxxxx_pv_power_total",
    "number.ef_xxxxxx_charging_power_limit",
    "number.ef_xxxxxx_base_load_power",
    "number.ef_xxxxxx_backup_reserve",
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
    assert d["name"] == "EcoFlow STREAM xxxxxx"
    # Battery entities auto-mapped from the ef_xxxxxx prefix.
    assert d["soc_entity"] == "sensor.ef_xxxxxx_battery_level"
    assert d["power_entity"] == "sensor.ef_xxxxxx_battery_power"
    assert d["charge_power_setpoint_entity"] == "number.ef_xxxxxx_charging_power_limit"
    assert d["discharge_power_setpoint_entity"] == "number.ef_xxxxxx_base_load_power"
    assert d["mode_setpoint_entity"] == "select.ef_xxxxxx_energy_strategy"
    assert d["reserve_soc_setpoint_entity"] == "number.ef_xxxxxx_backup_reserve"
    # Mode-switch options for the STREAM protocol.
    assert d["charge_mode_option"] == "scheduled"
    assert d["discharge_mode_option"] == "self_powered"
    assert d["active_control_enabled"] is True
    # MPPT role nested for the battery+mppt schema.
    assert d["roles"]["mppt"]["power_entity"] == "sensor.ef_xxxxxx_pv_power_total"
    assert d["roles"]["mppt"]["peak_power_w"] == 2000


def test_stream_inverter_preset_autodetects_curtailment() -> None:
    # The STREAM's micro-inverter is a separate ef_bk… device, added as MPPT only.
    ids = [
        "number.ef_bkxxxx_maximum_output_power",
        "sensor.ef_bkxxxx_grid_power",
        "sensor.ef_bkxxxx_pv_1_power",
    ]
    h = _handler(MpptSubentryFlowHandler, ids)
    d = h._preset_defaults("stream_inverter")
    assert d["name"] == "EcoFlow STREAM inverter bkxxxx"
    assert d["power_entity"] == "sensor.ef_bkxxxx_grid_power"
    assert d["power_limit_setpoint_entity"] == "number.ef_bkxxxx_maximum_output_power"
    assert d["active_control_enabled"] is True
    assert d["peak_power_w"] == 800
    assert "roles" not in d  # flat shape for the mppt kind


def test_preset_options_are_filtered_by_kind() -> None:
    def by_kind(kind: str) -> list[str]:
        return [k for k, p in _PRESETS.items() if kind in p.applies_to]

    assert "stream" in by_kind("battery")
    assert "stream_inverter" not in by_kind("battery")
    assert by_kind("mppt") == ["stream_inverter"]
    assert "stream" in by_kind("battery_mppt")


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
    assert device["roles"]["battery"]["mode_setpoint_entity"] == "select.ef_xxxxxx_energy_strategy"
