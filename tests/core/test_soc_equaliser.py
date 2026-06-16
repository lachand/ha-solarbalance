"""Tests for the indirect SoC equaliser (proportional + slow-cadence offer)."""

import pytest

from custom_components.solarbalance.core.controllers.soc_equaliser import (
    SocEqualiserController,
    SocEqualiserResult,
)
from custom_components.solarbalance.core.models import BatteryRole, BatteryState


def _role(
    *,
    soc_min_pct: int = 10,
    soc_max_pct: int = 95,
    max_charge: int = 3000,
    max_discharge: int = 3000,
    ac_charge_limit_w: int | None = None,
) -> BatteryRole:
    return BatteryRole(
        capacity_kwh=5.0,
        max_charge_power_w=max_charge,
        max_discharge_power_w=max_discharge,
        soc_entity="sensor.auto_soc",
        power_entity="sensor.auto_power",
        soc_min_pct=soc_min_pct,
        soc_max_pct=soc_max_pct,
        controllable=False,
        ac_charge_limit_w=ac_charge_limit_w,
    )


def _state(name: str, soc: float, *, power_w: float = 0.0, available: bool = True) -> BatteryState:
    return BatteryState(device_name=name, soc_pct=soc, power_w=power_w, available=available)


def _run(
    ctrl: SocEqualiserController,
    *,
    fleet_soc: float,
    auto_soc: float,
    auto_power_w: float = 0.0,
    grid_w: float = 0.0,
    available_pv_w: float = 5000.0,
    ticks: int = 1,
) -> list[float]:
    """Step the controller ``ticks`` times with constant inputs, return offers.

    ``available_pv_w`` defaults high so the PV gate is open in most tests.
    """
    out: list[float] = []
    for _ in range(ticks):
        r = ctrl.step(
            controllable_states=[_state("a", fleet_soc)],
            uncontrollable_states={"auto": _state("auto", auto_soc, power_w=auto_power_w)},
            grid_w=grid_w,
            available_pv_w=available_pv_w,
        )
        out.append(r.grid_setpoint_bias_w)
    return out


# -- PV gate & cap (only redistribute solar) -------------------------------


def test_no_steering_below_pv_threshold() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())], step_w=150.0, cadence_ticks=1, adaptive_cadence=False, min_pv_w=200.0
    )
    out = _run(ctrl, fleet_soc=90.0, auto_soc=20.0, available_pv_w=150.0, ticks=5)
    assert out == [pytest.approx(0.0)] * 5  # no battery-to-battery transfer without sun


def test_offer_capped_at_available_pv() -> None:
    # Big SoC gap would want a large offer, but PV is only 400 W -> capped at 400.
    ctrl = SocEqualiserController(
        [("auto", _role())],
        step_w=600.0,
        cadence_ticks=1,
        adaptive_cadence=False,
        max_offer_w=2000.0,
        min_pv_w=200.0,
    )
    out = _run(ctrl, fleet_soc=95.0, auto_soc=10.0, available_pv_w=400.0, ticks=12)
    assert max(out) == pytest.approx(400.0)


# -- proportional offer (no integrator windup) -----------------------------


def test_offer_converges_to_proportional_target_and_holds() -> None:
    # error 5 %, kp 80 -> offer target 400 W. Steps are proportional to the
    # remaining gap; the offer approaches 400, settles and holds without ever
    # overshooting (an integrator would keep ramping past it).
    ctrl = SocEqualiserController(
        [("auto", _role())],
        kp_w_per_pct=80.0,
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=False,
        max_offer_w=1500.0,
    )
    out = _run(ctrl, fleet_soc=55.0, auto_soc=50.0, ticks=10)
    assert out == sorted(out)  # monotonically approaching
    assert max(out) <= 400.0 + 1e-6  # never overshoots the target
    assert out[-1] == pytest.approx(400.0)  # settled at the proportional target


def test_above_target_offers_negative() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())], step_w=150.0, cadence_ticks=1, adaptive_cadence=False
    )
    [bias] = _run(ctrl, fleet_soc=40.0, auto_soc=70.0)
    assert bias == pytest.approx(-150.0)


def test_offer_clamped_to_max() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())],
        max_offer_w=400.0,
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=False,
    )
    out = _run(ctrl, fleet_soc=95.0, auto_soc=10.0, ticks=10)
    assert max(out) == pytest.approx(400.0)


