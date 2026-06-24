"""Tests for the real-time PV-drop detector."""

from custom_components.solarbalance.core.controllers.pv_drop import PvDropDetector


def test_first_sample_is_not_a_drop() -> None:
    assert PvDropDetector().update(2000.0) == 0.0


def test_rising_pv_is_never_a_drop() -> None:
    d = PvDropDetector()
    d.update(500.0)
    assert d.update(2000.0) == 0.0


def test_sudden_drop_above_threshold_is_reported() -> None:
    d = PvDropDetector(threshold_w=300.0)
    d.update(2000.0)
    drop = d.update(500.0)  # reference ~2000 → drop ~1500
    assert drop > 1000.0


def test_small_dip_below_threshold_is_ignored() -> None:
    d = PvDropDetector(threshold_w=300.0)
    d.update(2000.0)
    assert d.update(1850.0) == 0.0  # 150 W dip < threshold


def test_gradual_decline_does_not_trigger() -> None:
    d = PvDropDetector(threshold_w=300.0)
    pv = 2000.0
    fired = False
    for _ in range(60):  # decline ~50 W/step (a slow evening ramp-down)
        pv = max(0.0, pv - 50.0)
        if d.update(pv) > 0.0:
            fired = True
    assert not fired


def test_reference_recovers_after_pv_returns() -> None:
    d = PvDropDetector(threshold_w=300.0)
    d.update(2000.0)
    assert d.update(400.0) > 0.0  # cloud
    assert d.update(2000.0) == 0.0  # sun back → rise, no drop
