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
