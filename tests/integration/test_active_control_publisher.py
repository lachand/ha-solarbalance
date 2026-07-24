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


def test_duplicate_setpoint_entity_warns(caplog) -> None:  # type: ignore[no-untyped-def]
    import logging

    # Two devices writing to the same charge entity = a stale/duplicate device.
    with caplog.at_level(logging.WARNING):
        ActiveControlPublisher(
            _hass(),
            [
                _device("stream", entity=None, charge_entity="number.chg_shared"),
                _device("stream_xxxxx", entity=None, charge_entity="number.chg_shared"),
            ],
        )
    assert any("both write to number.chg_shared" in r.message for r in caplog.records), caplog.text


def test_distinct_setpoint_entities_do_not_warn(caplog) -> None:  # type: ignore[no-untyped-def]
    import logging

    with caplog.at_level(logging.WARNING):
        ActiveControlPublisher(
            _hass(),
            [
                _device("a", entity=None, charge_entity="number.chg_a"),
                _device("b", entity=None, charge_entity="number.chg_b"),
            ],
        )
    assert not any("both write to" in r.message for r in caplog.records)


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


def _river2(ceiling: int = 100) -> Device:
    # Charge-only station: max_discharge=0, a charge-power slider + a max-charge-SoC gate.
    return Device(
        name="r2",
        battery=BatteryRole(
            capacity_kwh=0.256,
            max_charge_power_w=360,
            max_discharge_power_w=0,
            soc_entity="sensor.soc",
            power_entity="sensor.pow",
            controllable=True,
            active_control_enabled=True,
            charge_power_setpoint_entity="number.speed",
            charge_limit_soc_setpoint_entity="number.limit",
            charge_ceiling_soc_pct=ceiling,
        ),
    )


async def test_river2_charge_gate_on_then_off() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_river2()])
    # Surplus → gate ON: raise the SoC limit to the ceiling AND drive the power slider.
    await pub.apply({"r2": 300.0}, {"r2": 45.0})
    calls = _calls(hass)
    assert ("number", "set_value", {"entity_id": "number.limit", "value": 100}) in calls
    assert ("number", "set_value", {"entity_id": "number.speed", "value": 300.0}) in calls
    # No surplus → gate OFF: drop the limit to floor(SoC) to stop; no new speed write.
    hass.services.async_call.reset_mock()
    await pub.apply({"r2": 0.0}, {"r2": 45.7})
    calls = _calls(hass)
    assert ("number", "set_value", {"entity_id": "number.limit", "value": 45}) in calls
    assert not any(c[2]["entity_id"] == "number.speed" for c in calls)


async def test_river2_charge_gate_hysteresis_holds() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_river2()])
    await pub.apply({"r2": 300.0}, {"r2": 45.0})  # ON
    hass.services.async_call.reset_mock()
    # 80 W is between the OFF (40) and ON (120) thresholds → stays ON, keeps charging.
    await pub.apply({"r2": 80.0}, {"r2": 45.0})
    assert ("number", "set_value", {"entity_id": "number.speed", "value": 80.0}) in _calls(hass)


def test_charge_only_battery_rejects_discharge_setpoint() -> None:
    import pytest

    with pytest.raises(ValueError, match="charge-only"):
        BatteryRole(
            capacity_kwh=1.0,
            max_charge_power_w=360,
            max_discharge_power_w=0,
            soc_entity="sensor.soc",
            power_entity="sensor.pow",
            controllable=True,
            active_control_enabled=True,
            discharge_power_setpoint_entity="number.dis",
        )


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


async def test_verify_pv_limit_rewrites_when_actual_drifts() -> None:
    # The write was sent (and latched) but the inverter didn't apply it (wrong /
    # intermittent entity): verify reads the actual back and re-asserts it.
    from types import SimpleNamespace

    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mppt_device("pv", entity="number.pv_limit")])
    await pub.apply_pv_limits({"pv": 800.0})  # commanded + latched
    hass.states.get = lambda eid: SimpleNamespace(state="0")  # reads back 0 → didn't land
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.pv_limit", "value": 800.0})
    ]


async def test_verify_pv_limit_no_rewrite_when_in_tolerance() -> None:
    from types import SimpleNamespace

    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mppt_device("pv", entity="number.pv_limit")])
    await pub.apply_pv_limits({"pv": 800.0})
    hass.states.get = lambda eid: SimpleNamespace(state="790")  # within tolerance
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert _calls(hass) == []


