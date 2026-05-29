"""Peak-shaving strategy.

Caps grid import below a configurable threshold (typically a fraction of the
subscribed power). Discharges batteries to compensate when import would
otherwise exceed the cap.
"""

import logging

from ..models import Decision, GridConstraint, Snapshot, StrategyKind
from .base import Strategy

_LOGGER = logging.getLogger(__name__)


class PeakShavingStrategy(Strategy):
    """Limit grid import to a configured threshold."""

    kind = StrategyKind.PEAK_SHAVING.value

    def __init__(self, *args: object, max_import_w: float | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._max_import_w = max_import_w

    def compute(self, snapshot: Snapshot) -> Decision:
        """Apply import cap as a hard grid constraint.

        Logs a warning when the cap is currently exceeded but no battery has
        discharge headroom — the constraint is in effect but cannot be enforced.
        """
        if self._max_import_w is not None and snapshot.grid_power_w > self._max_import_w:
            battery_states = {b.device_name: b for b in snapshot.batteries}
            can_discharge = any(
                (state := battery_states.get(d.name)) is not None
                and state.available
                and state.soc_pct > float(d.battery.soc_min_pct) + 1.0
                for d in self.batteries
                if d.battery is not None
            )
            if not can_discharge:
                _LOGGER.warning(
                    "peak_shaving: import %.0f W exceeds cap %.0f W "
                    "but no battery has discharge headroom — constraint infeasible",
                    snapshot.grid_power_w,
                    self._max_import_w,
                )

        return Decision(
            grid_constraint=GridConstraint(max_import_w=self._max_import_w),
            rationale=f"peak_shaving: max_import={self._max_import_w}W",
        )
