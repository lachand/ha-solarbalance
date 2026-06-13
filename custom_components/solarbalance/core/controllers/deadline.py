"""Deadline (departure-time) charge guarantee.

A load with a ``deadline_constraint`` must have received ``kwh_required`` by a
given time of day (e.g. "10 kWh in the car by 07:00"). Solar-following or
fast-charge logic may delay charging; this controller makes sure the deadline is
still met by forcing a grid-backed charge once we reach the *latest safe start*.

At each tick:

    remaining = max(0, kwh_required - delivered_today)
    hours_left = time until the next occurrence of before_time
    needed_w  = remaining * 1000 / hours_left

When ``needed_w`` approaches the charger's max power (``urgency`` margin), there
is no longer slack to wait for sun, so we force charging at full power. Until
then the decision is *not* forcing and the normal solar/fast-charge logic runs.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

_DEFAULT_URGENCY = 0.9


@dataclass(slots=True, frozen=True)
class DeadlineDecision:
    """Outcome of one deadline evaluation for a load."""

    force: bool  # force a grid-backed charge now to meet the deadline
    target_w: float
    remaining_kwh: float
    hours_left: float
    needed_w: float
    reason: str


def _next_occurrence(now: datetime, hhmm: str) -> datetime:
    """Next datetime matching ``HH:MM`` at or after ``now`` (today or tomorrow)."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def evaluate_deadline(
    *,
    now: datetime,
    before_time: str,
    required_kwh: float,
    delivered_kwh: float,
    max_charge_w: float,
    urgency: float = _DEFAULT_URGENCY,
) -> DeadlineDecision:
    """Decide whether the deadline forces a grid-backed charge now.

    Args:
        now: Current local datetime.
        before_time: Target time of day ``HH:MM`` to have ``required_kwh`` by.
        required_kwh: Energy that must be delivered before ``before_time``.
        delivered_kwh: Energy already delivered toward this deadline today.
        max_charge_w: The charger's maximum power (W).
        urgency: Force when ``needed_w >= max_charge_w * urgency``.
    """
    remaining_kwh = max(0.0, required_kwh - delivered_kwh)
    deadline = _next_occurrence(now, before_time)
    hours_left = max(0.0, (deadline - now).total_seconds() / 3600.0)

    if remaining_kwh <= 0.0:
        reason = "satisfied"
        needed_w = 0.0
        force = False
    elif hours_left <= 0.0:
        reason = "overdue"
        needed_w = float("inf")
        force = True
    else:
        needed_w = remaining_kwh * 1000.0 / hours_left
        force = max_charge_w > 0.0 and needed_w >= max_charge_w * urgency
        reason = "forcing" if force else "on_track"

    return DeadlineDecision(
        force=force,
        target_w=max_charge_w if force else 0.0,
        remaining_kwh=remaining_kwh,
        hours_left=hours_left,
        needed_w=needed_w,
        reason=reason,
    )