async def test_verify_failures_exposed_for_dashboard() -> None:
    from types import SimpleNamespace

    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mppt_device("pv", entity="number.pv_limit")])
    await pub.apply_pv_limits({"pv": 800.0})
    hass.states.get = lambda eid: SimpleNamespace(state="0")  # didn't land
    await pub.verify_writes()
    assert pub.verify_failures() == {"number.pv_limit": 800.0}
    # Once it applies, the failure clears.
    hass.states.get = lambda eid: SimpleNamespace(state="800")
    await pub.verify_writes()
    assert pub.verify_failures() == {}


def test_duplicate_entities_exposed_for_dashboard() -> None:
    pub = ActiveControlPublisher(
        _hass(),
        [
            _device("stream", entity=None, charge_entity="number.chg_shared"),
            _device("stream_xxxxx", entity=None, charge_entity="number.chg_shared"),
        ],
    )
    assert pub.duplicate_entities() == {"number.chg_shared": "stream & stream_xxxxx"}


async def test_power_write_clamped_to_entity_range() -> None:
    # A STREAM charging_power_limit maxes out below the allocation (e.g. 1050 W): the
    # write must clamp to the entity range, not send 1100 W (which raises
    # ServiceValidationError) and then re-write it forever via verify.
    from types import SimpleNamespace

    hass = _hass()
    hass.states.get = lambda eid: SimpleNamespace(state="1050", attributes={"min": 0, "max": 1050})
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -1100.0}, {"a": 50.0})
    # Commanded 1100 → clamped to the entity's 1050 ceiling for the actual write.
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis_a", "value": 1050.0})]
    # The latch holds the clamped 1050, matching the readback → verify does NOT re-write
    # (no ServiceValidationError loop).
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert _calls(hass) == []


async def test_discharge_mirror_group_totals_discharge_but_splits_charge() -> None:
    # Two STREAM batteries grouped: the discharge TOTAL is mirrored to each base-load
    # (800 to both = 800 total), while the charge stays per-battery.
    def _batt(name: str, dis: str, chg: str) -> Device:
        return Device(
            name=name,
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=2000,
                max_discharge_power_w=2000,
                soc_entity="sensor.soc",
                power_entity="sensor.power",
                controllable=True,
                active_control_enabled=True,
                discharge_power_setpoint_entity=dis,
                charge_power_setpoint_entity=chg,
                discharge_mirror_group="stream",
            ),
        )

    def _values(hass: MagicMock) -> dict[str, float]:
        return {
            c.args[2]["entity_id"]: c.args[2]["value"]
            for c in hass.services.async_call.call_args_list
        }

    hass = _hass()
    pub = ActiveControlPublisher(
        hass,
        [_batt("a", "number.dis_a", "number.chg_a"), _batt("b", "number.dis_b", "number.chg_b")],
    )
    # Discharge split -500 / -300 by the balancer → group total 800 mirrored to both.
    await pub.apply({"a": -500.0, "b": -300.0}, {"a": 50.0, "b": 50.0})
    vals = _values(hass)
    assert vals["number.dis_a"] == 800.0
    assert vals["number.dis_b"] == 800.0
    # The written-setpoint accessor (what the diagnostic shows) mirrors too.
    assert pub.last_setpoint_w("a", charge=False) == 800.0
    assert pub.last_setpoint_w("b", charge=False) == 800.0

    # Charge stays per-battery (not mirrored).
    hass.services.async_call.reset_mock()
    await pub.apply({"a": 400.0, "b": 200.0}, {"a": 50.0, "b": 50.0})
    vals = _values(hass)
    assert vals["number.chg_a"] == 400.0
    assert vals["number.chg_b"] == 200.0


async def test_verify_rewrites_battery_charge_setpoint_that_didnt_land() -> None:
    # A STREAM that accepted charge=600 then reverted its charging_power_limit to 0:
    # verify must re-assert the commanded charge (the user-reported symptom).
    from types import SimpleNamespace

    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("batt", charge_entity="number.chg", entity=None)])
    await pub.apply({"batt": 600.0}, {"batt": 50.0})  # command charge → latched
    hass.states.get = lambda eid: SimpleNamespace(state="0")  # box reverted it to 0
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert ("number", "set_value", {"entity_id": "number.chg", "value": 600.0}) in _calls(hass)


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


