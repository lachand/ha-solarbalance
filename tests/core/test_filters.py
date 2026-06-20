"""Tests for the rolling-median filter."""

import pytest

from custom_components.solarbalance.core.filters import AdaptiveVolatilityDamper, RollingMedian


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


def test_damper_first_value_passthrough() -> None:
    d = AdaptiveVolatilityDamper()
    assert d.update(123.0) == 123.0


def test_damper_steady_signal_is_transparent() -> None:
    d = AdaptiveVolatilityDamper()
    out = [d.update(100.0) for _ in range(20)]
    # A steady signal stays at its value (volatility ~0, light smoothing converges).
    assert out[-1] == pytest.approx(100.0, abs=0.5)
    assert d.volatility_w == pytest.approx(0.0, abs=0.5)


def test_damper_smooths_a_swinging_signal() -> None:
    d = AdaptiveVolatilityDamper(calm_alpha=0.8, volatile_alpha=0.1, ref_w=300.0)
    # A square-wave motor load 0<->600 builds volatility, so the output settles
    # near the average (~300) instead of swinging the full 0..600.
    out = 0.0
    for i in range(60):
        out = d.update(600.0 if i % 2 else 0.0)
    assert d.volatility_w > 300.0  # detected as volatile
    assert 150.0 < out < 450.0  # output tracks the average, not the extremes


def test_damper_responsive_when_calm() -> None:
    d = AdaptiveVolatilityDamper(calm_alpha=0.8)
    for _ in range(10):
        d.update(100.0)
    # A genuine slow step (low tick-to-tick volatility) is followed quickly.
    d.update(300.0)
    assert d.update(300.0) > 250.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"calm_alpha": 1.2},
        {"volatile_alpha": 0.0},
        {"volatile_alpha": 0.9, "calm_alpha": 0.5},
        {"ref_w": 0.0},
        {"volatility_alpha": 0.0},
    ],
)
def test_damper_invalid_params_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        AdaptiveVolatilityDamper(**kwargs)
