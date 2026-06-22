"""Tests for the active control publisher (charge / discharge / mode)."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.solarbalance.adapters.active_control_publisher import (
    ActiveControlPublisher,
)
from custom_components.solarbalance.core.models import BatteryRole, Device, MpptRole


def _device(
    name: str,
    *,
    active: bool = True,
    entity: str | None = "number.dis",
    charge_entity: str | None = None,
    mode_entity: str | None = None,
    controllable: bool = True,
    soc_min_pct: int = 10,
    soc_max_pct: int = 95,
) -> Device:
    return Device(
        name=name,
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="sensor.soc",
            power_entity="sensor.power",
            soc_min_pct=soc_min_pct,
            soc_max_pct=soc_max_pct,
            controllable=controllable,
            active_control_enabled=active,
            discharge_power_setpoint_entity=entity if active else None,
            charge_power_setpoint_entity=charge_entity,
            mode_setpoint_entity=mode_entity,
        ),
    )


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


def _calls(hass: MagicMock) -> list[tuple[str, str, dict[str, object]]]:
    return [(c.args[0], c.args[1], c.args[2]) for c in hass.services.async_call.call_args_list]


def test_enabled_only_when_a_device_declares_entity() -> None:
    assert ActiveControlPublisher(_hass(), [_device("a")]).enabled is True
    assert ActiveControlPublisher(_hass(), [_device("a", active=False)]).enabled is False


async def test_discharge_allocation_written_as_positive_value() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0}, {"a": 50.0})
    calls = _calls(hass)
    assert calls == [("number", "set_value", {"entity_id": "number.dis_a", "value": 800.0})]


async def test_charging_or_idle_writes_zero_discharge() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": 600.0}, {"a": 50.0})
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis_a", "value": 0.0})]


async def test_discharge_cut_at_low_soc_with_margin() -> None:
    hass = _hass()
    # soc_min 10 → floor 10.5. SoC 10.4 ≤ floor → discharge forced to 0.
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a", soc_min_pct=10)])
    await pub.apply({"a": -800.0}, {"a": 10.4})
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis_a", "value": 0.0})]


async def test_discharge_allowed_just_above_floor() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a", soc_min_pct=10)])
    await pub.apply({"a": -800.0}, {"a": 10.6})  # above 10.5 floor
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis_a", "value": 800.0})]


async def test_missing_soc_does_not_cut_discharge() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0}, {})  # no SoC reading → no cutoff
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis_a", "value": 800.0})]


async def test_unchanged_setpoint_is_not_rewritten() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0}, {"a": 50.0})
    await pub.apply({"a": -802.0}, {"a": 50.0})  # within epsilon → skipped
    assert len(_calls(hass)) == 1


async def test_input_number_entity_uses_its_own_domain() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="input_number.dis_a")])
    await pub.apply({"a": -500.0}, {"a": 50.0})
    assert _calls(hass)[0][0] == "input_number"


async def test_reset_commands_zero() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0}, {"a": 50.0})
    await pub.reset()
    assert _calls(hass)[-1] == ("number", "set_value", {"entity_id": "number.dis_a", "value": 0.0})


async def test_only_active_control_devices_are_written() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(
        hass,
        [_device("a", entity="number.dis_a"), _device("b", active=False)],
    )
    await pub.apply({"a": -300.0, "b": -300.0}, {"a": 50.0, "b": 50.0})
    written = {c[2]["entity_id"] for c in _calls(hass)}
    assert written == {"number.dis_a"}


async def test_charge_setpoint_written_when_charging() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity=None, charge_entity="number.chg_a")])
    await pub.apply({"a": 700.0}, {"a": 50.0})
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.chg_a", "value": 700.0})]


async def test_charge_cut_near_soc_ceiling() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(
        hass, [_device("a", entity=None, charge_entity="number.chg_a", soc_max_pct=95)]
    )
    await pub.apply({"a": 700.0}, {"a": 94.6})  # >= 94.5 ceiling → charge cut
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.chg_a", "value": 0.0})]


async def test_mode_select_written() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(
        hass, [_device("a", entity="number.dis_a", mode_entity="select.mode_a")]
    )
    await pub.apply({"a": -800.0}, {"a": 50.0})
    modes = [c for c in _calls(hass) if c[1] == "select_option"]
    assert modes == [
        ("select", "select_option", {"entity_id": "select.mode_a", "option": "discharge"})
    ]


async def test_mode_idle_leaves_mode_untouched_by_default() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(
        hass, [_device("a", entity=None, mode_entity="input_select.mode_a")]
    )
    await pub.apply({"a": 0.0}, {"a": 50.0})
    # idle_mode_option defaults to None → the select is not driven at idle (a vendor
    # strategy select often has no "idle" option; the powers are zeroed regardless).
    assert _calls(hass) == []


def _mppt_device(name: str, *, entity: str | None = "number.pv_limit") -> Device:
    return Device(
        name=name,
        mppt=MpptRole(
            peak_power_w=1000,
            power_entity="sensor.pv",
            active_control_enabled=entity is not None,
            power_limit_setpoint_entity=entity,
        ),
    )


def test_pv_curtailment_enabled_flag() -> None:
    assert ActiveControlPublisher(_hass(), [_mppt_device("pv")]).pv_curtailment_enabled is True
    assert ActiveControlPublisher(_hass(), [_device("a")]).pv_curtailment_enabled is False


async def test_pv_limit_written() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mppt_device("pv", entity="number.pv_limit")])
    await pub.apply_pv_limits({"pv": 650.0})
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.pv_limit", "value": 650.0})
    ]


async def test_publisher_enabled_with_only_pv_limit() -> None:
    pub = ActiveControlPublisher(_hass(), [_mppt_device("pv")])
    assert pub.enabled is True


async def test_service_failure_is_swallowed_and_not_cached() -> None:
    hass = _hass()
    hass.services.async_call.side_effect = RuntimeError("boom")
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0}, {"a": 50.0})  # must not raise
    # failed write is not cached → a retry is attempted on the next tick
    hass.services.async_call.side_effect = None
    await pub.apply({"a": -800.0}, {"a": 50.0})
    assert len(_calls(hass)) == 2


# --- Mode-based battery (e.g. EcoFlow STREAM): ordered switch + latching ---


def _mode_device(name: str = "s") -> Device:
    """A one-direction-at-a-time battery driven via a strategy select."""
    return Device(
        name=name,
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="sensor.soc",
            power_entity="sensor.power",
            active_control_enabled=True,
            mode_setpoint_entity="select.strat",
            charge_mode_option="scheduled",
            discharge_mode_option="self_powered",
            charge_power_setpoint_entity="number.chg",
            discharge_power_setpoint_entity="number.dis",
        ),
    )


async def test_mode_battery_charge_switch_is_ordered() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mode_device()])
    await pub.apply({"s": 600.0}, {"s": 50.0})
    # Zero the opposite direction, switch the strategy, THEN set the charge power.
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.dis", "value": 0.0}),
        ("select", "select_option", {"entity_id": "select.strat", "option": "scheduled"}),
        ("number", "set_value", {"entity_id": "number.chg", "value": 600.0}),
    ]


async def test_mode_battery_switch_to_discharge_zeroes_charge_first() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mode_device()])
    await pub.apply({"s": 600.0}, {"s": 50.0})  # now in scheduled/charge
    hass.services.async_call.reset_mock()
    await pub.apply({"s": -400.0}, {"s": 50.0})
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.chg", "value": 0.0}),
        ("select", "select_option", {"entity_id": "select.strat", "option": "self_powered"}),
        ("number", "set_value", {"entity_id": "number.dis", "value": 400.0}),
    ]


async def test_mode_battery_no_reswitch_when_direction_unchanged() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mode_device()])
    await pub.apply({"s": 600.0}, {"s": 50.0})  # switch to scheduled
    hass.services.async_call.reset_mock()
    await pub.apply({"s": 400.0}, {"s": 50.0})  # still charging, just less power
    # No opposite-zeroing, no strategy re-switch — only the charge power moves.
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.chg", "value": 400.0}),
    ]


async def test_mode_idle_writes_option_when_configured() -> None:
    hass = _hass()
    dev = Device(
        name="s",
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="sensor.soc",
            power_entity="sensor.power",
            active_control_enabled=True,
            mode_setpoint_entity="select.strat",
            idle_mode_option="idle",
            charge_power_setpoint_entity="number.chg",
            discharge_power_setpoint_entity="number.dis",
        ),
    )
    pub = ActiveControlPublisher(hass, [dev])
    await pub.apply({"s": 0.0}, {"s": 50.0})
    modes = [c for c in _calls(hass) if c[1] == "select_option"]
    assert modes == [("select", "select_option", {"entity_id": "select.strat", "option": "idle"})]
