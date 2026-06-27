"""Night-window baseline (standby) consumption estimator.

The instantaneous ``baseline_consumption_w`` (grid + pv - battery - pilotable
loads) is noisy and includes transient appliance loads. For planning — notably
the evening battery-priority shedding — we want a *stable* estimate of the
house's standby floor (the "talon").

This estimator averages the instantaneous baseline over a quiet night window
(e.g. 02:00-05:00 local), when only standby loads are typically running.

A big *unmanaged* night load (an EV charging, a dishwasher on a night tariff) can
fall inside that window and inflate the average — which made the evening shed think
no PV was left for the batteries and shed loads even at 90 %. So the nightly average
is not frozen as the talon directly: the talon **drops immediately** to a cleaner
(lower) night but **rises at most ``rise_cap_w`` per night**. A one-off EV night
therefore barely nudges the talon, and the next clean night snaps it back to the true
standby floor. The talon survives a restart (only an in-progress nightly average is
lost, which simply resumes next night).

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass, field
from datetime import date, time

# A night's average may raise the talon by at most this (W); it may drop freely.
# Caps the damage from an occasional big unmanaged night load (e.g. EV charging).
_TALON_RISE_CAP_W = 50.0


@dataclass(slots=True)
class NightBaselineEstimator:
    """Robust standby baseline over a quiet night window (talon, W)."""

    window_start_h: int = 2
    window_end_h: int = 5
    talon_w: float | None = None
    rise_cap_w: float = _TALON_RISE_CAP_W
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
            # Window just closed with samples collected. Drop freely to a cleaner
            # (lower) night, but rise at most rise_cap_w so a one-off EV/appliance
            # night cannot inflate the standby floor.
            nightly_w = self._sum_w / self._count
            if self.talon_w is None or nightly_w < self.talon_w:
                self.talon_w = nightly_w
            else:
                self.talon_w = min(nightly_w, self.talon_w + self.rise_cap_w)
            self._sum_w = 0.0
            self._count = 0
            self._accum_day = None

    def restore(self, talon_w: float | None) -> None:
        """Seed the last-known talon after a restart."""
        self.talon_w = talon_w
