"""Tests for the EV fast-charge assist controller."""

from custom_components.solarbalance.core.controllers.ev_fast_charge import (
    evaluate_fast_charge,
)
from custom_components.solarbalance.core.controllers.evening_shed import BatteryChargeNeed


def _need(soc: float, soc_max: float = 100.0, cap: float = 10.0) -> BatteryChargeNeed:
    return BatteryChargeNeed(soc_pct=soc, soc_max_pct=soc_max, usable_capacity_kwh=cap)


def _eval(**kw):
    base = {
        "enabled": True,
        "surplus_w": 1000.0,  # below the 2300 efficient floor
        "min_charge_w": 2300.0,
        "max_charge_w": 3680.0,
        "batteries": [_need(80.0)],  # 2 kWh deficit
        "avg_soc_pct": 80.0,
        "assist_floor_soc_pct": 40.0,
        "remaining_pv_kwh": 10.0,
        "remaining_hours": 4.0,
        "talon_w": 300.0,
        "pause_when_inefficient": True,
    }
    base.update(kw)
    return evaluate_fast_charge(**base)


def test_disabled_no_override() -> None:
    d = _eval(enabled=False)
    assert d.override is False and d.reason == "disabled"


def test_efficient_surplus_no_override() -> None:
    d = _eval(surplus_w=2500.0)  # >= min_charge_w
    assert d.override is False and d.reason == "surplus_efficient"


def test_assist_to_efficient_floor_when_recoverable() -> None:
    d = _eval()  # surplus 1000 < 2300, soc 80 > 40, plenty of PV ahead
    assert d.override is True
    assert d.target_w == 2300.0
    assert d.reason == "assist"
    assert d.gate_ok is True


def test_pause_when_soc_below_floor() -> None:
    d = _eval(avg_soc_pct=30.0)  # below 40 floor
    assert d.override is True and d.target_w == 0.0
    assert d.reason == "pause_low_soc"


def test_pause_when_not_recoverable() -> None:
    # Little PV left + big deficit → gate fails → pause.
    d = _eval(remaining_pv_kwh=1.0, batteries=[_need(50.0)])
    assert d.gate_ok is False
    assert d.override is True and d.target_w == 0.0 and d.reason == "pause_unrecoverable"


def test_slow_charge_fallback_when_pause_disabled() -> None:
    d = _eval(remaining_pv_kwh=1.0, batteries=[_need(50.0)], pause_when_inefficient=False)
    assert d.override is False and d.reason == "slow_charge_fallback"


def test_full_batteries_gate_ok() -> None:
    # No deficit → gate trivially OK → assist.
    d = _eval(batteries=[_need(100.0)], remaining_pv_kwh=0.5)
    assert d.gate_ok is True and d.reason == "assist"
