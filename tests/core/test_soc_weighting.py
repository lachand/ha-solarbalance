"""Tests for capacity-weighted (energy-true) mean SoC."""

import pytest

from custom_components.solarbalance.core.models import (
    capacity_weighted_soc_pct,
    stored_energy_kwh,
    usable_window_kwh,
)


def test_weighted_mean_is_energy_true_not_arithmetic() -> None:
    # 2 kWh @ 75 % + 3.96 kWh @ 25 % -> (1.5 + 0.99) / 5.96 = 41.78 %, not 50 %.
    assert capacity_weighted_soc_pct([(75.0, 2.0), (25.0, 3.96)]) == pytest.approx(41.78, abs=0.01)


def test_equal_capacities_match_arithmetic_mean() -> None:
    assert capacity_weighted_soc_pct([(75.0, 3.0), (25.0, 3.0)]) == pytest.approx(50.0)


def test_single_battery_returns_its_soc() -> None:
    assert capacity_weighted_soc_pct([(63.0, 5.0)]) == pytest.approx(63.0)


def test_empty_returns_none() -> None:
    assert capacity_weighted_soc_pct([]) is None


def test_non_positive_capacities_ignored() -> None:
    assert capacity_weighted_soc_pct([(80.0, 0.0), (40.0, -1.0)]) is None
    assert capacity_weighted_soc_pct([(80.0, 0.0), (40.0, 2.0)]) == pytest.approx(40.0)


def test_stored_energy_is_sum_of_soc_times_capacity() -> None:
    # 0.75*2 + 0.25*3.96 = 1.5 + 0.99 = 2.49 kWh.
    assert stored_energy_kwh([(75.0, 2.0), (25.0, 3.96)]) == pytest.approx(2.49)


def test_stored_energy_empty_is_zero() -> None:
    assert stored_energy_kwh([]) == pytest.approx(0.0)


def test_stored_energy_ignores_non_positive_capacity() -> None:
    assert stored_energy_kwh([(80.0, 0.0), (50.0, 4.0)]) == pytest.approx(2.0)


def test_usable_window_is_span_between_floor_and_ceiling() -> None:
    # (95-10)/100*2 + (90-20)/100*4 = 1.7 + 2.8 = 4.5 kWh.
    assert usable_window_kwh([(10.0, 95.0, 2.0), (20.0, 90.0, 4.0)]) == pytest.approx(4.5)


def test_usable_window_empty_is_zero() -> None:
    assert usable_window_kwh([]) == pytest.approx(0.0)


def test_usable_window_clamps_inverted_bounds_and_ignores_zero_capacity() -> None:
    assert usable_window_kwh([(90.0, 10.0, 5.0)]) == pytest.approx(0.0)
    assert usable_window_kwh([(10.0, 90.0, 0.0)]) == pytest.approx(0.0)
