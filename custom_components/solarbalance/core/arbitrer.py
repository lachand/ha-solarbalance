"""Arbiter — combines decisions from ordered strategies into a single output.

Rules (see SPECIFICATIONS §6.1):
- `battery_targets`: SoC window is narrowed by intersection; `preferred_power_w`
  is taken from the first (highest-priority) strategy that expresses an opinion.
- `grid_constraint`: intersection across all strategies (most restrictive wins).
- `load_priorities`: the highest-priority strategy that expresses an opinion on
  a given load sets that load's priority. Ordinal semantics are preserved
  (priority 1 = most urgent, not summed with lower-priority opinions).
- `dominant_strategy`: the strategy with the highest confidence among those that
  produced a substantive decision (non-empty battery targets or grid constraint).
- `rationale`: concatenated, prefixed with strategy name.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from .models import BatteryTarget, Decision, GridConstraint, Snapshot
from .strategies.base import Strategy

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ArbitrationResult:
    """Outcome of fusing N decisions."""

    decision: Decision
    dominant_strategy: str | None
    per_strategy: tuple[tuple[str, Decision], ...]


class Arbiter:
    """Combine decisions from ordered strategies."""

    def __init__(self, strategies: Sequence[Strategy]) -> None:
        if not strategies:
            raise ValueError("Arbiter requires at least one strategy")
        self._strategies = tuple(strategies)

    def arbitrate(self, decisions: Sequence[Decision]) -> ArbitrationResult:
        """Fuse `decisions` (in the same order as the strategies)."""
        if len(decisions) != len(self._strategies):
            raise ValueError(
                f"decisions length ({len(decisions)}) must match "
                f"strategies length ({len(self._strategies)})"
            )

        merged_targets = self._merge_battery_targets(decisions)
        merged_grid = self._merge_grid_constraints(decisions)
        merged_loads = self._merge_load_priorities(decisions)
        rationale = self._compose_rationale(decisions)

        fused = Decision(
            battery_targets=merged_targets,
            grid_constraint=merged_grid,
            load_priorities=merged_loads,
            confidence=min(d.confidence for d in decisions),
            rationale=rationale,
        )

        per_strategy = tuple(
            (strategy.kind, decision)
            for strategy, decision in zip(self._strategies, decisions, strict=True)
        )

        return ArbitrationResult(
            decision=fused,
            dominant_strategy=self._compute_dominant_strategy(decisions),
            per_strategy=per_strategy,
        )

    def run(self, snapshot: Snapshot) -> ArbitrationResult:
        """Compute all strategy decisions for *snapshot* and fuse them.

        Convenience method equivalent to calling ``strategy.compute(snapshot)`` on
        each strategy and passing the results to ``arbitrate()``. Callers should
        prefer this over accessing ``_strategies`` directly.
        """
        decisions = [s.compute(snapshot) for s in self._strategies]
        return self.arbitrate(decisions)

    # ------------------------------------------------------------------ helpers

    def _compute_dominant_strategy(self, decisions: Sequence[Decision]) -> str | None:
        """Return the strategy that produced the most substantive decision.

        'Substantive' means the decision has battery targets or a non-None grid
        constraint. Among substantive decisions, the one with highest confidence
        wins; ties are broken by list order (highest-priority strategy first).
        Falls back to the first strategy when all decisions are empty.
        """
        best_idx: int | None = None
        best_confidence = -1.0
        for i, decision in enumerate(decisions):
            is_substantive = bool(decision.battery_targets) or (
                decision.grid_constraint.max_import_w is not None
                or decision.grid_constraint.max_export_w is not None
            )
            if is_substantive and decision.confidence > best_confidence:
                best_confidence = decision.confidence
                best_idx = i
        if best_idx is None:
            return self._strategies[0].kind if self._strategies else None
        return self._strategies[best_idx].kind

    def _merge_battery_targets(
        self, decisions: Sequence[Decision]
    ) -> dict[str, BatteryTarget]:
        merged: dict[str, BatteryTarget] = {}
        device_names: set[str] = set()
        for d in decisions:
            device_names.update(d.battery_targets.keys())

        for name in device_names:
            soc_min: float | None = None
            soc_max: float | None = None
            preferred_w: float | None = None
            for d in decisions:
                target = d.battery_targets.get(name)
                if target is None:
                    continue
                # Resolve narrowing: take the more restrictive bound.
                soc_min = target.soc_min_pct if soc_min is None else max(soc_min, target.soc_min_pct)
                soc_max = target.soc_max_pct if soc_max is None else min(soc_max, target.soc_max_pct)
                if preferred_w is None and target.preferred_power_w is not None:
                    preferred_w = target.preferred_power_w

            if soc_min is None or soc_max is None:
                continue
            if soc_min > soc_max:
                midpoint = (soc_min + soc_max) / 2.0
                _LOGGER.warning(
                    "SoC window conflict for battery %r: strategies produced "
                    "min=%.1f%% > max=%.1f%% — collapsing to midpoint %.1f%%",
                    name,
                    soc_min,
                    soc_max,
                    midpoint,
                )
                soc_min = soc_max = midpoint

            merged[name] = BatteryTarget(
                soc_min_pct=soc_min,
                soc_max_pct=soc_max,
                preferred_power_w=preferred_w,
            )
        return merged

    @staticmethod
    def _merge_grid_constraints(decisions: Sequence[Decision]) -> GridConstraint:
        max_import: float | None = None
        max_export: float | None = None
        for d in decisions:
            if d.grid_constraint.max_import_w is not None:
                max_import = (
                    d.grid_constraint.max_import_w
                    if max_import is None
                    else min(max_import, d.grid_constraint.max_import_w)
                )
            if d.grid_constraint.max_export_w is not None:
                max_export = (
                    d.grid_constraint.max_export_w
                    if max_export is None
                    else min(max_export, d.grid_constraint.max_export_w)
                )
        return GridConstraint(max_import_w=max_import, max_export_w=max_export)

    @staticmethod
    def _merge_load_priorities(decisions: Sequence[Decision]) -> dict[str, int]:
        """Return load priorities using the highest-authority strategy's opinion.

        The strategy list is ordered highest-to-lowest priority. For each load,
        the first (most authoritative) strategy that expresses an opinion wins.
        This preserves ordinal semantics: priority 1 always means 'most urgent'
        and is never diluted by averaging with lower-priority opinions.
        """
        merged: dict[str, int] = {}
        for decision in decisions:  # ordered: highest → lowest priority
            for load_name, priority in decision.load_priorities.items():
                if load_name not in merged:  # first opinion wins
                    merged[load_name] = priority
        return merged

    @staticmethod
    def _compose_rationale(decisions: Sequence[Decision]) -> str:
        parts = [d.rationale for d in decisions if d.rationale]
        return " | ".join(parts)
