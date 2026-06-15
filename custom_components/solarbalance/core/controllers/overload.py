"""Multi-level priority load shedding for grid-overload protection.

When the projected grid import approaches the subscribed-power limit, shed the
*least important* loads first and only as much as needed — reducing modulating /
stepped loads toward their floor (e.g. lowering EV charge current) before cutting
on/off loads. This is a cascade, not all-or-nothing.

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class SheddableLoad:
    """A currently-running load that may be reduced or cut to relieve the grid."""

    name: str
    priority: int  # lower = less important → shed first
    current_w: float  # power it draws now
    floor_w: float  # lowest power it can run at when reducible
    interruptible: bool
    reducible: bool = False  # stepped/modulating → can run between floor and current


def relieve_overload(
    loads: Sequence[SheddableLoad], excess_w: float
) -> tuple[dict[str, float], float]:
    """Pick load power reductions to shed ``excess_w`` watts of grid import.

    Walks loads from the **lowest priority up**. A *reducible* load (modulating /
    stepped, e.g. an EV charger) is lowered toward its floor; an on/off load can
    only be cut entirely (all-or-nothing). Stops once ``excess_w`` is covered.
    Non-interruptible loads are never touched. Returns ``(targets, uncovered_w)``
    where ``targets`` maps each *affected* load name to its new power target (W).
    """
    if excess_w <= 0:
        return {}, 0.0
    targets: dict[str, float] = {}
    remaining = excess_w
    for load in sorted(loads, key=lambda x: x.priority):
        if remaining <= 0:
            break
        if not load.interruptible or load.current_w <= 0:
            continue
        if load.reducible:
            cut = min(max(0.0, load.current_w - max(0.0, load.floor_w)), remaining)
            if cut <= 0:
                continue
            targets[load.name] = round(load.current_w - cut, 1)
            remaining -= cut
        else:
            # On/off: cut fully (overshoot accepted — it cannot run partially).
            targets[load.name] = 0.0
            remaining -= load.current_w
    return targets, max(0.0, remaining)
