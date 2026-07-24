"""Tests for appliance cycle learning (recording, closing, summarising, matching)."""

from custom_components.solarbalance.core.appliance_cycles import (
    UNKNOWN_PROGRAM,
    ApplianceCycles,
    CycleTemplate,
    resample,
)


def _feed(ac: ApplianceCycles, name: str, samples: list[tuple[float, float]]):
    """Push (t, power) samples; return the template closed on the way, if any."""
    closed = None
    for t, p in samples:
        got = ac.observe(name, t, p)
        if got is not None:
            closed = got
    return closed


def _dishwasher_like(start: float = 0.0, step: float = 60.0) -> list[tuple[float, float]]:
    """A cycle shaped like the real one recorded 2026-07-23 (16:27→18:57).

    Heat ~1.8 kW, then an hour of ~75 W circulation *with brief dips to ~1 W*,
    then a second heating burst, then off. The dips are the trap: a naive
    "power == 0 ends the cycle" rule would split this into several cycles.
    """
    out: list[tuple[float, float]] = []
    t = start

    def run(minutes: int, power: float):
        nonlocal t
        for _ in range(minutes):
            out.append((t, power))
            t += step

    run(8, 1830.0)  # heating
    for _ in range(6):  # ~1 h of circulation with dips
        run(8, 75.0)
        run(2, 1.0)  # brief dip — must NOT close the cycle
    run(9, 1860.0)  # second heating burst
    run(5, 70.0)
    run(12, 0.0)  # off long enough to close (idle_gap_s = 300 s)
    return out


def test_a_dip_mid_cycle_does_not_split_the_cycle() -> None:
    ac = ApplianceCycles()
    closed = _feed(ac, "dw", _dishwasher_like())
    assert closed is not None, "the cycle never closed"
    assert ac.learned_cycles == 1, "brief dips split one cycle into several"
    # ~8 + 60 + 9 + 5 minutes of running before the idle tail.
    assert 4500 < closed.duration_s < 5400
    assert 0.5 < closed.energy_kwh < 1.2


def test_cycle_closes_only_after_a_sustained_idle_gap() -> None:
    ac = ApplianceCycles(idle_gap_s=300.0)
    # 10 min of real running first, so the close is not rejected as a blip and we
    # are genuinely exercising the idle-gap rule.
    samples = [(i * 60.0, 1800.0) for i in range(10)]
    samples += [(600.0 + i * 60.0, 0.0) for i in range(4)]  # 3 min idle — not enough
    assert _feed(ac, "wm", samples) is None
    assert ac.is_running("wm") is True
    closed = ac.observe("wm", 960.0, 0.0)  # now past the 5 min gap
    assert closed is not None
    assert closed.duration_s == 600.0  # the idle tail is trimmed, not counted


def test_a_blip_is_not_recorded_as_a_cycle() -> None:
    ac = ApplianceCycles()
    _feed(ac, "wm", [(0.0, 900.0), (60.0, 900.0)] + [(120.0 + i * 60, 0.0) for i in range(8)])
    assert ac.learned_cycles == 0  # under min_duration_s / min_energy_kwh


def test_program_label_is_read_at_close_not_at_start() -> None:
    # Appliance integrations identify the program late in the run; filing the
    # finished cycle under it is exactly what the late label is good for.
    ac = ApplianceCycles()
    _feed(ac, "dw", _dishwasher_like()[:-12])  # stop before the idle tail
    ac.close("dw", program="90 minutes")
    assert list(ac.templates["dw"].keys()) == ["90 minutes"]

    ac2 = ApplianceCycles()
    _feed(ac2, "dw", _dishwasher_like())  # closed by the gap, no label given
    assert list(ac2.templates["dw"].keys()) == [UNKNOWN_PROGRAM]


def test_summary_uses_medians_so_one_aborted_cycle_cannot_skew_it() -> None:
    ac = ApplianceCycles()
    for _ in range(3):
        ac.add_template("dw", CycleTemplate(7200.0, 1.2, tuple([500.0] * 24)), program="auto")
    ac.add_template("dw", CycleTemplate(300.0, 0.05, tuple([10.0] * 24)), program="auto")  # aborted
    s = ac.summary("dw")
    assert s is not None
    assert s.duration_s == 7200.0  # median, not dragged down by the outlier
    assert s.energy_kwh == 1.2
    assert s.samples == 4


def test_summary_is_none_before_anything_is_learned() -> None:
    assert ApplianceCycles().summary("dw") is None


def test_match_prefers_the_closest_curve_and_scores_confidence() -> None:
    ac = ApplianceCycles()
    hot = CycleTemplate(3600.0, 1.5, tuple([1800.0] * 12 + [80.0] * 12))
    cold = CycleTemplate(3600.0, 0.2, tuple([90.0] * 24))
    ac.add_template("wm", hot, program="60deg")
    ac.add_template("wm", cold, program="cold")
    # Observed prefix: clearly the hot one.
    prefix = [(i * 60.0, 1800.0) for i in range(15)]
    m = ac.match("wm", prefix)
    assert m is not None
    assert m.program == "60deg"
    assert m.confidence > 0.8


def test_match_returns_nothing_without_templates_or_prefix() -> None:
    ac = ApplianceCycles()
    assert ac.match("wm", [(0.0, 100.0), (60.0, 100.0)]) is None
    ac.add_template("wm", CycleTemplate(3600.0, 1.0, tuple([500.0] * 24)))
    assert ac.match("wm", [(0.0, 100.0)]) is None  # a single point is not a prefix


def test_resample_keeps_a_short_burst_visible() -> None:
    # A 1.8 kW burst inside an otherwise quiet stretch must survive bucketing,
    # otherwise the heating phase disappears from the template.
    samples = [(float(i), 50.0) for i in range(240)]
    for i in range(100, 110):
        samples[i] = (float(i), 1800.0)
    curve = resample(samples, steps=24)
    assert max(curve) > 200.0


def test_round_trip_through_the_store() -> None:
    ac = ApplianceCycles()
    ac.add_template("dw", CycleTemplate(7200.0, 1.2, tuple(range(24))), program="auto")
    back = ApplianceCycles.from_dict(ac.to_dict())
    assert back.learned_cycles == 1
    s = back.summary("dw")
    assert s is not None and s.program == "auto" and s.duration_s == 7200.0


def test_from_dict_survives_malformed_payloads() -> None:
    for bad in ({}, {"templates": "nope"}, {"templates": {"dw": {"auto": [{"curve_w": []}]}}}):
        assert ApplianceCycles.from_dict(bad).learned_cycles == 0
