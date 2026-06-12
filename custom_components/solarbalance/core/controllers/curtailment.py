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

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CurtailmentResult:
    """Outcome of one curtailment tick."""

    limit_total_w: float
    curtailing: bool


class CurtailmentController:
    """Sticky aggregate PV output limit, ramped to avoid oscillation."""

    def __init__(
        self, *, peak_total_w: float, deadband_w: float = 50.0, ramp_w: float = 200.0
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
        self._limit_w = peak_total_w  # start unrestricted

    @property
    def limit_w(self) -> float:
        """Current commanded aggregate output limit (W)."""
        return self._limit_w

    def reset_to_unlimited(self) -> None:
        """Release any curtailment (e.g. when suspended/degraded)."""
        self._limit_w = self._peak_total_w

    def step(
        self,
        *,
        pv_total_w: float,
        grid_w: float,
        setpoint_w: float,
        batteries_saturated: bool,
    ) -> CurtailmentResult:
        """Update the output limit for one tick.

        Args:
            pv_total_w: Current aggregate output of the curtailable inverters (W).
            grid_w: Grid power (positive = import).
            setpoint_w: Grid setpoint (target). Export = grid below setpoint.
            batteries_saturated: True when the batteries could not absorb the
                charge demand this tick (full) — curtailment may engage.
        """
        export_excess_w = setpoint_w - grid_w  # > 0 → exporting more than allowed
        if batteries_saturated and export_excess_w > self._deadband_w:
            # Remove the un-absorbable surplus from PV output (only tighten).
            self._limit_w = min(self._limit_w, max(0.0, pv_total_w - export_excess_w))
        elif self._limit_w < self._peak_total_w and (
            not batteries_saturated or grid_w > setpoint_w + self._deadband_w
        ):
            # Headroom returned (batteries free, or importing) → relax toward peak.
            self._limit_w = min(self._peak_total_w, self._limit_w + self._ramp_w)

        self._limit_w = max(0.0, min(self._peak_total_w, self._limit_w))
        return CurtailmentResult(
            limit_total_w=self._limit_w,
            curtailing=self._limit_w < self._peak_total_w - 1e-6,
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
