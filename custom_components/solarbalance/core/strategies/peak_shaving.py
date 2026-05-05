"""Peak-shaving strategy.

Caps grid import below a configurable threshold (typically a fraction of the
subscribed power). Discharges batteries to compensate when import would
otherwise exceed the cap.
"""

from ..models import Decision, GridConstraint, Snapshot, StrategyKind
from .base import Strategy


class PeakShavingStrategy(Strategy):
    """Limit grid import to a configured threshold."""

    kind = StrategyKind.PEAK_SHAVING.value

    def __init__(self, *args: object, max_import_w: float | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._max_import_w = max_import_w

    def compute(self, snapshot: Snapshot) -> Decision:
        """Apply import cap as a hard grid constraint."""
        return Decision(
            grid_constraint=GridConstraint(max_import_w=self._max_import_w),
            rationale=f"peak_shaving: max_import={self._max_import_w}W",
        )
