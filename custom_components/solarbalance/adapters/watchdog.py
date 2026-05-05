"""Watchdog: detect stale HA entities and report degraded status.

Each tick the coordinator calls ``EntityWatchdog.check()`` with the lists of
critical and monitored entity IDs.  A *critical* entity (e.g. the PDL meter)
going stale triggers an automatic switch to ``HemsMode.DEGRADED``.
Non-critical stale entities are logged as warnings but do not degrade the mode.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S: int = 300  # 5 minutes


@dataclass
class WatchdogReport:
    """Outcome of one watchdog pass."""

    stale_entities: list[str] = field(default_factory=list)
    critical_stale: list[str] = field(default_factory=list)

    @property
    def is_degraded(self) -> bool:
        """True if any critical entity is stale or missing."""
        return bool(self.critical_stale)


class EntityWatchdog:
    """Check HA entity last-update timestamps and flag stale entities."""

    def __init__(self, hass: HomeAssistant, timeout_s: int = _DEFAULT_TIMEOUT_S) -> None:
        self._hass = hass
        self._timeout = timedelta(seconds=timeout_s)

    def check(
        self,
        critical_entity_ids: list[str],
        monitored_entity_ids: list[str],
    ) -> WatchdogReport:
        """Inspect entity ages and return a WatchdogReport.

        Args:
            critical_entity_ids: Entities whose staleness triggers DEGRADED mode.
            monitored_entity_ids: Entities that are watched but not critical alone.

        Returns:
            A WatchdogReport describing any stale entities found.
        """
        now = datetime.now(UTC)
        report = WatchdogReport()
        # Preserve order, deduplicate
        seen: set[str] = set()
        all_ids: list[str] = []
        for eid in critical_entity_ids + monitored_entity_ids:
            if eid not in seen:
                seen.add(eid)
                all_ids.append(eid)

        critical_set = set(critical_entity_ids)

        for entity_id in all_ids:
            state = self._hass.states.get(entity_id)
            is_critical = entity_id in critical_set

            if state is None:
                _LOGGER.warning("Watchdog: entity %s not found in HA state machine", entity_id)
                if is_critical:
                    report.critical_stale.append(entity_id)
                else:
                    report.stale_entities.append(entity_id)
                continue

            age = now - state.last_updated
            if age > self._timeout:
                _LOGGER.warning(
                    "Watchdog: entity %s stale (age %.0f s, limit %.0f s)",
                    entity_id,
                    age.total_seconds(),
                    self._timeout.total_seconds(),
                )
                if is_critical:
                    report.critical_stale.append(entity_id)
                else:
                    report.stale_entities.append(entity_id)

        return report
