"""Cost-minimisation strategy.

Charges during low-tariff windows and discharges during high-tariff windows.
Requires a `TariffConfig` with at least two distinct import-price levels.

v1.0 implementation: threshold-based logic on current import price.
- Cheap window (price ≤ cheap_threshold): charge batteries up to `charge_soc_target_pct`.
- Expensive window (price > expensive_threshold): discharge down to `discharge_soc_floor_pct`.
- Neutral window (between thresholds): no opinion, let higher-priority strategies decide.

v2.0+ will add forward-looking optimisation using EPEX/Tempo day-ahead prices.
"""

from ..models import BatteryTarget, Decision, GridConstraint, Snapshot, StrategyKind
from ..tariff import TariffConfig
from .base import Strategy


class CostMinStrategy(Strategy):
    """Charge cheap, discharge expensive — threshold-based v1 heuristic."""

    kind = StrategyKind.COST_MIN.value

    def __init__(
        self,
        *args: object,
        tariff: TariffConfig,
        cheap_threshold: float,
        expensive_threshold: float,
        charge_soc_target_pct: float = 90.0,
        discharge_soc_floor_pct: float = 20.0,
        **kwargs: object,
    ) -> None:
        """Initialise the strategy.

        Args:
            *args: Forwarded to the base ``Strategy`` (devices, etc.).
            tariff: Accepted for API compatibility; prices are read from the snapshot
                (the coordinator injects resolved tariff prices each tick). Not stored.
            cheap_threshold: Import price at or below which we want to charge (€/kWh).
            expensive_threshold: Import price above which we want to discharge (€/kWh).
            charge_soc_target_pct: Upper SoC target when charging for cost reasons.
            discharge_soc_floor_pct: Lower SoC floor when discharging for cost reasons.
            **kwargs: Forwarded to the base ``Strategy``.
        """
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        if cheap_threshold > expensive_threshold:
            raise ValueError(
                "cheap_threshold must be ≤ expensive_threshold "
                f"(got {cheap_threshold} > {expensive_threshold})"
            )
        del tariff  # prices come from snapshot.current_import_price; tariff not needed
        self._cheap_threshold = cheap_threshold
        self._expensive_threshold = expensive_threshold
        self._charge_soc_target = charge_soc_target_pct
        self._discharge_soc_floor = discharge_soc_floor_pct

    def compute(self, snapshot: Snapshot) -> Decision:
        """Compute decision based on current tariff window."""
        price = snapshot.current_import_price
        if price is None:
            return Decision(
                confidence=0.0,
                rationale="cost_min: no import price available — no opinion",
            )

        is_cheap = price <= self._cheap_threshold
        is_expensive = price > self._expensive_threshold

        if not is_cheap and not is_expensive:
            return Decision(
                confidence=0.5,
                rationale=f"cost_min: neutral window (price={price:.4f})",
            )

        targets: dict[str, BatteryTarget] = {}
        for device in self.batteries:
            battery = device.battery
            assert battery is not None
            if is_cheap:
                # Raise the floor to push the battery towards the target SoC.
                # Use preferred_power_w to signal "please charge".
                targets[device.name] = BatteryTarget(
                    soc_min_pct=float(battery.soc_min_pct),
                    soc_max_pct=min(self._charge_soc_target, float(battery.soc_max_pct)),
                    preferred_power_w=float(battery.max_charge_power_w),
                )
            else:
                # Expensive: discharge. Raise the floor ceiling to push discharge.
                targets[device.name] = BatteryTarget(
                    soc_min_pct=max(self._discharge_soc_floor, float(battery.soc_min_pct)),
                    soc_max_pct=float(battery.soc_max_pct),
                    preferred_power_w=-float(battery.max_discharge_power_w),
                )

        # In cheap windows, allow grid import to fill batteries.
        # In expensive windows, allow grid export if surplus after discharge.
        grid = (
            GridConstraint(max_export_w=None)  # no export constraint
            if is_cheap
            else GridConstraint(max_import_w=0.0)  # avoid importing when expensive
        )

        window = "cheap" if is_cheap else "expensive"
        return Decision(
            battery_targets=targets,
            grid_constraint=grid,
            confidence=1.0,
            rationale=f"cost_min: {window} window (price={price:.4f})",
        )
