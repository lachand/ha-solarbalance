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


def test_battery_flat_round_trips_input_to_device() -> None:
    """Reconfigure prefill must invert the add-flow assembly (flat ⇄ device)."""
    from custom_components.solarbalance.config_flow import _battery_flat

    ui = {
        "name": "stream",
        "capacity_kwh": 3.92,
        "max_charge_power_w": 1200,
        "max_discharge_power_w": 2300,
        "soc_entity": "sensor.soc",
        "power_entity": "sensor.power",
    }
    device = _battery_input_to_device(ui)
    flat = _battery_flat(device)
    assert flat == ui  # stored device flattens back to the original form input


def test_battery_mppt_prefill_keeps_flat_battery_and_mppt_role() -> None:
    from custom_components.solarbalance.config_flow import (
        BatteryMpptSubentryFlowHandler,
        _battery_mppt_input_to_device,
    )

    ui = {
        "name": "stream",
        "capacity_kwh": 3.92,
        "max_charge_power_w": 1200,
        "max_discharge_power_w": 2300,
        "soc_entity": "sensor.soc",
        "power_entity": "sensor.bp",
        "mppt_peak_power_w": 1000,
        "mppt_power_entity": "sensor.pv",
    }
    device = _battery_mppt_input_to_device(ui)
    prefill = BatteryMpptSubentryFlowHandler._prefill(None, device)
    assert prefill["capacity_kwh"] == 3.92  # battery flattened to top level
    assert prefill["roles"]["mppt"]["peak_power_w"] == 1000  # mppt role kept for schema


def test_meter_prefill_coerces_phases_to_str() -> None:
    from custom_components.solarbalance.config_flow import MeterSubentryFlowHandler

    stored = {"name": "pdl", "kind": "pdl", "power_entity": "sensor.grid", "phases": 3}
    prefill = MeterSubentryFlowHandler._prefill(None, stored)
    assert prefill["phases"] == "3"  # select option is a string


