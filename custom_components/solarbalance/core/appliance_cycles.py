"""Learned power curves of appliance cycles (washing machine, dishwasher…).

A washing machine or a dishwasher is not a statistical process — it is a state
machine that replays a stereotyped power curve: fill, heat (~1.8 kW), wash at a
low circulation power (~75 W), rinse, spin. Knowing that curve is what lets the
panel answer "if I start it now, how much of it will the sun actually cover?".

Why a template library and not a model
--------------------------------------
The data is tiny (tens of cycles) and the signal is deterministic, so nearest-
neighbour matching on the recorded curves beats anything fitted: it needs no
dependency, stays interpretable ("this looks like your 40° mix cycle"), and
degrades safely — below a confidence threshold it simply predicts nothing.

Two design points earned from real data
---------------------------------------
* **Closing a cycle on a gap, not on zero.** A real dishwasher cycle spends an
  hour around 75 W between two 1.8 kW heating bursts, and dips to ~1 W several
  times mid-run. A cycle therefore ends only after the power stays under
  ``idle_w`` for a whole ``idle_gap_s``, or those dips would split one cycle into
  several bogus ones.
* **The program label arrives late, and that is fine.** Appliance integrations
  identify the program well into the run (observed: two hours in) — useless to
  *predict* with, but perfectly good to *file* a finished cycle under. So the
  label is read at close time and only groups templates; matching itself runs on
  the power prefix and never depends on it.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Resolution of a stored curve. 24 steps over a 2 h cycle is one point per 5 min —
# enough to place the heating bursts, small enough to keep the Store payload tiny.
_CURVE_STEPS = 24
_MAX_TEMPLATES = 8  # per (appliance, program); oldest dropped first
UNKNOWN_PROGRAM = "unknown"


def _median(values: Sequence[float]) -> float:
    """Median — used instead of a mean so one aborted cycle cannot skew a summary."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def resample(samples: Sequence[tuple[float, float]], steps: int = _CURVE_STEPS) -> list[float]:
    """Average ``(elapsed_s, power_w)`` samples into ``steps`` equal-time buckets.

    Averaging (rather than picking) keeps a short heating burst visible in its
    bucket instead of being missed between two sampling instants.
    """
    if not samples or steps <= 0:
        return [0.0] * max(0, steps)
    span = samples[-1][0] - samples[0][0]
    if span <= 0:
        return [samples[-1][1]] * steps
    start = samples[0][0]
    sums = [0.0] * steps
    counts = [0] * steps
    for elapsed, power in samples:
        idx = int((elapsed - start) / span * steps)
        idx = min(steps - 1, max(0, idx))
        sums[idx] += power
        counts[idx] += 1
    out: list[float] = []
    last = 0.0
    for i in range(steps):
        if counts[i]:
            last = sums[i] / counts[i]
        out.append(last)  # carry the previous level across an empty bucket
    return out


@dataclass(slots=True, frozen=True)
class CycleTemplate:
    """One completed cycle, stored compactly."""

    duration_s: float
    energy_kwh: float
    curve_w: tuple[float, ...]

    def power_at(self, fraction: float) -> float:
        """Power (W) at ``fraction`` (0..1) through the cycle."""
        if not self.curve_w:
            return 0.0
        idx = int(max(0.0, min(1.0, fraction)) * (len(self.curve_w) - 1))
        return self.curve_w[idx]


@dataclass(slots=True, frozen=True)
class CycleSummary:
    """Typical cycle of one appliance (what the dashboard shows)."""

    program: str
    samples: int
    duration_s: float
    energy_kwh: float
    curve_w: tuple[float, ...]


@dataclass(slots=True, frozen=True)
class CycleMatch:
    """Best-matching template for a cycle in progress."""

    template: CycleTemplate
    program: str
    confidence: float  # 0..1; below the caller's threshold, do not predict


@dataclass(slots=True)
class _Running:
    """A cycle being recorded."""

    started_at: float
    samples: list[tuple[float, float]] = field(default_factory=list)
    energy_ws: float = 0.0
    last_t: float | None = None
    idle_since: float | None = None


