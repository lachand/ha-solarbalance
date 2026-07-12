"""PV curtailment controller — zero-injection's last resort.

When the controllable batteries are saturated (full, cannot absorb more) and PV
surplus would otherwise be injected to the grid, the HEMS caps the controllable
micro-inverters' output so production tracks consumption. Curtailment is the
**last** actuator of zero-injection, after the batteries (which store the surplus
losslessly when they can).

The commanded output limit is **sticky** to avoid hunting: it is only lowered
while batteries are saturated and the grid exports past its setpoint, and only
raised again when the batteries can absorb again or the grid imports (so more PV
can be used). At balance it holds.

Anti-yoyo: moves are **gradual** (at most ``ramp_w`` per move, both directions) so
the limit converges on the balance instead of slamming between 0 and peak, and a
**settle window** (``settle_ticks``) holds the limit for a few ticks after each
move so the inverter's dead-time and the meter can catch up — writing a new limit
every tick out-runs the measurement and produces a 0↔peak sawtooth.

That stickiness is also a latency: the reactive branch cannot move before an export
has been *measured*. :mod:`.anticipation` closes that gap by supplying an optional
``preemptive_limit_w`` — a forecast-derived ceiling the limit is ramped toward
without waiting for the export it exists to prevent.

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CurtailmentResult:
    """Outcome of one curtailment tick."""

    limit_total_w: float
    curtailing: bool
    preemptive: bool = False


class CurtailmentController:
    """Sticky aggregate PV output limit, ramped to avoid oscillation."""

    def __init__(
        self,
        *,
        peak_total_w: float,
        deadband_w: float = 50.0,
        ramp_w: float = 150.0,
        settle_ticks: int = 3,
    ) -> None:
        if peak_total_w < 0:
            raise ValueError("peak_total_w must be non-negative")
        if deadband_w < 0:
            raise ValueError("deadband_w must be non-negative")
        if ramp_w <= 0:
            raise ValueError("ramp_w must be strictly positive")
        self._peak_total_w = peak_total_w
        self._deadband_w = deadband_w
        self._ramp_w = ramp_w
        self._settle_ticks = max(1, int(settle_ticks))
        self._limit_w = peak_total_w  # start unrestricted
        self._since_move = self._settle_ticks  # allow an immediate first move

    @property
    def limit_w(self) -> float:
        """Current commanded aggregate output limit (W)."""
        return self._limit_w

    def reset_to_unlimited(self) -> None:
        """Release any curtailment (e.g. when suspended/degraded)."""
        self._limit_w = self._peak_total_w
        self._since_move = self._settle_ticks

    def step(
        self,
        *,
        pv_total_w: float,
        grid_w: float,
        setpoint_w: float,
        batteries_saturated: bool,
        preemptive_limit_w: float | None = None,
    ) -> CurtailmentResult:
        """Update the output limit for one tick.

        Args:
            pv_total_w: Current aggregate output of the curtailable inverters (W).
            grid_w: Grid power (positive = import).
            setpoint_w: Grid setpoint (target). Export = grid below setpoint.
            batteries_saturated: True when the batteries could not absorb the
                charge demand this tick (full) — curtailment may engage.
            preemptive_limit_w: Forecast-derived ceiling (W) from the anticipation
                controller, or ``None`` for purely reactive behaviour. Unlike the
                reactive branch it does **not** wait for a measured export — that is
                the point: it caps the inverter *before* the surplus lands. It only
                ever lowers the limit, so it composes with the reactive trim as a
                ``min`` and can never force PV up.
        """
        export_excess_w = setpoint_w - grid_w  # > 0 → exporting more than allowed
        # Settle window: hold the limit for a few ticks after each move so the
        # inverter + meter catch up (writing every tick out-runs the dead-time and
        # yoyos between 0 and peak).
        self._since_move += 1
        if self._since_move < self._settle_ticks:
            return self._result(preemptive_limit_w)

        # While a ceiling is in force the relax branch may not climb above it, else
        # the ramp would undo the brake between two reactive moves.
        relax_ceiling_w = self._peak_total_w
        if preemptive_limit_w is not None:
            relax_ceiling_w = min(relax_ceiling_w, max(0.0, preemptive_limit_w))

        moved = False
        if batteries_saturated and export_excess_w > self._deadband_w:
            # Trim the un-absorbable surplus gradually (at most ramp_w per move) so
            # the limit converges on the balance instead of slamming to zero.
            new_limit = max(0.0, self._limit_w - min(export_excess_w, self._ramp_w))
            if new_limit < self._limit_w - 1e-6:
                self._limit_w = new_limit
                moved = True
        elif self._limit_w < relax_ceiling_w and (
            not batteries_saturated or -export_excess_w > self._deadband_w
        ):
            # Headroom returned (batteries free, or importing past the deadband) →
            # relax gently toward peak (or toward the anticipatory ceiling).
            self._limit_w = min(relax_ceiling_w, self._limit_w + self._ramp_w)
            moved = True

        if not moved and preemptive_limit_w is not None:
            # No reactive move: bring the limit down toward the forecast ceiling.
            # Ramped like everything else so the descent stays anti-yoyo.
            target_w = max(0.0, preemptive_limit_w)
            if target_w < self._limit_w - self._deadband_w:
                self._limit_w = max(target_w, self._limit_w - self._ramp_w)
                moved = True

        if moved:
            self._since_move = 0
        self._limit_w = max(0.0, min(self._peak_total_w, self._limit_w))
        return self._result(preemptive_limit_w)

    def _result(self, preemptive_limit_w: float | None) -> CurtailmentResult:
        return CurtailmentResult(
            limit_total_w=self._limit_w,
            curtailing=self._limit_w < self._peak_total_w - 1e-6,
            preemptive=preemptive_limit_w is not None,
        )


def distribute_pv_limit(
    limit_total_w: float,
    peak_by_device: Sequence[tuple[str, float]],
) -> Mapping[str, float]:
    """Split an aggregate output limit across inverters, proportional to peak."""
    peak_total = sum(p for _, p in peak_by_device)
    if peak_total <= 0:
        return {name: 0.0 for name, _ in peak_by_device}
    return {name: limit_total_w * peak / peak_total for name, peak in peak_by_device}
