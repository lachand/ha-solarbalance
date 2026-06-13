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
    grid_export_kwh: float = 0.0
    consumption_kwh: float = 0.0
    _day: date | None = field(default=None, repr=False)
    _last_ts: datetime | None = field(default=None, repr=False)

    def update(
        self,
        *,
        now: datetime,
        local_date: date,
        pv_w: float,
        grid_w: float,
        battery_w: float = 0.0,
    ) -> None:
        """Integrate one sample.

        Args:
            now: Timestamp of this sample (monotonic per tick).
            local_date: Local calendar date of ``now`` — drives the midnight reset.
            pv_w: Total PV power (W); only the positive part is integrated.
            grid_w: Grid power (W, positive = import); only import is integrated.
            battery_w: Aggregate battery power (W, positive = charging). Used to
                derive total house consumption ``pv + grid - battery``.
        """
        if self._day != local_date:
            self.pv_kwh = 0.0
            self.grid_import_kwh = 0.0
            self.grid_export_kwh = 0.0
            self.consumption_kwh = 0.0
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
        self.grid_export_kwh += max(0.0, -grid_w) * dt_h / 1000.0
        self.consumption_kwh += max(0.0, pv_w + grid_w - battery_w) * dt_h / 1000.0

    @property
    def day(self) -> date | None:
        """Local date the current totals belong to (None before the first sample)."""
        return self._day

    def restore(
        self,
        *,
        day: date,
        pv_kwh: float,
        grid_import_kwh: float,
        grid_export_kwh: float = 0.0,
        consumption_kwh: float = 0.0,
    ) -> None:
        """Seed persisted totals (e.g. after a restart).

        The next :meth:`update` re-seeds the timestamp; if ``day`` is no longer
        today it resets to zero, so a stale day cannot carry energy forward.
        """
        self._day = day
        self._last_ts = None
        self.pv_kwh = pv_kwh
        self.grid_import_kwh = grid_import_kwh
        self.grid_export_kwh = grid_export_kwh
        self.consumption_kwh = consumption_kwh
