"""Keep storing sunshine when the grid meter is gone.

Losing the grid meter makes zero-injection impossible — there is nothing left to
regulate against. Today that means the whole of active control is suspended, and
on 2026-07-24 that cost 38 minutes of a sunny morning: the PDL entity went
unavailable at 06:58 and nothing was commanded until 07:36.

But being blind on the grid does not mean being blind. The PV production is still
measured at the inverters, and the hour-of-day consumption profile
(:mod:`..consumption_profile`) already knows roughly what the house draws at this
time of day. That is enough to *estimate* a surplus and charge some of it — not
enough to chase zero, but far better than idling under a full sun.

Everything here is built around the fact that the estimate can be wrong:

* **Charge only, never discharge.** Discharging without a meter could push power
  onto the grid and there would be no way to notice.
* **Only a fraction of the estimated surplus** (``safety_factor``). If the profile
  underestimates the house, the shortfall comes off the margin rather than being
  pulled from the grid.
* **Nothing below a floor.** A small estimated surplus is indistinguishable from
  profile error, so it is not acted on at all.
* **Nothing without fresh PV telemetry.** No production reading, no fallback.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass

# Below this the "surplus" is within the noise of an hour-of-day profile and is
# not worth acting on blind.
_MIN_SURPLUS_W = 150.0


@dataclass(slots=True, frozen=True)
class SolarFallbackResult:
    """What to command while the grid meter is unavailable."""

    active: bool
    charge_w: float
    """Charge power to command (W, ≥ 0). Never negative: no blind discharging."""

    estimated_surplus_w: float
    reason: str
    """``disabled`` | ``no_pv_telemetry`` | ``no_surplus`` | ``battery_full`` | ``charging``"""


def solar_only_target_w(
    *,
    enabled: bool,
    pv_available: bool,
    controllable_mppt_w: float,
    predicted_house_w: float | None,
    headroom_kwh: float,
    safety_factor: float = 0.7,
) -> SolarFallbackResult:
    """Decide a blind, conservative charge target from PV minus the expected house load.

    Args:
        enabled: Master switch — off by default, since this commands hardware on an
            estimate rather than a measurement.
        pv_available: Whether the PV telemetry is fresh enough to be trusted.
        controllable_mppt_w: Measured production of the controllable inverters (W).
        predicted_house_w: The learned consumption for this hour (W), or ``None``
            when nothing has been learned yet — in which case we refuse to guess.
        headroom_kwh: Energy the fleet can still absorb; 0 means full.
        safety_factor: Fraction of the estimated surplus actually commanded.

    Returns:
        A :class:`SolarFallbackResult`. ``charge_w`` is 0 whenever anything is unsure.
    """
    if not enabled:
        return SolarFallbackResult(False, 0.0, 0.0, "disabled")
    if not pv_available or predicted_house_w is None:
        # No production reading, or no profile to compare it against: guessing here
        # would command hardware on nothing at all.
        return SolarFallbackResult(False, 0.0, 0.0, "no_pv_telemetry")

    surplus_w = controllable_mppt_w - max(0.0, predicted_house_w)
    if surplus_w < _MIN_SURPLUS_W:
        return SolarFallbackResult(False, 0.0, surplus_w, "no_surplus")
    if headroom_kwh <= 0.0:
        return SolarFallbackResult(False, 0.0, surplus_w, "battery_full")

    charge_w = max(0.0, surplus_w * max(0.0, min(1.0, safety_factor)))
    return SolarFallbackResult(True, charge_w, surplus_w, "charging")
