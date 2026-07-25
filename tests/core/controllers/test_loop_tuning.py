"""Tests for the actuator-lag-calibrated proportional gain (D1)."""

from custom_components.solarbalance.core.controllers.loop_tuning import tuned_kp


def test_a_one_tick_actuator_keeps_the_full_gain() -> None:
    # Answers within a tick: nothing to derate, identical to today's behaviour.
    assert tuned_kp(base_kp=0.6, actuator_lag_s=10.0, tick_s=10.0) == 0.6


def test_a_faster_than_a_tick_actuator_is_not_boosted() -> None:
    # The gain is a ceiling: a quick actuator never gets *more* than configured.
    assert tuned_kp(base_kp=0.6, actuator_lag_s=2.0, tick_s=10.0) == 0.6


def test_a_slow_actuator_lowers_the_gain() -> None:
    # 30 s lag against a 10 s tick = 3 commands in flight -> a third of the gain.
    kp = tuned_kp(base_kp=0.6, actuator_lag_s=30.0, tick_s=10.0)
    assert abs(kp - 0.2) < 1e-9


def test_a_slower_actuator_lowers_it_further() -> None:
    fast = tuned_kp(base_kp=0.6, actuator_lag_s=20.0, tick_s=10.0)
    slow = tuned_kp(base_kp=0.6, actuator_lag_s=40.0, tick_s=10.0)
    assert slow < fast < 0.6


def test_the_derate_has_a_floor() -> None:
    # However slow, the gain never collapses to near zero — a loop that cannot
    # correct is its own failure mode.
    kp = tuned_kp(base_kp=0.6, actuator_lag_s=3600.0, tick_s=10.0)
    assert kp == 0.6 * 0.25


def test_it_never_exceeds_the_configured_gain() -> None:
    for lag in (0.0, 5.0, 15.0, 60.0, 600.0):
        assert tuned_kp(base_kp=0.5, actuator_lag_s=lag, tick_s=10.0) <= 0.5


def test_unusable_inputs_return_the_base_gain() -> None:
    assert tuned_kp(base_kp=0.6, actuator_lag_s=0.0, tick_s=10.0) == 0.6
    assert tuned_kp(base_kp=0.6, actuator_lag_s=30.0, tick_s=0.0) == 0.6
    assert tuned_kp(base_kp=0.0, actuator_lag_s=30.0, tick_s=10.0) == 0.0