async def test_mode_battery_charge_switch_is_ordered_over_ticks() -> None:
    # One mutation per tick, gated on the device's ACTUAL state: zero base load →
    # switch strategy → set charge power. The box only honours the charge limit once
    # it actually reports "scheduled", so each step waits a tick for the prior to land.
    from types import SimpleNamespace

    hass = _hass()
    st = {"number.dis": 399.0, "select.strat": "self_powered", "number.chg": 0.0}
    hass.states.get = lambda eid: SimpleNamespace(state=str(st[eid])) if eid in st else None
    pub = ActiveControlPublisher(hass, [_mode_device()])

    await pub.apply({"s": 600.0}, {"s": 50.0})  # tick 1: base load non-zero → zero it
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis", "value": 0.0})]
    st["number.dis"] = 0.0

    hass.services.async_call.reset_mock()
    await pub.apply({"s": 600.0}, {"s": 50.0})  # tick 2: strategy wrong → switch
    assert _calls(hass) == [
        ("select", "select_option", {"entity_id": "select.strat", "option": "scheduled"})
    ]
    st["select.strat"] = "scheduled"

    hass.services.async_call.reset_mock()
    await pub.apply({"s": 600.0}, {"s": 50.0})  # tick 3: ready → set charge power
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.chg", "value": 600.0})]


async def test_mode_battery_switch_to_discharge_is_ordered_over_ticks() -> None:
    from types import SimpleNamespace

    hass = _hass()
    st = {"number.chg": 600.0, "select.strat": "scheduled", "number.dis": 0.0}
    hass.states.get = lambda eid: SimpleNamespace(state=str(st[eid])) if eid in st else None
    pub = ActiveControlPublisher(hass, [_mode_device()])

    await pub.apply({"s": -400.0}, {"s": 50.0})  # tick 1: charge power non-zero → zero it
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.chg", "value": 0.0})]
    st["number.chg"] = 0.0

    hass.services.async_call.reset_mock()
    await pub.apply({"s": -400.0}, {"s": 50.0})  # tick 2: strategy wrong → switch
    assert _calls(hass) == [
        ("select", "select_option", {"entity_id": "select.strat", "option": "self_powered"})
    ]
    st["select.strat"] = "self_powered"

    hass.services.async_call.reset_mock()
    await pub.apply({"s": -400.0}, {"s": 50.0})  # tick 3: ready → set discharge power
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.dis", "value": 400.0})]


async def test_mode_battery_no_reswitch_when_direction_unchanged() -> None:
    from types import SimpleNamespace

    hass = _hass()
    # The device correctly reports the strategy we set → no re-assert.
    hass.states.get = lambda eid: (
        SimpleNamespace(state="scheduled") if eid == "select.strat" else None
    )
    pub = ActiveControlPublisher(hass, [_mode_device()])
    await pub.apply({"s": 600.0}, {"s": 50.0})  # switch to scheduled
    hass.services.async_call.reset_mock()
    await pub.apply({"s": 400.0}, {"s": 50.0})  # still charging, just less power
    # No opposite-zeroing, no strategy re-switch — only the charge power moves.
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.chg", "value": 400.0}),
    ]


async def test_mode_reasserts_strategy_when_device_reverts() -> None:
    # The STREAM drops energy_strategy back to self_powered on its own; SB must
    # re-assert "scheduled" each tick, else charging_power_limit is ignored by the
    # box (charge setpoint > PV yet the battery does nothing).
    from types import SimpleNamespace

    hass = _hass()
    hass.states.get = lambda eid: (
        SimpleNamespace(state="self_powered") if eid == "select.strat" else None
    )
    pub = ActiveControlPublisher(hass, [_mode_device()])
    await pub.apply({"s": 600.0}, {"s": 50.0})  # initial switch to scheduled
    hass.services.async_call.reset_mock()
    await pub.apply({"s": 600.0}, {"s": 50.0})  # device reverted → re-assert scheduled
    modes = [c for c in _calls(hass) if c[1] == "select_option"]
    assert modes == [
        ("select", "select_option", {"entity_id": "select.strat", "option": "scheduled"})
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


async def test_mode_charge_reasserts_zero_on_self_imposed_base_load() -> None:
    # The STREAM re-imposes its own base load (discharge) while charging: SB must
    # force it back to 0 each tick, else it charges and discharges at once.
    from types import SimpleNamespace

    hass = _hass()
    hass.states.get = lambda eid: SimpleNamespace(state="399") if eid == "number.dis" else None
    pub = ActiveControlPublisher(hass, [_mode_device()])
    await pub.apply({"s": 600.0}, {"s": 50.0})  # switch to charge (zeros discharge once)
    hass.services.async_call.reset_mock()
    await pub.apply({"s": 600.0}, {"s": 50.0})  # no switch, device shows 399 → re-zero
    zeroed = [
        c
        for c in _calls(hass)
        if c[2].get("entity_id") == "number.dis" and c[2].get("value") == 0.0
    ]
    assert zeroed


async def test_charge_setpoint_written_as_is() -> None:
    # The per-battery target is written as-is (no PV added, nothing divided): the
    # regulator's velocity-form loop self-discovers the right magnitude.
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity=None, charge_entity="number.chg_a")])
    await pub.apply({"a": 600.0}, {"a": 50.0})
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.chg_a", "value": 600.0})]


