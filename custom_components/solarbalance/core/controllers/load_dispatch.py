"""Load dispatch controller.

Allocates available surplus power to pilotable loads in priority order,
respecting time windows, anti-short-cycle guards, and daily runtime caps.

This controller is pure: it does not write to HA entities. Its output is
a `LoadDispatchResult` listing the target state for each load, which the
`DecisionPublisher` translates into HA entity updates.

See SPECIFICATIONS §4.3 and §3.2 (load types).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time

from ..models import Load, LoadControlType, LoadState, LoadStep


@dataclass(slots=True, frozen=True)
class LoadCommand:
    """Command produced for one pilotable load.

    For `on_off` loads: `on` True/False.
    For `stepped` loads: `step_level` is the target level (int).
    For `modulating` loads: `power_w` is the target setpoint.
    """

    load_name: str
    on: bool
    step_level: int | None = None
    power_w: float | None = None
    rationale: str = ""


@dataclass(slots=True, frozen=True)
class LoadDispatchResult:
    """Outcome of one dispatch pass."""

    commands: tuple[LoadCommand, ...]
    allocated_w: float
    unallocated_surplus_w: float


def _time_in_window(t: time, start: time, end: time) -> bool:
    """Return True if `t` is in the window [start, end) (overnight-aware)."""
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def _load_eligible(
    load: Load,
    state: LoadState | None,
    now: datetime,
) -> bool:
    """Return True when the load can be considered for dispatch at `now`."""
    # Time window check
    if load.time_window is not None:
        sh, sm = map(int, load.time_window.start.split(":"))
        eh, em = map(int, load.time_window.end.split(":"))
        if not _time_in_window(now.time(), time(sh, sm), time(eh, em)):
            return False

    if state is None:
        return True

    # Daily runtime cap
    if (
        load.max_daily_runtime_s is not None
        and state.daily_runtime_s >= load.max_daily_runtime_s
    ):
        return False

    # Daily energy cap
    if (
        load.max_daily_energy_kwh is not None
        and state.daily_energy_kwh >= load.max_daily_energy_kwh
    ):
        return False

    # Anti-short-cycle: min_off_duration_s
    if load.min_off_duration_s > 0 and state.actual_power_w == 0.0 and state.last_off_at is not None:
        off_duration = (now - state.last_off_at).total_seconds()
        if off_duration < load.min_off_duration_s:
            return False

    return True


def _current_power(load: Load, state: LoadState | None) -> float:
    """Estimate load's current draw (0 if unknown)."""
    if state is None:
        return 0.0
    return state.actual_power_w


def _best_step_for_surplus(load: Load, surplus_w: float) -> LoadStep | None:
    """Return the highest step whose power_w fits within the available surplus."""
    if not load.steps:
        return None
    eligible = [s for s in load.steps if s.power_w <= surplus_w]
    if not eligible:
        return None
    return max(eligible, key=lambda s: s.power_w)


