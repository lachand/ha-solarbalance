"""Per-battery energy throughput: round-trip efficiency and equivalent cycles.

Two questions the fleet cannot answer from a spec sheet, because both drift with
age and use:

- **Round-trip efficiency** — of every kilowatt-hour put in, how much comes back
  out? The planner and the counterfactual assume a flat 90 %; a pack that has
  quietly fallen to 82 % makes every one of their sums a little wrong, and nothing
  measures it.
- **Equivalent full cycles** — how hard has the pack actually been worked? A vendor
  cycle count is the usual source, but most batteries here do not expose one, so
  their State-of-Health reads as *unknown* forever.

Both fall out of the same accounting. Integrating the battery power gives the
energy in and the energy out; the difference, once the charge still sitting in the
pack is subtracted, is the loss:

    in = out + stored_change + losses      =>      round_trip = out / (in - stored_change)

The ``stored_change`` correction is what makes this honest over any window: a pack
that ended fuller than it started has kept energy, not lost it, and dividing by
``in`` alone would understate the efficiency. With the correction the estimate is
exact energy accounting, gated only on enough throughput to be worth reporting.

Equivalent full cycles are the delivered energy over one usable capacity — the
standard throughput measure — and feed the existing SoH estimate when no vendor
cycle count exists.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Skip integration across a long gap (restart, outage) rather than booking a large
# bogus increment — same rule, same reason, as the daily energy accumulator.
_MAX_GAP_S = 1800.0

# Round-trip is only reported once enough energy has passed through that the
# residual measurement noise is small against it: the larger of an absolute floor
# and a few full charges of the pack.
_MIN_RT_KWH = 5.0
_MIN_RT_CAPACITY_MULT = 2.0


@dataclass(slots=True, frozen=True)
class BatteryEnergyStats:
    """What the throughput accounting says about one battery."""

    charge_in_kwh: float
    discharge_out_kwh: float
    equivalent_full_cycles: float | None
    """Delivered energy over one usable capacity; ``None`` without a capacity."""

    round_trip_pct: float | None
    """0-100, corrected for the charge still stored; ``None`` below the throughput
    floor, where the figure would be noise."""


@dataclass(slots=True)
class _Acc:
    charge_in_kwh: float = 0.0
    discharge_out_kwh: float = 0.0
    soc_start_pct: float | None = None
    soc_last_pct: float | None = None
    _last_ts: datetime | None = field(default=None, repr=False)


@dataclass(slots=True)
class BatteryEnergyTracker:
    """Accumulate charge-in / discharge-out energy per battery, across restarts."""

    _acc: dict[str, _Acc] = field(default_factory=dict)

    def observe(self, name: str, now: datetime, power_w: float, soc_pct: float | None) -> None:
        """Integrate one sample for a battery.

        Args:
            name: Battery device name.
            now: Timestamp of this sample (monotonic per tick).
            power_w: Battery power (positive = charging, negative = discharging).
            soc_pct: Current state of charge, or ``None`` when unavailable — the
                round-trip correction needs it, so a tick without it still books
                the energy but does not move the SoC reference.
        """
        acc = self._acc.get(name)
        if acc is None:
            acc = _Acc()
            self._acc[name] = acc
        if soc_pct is not None:
            if acc.soc_start_pct is None:
                acc.soc_start_pct = soc_pct
            acc.soc_last_pct = soc_pct

        last = acc._last_ts
        acc._last_ts = now
        if last is None:
            return
        dt_s = (now - last).total_seconds()
        if dt_s <= 0.0 or dt_s > _MAX_GAP_S:
            return
        dt_h = dt_s / 3600.0
        if power_w >= 0.0:
            acc.charge_in_kwh += power_w * dt_h / 1000.0
        else:
            acc.discharge_out_kwh += -power_w * dt_h / 1000.0

    def stats(self, name: str, *, usable_capacity_kwh: float) -> BatteryEnergyStats | None:
        """Summarise one battery, or ``None`` if it was never observed."""
        acc = self._acc.get(name)
        if acc is None:
            return None

        cycles: float | None = None
        if usable_capacity_kwh > 0:
            cycles = round(acc.discharge_out_kwh / usable_capacity_kwh, 2)

        round_trip: float | None = None
        floor = max(_MIN_RT_KWH, _MIN_RT_CAPACITY_MULT * usable_capacity_kwh)
        if acc.charge_in_kwh >= floor and acc.soc_start_pct is not None:
            net_stored = 0.0
            if usable_capacity_kwh > 0 and acc.soc_last_pct is not None:
                net_stored = (acc.soc_last_pct - acc.soc_start_pct) / 100.0 * usable_capacity_kwh
            denom = acc.charge_in_kwh - net_stored
            if denom > 0.0:
                round_trip = round(max(0.0, min(100.0, acc.discharge_out_kwh / denom * 100.0)), 1)

        return BatteryEnergyStats(
            charge_in_kwh=round(acc.charge_in_kwh, 3),
            discharge_out_kwh=round(acc.discharge_out_kwh, 3),
            equivalent_full_cycles=cycles,
            round_trip_pct=round_trip,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store; lifetime totals are worth keeping across restarts."""
        return {
            name: {
                "in": round(acc.charge_in_kwh, 4),
                "out": round(acc.discharge_out_kwh, 4),
                "soc_start": acc.soc_start_pct,
                "soc_last": acc.soc_last_pct,
            }
            for name, acc in self._acc.items()
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BatteryEnergyTracker":
        """Rebuild from a persisted dict; a malformed row is skipped, not fatal."""
        tracker = cls()
        if not isinstance(data, Mapping):
            return tracker
        for name, row in data.items():
            if not isinstance(row, Mapping):
                continue
            try:
                tracker._acc[str(name)] = _Acc(
                    charge_in_kwh=float(row.get("in", 0.0)),
                    discharge_out_kwh=float(row.get("out", 0.0)),
                    soc_start_pct=(
                        None if row.get("soc_start") is None else float(row["soc_start"])
                    ),
                    soc_last_pct=(None if row.get("soc_last") is None else float(row["soc_last"])),
                )
            except (TypeError, ValueError):
                continue
        return tracker
