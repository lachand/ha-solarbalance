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
