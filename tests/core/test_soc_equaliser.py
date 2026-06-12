"""Tests for the cascaded indirect SoC equaliser (grid-setpoint offer)."""

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
    max_charge: int = 2000,
    max_discharge: int = 2000,
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
    ticks: int = 1,
) -> list[float]:
    out: list[float] = []
    for _ in range(ticks):
        r = ctrl.step(
            controllable_states=[_state("a", fleet_soc)],
            uncontrollable_states={"auto": _state("auto", auto_soc, power_w=auto_power_w)},
            grid_w=grid_w,
        )
        out.append(r.grid_setpoint_bias_w)
    return out


def test_below_target_offers_surplus_ramped_by_step() -> None:
    ctrl = SocEqualiserController([("auto", _role())], step_w=150.0)
    out = _run(ctrl, fleet_soc=80.0, auto_soc=50.0, ticks=3)
    assert out == [pytest.approx(150.0), pytest.approx(300.0), pytest.approx(450.0)]


def test_above_target_offers_deficit() -> None:
    ctrl = SocEqualiserController([("auto", _role())], step_w=150.0)
    [bias] = _run(ctrl, fleet_soc=40.0, auto_soc=70.0)
    assert bias == pytest.approx(-150.0)


def test_offer_clamped_to_max() -> None:
    ctrl = SocEqualiserController([("auto", _role())], max_offer_w=400.0, step_w=150.0)
    out = _run(ctrl, fleet_soc=95.0, auto_soc=10.0, ticks=10)
    assert max(out) == pytest.approx(400.0)


def test_holds_when_auto_reaches_target() -> None:
    # kp 80, error 10 % → fa_target 800 W. Once the auto charges 800 W, err≈0.
    ctrl = SocEqualiserController([("auto", _role())], kp_w_per_pct=80.0, step_w=150.0)
    _run(ctrl, fleet_soc=60.0, auto_soc=50.0, ticks=3)  # ramp up
    before = _run(ctrl, fleet_soc=60.0, auto_soc=50.0, auto_power_w=800.0)[0]
    after = _run(ctrl, fleet_soc=60.0, auto_soc=50.0, auto_power_w=800.0)[0]
    assert after == pytest.approx(before)  # err≈0 → offer holds


def test_backs_off_when_surplus_leaks_to_grid() -> None:
    ctrl = SocEqualiserController([("auto", _role())], step_w=150.0)
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=2)  # offer = 300, auto not charging
    # Now the grid is exporting (surplus not absorbed) → offer backs off.
    [bias] = _run(ctrl, fleet_soc=90.0, auto_soc=20.0, grid_w=-500.0)
    assert bias == pytest.approx(150.0)  # 300 - 150


def test_decays_to_zero_within_deadband() -> None:
    ctrl = SocEqualiserController([("auto", _role())], step_w=150.0, soc_deadband_pct=2.0)
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=2)  # offer = 300
    out = _run(ctrl, fleet_soc=50.5, auto_soc=50.0, ticks=3)  # within deadband → decay
    assert out == [pytest.approx(150.0), pytest.approx(0.0), pytest.approx(0.0)]


def test_does_not_charge_above_auto_soc_max() -> None:
    ctrl = SocEqualiserController([("auto", _role(soc_max_pct=60))], step_w=150.0)
    [bias] = _run(ctrl, fleet_soc=90.0, auto_soc=60.0)
    assert bias == 0.0


def test_does_not_discharge_below_auto_soc_min() -> None:
    ctrl = SocEqualiserController([("auto", _role(soc_min_pct=20))], step_w=150.0)
    [bias] = _run(ctrl, fleet_soc=10.0, auto_soc=20.0)
    assert bias == 0.0


def test_no_controllable_battery_is_noop() -> None:
    ctrl = SocEqualiserController([("auto", _role())])
    r = ctrl.step(
        controllable_states=[],
        uncontrollable_states={"auto": _state("auto", 50.0)},
        grid_w=0.0,
    )
    assert r == SocEqualiserResult(grid_setpoint_bias_w=0.0, target_soc_pct=None, in_deadband=True)


def test_unavailable_uncontrollable_skipped() -> None:
    ctrl = SocEqualiserController([("auto", _role())], step_w=150.0)
    r = ctrl.step(
        controllable_states=[_state("a", 90.0)],
        uncontrollable_states={"auto": _state("auto", 50.0, available=False)},
        grid_w=0.0,
    )
    assert r.grid_setpoint_bias_w == 0.0
    assert r.in_deadband is True


@pytest.mark.parametrize(
    ("kp", "max_w", "deadband", "step"),
    [
        (-1.0, 1500.0, 2.0, 150.0),
        (80.0, -1.0, 2.0, 150.0),
        (80.0, 1500.0, -1.0, 150.0),
        (80.0, 1500.0, 2.0, 0.0),
    ],
)
def test_invalid_params_rejected(kp: float, max_w: float, deadband: float, step: float) -> None:
    with pytest.raises(ValueError):
        SocEqualiserController(
            [("auto", _role())],
            kp_w_per_pct=kp,
            max_offer_w=max_w,
            soc_deadband_pct=deadband,
            step_w=step,
        )
