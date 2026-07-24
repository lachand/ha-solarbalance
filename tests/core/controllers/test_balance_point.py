"""Tests for the balance-point hysteresis (two thresholds instead of one)."""

from custom_components.solarbalance.core.controllers.balance_point import (
    BalancePointState,
    balance_band,
)


def _call(**kw):
    base = {
        "enabled": True,
        "error_w": 0.0,
        "base_hysteresis_w": 50.0,
        "actuator_lag_s": 30.0,
        "tick_s": 10.0,
        "state": BalancePointState(),
    }
    base.update(kw)
    return balance_band(**base)  # type: ignore[arg-type]


def test_disabled_never_holds_anything() -> None:
    """It touches control, so off means bit-for-bit the previous behaviour."""
    res = _call(enabled=False, error_w=5.0)
    assert res.settled is False
    assert res.reason == "disabled"
    assert res.exit_import_w == res.exit_export_w == res.enter_w


def test_a_small_error_settles_the_loop() -> None:
    res = _call(error_w=20.0)
    assert res.settled is True
    assert res.reason == "settling"


def test_a_large_error_regulates_as_before() -> None:
    res = _call(error_w=400.0)
    assert res.settled is False
    assert res.reason == "regulating"


def test_the_error_that_used_to_dither_now_holds() -> None:
    """The bug, stated directly.

    With one threshold, an error hovering either side of 50 W flips the loop
    between regulating and idle on every tick — and each flip is a real command
    to hardware that will not answer for 30 s.
    """
    state = BalancePointState()
    decisions = []
    for error_w in [48.0, 52.0, 47.0, 55.0, 49.0, 53.0]:
        res = _call(error_w=error_w, state=state)
        state = res.new_state
        decisions.append(res.settled)

    assert decisions[0] is True, "it settles on the first small error"
    assert all(decisions), "and stays settled — 55 W is inside the widened band"


def test_leaving_the_band_takes_more_than_entering_it() -> None:
    """The definition of hysteresis, and the reason the dither stops."""
    settled = _call(error_w=20.0)
    assert settled.settled is True

    still_in = _call(error_w=70.0, state=settled.new_state)
    assert still_in.settled is True, "70 W is past the entry band but inside the exit one"

    out = _call(error_w=120.0, state=settled.new_state)
    assert out.settled is False
    assert out.reason == "resumed"


def test_a_slow_actuator_widens_the_band_and_a_fast_one_does_not() -> None:
    """The widening is the lag's doing, so hardware that answers gets no slack."""
    slow = _call(actuator_lag_s=30.0)
    instant = _call(actuator_lag_s=0.0)

    assert slow.exit_import_w > slow.enter_w
    assert instant.exit_import_w == instant.enter_w, "no lag, no widening"


def test_the_band_cannot_grow_without_limit() -> None:
    """A wide band is a blind loop; blindness is worse than a little dither."""
    absurd = _call(actuator_lag_s=3600.0)
    assert absurd.exit_import_w <= _call().enter_w * 3.0


def test_export_never_gets_the_extra_tolerance() -> None:
    """Zero-injection exists to stop exporting; slack on that side defeats it.

    An extra 50 W of import for a few seconds costs a fraction of a centime. The
    same 50 W of export is the failure the whole controller is built to prevent.
    """
    settled = _call(error_w=10.0)
    assert settled.exit_export_w == settled.enter_w
    assert settled.exit_import_w > settled.exit_export_w

    # Symmetric magnitudes, opposite signs: the export one must break the hold.
    magnitude = settled.enter_w + 20.0
    importing = _call(error_w=magnitude, state=settled.new_state)
    exporting = _call(error_w=-magnitude, state=settled.new_state)

    assert importing.settled is True
    assert exporting.settled is False, "an export excursion resumes regulation at once"


def test_a_zero_deadband_disables_the_mechanism() -> None:
    """Someone who set the deadband to zero asked for no deadband."""
    res = _call(base_hysteresis_w=0.0, error_w=0.0)
    assert res.settled is False
    assert res.reason == "disabled"


def test_a_missing_tick_interval_is_treated_as_no_lag() -> None:
    """Rather than dividing by zero and widening the band on nonsense."""
    res = _call(tick_s=0.0, actuator_lag_s=30.0)
    assert res.exit_import_w == res.enter_w


def test_a_negative_deadband_is_not_taken_at_face_value() -> None:
    res = _call(base_hysteresis_w=-50.0, error_w=0.0)
    assert res.reason == "disabled"
    assert res.settled is False


def test_the_hold_releases_and_re_arms() -> None:
    """A full cycle: settle, hold, a real excursion, then settle again."""
    res = _call(error_w=10.0)
    assert res.settled is True
    res = _call(error_w=600.0, state=res.new_state)
    assert res.settled is False and res.reason == "resumed"
    res = _call(error_w=500.0, state=res.new_state)
    assert res.reason == "regulating"
    res = _call(error_w=15.0, state=res.new_state)
    assert res.settled is True and res.reason == "settling"
