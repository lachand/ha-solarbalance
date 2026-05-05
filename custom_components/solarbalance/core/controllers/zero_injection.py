"""Zero-injection PI controller with hysteresis and anti-windup.

Computes a *delta* on the aggregate battery charge power that should be
applied at the next tick to keep the grid meter at the target setpoint.
The actual per-battery distribution is performed by the BalancingController.

See SPECIFICATIONS §6.3.
"""

from dataclasses import dataclass, replace


@dataclass(slots=True, frozen=True)
class ZeroInjectionState:
    """Persistent state of the PI controller (survives restart via Store)."""

    integral_w_s: float = 0.0


@dataclass(slots=True, frozen=True)
class ZeroInjectionResult:
    """Output of one PI tick."""

    correction_w: float
    in_deadband: bool
    new_state: ZeroInjectionState


class ZeroInjectionController:
    """Discrete-time PI controller with deadband and clamped integral.

    Conventions:
    - `grid_power_w` follows the meter convention: positive = import, negative = export.
    - `setpoint_w` is the target grid power (typically 0; can be slightly negative
      to leave a safety margin against momentary export spikes).
    - The returned `correction_w` is added to the current aggregate battery
      charge power (positive correction → charge more / discharge less).
    """

    def __init__(
        self,
        *,
        kp: float = 0.6,
        ki: float = 0.05,
        hysteresis_w: float = 50.0,
        integral_clamp_w_s: float = 1_000_000.0,
    ) -> None:
        if hysteresis_w < 0:
            raise ValueError("hysteresis_w must be non-negative")
        if integral_clamp_w_s <= 0:
            raise ValueError("integral_clamp_w_s must be strictly positive")
        self._kp = kp
        self._ki = ki
        self._hysteresis_w = hysteresis_w
        self._integral_clamp = integral_clamp_w_s

    def step(
        self,
        *,
        grid_power_w: float,
        setpoint_w: float,
        dt_s: float,
        state: ZeroInjectionState,
    ) -> ZeroInjectionResult:
        """Run one control step.

        The error is `grid_power_w - setpoint_w`. A positive error means we are
        importing more than wanted (or exporting less than allowed), so the
        correction is *negative* — discharge more / charge less.
        """
        if dt_s <= 0:
            raise ValueError("dt_s must be strictly positive")

        error = grid_power_w - setpoint_w

        if abs(error) <= self._hysteresis_w:
            return ZeroInjectionResult(
                correction_w=0.0,
                in_deadband=True,
                new_state=state,
            )

        new_integral = max(
            -self._integral_clamp,
            min(self._integral_clamp, state.integral_w_s + error * dt_s),
        )
        # Convention: correction adds to battery *charge* power.
        # error > 0 (over-importing) → we want to discharge more → negative correction.
        correction = -(self._kp * error + self._ki * new_integral)

        return ZeroInjectionResult(
            correction_w=correction,
            in_deadband=False,
            new_state=replace(state, integral_w_s=new_integral),
        )
