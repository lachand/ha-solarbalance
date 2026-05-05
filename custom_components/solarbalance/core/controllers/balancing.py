"""Hybrid balancing controller.

Distributes a global charge or discharge demand across N batteries with
heterogeneous capacities and SoC, using a tunable mix of capacity-weighted
and SoC-equalising allocation. See SPECIFICATIONS §6.2.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import BatteryRole, BatteryState, Device

# Numerical guardrails
_MAX_ITER = 32
_RESIDUAL_TOLERANCE_W = 1.0
_EQUALISER_EPSILON = 1e-3


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
    """

    def __init__(self, devices: Sequence[Device], alpha: float = 0.6) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be in [0, 1]")
        self._batteries: tuple[tuple[str, BatteryRole], ...] = tuple(
            (d.name, d.battery) for d in devices if d.battery is not None
        )
        self._alpha = alpha

    def allocate(
        self,
        total_power_w: float,
        states: Mapping[str, BatteryState],
    ) -> BalancingResult:
        """Allocate `total_power_w` across batteries (positive = charge)."""
        eligible = self._eligible_batteries(total_power_w, states)
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
                clamped = self._clamp_to_limits(role, proposed)
                per_battery[name] = clamped
                if abs(clamped - proposed) > _RESIDUAL_TOLERANCE_W:
                    saturated_now.append(name)

            allocated = sum(per_battery.values())
            remaining = total_power_w - allocated

            if not saturated_now:
                break
            saturated_set = set(saturated_now)
            active = [(n, r) for n, r in active if n not in saturated_set]

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
    ) -> list[tuple[str, BatteryRole]]:
        """Drop batteries that cannot accept the requested direction."""
        eligible: list[tuple[str, BatteryRole]] = []
        for name, role in self._batteries:
            state = states.get(name)
            if state is None or not state.available:
                continue
            if total_power_w > 0 and state.soc_pct >= role.soc_max_pct:
                continue
            if total_power_w < 0 and state.soc_pct <= role.soc_min_pct:
                continue
            eligible.append((name, role))
        return eligible

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
            weights[name] = self._alpha * cap_weight + (1.0 - self._alpha) * eq_weight
        return weights

    @staticmethod
    def _clamp_to_limits(role: BatteryRole, proposed_w: float) -> float:
        if proposed_w > 0:
            return min(proposed_w, float(role.max_charge_power_w))
        if proposed_w < 0:
            return max(proposed_w, -float(role.max_discharge_power_w))
        return 0.0
