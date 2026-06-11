"""Daily energy integration from instantaneous power.

When the user does not declare a vendor ``daily_energy_entity``, SolarBalance
integrates the power sensors itself (Riemann sum) to expose today's PV and grid
import energy. The accumulator resets at local midnight and ignores integration
across long gaps (restarts, outages) to avoid spurious jumps.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

# Skip integration across a gap longer than this (s): a restart or stale-entity
# outage would otherwise dump a large bogus energy increment.
_MAX_GAP_S = 1800.0


@dataclass(slots=True)
class DailyEnergyAccumulator:
    """Accumulate today's PV and grid-import energy (kWh) from power samples."""

    pv_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    _day: date | None = field(default=None, repr=False)
    _last_ts: datetime | None = field(default=None, repr=False)

    def update(self, *, now: datetime, local_date: date, pv_w: float, grid_w: float) -> None:
        """Integrate one sample.

        Args:
            now: Timestamp of this sample (monotonic per tick).
            local_date: Local calendar date of ``now`` — drives the midnight reset.
            pv_w: Total PV power (W); only the positive part is integrated.
            grid_w: Grid power (W, positive = import); only import is integrated.
        """
        if self._day != local_date:
            self.pv_kwh = 0.0
            self.grid_import_kwh = 0.0
            self._day = local_date
            self._last_ts = now
            return
        if self._last_ts is None:
            self._last_ts = now
            return
        dt_s = (now - self._last_ts).total_seconds()
        self._last_ts = now
        if dt_s <= 0.0 or dt_s > _MAX_GAP_S:
            return
        dt_h = dt_s / 3600.0
        self.pv_kwh += max(0.0, pv_w) * dt_h / 1000.0
        self.grid_import_kwh += max(0.0, grid_w) * dt_h / 1000.0
