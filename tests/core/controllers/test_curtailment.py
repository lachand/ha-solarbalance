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


# --------------------------------------- anticipatory pre-limit (forecast brake)


def test_preemptive_limit_lowers_without_any_measured_export() -> None:
    # The whole point: the reactive branch cannot move before an export is measured
    # (grid at setpoint here, batteries free). The forecast ceiling still brakes.
    c = _ctrl()
    r = c.step(
        pv_total_w=1000.0,
        grid_w=0.0,
        setpoint_w=0.0,
        batteries_saturated=False,
        preemptive_limit_w=400.0,
    )
    assert r.limit_total_w == 800.0  # one ramp step down (1000 - 200)
    assert r.curtailing is True
    assert r.preemptive is True


def test_preemptive_limit_descends_by_at_most_one_ramp_per_move() -> None:
    c = _ctrl()
    for expected in (800.0, 600.0, 400.0, 400.0):
        r = c.step(
            pv_total_w=1000.0,
            grid_w=0.0,
            setpoint_w=0.0,
            batteries_saturated=False,
            preemptive_limit_w=400.0,
        )
        assert r.limit_total_w == pytest.approx(expected)


def test_preemptive_limit_honours_the_settle_window() -> None:
    c = _ctrl(settle_ticks=3)
    first = c.step(
        pv_total_w=1000.0,
        grid_w=0.0,
        setpoint_w=0.0,
        batteries_saturated=False,
        preemptive_limit_w=400.0,
    )
    assert first.limit_total_w == 800.0
    # Held for the settle window — no second move yet.
    for _ in range(2):
        held = c.step(
            pv_total_w=1000.0,
            grid_w=0.0,
            setpoint_w=0.0,
            batteries_saturated=False,
            preemptive_limit_w=400.0,
        )
        assert held.limit_total_w == 800.0


def test_relax_cannot_climb_back_above_the_preemptive_ceiling() -> None:
    c = _ctrl()
    # Brake down to the ceiling.
    for _ in range(4):
        c.step(
            pv_total_w=1000.0,
            grid_w=0.0,
            setpoint_w=0.0,
            batteries_saturated=False,
            preemptive_limit_w=400.0,
        )
    assert c.limit_w == pytest.approx(400.0)
    # Importing hard (relax branch wants to raise) — but the ceiling still holds.
    r = c.step(
        pv_total_w=400.0,
        grid_w=500.0,
        setpoint_w=0.0,
        batteries_saturated=False,
        preemptive_limit_w=400.0,
    )
    assert r.limit_total_w == pytest.approx(400.0)


def test_measured_export_still_trims_below_the_preemptive_ceiling() -> None:
    # The two brakes compose as a min: a real export past the setpoint keeps biting.
    c = _ctrl()
    for _ in range(4):
        c.step(
            pv_total_w=1000.0,
            grid_w=0.0,
            setpoint_w=0.0,
            batteries_saturated=False,
            preemptive_limit_w=400.0,
        )
    assert c.limit_w == pytest.approx(400.0)
    r = c.step(
        pv_total_w=400.0,
        grid_w=-300.0,
        setpoint_w=0.0,
        batteries_saturated=True,
        preemptive_limit_w=400.0,
    )
    assert r.limit_total_w == pytest.approx(200.0)  # trimmed below the ceiling


def test_releasing_the_ceiling_lets_the_limit_relax_again() -> None:
    c = _ctrl()
    for _ in range(4):
        c.step(
            pv_total_w=1000.0,
            grid_w=0.0,
            setpoint_w=0.0,
            batteries_saturated=False,
            preemptive_limit_w=400.0,
        )
    assert c.limit_w == pytest.approx(400.0)
    # Forecast says the surplus fits again → no ceiling; relax back toward peak.
    r = c.step(
        pv_total_w=400.0,
        grid_w=100.0,
        setpoint_w=0.0,
        batteries_saturated=False,
        preemptive_limit_w=None,
    )
    assert r.limit_total_w == pytest.approx(600.0)
    assert r.preemptive is False