# -- slow cadence ----------------------------------------------------------


def test_offer_moves_only_every_cadence_ticks() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())], step_w=150.0, cadence_ticks=3, adaptive_cadence=False
    )
    out = _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=6)
    assert out == [
        pytest.approx(0.0),
        pytest.approx(0.0),
        pytest.approx(150.0),
        pytest.approx(150.0),
        pytest.approx(150.0),
        pytest.approx(300.0),
    ]


def test_adaptive_cadence_tracks_measured_lag() -> None:
    # The automatic battery responds 3 ticks after the offer first moves; the
    # controller learns lag=3 and widens the cadence to 2*lag=6.
    ctrl = SocEqualiserController(
        [("auto", _role())],
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=True,
        max_cadence_ticks=30,
    )
    powers = [0.0, 0.0, 0.0, 200.0]  # response appears on the 4th step
    result: SocEqualiserResult | None = None
    for p in powers:
        result = ctrl.step(
            controllable_states=[_state("a", 90.0)],
            uncontrollable_states={"auto": _state("auto", 20.0, power_w=p)},
            grid_w=0.0,
            available_pv_w=5000.0,
        )
    assert result is not None
    assert result.lag_ticks == pytest.approx(3.0)
    assert result.cadence_ticks == 6


# -- dead-time-aware back-off (fix #1) -------------------------------------


def test_export_with_responding_battery_is_not_a_leak() -> None:
    # Offer positive, grid exporting, but the automatic battery's power is rising
    # toward its target -> the ZI loop is executing the offer, not leaking: the
    # offer keeps growing instead of backing off.
    ctrl = SocEqualiserController(
        [("auto", _role())],
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=False,
        leak_persist_ticks=2,
    )
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=2)  # build offer to 300
    offers: list[float] = []
    for p in (200.0, 400.0, 600.0):  # auto power rising > 100 W/tick
        r = ctrl.step(
            controllable_states=[_state("a", 90.0)],
            uncontrollable_states={"auto": _state("auto", 20.0, power_w=p)},
            grid_w=-500.0,
            available_pv_w=5000.0,
        )
        offers.append(r.grid_setpoint_bias_w)
    assert offers == [pytest.approx(450.0), pytest.approx(600.0), pytest.approx(750.0)]


def test_persistent_export_with_flat_battery_backs_off() -> None:
    # Offer positive, grid exporting, automatic battery flat -> genuine leak:
    # after it persists past leak_persist the offer is backed off.
    ctrl = SocEqualiserController(
        [("auto", _role())],
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=False,
        leak_persist_ticks=2,
    )
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=2)  # build offer to 300
    out = _run(ctrl, fleet_soc=90.0, auto_soc=20.0, auto_power_w=0.0, grid_w=-500.0, ticks=4)
    assert out[0] == pytest.approx(300.0)  # suspected: held, not grown
    assert out[-1] < 200.0  # confirmed leak: backed off


# -- arming hysteresis (fix #3) --------------------------------------------


def test_stops_in_deadband_and_rearms_only_past_margin() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())],
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=False,
        soc_deadband_pct=2.0,
        rearm_margin_pct=1.0,
    )
    _run(ctrl, fleet_soc=70.0, auto_soc=50.0, ticks=3)  # armed, offer built up
    within = _run(ctrl, fleet_soc=51.5, auto_soc=50.0, ticks=2)  # |1.5| <= deadband -> stop
    assert within[-1] < within[0]  # decaying toward 0
    # |2.5| is past the deadband but below deadband+margin (3.0): stays stopped.
    margin = _run(ctrl, fleet_soc=52.5, auto_soc=50.0, ticks=2)
    assert margin[-1] <= margin[0]
    # |3.5| > deadband+margin -> re-arm and steer again.
    rearmed = _run(ctrl, fleet_soc=53.5, auto_soc=50.0, ticks=2)
    assert rearmed[-1] > 0.0


def test_decays_to_zero_within_deadband() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())],
        step_w=150.0,
        cadence_ticks=1,
        adaptive_cadence=False,
        soc_deadband_pct=2.0,
    )
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=2)  # offer 300
    out = _run(ctrl, fleet_soc=50.5, auto_soc=50.0, ticks=8)  # within deadband -> decay
    assert out == sorted(out, reverse=True)  # monotonically relaxing toward 0
    assert out[-1] == pytest.approx(0.0)  # reaches 0


