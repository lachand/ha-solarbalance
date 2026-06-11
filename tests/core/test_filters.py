"""Tests for the rolling-median filter."""

import pytest

from custom_components.solarbalance.core.filters import RollingMedian


def test_window_one_is_passthrough() -> None:
    f = RollingMedian(1)
    assert [f.update(x) for x in (5.0, -200.0, 3.0)] == [5.0, -200.0, 3.0]


def test_rejects_single_sample_spike() -> None:
    f = RollingMedian(3)
    f.update(100.0)
    f.update(110.0)
    # A 2000 W glitch among ~100 W readings is rejected by the median.
    assert f.update(2000.0) == 110.0


def test_tracks_sustained_change_with_small_lag() -> None:
    f = RollingMedian(3)
    for x in (100.0, 100.0, 100.0):
        f.update(x)
    f.update(500.0)  # median(100,100,500)=100
    assert f.update(500.0) == 500.0  # median(100,500,500)=500 → caught up


def test_invalid_window_rejected() -> None:
    with pytest.raises(ValueError):
        RollingMedian(0)
