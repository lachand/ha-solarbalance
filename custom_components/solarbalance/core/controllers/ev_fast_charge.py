"""EV fast-charge assist controller.

Slow charging is lossy: an EV's onboard charger has fixed conversion/standby
overhead, so charging at a low amperage just to match the instantaneous PV
surplus wastes energy. This controller instead enforces an *efficient* charge
floor and, when the surplus is short, lets the home batteries supply the gap so
the car still charges fast — but only while the PV forecast can still refill the
batteries once the car stops.

Decision (per tick), for a load flagged ``fast_charge``:

- surplus >= min_charge_w  -> no override: the surplus already feeds an efficient
  rate, let the normal dispatch modulate above the floor.
- surplus <  min_charge_w  -> the surplus alone would force a lossy slow charge:
    * if the battery SoC is above the assist floor AND the recoverability gate
      holds -> assist: command ``min_charge_w`` (batteries cover the gap via the
      zero-injection loop);
    * else -> pause (default) so we wait for surplus instead of charging slowly,
      or fall back to slow charge if ``pause_when_inefficient`` is False.

Recoverability gate (mirrors the evening-shed accounting, opposite condition)::

    pv_recovery = max(0, remaining_pv_kwh - talon_w/1000 * remaining_hours)
    gate_ok     = pv_recovery >= battery_deficit_kwh * (1 + margin)

As assisting discharges the batteries the deficit grows; once the gate fails the
assist stops and the EV pauses, so it is self-limiting and recovery-safe. It is
the exact complement of the evening shed (which engages when the gate fails).

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .evening_shed import BatteryChargeNeed

_DEFAULT_RECOVERY_MARGIN = 0.10


@dataclass(slots=True, frozen=True)
class FastChargeDecision:
    """Outcome of one fast-charge evaluation for an EV load."""

    override: bool  # True when the caller must replace the dispatch command
    target_w: float  # commanded EV power (0 = pause); meaningful when override
    gate_ok: bool
    battery_deficit_kwh: float
    pv_recovery_kwh: float
    reason: str


def evaluate_fast_charge(
    *,
    enabled: bool,
    surplus_w: float,
    min_charge_w: float,
    max_charge_w: float,
    batteries: Sequence[BatteryChargeNeed],
    avg_soc_pct: float | None,
    assist_floor_soc_pct: float,
    remaining_pv_kwh: float,
    remaining_hours: float,
    talon_w: float | None,
    pause_when_inefficient: bool = True,
    recovery_margin: float = _DEFAULT_RECOVERY_MARGIN,
) -> FastChargeDecision:
    """Decide whether to override the EV charge command for efficiency.

    Args:
        enabled: Master switch (the load's ``fast_charge`` flag).
        surplus_w: PV surplus available to the EV right now (W).
        min_charge_w: Efficient charge floor (W); below it charging is lossy.
        max_charge_w: Upper cap (the charger's max, W).
        batteries: Charge headroom of each controllable battery.
        avg_soc_pct: Mean SoC of the controllable fleet (None → unknown).
        assist_floor_soc_pct: Battery SoC below which no assist is allowed.
        remaining_pv_kwh: Forecast PV energy left in the production window.
        remaining_hours: Hours of production left (standby-energy term).
        talon_w: Standby baseline power (W); None assumes 0.
        pause_when_inefficient: Pause vs slow-charge when neither efficient
            surplus nor assist is possible.
        recovery_margin: Safety margin on the recoverability comparison.
    """
    deficit_kwh = sum(b.deficit_kwh for b in batteries)
    baseline_energy = max(0.0, (talon_w or 0.0) / 1000.0 * max(0.0, remaining_hours))
    pv_recovery_kwh = max(0.0, remaining_pv_kwh - baseline_energy)
    gate_ok = deficit_kwh <= 0.0 or pv_recovery_kwh >= deficit_kwh * (1.0 + recovery_margin)

    def _decision(override: bool, target_w: float, reason: str) -> FastChargeDecision:
        return FastChargeDecision(
            override=override,
            target_w=target_w,
            gate_ok=gate_ok,
            battery_deficit_kwh=deficit_kwh,
            pv_recovery_kwh=pv_recovery_kwh,
            reason=reason,
        )

    if not enabled:
        return _decision(False, 0.0, "disabled")
    if surplus_w >= min_charge_w:
        # Surplus already supports an efficient rate — let normal dispatch run.
        return _decision(False, 0.0, "surplus_efficient")

    soc_ok = avg_soc_pct is not None and avg_soc_pct > assist_floor_soc_pct
    if soc_ok and gate_ok:
        return _decision(True, min(max_charge_w, max(min_charge_w, surplus_w)), "assist")
    if pause_when_inefficient:
        reason = "pause_low_soc" if not soc_ok else "pause_unrecoverable"
        return _decision(True, 0.0, reason)
    return _decision(False, 0.0, "slow_charge_fallback")
