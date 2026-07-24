"""Reject grid readings that physics says cannot be true.

A grid meter occasionally reports a value the installation could not physically
have produced. Observed 2026-07-23 17:46: the meter read **-2032 W of export**
while PV was making 1638 W and the batteries were *charging* 1479 W — with the
house drawing nothing at all, the most that could have left the property was
``1638 - 1479 = 159 W``. The reading was impossible by more than 1.8 kW, and it
persisted two samples, so the rolling median let it through to the regulator.

The rule is an energy balance, not a threshold. Everything leaving the property
has to come from somewhere:

    export ≤ PV production + battery discharge

(and the symmetric bound on import, which is far looser: the grid can always
supply more, so only a wildly negative "import" is suspect there.) When a reading
breaks that budget by more than a tolerance, it is not information — it is a
sensor fault, and the honest response is to **hold the last trustworthy value**
rather than to let the loop act on a number that cannot exist.

Deliberately *not* a smoothing filter: it does nothing at all to plausible
readings, however noisy. `RollingMedian` and `AdaptiveVolatilityDamper` in
:mod:`.filters` handle noise; this handles impossibility, and runs before them so
the loop never sees the aberration in the first place.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass

# Headroom on the physical bound before a reading is called impossible. Covers
# unmetered generation, sampling skew between the meter and the inverters, and
# ordinary measurement error. Generous on purpose: a false rejection freezes the
# loop on a stale value, which is worse than letting a borderline reading through.
DEFAULT_TOLERANCE_W = 400.0


@dataclass(slots=True, frozen=True)
class PlausibilityResult:
    """Outcome of checking one grid reading."""

    grid_w: float
    """The value to use — the reading itself, or the held one when it was rejected."""

    rejected: bool
    max_export_w: float
    """Largest export the balance allows right now (positive number, diagnostic)."""

    reason: str
    """``ok`` | ``impossible_export`` | ``no_reference`` — why it was or wasn't held."""


def check_grid_reading(
    grid_w: float,
    *,
    pv_w: float,
    battery_w: float,
    last_valid_w: float | None,
    tolerance_w: float = DEFAULT_TOLERANCE_W,
) -> PlausibilityResult:
    """Validate a grid reading against what the installation can physically do.

    Args:
        grid_w: The raw reading (positive = import, negative = export).
        pv_w: Total PV production right now (W, ≥ 0).
        battery_w: Aggregate battery power (positive = charging, negative = discharging).
        last_valid_w: The last reading that passed, held when this one is rejected.
            With ``None`` (first tick) nothing can be held, so the reading is used
            as-is: an unverifiable start is better than refusing to start.
        tolerance_w: Headroom on the bound before calling a reading impossible.

    Returns:
        A :class:`PlausibilityResult` whose ``grid_w`` is safe to regulate on.
    """
    # What the property can push out = production, plus whatever the batteries are
    # discharging. A battery that is *charging* consumes part of the production, so
    # it lowers the ceiling — that is exactly the 2026-07-23 case.
    discharge_w = max(0.0, -battery_w)
    charge_w = max(0.0, battery_w)
    max_export_w = max(0.0, pv_w + discharge_w - charge_w)

    if grid_w >= 0:
        # Import: the grid is an effectively unbounded source, so there is no
        # comparable ceiling to check. Nothing to reject.
        return PlausibilityResult(
            grid_w=grid_w, rejected=False, max_export_w=max_export_w, reason="ok"
        )

    export_w = -grid_w
    if export_w <= max_export_w + tolerance_w:
        return PlausibilityResult(
            grid_w=grid_w, rejected=False, max_export_w=max_export_w, reason="ok"
        )

    if last_valid_w is None:
        # Nothing trustworthy to fall back on yet; flag it but do not block startup.
        return PlausibilityResult(
            grid_w=grid_w, rejected=False, max_export_w=max_export_w, reason="no_reference"
        )

    return PlausibilityResult(
        grid_w=last_valid_w,
        rejected=True,
        max_export_w=max_export_w,
        reason="impossible_export",
    )
