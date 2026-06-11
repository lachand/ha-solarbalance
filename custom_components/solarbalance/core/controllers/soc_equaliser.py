"""Indirect SoC equaliser for non-controllable batteries.

Some batteries report their state (SoC, power) but cannot be commanded
charge/discharge over Home Assistant — the user can only leave them in their own
"automatic" mode. This controller steers such a battery *indirectly*: by biasing
the aggregate charge/discharge demand of the controllable batteries it shifts the
AC-bus power balance, which the automatic battery then absorbs (charges) or
covers (discharges) on its own logic.

The control objective is SoC equalisation — drive each non-controllable
battery's SoC toward the mean SoC of the controllable fleet. The output is a
single *steering bias* (W) added to the aggregate ``total_power_w`` that the
coordinator hands to the BalancingController:

- ``steering_w < 0`` → controllable batteries discharge more → AC surplus →
  the automatic battery charges.
- ``steering_w > 0`` → controllable batteries charge more → AC deficit →
  the automatic battery discharges.

Safety: the steering is never forced onto the grid. The same tick's
zero-injection / self-consumption loops keep the grid at its setpoint, so any
power the automatic battery does *not* absorb is pulled back on the next tick.
The steering therefore only "sticks" to the extent the automatic battery
cooperates, and naturally saturates on the controllable batteries' capacity and
SoC limits.

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import BatteryRole, BatteryState


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
            SoC error. The aggregate steering is clamped to ``max_steering_w``.
        max_steering_w: Hard cap on the absolute steering bias, protecting the
            controllable batteries and the grid from large swings.
        soc_deadband_pct: Half-width of the SoC deadband; a battery within this
            band of the target contributes no steering (avoids hunting).
    """

    def __init__(
        self,
        uncontrollable: Sequence[tuple[str, BatteryRole]],
        *,
        kp_w_per_pct: float = 80.0,
        max_steering_w: float = 1500.0,
        soc_deadband_pct: float = 2.0,
    ) -> None:
        if kp_w_per_pct < 0:
            raise ValueError("kp_w_per_pct must be non-negative")
        if max_steering_w < 0:
            raise ValueError("max_steering_w must be non-negative")
        if soc_deadband_pct < 0:
            raise ValueError("soc_deadband_pct must be non-negative")
        self._uncontrollable = tuple(uncontrollable)
        self._kp = kp_w_per_pct
        self._max_steering_w = max_steering_w
        self._deadband = soc_deadband_pct

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
                continue
            error = target - state.soc_pct  # > 0 → below target → wants to charge
            if abs(error) <= self._deadband:
                continue
            # Don't steer past the automatic battery's own SoC bounds — it would
            # refuse anyway and we'd only push power to the grid.
            if error > 0 and state.soc_pct >= role.soc_max_pct:
                continue
            if error < 0 and state.soc_pct <= role.soc_min_pct:
                continue
            demand = self._kp * error  # > 0 → want to charge the automatic battery
            # Charging the automatic battery requires the controllable fleet to
            # discharge → negative bias on total_power_w.
            steering_w += -demand
            any_active = True

        steering_w = max(-self._max_steering_w, min(self._max_steering_w, steering_w))
        return SocEqualiserResult(
            steering_w=steering_w,
            target_soc_pct=target,
            in_deadband=not any_active,
        )
