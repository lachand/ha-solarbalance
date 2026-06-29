"""Indirect SoC equaliser for non-controllable batteries (proportional + slow).

Some batteries report their state (SoC, power) but cannot be commanded
charge/discharge over Home Assistant -- the user can only leave them in their own
"automatic" mode (typically a cloud-polled station). This controller steers such
a battery *indirectly* by shifting the AC-bus balance: the coordinator applies
this offer as a **direct floor** on the controllable fleet's power target (see
``regulation.apply_equaliser_offer``) -- so it can force a discharge even while
the fleet is charging from its own PV -- and zero-injection regulates the rest.

- ``grid_setpoint_bias_w > 0`` -> offer surplus -> fleet forced to discharge at
  least this much -> automatic battery charges.
- ``grid_setpoint_bias_w < 0`` -> offer deficit -> fleet forced to charge ->
  automatic battery discharges.

**Design (why it is shaped this way).** An earlier version made the offer an
*integrator* that servoed the automatic battery's measured power. Combined with
the zero-injection loop and the cloud battery's actuation dead-time (~minute), it
was a second integrator behind a long delay -> a slow, large-amplitude limit
cycle (the offer sawtoothed to its clamp and back, throwing kW-scale grid spikes
at every reset). This version removes that:

1. **Proportional, not integrating.** The offer target is a bounded function of
   the SoC error (``kp * error``, clamped). It cannot wind up.
2. **Slow cadence.** The offer only moves once every ``cadence`` ticks, with the
   cadence derived from the *measured* response lag of the automatic battery
   (``adaptive_cadence``) so it stays well slower than the plant -- never faster
   than the cloud station can follow.
3. **Dead-time-aware back-off.** An export/import beyond the deadband only backs
   the offer off when it *persists* **and** the automatic battery's measured
   power is **not** moving toward its target -- i.e. a genuine grid leak, not the
   zero-injection loop legitimately executing the offer during the dead-time.
4. **Symmetric slew + arming hysteresis.** Every change (including resets and
   relaxation) is rate-limited by ``step_w``; steering stops inside the SoC
   deadband and only re-arms past ``deadband + rearm_margin`` -- no sawtooth.

Requires zero-injection enabled. Pure module -- no Home Assistant imports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import BatteryRole, BatteryState

# Grid power (W) beyond the deadband above which the offered surplus/deficit is
# *suspected* of hitting the grid (not absorbed by the automatic battery).
_LEAK_W = 100.0
# Change in the automatic battery's measured power (W) that counts as it
# "responding" to the offer -- used both to confirm it is absorbing (so an export
# is the ZI executing the offer, not a leak) and to time the response lag.
_FA_RESPONSE_W = 100.0
# EMA weight for the measured response-lag estimate (slow, robust to noise).
_LAG_EMA_ALPHA = 0.3
# Per-move step is proportional to the remaining distance to the target: big steps
# when far (fast correction of a large SoC gap), gentle steps near equilibrium (no
# pumping). Bounded below by _MIN_STEP_W and above by the configured step_w.
_APPROACH_GAIN = 0.5
_MIN_STEP_W = 25.0


@dataclass(slots=True, frozen=True)
class SocEqualiserResult:
    """Output of one equaliser tick.

    Attributes:
        grid_setpoint_bias_w: Offer to subtract from the zero-injection setpoint
            (positive offers surplus -> charges the automatic battery; negative
            offers a deficit -> discharges it).
        target_soc_pct: Mean SoC of the controllable fleet, or ``None``.
        in_deadband: True when no battery is being steered this tick.
        cadence_ticks: Ticks currently waited between offer moves (observability).
        lag_ticks: Measured automatic-battery response lag in ticks, or ``None``
            until first measured (observability / adaptive-cadence input).
    """

    grid_setpoint_bias_w: float
    target_soc_pct: float | None
    in_deadband: bool
    cadence_ticks: int
    lag_ticks: float | None


class SocEqualiserController:
    """Drive non-controllable batteries' SoC toward the controllable fleet mean.

    Args:
        uncontrollable: ``(device_name, BatteryRole)`` pairs to steer indirectly.
        kp_w_per_pct: Gain mapping SoC error (%) to the offer target (W).
        max_offer_w: Hard clamp on the grid-setpoint offer.
        soc_deadband_pct: SoC deadband half-width; within it, no steering.
        step_w: Upper bound on the per-move offer change (the step is proportional
            to the remaining gap, capped here; symmetric, incl. resets).
        cadence_ticks: Minimum ticks between offer moves (the slow-loop floor).
        adaptive_cadence: Derive the cadence from the measured response lag.
        max_cadence_ticks: Upper clamp on the (adaptive) cadence.
        rearm_margin_pct: Extra SoC error beyond the deadband required to resume
            steering once stopped (arming hysteresis).
        leak_persist_ticks: Minimum consecutive leak ticks before backing off.
    """

    def __init__(
        self,
        uncontrollable: Sequence[tuple[str, BatteryRole]],
        *,
        kp_w_per_pct: float = 80.0,
        max_offer_w: float = 1500.0,
        soc_deadband_pct: float = 2.0,
        step_w: float = 150.0,
        cadence_ticks: int = 6,
        adaptive_cadence: bool = True,
        max_cadence_ticks: int = 30,
        rearm_margin_pct: float = 1.0,
        leak_persist_ticks: int = 3,
        min_pv_w: float = 200.0,
    ) -> None:
        if kp_w_per_pct < 0:
            raise ValueError("kp_w_per_pct must be non-negative")
        if min_pv_w < 0:
            raise ValueError("min_pv_w must be non-negative")
        if max_offer_w < 0:
            raise ValueError("max_offer_w must be non-negative")
        if soc_deadband_pct < 0:
            raise ValueError("soc_deadband_pct must be non-negative")
        if step_w <= 0:
            raise ValueError("step_w must be strictly positive")
        if cadence_ticks < 1:
            raise ValueError("cadence_ticks must be >= 1")
        if max_cadence_ticks < cadence_ticks:
            raise ValueError("max_cadence_ticks must be >= cadence_ticks")
        if rearm_margin_pct < 0:
            raise ValueError("rearm_margin_pct must be non-negative")
        if leak_persist_ticks < 1:
            raise ValueError("leak_persist_ticks must be >= 1")
        self._uncontrollable = tuple(uncontrollable)
        self._kp = kp_w_per_pct
        self._max_offer_w = max_offer_w
        self._deadband = soc_deadband_pct
        self._step_w = step_w
        self._cadence_floor = cadence_ticks
        self._adaptive = adaptive_cadence
        self._max_cadence_ticks = max_cadence_ticks
        self._rearm_margin = rearm_margin_pct
        self._leak_persist_floor = leak_persist_ticks
        self._min_pv_w = min_pv_w
        # Dynamic state (not persisted across restarts; starts neutral).
        self._offer_w = 0.0
        self._armed = True
        self._ticks_since_move = 0
        self._leak_ticks = 0
        self._disarm_ticks = 0
        self._prev_fa_meas: float | None = None
        self._last_moved_offer_w = 0.0
        self._lag_ema: float | None = None
        self._lag_watch_active = False
        self._lag_watch_ticks = 0
        self._lag_watch_base_fa = 0.0
        self._lag_watch_dir = 1.0

    def set_max_step_w(self, step_w: float) -> None:
        """Override the per-move step cap (used by the supervisory auto-tuner)."""
        self._step_w = step_w

    def step(
        self,
        *,
        controllable_states: Sequence[BatteryState],
        uncontrollable_states: Mapping[str, BatteryState],
        grid_w: float,
        available_pv_w: float = 0.0,
    ) -> SocEqualiserResult:
        """Update the offer for one tick and return it.

        Args:
            controllable_states: Controllable battery states; their mean available
                SoC is the equalisation target.
            uncontrollable_states: Steered battery states, keyed by device name.
            grid_w: Current (filtered) grid power, positive = import. Used to
                detect when the offer is leaking to the grid.
            available_pv_w: PV production of the controllable fleet. The offer is
                gated on it (``< min_pv_w`` -> no steering) and capped to it, so
                the equaliser only redistributes **solar** -- never drains a
                battery into another at a round-trip loss.
        """
        available = [s for s in controllable_states if s.available]
        if not available or not self._uncontrollable:
            self._offer_w = self._slew(self._offer_w, 0.0)
            self._reset_dynamics()
            return self._result(None, in_deadband=True)

        if available_pv_w < self._min_pv_w:
            # Not enough solar to redistribute: relax to 0 rather than move stored
            # energy battery-to-battery (lossy).
            self._armed = False
            self._offer_w = self._slew(self._offer_w, 0.0)
            self._reset_dynamics()
            return self._result(None, in_deadband=True)

        target = sum(s.soc_pct for s in available) / len(available)
        # Arming hysteresis: harder to start (deadband + margin) than to stop.
        threshold = self._deadband if self._armed else self._deadband + self._rearm_margin

        offer_target = 0.0
        fa_meas = 0.0
        active = False
        for name, role in self._uncontrollable:
            state = uncontrollable_states.get(name)
            # Skip a stale battery: a cloud station that is unplugged/not updating keeps
            # reporting its last SoC, and steering on that dead value made the offer (and
            # the whole binding chain) flutter on/off as the entity flapped available.
            if state is None or not state.available or state.stale:
                continue
            error = target - state.soc_pct  # > 0 -> below target -> wants to charge
            if abs(error) <= threshold:
                continue
            if error > 0 and state.soc_pct >= role.soc_max_pct:
                continue
            if error < 0 and state.soc_pct <= role.soc_min_pct:
                continue
            cap_charge = float(
                role.ac_charge_limit_w
                if role.ac_charge_limit_w is not None
                else role.max_charge_power_w
            )
            contribution = self._kp * error
            contribution = max(-float(role.max_discharge_power_w), min(cap_charge, contribution))
            offer_target += contribution
            fa_meas += state.power_w
            active = True

        if not active:
            # Inside the (hysteresis-widened) deadband or at a SoC bound. Hold a
            # meaningful offer through a brief dip (cloud SoC quantization) before
            # relaxing, so the offer doesn't flutter at the edge. The dwell adapts to
            # the cloud battery's *measured* response lag (_leak_persist) — a slow
            # station gets a longer hold — so a varying delay doesn't cause a collapse;
            # relax once the dip persists past it or the offer is already negligible.
            if abs(self._offer_w) > _MIN_STEP_W and self._disarm_ticks < self._leak_persist():
                self._disarm_ticks += 1
                return self._result(target, in_deadband=False)
            self._armed = False
            self._offer_w = self._slew(self._offer_w, 0.0)
            self._reset_dynamics()
            return self._result(target, in_deadband=True)

        self._armed = True
        self._disarm_ticks = 0
        offer_target = self._clamp_offer(offer_target)
        # Never transfer more than the controllable fleet's PV: redistribute solar,
        # don't drain its battery into the automatic one (round-trip loss).
        offer_target = max(-available_pv_w, min(available_pv_w, offer_target))
        if self._prev_fa_meas is None:
            self._prev_fa_meas = fa_meas
        self._observe_lag(fa_meas)

        # Dead-time-aware back-off. A suspected leak (export/import beyond the
        # deadband while the automatic battery is NOT moving toward its target)
        # first *holds* the offer; only once it persists past the response lag is
        # it backed off. This never forces grid exchange, yet does not fight the
        # ZI loop while it legitimately executes the offer during the cloud
        # battery's dead-time (then the battery is responding -> not a leak).
        if self._is_leaking(grid_w, fa_meas):
            self._leak_ticks += 1
            if self._leak_ticks >= self._leak_persist():
                self._offer_w = self._slew(self._offer_w, 0.0)
                self._prev_fa_meas = fa_meas
                self._last_moved_offer_w = self._offer_w
                self._ticks_since_move = 0
            # else: suspected leak building -> hold (do not grow into it).
            return self._result(target, in_deadband=False)

        self._leak_ticks = 0
        # Move toward the target, but only once per cadence -- the slow outer loop
        # must stay well slower than the plant's response lag.
        self._ticks_since_move += 1
        if self._ticks_since_move < self._effective_cadence():
            return self._result(target, in_deadband=False)
        self._offer_w = self._clamp_offer(self._slew(self._offer_w, offer_target))
        self._after_move(fa_meas)
        return self._result(target, in_deadband=False)

    # -- internals ---------------------------------------------------------

    def _result(self, target: float | None, *, in_deadband: bool) -> SocEqualiserResult:
        return SocEqualiserResult(
            grid_setpoint_bias_w=self._offer_w,
            target_soc_pct=target,
            in_deadband=in_deadband,
            cadence_ticks=self._effective_cadence(),
            lag_ticks=self._lag_ema,
        )

    def _clamp_offer(self, value: float) -> float:
        return max(-self._max_offer_w, min(self._max_offer_w, value))

    def _slew(self, value: float, target: float) -> float:
        """Move ``value`` toward ``target``, proportionally to the remaining gap.

        The step is ``|remaining| * _APPROACH_GAIN`` bounded to ``[_MIN_STEP_W,
        step_w]`` -- big when far (a large SoC gap is corrected in a few moves),
        gentle near equilibrium (no pumping). Snaps to target within the floor.
        """
        remaining = target - value
        if abs(remaining) <= _MIN_STEP_W:
            return target
        magnitude = min(self._step_w, max(_MIN_STEP_W, abs(remaining) * _APPROACH_GAIN))
        return value + (magnitude if remaining > 0 else -magnitude)

    def _is_leaking(self, grid_w: float, fa_meas: float) -> bool:
        """True when the offer is reaching the grid, not the automatic battery."""
        prev = self._prev_fa_meas
        sign = 1.0 if self._offer_w > 0.0 else -1.0 if self._offer_w < 0.0 else 0.0
        responding = prev is not None and (fa_meas - prev) * sign >= _FA_RESPONSE_W
        if responding or sign == 0.0:
            return False
        return (self._offer_w > 0.0 and grid_w < -_LEAK_W) or (
            self._offer_w < 0.0 and grid_w > _LEAK_W
        )

    def _observe_lag(self, fa_meas: float) -> None:
        """Advance an active response-lag watch and update the EMA on response."""
        if not self._adaptive or not self._lag_watch_active:
            return
        self._lag_watch_ticks += 1
        moved = (fa_meas - self._lag_watch_base_fa) * self._lag_watch_dir
        if moved >= _FA_RESPONSE_W:
            lag = float(max(1, self._lag_watch_ticks))
            self._lag_ema = (
                lag
                if self._lag_ema is None
                else _LAG_EMA_ALPHA * lag + (1.0 - _LAG_EMA_ALPHA) * self._lag_ema
            )
            self._lag_watch_active = False
        elif self._lag_watch_ticks > self._max_cadence_ticks * 2:
            self._lag_watch_active = False  # no response in time; keep last estimate

    def _after_move(self, fa_meas: float) -> None:
        """Record a move; arm a lag watch when the offer changed meaningfully."""
        moved = self._offer_w - self._last_moved_offer_w
        if self._adaptive and abs(moved) >= self._step_w * 0.5 and not self._lag_watch_active:
            self._lag_watch_active = True
            self._lag_watch_ticks = 0
            self._lag_watch_base_fa = fa_meas
            self._lag_watch_dir = 1.0 if moved > 0 else -1.0
        self._last_moved_offer_w = self._offer_w
        self._prev_fa_meas = fa_meas
        self._ticks_since_move = 0

    def _effective_cadence(self) -> int:
        if self._adaptive and self._lag_ema is not None:
            target = round(2.0 * self._lag_ema)
            return max(self._cadence_floor, min(self._max_cadence_ticks, target))
        return self._cadence_floor

    def _leak_persist(self) -> int:
        if self._adaptive and self._lag_ema is not None:
            return max(self._leak_persist_floor, round(self._lag_ema))
        return self._leak_persist_floor

    def _reset_dynamics(self) -> None:
        self._ticks_since_move = 0
        self._leak_ticks = 0
        self._lag_watch_active = False
        self._prev_fa_meas = None
