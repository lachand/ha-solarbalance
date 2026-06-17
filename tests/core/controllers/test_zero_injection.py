"""Tests for the zero-injection PI controller."""

import pytest

from custom_components.solarbalance.core.controllers.zero_injection import (
    PerPhaseZeroInjectionController,
    PerPhaseZeroInjectionState,
    ZeroInjectionController,
    ZeroInjectionState,
)


class TestZeroInjectionController:
    @pytest.mark.parametrize(
        ("kwarg", "value"),
        [
            ("hysteresis_w", -10.0),
            ("integral_clamp_w_s", 0.0),
            ("integral_clamp_w_s", -1.0),
        ],
    )
    def test_invalid_construction(self, kwarg: str, value: float) -> None:
        with pytest.raises(ValueError):
            ZeroInjectionController(**{kwarg: value})

    def test_dt_must_be_positive(self) -> None:
        controller = ZeroInjectionController()
        with pytest.raises(ValueError, match="dt_s"):
            controller.step(
                grid_power_w=100.0,
                setpoint_w=0.0,
                dt_s=0.0,
                state=ZeroInjectionState(),
            )

    def test_within_deadband_returns_no_correction(self) -> None:
        controller = ZeroInjectionController(hysteresis_w=50.0)
        result = controller.step(
            grid_power_w=30.0,
            setpoint_w=0.0,
            dt_s=10.0,
            state=ZeroInjectionState(),
        )
        assert result.in_deadband
        assert result.correction_w == 0.0
        assert result.new_state.integral_w_s == 0.0

    def test_over_import_yields_negative_correction(self) -> None:
        # Importing more than wanted: we should reduce charge / increase discharge.
        controller = ZeroInjectionController(kp_min=0.6, kp_max=0.6, ki=0.0, hysteresis_w=50.0)
        result = controller.step(
            grid_power_w=500.0,
            setpoint_w=0.0,
            dt_s=10.0,
            state=ZeroInjectionState(),
        )
        assert not result.in_deadband
        assert result.correction_w == pytest.approx(-300.0)

    def test_over_export_yields_positive_correction(self) -> None:
        # Exporting (grid_power < 0): we should charge more.
        controller = ZeroInjectionController(kp_min=0.6, kp_max=0.6, ki=0.0, hysteresis_w=50.0)
        result = controller.step(
            grid_power_w=-500.0,
            setpoint_w=0.0,
            dt_s=10.0,
            state=ZeroInjectionState(),
        )
        assert result.correction_w == pytest.approx(300.0)

    def test_progressive_gain_gentle_near_deadband_full_at_knee(self) -> None:
        # kp ramps from kp_min (just past hysteresis) to kp_max (at/above knee).
        ctrl = ZeroInjectionController(
            kp_min=0.2, kp_max=0.8, knee_w=600.0, ki=0.0, hysteresis_w=50.0
        )

        def corr(grid: float) -> float:
            return ctrl.step(
                grid_power_w=grid, setpoint_w=0.0, dt_s=10.0, state=ZeroInjectionState()
            ).correction_w

        def expected(err: float) -> float:
            frac = min(1.0, max(0.0, (abs(err) - 50.0) / (600.0 - 50.0)))
            return -(0.2 + 0.6 * frac) * err

        # Ramps from kp_min near the deadband to kp_max at/above the knee.
        for grid in (60.0, 110.0, 325.0, 600.0, 1000.0):
            assert corr(grid) == pytest.approx(expected(grid))
        # Endpoints: kp_max (0.8) at and beyond the knee.
        assert corr(600.0) == pytest.approx(-480.0)
        assert corr(1000.0) == pytest.approx(-800.0)
        # Effective gain is gentler near zero than far from it.
        assert abs(corr(60.0)) / 60.0 < abs(corr(1000.0)) / 1000.0

    def test_knee_must_exceed_hysteresis(self) -> None:
        with pytest.raises(ValueError, match="knee_w"):
            ZeroInjectionController(knee_w=40.0, hysteresis_w=50.0)

    def test_integral_accumulates_across_steps(self) -> None:
        controller = ZeroInjectionController(kp_min=0.0, kp_max=0.0, ki=0.1, hysteresis_w=50.0)
        state = ZeroInjectionState()
        for _ in range(3):
            result = controller.step(
                grid_power_w=200.0,
                setpoint_w=0.0,
                dt_s=10.0,
                state=state,
            )
            state = result.new_state
        # Integral should grow each step (200 W x 10 s x 3 = 6000 W*s)
        assert state.integral_w_s == pytest.approx(6000.0)

    def test_integral_is_clamped(self) -> None:
        controller = ZeroInjectionController(
            kp_min=0.0, kp_max=0.0, ki=1.0, hysteresis_w=10.0, integral_clamp_w_s=100.0
        )
        state = ZeroInjectionState()
        for _ in range(50):
            result = controller.step(
                grid_power_w=1000.0,
                setpoint_w=0.0,
                dt_s=10.0,
                state=state,
            )
            state = result.new_state
        assert state.integral_w_s == pytest.approx(100.0)


