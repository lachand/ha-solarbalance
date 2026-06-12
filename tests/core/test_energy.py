"""Tests for the daily energy accumulator."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.solarbalance.core.energy import DailyEnergyAccumulator


def _ts(minute: float) -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC) + timedelta(minutes=minute)


def test_first_sample_only_seeds_state() -> None:
    acc = DailyEnergyAccumulator()
    acc.update(now=_ts(0), local_date=_ts(0).date(), pv_w=1000.0, grid_w=500.0)
    assert acc.pv_kwh == 0.0
    assert acc.grid_import_kwh == 0.0


def test_integrates_power_over_time() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.update(now=_ts(0), local_date=d, pv_w=1000.0, grid_w=600.0)  # seed
    acc.update(now=_ts(10), local_date=d, pv_w=1000.0, grid_w=600.0)  # +10 min
    assert acc.pv_kwh == pytest.approx(1000.0 * (10 / 60) / 1000)  # 0.1667 kWh
    assert acc.grid_import_kwh == pytest.approx(600.0 * (10 / 60) / 1000)


def test_only_positive_pv_and_import_counted() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.update(now=_ts(0), local_date=d, pv_w=-50.0, grid_w=-800.0)  # export
    acc.update(now=_ts(10), local_date=d, pv_w=-50.0, grid_w=-800.0)
    assert acc.pv_kwh == 0.0
    assert acc.grid_import_kwh == 0.0


def test_grid_export_integrates_negative_grid() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.update(now=_ts(0), local_date=d, pv_w=2000.0, grid_w=-800.0)  # seed
    acc.update(now=_ts(10), local_date=d, pv_w=2000.0, grid_w=-800.0)  # +10 min export
    assert acc.grid_export_kwh == pytest.approx(800.0 * (10 / 60) / 1000)
    assert acc.grid_import_kwh == 0.0
    # Import does not feed the export accumulator.
    acc.update(now=_ts(20), local_date=d, pv_w=2000.0, grid_w=500.0)
    assert acc.grid_export_kwh == pytest.approx(800.0 * (10 / 60) / 1000)


def test_restore_seeds_grid_export() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.restore(day=d, pv_kwh=1.0, grid_import_kwh=0.5, grid_export_kwh=2.0)
    assert acc.grid_export_kwh == 2.0


def test_resets_at_local_midnight() -> None:
    acc = DailyEnergyAccumulator()
    d0 = _ts(0).date()
    acc.update(now=_ts(0), local_date=d0, pv_w=1000.0, grid_w=0.0)
    acc.update(now=_ts(10), local_date=d0, pv_w=1000.0, grid_w=0.0)
    assert acc.pv_kwh > 0.0
    next_day = d0 + timedelta(days=1)
    acc.update(now=_ts(20), local_date=next_day, pv_w=1000.0, grid_w=0.0)
    assert acc.pv_kwh == 0.0  # reset on date change


def test_restore_same_day_continues() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.restore(day=d, pv_kwh=3.0, grid_import_kwh=1.5)
    assert acc.day == d and acc.pv_kwh == 3.0
    # First update after restore re-seeds the timestamp (no jump), then accumulates.
    acc.update(now=_ts(0), local_date=d, pv_w=1000.0, grid_w=0.0)
    acc.update(now=_ts(10), local_date=d, pv_w=1000.0, grid_w=0.0)
    assert acc.pv_kwh == pytest.approx(3.0 + 1000.0 * (10 / 60) / 1000)


def test_restore_stale_day_resets_on_next_update() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.restore(day=d - timedelta(days=1), pv_kwh=9.9, grid_import_kwh=9.9)
    acc.update(now=_ts(0), local_date=d, pv_w=1000.0, grid_w=1000.0)  # new day → reset
    assert acc.pv_kwh == 0.0
    assert acc.grid_import_kwh == 0.0


def test_long_gap_is_not_integrated() -> None:
    acc = DailyEnergyAccumulator()
    d = _ts(0).date()
    acc.update(now=_ts(0), local_date=d, pv_w=1000.0, grid_w=0.0)
    # 40-minute gap (> 30 min cap) → skipped, no bogus increment.
    acc.update(now=_ts(40), local_date=d, pv_w=1000.0, grid_w=0.0)
    assert acc.pv_kwh == 0.0
