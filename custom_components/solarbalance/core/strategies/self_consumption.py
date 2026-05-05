"""Self-consumption strategy.

Maximises local consumption of PV production:
- when there is PV surplus, allocate it to charging batteries (preferred targets ↑);
- when there is grid import, allocate batteries to discharge (preferred targets ↓);
- forbids grid export by default (zero-injection-friendly).
"""

from ..models import (
    BatteryTarget,
    Decision,
    GridConstraint,
    Snapshot,
    StrategyKind,
)
from .base import Strategy


class SelfConsumptionStrategy(Strategy):
    """Charge on PV surplus, discharge on grid import."""

    kind = StrategyKind.SELF_CONSUMPTION.value

    def compute(self, snapshot: Snapshot) -> Decision:
        battery_targets: dict[str, BatteryTarget] = {}

        net_grid = snapshot.grid_power_w
        # Negative net_grid = exporting. We want batteries to absorb that.
        # Positive net_grid = importing. We want batteries to provide that.
        # The arbiter and the balancing controller turn these intents into
        # per-battery setpoints.
        for device in self.batteries:
            assert device.battery is not None  # checked by self.batteries
            target = BatteryTarget(
                soc_min_pct=float(device.battery.soc_min_pct),
                soc_max_pct=float(device.battery.soc_max_pct),
                preferred_power_w=-net_grid if abs(net_grid) > 1.0 else 0.0,
            )
            battery_targets[device.name] = target

        rationale = (
            f"net_grid={net_grid:+.0f}W → "
            f"{'charging' if net_grid < 0 else 'discharging' if net_grid > 0 else 'idle'}"
        )

        return Decision(
            battery_targets=battery_targets,
            grid_constraint=GridConstraint(max_export_w=0.0),
            load_priorities={},
            confidence=1.0,
            rationale=rationale,
        )
