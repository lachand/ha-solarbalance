"""DataUpdateCoordinator for SolarBalance."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adapters.decision_publisher import DecisionPublisher
from .adapters.entity_reader import EntityReader
from .adapters.watchdog import EntityWatchdog
from .const import (
    CONF_PRIORITIES,
    CONF_TICK_INTERVAL_S,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DEFAULT_BALANCING_ALPHA,
    DEFAULT_TICK_INTERVAL_S,
    DEFAULT_ZERO_INJECTION_HYSTERESIS_W,
    DOMAIN,
)
from .core.arbitrer import Arbiter, ArbitrationResult
from .core.controllers.balancing import BalancingController
from .core.controllers.load_dispatch import LoadDispatchController
from .core.controllers.zero_injection import ZeroInjectionController, ZeroInjectionState
from .core.models import (
    BatteryTarget,
    Decision,
    Device,
    HemsMode,
    Load,
    Meter,
    MeterKind,
    Snapshot,
    StrategyKind,
)
from .core.strategies.backup import BackupStrategy
from .core.strategies.cost_min import CostMinStrategy
from .core.strategies.longevity import LongevityStrategy
from .core.strategies.peak_shaving import PeakShavingStrategy
from .core.strategies.revenue_max import RevenueMaxStrategy
from .core.strategies.self_consumption import SelfConsumptionStrategy
from .core.tariff import TariffConfig

_LOGGER = logging.getLogger(__name__)

_STRATEGY_CLASSES = {
    StrategyKind.SELF_CONSUMPTION.value: SelfConsumptionStrategy,
    StrategyKind.COST_MIN.value: CostMinStrategy,
    StrategyKind.BACKUP.value: BackupStrategy,
    StrategyKind.LONGEVITY.value: LongevityStrategy,
    StrategyKind.PEAK_SHAVING.value: PeakShavingStrategy,
    StrategyKind.REVENUE_MAX.value: RevenueMaxStrategy,
}


@dataclass
class _BatteryOverride:
    """Parameters for a force_charge or force_discharge service call."""

    kind: str  # "charge" | "discharge"
    target_soc_pct: float
    power_w: float | None = None
    expires_at: datetime | None = None


class SolarBalanceCoordinator(DataUpdateCoordinator[Snapshot | None]):
    """Polls HA entities, runs the core engine, publishes results."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        devices: list[Device],
        meters: list[Meter],
        loads: list[Load],
        tariff: TariffConfig | None = None,
    ) -> None:
        cfg = dict(entry.options or entry.data)
        tick = int(cfg.get(CONF_TICK_INTERVAL_S, DEFAULT_TICK_INTERVAL_S))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=tick),
        )
        self._entry = entry
        self._devices = devices
        self._meters = meters
        self._loads = loads
        self._tariff = tariff or TariffConfig()
        self._mode: HemsMode = HemsMode.NORMAL
        self._pre_degraded_mode: HemsMode = HemsMode.NORMAL
        self._battery_override: _BatteryOverride | None = None
        self._zi_state = ZeroInjectionState()

        self._reader = EntityReader(
            hass,
            devices,
            meters,
            loads,
            pv_forecast_entity=cfg.get("pv_forecast_entity") or None,
            weather_warning_entity=cfg.get("weather_warning_entity") or None,
        )
        self._publisher = DecisionPublisher()
        self._balancing = BalancingController(devices, alpha=DEFAULT_BALANCING_ALPHA)
        self._load_dispatch = LoadDispatchController(loads)

        zi_enabled = bool(cfg.get(CONF_ZERO_INJECTION_ENABLED, True))
        self._zi_enabled = zi_enabled
        self._zi_controller = ZeroInjectionController(
            hysteresis_w=float(
                cfg.get(CONF_ZERO_INJECTION_HYSTERESIS_W, DEFAULT_ZERO_INJECTION_HYSTERESIS_W)
            ),
        )
        self._zi_setpoint_w = float(cfg.get(CONF_ZERO_INJECTION_SETPOINT_W, 0))
        self._tick_s = tick

        # Watchdog — entity lists built from config
        self._critical_entity_ids, self._monitored_entity_ids = self._collect_entity_ids(
            devices, meters
        )
        self._watchdog = EntityWatchdog(hass)

        # Build ordered strategy list from config
        priorities: list[str] = cfg.get(CONF_PRIORITIES, list(_STRATEGY_CLASSES))
        self._arbiter = self._build_arbiter(priorities, devices, loads, tariff)

    # ------------------------------------------------------------------ public

    @property
    def mode(self) -> HemsMode:
        return self._mode

    @mode.setter
    def mode(self, value: HemsMode) -> None:
        if self._mode != value:
            _LOGGER.info("SolarBalance mode: %s → %s", self._mode.value, value.value)
            self._mode = value

    @property
    def publisher(self) -> DecisionPublisher:
        return self._publisher

    @property
    def is_degraded(self) -> bool:
        """True when the HEMS is in degraded mode."""
        return self._mode is HemsMode.DEGRADED

    @property
    def daily_pv_energy_kwh(self) -> float | None:
        """Sum of today's PV energy across all MPPT devices with daily_energy_entity.

        Returns None when no device declares daily_energy_entity.
        Source entities are expected to be in kWh (standard HA energy unit).
        """
        total = 0.0
        found = False
        for device in self._devices:
            if device.mppt and device.mppt.daily_energy_entity:
                state = self.hass.states.get(device.mppt.daily_energy_entity)
                if state and state.state not in {"unavailable", "unknown", ""}:
                    try:
                        total += float(state.state)
                        found = True
                    except (ValueError, TypeError):
                        pass
        return round(total, 3) if found else None

    @property
    def daily_grid_import_kwh(self) -> float | None:
        """Grid energy imported today from the PDL meter daily_import_energy_entity.

        Returns None when the PDL meter does not declare daily_import_energy_entity.
        Source entity is expected to be in kWh.
        """
        for meter in self._meters:
            if meter.kind is MeterKind.PDL and meter.daily_import_energy_entity:
                state = self.hass.states.get(meter.daily_import_energy_entity)
                if state and state.state not in {"unavailable", "unknown", ""}:
                    try:
                        return round(float(state.state), 3)
                    except (ValueError, TypeError):
                        pass
        return None

    def set_force_override(
        self,
        kind: str,
        target_soc_pct: float,
        power_w: float | None = None,
        deadline: datetime | None = None,
    ) -> None:
        """Start a force_charge or force_discharge override."""
        self._battery_override = _BatteryOverride(
            kind=kind,
            target_soc_pct=target_soc_pct,
            power_w=power_w,
            expires_at=deadline,
        )
        self.mode = HemsMode.MANUAL_OVERRIDE

    def clear_force_override(self) -> None:
        """Cancel any active force override and return to normal mode."""
        self._battery_override = None
        if self._mode is HemsMode.MANUAL_OVERRIDE:
            self.mode = HemsMode.NORMAL

    # ------------------------------------------------------------------ HA hook

    async def _async_update_data(self) -> Snapshot | None:
        """Run one tick: read entities → watchdog → snapshot → arbitrate → publish."""
        if self._mode is HemsMode.PAUSED:
            return None

        try:
            snapshot = self._reader.snapshot()
        except Exception as exc:
            raise UpdateFailed(f"EntityReader failed: {exc}") from exc

        # --- Watchdog: detect stale critical entities ---
        wd = self._watchdog.check(self._critical_entity_ids, self._monitored_entity_ids)
        if wd.is_degraded:
            if self._mode is not HemsMode.DEGRADED:
                _LOGGER.warning(
                    "Switching to DEGRADED — stale critical entities: %s",
                    wd.critical_stale,
                )
                self._pre_degraded_mode = self._mode
                self.mode = HemsMode.DEGRADED
        elif self._mode is HemsMode.DEGRADED:
            _LOGGER.info(
                "Critical entities recovered — restoring %s mode",
                self._pre_degraded_mode.value,
            )
            self.mode = self._pre_degraded_mode
            self._pre_degraded_mode = HemsMode.NORMAL

        # --- Storm mode auto-trigger (only when in normal operation) ---
        if self._mode is HemsMode.NORMAL:
            if snapshot.weather_warning_active:
                self.mode = HemsMode.STORM
        elif self._mode is HemsMode.STORM and not snapshot.weather_warning_active:
            self.mode = HemsMode.NORMAL

        # Resolve current tariff prices
        import_price = self._tariff.current_import_price(snapshot.timestamp)
        export_price = self._tariff.current_export_price(snapshot.timestamp)

        from dataclasses import replace

        snapshot = replace(
            snapshot,
            current_import_price=import_price,
            current_export_price=export_price,
        )

        # --- Strategy execution or manual override ---
        if self._mode is HemsMode.MANUAL_OVERRIDE and self._battery_override is not None:
            result: ArbitrationResult = self._build_override_result(snapshot)
        else:
            decisions = [s.compute(snapshot) for s in self._arbiter._strategies]
            result = self._arbiter.arbitrate(decisions)

        # Apply zero-injection correction if enabled and not degraded
        if self._zi_enabled and self._mode is not HemsMode.DEGRADED:
            zi_result = self._zi_controller.step(
                grid_power_w=snapshot.grid_power_w,
                setpoint_w=self._zi_setpoint_w,
                dt_s=float(self._tick_s),
                state=self._zi_state,
            )
            self._zi_state = zi_result.new_state
            if not zi_result.in_deadband:
                _LOGGER.debug(
                    "ZI correction %.0fW (grid=%.0fW, setpoint=%.0fW)",
                    zi_result.correction_w,
                    snapshot.grid_power_w,
                    self._zi_setpoint_w,
                )

        # Dispatch loads using the unallocated surplus
        battery_states = {b.device_name: b for b in snapshot.batteries}
        balancing_result = self._balancing.allocate(
            total_power_w=sum(
                t.preferred_power_w or 0.0 for t in result.decision.battery_targets.values()
            ),
            states=battery_states,
        )
        load_states = {ls.name: ls for ls in snapshot.loads}
        self._load_dispatch.dispatch(
            available_surplus_w=max(
                0.0, -snapshot.grid_power_w - sum(balancing_result.per_battery_w.values())
            ),
            states=load_states,
            now=snapshot.timestamp,
        )

        self._publisher.publish(result)
        return snapshot

    # ------------------------------------------------------------------ helpers

    def _build_override_result(self, snapshot: Snapshot) -> ArbitrationResult:
        """Build an ArbitrationResult directly from the active battery override."""
        ovr = self._battery_override
        assert ovr is not None

        # Expiry check
        if ovr.expires_at is not None and snapshot.timestamp >= ovr.expires_at:
            _LOGGER.info("Force %s override expired — returning to normal", ovr.kind)
            self.clear_force_override()
            decisions = [s.compute(snapshot) for s in self._arbiter._strategies]
            return self._arbiter.arbitrate(decisions)

        # Target-reached check
        available = [b for b in snapshot.batteries if b.available]
        if available:
            if ovr.kind == "charge":
                reached = all(b.soc_pct >= ovr.target_soc_pct for b in available)
            else:
                reached = all(b.soc_pct <= ovr.target_soc_pct for b in available)
            if reached:
                _LOGGER.info(
                    "Force %s target %.0f%% reached — resuming normal", ovr.kind, ovr.target_soc_pct
                )
                self.clear_force_override()
                decisions = [s.compute(snapshot) for s in self._arbiter._strategies]
                return self._arbiter.arbitrate(decisions)

        # Build per-device battery targets
        targets: dict[str, BatteryTarget] = {}
        for device in self._devices:
            if device.battery is None:
                continue
            bat = device.battery
            if ovr.kind == "charge":
                targets[device.name] = BatteryTarget(
                    soc_min_pct=float(bat.soc_min_pct),
                    soc_max_pct=ovr.target_soc_pct,
                    preferred_power_w=float(ovr.power_w if ovr.power_w else bat.max_charge_power_w),
                )
            else:
                targets[device.name] = BatteryTarget(
                    soc_min_pct=ovr.target_soc_pct,
                    soc_max_pct=float(bat.soc_max_pct),
                    preferred_power_w=-float(
                        ovr.power_w if ovr.power_w else bat.max_discharge_power_w
                    ),
                )

        override_decision = Decision(
            battery_targets=targets,
            confidence=1.0,
            rationale=f"force_{ovr.kind} → {ovr.target_soc_pct:.0f}%",
        )
        return ArbitrationResult(
            decision=override_decision,
            dominant_strategy="manual_override",
            per_strategy=(),
        )

    @staticmethod
    def _collect_entity_ids(
        devices: list[Device], meters: list[Meter]
    ) -> tuple[list[str], list[str]]:
        """Return (critical_ids, monitored_ids) derived from config.

        Critical: PDL meter power entity — its staleness triggers DEGRADED.
        Monitored: battery SoC/power entities and MPPT power entities.
        """
        critical: list[str] = []
        monitored: list[str] = []
        for m in meters:
            if m.kind is MeterKind.PDL:
                critical.append(m.power_entity)
            else:
                monitored.append(m.power_entity)
        for d in devices:
            if d.battery:
                monitored.append(d.battery.soc_entity)
                if d.battery.power_entity:
                    monitored.append(d.battery.power_entity)
            if d.mppt:
                monitored.append(d.mppt.power_entity)
        return critical, monitored

    @staticmethod
    def _build_arbiter(
        priorities: list[str],
        devices: list[Device],
        loads: list[Load],
        tariff: TariffConfig | None,
    ) -> Arbiter:
        strategies = []
        for kind in priorities:
            cls = _STRATEGY_CLASSES.get(kind)
            if cls is None:
                _LOGGER.warning("Unknown strategy kind %r — skipping", kind)
                continue
            if kind == StrategyKind.COST_MIN.value:
                strat = cls(
                    devices,
                    loads,
                    tariff=tariff or TariffConfig(),
                    cheap_threshold=0.15,
                    expensive_threshold=0.25,
                )
            elif kind == StrategyKind.BACKUP.value:
                strat = cls(devices, loads, reserve_soc_pct=30.0)
            elif kind == StrategyKind.PEAK_SHAVING.value:
                strat = cls(devices, loads, max_import_w=None)
            else:
                strat = cls(devices, loads)
            strategies.append(strat)

        if not strategies:
            strategies.append(SelfConsumptionStrategy(devices, loads))
        return Arbiter(strategies)
