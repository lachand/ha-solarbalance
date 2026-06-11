"""Tests for the indirect SoC equaliser controller (adaptive, AC-bounded)."""

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
    ticks: int = 1,
) -> list[float]:
    """Run ``ticks`` steps with constant inputs, returning the steering each tick."""
    out: list[float] = []
    for _ in range(ticks):
        r = ctrl.step(
            controllable_states=[_state("a", fleet_soc)],
            uncontrollable_states={"auto": _state("auto", auto_soc, power_w=auto_power_w)},
        )
        out.append(r.steering_w)
    return out


def test_first_tick_charge_is_small_probe_step() -> None:
    ctrl = SocEqualiserController([("auto", _role())], probe_step_w=150.0)
    [steering] = _run(ctrl, fleet_soc=80.0, auto_soc=50.0)
    assert steering == pytest.approx(-150.0)  # negative = discharge fleet = charge auto


def test_first_tick_discharge_is_small_probe_step() -> None:
    ctrl = SocEqualiserController([("auto", _role())], probe_step_w=150.0)
    [steering] = _run(ctrl, fleet_soc=40.0, auto_soc=70.0)
    assert steering == pytest.approx(150.0)  # positive = charge fleet = discharge auto


def test_allowance_grows_geometrically_while_following() -> None:
    ctrl = SocEqualiserController([("auto", _role())], probe_step_w=100.0)
    out = _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=4)
    # 100 → 150 → 225 → 337.5, all far below kp*error and the AC cap.
    assert out == [
        pytest.approx(-100.0),
        pytest.approx(-150.0),
        pytest.approx(-225.0),
        pytest.approx(-337.5),
    ]


def test_allowance_capped_by_ac_charge_limit() -> None:
    ctrl = SocEqualiserController([("auto", _role(ac_charge_limit_w=400))], probe_step_w=150.0)
    out = _run(ctrl, fleet_soc=95.0, auto_soc=10.0, ticks=10)
    assert max(abs(s) for s in out) == pytest.approx(400.0)


def test_discharge_capped_by_max_discharge_power() -> None:
    ctrl = SocEqualiserController([("auto", _role(max_discharge=300))], probe_step_w=150.0)
    out = _run(ctrl, fleet_soc=10.0, auto_soc=95.0, ticks=10)
    assert max(out) == pytest.approx(300.0)


def test_wrong_way_resets_allowance() -> None:
    ctrl = SocEqualiserController([("auto", _role())], probe_step_w=100.0)
    # Grow a few ticks while the auto cooperates (idle / charging).
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=3)
    # Now the auto discharges hard while we still want to charge it → reset.
    [steering] = _run(ctrl, fleet_soc=90.0, auto_soc=20.0, auto_power_w=-500.0)
    assert steering == pytest.approx(-100.0)


def test_direction_reversal_resets_allowance() -> None:
    ctrl = SocEqualiserController([("auto", _role())], probe_step_w=100.0)
    _run(ctrl, fleet_soc=90.0, auto_soc=20.0, ticks=3)  # charging direction grows
    # Auto now above fleet mean → discharge direction, allowance back to probe.
    [steering] = _run(ctrl, fleet_soc=20.0, auto_soc=90.0)
    assert steering == pytest.approx(100.0)


def test_kp_bounds_steady_state_demand_near_target() -> None:
    # Small SoC error: kp*error = 80*3 = 240 caps the demand once allowance grows.
    ctrl = SocEqualiserController(
        [("auto", _role())], kp_w_per_pct=80.0, probe_step_w=100.0, soc_deadband_pct=1.0
    )
    out = _run(ctrl, fleet_soc=53.0, auto_soc=50.0, ticks=8)
    assert max(abs(s) for s in out) == pytest.approx(240.0)


def test_aggregate_clamped_to_max_steering() -> None:
    ctrl = SocEqualiserController([("auto", _role())], max_steering_w=500.0, probe_step_w=150.0)
    out = _run(ctrl, fleet_soc=95.0, auto_soc=10.0, ticks=10)
    assert max(abs(s) for s in out) == pytest.approx(500.0)


def test_within_deadband_yields_no_steering() -> None:
    ctrl = SocEqualiserController([("auto", _role())], soc_deadband_pct=2.0)
    [steering] = _run(ctrl, fleet_soc=51.0, auto_soc=50.0)
    assert steering == 0.0


def test_no_controllable_battery_is_noop() -> None:
    ctrl = SocEqualiserController([("auto", _role())])
    r = ctrl.step(
        controllable_states=[],
        uncontrollable_states={"auto": _state("auto", 50.0)},
    )
    assert r == SocEqualiserResult(steering_w=0.0, target_soc_pct=None, in_deadband=True)


def test_does_not_charge_above_auto_soc_max() -> None:
    ctrl = SocEqualiserController([("auto", _role(soc_max_pct=60))])
    [steering] = _run(ctrl, fleet_soc=90.0, auto_soc=60.0)
    assert steering == 0.0


def test_does_not_discharge_below_auto_soc_min() -> None:
    ctrl = SocEqualiserController([("auto", _role(soc_min_pct=20))])
    [steering] = _run(ctrl, fleet_soc=10.0, auto_soc=20.0)
    assert steering == 0.0


def test_unavailable_uncontrollable_skipped() -> None:
    ctrl = SocEqualiserController([("auto", _role())])
    r = ctrl.step(
        controllable_states=[_state("a", 90.0)],
        uncontrollable_states={"auto": _state("auto", 50.0, available=False)},
    )
    assert r.steering_w == 0.0
    assert r.in_deadband is True


@pytest.mark.parametrize(
    ("kp", "max_w", "deadband", "probe"),
    [
        (-1.0, 1500.0, 2.0, 150.0),
        (80.0, -1.0, 2.0, 150.0),
        (80.0, 1500.0, -1.0, 150.0),
        (80.0, 1500.0, 2.0, 0.0),
    ],
)
def test_invalid_params_rejected(kp: float, max_w: float, deadband: float, probe: float) -> None:
    with pytest.raises(ValueError):
        SocEqualiserController(
            [("auto", _role())],
            kp_w_per_pct=kp,
            max_steering_w=max_w,
            soc_deadband_pct=deadband,
            probe_step_w=probe,
        )
