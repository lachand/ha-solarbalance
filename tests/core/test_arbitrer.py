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

    def test_dominant_strategy_is_highest_confidence_substantive(self) -> None:
        # Second strategy produces a substantive decision with confidence 1.0;
        # first strategy is neutral (empty, confidence 0.5) → second dominates.
        arbiter = Arbiter([
            _StubStrategy("first", Decision(confidence=0.5)),
            _StubStrategy("second", Decision(
                battery_targets={"bat": BatteryTarget(10.0, 95.0)},
                confidence=1.0,
            )),
        ])
        result = arbiter.arbitrate([
            Decision(confidence=0.5),
            Decision(battery_targets={"bat": BatteryTarget(10.0, 95.0)}, confidence=1.0),
        ])
        assert result.dominant_strategy == "second"

    def test_dominant_strategy_falls_back_to_first_when_all_empty(self) -> None:
        arbiter = Arbiter([
            _StubStrategy("first", Decision()),
            _StubStrategy("second", Decision()),
        ])
        result = arbiter.arbitrate([Decision(), Decision()])
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

    def test_inconsistent_window_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        with caplog.at_level(logging.WARNING, logger="custom_components.solarbalance.core.arbitrer"):
            arbiter.arbitrate([
                Decision(battery_targets={"bat": BatteryTarget(80.0, 90.0)}),
                Decision(battery_targets={"bat": BatteryTarget(20.0, 30.0)}),
            ])
        assert any("conflict" in r.message.lower() for r in caplog.records)

    def test_load_priorities_highest_authority_wins(self) -> None:
        # Strategy "a" (highest authority) expresses priority 2 for ballon;
        # strategy "b" expresses priority 5. First opinion wins.
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(load_priorities={"ballon": 2}),
            Decision(load_priorities={"ballon": 5}),
        ])
        assert result.decision.load_priorities["ballon"] == 2

    def test_load_priorities_fallback_when_first_has_no_opinion(self) -> None:
        # Strategy "a" has no opinion on "ballon"; strategy "b" fills in.
        arbiter = Arbiter([
            _StubStrategy("a", Decision()),
            _StubStrategy("b", Decision()),
        ])
        result = arbiter.arbitrate([
            Decision(load_priorities={}),
            Decision(load_priorities={"ballon": 3}),
        ])
        assert result.decision.load_priorities["ballon"] == 3

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

    def test_run_calls_strategies_and_arbitrates(self, empty_snapshot: Snapshot) -> None:
        """run() should produce identical results to manually calling compute + arbitrate."""
        strategy = _StubStrategy(
            "a",
            Decision(battery_targets={"bat": BatteryTarget(20.0, 80.0)}, confidence=0.9),
        )
        arbiter = Arbiter([strategy])
        result_run = arbiter.run(empty_snapshot)
        result_manual = arbiter.arbitrate([strategy.compute(empty_snapshot)])
        assert result_run.decision.battery_targets == result_manual.decision.battery_targets
        assert result_run.dominant_strategy == result_manual.dominant_strategy
