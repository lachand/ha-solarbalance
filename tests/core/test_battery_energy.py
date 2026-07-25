"""Tests for per-battery throughput: round-trip efficiency and equivalent cycles."""

from datetime import datetime, timedelta

from custom_components.solarbalance.core.battery_energy import BatteryEnergyTracker

_T0 = datetime(2026, 7, 25, 6, 0)


def _run(
    tracker: BatteryEnergyTracker,
    name: str,
    samples: list[tuple[float, float]],
    *,
    step_s: int = 60,
    start: datetime = _T0,
) -> None:
    """Feed ``(power_w, soc_pct)`` samples, one per step."""
    now = start
    for power_w, soc in samples:
        tracker.observe(name, now, power_w, soc)
        now += timedelta(seconds=step_s)


def test_a_battery_never_seen_has_no_stats() -> None:
    assert BatteryEnergyTracker().stats("bat", usable_capacity_kwh=5.0) is None


def test_charge_and_discharge_energy_are_accounted_separately() -> None:
    t = BatteryEnergyTracker()
    # 1 h charging at 1000 W, then 1 h discharging at 1000 W (60 samples each).
    _run(t, "bat", [(1000.0, 50.0)] * 61 + [(-1000.0, 50.0)] * 60)
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None
    assert abs(s.charge_in_kwh - 1.0) < 0.02
    assert abs(s.discharge_out_kwh - 1.0) < 0.02


def test_round_trip_below_the_throughput_floor_is_withheld() -> None:
    t = BatteryEnergyTracker()
    _run(t, "bat", [(1000.0, 50.0)] * 30)  # 0.5 kWh, well under the floor
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None
    assert s.round_trip_pct is None


def test_round_trip_is_measured_once_enough_energy_has_flowed() -> None:
    t = BatteryEnergyTracker()
    # Put 12 kWh in and take 10.2 kWh out, ending at the same SoC: 85 % round trip.
    now = _T0
    for _ in range(720):  # 12 h charging at 1000 W -> 12 kWh
        t.observe("bat", now, 1000.0, 50.0)
        now += timedelta(seconds=60)
    for _ in range(612):  # 10.2 h discharging at 1000 W -> 10.2 kWh
        t.observe("bat", now, -1000.0, 50.0)
        now += timedelta(seconds=60)
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None
    assert s.round_trip_pct is not None
    assert 83.0 <= s.round_trip_pct <= 87.0


def test_charge_still_stored_does_not_count_as_a_loss() -> None:
    """The correction that keeps the figure honest.

    A pack that ended much fuller than it started has *kept* energy; dividing
    delivered by taken-in alone would read that as a huge efficiency loss.
    """
    t = BatteryEnergyTracker()
    now = _T0
    # 12 kWh in while SoC climbs 20 % -> 80 % of a 5 kWh pack = 3 kWh kept stored.
    for i in range(720):
        soc = 20.0 + i / 720.0 * 60.0
        t.observe("bat", now, 1000.0, soc)
        now += timedelta(seconds=60)
    # Then deliver 7.6 kWh, ending at that same 80 %.
    for _ in range(456):
        t.observe("bat", now, -1000.0, 80.0)
        now += timedelta(seconds=60)
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None and s.round_trip_pct is not None
    # Uncorrected this reads ~63 % (7.6 / 12); removing the 3 kWh still in the pack
    # lifts it to a plausible ~84 %.
    assert s.round_trip_pct > 75.0


def test_round_trip_never_exceeds_one_hundred() -> None:
    t = BatteryEnergyTracker()
    now = _T0
    for _ in range(700):
        t.observe("bat", now, 1000.0, 90.0)
        now += timedelta(seconds=60)
    # Discharge more than physically went in by ending far lower — the correction
    # must not let the ratio run past 100 %.
    for _ in range(700):
        t.observe("bat", now, -1000.0, 10.0)
        now += timedelta(seconds=60)
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None and s.round_trip_pct is not None
    assert s.round_trip_pct <= 100.0


def test_equivalent_cycles_are_delivered_energy_over_capacity() -> None:
    t = BatteryEnergyTracker()
    now = _T0
    for _ in range(600):  # 10 kWh delivered from a 5 kWh pack -> 2 full cycles
        t.observe("bat", now, -1000.0, 50.0)
        now += timedelta(seconds=60)
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None
    assert abs(s.equivalent_full_cycles - 2.0) < 0.05


def test_equivalent_cycles_need_a_capacity() -> None:
    t = BatteryEnergyTracker()
    _run(t, "bat", [(-1000.0, 50.0)] * 60)
    assert t.stats("bat", usable_capacity_kwh=0.0).equivalent_full_cycles is None


def test_a_long_gap_is_not_integrated() -> None:
    t = BatteryEnergyTracker()
    t.observe("bat", _T0, 1000.0, 50.0)
    t.observe("bat", _T0 + timedelta(hours=3), 1000.0, 50.0)  # restart-sized gap
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None
    assert s.charge_in_kwh == 0.0


def test_the_totals_survive_a_restart() -> None:
    t = BatteryEnergyTracker()
    _run(t, "bat", [(1000.0, 40.0)] * 61 + [(-1000.0, 60.0)] * 60)
    before = t.stats("bat", usable_capacity_kwh=5.0)

    back = BatteryEnergyTracker.from_dict(t.to_dict())
    after = back.stats("bat", usable_capacity_kwh=5.0)
    assert after == before


def test_a_malformed_row_is_skipped_not_fatal() -> None:
    back = BatteryEnergyTracker.from_dict({"good": {"in": 3.0, "out": 2.0}, "bad": 7})
    assert "bad" not in back._acc
    assert back.stats("good", usable_capacity_kwh=5.0).charge_in_kwh == 3.0


def test_a_missing_soc_still_books_energy() -> None:
    t = BatteryEnergyTracker()
    now = _T0
    for _ in range(700):
        t.observe("bat", now, 1000.0, None)  # SoC entity down the whole time
        now += timedelta(seconds=60)
    s = t.stats("bat", usable_capacity_kwh=5.0)
    assert s is not None
    assert s.charge_in_kwh > 10.0
    assert s.round_trip_pct is None  # no SoC reference, so no honest efficiency
