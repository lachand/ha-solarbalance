"""Revenue-max strategy.

Maximises revenue from grid export when the export price exceeds the
opportunity cost of stored energy (forward import price). Disabled by
default in zero-injection setups.
"""

from ..models import Decision, Snapshot, StrategyKind
from .base import Strategy


class RevenueMaxStrategy(Strategy):
    """Prefer export over storage when economically advantageous."""

    kind = StrategyKind.REVENUE_MAX.value

    def compute(self, snapshot: Snapshot) -> Decision:
        """Compute decision (placeholder for v1.5)."""
        return Decision(rationale="revenue_max: not yet implemented")
