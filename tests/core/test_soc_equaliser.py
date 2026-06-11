"""Tests for the indirect SoC equaliser controller."""

import pytest

from custom_components.solarbalance.core.controllers.soc_equaliser import (
    SocEqualiserController,
    SocEqualiserResult,
)
from custom_components.solarbalance.core.models import BatteryRole, BatteryState


def _role(*, soc_min_pct: int = 10, soc_max_pct: int = 95) -> BatteryRole:
    return BatteryRole(
        capacity_kwh=5.0,
        max_charge_power_w=2000,
        max_discharge_power_w=2000,
        soc_entity="sensor.auto_soc",
        power_entity="sensor.auto_power",
        soc_min_pct=soc_min_pct,
        soc_max_pct=soc_max_pct,
        controllable=False,
    )


def _state(name: str, soc: float, *, available: bool = True) -> BatteryState:
    return BatteryState(device_name=name, soc_pct=soc, power_w=0.0, available=available)


def test_below_target_steers_negative_to_charge() -> None:
    """An automatic battery below the fleet mean is charged via negative bias."""
    ctrl = SocEqualiserController([("auto", _role())], kp_w_per_pct=80.0, max_steering_w=5000.0)
    result = ctrl.step(
        controllable_states=[_state("a", 80.0), _state("b", 80.0)],
        uncontrollable_states={"auto": _state("auto", 50.0)},
    )
    assert result.target_soc_pct == pytest.approx(80.0)
    assert result.steering_w == pytest.approx(-80.0 * 30.0)
    assert result.in_deadband is False


def test_above_target_steers_positive_to_discharge() -> None:
    """An automatic battery above the fleet mean is discharged via positive bias."""
    ctrl = SocEqualiserController([("auto", _role())], kp_w_per_pct=80.0, max_steering_w=5000.0)
    result = ctrl.step(
        controllable_states=[_state("a", 40.0), _state("b", 40.0)],
        uncontrollable_states={"auto": _state("auto", 70.0)},
    )
    assert result.steering_w == pytest.approx(80.0 * 30.0)


def test_steering_clamped_to_max() -> None:
    """Large SoC errors saturate at max_steering_w."""
    ctrl = SocEqualiserController([("auto", _role())], kp_w_per_pct=80.0, max_steering_w=500.0)
    result = ctrl.step(
        controllable_states=[_state("a", 95.0)],
        uncontrollable_states={"auto": _state("auto", 10.0)},
    )
    assert result.steering_w == pytest.approx(-500.0)


def test_within_deadband_yields_no_steering() -> None:
    ctrl = SocEqualiserController([("auto", _role())], kp_w_per_pct=80.0, soc_deadband_pct=2.0)
    result = ctrl.step(
        controllable_states=[_state("a", 51.0)],
        uncontrollable_states={"auto": _state("auto", 50.0)},
    )
    assert result.steering_w == 0.0
    assert result.in_deadband is True


def test_no_controllable_battery_is_noop() -> None:
    ctrl = SocEqualiserController([("auto", _role())])
    result = ctrl.step(
        controllable_states=[],
        uncontrollable_states={"auto": _state("auto", 50.0)},
    )
    assert result == SocEqualiserResult(steering_w=0.0, target_soc_pct=None, in_deadband=True)


def test_unavailable_controllable_excluded_from_target() -> None:
    ctrl = SocEqualiserController([("auto", _role())], kp_w_per_pct=10.0)
    result = ctrl.step(
        controllable_states=[_state("a", 90.0), _state("b", 50.0, available=False)],
        uncontrollable_states={"auto": _state("auto", 50.0)},
    )
    assert result.target_soc_pct == pytest.approx(90.0)


def test_does_not_charge_above_auto_soc_max() -> None:
    """Below-fleet but already at its own ceiling → no charge steering."""
    ctrl = SocEqualiserController([("auto", _role(soc_max_pct=60))])
    result = ctrl.step(
        controllable_states=[_state("a", 90.0)],
        uncontrollable_states={"auto": _state("auto", 60.0)},
    )
    assert result.steering_w == 0.0


def test_does_not_discharge_below_auto_soc_min() -> None:
    ctrl = SocEqualiserController([("auto", _role(soc_min_pct=20))])
    result = ctrl.step(
        controllable_states=[_state("a", 10.0)],
        uncontrollable_states={"auto": _state("auto", 20.0)},
    )
    assert result.steering_w == 0.0


def test_unavailable_uncontrollable_skipped() -> None:
    ctrl = SocEqualiserController([("auto", _role())])
    result = ctrl.step(
        controllable_states=[_state("a", 90.0)],
        uncontrollable_states={"auto": _state("auto", 50.0, available=False)},
    )
    assert result.steering_w == 0.0
    assert result.in_deadband is True


@pytest.mark.parametrize(
    ("kp", "max_w", "deadband"),
    [(-1.0, 1500.0, 2.0), (80.0, -1.0, 2.0), (80.0, 1500.0, -1.0)],
)
def test_invalid_gains_rejected(kp: float, max_w: float, deadband: float) -> None:
    with pytest.raises(ValueError):
        SocEqualiserController(
            [("auto", _role())],
            kp_w_per_pct=kp,
            max_steering_w=max_w,
            soc_deadband_pct=deadband,
        )
