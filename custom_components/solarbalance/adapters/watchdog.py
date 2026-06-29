"""Watchdog: detect stale HA entities and report degraded status.

Each tick the coordinator calls ``EntityWatchdog.check()`` with the lists of
critical, monitored and optional entity IDs.  A *critical* entity (e.g. the PDL
meter) going stale triggers an automatic switch to ``HemsMode.DEGRADED``.
*Monitored* entities are watched but not critical alone. *Optional* entities
(MPPT/inverters) legitimately disappear when the device is powered down (a
micro-inverter at night), so being unavailable/missing is **expected** — not a
fault; only a *frozen* value (present but not updating) is flagged.

Logging is **edge-triggered**: a transition is logged once (gone, then once when
it recovers), never every tick — so a device that is simply off overnight does
not spam the log.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S: int = 300  # 5 minutes
_UNAVAILABLE_STATES = ("unavailable", "unknown")


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
        # Last-seen status per entity ("ok" / "off" / "stale"), for edge-triggered logs.
        self._prev: dict[str, str] = {}

    def check(
        self,
        critical_entity_ids: list[str],
        monitored_entity_ids: list[str],
        optional_entity_ids: list[str] | None = None,
    ) -> WatchdogReport:
        """Inspect entity ages and return a WatchdogReport.

        Args:
            critical_entity_ids: Entities whose staleness triggers DEGRADED mode.
            monitored_entity_ids: Entities watched but not critical alone.
            optional_entity_ids: Entities that may be off (MPPT/inverters) —
                unavailable/missing is expected (no fault); only a frozen value flags.

        Returns:
            A WatchdogReport describing any stale entities found.
        """
        now = datetime.now(UTC)
        report = WatchdogReport()
        critical_set = set(critical_entity_ids)
        optional_set = set(optional_entity_ids or [])

        # Preserve order, deduplicate (critical first so a shared id keeps its severity).
        seen: set[str] = set()
        all_ids: list[str] = []
        for eid in critical_entity_ids + monitored_entity_ids + list(optional_entity_ids or []):
            if eid not in seen:
                seen.add(eid)
                all_ids.append(eid)

        status_now: dict[str, str] = {}
        for entity_id in all_ids:
            state = self._hass.states.get(entity_id)
            is_critical = entity_id in critical_set
            is_optional = entity_id in optional_set and not is_critical

            off = state is None or state.state in _UNAVAILABLE_STATES
            stale = state is not None and (now - state.last_updated) > self._timeout

            if is_optional:
                # Powered down (missing/unavailable) is normal; a frozen value is not.
                status = "stale" if (not off and stale) else ("off" if off else "ok")
            else:
                # A critical/monitored entity: missing or not-updating is a problem.
                # (An unavailable state keeps its drop timestamp, so it trips on age,
                # tolerating a brief blip before flagging.)
                status = "stale" if (state is None or stale) else "ok"

            status_now[entity_id] = status
            if status == "stale":
                (report.critical_stale if is_critical else report.stale_entities).append(entity_id)

            prev = self._prev.get(entity_id, "ok")
            if status != prev:
                self._log_transition(entity_id, status, state, now)

        self._prev = status_now
        return report

    def _log_transition(self, entity_id: str, status: str, state: object, now: datetime) -> None:
        """Log a single status change (edge-triggered, never per-tick)."""
        if status == "stale":
            if state is None:
                _LOGGER.warning("Watchdog: %s missing from the state machine", entity_id)
            else:
                age = (now - state.last_updated).total_seconds()  # type: ignore[attr-defined]
                _LOGGER.warning(
                    "Watchdog: %s stale (age %.0f s, limit %.0f s)",
                    entity_id,
                    age,
                    self._timeout.total_seconds(),
                )
        elif status == "off":
            _LOGGER.info(
                "Watchdog: %s off (expected when the device is powered down, e.g. an "
                "inverter at night)",
                entity_id,
            )
        else:  # recovered to "ok"
            _LOGGER.info("Watchdog: %s recovered", entity_id)
