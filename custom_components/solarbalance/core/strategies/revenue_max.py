"""Revenue-max strategy.

Maximises revenue from grid export when the export price exceeds the
opportunity cost of stored energy (forward import price), and charges
batteries when the import price is unusually low.

Decision logic (v1.5 -- spread-based heuristic):
- If ``export_price > import_price + export_premium``: discharge batteries
  to sell stored energy. Grid export is authorised up to each battery's
  maximum discharge power.
- If ``import_price < cheap_import_threshold``: charge batteries to buy
  cheap energy for later arbitrage.
- Otherwise: abstain (confidence 0.5, empty targets) -- let higher-priority
  strategies decide.

Requires current_import_price and/or current_export_price on the snapshot.
"""

from collections.abc import Sequence

from ..models import (
    BatteryTarget,
    Decision,
    Device,
    GridConstraint,
    Load,
    Snapshot,
    StrategyKind,
)
from .base import Strategy


class RevenueMaxStrategy(Strategy):
    """Charge on cheap import, discharge on expensive export."""

    kind = StrategyKind.REVENUE_MAX.value

    def __init__(
        self,
        devices: Sequence[Device],
        loads: Sequence[Load],
        *,
        export_premium: float = 0.05,
        cheap_import_threshold: float = 0.10,
        charge_soc_target_pct: float = 90.0,
        discharge_soc_floor_pct: float = 15.0,
    ) -> None:
        """Initialise the strategy.

        Args:
            devices: Configured devices (passed to base Strategy).
            loads: Configured loads (passed to base Strategy).
            export_premium: Minimum spread (EUR/kWh) between export price and
                import price that makes discharging profitable. Defaults to 0.05.
            cheap_import_threshold: Import price (EUR/kWh) at or below which
                buying energy is cheap enough to charge. Defaults to 0.10.
            charge_soc_target_pct: Upper SoC target when charging for arbitrage.
            discharge_soc_floor_pct: Lower SoC floor when discharging to export.
        """
        super().__init__(devices, loads)
        self._export_premium = export_premium
        self._cheap_threshold = cheap_import_threshold
        self._charge_soc_target = charge_soc_target_pct
        self._discharge_soc_floor = discharge_soc_floor_pct

    def compute(self, snapshot: Snapshot) -> Decision:
        """Compute decision based on current spot prices."""
        import_price = snapshot.current_import_price
        export_price = snapshot.current_export_price

        if import_price is None and export_price is None:
            return Decision(
                confidence=0.0,
                rationale="revenue_max: no price data available -- no opinion",
            )

        want_discharge = self._should_discharge(import_price, export_price)
        want_charge = self._should_charge(import_price)

        if not want_discharge and not want_charge:
            return Decision(
                confidence=0.5,
                rationale=(
                    f"revenue_max: spread too small or price neutral "
                    f"(import={import_price}, export={export_price})"
                ),
            )

        targets: dict[str, BatteryTarget] = {}
        for device in self.batteries:
            battery = device.battery
            assert battery is not None
            if want_discharge:
                targets[device.name] = BatteryTarget(
                    soc_min_pct=self._discharge_soc_floor,
                    soc_max_pct=float(battery.soc_max_pct),
                    preferred_power_w=-float(battery.max_discharge_power_w),
                )
            else:
                targets[device.name] = BatteryTarget(
                    soc_min_pct=float(battery.soc_min_pct),
                    soc_max_pct=self._charge_soc_target,
                    preferred_power_w=float(battery.max_charge_power_w),
                )

        if want_discharge:
            import_str = f"{import_price:.4f}" if import_price is not None else "N/A"
            rationale = (
                f"revenue_max: export profitable "
                f"(export={export_price:.4f} > import={import_str}+{self._export_premium})"
            )
            max_export = float(
                sum(
                    d.battery.max_discharge_power_w for d in self.batteries if d.battery is not None
                )
            )
            grid_constraint = GridConstraint(max_export_w=max_export)
        else:
            rationale = (
                f"revenue_max: cheap import (price={import_price:.4f} <= {self._cheap_threshold})"
            )
            grid_constraint = GridConstraint()

        return Decision(
            battery_targets=targets,
            grid_constraint=grid_constraint,
            confidence=1.0,
            rationale=rationale,
        )

    def _should_discharge(self, import_price: float | None, export_price: float | None) -> bool:
        """Return True when exporting is more profitable than keeping energy stored."""
        if export_price is None:
            return False
        if import_price is None:
            return export_price > self._export_premium
        return export_price > import_price + self._export_premium

    def _should_charge(self, import_price: float | None) -> bool:
        """Return True when grid energy is cheap enough to buy for later arbitrage."""
        if import_price is None:
            return False
        return import_price <= self._cheap_threshold
