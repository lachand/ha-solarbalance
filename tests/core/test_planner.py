"""Tests for the predictive multi-horizon scheduler (V2)."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.solarbalance.core.planner import (
    BatteryConstraints,
    ForecastSlot,
    PredictiveScheduler,
)


def _bat(
    *,
    capacity_kwh: float = 10.0,
    max_charge_w: float = 3000.0,
    max_discharge_w: float = 3000.0,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 95.0,
    eta: float = 1.0,
) -> BatteryConstraints:
    return BatteryConstraints(
        capacity_kwh=capacity_kwh,
        max_charge_w=max_charge_w,
        max_discharge_w=max_discharge_w,
        soc_min_pct=soc_min_pct,
        soc_max_pct=soc_max_pct,
        round_trip_efficiency=eta,
    )


def _slot(
    hour: int,
    net_load_w: float,
    import_price: float = 0.20,
    export_price: float = 0.10,
) -> ForecastSlot:
    return ForecastSlot(
        start=datetime(2026, 5, 4, hour, tzinfo=UTC),
        duration_s=3600.0,
        net_load_w=net_load_w,
        import_price=import_price,
        export_price=export_price,
    )


class TestPlanningResult:
    def test_empty_slots_returns_zero_cost(self) -> None:
        sched = PredictiveScheduler(_bat()).plan((), current_soc_pct=50.0)
        assert sched.total_cost_eur == 0.0
        assert sched.schedule == ()

    def test_first_setpoint_w_from_first_slot(self) -> None:
        sched = PredictiveScheduler(_bat()).plan((_slot(0, 500.0),), current_soc_pct=50.0)
        assert sched.first_setpoint_w == sched.schedule[0].battery_power_w

    def test_horizon_start_end_match_slots(self) -> None:
        slots = (_slot(0, 0.0), _slot(1, 0.0))
        sched = PredictiveScheduler(_bat()).plan(slots, current_soc_pct=50.0)
        assert sched.horizon_start == slots[0].start
        assert sched.horizon_end == slots[-1].start + timedelta(seconds=3600)


class TestSocConstraints:
    def test_soc_never_below_min(self) -> None:
        """Planner must not discharge below soc_min_pct."""
        bat = _bat(soc_min_pct=20.0)
        # Heavy discharge pressure: net_load is very negative (big surplus)
        # but battery starts low; planner should keep SoC above 20%.
        slots = tuple(_slot(h, -5000.0) for h in range(4))
        sched = PredictiveScheduler(bat).plan(slots, current_soc_pct=25.0)
        for s in sched.schedule:
            assert s.soc_end_pct >= bat.soc_min_pct - 0.1

    def test_soc_never_above_max(self) -> None:
        """Planner must not charge above soc_max_pct."""
        bat = _bat(soc_max_pct=80.0)
        slots = tuple(_slot(h, 5000.0, import_price=0.30) for h in range(4))
        sched = PredictiveScheduler(bat).plan(slots, current_soc_pct=70.0)
        for s in sched.schedule:
            assert s.soc_end_pct <= bat.soc_max_pct + 0.1


class TestCostOptimisation:
    def test_discharges_during_expensive_import(self) -> None:
        """At high import price the planner should use the battery (discharge)."""
        bat = _bat()
        # Single slot: net_load positive (need to import) with expensive price.
        slot = _slot(12, net_load_w=2000.0, import_price=0.60)
        sched = PredictiveScheduler(bat, n_soc_steps=30, n_power_steps=10).plan(
            (slot,), current_soc_pct=80.0
        )
        # Battery should discharge (negative power) to reduce grid import cost.
        assert sched.schedule[0].battery_power_w <= 0.0

    def test_charges_during_cheap_surplus(self) -> None:
        """With negative net load (surplus PV) and low export price the planner
        should prefer charging over exporting."""
        bat = _bat()
        # Surplus production, low export price → charging saves for later
        slot = _slot(12, net_load_w=-3000.0, import_price=0.20, export_price=0.05)
        sched = PredictiveScheduler(bat, n_soc_steps=30, n_power_steps=10).plan(
            (slot,), current_soc_pct=10.0
        )
        assert sched.schedule[0].battery_power_w >= 0.0

    def test_total_cost_cheaper_with_battery_than_without(self) -> None:
        """Cost with battery should be <= cost without battery (idle = 0 W)."""
        bat = _bat(eta=0.95)
        # Morning cheap import, afternoon expensive import
        slots = (
            _slot(6, net_load_w=1000.0, import_price=0.10),  # cheap: charge
            _slot(18, net_load_w=1500.0, import_price=0.40),  # expensive: discharge
        )
        sched = PredictiveScheduler(bat, n_soc_steps=40, n_power_steps=15).plan(
            slots, current_soc_pct=30.0
        )
        # Reference cost: battery idle (all met by grid)
        cost_no_bat = sum(
            s.net_load_w / 1000.0 * (s.duration_s / 3600.0) * s.import_price for s in slots
        )
        assert sched.total_cost_eur <= cost_no_bat + 1e-4  # allow small numerical slack


class TestScheduleShape:
    def test_schedule_length_matches_slots(self) -> None:
        n = 8
        slots = tuple(_slot(h, 500.0) for h in range(n))
        sched = PredictiveScheduler(_bat()).plan(slots, current_soc_pct=50.0)
        assert len(sched.schedule) == n

    def test_schedule_slot_starts_match_input(self) -> None:
        slots = tuple(_slot(h, 0.0) for h in range(6))
        sched = PredictiveScheduler(_bat()).plan(slots, current_soc_pct=50.0)
        for i, s in enumerate(sched.schedule):
            assert s.start == slots[i].start

    def test_expected_grid_w_consistent(self) -> None:
        """expected_grid_w should equal net_load_w + battery_power_w."""
        slots = tuple(_slot(h, float(h * 100)) for h in range(6))
        sched = PredictiveScheduler(_bat(), n_soc_steps=20).plan(slots, current_soc_pct=50.0)
        for s_in, s_out in zip(slots, sched.schedule, strict=False):
            expected = s_in.net_load_w + s_out.battery_power_w
            assert s_out.expected_grid_w == pytest.approx(expected, abs=1e-3)
