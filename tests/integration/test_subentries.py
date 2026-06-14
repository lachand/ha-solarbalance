"""Tests for UI device configuration via config subentries (battery)."""

from types import SimpleNamespace

from custom_components.solarbalance import _build_from_subentries
from custom_components.solarbalance.config_flow import _battery_input_to_device
from custom_components.solarbalance.yaml_loader import build_device_from_dict


def _entry_with_subentries(*subs):
    return SimpleNamespace(subentries={f"s{i}": s for i, s in enumerate(subs)})


def _sub(subentry_type, data, title="x"):
    return SimpleNamespace(subentry_type=subentry_type, data=data, title=title)


def test_battery_input_to_device_strips_empty_and_wraps_roles() -> None:
    ui = {
        "name": "stream",
        "capacity_kwh": 3.92,
        "max_charge_power_w": 1200,
        "max_discharge_power_w": 2300,
        "soc_entity": "sensor.soc",
        "power_entity": "sensor.power",
        "temperature_entity": "",  # empty → dropped
        "controllable": True,
    }
    device = _battery_input_to_device(ui)
    assert device["name"] == "stream"
    bat = device["roles"]["battery"]
    assert bat["capacity_kwh"] == 3.92
    assert "temperature_entity" not in bat  # empty stripped
    # Validates through the shared builder without raising.
    built = build_device_from_dict(device)
    assert built.battery is not None
    assert built.battery.capacity_kwh == 3.92


def test_build_from_subentries_builds_battery_device() -> None:
    data = {
        "name": "stream",
        "roles": {
            "battery": {
                "capacity_kwh": 3.92,
                "max_charge_power_w": 1200,
                "max_discharge_power_w": 2300,
                "soc_entity": "sensor.soc",
                "power_entity": "sensor.power",
            }
        },
    }
    entry = _entry_with_subentries(_sub("battery", data, "stream"))
    devices, meters, loads = _build_from_subentries(entry)
    assert len(devices) == 1 and devices[0].name == "stream"
    assert devices[0].battery is not None
    assert not meters and not loads


def test_build_from_subentries_skips_invalid() -> None:
    bad = {"name": "broken", "roles": {"battery": {"capacity_kwh": 5.0}}}  # missing required
    entry = _entry_with_subentries(_sub("battery", bad))
    devices, _meters, _loads = _build_from_subentries(entry)
    assert devices == []  # invalid subentry skipped, no crash


def test_load_input_parses_steps_and_deadline() -> None:
    from custom_components.solarbalance.config_flow import _load_input_to_dict
    from custom_components.solarbalance.yaml_loader import build_load_from_dict

    ui = {
        "name": "voiture",
        "control_type": "stepped",
        "priority": 5,
        "interruptible": True,
        "switch_entity": "switch.borne",
        "level_entity": "number.borne_amperage",
        "steps": "6:1380, 8:1840, 10:2300",
        "fast_charge": True,
        "min_charge_w": 2300,
        "assist_floor_soc_pct": 50,
        "deadline_kwh": 10,
        "deadline_before": "07:00",
    }
    load = _load_input_to_dict(ui)
    assert load["steps"] == [
        {"level": 6, "power_w": 1380},
        {"level": 8, "power_w": 1840},
        {"level": 10, "power_w": 2300},
    ]
    assert load["deadline_constraint"] == {"kwh_required": 10, "before_time": "07:00"}
    built = build_load_from_dict(load)
    assert built.fast_charge is True
    assert built.deadline_constraint is not None


def test_load_subentry_builds_via_assembler() -> None:
    data = {
        "name": "wh",
        "control_type": "on_off",
        "priority": 3,
        "nominal_power_w": 2000,
        "switch_entity": "switch.wh",
    }
    entry = _entry_with_subentries(_sub("load", data, "wh"))
    devices, meters, loads = _build_from_subentries(entry)
    assert len(loads) == 1 and loads[0].name == "wh"
    assert not devices and not meters


