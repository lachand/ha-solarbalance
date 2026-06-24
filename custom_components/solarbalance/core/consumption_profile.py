"""Learned hour-of-day background-consumption profile (predictive planning input).

24 hourly buckets, each a **cross-day EMA** of that hour's mean background
consumption. Intra-hour samples are averaged, then folded into the bucket at the
hour boundary, so each bucket is a multi-day-smoothed estimate of "typical
consumption at hour H". It replaces the planner's single flat night-talon so the
schedule anticipates the morning/evening peaks.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``,
seed from history via ``seed``.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_HOURS = 24


def mean_by_hour(samples: Iterable[tuple[int, float]]) -> dict[int, float]:
    """Mean value per hour-of-day (0-23) from ``(hour, value)`` samples."""
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for hour, value in samples:
        h = hour % _HOURS
        sums[h] = sums.get(h, 0.0) + value
        counts[h] = counts.get(h, 0) + 1
    return {h: sums[h] / counts[h] for h in counts}


@dataclass(slots=True)
class ConsumptionProfile:
    """Hour-of-day background consumption (W), learned online and/or seeded."""

    day_alpha: float = 0.3  # cross-day EMA weight (~3 effective days of memory)
    buckets: list[float | None] = field(default_factory=lambda: [None] * _HOURS)
    _cur_hour: int | None = None
    _sum_w: float = 0.0
    _count: int = 0

    def observe(self, hour: int, value_w: float) -> None:
        """Add one background-consumption sample for ``hour`` (0-23).

        Samples accumulate within an hour; the hour's mean is folded into its
        bucket (cross-day EMA) when the hour rolls over.
        """
        hour %= _HOURS
        if self._cur_hour is None:
            self._cur_hour = hour
        elif hour != self._cur_hour:
            self._commit()
            self._cur_hour = hour
        self._sum_w += value_w
        self._count += 1

    def _commit(self) -> None:
        if self._count == 0 or self._cur_hour is None:
            return
        mean = self._sum_w / self._count
        prev = self.buckets[self._cur_hour]
        self.buckets[self._cur_hour] = (
            mean if prev is None else prev + self.day_alpha * (mean - prev)
        )
        self._sum_w = 0.0
        self._count = 0

    def predict(self, hour: int) -> float | None:
        """Typical consumption (W) at ``hour`` (0-23), or None if never learned."""
        return self.buckets[hour % _HOURS]

    def by_hour(self, fallback_w: float) -> list[float]:
        """24 hour-of-day values; unknown hours filled with ``fallback_w``."""
        return [fallback_w if b is None else b for b in self.buckets]

    def seed(self, hour: int, value_w: float) -> None:
        """Set a bucket directly (e.g. from recorder history)."""
        self.buckets[hour % _HOURS] = value_w

    def seed_missing(self, means: Mapping[int, float]) -> int:
        """Fill only the still-unlearned hours from ``means``; return how many.

        Used to bootstrap from history without clobbering buckets already learned
        online (the persisted profile wins).
        """
        seeded = 0
        for hour, value in means.items():
            if self.buckets[hour % _HOURS] is None:
                self.buckets[hour % _HOURS] = value
                seeded += 1
        return seeded

    @property
    def learned_hours(self) -> int:
        """How many of the 24 hourly buckets have data (diagnostic)."""
        return sum(1 for b in self.buckets if b is not None)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store (only the buckets + alpha need persisting)."""
        return {"day_alpha": self.day_alpha, "buckets": list(self.buckets)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConsumptionProfile":
        """Rebuild from a persisted dict; tolerates missing/garbage fields."""
        prof = cls(day_alpha=float(data.get("day_alpha", 0.3)))
        buckets = data.get("buckets")
        if isinstance(buckets, list) and len(buckets) == _HOURS:
            prof.buckets = [None if b is None else float(b) for b in buckets]
        return prof
