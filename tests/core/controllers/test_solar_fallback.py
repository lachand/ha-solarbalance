"""Tests for the solar-only fallback used when the grid meter is unavailable."""

from custom_components.solarbalance.core.controllers.solar_fallback import (
    solar_only_target_w,
)


def _call(**kw):
    base = {
        "enabled": True,
        "pv_available": True,
        "controllable_mppt_w": 1500.0,
        "predicted_house_w": 400.0,
        "headroom_kwh": 2.0,
    }
    base.update(kw)
    return solar_only_target_w(**base)  # type: ignore[arg-type]


def test_charges_a_fraction_of_the_estimated_surplus() -> None:
    # 1500 W of PV against a 400 W expected house = 1100 W of estimated surplus.
    # Only 70 % is commanded, so an underestimated house comes off the margin
    # instead of being pulled from the grid.
    res = _call()
    assert res.active is True
    assert res.estimated_surplus_w == 1100.0
    assert res.charge_w == 770.0
    assert res.reason == "charging"


def test_never_discharges_even_when_the_house_exceeds_production() -> None:
    # The whole point: blind discharging could export with nobody watching.
    res = _call(controllable_mppt_w=200.0, predicted_house_w=900.0)
    assert res.active is False
    assert res.charge_w == 0.0
    assert res.charge_w >= 0.0
    assert res.reason == "no_surplus"


def test_a_surplus_within_profile_noise_is_not_acted_on() -> None:
    res = _call(controllable_mppt_w=500.0, predicted_house_w=400.0)  # 100 W
    assert res.active is False
    assert res.reason == "no_surplus"


def test_refuses_to_guess_without_a_learned_profile() -> None:
    res = _call(predicted_house_w=None)
    assert res.active is False
    assert res.reason == "no_pv_telemetry"


def test_refuses_without_fresh_pv_telemetry() -> None:
    res = _call(pv_available=False)
    assert res.active is False
    assert res.charge_w == 0.0


def test_does_nothing_when_the_fleet_is_full() -> None:
    res = _call(headroom_kwh=0.0)
    assert res.active is False
    assert res.reason == "battery_full"


def test_disabled_by_default_is_inert() -> None:
    res = _call(enabled=False)
    assert res.active is False
    assert res.charge_w == 0.0
    assert res.reason == "disabled"


def test_safety_factor_bounds_are_respected() -> None:
    assert _call(safety_factor=2.0).charge_w == 1100.0  # clamped to 1.0
    assert _call(safety_factor=-1.0).charge_w == 0.0  # clamped to 0.0
