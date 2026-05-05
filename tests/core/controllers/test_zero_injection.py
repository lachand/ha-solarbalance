"""Tests for the zero-injection PI controller."""

import pytest

from custom_components.solarbalance.core.controllers.zero_injection import (
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
        controller = ZeroInjectionController(kp=0.6, ki=0.0, hysteresis_w=50.0)
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
        controller = ZeroInjectionController(kp=0.6, ki=0.0, hysteresis_w=50.0)
        result = controller.step(
            grid_power_w=-500.0,
            setpoint_w=0.0,
            dt_s=10.0,
            state=ZeroInjectionState(),
        )
        assert result.correction_w == pytest.approx(300.0)

    def test_integral_accumulates_across_steps(self) -> None:
        controller = ZeroInjectionController(kp=0.0, ki=0.1, hysteresis_w=50.0)
        state = ZeroInjectionState()
        for _ in range(3):
            result = controller.step(
                grid_power_w=200.0,
                setpoint_w=0.0,
                dt_s=10.0,
                state=state,
            )
            state = result.new_state
        # Integral should grow each step (200 W × 10 s × 3 = 6000 W·s)
        assert state.integral_w_s == pytest.approx(6000.0)

    def test_integral_is_clamped(self) -> None:
        controller = ZeroInjectionController(
            kp=0.0, ki=1.0, hysteresis_w=10.0, integral_clamp_w_s=100.0
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
