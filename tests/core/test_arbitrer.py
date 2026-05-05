"""Tests for the strategy arbiter."""

import pytest

from custom_components.solarbalance.core.arbitrer import Arbiter
from custom_components.solarbalance.core.models import (
    BatteryTarget,
    Decision,
    GridConstraint,
    Snapshot,
)
from custom_components.solarbalance.core.strategies.base import Strategy


class _StubStrategy(Strategy):
    """Minimal strategy returning a fixed decision."""

    def __init__(self, kind_name: str, decision: Decision) -> None:
        super().__init__(devices=(), loads=())
        self._kind = kind_name
        self._decision = decision

    @property
    def kind(self) -> str:
        return self._kind

    def compute(self, snapshot: Snapshot) -> Decision:
        return self._decision


class TestArbiter:
    def test_requires_at_least_one_strategy(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            Arbiter([])

    def test_decisions_count_must_match_strategies(self) -> None:
        arbiter = Arbiter([_StubStrategy("a", Decision())])
        with pytest.raises(ValueError, match="length"):
            arbiter.arbitrate([Decision(), Decision()])

    def test_dominant_strategy_is_first(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("first", Decision(rationale="R1")),
            _StubStrategy("second", Decision(rationale="R2")),
        ])
        result = arbiter.arbitrate([Decision(rationale="R1"), Decision(rationale="R2")])
        assert result.dominant_strategy == "first"

    def test_grid_constraint_intersects_to_most_restrictive(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(grid_constraint=GridConstraint(max_export_w=500.0, max_import_w=3000.0)),
            Decision(grid_constraint=GridConstraint(max_export_w=200.0, max_import_w=2000.0)),
        ])
        assert result.decision.grid_constraint.max_export_w == 200.0
        assert result.decision.grid_constraint.max_import_w == 2000.0

    def test_grid_constraint_none_is_ignored(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(grid_constraint=GridConstraint(max_export_w=500.0)),
            Decision(grid_constraint=GridConstraint()),
        ])
        assert result.decision.grid_constraint.max_export_w == 500.0

    def test_battery_target_window_is_narrowed_by_lower_priority(self) -> None:
        # First strategy proposes 10-95 ; second strategy proposes 30-90.
        # The fused window should be 30-90 (most restrictive).
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(battery_targets={"bat": BatteryTarget(10.0, 95.0, 500.0)}),
            Decision(battery_targets={"bat": BatteryTarget(30.0, 90.0, None)}),
        ])
        target = result.decision.battery_targets["bat"]
        assert target.soc_min_pct == 30.0
        assert target.soc_max_pct == 90.0
        # preferred_power_w comes from the highest-priority opinion.
        assert target.preferred_power_w == 500.0

    def test_inconsistent_window_collapses_to_midpoint(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(battery_targets={"bat": BatteryTarget(80.0, 90.0)}),
            Decision(battery_targets={"bat": BatteryTarget(20.0, 30.0)}),
        ])
        target = result.decision.battery_targets["bat"]
        # Resolved min=80, max=30 → inconsistent → collapsed to midpoint 55.
        assert target.soc_min_pct == 55.0
        assert target.soc_max_pct == 55.0

    def test_load_priorities_weighted_average_with_decay(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
            _StubStrategy("c", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(load_priorities={"ballon": 1}),  # weight 1.0
            Decision(load_priorities={"ballon": 3}),  # weight 0.5
            Decision(load_priorities={"ballon": 5}),  # weight 0.25
        ])
        # weighted = (1×1 + 3×0.5 + 5×0.25) / (1 + 0.5 + 0.25) = 3.75 / 1.75 ≈ 2.14 → round 2
        assert result.decision.load_priorities["ballon"] == 2

    def test_confidence_takes_minimum(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(confidence=0.9),
            Decision(confidence=0.4),
        ])
        assert result.decision.confidence == 0.4

    def test_rationale_is_concatenated(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("a", Decision(rationale="R1")),
            _StubStrategy("b", Decision(rationale="R2")),
        ])
        result = arbiter.arbitrate([
            Decision(rationale="R1"),
            Decision(rationale="R2"),
        ])
        assert "R1" in result.decision.rationale
        assert "R2" in result.decision.rationale
