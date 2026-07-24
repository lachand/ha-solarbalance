"""How much of an appliance cycle the sun would actually cover, and when to start it.

Given a learned cycle curve (:mod:`..appliance_cycles`) and the hourly PV and
house-consumption forecasts already maintained for the planner, this answers the
question the dashboard asks: *if I run the dishwasher now, what share of it is
solar — and would waiting help?*

The accounting is deliberately plain: for each hour, the surplus available to the
appliance is what the array makes beyond what the house is already drawing,
``max(0, pv - house)``. The appliance takes the smaller of what it wants and what
is spare; the rest is imported. Summed over the cycle that gives an energy share.

Two honesty rules are built in, because a confident wrong number here would send
someone to run a 2 kWh cycle off the grid:

* The house forecast must **not** already include the appliance, or its own draw
  would be counted as pre-existing load and the surplus understated.
* A cycle longer than the forecast horizon is reported on the hours actually
  covered, and ``truncated`` is set — the caller shows it as a partial answer
  rather than pretending the rest was solar.

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from dataclasses import dataclass

_HOURS_PER_DAY = 24


@dataclass(slots=True, frozen=True)
class SolarShare:
    """Outcome of running a cycle at a given start hour."""

    start_hour: int
    solar_kwh: float
    grid_kwh: float
    truncated: bool

    @property
    def total_kwh(self) -> float:
        """Total energy the cycle draws (kWh)."""
        return self.solar_kwh + self.grid_kwh

    @property
    def solar_fraction(self) -> float:
        """0..1 share of the cycle's energy covered by PV surplus."""
        total = self.total_kwh
        return 0.0 if total <= 0 else self.solar_kwh / total


def estimate_solar_share(
    curve_w: Sequence[float],
    duration_s: float,
    start_hour: int,
    pv_by_hour: Sequence[float],
    house_by_hour: Sequence[float],
) -> SolarShare:
    """Split a cycle's energy into solar-covered and grid-drawn kWh.

    Args:
        curve_w: The cycle's power curve, evenly spaced over its duration.
        duration_s: Cycle length (s).
        start_hour: Hour index into the forecasts at which the cycle starts.
        pv_by_hour: Forecast PV power (W) per hour, index 0 = the first forecast hour.
        house_by_hour: Forecast house consumption (W) per hour, **excluding this
            appliance** — counting it would understate the surplus.

    Returns:
        A :class:`SolarShare`. ``truncated`` marks a cycle running past the forecast.
    """
    if not curve_w or duration_s <= 0 or not pv_by_hour:
        return SolarShare(start_hour=start_hour, solar_kwh=0.0, grid_kwh=0.0, truncated=False)

    solar_kwh = 0.0
    grid_kwh = 0.0
    truncated = False
    steps = len(curve_w)
    step_s = duration_s / steps
    # Surplus is an hourly figure but several steps can fall in the same hour, so
    # track what each hour has left instead of offering it to every step.
    spare_wh: dict[int, float] = {}

    for i, power_w in enumerate(curve_w):
        offset_h = (i * step_s) / 3600.0
        hour = start_hour + int(offset_h)
        need_wh = max(0.0, power_w) * (step_s / 3600.0)
        if need_wh <= 0:
            continue
        if hour >= len(pv_by_hour):
            truncated = True
            grid_kwh += need_wh / 1000.0
            continue
        if hour not in spare_wh:
            house = house_by_hour[hour] if hour < len(house_by_hour) else 0.0
            spare_wh[hour] = max(0.0, pv_by_hour[hour] - house)
        take = min(need_wh, spare_wh[hour])
        spare_wh[hour] -= take
        solar_kwh += take / 1000.0
        grid_kwh += (need_wh - take) / 1000.0

    return SolarShare(
        start_hour=start_hour,
        solar_kwh=solar_kwh,
        grid_kwh=grid_kwh,
        truncated=truncated,
    )


def best_start(
    curve_w: Sequence[float],
    duration_s: float,
    pv_by_hour: Sequence[float],
    house_by_hour: Sequence[float],
    *,
    earliest_hour: int = 0,
    latest_hour: int | None = None,
) -> SolarShare | None:
    """Best start hour in a window, by solar share.

    Ties go to the **earliest** hour: with equal solar coverage there is no reason
    to make someone wait. Returns None when the window is empty.
    """
    if not curve_w or duration_s <= 0 or not pv_by_hour:
        return None
    last = len(pv_by_hour) - 1 if latest_hour is None else min(latest_hour, len(pv_by_hour) - 1)
    if last < earliest_hour:
        return None
    best: SolarShare | None = None
    for hour in range(max(0, earliest_hour), last + 1):
        share = estimate_solar_share(curve_w, duration_s, hour, pv_by_hour, house_by_hour)
        if best is None or share.solar_fraction > best.solar_fraction + 1e-9:
            best = share
    return best


def hours_from_now(hour_index: int, now_hour: int) -> int:
    """Wall-clock hour for a forecast index whose 0 is the current hour."""
    return (now_hour + hour_index) % _HOURS_PER_DAY
