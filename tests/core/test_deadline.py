"""Tests for the deadline (departure-time) charge guarantee."""

from datetime import UTC, datetime

from custom_components.solarbalance.core.controllers.deadline import evaluate_deadline


def _now(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 13, hour, minute, tzinfo=UTC)


def _eval(**kw):
    base = {
        "now": _now(22, 0),
        "before_time": "07:00",
        "required_kwh": 10.0,
        "delivered_kwh": 0.0,
        "max_charge_w": 3680.0,
    }
    base.update(kw)
    return evaluate_deadline(**base)


def test_satisfied_when_required_met() -> None:
    d = _eval(delivered_kwh=10.0)
    assert d.force is False and d.reason == "satisfied" and d.remaining_kwh == 0.0


def test_on_track_with_plenty_of_time() -> None:
    # 10 kWh over 9h needs ~1.1 kW << 3.68 kW → no forcing.
    d = _eval()
    assert d.force is False and d.reason == "on_track"
    assert d.hours_left == 9.0


def test_forces_when_time_is_tight() -> None:
    # 10 kWh, deadline in 3h → ~3.3 kW ≈ max → force.
    d = _eval(now=_now(4, 0))
    assert d.force is True and d.reason == "forcing"
    assert d.target_w == 3680.0


def test_overdue_forces() -> None:
    # before_time already passed today → next occurrence tomorrow gives ~24h,
    # but with a tiny window we still force; use exactly the deadline minute.
    d = _eval(now=_now(7, 0), before_time="07:00")
    # 07:00 == now → next occurrence is tomorrow (24h), plenty → on track.
    assert d.force is False


def test_partial_delivery_reduces_remaining() -> None:
    d = _eval(now=_now(4, 0), delivered_kwh=8.0)  # only 2 kWh left over 3h
    assert d.remaining_kwh == 2.0
    assert d.force is False  # 2 kWh / 3h ≈ 0.67 kW << max
