"""Tests for the bounded anomaly timeline."""

from custom_components.solarbalance.core.event_log import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    EventLog,
)

_T0 = 1_753_400_000.0


def test_events_come_back_newest_first() -> None:
    log = EventLog()
    log.record(_T0, "meter_lost", "Meter gone")
    log.record(_T0 + 60, "meter_back", "Meter back", SEVERITY_INFO)
    recent = log.recent()
    assert [e.kind for e in recent] == ["meter_back", "meter_lost"]


def test_an_immediate_repeat_folds_into_the_last_row() -> None:
    # A flapping meter must not bury everything else under identical rows.
    log = EventLog()
    for i in range(40):
        log.record(_T0 + i, "meter_lost", "Meter unavailable")
    recent = log.recent()
    assert len(recent) == 1
    assert recent[0].count == 40
    assert recent[0].at_s == _T0 + 39  # timestamp tracks the latest occurrence


def test_a_repeat_after_the_window_starts_a_new_row() -> None:
    log = EventLog()
    log.record(_T0, "link_down", "Cloud battery down")
    log.record(_T0 + 5000, "link_down", "Cloud battery down")  # well past the window
    assert len(log.recent()) == 2


def test_a_different_kind_between_repeats_is_not_folded() -> None:
    log = EventLog()
    log.record(_T0, "meter_lost", "a")
    log.record(_T0 + 1, "grid_rejected", "b")
    log.record(_T0 + 2, "meter_lost", "c")
    assert [e.kind for e in log.recent()] == ["meter_lost", "grid_rejected", "meter_lost"]


def test_the_log_is_bounded() -> None:
    log = EventLog()
    for i in range(200):
        log.record(_T0 + i * 5000, f"kind_{i}", "x")  # distinct kinds, past the window
    assert len(log.recent(limit=1000)) == 50


def test_an_unknown_severity_falls_back_to_warning() -> None:
    log = EventLog()
    e = log.record(_T0, "weird", "msg", severity="catastrophe")
    assert e.severity == "warning"


def test_severity_is_preserved_when_valid() -> None:
    log = EventLog()
    assert log.record(_T0, "boom", "msg", SEVERITY_ERROR).severity == "error"


def test_the_timeline_survives_a_restart() -> None:
    log = EventLog()
    log.record(_T0, "meter_lost", "gone", SEVERITY_ERROR)
    log.record(_T0 + 5000, "link_down", "cloud down")
    back = EventLog.from_dict(log.to_dict())
    assert [e.kind for e in back.recent()] == ["link_down", "meter_lost"]
    assert back.recent()[-1].severity == "error"


def test_a_malformed_row_is_skipped_not_fatal() -> None:
    payload = {"events": [{"at": 1.0, "kind": "ok", "message": "m"}, {"kind": "no_at"}, 42]}
    back = EventLog.from_dict(payload)
    assert [e.kind for e in back.recent()] == ["ok"]
