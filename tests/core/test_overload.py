"""Tests for the priority cascade overload-relief controller."""

from custom_components.solarbalance.core.controllers.overload import (
    SheddableLoad,
    relieve_overload,
)


def _l(name, prio, cur, floor=0.0, interruptible=True, reducible=None):
    return SheddableLoad(
        name=name,
        priority=prio,
        current_w=cur,
        floor_w=floor,
        interruptible=interruptible,
        reducible=(floor > 0) if reducible is None else reducible,
    )


def test_no_excess_changes_nothing() -> None:
    targets, uncovered = relieve_overload([_l("a", 1, 1000)], 0)
    assert targets == {} and uncovered == 0.0


def test_lowest_priority_shed_first_and_only_enough() -> None:
    loads = [_l("ev", 5, 2000), _l("wh", 1, 2000), _l("pool", 3, 1000)]
    # Need to shed 1500 W → cut the lowest priority (wh=2000) partial? wh is on/off
    # (floor 0) so it can only go fully off (-2000), which already covers 1500.
    targets, uncovered = relieve_overload(loads, 1500)
    assert targets == {"wh": 0.0}
    assert uncovered == 0.0


def test_reduces_modulating_toward_floor_before_cutting() -> None:
    # EV is reducible (floor 1400); shedding 600 W lowers it to 1400, not off.
    loads = [_l("ev", 1, 2000, floor=1400)]
    targets, uncovered = relieve_overload(loads, 600)
    assert targets == {"ev": 1400.0}
    assert uncovered == 0.0


def test_cascade_across_multiple_loads() -> None:
    loads = [_l("ev", 1, 2000, floor=1400), _l("wh", 2, 2000)]
    # 1200 W: ev gives 600 (→1400), still 600 short → wh on/off cut to 0 (-2000).
    targets, uncovered = relieve_overload(loads, 1200)
    assert targets["ev"] == 1400.0
    assert targets["wh"] == 0.0
    assert uncovered == 0.0


def test_non_interruptible_is_never_touched() -> None:
    loads = [_l("critical", 1, 3000, interruptible=False)]
    targets, uncovered = relieve_overload(loads, 1000)
    assert targets == {}
    assert uncovered == 1000.0
