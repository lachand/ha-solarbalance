"""Tests for the physical-plausibility guard on grid readings."""

from custom_components.solarbalance.core.plausibility import (
    DEFAULT_TOLERANCE_W,
    check_grid_reading,
)


def test_the_real_impossible_reading_is_rejected() -> None:
    # Observed 2026-07-23 17:46:34: meter read -2032 W of export while PV made
    # 1638 W and the batteries were CHARGING 1479 W. Max possible export was
    # 1638 - 1479 = 159 W, so the reading was impossible by ~1.87 kW.
    res = check_grid_reading(-2032.0, pv_w=1638.0, battery_w=1479.0, last_valid_w=-4.0)
    assert res.rejected is True
    assert res.reason == "impossible_export"
    assert res.grid_w == -4.0  # the held value, not the impossible one
    assert round(res.max_export_w) == 159


def test_a_battery_discharging_raises_the_export_ceiling() -> None:
    # Same export, but now the batteries are pushing 1500 W out instead of soaking
    # it: 1638 + 1500 = 3138 W available, so -2032 W is entirely plausible.
    res = check_grid_reading(-2032.0, pv_w=1638.0, battery_w=-1500.0, last_valid_w=0.0)
    assert res.rejected is False
    assert res.grid_w == -2032.0


def test_a_genuine_pv_surplus_passes_untouched() -> None:
    res = check_grid_reading(-1200.0, pv_w=2000.0, battery_w=0.0, last_valid_w=0.0)
    assert res.rejected is False
    assert res.grid_w == -1200.0


def test_import_is_never_rejected() -> None:
    # The grid can always supply more, so there is no ceiling to break — even a
    # large import with zero production is legitimate (a 3 kW appliance at night).
    res = check_grid_reading(3000.0, pv_w=0.0, battery_w=0.0, last_valid_w=0.0)
    assert res.rejected is False
    assert res.grid_w == 3000.0


def test_tolerance_lets_a_borderline_reading_through() -> None:
    # 159 W of headroom + the default tolerance: a slightly-over reading is kept,
    # because a false rejection freezes the loop on a stale value.
    res = check_grid_reading(
        -(159.0 + DEFAULT_TOLERANCE_W - 10.0), pv_w=1638.0, battery_w=1479.0, last_valid_w=0.0
    )
    assert res.rejected is False


def test_just_past_the_tolerance_is_rejected() -> None:
    res = check_grid_reading(
        -(159.0 + DEFAULT_TOLERANCE_W + 10.0), pv_w=1638.0, battery_w=1479.0, last_valid_w=-50.0
    )
    assert res.rejected is True
    assert res.grid_w == -50.0


def test_first_tick_has_nothing_to_hold_so_it_does_not_block_startup() -> None:
    res = check_grid_reading(-5000.0, pv_w=0.0, battery_w=0.0, last_valid_w=None)
    assert res.rejected is False
    assert res.reason == "no_reference"
    assert res.grid_w == -5000.0


def test_night_export_with_no_production_is_impossible() -> None:
    # No PV, batteries idle: nothing can leave the property.
    res = check_grid_reading(-900.0, pv_w=0.0, battery_w=0.0, last_valid_w=120.0)
    assert res.rejected is True
    assert res.max_export_w == 0.0
    assert res.grid_w == 120.0
