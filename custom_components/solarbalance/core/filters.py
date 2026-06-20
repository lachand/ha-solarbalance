"""Small signal filters used to clean noisy meter readings.

Pure module — no Home Assistant imports.
"""

from collections import deque
from statistics import median


class RollingMedian:
    """Median over a sliding window of the last ``window`` samples.

    A median rejects single-sample outliers (sensor dropouts, brief load steps)
    far better than a mean, while lagging a *sustained* change by at most
    ``window // 2`` samples. ``window=1`` is a pass-through (no filtering).
    """

    def __init__(self, window: int) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self._buf: deque[float] = deque(maxlen=window)

    def update(self, value: float) -> float:
        """Append ``value`` and return the median of the current window."""
        self._buf.append(value)
        return float(median(self._buf))


class AdaptiveVolatilityDamper:
    """Low-pass that smooths *more* when the signal is volatile.

    Motor-type loads (a washing machine, a pump) swing too fast for a battery to
    follow; chasing them makes the regulation yoyo. This damper feeds the loop a
    signal that tracks the **slow average** while letting the grid absorb the fast
    swings: it measures volatility as an EMA of the absolute tick-to-tick change
    and uses it to scale the smoothing factor.

    - Calm (volatility ~0): ``calm_alpha`` -> light smoothing, responsive.
    - Volatile (volatility >= ``ref_w``): ``volatile_alpha`` -> heavy smoothing,
      the output barely moves so the battery holds the average.

    Unlike a plain low-pass, it does **not** lag genuine slow load changes (those
    have low tick-to-tick volatility, so smoothing stays light).
    """

    def __init__(
        self,
        *,
        calm_alpha: float = 0.8,
        volatile_alpha: float = 0.1,
        ref_w: float = 300.0,
        volatility_alpha: float = 0.3,
    ) -> None:
        if not 0.0 < volatile_alpha <= calm_alpha <= 1.0:
            raise ValueError("require 0 < volatile_alpha <= calm_alpha <= 1")
        if ref_w <= 0:
            raise ValueError("ref_w must be strictly positive")
        if not 0.0 < volatility_alpha <= 1.0:
            raise ValueError("volatility_alpha must be in (0, 1]")
        self._calm_alpha = calm_alpha
        self._volatile_alpha = volatile_alpha
        self._ref_w = ref_w
        self._vol_alpha = volatility_alpha
        self._smoothed: float | None = None
        self._prev: float | None = None
        self._volatility = 0.0

    @property
    def volatility_w(self) -> float:
        """Current volatility estimate (EMA of |tick-to-tick change|, W)."""
        return self._volatility

    def update(self, value: float) -> float:
        """Feed a raw value, return the volatility-smoothed value."""
        if self._smoothed is None or self._prev is None:
            self._smoothed = value
            self._prev = value
            return value
        self._volatility += self._vol_alpha * (abs(value - self._prev) - self._volatility)
        self._prev = value
        frac = min(1.0, self._volatility / self._ref_w)
        alpha = self._calm_alpha + (self._volatile_alpha - self._calm_alpha) * frac
        self._smoothed += alpha * (value - self._smoothed)
        return self._smoothed
