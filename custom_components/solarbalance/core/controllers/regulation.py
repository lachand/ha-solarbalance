"""Aggregate fleet-power target resolution and slew limiting.

These helpers decide the single aggregate charge/discharge target (W, positive =
charge) handed to the BalancingController, and bound how fast it may change.

Background: zero-injection is a PI controller that returns a *delta* on the
current aggregate battery power (see ``zero_injection``). Earlier the coordinator
summed that delta with ``self_consumption``'s *absolute* ``-net_grid`` target —
two corrections of the same grid error, an effective proportional gain > 1 with a
one-tick actuation lag → a limit cycle at the tick frequency. The fix is to pick a
single regulator: when zero-injection is active it owns regulation (target =
current fleet power + correction); otherwise the strategies' absolute target is
used. A slew-rate limit then caps the per-tick change as a hard safety belt.

Pure module — no Home Assistant imports.
"""


def resolve_fleet_target_w(
    *,
    zi_regulating: bool,
    current_fleet_w: float,
    zi_correction_w: float,
    absolute_target_w: float,
    steering_w: float,
) -> float:
    """Return the aggregate fleet power target (W, positive = charge).

    Args:
        zi_regulating: True when zero-injection owns grid regulation this tick.
        current_fleet_w: Current aggregate power of the controllable fleet
            (positive = charging), the base the PI delta is applied to.
        zi_correction_w: Zero-injection PI delta to add to the current power.
        absolute_target_w: Strategies' absolute target, used when zero-injection
            is not regulating (e.g. storm, override, or ZI disabled).
        steering_w: Indirect SoC-equaliser bias (0 when inactive).
    """
    base = current_fleet_w + zi_correction_w if zi_regulating else absolute_target_w
    return base + steering_w


def apply_slew_limit(
    target_w: float,
    last_target_w: float | None,
    max_ramp_w: float,
) -> float:
    """Clamp ``target_w`` to within ``max_ramp_w`` of the previous command.

    Returns ``target_w`` unchanged when the limit is disabled (``max_ramp_w <=
    0``) or there is no previous command yet (``last_target_w is None``).
    """
    if max_ramp_w <= 0 or last_target_w is None:
        return target_w
    lo = last_target_w - max_ramp_w
    hi = last_target_w + max_ramp_w
    return max(lo, min(hi, target_w))
