"""Arbiter — combines decisions from ordered strategies into a single output.

Rules (see SPECIFICATIONS §6.1):
- `battery_targets`: the highest-priority opinion sets the central window;
  lower-priority strategies can only *narrow* the window, never widen it.
  `preferred_power_w` is taken from the highest-priority opinion.
- `grid_constraint`: intersection across all strategies (most restrictive wins).
- `load_priorities`: weighted average with exponential decay
  (priority 1 → 1.0, priority 2 → 0.5, priority 3 → 0.25, …).
- `rationale`: concatenated, prefixed with strategy name.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .models import BatteryTarget, Decision, GridConstraint
from .strategies.base import Strategy


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
            dominant_strategy=self._strategies[0].kind,
            per_strategy=per_strategy,
        )

    # ------------------------------------------------------------------ helpers

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
                # Inconsistent narrowing — collapse to the midpoint so downstream
                # controllers do not have to handle empty windows.
                midpoint = (soc_min + soc_max) / 2.0
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
        merged: dict[str, float] = {}
        weights: dict[str, float] = {}
        for rank, decision in enumerate(decisions):
            weight = 0.5**rank
            for load_name, priority in decision.load_priorities.items():
                merged[load_name] = merged.get(load_name, 0.0) + priority * weight
                weights[load_name] = weights.get(load_name, 0.0) + weight
        return {name: round(merged[name] / weights[name]) for name in merged}

    @staticmethod
    def _compose_rationale(decisions: Sequence[Decision]) -> str:
        parts = [d.rationale for d in decisions if d.rationale]
        return " | ".join(parts)
