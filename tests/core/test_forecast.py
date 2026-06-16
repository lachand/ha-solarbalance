"""Tests for the advisory forecast-slot builder and fleet aggregation."""

from datetime import UTC, datetime

from custom_components.solarbalance.core.forecast import (
    ForecastConfig,
    ForecastUnit,
    aggregate_battery_constraints,
    build_forecast_slots,
    build_pv_w_by_hour,
)
from custom_components.solarbalance.core.planner import BatteryConstraints
from custom_components.solarbalance.core.tariff import TariffConfig

_START = datetime(2026, 6, 12, 0, 0, tzinfo=UTC)


def _bat(**kw: float) -> BatteryConstraints:
    base = {"capacity_kwh": 5.0, "max_charge_w": 2000.0, "max_discharge_w": 2000.0}
    base.update(kw)
    return BatteryConstraints(**base)  # type: ignore[arg-type]


def test_build_slots_net_load_is_baseline_minus_pv() -> None:
    slots = build_forecast_slots(
        start=_START,
        n_hours=3,
        pv_w_by_hour=[1000.0, 500.0, 0.0],
        baseline_w=400.0,
        tariff=TariffConfig(),
    )
    assert [s.net_load_w for s in slots] == [-600.0, -100.0, 400.0]
    assert all(s.duration_s == 3600.0 for s in slots)
    assert len(slots) == 3


def test_pv_series_repeats_last_value() -> None:
    slots = build_forecast_slots(
        start=_START,
        n_hours=4,
        pv_w_by_hour=[800.0],
        baseline_w=300.0,
        tariff=TariffConfig(),
    )
    # single PV value held flat across the horizon → constant net load
    assert [s.net_load_w for s in slots] == [-500.0, -500.0, -500.0, -500.0]


def test_empty_pv_means_no_production() -> None:
    slots = build_forecast_slots(
        start=_START,
        n_hours=2,
        pv_w_by_hour=[],
        baseline_w=250.0,
        tariff=TariffConfig(),
    )
    assert [s.net_load_w for s in slots] == [250.0, 250.0]


def test_prices_are_always_populated() -> None:
    slots = build_forecast_slots(
        start=_START,
        n_hours=2,
        pv_w_by_hour=[],
        baseline_w=0.0,
        tariff=TariffConfig(),
    )
    assert all(isinstance(s.import_price, float) for s in slots)
    assert all(isinstance(s.export_price, float) for s in slots)


def test_aggregate_sums_and_tightens_bounds() -> None:
    agg = aggregate_battery_constraints(
        [
            _bat(
                capacity_kwh=5.0,
                max_charge_w=2000.0,
                max_discharge_w=1800.0,
                soc_min_pct=10.0,
                soc_max_pct=95.0,
            ),
            _bat(
                capacity_kwh=3.0,
                max_charge_w=1000.0,
                max_discharge_w=1200.0,
                soc_min_pct=15.0,
                soc_max_pct=90.0,
            ),
        ]
    )
    assert agg is not None
    assert agg.capacity_kwh == 8.0
    assert agg.max_charge_w == 3000.0
    assert agg.max_discharge_w == 3000.0
    assert agg.soc_min_pct == 15.0  # most restrictive
    assert agg.soc_max_pct == 90.0


def test_aggregate_empty_is_none() -> None:
    assert aggregate_battery_constraints([]) is None


def test_build_pv_by_hour_kwh_converted_to_power() -> None:
    cfg = ForecastConfig(
        unit=ForecastUnit.KWH,
        hour_entities=((0, "sensor.this_hour"), (1, "sensor.next_hour")),
    )
    pv = build_pv_w_by_hour(cfg, {"sensor.this_hour": 0.8, "sensor.next_hour": 0.5}, horizon_h=4)
    assert pv == [800.0, 500.0, 0.0, 0.0]  # kWh/h → W, undeclared hours = 0


def test_build_pv_by_hour_watt_passthrough_and_clamp() -> None:
    cfg = ForecastConfig(unit=ForecastUnit.W, hour_entities=((0, "sensor.now"),))
    assert build_pv_w_by_hour(cfg, {"sensor.now": -50.0}, horizon_h=2) == [0.0, 0.0]


def test_build_pv_by_hour_missing_value_is_zero() -> None:
    cfg = ForecastConfig(unit=ForecastUnit.W, hour_entities=((1, "sensor.next"),))
    assert build_pv_w_by_hour(cfg, {}, horizon_h=3) == [0.0, 0.0, 0.0]


def test_forecast_entities_deduplicated() -> None:
    cfg = ForecastConfig(
        unit=ForecastUnit.W,
        hour_entities=((0, "sensor.a"), (1, "sensor.a"), (2, "sensor.b")),
    )
    assert cfg.entities == ("sensor.a", "sensor.b")
