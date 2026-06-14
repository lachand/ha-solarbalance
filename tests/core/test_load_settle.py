"""Tests for the anti-yoyo load-settle helper."""

from custom_components.solarbalance.core.controllers.load_settle import (
    SettleState,
    advance_settle,
    arm_settle,
    load_drop_w,
)


def test_load_drop_counts_only_decreases() -> None:
    prev = {"car": 2300.0, "wh": 2000.0, "fridge": 100.0}
    current = {"car": 0.0, "wh": 2000.0, "fridge": 150.0}  # car off, fridge up
    assert load_drop_w(prev, current) == 2300.0  # only the car drop counts


def test_arm_settle_triggers_on_big_drop() -> None:
    state = arm_settle(
        prev_loads={"car": 2300.0},
        current_loads={"car": 0.0},
        settle_ticks=2,
        min_drop_w=300.0,
    )
    assert state is not None
    assert state.ticks_remaining == 2
    assert state.feedforward_w == 2300.0
    assert state.active


def test_arm_settle_ignores_small_drop() -> None:
    assert (
        arm_settle(
            prev_loads={"x": 200.0},
            current_loads={"x": 0.0},
            settle_ticks=2,
            min_drop_w=300.0,
        )
        is None
    )


def test_arm_settle_disabled_when_ticks_zero() -> None:
    assert (
        arm_settle(
            prev_loads={"car": 3000.0},
            current_loads={"car": 0.0},
            settle_ticks=0,
            min_drop_w=300.0,
        )
        is None
    )


def test_advance_settle_feeds_forward_once_then_freezes() -> None:
    state = SettleState(ticks_remaining=2, feedforward_w=2300.0)
    # First tick: emit the feed-forward.
    ff1, state = advance_settle(state)
    assert ff1 == 2300.0
    assert state.ticks_remaining == 1
    assert state.feedforward_w == 0.0  # cleared so it fires only once
    # Second tick: pure freeze, no feed-forward.
    ff2, state = advance_settle(state)
    assert ff2 == 0.0
    assert state.ticks_remaining == 0
    assert not state.active
    # Once expired, advancing is a no-op.
    ff3, state = advance_settle(state)
    assert ff3 == 0.0
    assert not state.active
