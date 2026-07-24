"""Tests for the solar-recoverability estimate of an appliance cycle."""

from custom_components.solarbalance.core.controllers.solar_recovery import (
    best_start,
    estimate_solar_share,
)


def test_full_solar_when_the_surplus_covers_the_whole_cycle() -> None:
    # 1000 W for 1 h = 1 kWh, against 2000 W of PV over an idle house.
    share = estimate_solar_share([1000.0], 3600.0, 0, [2000.0] * 4, [0.0] * 4)
    assert share.solar_kwh == 1.0
    assert share.grid_kwh == 0.0
    assert share.solar_fraction == 1.0


def test_no_solar_at_night() -> None:
    share = estimate_solar_share([1000.0], 3600.0, 0, [0.0] * 4, [0.0] * 4)
    assert share.solar_kwh == 0.0
    assert share.grid_kwh == 1.0
    assert share.solar_fraction == 0.0


def test_house_load_is_served_before_the_appliance() -> None:
    # 1500 W of PV, the house already takes 900 → only 600 W spare for a 1000 W
    # appliance running an hour: 0.6 kWh solar, 0.4 kWh imported.
    share = estimate_solar_share([1000.0], 3600.0, 0, [1500.0] * 4, [900.0] * 4)
    assert round(share.solar_kwh, 3) == 0.6
    assert round(share.grid_kwh, 3) == 0.4
    assert round(share.solar_fraction, 2) == 0.6


def test_surplus_is_not_offered_twice_within_one_hour() -> None:
    # Two half-hour steps in the SAME hour with only 500 Wh of surplus: the first
    # step consumes it, the second must import. Offering the hourly surplus to
    # every step would report 1.0 kWh of solar out of thin air.
    share = estimate_solar_share([1000.0, 1000.0], 3600.0, 0, [500.0] * 3, [0.0] * 3)
    assert round(share.solar_kwh, 3) == 0.5
    assert round(share.grid_kwh, 3) == 0.5


def test_a_cycle_running_past_the_forecast_is_flagged_not_assumed_solar() -> None:
    # 3 h cycle but only 2 h of forecast: the tail is counted as grid and marked.
    share = estimate_solar_share([1000.0] * 3, 3 * 3600.0, 0, [5000.0] * 2, [0.0] * 2)
    assert share.truncated is True
    assert share.grid_kwh > 0.0


def test_best_start_picks_the_sunny_window() -> None:
    pv = [0.0, 0.0, 3000.0, 3000.0, 0.0]  # sun only in hours 2-3
    share = best_start([1000.0], 3600.0, pv, [0.0] * 5)
    assert share is not None
    assert share.start_hour == 2
    assert share.solar_fraction == 1.0


def test_best_start_breaks_ties_towards_the_earliest_hour() -> None:
    # Equal coverage everywhere → no reason to make the user wait.
    share = best_start([1000.0], 3600.0, [3000.0] * 5, [0.0] * 5)
    assert share is not None
    assert share.start_hour == 0


def test_best_start_respects_the_window_bounds() -> None:
    pv = [0.0, 0.0, 3000.0, 3000.0, 0.0]
    share = best_start([1000.0], 3600.0, pv, [0.0] * 5, earliest_hour=4)
    assert share is not None
    assert share.start_hour == 4
    assert share.solar_fraction == 0.0


def test_degenerate_inputs_are_safe() -> None:
    assert best_start([], 0.0, [], []) is None
    empty = estimate_solar_share([], 0.0, 0, [], [])
    assert empty.total_kwh == 0.0
    assert empty.solar_fraction == 0.0
