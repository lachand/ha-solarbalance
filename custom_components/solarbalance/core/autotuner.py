"""Supervisory auto-tuner that damps a regulation gain when it oscillates.

It watches a control signal each tick and counts **direction reversals** over a
rolling window. When the signal oscillates (pumping) it *loosens* the tuned value
(reduces it) quickly; when calm it *restores* the value toward the configured
default slowly. The value is bounded to ``[min_value, default]`` -- the tuner can
only make a loop **gentler** than configured, never more aggressive, so it is
safe to run on by default.

Used for the zero-injection ``kp`` and the SoC-equaliser step cap. Pure module --
no Home Assistant imports.
"""

from collections import deque


def _sign(x: float) -> int:
    if x > 0.0:
        return 1
    if x < 0.0:
        return -1
    return 0


class RegulationAutoTuner:
    """Adapt one gain from observed oscillation of a control signal.

    Args:
        default: Configured value; the upper bound and restore target.
        min_value: Hard floor when loosening.
        window_ticks: Rolling window (ticks) over which reversals are counted.
        adapt_every: Re-evaluate (and possibly adjust) every N ticks.
        osc_high: Reversals/window at or above which the value is loosened.
        osc_low: Reversals/window at or below which the value is restored.
        loosen_factor: Multiplier applied when loosening (<1).
        tighten_factor: Multiplier applied when restoring (>1).
    """

    def __init__(
        self,
        *,
        default: float,
        min_value: float,
        window_ticks: int = 30,
        adapt_every: int = 18,
        osc_high: int = 6,
        osc_low: int = 1,
        loosen_factor: float = 0.8,
        tighten_factor: float = 1.08,
    ) -> None:
        if not 0.0 < min_value <= default:
            raise ValueError("require 0 < min_value <= default")
        if window_ticks < 2 or adapt_every < 1:
            raise ValueError("window_ticks >= 2 and adapt_every >= 1 required")
        if not 0.0 < loosen_factor < 1.0 < tighten_factor:
            raise ValueError("require 0 < loosen_factor < 1 < tighten_factor")
        if not 0 <= osc_low < osc_high:
            raise ValueError("require 0 <= osc_low < osc_high")
        self._default = default
        self._min = min_value
        self._adapt_every = adapt_every
        self._osc_high = osc_high
        self._osc_low = osc_low
        self._loosen = loosen_factor
        self._tighten = tighten_factor
        self._value = default
        self._window = window_ticks
        self._signs: deque[int] = deque(maxlen=window_ticks)
        self._last: float | None = None
        self._ticks = 0

    @property
    def value(self) -> float:
        """Current tuned value (bounded to [min_value, default])."""
        return self._value

    def reset(self) -> None:
        """Restore the value to the configured default and clear history."""
        self._value = self._default
        self._signs.clear()
        self._last = None
        self._ticks = 0

    def step(self, signal: float) -> float:
        """Record one sample of the control signal; adapt on schedule.

        ``signal`` is the regulating quantity (e.g. the ZI correction or the
        equaliser offer); the tuner reacts to its **reversals**, so a steady
        ramp is "calm" and an alternating value is "oscillating".
        """
        if self._last is not None:
            self._signs.append(_sign(signal - self._last))
        self._last = signal
        self._ticks += 1
        if self._ticks >= self._adapt_every and len(self._signs) >= self._window:
            self._ticks = 0
            reversals = self._reversals()
            if reversals >= self._osc_high:
                self._value = max(self._min, self._value * self._loosen)
            elif reversals <= self._osc_low:
                self._value = min(self._default, self._value * self._tighten)
        return self._value

    def _reversals(self) -> int:
        reversals = 0
        prev = 0
        for s in self._signs:
            if s == 0:
                continue
            if prev != 0 and s != prev:
                reversals += 1
            prev = s
        return reversals
