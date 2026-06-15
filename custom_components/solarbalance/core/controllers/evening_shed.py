"""Evening battery-priority load-shedding controller.

Goal: at the end of the production window, shed the big interruptible loads so
the remaining PV charges the batteries to their SoC max, instead of being eaten
by those loads.

The decision is energy-based and therefore self-timing: in the morning there is
plenty of PV ahead, so the deficit is easily covered and nothing is shed; as the
day ends the remaining PV shrinks and, once it can no longer both run the big
loads *and* fill the batteries, shedding kicks in.

Accounting (all energies in kWh over the remaining production window):
    deficit          = Σ max(0, (soc_max - soc)/100 * usable_capacity)
    baseline_energy  = talon_w / 1000 * remaining_hours      (standby eats PV too)
    pv_for_charge    = max(0, remaining_pv - baseline_energy)

Shed when production is still expected (``remaining_pv > 0``), the batteries are
not full (``deficit > 0``) and the PV available for charging after the standby
talon is not enough to fill them (``pv_for_charge < deficit``). Only interruptible
loads at or above ``min_shed_power_w`` are shed.

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# Below these the comparison is noise: skip shedding.
_MIN_REMAINING_PV_KWH = 0.05
_MIN_DEFICIT_KWH = 0.05


@dataclass(slots=True, frozen=True)
class BatteryChargeNeed:
    """Charge headroom of one controllable battery."""

    soc_pct: float
    soc_max_pct: float
    usable_capacity_kwh: float

    @property
    def deficit_kwh(self) -> float:
        """Energy needed to reach SoC max (kWh, never negative)."""
        return max(0.0, (self.soc_max_pct - self.soc_pct) / 100.0 * self.usable_capacity_kwh)


@dataclass(slots=True, frozen=True)
class ShedDecision:
    """Outcome of one evening-shed evaluation."""

    active: bool
    shed_load_names: frozenset[str]
    deficit_kwh: float
    pv_for_charge_kwh: float
    reason: str


def evaluate_evening_shed(
    *,
    enabled: bool,
    batteries: Sequence[BatteryChargeNeed],
    remaining_pv_kwh: float,
    remaining_hours: float,
    talon_w: float | None,
    sheddable: Sequence[tuple[str, float, int]],
    min_shed_power_w: float,
) -> ShedDecision:
    """Decide whether to shed big loads to prioritise battery charging.

    Sheds **as a cascade**: the least important loads first (lowest priority),
    and only enough of them to free the power the batteries are short — not
    all-or-nothing.

    Args:
        enabled: Master switch for the behaviour.
        batteries: Charge headroom of each controllable battery.
        remaining_pv_kwh: Forecast PV energy left in the production window.
        remaining_hours: Hours of production left (for the standby energy term).
        talon_w: Standby baseline power (W); ``None`` assumes 0.
        sheddable: ``(load_name, nominal_power_w, priority)`` for interruptible
            loads — lower ``priority`` is shed first.
        min_shed_power_w: Only loads at/above this power are shed ("big" loads).

    Returns:
        A :class:`ShedDecision`. ``shed_load_names`` is empty when inactive.
    """
    deficit_kwh = sum(b.deficit_kwh for b in batteries)
    baseline_energy_kwh = max(0.0, (talon_w or 0.0) / 1000.0 * max(0.0, remaining_hours))
    pv_for_charge_kwh = max(0.0, remaining_pv_kwh - baseline_energy_kwh)

    if not enabled:
        reason = "disabled"
    elif remaining_pv_kwh < _MIN_REMAINING_PV_KWH:
        reason = "no_production_left"
    elif deficit_kwh < _MIN_DEFICIT_KWH:
        reason = "batteries_full"
    elif pv_for_charge_kwh >= deficit_kwh:
        reason = "surplus_sufficient"
    else:
        # Power we must free so the remaining PV can also fill the batteries.
        shortfall_kwh = deficit_kwh - pv_for_charge_kwh
        needed_w = shortfall_kwh / remaining_hours * 1000.0 if remaining_hours > 0 else float("inf")
        big = sorted(
            (item for item in sheddable if item[1] >= min_shed_power_w),
            key=lambda item: item[2],  # ascending priority → least important first
        )
        shed: set[str] = set()
        freed = 0.0
        for name, power, _priority in big:
            if freed >= needed_w:
                break
            shed.add(name)
            freed += power
        names = frozenset(shed)
        reason = "shedding" if names else "no_sheddable_load"
        return ShedDecision(
            active=bool(names),
            shed_load_names=names,
            deficit_kwh=deficit_kwh,
            pv_for_charge_kwh=pv_for_charge_kwh,
            reason=reason,
        )

    return ShedDecision(
        active=False,
        shed_load_names=frozenset(),
        deficit_kwh=deficit_kwh,
        pv_for_charge_kwh=pv_for_charge_kwh,
        reason=reason,
    )
