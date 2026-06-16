"""Tests for the self-consumption strategy."""

import pytest

from custom_components.solarbalance.core.models import (
    BatteryState,
    Device,
    MpptState,
)
from custom_components.solarbalance.core.strategies.self_consumption import (
    SelfConsumptionStrategy,
)
from tests.core.conftest import make_snapshot


class TestSelfConsumptionStrategy:
    def test_kind_identifier(self, ecoflow_device: Device) -> None:
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        assert strat.kind == "self_consumption"

    @pytest.mark.parametrize(
        ("grid_w", "expected_sign"),
        [
            (-500.0, 1),  # exporting → want to charge (positive preferred power)
            (300.0, -1),  # importing → want to discharge (negative)
            (0.0, 0),  # balanced → idle
            (0.5, 0),  # below 1 W threshold → idle
        ],
    )
    def test_preferred_power_sign_follows_grid(
        self, ecoflow_device: Device, grid_w: float, expected_sign: int
    ) -> None:
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(
            grid_w=grid_w,
            batteries=(BatteryState(device_name="ecoflow_living_room", soc_pct=50.0, power_w=0.0),),
            mppts=(MpptState(device_name="ecoflow_living_room", power_w=0.0),),
        )
        decision = strat.compute(snap)
        target = decision.battery_targets["ecoflow_living_room"]
        assert target.preferred_power_w is not None

        if expected_sign == 0:
            assert target.preferred_power_w == 0.0
        else:
            assert (target.preferred_power_w > 0) is (expected_sign > 0)

    def test_no_grid_export_constraint(self, ecoflow_device: Device) -> None:
        """SelfConsumption no longer locks out export; ZI controller handles injection."""
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        assert decision.grid_constraint.max_export_w is None

    def test_confidence_below_economic_strategies(self, ecoflow_device: Device) -> None:
        """confidence=0.8 so CostMin/RevenueMax (1.0) can win dominant_strategy."""
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        assert decision.confidence < 1.0

    def test_battery_targets_use_role_soc_bounds(self, ecoflow_device: Device) -> None:
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        target = decision.battery_targets["ecoflow_living_room"]
        # ecoflow_device has default 10/95 bounds.
        assert target.soc_min_pct == 10.0
        assert target.soc_max_pct == 95.0

    def test_preferred_power_sums_to_grid_deviation_for_multiple_batteries(
        self,
        ecoflow_device: Device,
        jackery_device: Device,
    ) -> None:
        """Sum of preferred_power_w across all batteries must equal the grid deviation.

        The coordinator sums preferred_power_w as the total_power_w for balancing;
        each battery must carry its proportional share so the sum matches net_grid.
        """
        strat = SelfConsumptionStrategy([ecoflow_device, jackery_device], loads=[])
        grid_w = 600.0
        snap = make_snapshot(
            grid_w=grid_w,
            batteries=(
                BatteryState(device_name="ecoflow_living_room", soc_pct=50.0, power_w=0.0),
                BatteryState(device_name="jackery_garage", soc_pct=50.0, power_w=0.0),
            ),
        )
        decision = strat.compute(snap)
        total_preferred = sum(t.preferred_power_w or 0.0 for t in decision.battery_targets.values())
        assert total_preferred == pytest.approx(-grid_w, abs=0.1)
