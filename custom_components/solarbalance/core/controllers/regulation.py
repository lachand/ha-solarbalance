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


def apply_equaliser_offer(target_w: float, offer_w: float) -> float:
    """Force the fleet at least ``offer_w`` toward charging the automatic battery.

    The SoC equaliser offer is applied as a **direct floor** on the fleet target,
    not as a zero-injection setpoint bias: a positive offer (charge the automatic
    battery) forces **at least that much fleet discharge** (``target <= -offer``),
    a negative offer forces at least that much charge. This lets the offer push a
    discharge even while the controllable fleet is charging from its own PV (where
    the net-grid ZI loop alone keeps the target positive).

    It is **absolute** (clamps, does not add to the measured fleet power), so it
    does not integrate/run away; the offer is itself proportional and bounded, and
    the equaliser backs it off if the surplus reaches the grid.
    """
    if offer_w > 0.0:
        return min(target_w, -offer_w)
    if offer_w < 0.0:
        return max(target_w, -offer_w)
    return target_w


def noncontrollable_charge_offset_w(
    charge_w: float, grid_w: float, force_offset_w: float = 0.0
) -> float:
    """Zero-injection setpoint offset that spares the fleet a cloud battery's charge.

    A non-controllable (e.g. cloud) battery may charge on its own; that power flows
    through the grid meter, so the zero-injection loop would discharge the
    controllable fleet to cover it -- a lossy battery-to-battery transfer (worst at
    night with no PV). Raising the ZI setpoint by ``charge_w`` makes the loop
    tolerate that import instead, so the cloud battery draws from the grid.

    ``charge_w`` is the cloud battery's charge power (>= 0). The offer is capped at
    the remaining grid *import* (``grid_w - force_offset_w``, after the
    force-charge feed-forward) so it never makes the fleet charge from the grid
    during a PV surplus (when the grid is exporting, the cap is 0).
    """
    if charge_w <= 0.0:
        return 0.0
    return min(charge_w, max(0.0, grid_w - force_offset_w))


def predictive_steering_w(
    *,
    base_target_w: float,
    planner_w: float,
    is_cheap: bool,
    is_expensive: bool,
) -> float:
    """Bias toward the planner setpoint, but only in the tariff-beneficial direction.

    Returns the bias to add to the fleet target so it moves toward ``planner_w``:

    - in a cheap window, only *more charge* (import to store cheap energy);
    - in an expensive window, only *more discharge* (avoid buying at peak).

    Otherwise 0 — zero-injection keeps full control. With a flat tariff (no cheap
    nor expensive window) this is always 0, so active control is inert until a
    time-of-use tariff is configured. The result is still slew- and
    grid-constraint-limited by the caller.
    """
    if is_cheap and planner_w > base_target_w:
        return planner_w - base_target_w
    if is_expensive and planner_w < base_target_w:
        return planner_w - base_target_w
    return 0.0


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
