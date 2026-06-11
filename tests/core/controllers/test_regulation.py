"""Tests for fleet-target resolution and slew limiting."""

import pytest

from custom_components.solarbalance.core.controllers.regulation import (
    apply_slew_limit,
    resolve_fleet_target_w,
)


class TestResolveFleetTarget:
    def test_zi_regulating_uses_current_power_plus_correction(self) -> None:
        # Fleet currently discharging 300 W, PI asks for +500 → target -300+500.
        target = resolve_fleet_target_w(
            zi_regulating=True,
            current_fleet_w=-300.0,
            zi_correction_w=500.0,
            absolute_target_w=9999.0,  # must be ignored
            steering_w=0.0,
        )
        assert target == pytest.approx(200.0)

    def test_zi_not_regulating_uses_absolute_target(self) -> None:
        target = resolve_fleet_target_w(
            zi_regulating=False,
            current_fleet_w=-300.0,
            zi_correction_w=500.0,  # must be ignored
            absolute_target_w=1200.0,
            steering_w=0.0,
        )
        assert target == pytest.approx(1200.0)

    @pytest.mark.parametrize("zi_regulating", [True, False])
    def test_steering_is_always_added(self, zi_regulating: bool) -> None:
        target = resolve_fleet_target_w(
            zi_regulating=zi_regulating,
            current_fleet_w=0.0,
            zi_correction_w=0.0,
            absolute_target_w=0.0,
            steering_w=-150.0,
        )
        assert target == pytest.approx(-150.0)


class TestSlewLimit:
    def test_no_previous_command_passes_through(self) -> None:
        assert apply_slew_limit(2000.0, None, 800.0) == 2000.0

    def test_disabled_when_max_ramp_zero(self) -> None:
        assert apply_slew_limit(2000.0, 0.0, 0.0) == 2000.0

    def test_clamps_rising_step(self) -> None:
        assert apply_slew_limit(2000.0, 100.0, 800.0) == pytest.approx(900.0)

    def test_clamps_falling_step(self) -> None:
        assert apply_slew_limit(-2000.0, 100.0, 800.0) == pytest.approx(-700.0)

    def test_small_change_within_limit_unchanged(self) -> None:
        assert apply_slew_limit(300.0, 100.0, 800.0) == pytest.approx(300.0)

    def test_oscillation_is_damped_over_ticks(self) -> None:
        # A command oscillating between +2000 and -2000 is ramp-limited so the
        # actual command crawls instead of slamming between extremes.
        last = 0.0
        commands = []
        for desired in (2000.0, -2000.0, 2000.0, -2000.0):
            last = apply_slew_limit(desired, last, 800.0)
            commands.append(last)
        assert commands == [
            pytest.approx(800.0),
            pytest.approx(0.0),
            pytest.approx(800.0),
            pytest.approx(0.0),
        ]