async def test_battery_sensors_linked_to_subentry(hass) -> None:
    """Per-battery sensors must register under their device's UI subentry."""
    from homeassistant.config_entries import ConfigSubentryData
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solarbalance.const import (
        CONF_PHASES,
        CONF_PRIORITIES,
        CONF_SUBSCRIBED_POWER_KVA,
        CONF_TICK_INTERVAL_S,
        DOMAIN,
    )
    from custom_components.solarbalance.core.models import StrategyKind

    battery = ConfigSubentryData(
        subentry_type="battery",
        title="stream",
        unique_id=None,
        data={
            "name": "stream",
            "roles": {"battery": {
                "capacity_kwh": 3.92, "max_charge_power_w": 1200, "max_discharge_power_w": 2300,
                "soc_entity": "sensor.stream_soc", "power_entity": "sensor.stream_power",
            }},
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10,
            CONF_PHASES: 1,
            CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
        subentries_data=[battery],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sub_id = next(iter(entry.subentries))
    reg = er.async_get(hass)
    battery_entities = [
        e for e in reg.entities.values()
        if e.config_entry_id == entry.entry_id and "_stream_" in e.unique_id
    ]
    assert battery_entities, "no per-battery sensors registered"
    assert all(e.config_subentry_id == sub_id for e in battery_entities)


async def test_load_shed_exempt_switch_created_and_linked(hass) -> None:
    """An interruptible load gets a 'do not shed' switch under its subentry."""
    from homeassistant.config_entries import ConfigSubentryData
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solarbalance import COORDINATOR_KEY
    from custom_components.solarbalance.const import (
        CONF_PHASES,
        CONF_PRIORITIES,
        CONF_SUBSCRIBED_POWER_KVA,
        CONF_TICK_INTERVAL_S,
        DOMAIN,
    )
    from custom_components.solarbalance.core.models import StrategyKind

    load = ConfigSubentryData(
        subentry_type="load",
        title="voiture",
        unique_id=None,
        data={
            "name": "voiture", "control_type": "on_off", "priority": 5,
            "interruptible": True, "switch_entity": "switch.borne", "nominal_power_w": 2000,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10,
            CONF_PHASES: 1,
            CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
        subentries_data=[load],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sub_id = next(iter(entry.subentries))
    reg = er.async_get(hass)
    sw = next(
        (e for e in reg.entities.values() if e.unique_id.endswith("_load_voiture_shed_exempt")),
        None,
    )
    assert sw is not None, "shed-exempt switch not created"
    assert sw.config_subentry_id == sub_id  # grouped under the load's subentry

    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    assert not coordinator.is_shed_exempt("voiture")
    coordinator.set_shed_exempt("voiture", True)
    assert coordinator.is_shed_exempt("voiture")
    coordinator.set_shed_exempt("voiture", False)
    assert not coordinator.is_shed_exempt("voiture")


async def test_force_charge_switch_request_and_autoclear(hass) -> None:
    """The force-charge switch is created/linked, forces the load, and auto-clears."""
    from homeassistant.config_entries import ConfigSubentryData
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solarbalance import COORDINATOR_KEY
    from custom_components.solarbalance.const import (
        CONF_PHASES,
        CONF_PRIORITIES,
        CONF_SUBSCRIBED_POWER_KVA,
        CONF_TICK_INTERVAL_S,
        DOMAIN,
    )
    from custom_components.solarbalance.core.models import StrategyKind

    load = ConfigSubentryData(
        subentry_type="load",
        title="voiture",
        unique_id=None,
        data={
            "name": "voiture", "control_type": "on_off", "priority": 5,
            "interruptible": True, "switch_entity": "switch.borne", "nominal_power_w": 2000,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10, CONF_PHASES: 1, CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
        subentries_data=[load],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sub_id = next(iter(entry.subentries))
    reg = er.async_get(hass)
    sw = next(
        (e for e in reg.entities.values() if e.unique_id.endswith("_load_voiture_force_charge")),
        None,
    )
    assert sw is not None and sw.config_subentry_id == sub_id

    coord = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    coord.request_force_charge_load("voiture")
    assert coord.force_charge_load_active("voiture")
    # With no prior dispatch command, force-charge injects a full-power "on".
    forced = coord._apply_force_charge((), coord.data)
    assert any(c.load_name == "voiture" and c.on for c in forced)

    # A kWh-bounded request auto-clears once the energy is delivered.
    coord.request_force_charge_load("voiture", kwh=1.0)
    coord._load_energy_kwh["voiture"] = coord._load_energy_kwh.get("voiture", 0.0) + 2.0
    coord._apply_force_charge((), coord.data)
    assert not coord.force_charge_load_active("voiture")


async def test_off_peak_only_forces_load_off_outside_cheap_window(hass) -> None:
    """An off-peak-only load is forced off when the tariff window is not cheap."""
    from types import SimpleNamespace

    from homeassistant.config_entries import ConfigSubentryData
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solarbalance import COORDINATOR_KEY
    from custom_components.solarbalance.const import (
        CONF_PHASES,
        CONF_PRIORITIES,
        CONF_SUBSCRIBED_POWER_KVA,
        CONF_TICK_INTERVAL_S,
        DOMAIN,
    )
    from custom_components.solarbalance.core.controllers.load_dispatch import LoadCommand
    from custom_components.solarbalance.core.models import StrategyKind

    load = ConfigSubentryData(
        subentry_type="load", title="voiture", unique_id=None,
        data={"name": "voiture", "control_type": "on_off", "priority": 5,
              "interruptible": True, "switch_entity": "switch.borne", "nominal_power_w": 2000},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TICK_INTERVAL_S: 10, CONF_PHASES: 1, CONF_SUBSCRIBED_POWER_KVA: 6,
              CONF_PRIORITIES: [k.value for k in StrategyKind]},
        subentries_data=[load],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coord = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    coord.set_off_peak_only("voiture", True)
    cmds = (LoadCommand(load_name="voiture", on=True, rationale="dispatch"),)

    coord._tariff = SimpleNamespace(is_cheap_window=lambda ts, *, threshold: False)
    out = coord._apply_off_peak(cmds, coord.data)
    assert out[0].on is False and out[0].rationale == "off_peak_only"

    coord._tariff = SimpleNamespace(is_cheap_window=lambda ts, *, threshold: True)
    out = coord._apply_off_peak(cmds, coord.data)
    assert out[0].on is True  # cheap window → unchanged


def test_optional_empty_fields_pass_schema_validation() -> None:
    """Re-submitting a prefilled form with blank optional entity/number fields
    must validate (regression: 'Entity is neither a valid entity ID nor a valid
    UUID' / 'expected float' blocked saving)."""
    import voluptuous as vol

    from custom_components.solarbalance.config_flow import (
        _battery_flat,
        _battery_subentry_schema,
    )

    stored = {
        "name": "stream",
        "roles": {"battery": {
            "capacity_kwh": 3.92, "max_charge_power_w": 1200, "max_discharge_power_w": 2300,
            "soc_entity": "sensor.soc", "power_entity": "sensor.bp",
        }},
    }
    schema = _battery_subentry_schema(_battery_flat(stored))
    submit = {
        str(m): (m.default() if m.default is not vol.UNDEFINED else None)
        for m in schema.schema
    }
    # temperature_entity / cycles_entity / usable_capacity_kwh are blank ("").
    validated = schema(submit)
    assert validated["temperature_entity"] == ""  # blank optional entity accepted
    assert validated["usable_capacity_kwh"] == ""  # blank optional number accepted


def test_remaining_production_caps_at_local_midnight() -> None:
    """The integral must stop at midnight so tomorrow's sun never counts."""
    from custom_components.solarbalance.coordinator import SolarBalanceCoordinator

    # 24-slot profile, 1000 W every hour; slot 0 = current hour.
    profile = [1000.0] * 24
    # 3 slots left until midnight (e.g. local hour 21), full current hour.
    kwh, hours = SolarBalanceCoordinator._integrate_remaining(profile, 1.0, max_slots=3)
    assert kwh == 3.0  # 3 hours x 1 kWh, not 24
    assert hours == 3.0
    # Without a cap the old behaviour rolled into tomorrow.
    kwh_all, _ = SolarBalanceCoordinator._integrate_remaining(profile, 1.0)
    assert kwh_all == 24.0


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
