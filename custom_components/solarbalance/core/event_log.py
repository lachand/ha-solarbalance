"""A short, bounded timeline of the notable things that happened.

Every incident this month ended the same way: someone scrolling the Home Assistant
logbook trying to reconstruct *when* the meter went quiet, *when* the cloud battery
dropped out, *when* that impossible export reading was rejected. The signals were
all there — fired as events, logged as warnings — but scattered across a firehose,
with no one place that answered "what has gone wrong lately, and in what order?".

This is that place: a small ring of records, each a timestamp, a kind, a
severity and a one-line human message. It is deliberately not the logbook — it
keeps only what is worth waking up for, capped so it can be held in a sensor
attribute and persisted without growing without bound.

De-duplication is built in because the failure modes here repeat: a meter that
flaps produces the same "meter unavailable" every tick, and forty identical rows
bury the one new thing. A repeat of the most recent event of the same kind bumps
its count and timestamp instead of adding a row.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Kept small on purpose: this is the "what went wrong lately" view, not a log.
_MAX_EVENTS = 50
# A repeat of the same kind within this window folds into the last row rather than
# adding one, so a flapping signal cannot flood the timeline.
_DEDUP_WINDOW_S = 900.0

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
_SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR)


@dataclass(slots=True, frozen=True)
class Event:
    """One notable moment."""

    at_s: float
    """Wall-clock epoch seconds it (last) happened."""

    kind: str
    """Stable slug — ``meter_lost``, ``grid_rejected``, ``link_down``…"""

    severity: str
    """``info`` | ``warning`` | ``error``."""

    message: str
    """One human-readable line."""

    count: int = 1
    """How many times it repeated inside the dedup window."""


@dataclass(slots=True)
class EventLog:
    """A bounded, de-duplicated timeline of notable events, newest last."""

    _events: list[Event] = field(default_factory=list)

    def record(
        self, at_s: float, kind: str, message: str, severity: str = SEVERITY_WARNING
    ) -> Event:
        """Add an event, folding an immediate repeat of the same kind into the last.

        Args:
            at_s: Epoch seconds of the event.
            kind: Stable slug identifying the type.
            message: One-line description.
            severity: One of ``info`` / ``warning`` / ``error`` (anything else is
                treated as ``warning``, so a caller typo never hides an event).

        Returns:
            The stored :class:`Event` — either a new row or the bumped last one.
        """
        if severity not in _SEVERITIES:
            severity = SEVERITY_WARNING

        if self._events:
            last = self._events[-1]
            if last.kind == kind and 0.0 <= at_s - last.at_s <= _DEDUP_WINDOW_S:
                bumped = Event(
                    at_s=at_s,
                    kind=kind,
                    severity=severity,
                    message=message,
                    count=last.count + 1,
                )
                self._events[-1] = bumped
                return bumped

        event = Event(at_s=at_s, kind=kind, severity=severity, message=message)
        self._events.append(event)
        del self._events[:-_MAX_EVENTS]
        return event

    def recent(self, limit: int = _MAX_EVENTS) -> list[Event]:
        """The most recent events, newest first."""
        return list(reversed(self._events[-limit:]))

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store."""
        return {
            "events": [
                {
                    "at": round(e.at_s, 1),
                    "kind": e.kind,
                    "severity": e.severity,
                    "message": e.message,
                    "count": e.count,
                }
                for e in self._events
            ]
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EventLog":
        """Rebuild from a persisted dict; malformed rows are skipped, not fatal."""
        log = cls()
        rows = data.get("events") if isinstance(data, Mapping) else None
        if not isinstance(rows, Sequence):
            return log
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            try:
                log._events.append(
                    Event(
                        at_s=float(row["at"]),
                        kind=str(row["kind"]),
                        severity=str(row.get("severity", SEVERITY_WARNING)),
                        message=str(row.get("message", "")),
                        count=int(row.get("count", 1)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        del log._events[:-_MAX_EVENTS]
        return log
