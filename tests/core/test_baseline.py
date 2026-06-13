"""Tests for the night-window baseline (talon) estimator."""

from datetime import date, time

from custom_components.solarbalance.core.baseline import NightBaselineEstimator


def _feed(est: NightBaselineEstimator, d: date, samples: list[tuple[time, float]]) -> None:
    for t, w in samples:
        est.update(local_time=t, local_date=d, baseline_w=w)


def test_talon_none_before_first_window_closes() -> None:
    est = NightBaselineEstimator()
    _feed(est, date(2026, 6, 13), [(time(3, 0), 300.0), (time(3, 30), 320.0)])
    assert est.talon_w is None  # still inside window, not finalised


def test_talon_finalised_when_window_closes() -> None:
    est = NightBaselineEstimator(window_start_h=2, window_end_h=5)
    d = date(2026, 6, 13)
    _feed(est, d, [(time(2, 30), 200.0), (time(3, 30), 300.0), (time(4, 30), 400.0)])
    assert est.talon_w is None
    est.update(local_time=time(5, 1), local_date=d, baseline_w=1500.0)  # window closed
    assert est.talon_w == 300.0  # mean of 200/300/400, daytime spike ignored


def test_negative_baseline_clamped() -> None:
    est = NightBaselineEstimator()
    d = date(2026, 6, 13)
    _feed(est, d, [(time(3, 0), -50.0), (time(3, 30), 100.0)])
    est.update(local_time=time(6, 0), local_date=d, baseline_w=0.0)
    assert est.talon_w == 50.0  # mean of 0 (clamped) and 100


def test_talon_held_until_next_night() -> None:
    est = NightBaselineEstimator()
    d = date(2026, 6, 13)
    _feed(est, d, [(time(3, 0), 250.0)])
    est.update(local_time=time(6, 0), local_date=d, baseline_w=900.0)
    assert est.talon_w == 250.0
    # Daytime samples do not change it.
    est.update(local_time=time(14, 0), local_date=d, baseline_w=2000.0)
    assert est.talon_w == 250.0


def test_overnight_window() -> None:
    est = NightBaselineEstimator(window_start_h=22, window_end_h=5)
    assert est._in_window(time(23, 0))
    assert est._in_window(time(3, 0))
    assert not est._in_window(time(12, 0))


def test_restore_seeds_talon() -> None:
    est = NightBaselineEstimator()
    est.restore(275.0)
    assert est.talon_w == 275.0
