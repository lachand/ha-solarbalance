"""Tests for the evening battery-priority load-shedding controller."""

from custom_components.solarbalance.core.controllers.evening_shed import (
    BatteryChargeNeed,
    evaluate_evening_shed,
)


def _need(soc: float, soc_max: float = 100.0, cap: float = 10.0) -> BatteryChargeNeed:
    return BatteryChargeNeed(soc_pct=soc, soc_max_pct=soc_max, usable_capacity_kwh=cap)


def _eval(**kw):
    base = {
        "enabled": True,
        "batteries": [_need(50.0)],  # 5 kWh deficit
        "remaining_pv_kwh": 10.0,
        "remaining_hours": 3.0,
        "talon_w": 300.0,
        "sheddable": [("water_heater", 2000.0), ("small", 100.0)],
        "min_shed_power_w": 500.0,
    }
    base.update(kw)
    return evaluate_evening_shed(**base)


def test_disabled_never_sheds() -> None:
    d = _eval(enabled=False)
    assert d.active is False and d.reason == "disabled"


def test_no_production_left_does_not_shed() -> None:
    d = _eval(remaining_pv_kwh=0.0)
    assert d.active is False and d.reason == "no_production_left"


def test_full_batteries_do_not_shed() -> None:
    d = _eval(batteries=[_need(100.0)])
    assert d.active is False and d.reason == "batteries_full"


def test_surplus_sufficient_does_not_shed() -> None:
    # 20 kWh PV, talon 300W*3h=0.9 kWh → 19.1 available > 5 kWh deficit.
    d = _eval(remaining_pv_kwh=20.0)
    assert d.active is False and d.reason == "surplus_sufficient"


def test_sheds_only_big_interruptible_loads() -> None:
    # 3 kWh PV - 0.9 baseline = 2.1 available < 5 kWh deficit → shed.
    d = _eval(remaining_pv_kwh=3.0)
    assert d.active is True
    assert d.shed_load_names == frozenset({"water_heater"})  # small (100W) excluded
    assert d.reason == "shedding"


def test_deficit_aggregates_across_batteries() -> None:
    d = _eval(batteries=[_need(50.0, cap=10.0), _need(80.0, cap=10.0)], remaining_pv_kwh=3.0)
    assert d.deficit_kwh == 7.0  # 5 + 2


def test_no_sheddable_load_marks_reason_but_inactive() -> None:
    d = _eval(remaining_pv_kwh=3.0, sheddable=[("tiny", 100.0)])
    assert d.active is False and d.reason == "no_sheddable_load"


def test_baseline_reduces_available_pv() -> None:
    # 6 kWh PV, big talon 1500W*4h=6 kWh → 0 available < 5 deficit → shed.
    d = _eval(remaining_pv_kwh=6.0, remaining_hours=4.0, talon_w=1500.0)
    assert d.pv_for_charge_kwh == 0.0
    assert d.active is True
