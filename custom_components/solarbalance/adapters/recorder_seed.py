"""Seed the learned consumption profile from the recorder's long-term statistics.

Bootstraps the hour-of-day consumption profile from history so it is accurate from
day one for users who already have weeks of data, instead of waiting for the online
EMA to fill in. Reads the long-term **hourly mean** statistics (which survive the
recorder's state purge). Any failure is a silent no-op — online learning still
fills the profile over time.
"""

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..core.consumption_profile import ConsumptionProfile, mean_by_hour

_LOGGER = logging.getLogger(__name__)


async def seed_consumption_from_statistics(
    hass: HomeAssistant,
    statistic_id: str,
    profile: ConsumptionProfile,
    *,
    days: int = 14,
) -> int:
    """Seed the profile's still-unlearned hours from ``statistic_id`` hourly means.

    Returns the number of hour-of-day buckets seeded (0 on any failure).
    """
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period
    except ImportError:
        return 0

    end = dt_util.utcnow()
    start = end - timedelta(days=days)
    try:
        stats = await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            start,
            end,
            {statistic_id},
            "hour",
            None,
            {"mean"},
        )
    except Exception:  # recorder unavailable / API drift → online learning only
        _LOGGER.debug("Consumption seed: statistics query failed for %s", statistic_id)
        return 0

    rows = stats.get(statistic_id) or []
    pairs: list[tuple[int, float]] = []
    for row in rows:
        mean = row.get("mean")
        raw_start = row.get("start")
        if mean is None or raw_start is None:
            continue
        when = (
            dt_util.utc_from_timestamp(float(raw_start))
            if isinstance(raw_start, int | float)
            else raw_start
        )
        pairs.append((dt_util.as_local(when).hour, max(0.0, float(mean))))
    if not pairs:
        return 0
    seeded = profile.seed_missing(mean_by_hour(pairs))
    if seeded:
        _LOGGER.info("Consumption profile: seeded %d hour(s) from %s history", seeded, statistic_id)
    return seeded
