"""Stop the loop toggling on and off around the balance point.

The zero-injection deadband is a single threshold: act when ``|error| > 50 W``,
sit still otherwise. That is not hysteresis — it is memoryless, so an error
hovering *at* the threshold flips the loop between regulating and idle on every
tick. Each flip commands a real change to the batteries, and on hardware that
takes ~30 s to answer (the STREAM over BLE), three more ticks land before the
first one shows up in the meter. The result is the yoyo that keeps turning up in
the logs around equilibrium, where the error is small by definition.

Two thresholds instead of one
-----------------------------
Settle when the error falls inside the base band; resume only when it climbs back
out past a **wider** one. Between the two the loop holds its last command, which
is exactly what a slow actuator needs: time for the previous order to arrive.

How much wider is set by the actuator's own dead time. An actuator that answers
within one tick needs no widening at all and gets none — this degrades exactly to
today's behaviour. One that swallows three ticks has three commands in flight
against an error none of them has corrected yet, and the band widens to keep the
loop from stacking them up. The weighting is a heuristic calibrated on the
observed 30 s STREAM lag, not a derivation, and it is capped so no amount of lag
can blind the loop.

Asymmetric on purpose
---------------------
The widening applies to **import only**. Tolerating an extra 50 W of import for a
few seconds costs a fraction of a centime; tolerating an extra 50 W of *export*
defeats the one thing zero-injection exists to do. So the export side keeps the
base threshold and reacts as promptly as it always did.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass

# How much of each extra in-flight tick is added to the band, as a multiple of the
# base threshold. Calibrated on the 30 s STREAM lag against a 10 s tick: three
# ticks in flight -> a band twice the base.
_LAG_WEIGHT = 0.5
# However slow the actuator, the band never grows past this multiple of the base:
# a wide band is a blind loop, and blindness is worse than a little dither.
_MAX_WIDEN = 3.0


@dataclass(slots=True, frozen=True)
class BalancePointState:
    """Whether the loop is currently sitting settled at the balance point."""

    settled: bool = False


@dataclass(slots=True, frozen=True)
class BalanceBand:
    """The decision for one tick, and the thresholds behind it."""

    settled: bool
    """True when the loop should hold its last command instead of correcting."""

    enter_w: float
    """Error at or below which the loop settles."""

    exit_import_w: float
    """Import-side error that resumes regulation (widened by the actuator lag)."""

    exit_export_w: float
    """Export-side error that resumes regulation (never widened)."""

    new_state: BalancePointState
    reason: str
    """``disabled`` | ``settling`` | ``holding`` | ``resumed`` | ``regulating``"""


def balance_band(
    *,
    enabled: bool,
    error_w: float,
    base_hysteresis_w: float,
    actuator_lag_s: float,
    tick_s: float,
    state: BalancePointState,
) -> BalanceBand:
    """Decide whether the loop should hold still at the balance point.

    Args:
        enabled: Master switch. Off means the caller keeps its existing single
            threshold — this touches control, so it stays opt-in.
        error_w: ``grid_w - setpoint_w``; positive = importing more than wanted,
            negative = exporting more than allowed.
        base_hysteresis_w: The configured deadband, used as the settle threshold.
        actuator_lag_s: How long the hardware takes to answer a setpoint change.
        tick_s: Regulation tick interval.
        state: Carried between ticks — a memoryless band is the bug, not the fix.

    Returns:
        A :class:`BalanceBand`. ``settled`` is safe to act on directly: when it is
        true the caller should emit no correction and leave its integral alone.
    """
    base = max(0.0, base_hysteresis_w)
    if not enabled or base <= 0.0:
        return BalanceBand(
            settled=False,
            enter_w=base,
            exit_import_w=base,
            exit_export_w=base,
            new_state=BalancePointState(False),
            reason="disabled",
        )

    ticks_in_flight = max(1.0, actuator_lag_s / tick_s) if tick_s > 0 else 1.0
    widen = min(_MAX_WIDEN, 1.0 + _LAG_WEIGHT * (ticks_in_flight - 1.0))
    exit_import_w = base * widen
    # Export is what the controller exists to prevent; it never gets the slack.
    exit_export_w = base

    if state.settled:
        threshold = exit_import_w if error_w > 0 else exit_export_w
        if abs(error_w) > threshold:
            return BalanceBand(
                settled=False,
                enter_w=base,
                exit_import_w=exit_import_w,
                exit_export_w=exit_export_w,
                new_state=BalancePointState(False),
                reason="resumed",
            )
        return BalanceBand(
            settled=True,
            enter_w=base,
            exit_import_w=exit_import_w,
            exit_export_w=exit_export_w,
            new_state=BalancePointState(True),
            reason="holding",
        )

    if abs(error_w) <= base:
        return BalanceBand(
            settled=True,
            enter_w=base,
            exit_import_w=exit_import_w,
            exit_export_w=exit_export_w,
            new_state=BalancePointState(True),
            reason="settling",
        )
    return BalanceBand(
        settled=False,
        enter_w=base,
        exit_import_w=exit_import_w,
        exit_export_w=exit_export_w,
        new_state=BalancePointState(False),
        reason="regulating",
    )