class TestPerPhaseZeroInjectionController:
    def test_all_deadband_reports_in_deadband(self) -> None:
        ctrl = PerPhaseZeroInjectionController(hysteresis_w=50.0)
        result = ctrl.step(
            grid_l1_w=10.0,
            grid_l2_w=-5.0,
            grid_l3_w=20.0,
            setpoint_l1_w=0.0,
            setpoint_l2_w=0.0,
            setpoint_l3_w=0.0,
            dt_s=10.0,
            state=PerPhaseZeroInjectionState(),
        )
        assert result.in_deadband
        assert result.correction_w == pytest.approx(0.0)

    def test_partial_deadband_not_in_deadband(self) -> None:
        ctrl = PerPhaseZeroInjectionController(kp_min=0.6, kp_max=0.6, ki=0.0, hysteresis_w=50.0)
        result = ctrl.step(
            grid_l1_w=10.0,
            grid_l2_w=500.0,
            grid_l3_w=10.0,
            setpoint_l1_w=0.0,
            setpoint_l2_w=0.0,
            setpoint_l3_w=0.0,
            dt_s=10.0,
            state=PerPhaseZeroInjectionState(),
        )
        assert not result.in_deadband
        assert result.in_deadband_l1
        assert not result.in_deadband_l2
        assert result.in_deadband_l3

    def test_aggregate_correction_is_sum_of_phases(self) -> None:
        ctrl = PerPhaseZeroInjectionController(kp_min=0.6, kp_max=0.6, ki=0.0, hysteresis_w=0.0)
        result = ctrl.step(
            grid_l1_w=100.0,
            grid_l2_w=200.0,
            grid_l3_w=300.0,
            setpoint_l1_w=0.0,
            setpoint_l2_w=0.0,
            setpoint_l3_w=0.0,
            dt_s=10.0,
            state=PerPhaseZeroInjectionState(),
        )
        # kp=0.6: corrections = -60, -120, -180 → total -360
        assert result.correction_l1_w == pytest.approx(-60.0)
        assert result.correction_l2_w == pytest.approx(-120.0)
        assert result.correction_l3_w == pytest.approx(-180.0)
        assert result.correction_w == pytest.approx(-360.0)

    def test_state_updated_per_phase_independently(self) -> None:
        ctrl = PerPhaseZeroInjectionController(kp_min=0.0, kp_max=0.0, ki=0.1, hysteresis_w=0.0)
        state = PerPhaseZeroInjectionState()
        result = ctrl.step(
            grid_l1_w=200.0,
            grid_l2_w=0.0,
            grid_l3_w=0.0,
            setpoint_l1_w=0.0,
            setpoint_l2_w=0.0,
            setpoint_l3_w=0.0,
            dt_s=10.0,
            state=state,
        )
        # L1 should accumulate integral (200 x 10 = 2000 W*s), L2/L3 stay at 0
        assert result.new_state.l1.integral_w_s == pytest.approx(2000.0)
        assert result.new_state.l2.integral_w_s == pytest.approx(0.0)
        assert result.new_state.l3.integral_w_s == pytest.approx(0.0)
