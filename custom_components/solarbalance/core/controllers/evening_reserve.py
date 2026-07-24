"""Hold back enough charge for the evening instead of spending it at 16:00.

The batteries are usually emptied by whatever the afternoon happens to demand, and
the evening peak — the predictable one, when the sun is gone and the house is at its
busiest — is then met from the grid. The information needed to avoid that is already
being collected: the hour-of-day consumption profile knows what the evening costs,
and the PV forecast knows how much of it the sun will still cover.

This differs from the existing predictive steering in one decisive way: it does not
depend on a tariff. ``predictive_steering_w`` only acts when prices differ across the
day, so on a flat tariff it is inert and the planner's work goes unused. Keeping
energy for the evening is worth doing whatever the price, because it is the
difference between covering the peak from the battery or from the grid.

How the floor is set
--------------------
Over the evening window, only the part of the load the sun will *not* cover has to
come from storage::

    need = Σ over peak hours of max(0, house - pv)

That energy becomes a SoC floor held during the day and **released when the peak
starts** — a reserve that is never spent is just a smaller battery.

Two refusals are built in. The floor never exceeds a configurable share of the usable
capacity, so a large predicted evening cannot pin the whole pack and stop the
afternoon regulating at all. And the floor is never set below the battery's own
minimum, which stays the hard limit.

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# Below this the reserve is not worth the loss of afternoon flexibility.
_MIN_RESERVE_KWH = 0.1


@dataclass(slots=True, frozen=True)
class EveningReserve:
    """The floor to hold, and why."""

    active: bool
    reserve_kwh: float
    soc_floor_pct: float
    """SoC floor to apply now; equals the battery minimum when inactive."""

    reason: str
    """``disabled`` | ``in_peak`` | ``no_profile`` | ``nothing_needed`` | ``holding``"""


def evening_reserve(
    *,
    enabled: bool,
    hour: int,
    house_by_hour: Sequence[float] | None,
    pv_by_hour: Sequence[float] | None,
    usable_capacity_kwh: float,
    soc_min_pct: float,
    peak_start_hour: int = 18,
    peak_end_hour: int = 22,
    max_share: float = 0.6,
) -> EveningReserve:
    """Decide how much charge to hold back for the evening peak.

    Args:
        enabled: Master switch (opt-in: this withholds energy the afternoon could use).
        hour: Current local hour.
        house_by_hour: Learned consumption (W) indexed by hour of day, or ``None``.
        pv_by_hour: Forecast PV (W) indexed by hour of day, or ``None`` — treated as
            no production, which only makes the reserve larger.
        usable_capacity_kwh: Usable energy of the controllable fleet.
        soc_min_pct: The battery's own floor; the reserve never goes below it.
        peak_start_hour: First local hour of the evening window to cover.
        peak_end_hour: Hour the evening window ends (exclusive).
        max_share: Largest share of usable capacity the reserve may claim.

    Returns:
        An :class:`EveningReserve`. ``soc_floor_pct`` is always safe to apply.
    """
    if not enabled or usable_capacity_kwh <= 0:
        return EveningReserve(False, 0.0, soc_min_pct, "disabled")
    if house_by_hour is None or not house_by_hour:
        # Nothing learned yet: withholding energy on a guess would cost the afternoon
        # for no reason.
        return EveningReserve(False, 0.0, soc_min_pct, "no_profile")
    # Inside or past the peak the reserve has done its job and must be spendable.
    if hour >= peak_start_hour or hour >= peak_end_hour:
        return EveningReserve(False, 0.0, soc_min_pct, "in_peak")

    need_kwh = 0.0
    for h in range(peak_start_hour, peak_end_hour):
        house_w = house_by_hour[h % len(house_by_hour)]
        pv_w = 0.0
        if pv_by_hour and len(pv_by_hour) > 0:
            pv_w = pv_by_hour[h % len(pv_by_hour)]
        need_kwh += max(0.0, house_w - pv_w) / 1000.0

    if need_kwh < _MIN_RESERVE_KWH:
        return EveningReserve(False, 0.0, soc_min_pct, "nothing_needed")

    reserve_kwh = min(need_kwh, usable_capacity_kwh * max(0.0, min(1.0, max_share)))
    floor_pct = soc_min_pct + (reserve_kwh / usable_capacity_kwh) * 100.0
    floor_pct = min(100.0, max(soc_min_pct, floor_pct))
    return EveningReserve(True, reserve_kwh, floor_pct, "holding")