@dataclass(slots=True)
class ApplianceCycles:
    """Records appliance cycles and matches a running one against past ones."""

    idle_w: float = 15.0  # below this the appliance counts as off
    idle_gap_s: float = 300.0  # …and must stay so this long to close the cycle
    min_duration_s: float = 300.0  # shorter runs are noise, not cycles
    min_energy_kwh: float = 0.05
    templates: dict[str, dict[str, list[CycleTemplate]]] = field(default_factory=dict)
    _running: dict[str, _Running] = field(default_factory=dict)

    # ---------------------------------------------------------------- recording

    def observe(self, name: str, t: float, power_w: float) -> CycleTemplate | None:
        """Feed one sample (``t`` in seconds, monotonic). Returns a closed cycle, if any.

        Call every tick. The appliance is considered running from the first sample
        above ``idle_w``; the cycle closes once it has been continuously under it
        for ``idle_gap_s`` — never on a single dip, which real cycles are full of.
        """
        run = self._running.get(name)
        if run is None:
            if power_w <= self.idle_w:
                return None
            self._running[name] = _Running(started_at=t, samples=[(t, power_w)], last_t=t)
            return None

        if run.last_t is not None and t > run.last_t:
            run.energy_ws += power_w * (t - run.last_t)
        run.last_t = t
        run.samples.append((t, power_w))

        if power_w > self.idle_w:
            run.idle_since = None
            return None
        if run.idle_since is None:
            run.idle_since = t
        elif t - run.idle_since >= self.idle_gap_s:
            return self.close(name, at=run.idle_since)
        return None

    def close(
        self, name: str, *, program: str | None = None, at: float | None = None
    ) -> CycleTemplate | None:
        """End the running cycle and file it under ``program``.

        ``program`` is read at close time on purpose: appliance integrations only
        identify it late in the run, which is useless for prediction but perfectly
        good for filing. Unlabelled cycles land in ``unknown`` and still work.
        """
        run = self._running.pop(name, None)
        if run is None:
            return None
        end = at if at is not None else (run.last_t or run.started_at)
        duration = end - run.started_at
        # Trim the trailing idle tail so it doesn't stretch the stored duration.
        active = [s for s in run.samples if s[0] <= end]
        energy_kwh = run.energy_ws / 3_600_000.0
        if duration < self.min_duration_s or energy_kwh < self.min_energy_kwh or not active:
            return None  # a blip, not a cycle
        template = CycleTemplate(
            duration_s=duration,
            energy_kwh=energy_kwh,
            curve_w=tuple(resample(active)),
        )
        key = program or UNKNOWN_PROGRAM
        bucket = self.templates.setdefault(name, {}).setdefault(key, [])
        bucket.append(template)
        del bucket[:-_MAX_TEMPLATES]
        return template

    def add_template(
        self, name: str, template: CycleTemplate, *, program: str | None = None
    ) -> None:
        """Insert a template directly (used when seeding from recorder history)."""
        bucket = self.templates.setdefault(name, {}).setdefault(program or UNKNOWN_PROGRAM, [])
        bucket.append(template)
        del bucket[:-_MAX_TEMPLATES]

    def is_running(self, name: str) -> bool:
        """True while a cycle is being recorded for this appliance."""
        return name in self._running

    def elapsed_s(self, name: str, now: float) -> float | None:
        """Seconds since the running cycle started, or None."""
        run = self._running.get(name)
        return None if run is None else now - run.started_at

    # ----------------------------------------------------------------- querying

    def summary(self, name: str, program: str | None = None) -> CycleSummary | None:
        """Typical cycle: median duration/energy and median curve, or None if unlearned."""
        by_program = self.templates.get(name) or {}
        groups = {program: by_program.get(program, [])} if program is not None else by_program
        best_key: str | None = None
        best: list[CycleTemplate] = []
        for key, items in groups.items():
            if len(items) > len(best):
                best_key, best = key, items
        if not best or best_key is None:
            return None
        steps = len(best[0].curve_w)
        curve = tuple(
            _median([t.curve_w[i] for t in best if i < len(t.curve_w)]) for i in range(steps)
        )
        return CycleSummary(
            program=best_key,
            samples=len(best),
            duration_s=_median([t.duration_s for t in best]),
            energy_kwh=_median([t.energy_kwh for t in best]),
            curve_w=curve,
        )

    def match(self, name: str, prefix: Sequence[tuple[float, float]]) -> CycleMatch | None:
        """Best template for a cycle in progress, from its power prefix so far.

        Compares the observed prefix with the same *elapsed-time* span of each
        template and scores it by mean absolute error, normalised by the template's
        own peak so a 1.8 kW appliance is not judged on the same scale as a 100 W
        one. ``confidence`` is 1 at a perfect match and 0 once the error reaches
        the peak — the caller decides what is good enough.
        """
        by_program = self.templates.get(name) or {}
        if not by_program or len(prefix) < 2:
            return None
        elapsed = prefix[-1][0] - prefix[0][0]
        if elapsed <= 0:
            return None
        observed = resample(prefix)
        best: CycleMatch | None = None
        for program, items in by_program.items():
            for template in items:
                if template.duration_s <= 0 or not template.curve_w:
                    continue
                covered = min(1.0, elapsed / template.duration_s)
                steps = max(1, int(covered * len(observed)))
                peak = max(template.curve_w) or 1.0
                err = 0.0
                for i in range(steps):
                    err += abs(observed[i] - template.power_at((i / len(observed)) * covered))
                score = max(0.0, 1.0 - (err / steps) / peak)
                if best is None or score > best.confidence:
                    best = CycleMatch(template=template, program=program, confidence=score)
        return best

    @property
    def learned_cycles(self) -> int:
        """Total stored templates across every appliance (diagnostic)."""
        return sum(len(v) for by_prog in self.templates.values() for v in by_prog.values())

    # -------------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store (running cycles are deliberately not persisted)."""
        return {
            "templates": {
                name: {
                    program: [
                        {
                            "duration_s": t.duration_s,
                            "energy_kwh": t.energy_kwh,
                            "curve_w": list(t.curve_w),
                        }
                        for t in items
                    ]
                    for program, items in by_program.items()
                }
                for name, by_program in self.templates.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ApplianceCycles":
        """Rebuild from a persisted dict, skipping anything malformed."""
        out = cls()
        raw = data.get("templates")
        if not isinstance(raw, dict):
            return out
        for name, by_program in raw.items():
            if not isinstance(by_program, dict):
                continue
            for program, items in by_program.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    curve = item.get("curve_w")
                    if not isinstance(curve, list) or not curve:
                        continue
                    out.add_template(
                        name,
                        CycleTemplate(
                            duration_s=float(item.get("duration_s", 0.0)),
                            energy_kwh=float(item.get("energy_kwh", 0.0)),
                            curve_w=tuple(float(x) for x in curve),
                        ),
                        program=str(program),
                    )
        return out
