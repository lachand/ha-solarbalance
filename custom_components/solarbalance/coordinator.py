"""DataUpdateCoordinator for SolarBalance."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .adapters.active_control_publisher import ActiveControlPublisher
from .adapters.decision_publisher import DecisionPublisher
from .adapters.entity_reader import EntityReader
from .adapters.watchdog import EntityWatchdog
from .const import (
    CONF_ACTIVE_CONTROL_ENABLED,
    CONF_GRID_FILTER_SAMPLES,
    CONF_MAX_RAMP_W,
    CONF_PRIORITIES,
    CONF_SOC_EQUALISER_DEADBAND_PCT,
    CONF_SOC_EQUALISER_ENABLED,
    CONF_SOC_EQUALISER_KP_W_PER_PCT,
    CONF_SOC_EQUALISER_MAX_W,
    CONF_SOC_EQUALISER_PROBE_STEP_W,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TICK_INTERVAL_S,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_SETPOINT_W,
    DEFAULT_BACKUP_RESERVE_SOC_PCT,
    DEFAULT_BALANCING_ALPHA,
    DEFAULT_COST_MIN_CHEAP_THRESHOLD,
    DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD,
    DEFAULT_GRID_FILTER_SAMPLES,
    DEFAULT_MAX_RAMP_W,
    DEFAULT_SOC_EQUALISER_DEADBAND_PCT,
    DEFAULT_SOC_EQUALISER_KP_W_PER_PCT,
    DEFAULT_SOC_EQUALISER_MAX_W,
    DEFAULT_SOC_EQUALISER_PROBE_STEP_W,
    DEFAULT_STORM_TARGET_SOC_PCT,
    DEFAULT_TICK_INTERVAL_S,
    DEFAULT_ZERO_INJECTION_HYSTERESIS_W,
    DOMAIN,
)
from .core.arbitrer import Arbiter, ArbitrationResult
from .core.controllers.balancing import BalancingController
from .core.controllers.load_dispatch import LoadDispatchController
from .core.controllers.regulation import apply_slew_limit, resolve_fleet_target_w
from .core.controllers.soc_equaliser import SocEqualiserController
from .core.controllers.zero_injection import (
    PerPhaseZeroInjectionController,
    PerPhaseZeroInjectionState,
    ZeroInjectionController,
    ZeroInjectionState,
)
from .core.energy import DailyEnergyAccumulator
from .core.filters import RollingMedian
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
        self._zi_state: ZeroInjectionState | PerPhaseZeroInjectionState = ZeroInjectionState()
        self._negative_baseline_ticks: int = 0
        self._baseline_notification_sent: bool = False
        self._storm_expires_at: datetime | None = None
        self._storm_manual: bool = False

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

        # Indirect SoC equaliser — only meaningful when at least one battery is
        # declared non-controllable (reports state but cannot be commanded).
        self._controllable_battery_names = frozenset(
            d.name for d in devices if d.battery is not None and d.battery.controllable
        )
        uncontrollable = [
            (d.name, d.battery)
            for d in devices
            if d.battery is not None and not d.battery.controllable
        ]
        self._soc_equaliser: SocEqualiserController | None = None
        if uncontrollable and bool(cfg.get(CONF_SOC_EQUALISER_ENABLED, False)):
            self._soc_equaliser = SocEqualiserController(
                uncontrollable,
                kp_w_per_pct=float(
                    cfg.get(CONF_SOC_EQUALISER_KP_W_PER_PCT, DEFAULT_SOC_EQUALISER_KP_W_PER_PCT)
                ),
                max_steering_w=float(
                    cfg.get(CONF_SOC_EQUALISER_MAX_W, DEFAULT_SOC_EQUALISER_MAX_W)
                ),
                soc_deadband_pct=float(
                    cfg.get(CONF_SOC_EQUALISER_DEADBAND_PCT, DEFAULT_SOC_EQUALISER_DEADBAND_PCT)
                ),
                probe_step_w=float(
                    cfg.get(CONF_SOC_EQUALISER_PROBE_STEP_W, DEFAULT_SOC_EQUALISER_PROBE_STEP_W)
                ),
            )

        # Active control — entity writes to user equipment (V2). Off by default;
        # the publisher is a no-op unless the global flag is on and at least one
        # device declares a discharge setpoint entity.
        self._active_control_enabled = bool(cfg.get(CONF_ACTIVE_CONTROL_ENABLED, False))
        self._active_control = ActiveControlPublisher(hass, devices)
        self._active_control_suspended = False

        # Slew-rate limit on the aggregate battery target (anti limit-cycle).
        self._max_ramp_w = float(cfg.get(CONF_MAX_RAMP_W, DEFAULT_MAX_RAMP_W))
        self._last_total_power_w: float | None = None

        zi_enabled = bool(cfg.get(CONF_ZERO_INJECTION_ENABLED, True))
        self._zi_enabled = zi_enabled
        pdl = next((m for m in meters if m.kind is MeterKind.PDL), None)
        self._per_phase_zi = bool(pdl and pdl.per_phase_zi and pdl.phases == 3)
        hysteresis = float(
            cfg.get(CONF_ZERO_INJECTION_HYSTERESIS_W, DEFAULT_ZERO_INJECTION_HYSTERESIS_W)
        )
        if self._per_phase_zi:
            self._zi_controller: ZeroInjectionController | PerPhaseZeroInjectionController = (
                PerPhaseZeroInjectionController(hysteresis_w=hysteresis)
            )
            self._zi_state = PerPhaseZeroInjectionState()
        else:
            self._zi_controller = ZeroInjectionController(hysteresis_w=hysteresis)
        self._zi_setpoint_w = float(cfg.get(CONF_ZERO_INJECTION_SETPOINT_W, 0))
        self._tick_s = tick

        # Rolling-median filter on the grid reading fed to the regulator (B):
        # rejects single-tick sensor glitches and brief load steps. The displayed
        # grid sensor keeps the raw value.
        grid_samples = int(cfg.get(CONF_GRID_FILTER_SAMPLES, DEFAULT_GRID_FILTER_SAMPLES))
        self._grid_filter = RollingMedian(grid_samples)
        self._grid_filter_l1 = RollingMedian(grid_samples)
        self._grid_filter_l2 = RollingMedian(grid_samples)
        self._grid_filter_l3 = RollingMedian(grid_samples)

        # Daily energy integration (fallback when no vendor daily_energy_entity).
        self._energy = DailyEnergyAccumulator()

        # Watchdog — entity lists built from config
        self._critical_entity_ids, self._monitored_entity_ids = self._collect_entity_ids(
            devices, meters
        )
        self._watchdog = EntityWatchdog(hass)

        # Build ordered strategy list from config
        priorities: list[str] = cfg.get(CONF_PRIORITIES, list(_STRATEGY_CLASSES))
        subscribed_kva = int(cfg.get(CONF_SUBSCRIBED_POWER_KVA, 6))
        self._arbiter = self._build_arbiter(priorities, devices, loads, tariff, subscribed_kva)

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
        """Today's PV energy (kWh).

        Prefers a declared ``daily_energy_entity``; otherwise falls back to the
        value integrated from the PV power sensors by this integration.
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
        return round(total, 3) if found else round(self._energy.pv_kwh, 3)

    @property
    def daily_grid_import_kwh(self) -> float | None:
        """Today's grid import energy (kWh).

        Prefers the PDL meter's ``daily_import_energy_entity``; otherwise falls
        back to the value integrated from the grid power sensor.
        """
        for meter in self._meters:
            if meter.kind is MeterKind.PDL and meter.daily_import_energy_entity:
                state = self.hass.states.get(meter.daily_import_energy_entity)
                if state and state.state not in {"unavailable", "unknown", ""}:
                    try:
                        return round(float(state.state), 3)
                    except (ValueError, TypeError):
                        pass
        return round(self._energy.grid_import_kwh, 3)

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

    def activate_storm_mode(self, duration_h: float | None = None) -> None:
        """Enter storm mode, optionally with an automatic exit after ``duration_h`` hours."""
        self.mode = HemsMode.STORM
        self._storm_manual = True
        if duration_h is not None:
            self._storm_expires_at = datetime.now(UTC) + timedelta(hours=duration_h)
            _LOGGER.info("Storm mode activated — will auto-exit after %.1f h", duration_h)
        else:
            self._storm_expires_at = None

    # ------------------------------------------------------------------ HA hook

    async def _async_update_data(self) -> Snapshot | None:
        """Run one tick: read entities → watchdog → snapshot → arbitrate → publish."""
        if self._mode is HemsMode.PAUSED:
            return None

        try:
            snapshot = self._reader.snapshot()
        except Exception as exc:
            raise UpdateFailed(f"EntityReader failed: {exc}") from exc

        # --- Baseline sanity check: negative baseline signals a mapping error ---
        self._check_baseline(snapshot)

        # --- Daily energy integration (fallback when no vendor daily entity) ---
        self._energy.update(
            now=snapshot.timestamp,
            local_date=dt_util.as_local(snapshot.timestamp).date(),
            pv_w=snapshot.pv_total_w,
            grid_w=snapshot.grid_power_w,
        )

        # --- Grid median filter (B): clean the value handed to the regulator;
        # the displayed grid sensor keeps snapshot.grid_power_w (raw). ---
        grid_filtered_w = self._grid_filter.update(snapshot.grid_power_w)
        grid_l1_filtered = (
            self._grid_filter_l1.update(snapshot.grid_power_l1_w)
            if snapshot.grid_power_l1_w is not None
            else None
        )
        grid_l2_filtered = (
            self._grid_filter_l2.update(snapshot.grid_power_l2_w)
            if snapshot.grid_power_l2_w is not None
            else None
        )
        grid_l3_filtered = (
            self._grid_filter_l3.update(snapshot.grid_power_l3_w)
            if snapshot.grid_power_l3_w is not None
            else None
        )

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

        # --- Storm mode auto-trigger and duration expiry ---
        if self._mode is HemsMode.STORM:
            if self._storm_expires_at is not None and snapshot.timestamp >= self._storm_expires_at:
                _LOGGER.info("Storm mode duration elapsed — returning to normal")
                self._storm_expires_at = None
                # Keep _storm_manual=True to suppress immediate auto re-entry while
                # the weather warning is still active.
                self.mode = HemsMode.NORMAL
            elif not self._storm_manual and not snapshot.weather_warning_active:
                # Auto-triggered storm: exit when warning clears
                self.mode = HemsMode.NORMAL
        elif self._mode is HemsMode.NORMAL and snapshot.weather_warning_active and not self._storm_manual:
            self.mode = HemsMode.STORM
        elif self._mode is HemsMode.NORMAL and not snapshot.weather_warning_active and self._storm_manual:
            # Warning cleared after a timer-based exit — re-arm auto-trigger for future events.
            self._storm_manual = False

        # Resolve current tariff prices
        import_price = self._tariff.current_import_price(snapshot.timestamp)
        export_price = self._tariff.current_export_price(snapshot.timestamp)

        snapshot = replace(
            snapshot,
            current_import_price=import_price,
            current_export_price=export_price,
        )

        # --- Strategy execution or manual override ---
        if self._mode is HemsMode.MANUAL_OVERRIDE and self._battery_override is not None:
            result: ArbitrationResult = self._build_override_result(snapshot)
        elif self._mode is HemsMode.STORM:
            result = self._build_storm_result(snapshot)
        else:
            result = self._arbiter.run(snapshot)

        # Apply zero-injection correction when it owns regulation: only in NORMAL
        # mode (storm/override/degraded drive batteries with explicit intent).
        zi_correction_w = 0.0
        zi_regulating = self._zi_enabled and self._mode is HemsMode.NORMAL
        if zi_regulating:
            if (
                self._per_phase_zi
                and isinstance(self._zi_controller, PerPhaseZeroInjectionController)
                and isinstance(self._zi_state, PerPhaseZeroInjectionState)
            ):
                # Per-phase correction requires all three phase readings.
                l1 = grid_l1_filtered
                l2 = grid_l2_filtered
                l3 = grid_l3_filtered
                if l1 is not None and l2 is not None and l3 is not None:
                    sp = self._zi_setpoint_w / 3.0
                    zi_result = self._zi_controller.step(
                        grid_l1_w=l1,
                        grid_l2_w=l2,
                        grid_l3_w=l3,
                        setpoint_l1_w=sp,
                        setpoint_l2_w=sp,
                        setpoint_l3_w=sp,
                        dt_s=float(self._tick_s),
                        state=self._zi_state,
                    )
                    self._zi_state = zi_result.new_state
                    zi_correction_w = zi_result.correction_w
                    if not zi_result.in_deadband:
                        _LOGGER.debug(
                            "ZI/3ph corrections L1=%.0fW L2=%.0fW L3=%.0fW",
                            zi_result.correction_l1_w,
                            zi_result.correction_l2_w,
                            zi_result.correction_l3_w,
                        )
                else:
                    _LOGGER.warning(
                        "per_phase_zi enabled but L1/L2/L3 entities missing — "
                        "falling back to aggregate ZI"
                    )
            else:
                assert isinstance(self._zi_controller, ZeroInjectionController)
                assert isinstance(self._zi_state, ZeroInjectionState)
                zi_result = self._zi_controller.step(
                    grid_power_w=grid_filtered_w,
                    setpoint_w=self._zi_setpoint_w,
                    dt_s=float(self._tick_s),
                    state=self._zi_state,
                )
                self._zi_state = zi_result.new_state
                zi_correction_w = zi_result.correction_w
                if not zi_result.in_deadband:
                    _LOGGER.debug(
                        "ZI correction %.0fW (grid=%.0fW filtered, setpoint=%.0fW)",
                        zi_result.correction_w,
                        grid_filtered_w,
                        self._zi_setpoint_w,
                    )

        # Indirect SoC equaliser: bias the controllable fleet to steer the
        # automatic (non-controllable) battery toward the fleet mean SoC. Skipped
        # in modes that drive batteries with their own logic (storm / override).
        steering_w = 0.0
        if self._soc_equaliser is not None and self._mode not in {
            HemsMode.DEGRADED,
            HemsMode.STORM,
            HemsMode.MANUAL_OVERRIDE,
        }:
            controllable_states = [
                b for b in snapshot.batteries if b.device_name in self._controllable_battery_names
            ]
            uncontrollable_states = {
                b.device_name: b
                for b in snapshot.batteries
                if b.device_name not in self._controllable_battery_names
            }
            eq_result = self._soc_equaliser.step(
                controllable_states=controllable_states,
                uncontrollable_states=uncontrollable_states,
            )
            steering_w = eq_result.steering_w
            if not eq_result.in_deadband:
                _LOGGER.debug(
                    "SoC equaliser steering %.0fW (fleet target=%.1f%%)",
                    steering_w,
                    eq_result.target_soc_pct,
                )

        # Resolve a single aggregate target. When zero-injection regulates, it
        # owns the grid loop (target = current fleet power + PI delta); otherwise
        # the strategies' absolute target drives the fleet. Summing both is what
        # caused the tick-frequency limit cycle. See core/controllers/regulation.
        current_fleet_w = sum(
            b.power_w
            for b in snapshot.batteries
            if b.available and b.device_name in self._controllable_battery_names
        )
        absolute_target_w = sum(
            t.preferred_power_w or 0.0 for t in result.decision.battery_targets.values()
        )
        total_power_w = resolve_fleet_target_w(
            zi_regulating=zi_regulating,
            current_fleet_w=current_fleet_w,
            zi_correction_w=zi_correction_w,
            absolute_target_w=absolute_target_w,
            steering_w=steering_w,
        )

        # Apply grid constraints: clamp the aggregate battery target so the
        # projected grid exchange honours max_import_w and max_export_w.
        # Projection: new_grid ≈ current_grid + (target_battery - current_battery)
        gc = result.decision.grid_constraint
        current_battery_w = snapshot.battery_power_total_w
        if gc.max_import_w is not None:
            # target_battery ≤ max_import_w - current_grid + current_battery
            total_power_w = min(
                total_power_w,
                gc.max_import_w - snapshot.grid_power_w + current_battery_w,
            )
        if gc.max_export_w is not None:
            # target_battery ≥ -max_export_w - current_grid + current_battery
            total_power_w = max(
                total_power_w,
                -gc.max_export_w - snapshot.grid_power_w + current_battery_w,
            )

        # Slew-rate limit: cap how far the command may move per tick. Hard safety
        # belt against limit cycles given the battery's actuation lag.
        total_power_w = apply_slew_limit(total_power_w, self._last_total_power_w, self._max_ramp_w)
        self._last_total_power_w = total_power_w

        # Dispatch loads using the unallocated surplus
        battery_states = {b.device_name: b for b in snapshot.batteries}
        balancing_result = self._balancing.allocate(
            total_power_w=total_power_w,
            states=battery_states,
            now=snapshot.timestamp,
        )
        load_states = {ls.name: ls for ls in snapshot.loads}
        self._load_dispatch.dispatch(
            available_surplus_w=max(
                0.0,
                -snapshot.grid_power_w
                - sum(balancing_result.per_battery_w.values())
                + current_battery_w,
            ),
            states=load_states,
            now=snapshot.timestamp,
        )

        self._publisher.publish(result, balancing_result=balancing_result)
        soc_by_device = {b.device_name: b.soc_pct for b in snapshot.batteries}
        await self._apply_active_control(balancing_result.per_battery_w, soc_by_device)
        return snapshot

    # ------------------------------------------------------------------ helpers

    async def _apply_active_control(
        self,
        per_battery_w: Mapping[str, float],
        soc_by_device: Mapping[str, float],
    ) -> None:
        """Write discharge setpoints to equipment when active control is enabled.

        Suspended in DEGRADED mode (stale entities): managed setpoints are reset
        to 0 W once, then left untouched until the entities recover.
        """
        if not (self._active_control_enabled and self._active_control.enabled):
            return
        if self._mode is HemsMode.DEGRADED:
            if not self._active_control_suspended:
                await self._active_control.reset()
                self._active_control_suspended = True
            return
        self._active_control_suspended = False
        await self._active_control.apply(per_battery_w, soc_by_device)

    def _build_storm_result(self, snapshot: Snapshot) -> ArbitrationResult:
        """Build an ArbitrationResult that charges all batteries to the storm SoC target.

        Falls back to normal arbitration once all available batteries have
        reached DEFAULT_STORM_TARGET_SOC_PCT, so the system stops trying to
        push past the target when there is nothing left to charge.
        """
        available = [b for b in snapshot.batteries if b.available]
        if available and all(b.soc_pct >= DEFAULT_STORM_TARGET_SOC_PCT for b in available):
            _LOGGER.info(
                "Storm preparation complete — all batteries at ≥%.0f%% SoC",
                DEFAULT_STORM_TARGET_SOC_PCT,
            )
            return self._arbiter.run(snapshot)

        targets: dict[str, BatteryTarget] = {}
        for device in self._devices:
            if device.battery is None:
                continue
            bat = device.battery
            targets[device.name] = BatteryTarget(
                soc_min_pct=float(bat.soc_min_pct),
                soc_max_pct=DEFAULT_STORM_TARGET_SOC_PCT,
                preferred_power_w=float(bat.max_charge_power_w),
            )
        storm_decision = Decision(
            battery_targets=targets,
            confidence=1.0,
            rationale=f"storm: charging to {DEFAULT_STORM_TARGET_SOC_PCT:.0f}% SoC",
        )
        return ArbitrationResult(
            decision=storm_decision,
            dominant_strategy="storm",
            per_strategy=(),
        )

    def _build_override_result(self, snapshot: Snapshot) -> ArbitrationResult:
        """Build an ArbitrationResult directly from the active battery override."""
        ovr = self._battery_override
        assert ovr is not None

        # Expiry check
        if ovr.expires_at is not None and snapshot.timestamp >= ovr.expires_at:
            _LOGGER.info("Force %s override expired — returning to normal", ovr.kind)
            self.clear_force_override()
            return self._arbiter.run(snapshot)

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
                return self._arbiter.run(snapshot)

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

    _BASELINE_NEGATIVE_THRESHOLD_W = -100.0
    _BASELINE_NEGATIVE_TICKS_TRIGGER = 3
    _BASELINE_NOTIFICATION_ID = "solarbalance_baseline_negative"

    def _check_baseline(self, snapshot: Snapshot) -> None:
        """Fire (or dismiss) a persistent notification when baseline is persistently negative.

        A negative baseline means the sign convention of at least one entity is wrong.
        We wait for 3 consecutive ticks to avoid spurious alerts during transients.
        """
        from homeassistant.components.persistent_notification import async_create, async_dismiss

        if snapshot.baseline_consumption_w < self._BASELINE_NEGATIVE_THRESHOLD_W:
            self._negative_baseline_ticks += 1
            if (
                self._negative_baseline_ticks >= self._BASELINE_NEGATIVE_TICKS_TRIGGER
                and not self._baseline_notification_sent
            ):
                _LOGGER.warning(
                    "Baseline consumption persistently negative (%.0f W) — "
                    "check entity sign conventions",
                    snapshot.baseline_consumption_w,
                )
                async_create(
                    self.hass,
                    (
                        f"La consommation de fond calculée est **négative** "
                        f"({snapshot.baseline_consumption_w:.0f} W) depuis plusieurs cycles.\n\n"
                        "Cela indique probablement une erreur de convention de signe "
                        "sur une entité batterie ou compteur. Vérifiez le paramètre "
                        "`power_sign_convention` dans votre configuration YAML SolarBalance."
                    ),
                    title="SolarBalance — Mapping incorrect",
                    notification_id=self._BASELINE_NOTIFICATION_ID,
                )
                self._baseline_notification_sent = True
        else:
            if self._baseline_notification_sent:
                async_dismiss(self.hass, self._BASELINE_NOTIFICATION_ID)
                self._baseline_notification_sent = False
            self._negative_baseline_ticks = 0

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
        subscribed_power_kva: int = 6,
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
                    cheap_threshold=DEFAULT_COST_MIN_CHEAP_THRESHOLD,
                    expensive_threshold=DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD,
                )
            elif kind == StrategyKind.BACKUP.value:
                strat = cls(devices, loads, reserve_soc_pct=DEFAULT_BACKUP_RESERVE_SOC_PCT)
            elif kind == StrategyKind.PEAK_SHAVING.value:
                # Convert kVA subscription to W; use None only when kVA is 0
                max_import_w: float | None = (
                    float(subscribed_power_kva * 1000) if subscribed_power_kva > 0 else None
                )
                strat = cls(devices, loads, max_import_w=max_import_w)
            else:
                strat = cls(devices, loads)
            strategies.append(strat)

        if not strategies:
            strategies.append(SelfConsumptionStrategy(devices, loads))
        return Arbiter(strategies)
