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
