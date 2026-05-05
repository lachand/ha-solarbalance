"""Backup strategy.

Maintains a configured SoC floor across all batteries to preserve autonomy
in case of grid outage. Refuses any discharge below the floor; lower-priority
strategies cannot override this constraint.
"""

from ..models import BatteryTarget, Decision, Snapshot, StrategyKind
from .base import Strategy


class BackupStrategy(Strategy):
    """Reserve a SoC floor for grid-outage autonomy."""

    kind = StrategyKind.BACKUP.value

    def __init__(self, *args: object, reserve_soc_pct: float = 30.0, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._reserve_soc_pct = reserve_soc_pct

    def compute(self, snapshot: Snapshot) -> Decision:
        """Force SoC floor across all batteries."""
        targets = {
            device.name: BatteryTarget(
                soc_min_pct=max(self._reserve_soc_pct, float(device.battery.soc_min_pct)),
                soc_max_pct=float(device.battery.soc_max_pct),
            )
            for device in self.batteries
            if device.battery is not None
        }
        return Decision(
            battery_targets=targets,
            rationale=f"backup: floor={self._reserve_soc_pct:.0f}%",
        )
