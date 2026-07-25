"""Set the loop's proportional gain from how slowly the hardware answers.

The zero-injection gain ``Kp`` decides how hard the loop reacts to a grid error.
Its safe value is not a constant: it depends on the dead time between commanding a
setpoint and seeing it in the meter. A gain that is calm on an inverter answering
within a tick becomes a gain that overshoots and rings on an EcoFlow STREAM that
takes ~30 s over BLE — the loop keeps pushing because the last three commands have
not landed yet, then slams back when they all arrive at once.

The classical result behind this is that a proportional loop's safe gain scales
roughly with the ratio of the control period to the dead time. Turned around: the
more ticks of lag the actuator hides, the lower the gain has to be to stay stable.
This module applies exactly that, as a bounded derating of the configured gain:

    ticks_in_flight = lag / tick
    kp = base_kp / ticks_in_flight        (clamped to a sane floor)

An actuator that answers within one tick has ``ticks_in_flight = 1`` and keeps the
full configured gain — so this degrades to today's behaviour, and there is nothing
to regret leaving it off. It only ever *lowers* the gain, never raises it above
what the user configured, and never below a floor where the loop would stop
correcting at all.

This is the base gain. The supervisory auto-tuner still damps from here when it
sees oscillation; D1 gives it a better starting point so it has less to undo.

Pure module — no Home Assistant imports.
"""

# Never derate below this fraction of the configured gain: past here the loop is
# so slow it barely regulates, which is its own failure. A very laggy actuator is
# better served by the settle/hysteresis machinery than by a near-zero gain.
_MIN_DERATE = 0.25


def tuned_kp(*, base_kp: float, actuator_lag_s: float, tick_s: float) -> float:
    """Derate the proportional gain for the actuator's dead time.

    Args:
        base_kp: The configured proportional gain (the ceiling; never exceeded).
        actuator_lag_s: How long the hardware takes to act on a new setpoint.
        tick_s: Regulation tick interval.

    Returns:
        A gain in ``[base_kp * _MIN_DERATE, base_kp]``. Equal to ``base_kp`` when
        the actuator answers within one tick or the inputs are unusable.
    """
    if base_kp <= 0.0 or tick_s <= 0.0 or actuator_lag_s <= 0.0:
        return base_kp
    ticks_in_flight = max(1.0, actuator_lag_s / tick_s)
    derate = max(_MIN_DERATE, 1.0 / ticks_in_flight)
    return base_kp * derate
