"""Tests for the PV curtailment controller."""

import pytest

from custom_components.solarbalance.core.controllers.curtailment import (
    CurtailmentController,
    distribute_pv_limit,
)


def _ctrl(peak: float = 1000.0) -> CurtailmentController:
    return CurtailmentController(peak_total_w=peak, deadband_w=50.0, ramp_w=200.0)


def test_starts_unrestricted() -> None:
    c = _ctrl()
    assert c.limit_w == 1000.0


def test_no_curtail_when_batteries_can_absorb() -> None:
    # Exporting but batteries not saturated → leave PV alone (batteries store it).
    c = _ctrl()
    r = c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=False)
    assert r.curtailing is False
    assert r.limit_total_w == 1000.0


def test_curtails_excess_when_saturated_and_exporting() -> None:
    c = _ctrl()
    r = c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(700.0)  # 1000 - 300 export
    assert r.curtailing is True


def test_holds_limit_at_balance() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=True)  # → 700
    r = c.step(pv_total_w=700.0, grid_w=0.0, setpoint_w=0.0, batteries_saturated=True)
    assert r.limit_total_w == pytest.approx(700.0)  # balanced → hold


def test_relaxes_when_importing() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=True)  # → 700
    r = c.step(pv_total_w=700.0, grid_w=200.0, setpoint_w=0.0, batteries_saturated=False)
    assert r.limit_total_w == pytest.approx(900.0)  # 700 + 200 ramp


def test_relaxes_back_to_peak_when_batteries_free() -> None:
    c = _ctrl()
    c.step(pv_total_w=1000.0, grid_w=-300.0, setpoint_w=0.0, batteries_saturated=True)  # → 700
    # batteries no longer saturated → relax even at balance
    c.step(pv_total_w=700.0, grid_w=0.0, setpoint_w=0.0, batteries_saturated=False)  # → 900
    r = c.step(pv_total_w=900.0, grid_w=0.0, setpoint_w=0.0, batteries_saturated=False)  # → 1000
    assert r.limit_total_w == pytest.approx(1000.0)
    assert r.curtailing is False


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
