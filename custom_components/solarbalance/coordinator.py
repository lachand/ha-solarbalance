"""DataUpdateCoordinator for SolarBalance."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adapters.decision_publisher import DecisionPublisher
from .adapters.entity_reader import EntityReader
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
    Device,
    HemsMode,
    Load,
    Meter,
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

    # ------------------------------------------------------------------ HA hook

    async def _async_update_data(self) -> Snapshot | None:
        """Run one tick: read entities → snapshot → arbitrate → publish."""
        if self._mode is HemsMode.PAUSED:
            return None

        try:
            snapshot = self._reader.snapshot()
        except Exception as exc:
            raise UpdateFailed(f"EntityReader failed: {exc}") from exc

        # Storm mode: override battery targets to ramp SoC up
        if snapshot.weather_warning_active and self._mode is HemsMode.NORMAL:
            self.mode = HemsMode.STORM
        elif not snapshot.weather_warning_active and self._mode is HemsMode.STORM:
            self.mode = HemsMode.NORMAL

        # Resolve current tariff prices
        import_price = self._tariff.current_import_price(snapshot.timestamp)
        export_price = self._tariff.current_export_price(snapshot.timestamp)

        # Rebuild snapshot with tariff prices (snapshot is frozen, so replace)
        from dataclasses import replace
        snapshot = replace(
            snapshot,
            current_import_price=import_price,
            current_export_price=export_price,
        )

        # Run strategies
        decisions = [s.compute(snapshot) for s in self._arbiter._strategies]
        result: ArbitrationResult = self._arbiter.arbitrate(decisions)

        # Apply zero-injection correction if enabled
        if self._zi_enabled:
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
                t.preferred_power_w or 0.0
                for t in result.decision.battery_targets.values()
            ),
            states=battery_states,
        )
        load_states = {ls.name: ls for ls in snapshot.loads}
        self._load_dispatch.dispatch(
            available_surplus_w=max(0.0, -snapshot.grid_power_w - balancing_result.allocated_w),
            states=load_states,
            now=snapshot.timestamp,
        )

        self._publisher.publish(result)
        return snapshot

    # ------------------------------------------------------------------ helpers

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
