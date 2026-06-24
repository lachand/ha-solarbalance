"""Real-time PV-drop detector (a passing cloud).

Compares the current PV to the **peak of the last few samples**: a sudden dip
(a cloud edge) shows up as a large ``peak - current`` over that short window, while
a gradual evening decline never opens more than a small gap (so it does not fire).
The emitted drop magnitude (W) is the basis for a fast reaction (cover the lost PV
from the battery without waiting for the PI) and for an observability signal.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class PvDropDetector:
    """Detect a sharp PV drop by comparing to the recent peak."""

    threshold_w: float = 300.0
    window: int = 3  # samples to look back for the pre-drop peak (~window*tick s)
    _recent: list[float] = field(default_factory=list)

    def update(self, pv_w: float) -> float:
        """Feed the current PV (W); return the drop magnitude (W), 0 if none.

        ``drop = max(recent window) - pv``; reported only when it clears the
        threshold. A gradual decline keeps the window's peak close to ``pv`` (small
        gap); a sudden dip leaves a high recent peak (large gap) for ``window`` ticks.
        """
        peak = max(self._recent) if self._recent else pv_w
        self._recent.append(pv_w)
        if len(self._recent) > self.window:
            self._recent.pop(0)
        drop_w = peak - pv_w
        return drop_w if drop_w > self.threshold_w else 0.0

    @property
    def reference_w(self) -> float | None:
        """The recent PV peak (W) used as the drop reference, or None if no sample."""
        return max(self._recent) if self._recent else None
