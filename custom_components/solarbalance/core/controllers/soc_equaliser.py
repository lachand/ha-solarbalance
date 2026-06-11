"""Indirect SoC equaliser for non-controllable batteries.

Some batteries report their state (SoC, power) but cannot be commanded
charge/discharge over Home Assistant — the user can only leave them in their own
"automatic" mode. This controller steers such a battery *indirectly*: by biasing
the aggregate charge/discharge demand of the controllable batteries it shifts the
AC-bus power balance, which the automatic battery then absorbs (charges) or
covers (discharges) on its own logic.

The control objective is SoC equalisation — drive each non-controllable
battery's SoC toward the mean SoC of the controllable fleet. The output is a
single *steering bias* (W) added to the aggregate ``total_power_w`` handed to the
BalancingController:

- ``steering_w < 0`` → controllable batteries discharge more → AC surplus →
  the automatic battery charges.
- ``steering_w > 0`` → controllable batteries charge more → AC deficit →
  the automatic battery discharges.

To avoid pushing more than the automatic battery can absorb (the excess would
spill to the grid and fight zero-injection → oscillation), the per-battery bias
is bounded by three nested limits:

1. **AC capacity** (``ac_charge_limit_w`` / ``max_discharge_power_w``) — never
   command more than the battery's physical AC input/output rate.
2. **Adaptive allowance** — start from a small ``probe_step_w`` and grow it
   geometrically each tick while steering holds its direction (small steps first,
   progressively larger), capped by the AC capacity.
3. **Measured-response back-off** — if the automatic battery moves *against* the
   requested direction, reset the allowance to the small probe (don't fight a
   battery that is doing its own thing).

Finally the aggregate is clamped to ``max_steering_w``.

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import BatteryRole, BatteryState

# Geometric growth factor of the adaptive allowance per sustained tick.
_ALLOWANCE_GROWTH = 1.5
# Measured power (W, charge-positive) beyond which the battery counts as moving
# against the requested direction — back off below this noise floor.
_WRONG_WAY_EPS_W = 50.0


@dataclass(slots=True, frozen=True)
class SocEqualiserResult:
    """Output of one equaliser tick.

    Attributes:
        steering_w: Bias to add to the aggregate ``total_power_w`` (negative
            charges the automatic battery, positive discharges it).
        target_soc_pct: Mean SoC of the controllable fleet used as the target,
            or ``None`` when no controllable battery is available.
        in_deadband: True when no battery is outside its SoC deadband, i.e. the
            steering is zero this tick.
    """

    steering_w: float
    target_soc_pct: float | None
    in_deadband: bool


class SocEqualiserController:
    """Drive non-controllable batteries' SoC toward the controllable fleet mean.

    Args:
        uncontrollable: ``(device_name, BatteryRole)`` pairs of the batteries to
            steer indirectly (those declared ``controllable: false``).
        kp_w_per_pct: Proportional gain — watts of steering demand per percent of
            SoC error. Bounds the steady-state demand near the target.
        max_steering_w: Hard cap on the absolute aggregate steering bias.
        soc_deadband_pct: Half-width of the SoC deadband; a battery within this
            band of the target contributes no steering (avoids hunting).
        probe_step_w: Initial steering step; the per-battery allowance starts here
            and grows geometrically while the battery follows the request.
    """

    def __init__(
        self,
        uncontrollable: Sequence[tuple[str, BatteryRole]],
        *,
        kp_w_per_pct: float = 80.0,
        max_steering_w: float = 1500.0,
        soc_deadband_pct: float = 2.0,
        probe_step_w: float = 150.0,
    ) -> None:
        if kp_w_per_pct < 0:
            raise ValueError("kp_w_per_pct must be non-negative")
        if max_steering_w < 0:
            raise ValueError("max_steering_w must be non-negative")
        if soc_deadband_pct < 0:
            raise ValueError("soc_deadband_pct must be non-negative")
        if probe_step_w <= 0:
            raise ValueError("probe_step_w must be strictly positive")
        self._uncontrollable = tuple(uncontrollable)
        self._kp = kp_w_per_pct
        self._max_steering_w = max_steering_w
        self._deadband = soc_deadband_pct
        self._probe_step_w = probe_step_w
        self._allowance: dict[str, float] = {}
        self._last_dir: dict[str, int] = {}

    def step(
        self,
        *,
        controllable_states: Sequence[BatteryState],
        uncontrollable_states: Mapping[str, BatteryState],
    ) -> SocEqualiserResult:
        """Compute the steering bias for one tick.

        Args:
            controllable_states: States of the controllable batteries; their mean
                available SoC defines the equalisation target.
            uncontrollable_states: States of the steered batteries, keyed by
                device name.
        """
        available = [s for s in controllable_states if s.available]
        if not available or not self._uncontrollable:
            return SocEqualiserResult(steering_w=0.0, target_soc_pct=None, in_deadband=True)

        target = sum(s.soc_pct for s in available) / len(available)

        steering_w = 0.0
        any_active = False
        for name, role in self._uncontrollable:
            state = uncontrollable_states.get(name)
            if state is None or not state.available:
                self._reset(name)
                continue
            error = target - state.soc_pct  # > 0 → below target → wants to charge
            if abs(error) <= self._deadband:
                self._reset(name)
                continue
            # Don't steer past the automatic battery's own SoC bounds — it would
            # refuse anyway and we'd only push power to the grid.
            if error > 0 and state.soc_pct >= role.soc_max_pct:
                self._reset(name)
                continue
            if error < 0 and state.soc_pct <= role.soc_min_pct:
                self._reset(name)
                continue

            desired_dir = 1 if error > 0 else -1  # +1 charge the auto, -1 discharge it
            ac_cap = self._ac_capacity_w(role, desired_dir)
            going_wrong = (desired_dir > 0 and state.power_w < -_WRONG_WAY_EPS_W) or (
                desired_dir < 0 and state.power_w > _WRONG_WAY_EPS_W
            )

            if self._last_dir.get(name) != desired_dir or going_wrong:
                allowance = self._probe_step_w
            else:
                allowance = self._allowance.get(name, self._probe_step_w) * _ALLOWANCE_GROWTH
            allowance = min(allowance, ac_cap)
            self._allowance[name] = allowance
            self._last_dir[name] = desired_dir

            demand_mag = min(abs(self._kp * error), allowance)
            steering_w += -desired_dir * demand_mag
            any_active = True

        steering_w = max(-self._max_steering_w, min(self._max_steering_w, steering_w))
        return SocEqualiserResult(
            steering_w=steering_w,
            target_soc_pct=target,
            in_deadband=not any_active,
        )

    @staticmethod
    def _ac_capacity_w(role: BatteryRole, desired_dir: int) -> float:
        """AC absorption (charge) or delivery (discharge) limit for ``role`` (W)."""
        if desired_dir > 0:
            limit = role.ac_charge_limit_w
            return float(limit if limit is not None else role.max_charge_power_w)
        return float(role.max_discharge_power_w)

    def _reset(self, name: str) -> None:
        """Forget the adaptive state for a battery that is idle/out of band."""
        self._allowance.pop(name, None)
        self._last_dir.pop(name, None)
