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
            (-500.0, 1),    # exporting → want to charge (positive preferred power)
            (300.0, -1),    # importing → want to discharge (negative)
            (0.0, 0),       # balanced → idle
            (0.5, 0),       # below 1 W threshold → idle
        ],
    )
    def test_preferred_power_sign_follows_grid(
        self, ecoflow_device: Device, grid_w: float, expected_sign: int
    ) -> None:
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(
            grid_w=grid_w,
            batteries=(
                BatteryState(device_name="ecoflow_living_room", soc_pct=50.0, power_w=0.0),
            ),
            mppts=(MpptState(device_name="ecoflow_living_room", power_w=0.0),),
        )
        decision = strat.compute(snap)
        target = decision.battery_targets["ecoflow_living_room"]
        assert target.preferred_power_w is not None

        if expected_sign == 0:
            assert target.preferred_power_w == 0.0
        else:
            assert (target.preferred_power_w > 0) is (expected_sign > 0)

    def test_export_is_forbidden_by_default(self, ecoflow_device: Device) -> None:
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        assert decision.grid_constraint.max_export_w == 0.0

    def test_battery_targets_use_role_soc_bounds(self, ecoflow_device: Device) -> None:
        strat = SelfConsumptionStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        target = decision.battery_targets["ecoflow_living_room"]
        # ecoflow_device has default 10/95 bounds.
        assert target.soc_min_pct == 10.0
        assert target.soc_max_pct == 95.0
