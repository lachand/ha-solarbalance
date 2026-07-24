"""Tests for the forecast-driven evening reserve."""

from custom_components.solarbalance.core.controllers.evening_reserve import evening_reserve

# 500 W all day, 900 W across the 18:00-22:00 peak.
_HOUSE = [500.0] * 18 + [900.0] * 4 + [500.0] * 2
_NO_PV = [0.0] * 24


def _call(**kw):
    base = {
        "enabled": True,
        "hour": 14,
        "house_by_hour": _HOUSE,
        "pv_by_hour": _NO_PV,
        "usable_capacity_kwh": 8.0,
        "soc_min_pct": 10.0,
    }
    base.update(kw)
    return evening_reserve(**base)  # type: ignore[arg-type]


def test_holds_the_energy_the_evening_will_actually_need() -> None:
    # 4 peak hours at 900 W with no sun = 3.6 kWh. On an 8 kWh pack that is 45 %,
    # so the floor sits at 10 + 45 = 55 %.
    res = _call()
    assert res.active is True
    assert round(res.reserve_kwh, 2) == 3.6
    assert round(res.soc_floor_pct) == 55
    assert res.reason == "holding"


def test_evening_sun_reduces_what_must_be_stored() -> None:
    # Still producing 700 W through the peak: only 200 W/h has to come from storage.
    pv = [0.0] * 18 + [700.0] * 4 + [0.0] * 2
    res = _call(pv_by_hour=pv)
    assert round(res.reserve_kwh, 2) == 0.8


def test_the_reserve_is_released_once_the_peak_starts() -> None:
    # A reserve that is never spent is just a smaller battery.
    res = _call(hour=19)
    assert res.active is False
    assert res.soc_floor_pct == 10.0
    assert res.reason == "in_peak"


def test_it_never_claims_the_whole_pack() -> None:
    # A very expensive predicted evening must not pin the battery and leave the
    # afternoon unable to regulate at all.
    house = [500.0] * 18 + [5000.0] * 4 + [500.0] * 2
    res = _call(house_by_hour=house, max_share=0.6)
    assert res.reserve_kwh == 8.0 * 0.6
    assert round(res.soc_floor_pct) == 70  # 10 % + 60 %


def test_it_never_goes_below_the_battery_floor() -> None:
    res = _call(soc_min_pct=20.0)
    assert res.soc_floor_pct >= 20.0


def test_no_profile_means_no_guessing() -> None:
    res = _call(house_by_hour=None)
    assert res.active is False
    assert res.reason == "no_profile"
    assert res.soc_floor_pct == 10.0


def test_a_cheap_evening_is_not_worth_the_lost_flexibility() -> None:
    res = _call(house_by_hour=[10.0] * 24)
    assert res.active is False
    assert res.reason == "nothing_needed"


def test_disabled_is_inert() -> None:
    res = _call(enabled=False)
    assert res.active is False
    assert res.soc_floor_pct == 10.0
    assert res.reason == "disabled"


def test_missing_pv_forecast_only_makes_the_reserve_larger() -> None:
    # Treating an absent forecast as "no sun" errs toward holding more, which is the
    # safe direction: the worst case is an unnecessarily full battery.
    with_pv = _call(pv_by_hour=[900.0] * 24).reserve_kwh
    without = _call(pv_by_hour=None).reserve_kwh
    assert without > with_pv


def test_the_reserve_only_ever_blocks_a_discharge() -> None:
    """The clamp's contract, stated as a test.

    The reserve refuses to spend below its floor; it must never *force* a charge,
    or a cloudy afternoon would start importing from the grid to fill a battery for
    an evening the grid could serve just as well.
    """
    res = _call()
    assert res.active is True
    # The coordinator applies it as: if target < 0 and stored <= reserve -> target = 0.
    for target_w, stored_kwh, expected in [
        (-800.0, 1.0, 0.0),  # below the reserve: stop discharging
        (-800.0, 9.0, -800.0),  # plenty above it: discharge freely
        (600.0, 1.0, 600.0),  # charging is never touched
    ]:
        clamped = 0.0 if (target_w < 0 and stored_kwh <= res.reserve_kwh) else target_w
        assert clamped == expected
