"""Score how reliably each mapped entity actually reports.

Three of this week's incidents were link failures wearing an algorithm's clothes.
The PDL meter went silent for 38 minutes at sunrise on 2026-07-24 and the loop sat
in DEGRADED through the best light of the morning. A cloud battery stopped
publishing and the fleet target collapsed, which read as a control bug. Each time
the diagnosis took hours, because nothing recorded *how often a link answers* —
only whether it answered right now.

This module records exactly that, per entity, over a rolling 24 hours:

    availability %  ·  median age  ·  longest gap  ·  dropout count

Availability alone is the wrong headline. A meter that misses 3 % of samples,
scattered, costs nothing — the median filter absorbs it. A meter that misses the
same 3 % as **one 40-minute hole** stops the house regulating. So the score
penalises the longest gap on top of the availability, and a link with one long
outage scores far below a link with the same amount of scattered noise.

Storage is bucketed by hour rather than sample-by-sample: 24 counters per entity
instead of 8 640 timestamps, which keeps a restart-persistable footprint whatever
the tick rate. The cost is a median read off a coarse histogram, which is ample
for "is this link healthy" and never pretends to more precision than it has.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_WINDOW_HOURS = 24
_HOUR_S = 3600.0

# Upper edge of each age bucket (s); the last bucket is everything beyond.
_AGE_EDGES: tuple[float, ...] = (5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0)
_N_BUCKETS = len(_AGE_EDGES) + 1

# A gap this long is a total loss of control for the period it covers, so it costs
# the full gap penalty. Set from the 2026-07-24 outage: 38 min of blind sunrise.
_CRITICAL_GAP_S = 1800.0
# How many points of the score the longest gap can take away. Large enough that one
# real outage outranks any amount of scattered jitter, small enough that a link that
# is otherwise dead still scores worse than one that had a single bad half-hour.
_GAP_PENALTY = 40.0

# Below this, an entity has not been watched long enough for its score to mean
# anything, and reporting one would invite acting on noise.
_MIN_SAMPLES = 20


@dataclass(slots=True)
class _Bucket:
    """One hour of observations for one entity."""

    hour: int
    """Absolute hour index (``floor(epoch_s / 3600)``), so buckets roll off by age."""

    samples: int = 0
    fresh: int = 0
    dropouts: int = 0
    longest_gap_s: float = 0.0
    hist: list[int] = field(default_factory=lambda: [0] * _N_BUCKETS)


def _bucket_for(age_s: float) -> int:
    for i, edge in enumerate(_AGE_EDGES):
        if age_s <= edge:
            return i
    return _N_BUCKETS - 1


def _median_from_hist(hist: list[int]) -> float | None:
    """Median age (s) read off the histogram, or ``None`` when it is empty.

    Returns the *upper edge* of the bucket holding the median — an honest
    over-estimate rather than an interpolation the counts cannot support.
    """
    total = sum(hist)
    if total == 0:
        return None
    target = total / 2.0
    seen = 0
    for i, count in enumerate(hist):
        seen += count
        if seen >= target:
            return _AGE_EDGES[i] if i < len(_AGE_EDGES) else _AGE_EDGES[-1] * 2.0
    return None


@dataclass(slots=True, frozen=True)
class LinkStats:
    """What 24 hours of watching one entity says about it."""

    key: str
    samples: int
    available_pct: float
    median_age_s: float | None
    longest_gap_s: float
    dropouts: int
    score: float
    """0-100: availability, less a penalty for the longest continuous outage."""

    verdict: str
    """``healthy`` | ``flaky`` | ``unreliable`` | ``unknown`` (not enough samples)."""


@dataclass(slots=True)
class LinkHealth:
    """Rolling per-entity availability record.

    Args:
        stale_s: Age above which a reading counts as *not* fresh. Matches the
            reader's own staleness rule so the two agree on what "reporting" means.
    """

    stale_s: float = 300.0
    _buckets: dict[str, list[_Bucket]] = field(default_factory=dict)
    _gap_start_s: dict[str, float] = field(default_factory=dict)
    _last_fresh: dict[str, bool] = field(default_factory=dict)

    def observe(self, key: str, now_s: float, age_s: float | None) -> None:
        """Record one observation.

        Args:
            key: Stable label for the entity (``pdl/power``, ``stream_a/soc``…).
            now_s: Wall-clock epoch seconds. Drives which hourly bucket is written
                and how long a gap has lasted.
            age_s: Seconds since the entity last updated, or ``None`` when it has
                no usable state at all — which counts as a gap, not as a large age.
        """
        hour = int(now_s // _HOUR_S)
        bucket = self._bucket(key, hour)
        bucket.samples += 1

        fresh = age_s is not None and age_s <= self.stale_s
        was_fresh = self._last_fresh.get(key)
        self._last_fresh[key] = fresh

        if fresh:
            bucket.fresh += 1
            assert age_s is not None  # narrowed by `fresh`
            bucket.hist[_bucket_for(age_s)] += 1
            started = self._gap_start_s.pop(key, None)
            if started is not None:
                # Close the gap in the bucket where it *ended*, so a gap is only
                # ever counted once however many hours it spanned.
                bucket.longest_gap_s = max(bucket.longest_gap_s, now_s - started)
            return

        if was_fresh is not False:
            # First observation, or a fall from fresh: either way a gap opens here.
            bucket.dropouts += 1
            self._gap_start_s[key] = now_s
        started = self._gap_start_s.get(key)
        if started is not None:
            # Keep an in-flight gap visible: an outage still running is precisely
            # the one worth seeing, and waiting for it to end would hide it.
            bucket.longest_gap_s = max(bucket.longest_gap_s, now_s - started)

    def stats(self, key: str, now_s: float) -> LinkStats:
        """Summarise the last 24 hours for one entity."""
        buckets = self._live(key, now_s)
        samples = sum(b.samples for b in buckets)
        if samples == 0:
            return LinkStats(key, 0, 0.0, None, 0.0, 0, 0.0, "unknown")

        fresh = sum(b.fresh for b in buckets)
        available_pct = fresh / samples * 100.0
        longest_gap_s = max((b.longest_gap_s for b in buckets), default=0.0)
        dropouts = sum(b.dropouts for b in buckets)

        hist = [0] * _N_BUCKETS
        for b in buckets:
            for i, count in enumerate(b.hist):
                hist[i] += count

        penalty = _GAP_PENALTY * min(1.0, longest_gap_s / _CRITICAL_GAP_S)
        score = max(0.0, min(100.0, available_pct - penalty))

        if samples < _MIN_SAMPLES:
            verdict = "unknown"
        elif score >= 95.0:
            verdict = "healthy"
        elif score >= 70.0:
            verdict = "flaky"
        else:
            verdict = "unreliable"

        return LinkStats(
            key=key,
            samples=samples,
            available_pct=round(available_pct, 1),
            median_age_s=_median_from_hist(hist),
            longest_gap_s=round(longest_gap_s, 1),
            dropouts=dropouts,
            score=round(score, 1),
            verdict=verdict,
        )

    def summary(self, now_s: float) -> list[LinkStats]:
        """Every watched entity, worst score first — the order to read them in."""
        rows = [self.stats(key, now_s) for key in self._buckets]
        rows.sort(key=lambda s: (s.verdict == "unknown", s.score))
        return rows

    def worst(self, now_s: float) -> LinkStats | None:
        """The weakest link with a usable score, or ``None`` when none has one."""
        rated = [s for s in self.summary(now_s) if s.verdict != "unknown"]
        return rated[0] if rated else None

    def forget(self, keys: set[str]) -> None:
        """Drop entities no longer watched, so a reconfiguration doesn't leak rows."""
        for key in list(self._buckets):
            if key not in keys:
                del self._buckets[key]
                self._gap_start_s.pop(key, None)
                self._last_fresh.pop(key, None)

    def _bucket(self, key: str, hour: int) -> _Bucket:
        buckets = self._buckets.setdefault(key, [])
        if buckets and buckets[-1].hour == hour:
            return buckets[-1]
        bucket = _Bucket(hour=hour)
        buckets.append(bucket)
        # Keep one spare hour so a bucket only expires once it is fully outside
        # the window, rather than the moment its hour ticks over.
        del buckets[: max(0, len(buckets) - (_WINDOW_HOURS + 1))]
        return bucket

    def _live(self, key: str, now_s: float) -> list[_Bucket]:
        cutoff = int(now_s // _HOUR_S) - _WINDOW_HOURS
        return [b for b in self._buckets.get(key, []) if b.hour > cutoff]

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store.

        Worth persisting: the buckets are keyed by absolute hour, so a restart
        resumes the same 24-hour window instead of restarting the clock — and a
        restart is often exactly when someone goes looking for this.
        """
        return {
            "stale_s": self.stale_s,
            "links": {
                key: [
                    {
                        "hour": b.hour,
                        "samples": b.samples,
                        "fresh": b.fresh,
                        "dropouts": b.dropouts,
                        "gap": round(b.longest_gap_s, 1),
                        "hist": list(b.hist),
                    }
                    for b in buckets
                ]
                for key, buckets in self._buckets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LinkHealth":
        """Rebuild from a persisted dict; a malformed row is skipped, not fatal."""
        health = cls(stale_s=float(data.get("stale_s", 300.0)))
        links = data.get("links")
        if not isinstance(links, dict):
            return health
        for key, rows in links.items():
            if not isinstance(rows, list):
                continue
            restored: list[_Bucket] = []
            for row in rows:
                if not isinstance(row, dict) or "hour" not in row:
                    continue
                hist = row.get("hist")
                restored.append(
                    _Bucket(
                        hour=int(row["hour"]),
                        samples=int(row.get("samples", 0)),
                        fresh=int(row.get("fresh", 0)),
                        dropouts=int(row.get("dropouts", 0)),
                        longest_gap_s=float(row.get("gap", 0.0)),
                        hist=(
                            [int(x) for x in hist]
                            if isinstance(hist, list) and len(hist) == _N_BUCKETS
                            else [0] * _N_BUCKETS
                        ),
                    )
                )
            if restored:
                restored.sort(key=lambda b: b.hour)
                health._buckets[str(key)] = restored[-(_WINDOW_HOURS + 1) :]
        return health
