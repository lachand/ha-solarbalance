"""Tests for the revenue-max strategy."""

from dataclasses import replace

import pytest

from custom_components.solarbalance.core.models import (
    BatteryState,
    Device,
    Snapshot,
)
from custom_components.solarbalance.core.strategies.revenue_max import RevenueMaxStrategy
from tests.core.conftest import make_snapshot


def _snap_with_prices(
    *,
    import_price: float | None = None,
    export_price: float | None = None,
    grid_w: float = 0.0,
    batteries: tuple[BatteryState, ...] = (),
) -> Snapshot:
    base = make_snapshot(grid_w=grid_w, batteries=batteries)
    return replace(base, current_import_price=import_price, current_export_price=export_price)


class TestRevenueMaxStrategy:
    def test_kind_identifier(self, ecoflow_device: Device) -> None:
        strat = RevenueMaxStrategy([ecoflow_device], loads=[])
        assert strat.kind == "revenue_max"

    def test_no_prices_returns_no_opinion(self, ecoflow_device: Device) -> None:
        strat = RevenueMaxStrategy([ecoflow_device], loads=[])
        snap = _snap_with_prices(import_price=None, export_price=None)
        decision = strat.compute(snap)
        assert decision.confidence == 0.0
        assert not decision.battery_targets

    @pytest.mark.parametrize(
        ("import_price", "export_price"),
        [
            (0.20, 0.22),  # spread = 0.02 < 0.05 premium
            (0.20, 0.24),  # spread = 0.04 < 0.05 premium
            (0.15, 0.18),  # spread = 0.03, import not cheap enough
        ],
    )
    def test_insufficient_spread_abstains(
        self, ecoflow_device: Device, import_price: float, export_price: float
    ) -> None:
        strat = RevenueMaxStrategy([ecoflow_device], loads=[], export_premium=0.05)
        snap = _snap_with_prices(import_price=import_price, export_price=export_price)
        decision = strat.compute(snap)
        assert decision.confidence == 0.5
        assert not decision.battery_targets

    def test_profitable_spread_triggers_discharge(self, ecoflow_device: Device) -> None:
        strat = RevenueMaxStrategy(
            [ecoflow_device], loads=[], export_premium=0.05, discharge_soc_floor_pct=15.0
        )
        snap = _snap_with_prices(
            import_price=0.20,
            export_price=0.30,  # spread = 0.10 > 0.05
            batteries=(BatteryState(device_name="ecoflow_living_room", soc_pct=60.0, power_w=0.0),),
        )
        decision = strat.compute(snap)
        assert decision.confidence == 1.0
        target = decision.battery_targets["ecoflow_living_room"]
        assert target.preferred_power_w is not None
        assert target.preferred_power_w < 0  # discharge intent
        assert target.soc_min_pct == 15.0

    def test_cheap_import_triggers_charge(self, ecoflow_device: Device) -> None:
        strat = RevenueMaxStrategy(
            [ecoflow_device], loads=[], cheap_import_threshold=0.10, charge_soc_target_pct=90.0
        )
        snap = _snap_with_prices(
            import_price=0.08,  # below cheap threshold
            export_price=0.05,
            batteries=(BatteryState(device_name="ecoflow_living_room", soc_pct=30.0, power_w=0.0),),
        )
        decision = strat.compute(snap)
        assert decision.confidence == 1.0
        target = decision.battery_targets["ecoflow_living_room"]
        assert target.preferred_power_w is not None
        assert target.preferred_power_w > 0  # charge intent
        assert target.soc_max_pct == 90.0

    def test_discharge_authorises_export(self, ecoflow_device: Device) -> None:
        strat = RevenueMaxStrategy([ecoflow_device], loads=[], export_premium=0.05)
        snap = _snap_with_prices(import_price=0.20, export_price=0.30)
        decision = strat.compute(snap)
        assert decision.grid_constraint.max_export_w is not None
        assert decision.grid_constraint.max_export_w > 0

    def test_cheap_charge_does_not_authorise_export(self, ecoflow_device: Device) -> None:
        strat = RevenueMaxStrategy([ecoflow_device], loads=[], cheap_import_threshold=0.10)
        snap = _snap_with_prices(import_price=0.05, export_price=None)
        decision = strat.compute(snap)
        assert decision.grid_constraint.max_export_w is None

    def test_discharge_prefers_over_charge_when_both_triggered(
        self, ecoflow_device: Device
    ) -> None:
        """Discharge takes priority when both conditions are met simultaneously."""
        strat = RevenueMaxStrategy(
            [ecoflow_device], loads=[], export_premium=0.05, cheap_import_threshold=0.15
        )
        # import_price=0.10 ≤ 0.15 (cheap) AND export=0.20 > 0.10+0.05 (profitable)
        snap = _snap_with_prices(import_price=0.10, export_price=0.20)
        decision = strat.compute(snap)
        target = decision.battery_targets.get("ecoflow_living_room")
        assert target is not None
        assert target.preferred_power_w is not None
        assert target.preferred_power_w < 0  # discharge wins

    def test_no_batteries_no_targets(self) -> None:
        strat = RevenueMaxStrategy([], loads=[])
        snap = _snap_with_prices(import_price=0.05, export_price=0.30)
        decision = strat.compute(snap)
        assert not decision.battery_targets