async def test_charge_setpoint_quantised_to_step() -> None:
    # The charge setpoint is rounded to _CHARGE_STEP_W (10 W) so a slow BLE box is
    # not spammed with sub-step PI ripple.
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity=None, charge_entity="number.chg_a")])
    await pub.apply({"a": 217.0}, {"a": 50.0})  # 217 → 220
    assert _calls(hass) == [("number", "set_value", {"entity_id": "number.chg_a", "value": 220.0})]


async def test_skips_write_to_unavailable_entity() -> None:
    # A BLE device that dropped off the bus (entity "unavailable") must not be
    # written to — it just spams "missing or not currently available" otherwise.
    from types import SimpleNamespace

    hass = _hass()
    hass.states.get = lambda eid: SimpleNamespace(state="unavailable")
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0}, {"a": 50.0})
    assert _calls(hass) == []


async def test_skips_pv_limit_write_to_unavailable_entity() -> None:
    from types import SimpleNamespace

    hass = _hass()
    hass.states.get = lambda eid: SimpleNamespace(state="unavailable")
    pub = ActiveControlPublisher(hass, [_mppt_device("pv", entity="number.pv_limit")])
    await pub.apply_pv_limits({"pv": 650.0})
    assert _calls(hass) == []


def _stream_like(name: str = "stream"):
    """A mode-switch (solar-first) battery: it modulates its own base-load setpoint."""
    return _device(name, entity="number.base_load", mode_entity="select.strategy")


def _state_map(overrides: dict[str, str]):
    """hass.states.get returning a per-entity state (with attributes for clamping)."""
    from types import SimpleNamespace

    def get(eid: str):
        return SimpleNamespace(state=overrides.get(eid, "0"), attributes={})

    return get


async def _armed_stream():
    """Publisher whose base-load setpoint has actually been written and latched.

    A mode-switch battery mutates one thing per tick, so the mode is driven first; the
    power write only lands once the select already reads the discharge option.
    """
    hass = _hass()
    hass.states.get = _state_map({"select.strategy": "discharge"})
    pub = ActiveControlPublisher(hass, [_stream_like()])
    await pub.apply({"stream": -275.0}, {"stream": 50.0})
    assert ("number", "set_value", {"entity_id": "number.base_load", "value": 275.0}) in _calls(
        hass
    ), "setup failed: the base-load setpoint was never written, so nothing is latched"
    return hass, pub


async def test_verify_leaves_a_setpoint_the_device_eased_down() -> None:
    # Observed live 2026-07-24 07:36-07:46: a STREAM in self_powered walks its base load
    # down toward the real house load (275 -> 82 W). Re-asserting our value fought that
    # regulation and sawtoothed the setpoint ~190 W every ~40 s. An eased-down value on a
    # device-modulated setpoint must be left alone.
    hass, pub = await _armed_stream()
    hass.states.get = _state_map({"select.strategy": "discharge", "number.base_load": "82"})
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert _calls(hass) == [], "re-asserted a value the device is legitimately modulating"


async def test_verify_still_rewrites_a_collapsed_setpoint() -> None:
    # The mitigation must not blind the check: a value that fell to ~0 is a lost or
    # cancelled write, not modulation, and is still re-asserted.
    hass, pub = await _armed_stream()
    hass.states.get = _state_map({"select.strategy": "discharge", "number.base_load": "0"})
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert ("number", "set_value", {"entity_id": "number.base_load", "value": 275.0}) in _calls(
        hass
    )


async def test_verify_still_rewrites_when_the_device_exceeds_the_command() -> None:
    # Overshoot is never "regulation we allow" — more output than asked can push export.
    hass, pub = await _armed_stream()
    hass.states.get = _state_map({"select.strategy": "discharge", "number.base_load": "900"})
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert ("number", "set_value", {"entity_id": "number.base_load", "value": 275.0}) in _calls(
        hass
    )


async def test_verify_pv_limit_still_rewrites_on_downward_drift() -> None:
    # A PV *limit* is not device-modulated: reading lower than commanded means the array
    # is over-restricted and we lose production — that must still be corrected.
    from types import SimpleNamespace

    hass = _hass()
    pub = ActiveControlPublisher(hass, [_mppt_device("pv", entity="number.pv_limit")])
    await pub.apply_pv_limits({"pv": 800.0})
    hass.states.get = lambda eid: SimpleNamespace(state="400", attributes={})
    hass.services.async_call.reset_mock()
    await pub.verify_writes()
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.pv_limit", "value": 800.0})
    ]
