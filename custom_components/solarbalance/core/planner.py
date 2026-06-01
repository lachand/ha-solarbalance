"""Multi-horizon predictive scheduler (V2).

Computes an optimal 24-hour charge/discharge schedule for a battery using
dynamic programming on a discretised State-of-Charge grid.

The planner is pure Python — no HA imports, no IO. It receives:
- A time series of net-load forecasts (load minus PV production), one per slot.
- A time series of import/export prices, one per slot.
- Battery configuration (capacity, SoC bounds, power limits).
- The current SoC as starting state.

It returns the optimal sequence of battery power setpoints (W) that minimises
total electricity cost over the planning horizon.

See SPECIFICATIONS §11 (roadmap v2.0) — Optimisation prédictive multi-horaire.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ForecastSlot:
    """One planning time slot.

    Args:
        start: Wall-clock start of the slot.
        duration_s: Slot duration in seconds (typically 3600 for hourly slots).
        net_load_w: Expected net load for this slot in W (positive = consumption
            exceeds PV, negative = surplus production). Positive values mean the
            home draws from battery/grid; negative means excess that can be stored.
        import_price: Grid import price in €/kWh for this slot.
        export_price: Grid export price in €/kWh for this slot.
    """

    start: datetime
    duration_s: float
    net_load_w: float
    import_price: float
    export_price: float


@dataclass(slots=True, frozen=True)
class BatteryConstraints:
    """Battery physical and operational constraints for the planner.

    Args:
        capacity_kwh: Total usable capacity in kWh.
        max_charge_w: Maximum charge power in W.
        max_discharge_w: Maximum discharge power in W.
        soc_min_pct: Minimum allowed SoC in percent.
        soc_max_pct: Maximum allowed SoC in percent.
        round_trip_efficiency: Round-trip energy efficiency (0 < η ≤ 1).
            Used as the source for charge/discharge efficiencies unless overrides
            are supplied. Default split: charge_efficiency = discharge_efficiency = √η.
        charge_efficiency_override: Direct charge efficiency (0 < η ≤ 1). When set,
            overrides the √(round_trip_efficiency) default. Use when charge and
            discharge losses are not symmetric (e.g. LFP with asymmetric inverter loss).
        discharge_efficiency_override: Direct discharge efficiency (0 < η ≤ 1).
            Same as charge_efficiency_override but for the discharge direction.
    """

    capacity_kwh: float
    max_charge_w: float
    max_discharge_w: float
    soc_min_pct: float = 10.0
    soc_max_pct: float = 95.0
    round_trip_efficiency: float = 0.95
    charge_efficiency_override: float | None = None
    discharge_efficiency_override: float | None = None

    @property
    def charge_efficiency(self) -> float:
        """Charge-direction efficiency.

        Returns charge_efficiency_override when set, else √(round_trip_efficiency).
        """
        if self.charge_efficiency_override is not None:
            return self.charge_efficiency_override
        return math.sqrt(self.round_trip_efficiency)

    @property
    def discharge_efficiency(self) -> float:
        """Discharge-direction efficiency.

        Returns discharge_efficiency_override when set, else √(round_trip_efficiency).
        """
        if self.discharge_efficiency_override is not None:
            return self.discharge_efficiency_override
        return math.sqrt(self.round_trip_efficiency)

    @property
    def soc_min_kwh(self) -> float:
        """Minimum allowed SoC in kWh."""
        return self.capacity_kwh * self.soc_min_pct / 100.0

    @property
    def soc_max_kwh(self) -> float:
        """Maximum allowed SoC in kWh."""
        return self.capacity_kwh * self.soc_max_pct / 100.0


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ScheduleSlot:
    """Optimal setpoint for one planning slot.

    Args:
        start: Wall-clock start of the slot.
        duration_s: Slot duration in seconds.
        battery_power_w: Recommended battery power in W. Positive = charge,
            negative = discharge (internal charge_positive convention).
        expected_grid_w: Expected grid exchange after this setpoint (positive
            = import, negative = export).
        expected_cost_eur: Expected electricity cost for this slot in euros.
            Negative means revenue from export.
        soc_end_pct: Expected battery SoC at the end of this slot (%).
    """

    start: datetime
    duration_s: float
    battery_power_w: float
    expected_grid_w: float
    expected_cost_eur: float
    soc_end_pct: float


@dataclass(slots=True, frozen=True)
class PlanningResult:
    """Full planning result from the predictive scheduler.

    Args:
        schedule: Ordered list of optimal schedule slots, one per input slot.
        total_cost_eur: Total expected cost over the horizon (negative = net revenue).
        horizon_start: Start of the planning horizon.
        horizon_end: End of the planning horizon.
    """

    schedule: tuple[ScheduleSlot, ...]
    total_cost_eur: float
    horizon_start: datetime
    horizon_end: datetime

    @property
    def first_setpoint_w(self) -> float:
        """Convenience accessor: battery power setpoint for the current slot."""
        if not self.schedule:
            return 0.0
        return self.schedule[0].battery_power_w


# ---------------------------------------------------------------------------
# Dynamic programming planner
# ---------------------------------------------------------------------------


class PredictiveScheduler:
    """Battery schedule optimiser using dynamic programming.

    Discretises the battery SoC into `n_soc_steps` levels and finds the
    charge/discharge sequence that minimises total electricity cost over the
    planning horizon.

    The DP state is the battery SoC level (index). For each time slot and each
    SoC state the planner evaluates all feasible battery power levels and
    selects the one leading to minimum cumulative cost.

    Terminal value: stored energy at the end of the horizon is valued at
    ``terminal_value_eur_per_kwh`` (default 0.20 €/kWh, a reasonable average
    import price). This prevents the DP from scheduling aggressive end-of-horizon
    discharge to minimise immediate cost while disregarding the next day's needs.

    Args:
        battery: Battery constraints.
        n_soc_steps: Number of SoC discretisation levels (trade-off between
            accuracy and computation time). Default 50 is fast (< 1 ms for
            24 hourly slots) and accurate enough for hourly scheduling.
        n_power_steps: Number of battery power levels to evaluate per state.
            Higher values give better resolution at the cost of O(n²) growth.
        terminal_value_eur_per_kwh: Value assigned to each kWh of stored energy
            remaining at the end of the planning horizon (€/kWh). Set to 0 to
            disable the terminal value (legacy behaviour, risks end-of-horizon
            depletion).
    """

    def __init__(
        self,
        battery: BatteryConstraints,
        *,
        n_soc_steps: int = 50,
        n_power_steps: int = 20,
        terminal_value_eur_per_kwh: float = 0.20,
    ) -> None:
        self._bat = battery
        self._n = n_soc_steps
        self._m = n_power_steps
        self._terminal_value_eur_per_kwh = terminal_value_eur_per_kwh

        # Pre-compute the SoC grid in kWh
        lo, hi = battery.soc_min_kwh, battery.soc_max_kwh
        self._soc_grid: tuple[float, ...] = tuple(
            lo + i * (hi - lo) / (n_soc_steps - 1) for i in range(n_soc_steps)
        )

    def _nearest_soc_idx(self, soc_kwh: float) -> int:
        """Find the closest SoC grid index for a given SoC (kWh)."""
        lo, hi = self._bat.soc_min_kwh, self._bat.soc_max_kwh
        soc_clamped = max(lo, min(hi, soc_kwh))
        frac = (soc_clamped - lo) / (hi - lo) if hi > lo else 0.0
        return round(frac * (self._n - 1))

    def _soc_to_pct(self, soc_kwh: float) -> float:
        return 100.0 * soc_kwh / self._bat.capacity_kwh

    def plan(
        self,
        slots: tuple[ForecastSlot, ...],
        current_soc_pct: float,
    ) -> PlanningResult:
        """Compute the optimal schedule for the given forecast horizon.

        Args:
            slots: Ordered sequence of forecast slots (typically 24 hourly slots).
            current_soc_pct: Current battery SoC in percent.

        Returns:
            `PlanningResult` with the optimal schedule and total expected cost.
        """
        if not slots:
            return PlanningResult(
                schedule=(),
                total_cost_eur=0.0,
                horizon_start=datetime.now(UTC),
                horizon_end=datetime.now(UTC),
            )

        n_slots = len(slots)
        n_soc = self._n
        bat = self._bat

        # DP tables
        # cost[t][s] = minimum total future cost from slot t with SoC index s
        inf = float("inf")
        cost: list[list[float]] = [[inf] * n_soc for _ in range(n_slots + 1)]
        # choice[t][s] = (soc_next_idx, battery_power_w) chosen at (t, s)
        choice: list[list[tuple[int, float]]] = [[(0, 0.0)] * n_soc for _ in range(n_slots)]

        # Terminal condition: value of stored energy at end of horizon.
        # Stored energy at state s has value terminal_value_eur_per_kwh per kWh,
        # which means it reduces future cost → negative cost (it's a reward).
        for s in range(n_soc):
            cost[n_slots][s] = -self._soc_grid[s] * self._terminal_value_eur_per_kwh

        # Build power candidates once (relative fractions of max power)
        power_fracs = [i / (self._m - 1) for i in range(self._m)]

        # Backward DP
        for t in range(n_slots - 1, -1, -1):
            slot = slots[t]
            dt_h = slot.duration_s / 3600.0

            for s in range(n_soc):
                soc_kwh = self._soc_grid[s]
                best_cost = inf
                best_choice = (s, 0.0)

                for frac in power_fracs:
                    # Try both charge and discharge at this fraction
                    for bat_w in (
                        frac * bat.max_charge_w,
                        -frac * bat.max_discharge_w,
                    ):
                        # Energy stored in battery this slot (kWh), accounting for efficiency.
                        # bat_w is in W; bat_w * dt_h [h] gives Wh; divide by 1000 for kWh.
                        if bat_w >= 0:
                            energy_stored_kwh = bat_w * dt_h * bat.charge_efficiency / 1000.0
                        else:
                            energy_stored_kwh = bat_w * dt_h / bat.discharge_efficiency / 1000.0

                        soc_next_kwh = soc_kwh + energy_stored_kwh
                        if soc_next_kwh < bat.soc_min_kwh - 1e-6:
                            continue
                        if soc_next_kwh > bat.soc_max_kwh + 1e-6:
                            continue

                        # Grid power = net_load + bat_w (positive = import)
                        grid_w = slot.net_load_w + bat_w

                        # Cost this slot
                        if grid_w >= 0:
                            slot_cost = grid_w / 1000.0 * dt_h * slot.import_price
                        else:
                            slot_cost = grid_w / 1000.0 * dt_h * slot.export_price

                        s_next = self._nearest_soc_idx(soc_next_kwh)
                        future = cost[t + 1][s_next]
                        if future == inf:
                            continue

                        total = slot_cost + future
                        if total < best_cost:
                            best_cost = total
                            best_choice = (s_next, bat_w)

                cost[t][s] = best_cost
                choice[t][s] = best_choice

        # Forward pass: reconstruct optimal schedule
        current_soc_kwh = current_soc_pct / 100.0 * bat.capacity_kwh
        s_cur = self._nearest_soc_idx(current_soc_kwh)

        schedule_slots: list[ScheduleSlot] = []
        total_cost = 0.0

        for t in range(n_slots):
            slot = slots[t]
            dt_h = slot.duration_s / 3600.0
            s_next, bat_w = choice[t][s_cur]

            soc_kwh = self._soc_grid[s_cur]
            if bat_w >= 0:
                energy_stored_kwh = bat_w * dt_h * bat.charge_efficiency / 1000.0
            else:
                energy_stored_kwh = bat_w * dt_h / bat.discharge_efficiency / 1000.0
            soc_next_kwh = soc_kwh + energy_stored_kwh

            grid_w = slot.net_load_w + bat_w
            if grid_w >= 0:
                slot_cost = grid_w / 1000.0 * dt_h * slot.import_price
            else:
                slot_cost = grid_w / 1000.0 * dt_h * slot.export_price

            total_cost += slot_cost
            schedule_slots.append(
                ScheduleSlot(
                    start=slot.start,
                    duration_s=slot.duration_s,
                    battery_power_w=bat_w,
                    expected_grid_w=grid_w,
                    expected_cost_eur=slot_cost,
                    soc_end_pct=self._soc_to_pct(soc_next_kwh),
                )
            )
            s_cur = s_next

        return PlanningResult(
            schedule=tuple(schedule_slots),
            total_cost_eur=total_cost,
            horizon_start=slots[0].start,
            horizon_end=slots[-1].start + timedelta(seconds=slots[-1].duration_s),
        )
