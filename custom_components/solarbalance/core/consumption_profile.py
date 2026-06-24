"""Learned consumption profile (predictive planning input), by segment & hour.

Two day-segments — **weekday** and **weekend** — each with 24 hourly buckets that
are a **cross-day EMA** of that hour's mean background consumption. Weekends often
differ (home all day), so splitting them sharpens the plan. Intra-hour samples are
averaged, then folded into the bucket when the (segment, hour) rolls over.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``
(old flat 24-bucket payloads are migrated into both segments), seed from history
via ``seed_missing``.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_HOURS = 24
_WEEKDAY = "weekday"
_WEEKEND = "weekend"
_SEGMENTS = (_WEEKDAY, _WEEKEND)


def segment_for(weekday: int) -> str:
    """Map a Python weekday (Mon=0 … Sun=6) to a profile segment."""
    return _WEEKEND if weekday >= 5 else _WEEKDAY


def mean_by_hour(samples: Iterable[tuple[int, float]]) -> dict[int, float]:
    """Mean value per hour-of-day (0-23) from ``(hour, value)`` samples."""
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for hour, value in samples:
        h = hour % _HOURS
        sums[h] = sums.get(h, 0.0) + value
        counts[h] = counts.get(h, 0) + 1
    return {h: sums[h] / counts[h] for h in counts}


def _empty_buckets() -> dict[str, list[float | None]]:
    return {seg: [None] * _HOURS for seg in _SEGMENTS}


@dataclass(slots=True)
class ConsumptionProfile:
    """Background consumption (W) by day-segment and hour, learned and/or seeded."""

    day_alpha: float = 0.3  # cross-day EMA weight (~3 effective days of memory)
    buckets: dict[str, list[float | None]] = field(default_factory=_empty_buckets)
    _cur: tuple[str, int] | None = None
    _sum_w: float = 0.0
    _count: int = 0

    def observe(self, segment: str, hour: int, value_w: float) -> None:
        """Add one sample for ``(segment, hour)``; folds the previous on rollover."""
        key = (segment, hour % _HOURS)
        if self._cur is None:
            self._cur = key
        elif key != self._cur:
            self._commit()
            self._cur = key
        self._sum_w += value_w
        self._count += 1

    def _commit(self) -> None:
        if self._count == 0 or self._cur is None:
            return
        seg, hour = self._cur
        prev = self.buckets[seg][hour]
        mean = self._sum_w / self._count
        self.buckets[seg][hour] = mean if prev is None else prev + self.day_alpha * (mean - prev)
        self._sum_w = 0.0
        self._count = 0

    def predict(self, segment: str, hour: int) -> float | None:
        """Typical consumption (W) for ``(segment, hour)``, or None if unlearned."""
        return self.buckets[segment][hour % _HOURS]

    def by_hour(self, segment: str, fallback_w: float) -> list[float]:
        """24 hour-of-day values for ``segment``; unknown hours → ``fallback_w``."""
        return [fallback_w if b is None else b for b in self.buckets[segment]]

    def seed(self, segment: str, hour: int, value_w: float) -> None:
        """Set a bucket directly (e.g. from recorder history)."""
        self.buckets[segment][hour % _HOURS] = value_w

    def seed_missing(self, segment: str, means: Mapping[int, float]) -> int:
        """Fill only the still-unlearned hours of ``segment``; return how many."""
        seeded = 0
        for hour, value in means.items():
            if self.buckets[segment][hour % _HOURS] is None:
                self.buckets[segment][hour % _HOURS] = value
                seeded += 1
        return seeded

    @property
    def learned_hours(self) -> int:
        """Total learned buckets across all segments (diagnostic)."""
        return sum(1 for seg in _SEGMENTS for b in self.buckets[seg] if b is not None)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store."""
        return {
            "day_alpha": self.day_alpha,
            "buckets": {s: list(self.buckets[s]) for s in _SEGMENTS},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConsumptionProfile":
        """Rebuild from a persisted dict; migrate the old flat 24-bucket format."""
        prof = cls(day_alpha=float(data.get("day_alpha", 0.3)))
        raw = data.get("buckets")
        if isinstance(raw, dict):
            for seg in _SEGMENTS:
                col = raw.get(seg)
                if isinstance(col, list) and len(col) == _HOURS:
                    prof.buckets[seg] = [None if b is None else float(b) for b in col]
        elif isinstance(raw, list) and len(raw) == _HOURS:
            # Old single-segment payload → seed both weekday and weekend with it.
            migrated = [None if b is None else float(b) for b in raw]
            prof.buckets = {seg: list(migrated) for seg in _SEGMENTS}
        return prof
