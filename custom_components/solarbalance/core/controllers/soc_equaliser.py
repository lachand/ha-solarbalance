"""Indirect SoC equaliser for non-controllable batteries (cascaded).

Some batteries report their state (SoC, power) but cannot be commanded
charge/discharge over Home Assistant — the user can only leave them in their own
"automatic" mode. This controller steers such a battery *indirectly* by shifting
the AC-bus balance through the zero-injection regulator.

**Why a cascade (and not a fleet-power bias).** An earlier version added a fleet
*power* bias to the aggregate target every tick. Because the target is
``current_fleet_power + bias``, the bias was re-added on top of a position that
already contained it → it integrated, ramped to the battery's AC limit, then
spilled to the grid and fought zero-injection (a tick-frequency limit cycle).

This version is a slow **outer loop**: it holds a bounded *grid-setpoint offer*
and drives it so the automatic battery's **measured** charge power reaches a
SoC-derived target. The single zero-injection inner loop then regulates the grid
to ``setpoint - offer`` -- only one integrator acts on the fleet, so there is no
runaway.

- ``grid_setpoint_bias_w > 0`` → offer surplus (ZI targets a slight export) →
  controllable fleet discharges → automatic battery charges.
- ``grid_setpoint_bias_w < 0`` → offer deficit → fleet charges → automatic
  battery discharges.

**Anti-windup / safety.** If the offered surplus/deficit reaches the *grid*
instead of the automatic battery (the battery is not absorbing it), the offer is
backed off rather than grown — so it never forces grid import/export. The offer
is also hard-clamped to ``max_offer_w``. Requires zero-injection enabled.

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import BatteryRole, BatteryState

# Grid power (W) beyond the deadband above which the offered surplus/deficit is
# deemed to be hitting the grid (not absorbed by the automatic battery).
_LEAK_W = 100.0


@dataclass(slots=True, frozen=True)
class SocEqualiserResult:
    """Output of one equaliser tick.

    Attributes:
        grid_setpoint_bias_w: Offer to subtract from the zero-injection setpoint
            (positive offers surplus → charges the automatic battery; negative
            offers a deficit → discharges it).
        target_soc_pct: Mean SoC of the controllable fleet, or ``None``.
        in_deadband: True when no battery is being steered this tick.
    """

    grid_setpoint_bias_w: float
    target_soc_pct: float | None
    in_deadband: bool


class SocEqualiserController:
    """Drive non-controllable batteries' SoC toward the controllable fleet mean.

    Args:
        uncontrollable: ``(device_name, BatteryRole)`` pairs to steer indirectly.
        kp_w_per_pct: Gain mapping SoC error (%) to a target auto-battery power.
        max_offer_w: Hard clamp on the grid-setpoint offer.
        soc_deadband_pct: SoC deadband half-width; within it, no steering.
        step_w: Max change of the offer per tick (slow ramp / back-off rate).
    """

    def __init__(
        self,
        uncontrollable: Sequence[tuple[str, BatteryRole]],
        *,
        kp_w_per_pct: float = 80.0,
        max_offer_w: float = 1500.0,
        soc_deadband_pct: float = 2.0,
        step_w: float = 150.0,
    ) -> None:
        if kp_w_per_pct < 0:
            raise ValueError("kp_w_per_pct must be non-negative")
        if max_offer_w < 0:
            raise ValueError("max_offer_w must be non-negative")
        if soc_deadband_pct < 0:
            raise ValueError("soc_deadband_pct must be non-negative")
        if step_w <= 0:
            raise ValueError("step_w must be strictly positive")
        self._uncontrollable = tuple(uncontrollable)
        self._kp = kp_w_per_pct
        self._max_offer_w = max_offer_w
        self._deadband = soc_deadband_pct
        self._step_w = step_w
        self._offer_w = 0.0

    def step(
        self,
        *,
        controllable_states: Sequence[BatteryState],
        uncontrollable_states: Mapping[str, BatteryState],
        grid_w: float,
    ) -> SocEqualiserResult:
        """Update the offer for one tick and return it.

        Args:
            controllable_states: Controllable battery states; their mean available
                SoC is the equalisation target.
            uncontrollable_states: Steered battery states, keyed by device name.
            grid_w: Current (filtered) grid power, positive = import. Used to
                detect when the offer is leaking to the grid.
        """
        available = [s for s in controllable_states if s.available]
        if not available or not self._uncontrollable:
            self._offer_w = 0.0
            return SocEqualiserResult(0.0, None, True)

        target = sum(s.soc_pct for s in available) / len(available)

        fa_target = 0.0  # desired aggregate auto-battery power (+ = charge)
        fa_meas = 0.0  # measured aggregate auto-battery power
        active = False
        for name, role in self._uncontrollable:
            state = uncontrollable_states.get(name)
            if state is None or not state.available:
                continue
            error = target - state.soc_pct  # > 0 → below target → wants to charge
            if abs(error) <= self._deadband:
                continue
            if error > 0 and state.soc_pct >= role.soc_max_pct:
                continue
            if error < 0 and state.soc_pct <= role.soc_min_pct:
                continue
            cap_charge = float(
                role.ac_charge_limit_w if role.ac_charge_limit_w is not None
                else role.max_charge_power_w
            )
            fa = self._kp * error
            fa = max(-float(role.max_discharge_power_w), min(cap_charge, fa))
            fa_target += fa
            fa_meas += state.power_w
            active = True

        if not active:
            self._offer_w = self._decay(self._offer_w)
            return SocEqualiserResult(self._offer_w, target, True)

        # Anti-windup: if the offered surplus/deficit is reaching the grid (the
        # automatic battery is not absorbing it), back the offer off instead of
        # growing it — never force grid export/import.
        if self._offer_w > 0.0 and grid_w < -_LEAK_W:
            self._offer_w = max(0.0, self._offer_w - self._step_w)
        elif self._offer_w < 0.0 and grid_w > _LEAK_W:
            self._offer_w = min(0.0, self._offer_w + self._step_w)
        else:
            # Move the offer (rate-limited) toward making the auto reach fa_target.
            err = fa_target - fa_meas
            self._offer_w += max(-self._step_w, min(self._step_w, err))

        self._offer_w = max(-self._max_offer_w, min(self._max_offer_w, self._offer_w))
        return SocEqualiserResult(self._offer_w, target, False)

    def _decay(self, offer: float) -> float:
        """Relax the offer toward zero by one step (no active steering)."""
        if offer > 0.0:
            return max(0.0, offer - self._step_w)
        if offer < 0.0:
            return min(0.0, offer + self._step_w)
        return 0.0