# -- symmetric slew on reset (fix #3) --------------------------------------


def test_reset_is_rate_limited_not_a_jump() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())], step_w=150.0, cadence_ticks=1, adaptive_cadence=False
    )
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=2)  # offer 300
    # Controllable fleet disappears: the offer must slew toward 0, not snap to it.
    r = ctrl.step(
        controllable_states=[],
        uncontrollable_states={"auto": _state("auto", 20.0)},
        grid_w=0.0,
    )
    assert r.grid_setpoint_bias_w == pytest.approx(150.0)
    assert r.in_deadband is True


# -- SoC bounds ------------------------------------------------------------


def test_does_not_charge_above_auto_soc_max() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role(soc_max_pct=60))], step_w=150.0, cadence_ticks=1, adaptive_cadence=False
    )
    [bias] = _run(ctrl, fleet_soc=90.0, auto_soc=60.0)
    assert bias == 0.0


def test_does_not_discharge_below_auto_soc_min() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role(soc_min_pct=20))], step_w=150.0, cadence_ticks=1, adaptive_cadence=False
    )
    [bias] = _run(ctrl, fleet_soc=10.0, auto_soc=20.0)
    assert bias == 0.0


# -- availability ----------------------------------------------------------


def test_no_controllable_battery_is_noop() -> None:
    ctrl = SocEqualiserController([("auto", _role())], cadence_ticks=1)
    r = ctrl.step(
        controllable_states=[],
        uncontrollable_states={"auto": _state("auto", 50.0)},
        grid_w=0.0,
    )
    assert r.grid_setpoint_bias_w == pytest.approx(0.0)
    assert r.target_soc_pct is None
    assert r.in_deadband is True
    assert r.lag_ticks is None


def test_unavailable_uncontrollable_skipped() -> None:
    ctrl = SocEqualiserController(
        [("auto", _role())], step_w=150.0, cadence_ticks=1, adaptive_cadence=False
    )
    r = ctrl.step(
        controllable_states=[_state("a", 90.0)],
        uncontrollable_states={"auto": _state("auto", 50.0, available=False)},
        grid_w=0.0,
        available_pv_w=5000.0,
    )
    assert r.grid_setpoint_bias_w == 0.0
    assert r.in_deadband is True


@pytest.mark.parametrize(
    ("kp", "max_w", "deadband", "step", "cadence", "max_cadence", "rearm", "leak", "min_pv"),
    [
        (-1.0, 1500.0, 2.0, 150.0, 6, 30, 1.0, 3, 200.0),
        (80.0, -1.0, 2.0, 150.0, 6, 30, 1.0, 3, 200.0),
        (80.0, 1500.0, -1.0, 150.0, 6, 30, 1.0, 3, 200.0),
        (80.0, 1500.0, 2.0, 0.0, 6, 30, 1.0, 3, 200.0),
        (80.0, 1500.0, 2.0, 150.0, 0, 30, 1.0, 3, 200.0),
        (80.0, 1500.0, 2.0, 150.0, 6, 3, 1.0, 3, 200.0),
        (80.0, 1500.0, 2.0, 150.0, 6, 30, -1.0, 3, 200.0),
        (80.0, 1500.0, 2.0, 150.0, 6, 30, 1.0, 0, 200.0),
        (80.0, 1500.0, 2.0, 150.0, 6, 30, 1.0, 3, -1.0),
    ],
)
def test_invalid_params_rejected(
    kp: float,
    max_w: float,
    deadband: float,
    step: float,
    cadence: int,
    max_cadence: int,
    rearm: float,
    leak: int,
    min_pv: float,
) -> None:
    with pytest.raises(ValueError):
        SocEqualiserController(
            [("auto", _role())],
            kp_w_per_pct=kp,
            max_offer_w=max_w,
            soc_deadband_pct=deadband,
            step_w=step,
            cadence_ticks=cadence,
            max_cadence_ticks=max_cadence,
            rearm_margin_pct=rearm,
            leak_persist_ticks=leak,
            min_pv_w=min_pv,
        )
