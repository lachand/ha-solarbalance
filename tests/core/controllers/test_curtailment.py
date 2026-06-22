"""Tests for the PV curtailment controller."""

import pytest

from custom_components.solarbalance.core.controllers.curtailment import (
    CurtailmentController,
    distribute_pv_limit,
)


def _ctrl(peak: float = 1000.0, settle_ticks: int = 1) -> CurtailmentController:
    # settle_ticks=1 → a move is allowed every step (per-step unit assertions).
    return CurtailmentController(
        peak_total_w=peak, deadband_w=50.0, ramp_w=200.0, settle_ticks=settle_ticks
    )


def test_starts_unrestricted() -> None:
    c = _ctrl()
    assert c.limit_w == 1000.0


def test_no_curtail_when_batteries_can_absorb() -> None:
    # Exporting but batteries not saturated → leave PV alone (batteries store it).
    c = _ctrl()
    r = c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=False)
    assert r.curtailing is False
    assert r.limit_total_w == 1000.0


def test_curtails_gradually_when_saturated_and_exporting() -> None:
    # Each move trims at most ramp_w (200), converging instead of slamming to 0.
    c = _ctrl()
    r = c.step(pv_total_w=1000.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(800.0)  # 1000 - min(500, 200)
    assert r.curtailing is True
    r = c.step(pv_total_w=800.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(600.0)  # another 200


def test_small_excess_step_is_not_capped() -> None:
    c = _ctrl()
    r = c.step(pv_total_w=1000.0, grid_w=-120.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(880.0)  # 1000 - min(120, 200)


def test_holds_limit_at_balance() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=True)  # → 800
    r = c.step(pv_total_w=800.0, grid_w=0.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(800.0)  # balanced → hold


def test_relaxes_when_importing() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)  # → 800
    r = c.step(pv_total_w=800.0, grid_w=300.0, setpoint_w=0.0, batteries_saturated=False)
    assert r.limit_total_w == pytest.approx(1000.0)  # 800 + 200 ramp


def test_relaxes_back_to_peak_when_batteries_free() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)  # → 800
    c.step(pv_total_w=800.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)  # → 600
    # batteries no longer saturated → relax even at balance
    c.step(pv_total_w=600.0, grid_w=0.0, setpoint_w=0.0, batteries_saturated=False)  # → 800
    r = c.step(pv_total_w=800.0, grid_w=0.0, setpoint_w=0.0, batteries_saturated=False)  # → 1000
    assert r.limit_total_w == pytest.approx(1000.0)
    assert r.curtailing is False


def test_settle_window_holds_between_moves() -> None:
    c = _ctrl(settle_ticks=3)
    r = c.step(pv_total_w=1000.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(800.0)  # first move allowed
    # next two ticks fall inside the settle window → hold
    for _ in range(2):
        r = c.step(pv_total_w=800.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)
        assert r.limit_total_w == pytest.approx(800.0)
    # settle elapsed → may move again
    r = c.step(pv_total_w=800.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(600.0)


def test_reset_releases_curtailment() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-500.0, setpoint_w=0.0, batteries_saturated=True)
    c.reset_to_unlimited()
    assert c.limit_w == 1000.0


def test_distribute_proportional_to_peak() -> None:
    limits = distribute_pv_limit(600.0, [("a", 400.0), ("b", 200.0)])
    assert limits == {"a": pytest.approx(400.0), "b": pytest.approx(200.0)}


def test_distribute_zero_peak_is_zero() -> None:
    assert distribute_pv_limit(600.0, [("a", 0.0)]) == {"a": 0.0}


@pytest.mark.parametrize(
    ("peak", "deadband", "ramp"),
    [(-1.0, 50.0, 200.0), (1000.0, -1.0, 200.0), (1000.0, 50.0, 0.0)],
)
def test_invalid_params_rejected(peak: float, deadband: float, ramp: float) -> None:
    with pytest.raises(ValueError):
        CurtailmentController(peak_total_w=peak, deadband_w=deadband, ramp_w=ramp)