def test_bad_steps_raise() -> None:
    import pytest

    from custom_components.solarbalance.config_flow import _parse_steps

    with pytest.raises(ValueError):
        _parse_steps("6-1380")  # missing ':'


def test_mppt_input_and_build() -> None:
    from custom_components.solarbalance.config_flow import _mppt_input_to_device
    from custom_components.solarbalance.yaml_loader import build_device_from_dict

    ui = {
        "name": "onduleur",
        "peak_power_w": 1000,
        "power_entity": "sensor.pv",
        "active_control_enabled": True,
        "power_limit_setpoint_entity": "number.limit",
    }
    device = _mppt_input_to_device(ui)
    built = build_device_from_dict(device)
    assert built.mppt is not None and built.mppt.peak_power_w == 1000


def test_meter_input_coerces_phases_and_builds() -> None:
    from custom_components.solarbalance.config_flow import _meter_input_to_dict
    from custom_components.solarbalance.yaml_loader import build_meter_from_dict

    ui = {"name": "pdl", "kind": "pdl", "power_entity": "sensor.grid", "phases": "3"}
    meter = _meter_input_to_dict(ui)
    assert meter["phases"] == 3  # coerced from select string
    built = build_meter_from_dict(meter)
    assert built.name == "pdl"


def test_build_from_subentries_mixed_types() -> None:
    bat = {"name": "b", "roles": {"battery": {
        "capacity_kwh": 5.0, "max_charge_power_w": 1000, "max_discharge_power_w": 1000,
        "soc_entity": "sensor.s", "power_entity": "sensor.p",
    }}}
    mppt = {"name": "m", "roles": {"mppt": {"peak_power_w": 800, "power_entity": "sensor.pv"}}}
    meter = {"name": "pdl", "kind": "pdl", "power_entity": "sensor.grid"}
    ld = {"name": "wh", "control_type": "on_off", "priority": 1, "nominal_power_w": 2000,
          "switch_entity": "switch.wh"}
    entry = _entry_with_subentries(
        _sub("battery", bat), _sub("mppt", mppt), _sub("meter", meter), _sub("load", ld)
    )
    devices, meters, loads = _build_from_subentries(entry)
    assert len(devices) == 2 and len(meters) == 1 and len(loads) == 1


def test_battery_mppt_combined_builds_both_roles() -> None:
    from custom_components.solarbalance.config_flow import _battery_mppt_input_to_device
    from custom_components.solarbalance.yaml_loader import build_device_from_dict

    ui = {
        "name": "stream",
        "capacity_kwh": 3.92,
        "max_charge_power_w": 1200,
        "max_discharge_power_w": 2300,
        "soc_entity": "sensor.soc",
        "power_entity": "sensor.batt_power",
        "mppt_peak_power_w": 1000,
        "mppt_power_entity": "sensor.pv_power",
    }
    device = _battery_mppt_input_to_device(ui)
    built = build_device_from_dict(device)
    assert built.battery is not None and built.mppt is not None
    assert built.mppt.peak_power_w == 1000
    # power_entity must not collide between roles
    assert built.battery.power_entity == "sensor.batt_power"
    assert built.mppt.power_entity == "sensor.pv_power"


def test_battery_mppt_subentry_assembles() -> None:
    data = {
        "name": "stream",
        "roles": {
            "battery": {
                "capacity_kwh": 3.92, "max_charge_power_w": 1200, "max_discharge_power_w": 2300,
                "soc_entity": "sensor.soc", "power_entity": "sensor.bp",
            },
            "mppt": {"peak_power_w": 1000, "power_entity": "sensor.pv"},
        },
    }
    entry = _entry_with_subentries(_sub("battery_mppt", data, "stream"))
    devices, _m, _l = _build_from_subentries(entry)
    assert len(devices) == 1
    assert devices[0].battery is not None and devices[0].mppt is not None
