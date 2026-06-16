"""Tests for the supervisory regulation auto-tuner."""

import pytest

from custom_components.solarbalance.core.autotuner import RegulationAutoTuner


def _feed(tuner: RegulationAutoTuner, signals: list[float]) -> float:
    out = 0.0
    for s in signals:
        out = tuner.step(s)
    return out


def test_calm_signal_keeps_default() -> None:
    # A steady ramp = no reversals -> value stays at default.
    t = RegulationAutoTuner(default=0.6, min_value=0.15, window_ticks=10, adapt_every=5)
    out = _feed(t, [float(i) for i in range(40)])
    assert out == pytest.approx(0.6)


def test_oscillation_loosens_toward_floor() -> None:
    t = RegulationAutoTuner(
        default=0.6, min_value=0.15, window_ticks=10, adapt_every=5, loosen_factor=0.8
    )
    osc = [100.0 if i % 2 == 0 else -100.0 for i in range(60)]
    out = _feed(t, osc)
    assert out < 0.6  # loosened
    assert out >= 0.15  # never below the floor


def test_loosen_then_restore_when_calm() -> None:
    t = RegulationAutoTuner(
        default=0.6,
        min_value=0.15,
        window_ticks=10,
        adapt_every=5,
        loosen_factor=0.8,
        tighten_factor=1.1,
    )
    loosened = _feed(t, [100.0 if i % 2 == 0 else -100.0 for i in range(60)])
    restored = _feed(t, [float(i) for i in range(60)])  # calm ramp
    assert loosened < 0.6
    assert restored > loosened  # restored upward
    assert restored <= 0.6  # never above default


def test_oscillation_detected_around_a_nonzero_offset() -> None:
    # Offer-style signal: always positive but alternating -> reversals detected.
    t = RegulationAutoTuner(default=600.0, min_value=100.0, window_ticks=10, adapt_every=5)
    out = _feed(t, [1500.0 if i % 2 == 0 else 1400.0 for i in range(60)])
    assert out < 600.0


def test_reset_restores_default() -> None:
    t = RegulationAutoTuner(default=0.6, min_value=0.15, window_ticks=10, adapt_every=5)
    _feed(t, [100.0 if i % 2 == 0 else -100.0 for i in range(60)])
    t.reset()
    assert t.value == pytest.approx(0.6)


@pytest.mark.parametrize(
    ("default", "min_value", "window", "adapt", "loosen", "tighten", "olow", "ohigh"),
    [
        (0.6, 0.0, 10, 5, 0.8, 1.1, 1, 6),  # min_value <= 0
        (0.6, 0.7, 10, 5, 0.8, 1.1, 1, 6),  # min_value > default
        (0.6, 0.15, 1, 5, 0.8, 1.1, 1, 6),  # window too small
        (0.6, 0.15, 10, 5, 1.2, 1.1, 1, 6),  # loosen >= 1
        (0.6, 0.15, 10, 5, 0.8, 0.9, 1, 6),  # tighten <= 1
        (0.6, 0.15, 10, 5, 0.8, 1.1, 6, 6),  # osc_low >= osc_high
    ],
)
def test_invalid_params_rejected(
    default: float,
    min_value: float,
    window: int,
    adapt: int,
    loosen: float,
    tighten: float,
    olow: int,
    ohigh: int,
) -> None:
    with pytest.raises(ValueError):
        RegulationAutoTuner(
            default=default,
            min_value=min_value,
            window_ticks=window,
            adapt_every=adapt,
            loosen_factor=loosen,
            tighten_factor=tighten,
            osc_low=olow,
            osc_high=ohigh,
        )