class LoadDispatchController:
    """Allocate surplus power to loads in priority order.

    The controller is stateless between calls — all history is captured in
    the `LoadState` objects passed via `states`.

    Args:
        loads: All configured pilotable loads (sorted by priority, 1 = highest).
    """

    def __init__(self, loads: Sequence[Load]) -> None:
        self._loads = tuple(sorted(loads, key=lambda load: load.priority))

    def dispatch(
        self,
        *,
        available_surplus_w: float,
        states: Mapping[str, LoadState],
        now: datetime,
    ) -> LoadDispatchResult:
        """Assign surplus to loads and return per-load commands.

        Loads that are currently ON and consuming power keep their slot as long
        as enough surplus remains.  New loads are activated greedily in priority
        order until the surplus is exhausted.

        Args:
            available_surplus_w: Power available for dispatch (positive = surplus).
            states: Current measured state of each load (keyed by load name).
            now: Current datetime (used for time-window and anti-cycle checks).
        """
        commands: list[LoadCommand] = []
        remaining = available_surplus_w

        for load in self._loads:
            state = states.get(load.name)
            currently_on = state is not None and state.actual_power_w > 0.0
            eligible = _load_eligible(load, state, now)

            if load.control_type is LoadControlType.ON_OFF:
                cmd = self._dispatch_on_off(load, state, remaining, currently_on, eligible, now)
            elif load.control_type is LoadControlType.STEPPED:
                cmd = self._dispatch_stepped(load, state, remaining, currently_on, eligible, now)
            else:
                cmd = self._dispatch_modulating(load, state, remaining, currently_on, eligible, now)

            commands.append(cmd)
            if cmd.on:
                allocated = cmd.power_w if cmd.power_w is not None else (
                    _step_power(load, cmd.step_level) or _nominal(load)
                )
                remaining -= allocated
                if remaining < 0:
                    remaining = 0.0

        allocated_w = available_surplus_w - remaining
        return LoadDispatchResult(
            commands=tuple(commands),
            allocated_w=allocated_w,
            unallocated_surplus_w=remaining,
        )

    # ------------------------------------------------------------------ helpers

    def _dispatch_on_off(
        self,
        load: Load,
        state: LoadState | None,
        remaining: float,
        currently_on: bool,
        eligible: bool,
        now: datetime,
    ) -> LoadCommand:
        nominal = load.nominal_power_w or 0
        if currently_on:
            # Keep ON if still eligible and surplus covers it
            if eligible and remaining >= nominal:
                return LoadCommand(load_name=load.name, on=True, rationale="keep_on")
            # Check min_on_duration
            if (
                load.min_on_duration_s > 0
                and state is not None
                and state.last_on_at is not None
            ):
                on_duration = (now - state.last_on_at).total_seconds()
                if on_duration < load.min_on_duration_s:
                    return LoadCommand(
                        load_name=load.name, on=True, rationale="min_on_guard"
                    )
            return LoadCommand(load_name=load.name, on=False, rationale="turn_off")
        # Currently off: activate if eligible and surplus sufficient
        if eligible and remaining >= nominal:
            return LoadCommand(load_name=load.name, on=True, rationale="activate")
        return LoadCommand(load_name=load.name, on=False, rationale="insufficient_surplus")

    def _dispatch_stepped(
        self,
        load: Load,
        state: LoadState | None,
        remaining: float,
        currently_on: bool,
        eligible: bool,
        now: datetime,
    ) -> LoadCommand:
        if not eligible:
            return LoadCommand(load_name=load.name, on=False, step_level=0, rationale="not_eligible")

        current_power = _current_power(load, state)
        best = _best_step_for_surplus(load, remaining + current_power)
        if best is None:
            if currently_on and load.min_on_duration_s > 0 and state and state.last_on_at:
                on_dur = (now - state.last_on_at).total_seconds()
                if on_dur < load.min_on_duration_s:
                    # Keep at current step under guard
                    cur_level = _current_level(load, state)
                    return LoadCommand(
                        load_name=load.name, on=True, step_level=cur_level, rationale="min_on_guard"
                    )
            return LoadCommand(load_name=load.name, on=False, step_level=0, rationale="no_step_fits")

        return LoadCommand(
            load_name=load.name,
            on=True,
            step_level=best.level,
            power_w=float(best.power_w),
            rationale=f"step_{best.level}",
        )

    def _dispatch_modulating(
        self,
        load: Load,
        state: LoadState | None,
        remaining: float,
        currently_on: bool,
        eligible: bool,
        now: datetime,
    ) -> LoadCommand:
        if not eligible:
            return LoadCommand(load_name=load.name, on=False, power_w=0.0, rationale="not_eligible")

        min_w = load.min_power_w or 0
        max_w = load.max_power_w or 0
        current_power = _current_power(load, state)

        available = remaining + current_power
        if available < min_w:
            if currently_on and load.min_on_duration_s > 0 and state and state.last_on_at:
                on_dur = (now - state.last_on_at).total_seconds()
                if on_dur < load.min_on_duration_s:
                    return LoadCommand(
                        load_name=load.name, on=True, power_w=float(min_w), rationale="min_on_guard"
                    )
            return LoadCommand(load_name=load.name, on=False, power_w=0.0, rationale="below_min")

        step = load.step_w if load.step_w > 0 else 1
        target = min(available, float(max_w))
        # Round down to the nearest step
        target = (int(target) // step) * step
        target = max(float(min_w), float(target))

        return LoadCommand(
            load_name=load.name,
            on=True,
            power_w=target,
            rationale=f"modulate_{target:.0f}W",
        )


# ------------------------------------------------------------------ module helpers

def _nominal(load: Load) -> float:
    return float(load.nominal_power_w or 0)


def _step_power(load: Load, level: int | None) -> float | None:
    if level is None:
        return None
    for s in load.steps:
        if s.level == level:
            return float(s.power_w)
    return None


def _current_level(load: Load, state: LoadState | None) -> int:
    """Guess current stepped load level from its measured power."""
    if state is None or not load.steps:
        return 0
    # Match closest step by power
    closest = min(load.steps, key=lambda s: abs(s.power_w - state.actual_power_w))
    return closest.level
