"""Tests for fleet-target resolution helpers."""

import pytest

from custom_components.solarbalance.core.controllers.regulation import (
    apply_equaliser_offer,
    apply_slew_limit,
    predictive_steering_w,
    resolve_fleet_target_w,
)


@pytest.mark.parametrize(
    ("target", "offer", "expected"),
    [
        # Fleet charging from PV (+625); a +1200 offer forces a 1200 discharge.
        (625.0, 1200.0, -1200.0),
        # Already discharging more than the offer -> unchanged.
        (-1500.0, 1200.0, -1500.0),
        # Negative offer forces charge.
        (-100.0, -800.0, 800.0),
        (900.0, -800.0, 900.0),
        # No offer -> passthrough.
        (300.0, 0.0, 300.0),
    ],
)
def test_apply_equaliser_offer(target: float, offer: float, expected: float) -> None:
    assert apply_equaliser_offer(target, offer) == pytest.approx(expected)


def test_resolve_zi_owns_loop() -> None:
    out = resolve_fleet_target_w(
        zi_regulating=True,
        current_fleet_w=300.0,
        zi_correction_w=-50.0,
        absolute_target_w=999.0,  # ignored when ZI regulates
        steering_w=0.0,
    )
    assert out == 250.0


def test_resolve_absolute_when_not_regulating() -> None:
    out = resolve_fleet_target_w(
        zi_regulating=False,
        current_fleet_w=300.0,
        zi_correction_w=-50.0,
        absolute_target_w=800.0,
        steering_w=20.0,
    )
    assert out == 820.0


def test_slew_limit_clamps_change() -> None:
    assert apply_slew_limit(2000.0, 500.0, 800.0) == 1300.0
    assert apply_slew_limit(2000.0, None, 800.0) == 2000.0  # no previous
    assert apply_slew_limit(2000.0, 500.0, 0.0) == 2000.0  # disabled


def test_predictive_cheap_only_adds_charge() -> None:
    # Plan wants to charge more than the solar base, cheap window → grid-charge.
    assert (
        predictive_steering_w(
            base_target_w=200.0, planner_w=2000.0, is_cheap=True, is_expensive=False
        )
        == 1800.0
    )
    # Plan wants less charge than base in cheap window → no negative bias.
    assert (
        predictive_steering_w(
            base_target_w=2000.0, planner_w=200.0, is_cheap=True, is_expensive=False
        )
        == 0.0
    )


def test_predictive_expensive_only_adds_discharge() -> None:
    assert (
        predictive_steering_w(
            base_target_w=0.0, planner_w=-1500.0, is_cheap=False, is_expensive=True
        )
        == -1500.0
    )
    assert (
        predictive_steering_w(
            base_target_w=-1500.0, planner_w=0.0, is_cheap=False, is_expensive=True
        )
        == 0.0
    )


def test_predictive_inert_with_flat_tariff() -> None:
    # Neither cheap nor expensive (flat tariff) → no steering, ZI stays in control.
    assert (
        predictive_steering_w(
            base_target_w=100.0, planner_w=3000.0, is_cheap=False, is_expensive=False
        )
        == 0.0
    )
