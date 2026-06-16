"""Longevity strategy.

Penalises behaviours that shorten battery life: deep discharges, full charges,
and high C-rates. The comfort window is narrowed versus the user's absolute
bounds, differentiated by chemistry — see SPECIFICATIONS §6.1.

Default longevity windows:
- LiFePO4 : 20 % - 90 %  (most tolerant chemistry)
- NMC      : 20 % - 85 %
- Lead-acid: 30 % - 80 %
- Other    : 20 % - 85 %  (conservative)
"""

from ..models import BatteryTarget, Chemistry, Decision, Snapshot, StrategyKind
from .base import Strategy

# Comfort window shrinkage per chemistry [soc_min_pct, soc_max_pct]
_CHEMISTRY_WINDOW: dict[Chemistry, tuple[float, float]] = {
    Chemistry.LIFEPO4: (20.0, 90.0),
    Chemistry.NMC: (20.0, 85.0),
    Chemistry.LEADACID: (30.0, 80.0),
    Chemistry.OTHER: (20.0, 85.0),
}


class LongevityStrategy(Strategy):
    """Narrow the SoC comfort window per chemistry to extend battery life."""

    kind = StrategyKind.LONGEVITY.value

    def __init__(
        self,
        *args: object,
        override_soc_min_pct: float | None = None,
        override_soc_max_pct: float | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._override_min = override_soc_min_pct
        self._override_max = override_soc_max_pct

    def compute(self, snapshot: Snapshot) -> Decision:
        """Narrow the SoC window for all batteries according to their chemistry."""
        targets: dict[str, BatteryTarget] = {}
        notes: list[str] = []

        for device in self.batteries:
            battery = device.battery
            assert battery is not None

            default_min, default_max = _CHEMISTRY_WINDOW[battery.chemistry]
            lon_min = self._override_min if self._override_min is not None else default_min
            lon_max = self._override_max if self._override_max is not None else default_max

            # Never widen beyond the user's absolute bounds.
            effective_min = max(lon_min, float(battery.soc_min_pct))
            effective_max = min(lon_max, float(battery.soc_max_pct))

            targets[device.name] = BatteryTarget(
                soc_min_pct=effective_min,
                soc_max_pct=effective_max,
            )
            notes.append(
                f"{device.name}({battery.chemistry})=[{effective_min:.0f}%,{effective_max:.0f}%]"
            )

        return Decision(
            battery_targets=targets,
            rationale=f"longevity: {', '.join(notes)}" if notes else "longevity: no batteries",
        )
