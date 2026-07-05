"""Hybrid balancing controller.

Distributes a global charge or discharge demand across N batteries with
heterogeneous capacities and SoC, using a tunable mix of capacity-weighted
and SoC-equalising allocation. See SPECIFICATIONS §6.2.

Anti-short-cycle guard (v1.5): when ``min_dwell_s > 0``, a battery that just
reversed direction is kept at zero for at least ``min_dwell_s`` seconds before
being allowed to reverse again. This prevents oscillatory charging/discharging
caused by fluctuating grid power around 0 W.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from ..models import BatteryRole, BatteryState, Device

# Numerical guardrails
_MAX_ITER = 32
_RESIDUAL_TOLERANCE_W = 1.0
_EQUALISER_EPSILON = 1e-3
# Stop allocating discharge this far ABOVE the SoC floor. A battery near its floor (or
# its device's backup reserve, which the box maintains a little above) won't actually
# discharge — commanding it anyway winds the zero-injection loop up (the morning
# "wants to charge before it can discharge" case). Excluding it early lets the
# anti-windup relax the command instead.
_DISCHARGE_SOC_MARGIN_PCT = 2.0
# Above the margin, ramp the allowed discharge up smoothly over this band instead of
# snapping 0 -> full: a battery hovering at the margin no longer slams the setpoint
# 0<->max every tick when its (1 %-quantised) SoC flickers across the boundary.
_DISCHARGE_TAPER_BAND_PCT = 4.0
# Hysteresis: once a battery has been rested at/under the margin, keep it at zero
# discharge until its SoC recovers this far above the margin — so SoC quantisation
# noise at the boundary cannot re-arm it every tick (the morning discharge yoyo).
_DISCHARGE_REARM_PCT = 2.0
# Additive weight for a charge-priority battery below its target SoC. Dominates the normal
# weights (which sum to ~1) so it takes the surplus first; it then saturates at its cap and
# the saturation loop redistributes the remainder to the rest of the fleet.
_CHARGE_PRIORITY_WEIGHT = 1000.0


@dataclass(slots=True, frozen=True)
class BalancingResult:
    """Outcome of one balancing pass."""

    per_battery_w: Mapping[str, float]
    unallocated_w: float
    iterations: int


class BalancingController:
    """Allocate aggregate power across batteries with hybrid weighting.

    Weighting blends two terms by `alpha`:
    - `alpha=1.0` → fully proportional to capacity (each battery contributes
      its share of the total capacity, SoC drift is preserved);
    - `alpha=0.0` → fully proportional to SoC equalisation (lagging batteries
      charge more, leading batteries discharge more);
    - default `alpha=0.6` → mostly capacity, with a steady drift towards
      equalisation.

    When ``min_dwell_s > 0``, a battery is held at zero after a direction
    reversal until the dwell period elapses (anti-short-cycle guard).
    """

    def __init__(
        self,
        devices: Sequence[Device],
        alpha: float = 0.6,
        min_dwell_s: float = 60.0,
    ) -> None:
        """Initialise the controller.

        Args:
            devices: All configured devices; only those with a battery role are used.
            alpha: Blend coefficient between capacity-proportional (1.0) and
                SoC-equalising (0.0) allocation. Must be in [0, 1].
            min_dwell_s: Minimum seconds a battery must stay in one direction
                before it may reverse. Set to 0 to disable the guard.
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be in [0, 1]")
        self._batteries: tuple[tuple[str, BatteryRole], ...] = tuple(
            (d.name, d.battery) for d in devices if d.battery is not None and d.battery.controllable
        )
        self._alpha = alpha
        self._min_dwell_s = min_dwell_s
        self._last_direction: dict[str, int] = {}  # 1=charging, -1=discharging
        self._last_direction_at: dict[str, datetime] = {}
        # Per-battery discharge-floor hysteresis latch: True once rested at/under the
        # margin, cleared only when SoC recovers past the re-arm band. See _discharge_scale.
        self._discharge_rested: dict[str, bool] = {}

    def allocate(
        self,
        total_power_w: float,
        states: Mapping[str, BatteryState],
        now: datetime | None = None,
        charge_caps: Mapping[str, float] | None = None,
    ) -> BalancingResult:
        """Allocate `total_power_w` across batteries (positive = charge).

        Args:
            total_power_w: Signed aggregate power to distribute.
            states: Current battery states keyed by device name.
            now: Current timestamp used for the anti-short-cycle guard.
                When None, the guard is skipped for this tick.
            charge_caps: Optional per-battery max *charge* (W), e.g. the hardware
                setpoint entity's real ceiling. Caps the allocation below
                ``max_charge_power_w`` so ``unallocated_w`` reflects the true saturation
                (and the velocity-form anti-windup does not wind past the physical limit).
        """
        # Per-battery discharge caps (SoC taper + hysteresis) — 0 near the floor,
        # ramping to the full rate over the taper band. Computed once per tick.
        discharge_caps = self._discharge_caps(total_power_w, states)
        eligible = self._eligible_batteries(total_power_w, states, now, discharge_caps)
        if not eligible:
            return BalancingResult(per_battery_w={}, unallocated_w=total_power_w, iterations=0)

        per_battery: dict[str, float] = {name: 0.0 for name, _ in self._batteries}
        remaining = total_power_w
        iterations = 0
        active = list(eligible)

        while abs(remaining) > _RESIDUAL_TOLERANCE_W and active and iterations < _MAX_ITER:
            iterations += 1
            weights = self._compute_weights(active, states, charging=remaining > 0)
            weight_sum = sum(weights.values())
            if weight_sum <= 0.0:
                break

            saturated_now: list[str] = []
            for name, role in active:
                share = remaining * (weights[name] / weight_sum)
                proposed = per_battery[name] + share
                max_discharge_w = discharge_caps.get(name, float(role.max_discharge_power_w))
                max_charge_w = float(role.max_charge_power_w)
                if charge_caps is not None and name in charge_caps:
                    max_charge_w = min(max_charge_w, charge_caps[name])
                clamped = self._clamp_to_limits(max_charge_w, max_discharge_w, proposed)
                per_battery[name] = clamped
                if abs(clamped - proposed) > _RESIDUAL_TOLERANCE_W:
                    saturated_now.append(name)

            allocated = sum(per_battery.values())
            remaining = total_power_w - allocated

            if not saturated_now:
                break
            saturated_set = set(saturated_now)
            active = [(n, r) for n, r in active if n not in saturated_set]

        if now is not None:
            self._update_direction_tracking(per_battery, now)

        return BalancingResult(
            per_battery_w=per_battery,
            unallocated_w=remaining,
            iterations=iterations,
        )

    # ------------------------------------------------------------------ helpers

    def _eligible_batteries(
        self,
        total_power_w: float,
        states: Mapping[str, BatteryState],
        now: datetime | None = None,
        discharge_caps: Mapping[str, float] | None = None,
    ) -> list[tuple[str, BatteryRole]]:
        """Drop batteries that cannot accept the requested direction.

        Also excludes batteries that reversed direction too recently (anti-short-cycle).
        """
        caps = discharge_caps or {}
        eligible: list[tuple[str, BatteryRole]] = []
        requested_dir = 1 if total_power_w > 0 else (-1 if total_power_w < 0 else 0)
        for name, role in self._batteries:
            state = states.get(name)
            if state is None or not state.available:
                continue
            if total_power_w > 0 and state.soc_pct >= role.soc_max_pct:
                continue
            # Discharge: excluded only when the SoC taper has ramped its cap to ~0
            # (at/under the floor, held there by the re-arm hysteresis). Above the
            # floor the battery is eligible but rate-limited by discharge_caps.
            if total_power_w < 0 and caps.get(name, 0.0) <= _RESIDUAL_TOLERANCE_W:
                continue
            # Anti-short-cycle guard: block direction reversal during dwell window.
            if now is not None and self._min_dwell_s > 0 and requested_dir != 0:
                last_dir = self._last_direction.get(name, 0)
                if last_dir != 0 and last_dir != requested_dir:
                    last_at = self._last_direction_at.get(name)
                    if last_at is not None:
                        elapsed = (now - last_at).total_seconds()
                        if elapsed < self._min_dwell_s:
                            continue
            eligible.append((name, role))
        return eligible

    def _update_direction_tracking(self, per_battery: dict[str, float], now: datetime) -> None:
        """Record direction changes for the anti-short-cycle guard."""
        for name, power_w in per_battery.items():
            current_dir = (
                1
                if power_w > _RESIDUAL_TOLERANCE_W
                else (-1 if power_w < -_RESIDUAL_TOLERANCE_W else 0)
            )
            if current_dir == 0:
                continue
            last_dir = self._last_direction.get(name, 0)
            if current_dir != last_dir:
                self._last_direction[name] = current_dir
                self._last_direction_at[name] = now

    def _compute_weights(
        self,
        active: Sequence[tuple[str, BatteryRole]],
        states: Mapping[str, BatteryState],
        *,
        charging: bool,
    ) -> dict[str, float]:
        total_capacity = sum(role.capacity_kwh for _, role in active)
        soc_values = [states[name].soc_pct for name, _ in active]
        soc_mean = sum(soc_values) / len(soc_values)

        weights: dict[str, float] = {}
        for name, role in active:
            cap_weight = role.capacity_kwh / total_capacity if total_capacity > 0 else 0.0
            soc = states[name].soc_pct
            if charging:
                eq_weight = max(0.0, soc_mean - soc + _EQUALISER_EPSILON)
            else:
                eq_weight = max(0.0, soc - soc_mean + _EQUALISER_EPSILON)
            weight = self._alpha * cap_weight + (1.0 - self._alpha) * eq_weight
            # Charge priority: a small station you want topped up first (River 2) grabs the
            # surplus before the rest of the fleet — a dominating additive weight until it
            # reaches its target SoC. It saturates at its rate/entity cap and the saturation
            # loop then hands the remainder to the others.
            if (
                charging
                and role.charge_priority_target_soc_pct is not None
                and soc < role.charge_priority_target_soc_pct
            ):
                weight += _CHARGE_PRIORITY_WEIGHT
            weights[name] = weight
        return weights

    @staticmethod
    def _clamp_to_limits(max_charge_w: float, max_discharge_w: float, proposed_w: float) -> float:
        if proposed_w > 0:
            return min(proposed_w, max_charge_w)
        if proposed_w < 0:
            return max(proposed_w, -max_discharge_w)
        return 0.0

    def _discharge_caps(
        self, total_power_w: float, states: Mapping[str, BatteryState]
    ) -> dict[str, float]:
        """Per-battery max discharge (W) after the SoC taper + hysteresis.

        Only computed for a discharge request (``total_power_w < 0``); for a charge the
        map is empty and the full ``max_discharge_power_w`` applies. Updates the per-battery
        rest latch as a side effect (once per tick).
        """
        caps: dict[str, float] = {}
        if total_power_w >= 0:
            return caps
        for name, role in self._batteries:
            state = states.get(name)
            if state is None or not state.available:
                continue
            scale = self._discharge_scale(name, role, state.soc_pct)
            caps[name] = scale * float(role.max_discharge_power_w)
        return caps

    def _discharge_scale(self, name: str, role: BatteryRole, soc_pct: float) -> float:
        """Fraction (0..1) of the discharge rate allowed at this SoC.

        Zero at/under ``soc_min + margin`` (the floor), ramping linearly to 1 over the
        taper band above it. A hysteresis latch keeps a rested battery at 0 until its SoC
        climbs past ``floor + rearm`` — so a SoC hovering on the 1 %-quantised boundary
        can't flip the discharge on/off every tick (the morning discharge yoyo).
        """
        floor = float(role.soc_min_pct) + _DISCHARGE_SOC_MARGIN_PCT
        if self._discharge_rested.get(name, False):
            if soc_pct < floor + _DISCHARGE_REARM_PCT:
                return 0.0  # stay rested until well clear of the floor
            self._discharge_rested[name] = False
        if soc_pct <= floor:
            self._discharge_rested[name] = True
            return 0.0
        return min(1.0, (soc_pct - floor) / _DISCHARGE_TAPER_BAND_PCT)
