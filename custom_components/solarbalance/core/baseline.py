"""Night-window baseline (standby) consumption estimator.

The instantaneous ``baseline_consumption_w`` (grid + pv - battery - pilotable
loads) is noisy and includes transient appliance loads. For planning — notably
the evening battery-priority shedding — we want a *stable* estimate of the
house's standby floor (the "talon").

This estimator averages the instantaneous baseline over a quiet night window
(e.g. 02:00-05:00 local), when only standby loads are typically running. The
average is frozen as the talon once the window ends and held until the next
night refreshes it. The talon survives a restart (only an in-progress nightly
average is lost, which simply resumes next night).

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass, field
from datetime import date, time


@dataclass(slots=True)
class NightBaselineEstimator:
    """Average baseline consumption over a quiet night window (talon, W)."""

    window_start_h: int = 2
    window_end_h: int = 5
    talon_w: float | None = None
    _sum_w: float = field(default=0.0, repr=False)
    _count: int = field(default=0, repr=False)
    _accum_day: date | None = field(default=None, repr=False)

    def _in_window(self, t: time) -> bool:
        start = time(self.window_start_h % 24)
        end = time(self.window_end_h % 24)
        if start <= end:
            return start <= t < end
        # Overnight window (e.g. 22:00-05:00).
        return t >= start or t < end

    def update(self, *, local_time: time, local_date: date, baseline_w: float) -> None:
        """Feed one instantaneous baseline sample (clamped ≥ 0).

        Accumulates while inside the night window; finalises the talon on the
        first sample after the window closes.
        """
        sample = max(0.0, baseline_w)
        if self._in_window(local_time):
            if self._accum_day != local_date:
                self._sum_w = 0.0
                self._count = 0
                self._accum_day = local_date
            self._sum_w += sample
            self._count += 1
        elif self._count > 0:
            # Window just closed with samples collected — freeze the talon.
            self.talon_w = self._sum_w / self._count
            self._sum_w = 0.0
            self._count = 0
            self._accum_day = None

    def restore(self, talon_w: float | None) -> None:
        """Seed the last-known talon after a restart."""
        self.talon_w = talon_w
