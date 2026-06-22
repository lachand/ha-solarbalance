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

from dataclasses import dataclass


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


def clamp_discharge_no_export(target_w: float, current_fleet_w: float, grid_w: float) -> float:
    """Cap a discharge so the controllable fleet never pushes the grid into export.

    There is no reason to discharge a battery while already injecting into the
    grid. Under zero-injection the PI loop targets grid = 0, but because it tracks
    ``current_fleet + correction`` and the hardware ramps slowly, a large
    over-discharge can take minutes to wind down -- dumping stored energy to the
    grid the whole time. This enforces the same goal in a single tick by direct
    projection: ``projected_grid = grid + (target - current_fleet) >= 0`` gives
    ``target >= current_fleet - grid``.

    Only ever *reduces a discharge* (``target_w < 0``); the floor is capped at 0 so
    it never forces a charge, leaving a genuine PV surplus free to export. When the
    grid is importing it does nothing (the discharge is legitimately covering load).
    """
    if target_w >= 0.0:
        return target_w
    return max(target_w, min(0.0, current_fleet_w - grid_w))


def noncontrollable_charge_offset_w(
    charge_w: float, natural_grid_w: float, force_offset_w: float = 0.0
) -> float:
    """Zero-injection setpoint offset that spares the fleet a cloud battery's charge.

    A non-controllable (e.g. cloud) battery may charge on its own; that power flows
    through the grid meter, so the zero-injection loop would discharge the
    controllable fleet to cover it -- a lossy battery-to-battery transfer (worst at
    night with no PV). Raising the ZI setpoint by ``charge_w`` makes the loop
    tolerate that import instead, so the cloud battery draws from the grid.

    ``charge_w`` is the cloud battery's charge power (>= 0). ``natural_grid_w`` is
    the grid power *without* the controllable fleet's contribution
    (``grid_filtered - current_fleet``): the raw grid cannot be used because once
    the fleet already discharges to cover the cloud charge, the raw grid reads ~0
    and the offset would collapse to 0 (the loop would keep draining the fleet).
    The offset is capped at that natural import (after the force-charge
    feed-forward) so it never makes the fleet charge from the grid during a PV
    surplus (when the natural grid is exporting, the cap is 0).
    """
    if charge_w <= 0.0:
        return 0.0
    return min(charge_w, max(0.0, natural_grid_w - force_offset_w))


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


@dataclass(frozen=True, slots=True)
class RegulationInputs:
    """All inputs to the aggregate-target clamp pipeline (see resolve_total_power)."""

    zi_regulating: bool
    current_fleet_w: float
    zi_correction_w: float
    absolute_target_w: float
    steering_w: float
    eq_bias_w: float
    grid_filtered_w: float
    controllable_mppt_w: float
    nc_charge_offset_w: float
    noncontrollable_charging: bool
    noncontrollable_charge_w: float
    zi_hysteresis_w: float
    no_battery_export: bool
    stop_cloud_charge: bool
    max_import_w: float | None
    max_export_w: float | None


@dataclass(frozen=True, slots=True)
class RegulationResult:
    """Outcome of the clamp pipeline + which step set the final value (observability).

    ``binding`` names the last clamp that moved the target -- the one that decides
    the command this tick (``base`` when nothing clamped). Exposed as a diagnostic
    so a surprising target is self-explanatory ("no_feed is capping the discharge")
    instead of guessed from graphs.
    """

    total_w: float
    binding: str
    base_w: float
    natural_grid_w: float


def resolve_total_power(inp: RegulationInputs) -> RegulationResult:
    """Aggregate fleet target after the full clamp pipeline (positive = charge).

    Single pure place for the sequence the coordinator used to inline: base target
    → equaliser offer → no-export → no-charge floor → no-feed / stop-cloud → grid
    constraints. Mode caps (vacation) and the slew limit stay in the caller.
    Behaviour-preserving extraction — see tests/integration/
    test_regulation_combinations.py and tests/core/controllers/test_regulation.py.
    """
    base_w = resolve_fleet_target_w(
        zi_regulating=inp.zi_regulating,
        current_fleet_w=inp.current_fleet_w,
        zi_correction_w=inp.zi_correction_w,
        absolute_target_w=inp.absolute_target_w,
        steering_w=inp.steering_w,
    )
    natural_grid_w = inp.grid_filtered_w - inp.current_fleet_w
    total_w = base_w
    binding = "base"

    def pin(value: float, name: str) -> None:
        nonlocal total_w, binding
        if abs(value - total_w) > 1e-6:
            total_w = value
            binding = name

    if inp.zi_regulating:
        # SoC-equaliser offer as a direct floor/ceiling on the fleet target.
        pin(apply_equaliser_offer(total_w, inp.eq_bias_w), "equaliser")
        # Strict self-consumption: never discharge the fleet into the grid.
        if inp.no_battery_export:
            pin(
                clamp_discharge_no_export(total_w, inp.current_fleet_w, inp.grid_filtered_w),
                "no_export",
            )
        # No-charge floor: in surplus (and no cloud battery absorbing it, no
        # equaliser charge intent), don't charge from the grid / a discharging
        # cloud battery — floor the output at the fleet's own solar.
        if (
            inp.grid_filtered_w >= -inp.zi_hysteresis_w
            and inp.eq_bias_w >= 0.0
            and not inp.noncontrollable_charging
        ):
            pin(min(total_w, -inp.controllable_mppt_w), "no_charge_floor")
        # No-feed: don't discharge the fleet to feed a self-charging cloud battery
        # (it draws from the grid instead). stop_cloud_charge additionally cuts the
        # discharge to 0 to starve it — but only in a surplus context, never while a
        # real load is importing (else it dumps the load on the grid and yoyos).
        if inp.nc_charge_offset_w > 0.0:
            pin(
                max(total_w, inp.nc_charge_offset_w - inp.grid_filtered_w + inp.current_fleet_w),
                "no_feed",
            )
            real_load_w = natural_grid_w - inp.noncontrollable_charge_w
            if inp.stop_cloud_charge and real_load_w <= inp.zi_hysteresis_w:
                pin(max(total_w, 0.0), "stop_cloud")
    # Grid constraints (honour the breaker/contract regardless of the regulator).
    if inp.max_import_w is not None:
        pin(
            min(total_w, inp.max_import_w - inp.grid_filtered_w + inp.current_fleet_w),
            "grid_import",
        )
    if inp.max_export_w is not None:
        pin(
            max(total_w, -inp.max_export_w - inp.grid_filtered_w + inp.current_fleet_w),
            "grid_export",
        )
    return RegulationResult(
        total_w=total_w, binding=binding, base_w=base_w, natural_grid_w=natural_grid_w
    )


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
