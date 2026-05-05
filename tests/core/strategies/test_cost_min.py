"""Tests for the cost-minimisation strategy."""

import pytest

from custom_components.solarbalance.core.models import Device
from custom_components.solarbalance.core.strategies.cost_min import CostMinStrategy
from custom_components.solarbalance.core.tariff import TariffConfig, TariffSlot
from tests.core.conftest import make_snapshot
from datetime import time, datetime, UTC


def _snap_with_price(import_price: float | None) -> object:
    from dataclasses import replace
    snap = make_snapshot(grid_w=0.0)
    return replace(snap, current_import_price=import_price)


def _cheap_tariff() -> TariffConfig:
    return TariffConfig(slots=[
        TariffSlot("hc", time(0), time(6), import_price=0.15),
        TariffSlot("hp", time(6), time(22), import_price=0.28),
    ])


class TestCostMinStrategy:
    def test_kind_identifier(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.15, expensive_threshold=0.25,
        )
        assert strat.kind == "cost_min"

    def test_cheap_threshold_must_not_exceed_expensive(self, ecoflow_device: Device) -> None:
        with pytest.raises(ValueError, match="cheap_threshold"):
            CostMinStrategy(
                [ecoflow_device], loads=[],
                tariff=TariffConfig(), cheap_threshold=0.30, expensive_threshold=0.20,
            )

    def test_no_price_returns_no_opinion(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.15, expensive_threshold=0.25,
        )
        snap = _snap_with_price(None)
        decision = strat.compute(snap)  # type: ignore[arg-type]
        assert decision.confidence == 0.0
        assert "no import price" in decision.rationale

    def test_cheap_window_sets_charge_preferred(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.17, expensive_threshold=0.25,
        )
        snap = _snap_with_price(0.15)
        decision = strat.compute(snap)  # type: ignore[arg-type]
        target = decision.battery_targets[ecoflow_device.name]
        assert target.preferred_power_w is not None
        assert target.preferred_power_w > 0
        assert "cheap" in decision.rationale

    def test_expensive_window_sets_discharge_preferred(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.17, expensive_threshold=0.25,
        )
        snap = _snap_with_price(0.30)
        decision = strat.compute(snap)  # type: ignore[arg-type]
        target = decision.battery_targets[ecoflow_device.name]
        assert target.preferred_power_w is not None
        assert target.preferred_power_w < 0
        assert "expensive" in decision.rationale

    def test_neutral_window_has_no_targets(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.15, expensive_threshold=0.25,
        )
        snap = _snap_with_price(0.20)
        decision = strat.compute(snap)  # type: ignore[arg-type]
        assert decision.battery_targets == {}
        assert decision.confidence == pytest.approx(0.5)

    def test_cheap_window_allows_grid_import(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.17, expensive_threshold=0.25,
        )
        snap = _snap_with_price(0.15)
        decision = strat.compute(snap)  # type: ignore[arg-type]
        assert decision.grid_constraint.max_import_w is None

    def test_expensive_window_forbids_import(self, ecoflow_device: Device) -> None:
        strat = CostMinStrategy(
            [ecoflow_device], loads=[],
            tariff=TariffConfig(), cheap_threshold=0.17, expensive_threshold=0.25,
        )
        snap = _snap_with_price(0.30)
        decision = strat.compute(snap)  # type: ignore[arg-type]
        assert decision.grid_constraint.max_import_w == pytest.approx(0.0)
