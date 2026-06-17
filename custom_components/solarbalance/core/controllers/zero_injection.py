"""Zero-injection PI controller with hysteresis and anti-windup.

Computes a *delta* on the aggregate battery charge power that should be
applied at the next tick to keep the grid meter at the target setpoint.
The actual per-battery distribution is performed by the BalancingController.

See SPECIFICATIONS §6.3.
"""

from dataclasses import dataclass, field, replace


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


@dataclass(slots=True, frozen=True)
class PerPhaseZeroInjectionState:
    """Persistent PI state for three-phase per-phase zero-injection.

    Each phase carries its own integral accumulator.
    """

    l1: ZeroInjectionState = field(default_factory=ZeroInjectionState)
    l2: ZeroInjectionState = field(default_factory=ZeroInjectionState)
    l3: ZeroInjectionState = field(default_factory=ZeroInjectionState)


@dataclass(slots=True, frozen=True)
class PerPhaseZeroInjectionResult:
    """Output of one per-phase PI tick.

    `correction_w` is the **sum** of all three phase corrections, ready to be
    fed to the balancing controller as the aggregate correction signal.
    Individual phase corrections are also exposed for logging / observability.
    """

    correction_l1_w: float
    correction_l2_w: float
    correction_l3_w: float
    in_deadband_l1: bool
    in_deadband_l2: bool
    in_deadband_l3: bool
    new_state: PerPhaseZeroInjectionState

    @property
    def correction_w(self) -> float:
        """Aggregate correction across all three phases."""
        return self.correction_l1_w + self.correction_l2_w + self.correction_l3_w

    @property
    def in_deadband(self) -> bool:
        """True only when all three phases are within their deadband."""
        return self.in_deadband_l1 and self.in_deadband_l2 and self.in_deadband_l3


class ZeroInjectionController:
    """Discrete-time PI controller with deadband and clamped integral.

    Conventions:
    - `grid_power_w` follows the meter convention: positive = import, negative = export.
    - `setpoint_w` is the target grid power (typically 0; can be slightly negative
      to leave a safety margin against momentary export spikes).
    - The returned `correction_w` is added to the current aggregate battery
      charge power (positive correction → charge more / discharge less).

    Gain calibration notes:
    - `kp=0.6` and `ki=0.05` are tuned for a reference tick interval of 10 s with
      a typical home battery of 1-3 kW. The integral accumulates as ``I += e * dt_s``
      (units: W·s), so Ki has units of 1/s and is tick-rate independent.
    - `integral_clamp_w_s`: anti-windup clamp on the integral accumulator. The
      default 30 000 W·s limits the integral-only contribution to
      ``30_000 x 0.05 = 1 500 W`` -- roughly the full discharge power of a 1.5 kW
      battery. Raise this proportionally for larger installations.
    """

    def __init__(
        self,
        *,
        kp_min: float = 0.2,
        kp_max: float = 0.6,
        knee_w: float = 600.0,
        ki: float = 0.05,
        hysteresis_w: float = 50.0,
        integral_clamp_w_s: float = 30_000.0,
    ) -> None:
        if hysteresis_w < 0:
            raise ValueError("hysteresis_w must be non-negative")
        if integral_clamp_w_s <= 0:
            raise ValueError("integral_clamp_w_s must be strictly positive")
        if kp_min < 0 or kp_max < 0:
            raise ValueError("kp_min/kp_max must be non-negative")
        if knee_w <= hysteresis_w:
            raise ValueError("knee_w must be greater than hysteresis_w")
        self._kp_min = kp_min
        self._kp_max = max(kp_min, kp_max)
        self._knee_w = knee_w
        self._ki = ki
        self._hysteresis_w = hysteresis_w
        self._integral_clamp = integral_clamp_w_s

    def kp_for(self, error: float) -> float:
        """Progressive gain: kp_min near the deadband, kp_max from ``knee_w`` on.

        Ramps linearly with |error| across ``(hysteresis_w, knee_w)`` so the loop
        is gentle near balance (no pumping against actuation lag / meter noise) and
        aggressive on a large deficit or export (fast wind-down). Exposed for the
        effective-gain diagnostic sensor.
        """
        span = self._knee_w - self._hysteresis_w
        frac = min(1.0, max(0.0, (abs(error) - self._hysteresis_w) / span))
        return self._kp_min + (self._kp_max - self._kp_min) * frac

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
        correction = -(self.kp_for(error) * error + self._ki * new_integral)

        return ZeroInjectionResult(
            correction_w=correction,
            in_deadband=False,
            new_state=replace(state, integral_w_s=new_integral),
        )


class PerPhaseZeroInjectionController:
    """Three independent PI controllers, one per phase (L1/L2/L3).

    Used when `per_phase_zi=True` on a three-phase PDL meter. Each phase
    has its own error signal and integral state. The aggregate correction
    (sum of the three phase corrections) is what the balancing controller
    receives; per-phase values are available for diagnostics.

    The setpoint is applied **per phase**: typically setpoint_w/3 when the
    target is a balanced three-phase zero-injection, or per-phase setpoints
    can be supplied individually.

    Args:
        kp_min/kp_max/knee_w: Progressive gain (same schedule for all phases).
        ki: Integral gain (same for all phases).
        hysteresis_w: Deadband half-width **per phase** in watts.
        integral_clamp_w_s: Anti-windup clamp **per phase**.
    """

    def __init__(
        self,
        *,
        kp_min: float = 0.2,
        kp_max: float = 0.6,
        knee_w: float = 600.0,
        ki: float = 0.05,
        hysteresis_w: float = 50.0,
        integral_clamp_w_s: float = 30_000.0,
    ) -> None:
        self._ctrl = ZeroInjectionController(
            kp_min=kp_min,
            kp_max=kp_max,
            knee_w=knee_w,
            ki=ki,
            hysteresis_w=hysteresis_w,
            integral_clamp_w_s=integral_clamp_w_s,
        )

    def kp_for(self, error: float) -> float:
        """Progressive gain for a per-phase error (same schedule on every phase)."""
        return self._ctrl.kp_for(error)

    def step(
        self,
        *,
        grid_l1_w: float,
        grid_l2_w: float,
        grid_l3_w: float,
        setpoint_l1_w: float,
        setpoint_l2_w: float,
        setpoint_l3_w: float,
        dt_s: float,
        state: PerPhaseZeroInjectionState,
    ) -> PerPhaseZeroInjectionResult:
        """Run one control step for all three phases.

        Each phase is controlled independently. `dt_s` must be strictly positive.
        """
        r1 = self._ctrl.step(
            grid_power_w=grid_l1_w, setpoint_w=setpoint_l1_w, dt_s=dt_s, state=state.l1
        )
        r2 = self._ctrl.step(
            grid_power_w=grid_l2_w, setpoint_w=setpoint_l2_w, dt_s=dt_s, state=state.l2
        )
        r3 = self._ctrl.step(
            grid_power_w=grid_l3_w, setpoint_w=setpoint_l3_w, dt_s=dt_s, state=state.l3
        )
        return PerPhaseZeroInjectionResult(
            correction_l1_w=r1.correction_w,
            correction_l2_w=r2.correction_w,
            correction_l3_w=r3.correction_w,
            in_deadband_l1=r1.in_deadband,
            in_deadband_l2=r2.in_deadband,
            in_deadband_l3=r3.in_deadband,
            new_state=PerPhaseZeroInjectionState(l1=r1.new_state, l2=r2.new_state, l3=r3.new_state),
        )
