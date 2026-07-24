"""DataUpdateCoordinator for SolarBalance."""

import contextlib
import logging
import math
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .adapters.active_control_publisher import ActiveControlPublisher
from .adapters.decision_publisher import DecisionPublisher
from .adapters.entity_reader import EntityReader
from .adapters.load_publisher import LoadPublisher
from .adapters.recorder_seed import seed_consumption_from_statistics
from .adapters.watchdog import EntityWatchdog
from .const import (
    AUTOTUNE_EQ_STEP_MIN_W,
    AUTOTUNE_ZI_KP_MIN,
    CONF_ACTIVE_CONTROL_ENABLED,
    CONF_ANTICIPATION_HORIZON_MIN,
    CONF_ANTICIPATION_MARGIN_W,
    CONF_ANTICIPATORY_CURTAILMENT_ENABLED,
    CONF_APPLIANCE_POWER_ENTITIES,
    CONF_BACKUP_RESERVE_SOC_PCT,
    CONF_BASELINE_FLOOR_MARGIN_W,
    CONF_BASELINE_WINDOW_END_H,
    CONF_BASELINE_WINDOW_START_H,
    CONF_CURTAILMENT_DEADBAND_W,
    CONF_CURTAILMENT_RAMP_W,
    CONF_CURTAILMENT_SETTLE_TICKS,
    CONF_DRY_RUN,
    CONF_EVENING_PEAK_END_H,
    CONF_EVENING_PEAK_START_H,
    CONF_EVENING_RESERVE_ENABLED,
    CONF_EVENING_RESERVE_MAX_PCT,
    CONF_EVENING_SHED_ENABLED,
    CONF_EVENING_SHED_MIN_POWER_W,
    CONF_EXPORT_PRICE,
    CONF_FLEET_REVERSAL_DWELL_S,
    CONF_FORECAST_SAFETY_FACTOR,
    CONF_GRID_BACKUP_ENTITY,
    CONF_GRID_FILTER_SAMPLES,
    CONF_HC_END,
    CONF_HC_PRICE,
    CONF_HC_START,
    CONF_HP_PRICE,
    CONF_IMPORT_PRICE,
    CONF_LOAD_CONTROL_ENABLED,
    CONF_LOCAL_AC_LOAD_ENTITIES,
    CONF_MAX_RAMP_W,
    CONF_NO_BATTERY_EXPORT,
    CONF_NONCONTROLLABLE_STALE_S,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_OVERLOAD_PROTECTION_ENABLED,
    CONF_PREDICTIVE_CONTROL_ENABLED,
    CONF_PRIORITIES,
    CONF_PV_DROP_COMPENSATION_ENABLED,
    CONF_PV_FORECAST_TOMORROW_ENTITY,
    CONF_SOC_EQUALISER_ADAPTIVE_CADENCE,
    CONF_SOC_EQUALISER_CADENCE_TICKS,
    CONF_SOC_EQUALISER_DEADBAND_PCT,
    CONF_SOC_EQUALISER_ENABLED,
    CONF_SOC_EQUALISER_KP_W_PER_PCT,
    CONF_SOC_EQUALISER_MAX_W,
    CONF_SOC_EQUALISER_MIN_PV_W,
    CONF_SOC_EQUALISER_PROBE_STEP_W,
    CONF_SOLAR_FALLBACK_ENABLED,
    CONF_SOLAR_FALLBACK_SAFETY_PCT,
    CONF_SPOT_MARKUP,
    CONF_SPOT_PRICE_ENTITY,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TARIFF_TYPE,
    CONF_TEMPO_COLOR_ENTITY,
    CONF_TEMPO_COLOR_TOMORROW_ENTITY,
    CONF_TEMPO_RED_PREP_ENABLED,
    CONF_TEMPO_RED_PREP_SOC_PCT,
    CONF_TICK_INTERVAL_S,
    CONF_VACATION_SOC_MAX_PCT,
    CONF_WEATHER_MIN_LEVEL,
    CONF_WEATHER_PHENOMENA,
    CONF_ZERO_INJECTION_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    CONF_ZERO_INJECTION_KP,
    CONF_ZERO_INJECTION_SETPOINT_W,
    CONF_ZI_SETTLE_MIN_DROP_W,
    CONF_ZI_SETTLE_TICKS,
    DEFAULT_ANTICIPATION_HORIZON_MIN,
    DEFAULT_ANTICIPATION_MARGIN_W,
    DEFAULT_BACKUP_RESERVE_SOC_PCT,
    DEFAULT_BALANCING_ALPHA,
    DEFAULT_BASELINE_FLOOR_MARGIN_W,
    DEFAULT_BASELINE_WINDOW_END_H,
    DEFAULT_BASELINE_WINDOW_START_H,
    DEFAULT_COST_MIN_CHEAP_THRESHOLD,
    DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD,
    DEFAULT_CURTAILMENT_DEADBAND_W,
    DEFAULT_CURTAILMENT_RAMP_W,
    DEFAULT_CURTAILMENT_SETTLE_TICKS,
    DEFAULT_DRY_RUN,
    DEFAULT_EVENING_PEAK_END_H,
    DEFAULT_EVENING_PEAK_START_H,
    DEFAULT_EVENING_RESERVE_MAX_PCT,
    DEFAULT_EVENING_SHED_MIN_POWER_W,
    DEFAULT_EXPORT_PRICE,
    DEFAULT_FLEET_REVERSAL_DWELL_S,
    DEFAULT_FORECAST_SAFETY_FACTOR,
    DEFAULT_GRID_FILTER_SAMPLES,
    DEFAULT_HC_END,
    DEFAULT_HC_PRICE,
    DEFAULT_HC_START,
    DEFAULT_HP_PRICE,
    DEFAULT_IMPORT_PRICE,
    DEFAULT_MAX_RAMP_W,
    DEFAULT_NO_BATTERY_EXPORT,
    DEFAULT_NONCONTROLLABLE_STALE_S,
    DEFAULT_OVERLOAD_PROTECTION_ENABLED,
    DEFAULT_PV_DROP_COMPENSATION_ENABLED,
    DEFAULT_SOC_EQUALISER_ADAPTIVE_CADENCE,
    DEFAULT_SOC_EQUALISER_CADENCE_TICKS,
    DEFAULT_SOC_EQUALISER_DEADBAND_PCT,
    DEFAULT_SOC_EQUALISER_KP_W_PER_PCT,
    DEFAULT_SOC_EQUALISER_MAX_W,
    DEFAULT_SOC_EQUALISER_MIN_PV_W,
    DEFAULT_SOC_EQUALISER_PROBE_STEP_W,
    DEFAULT_SOLAR_FALLBACK_SAFETY_PCT,
    DEFAULT_SPOT_MARKUP,
    DEFAULT_STORM_TARGET_SOC_PCT,
    DEFAULT_TARIFF_TYPE,
    DEFAULT_TEMPO_RED_PREP_SOC_PCT,
    DEFAULT_TICK_INTERVAL_S,
    DEFAULT_VACATION_SOC_MAX_PCT,
    DEFAULT_WEATHER_MIN_LEVEL,
    DEFAULT_ZERO_INJECTION_HYSTERESIS_W,
    DEFAULT_ZERO_INJECTION_KP,
    DEFAULT_ZI_SETTLE_MIN_DROP_W,
    DEFAULT_ZI_SETTLE_TICKS,
    DOMAIN,
    EVENT_APPLIANCE_ANOMALY,
    EVENT_FORCE_CHARGE,
    EVENT_MODE_CHANGED,
    EVENT_SHEDDING,
    EVENT_TEMPO_RED_DAY,
    OVERLOAD_PROTECTION_FRACTION,
    STORE_KEY,
    STORE_VERSION,
)
from .core.appliance_cycles import ApplianceCycles
from .core.arbitrer import Arbiter, ArbitrationResult
from .core.autotuner import RegulationAutoTuner
from .core.baseline import NightBaselineEstimator
from .core.consumption_profile import ConsumptionProfile, segment_for
from .core.controllers.anticipation import (
    SINK_CLOUD_BATTERY,
    SINK_CONTROLLABLE_BATTERY,
    SINK_LOAD,
    AnticipationInputs,
    AnticipationResult,
    Sink,
    compute_sink_budget,
    evaluate_anticipation,
)
from .core.controllers.balancing import BalancingController, BalancingResult
from .core.controllers.curtailment import CurtailmentController, distribute_pv_limit
from .core.controllers.deadline import DeadlineDecision, evaluate_deadline
from .core.controllers.ev_fast_charge import FastChargeDecision, evaluate_fast_charge
from .core.controllers.evening_reserve import EveningReserve, evening_reserve
from .core.controllers.evening_shed import (
    BatteryChargeNeed,
    ShedDecision,
    evaluate_evening_shed,
)
from .core.controllers.load_dispatch import LoadCommand, LoadDispatchController, load_eligible
from .core.controllers.load_settle import SettleState, advance_settle, arm_settle
from .core.controllers.overload import SheddableLoad, relieve_overload
from .core.controllers.pv_drop import PvDropDetector
from .core.controllers.regulation import (
    RegulationInputs,
    apply_slew_limit,
    noncontrollable_charge_offset_w,
    predictive_steering_w,
    resolve_total_power,
)
from .core.controllers.soc_equaliser import SocEqualiserController
from .core.controllers.solar_fallback import SolarFallbackResult, solar_only_target_w
from .core.controllers.solar_recovery import best_start, estimate_solar_share
from .core.controllers.zero_injection import (
    PerPhaseZeroInjectionController,
    PerPhaseZeroInjectionState,
    ZeroInjectionController,
    ZeroInjectionState,
)
from .core.energy import DailyEnergyAccumulator
from .core.explain import Explanation, explain_tick
from .core.filters import AdaptiveVolatilityDamper, RollingMedian
from .core.forecast import (
    ForecastConfig,
    aggregate_battery_constraints,
    build_forecast_slots,
    build_pv_w_by_hour,
)
from .core.models import (
    BatteryTarget,
    Decision,
    Device,
    HemsMode,
    Load,
    LoadControlType,
    Meter,
    MeterKind,
    Snapshot,
    StrategyKind,
    capacity_weighted_soc_pct,
    stored_energy_kwh,
    usable_window_kwh,
)
from .core.planner import BatteryConstraints, PlanningResult, PredictiveScheduler
from .core.plausibility import check_grid_reading
from .core.strategies.backup import BackupStrategy
from .core.strategies.cost_min import CostMinStrategy
from .core.strategies.longevity import LongevityStrategy
from .core.strategies.peak_shaving import PeakShavingStrategy
from .core.strategies.revenue_max import RevenueMaxStrategy
from .core.strategies.self_consumption import SelfConsumptionStrategy
from .core.tariff import (
    TariffConfig,
    TempoColor,
    TempoTariff,
    build_tariff,
    parse_tempo_color,
)
from .core.weather import level_rank

_LOGGER = logging.getLogger(__name__)

# Debounce persisted-state writes; the daily counters change every tick but we
# don't need to hit disk that often. Store also flushes on HA shutdown.
_STORE_SAVE_DELAY_S = 60.0

# Advisory predictive plan re-run cadence (in ticks). The plan changes slowly and
# the DP is cheap; ~15 min at the default 10 s tick is plenty.
_PLAN_EVERY_TICKS = 90
# Ring-buffer depth of the per-tick debug history (the capture_debug service). ~2 h at
# the default 10 s tick — enough to grab an event that happened a while before.
_TICK_HISTORY_MAXLEN = 720
# Below this similarity to every known cycle, a finished cycle is called unusual.
_APPLIANCE_ANOMALY_CONFIDENCE = 0.45
# How far ahead the running-appliance draw is folded into the consumption forecast.
_APPLIANCE_FORECAST_HORIZON_S = 900.0
# Smoothing factor of the background-load estimate fed to the advisory planner.
_BASELINE_EMA_ALPHA = 0.05
# SoC margin below soc_max at which a controllable battery is treated as unable to
# absorb more (charge tapers near full). When exporting and the whole controllable
# fleet is within this margin of its ceiling, PV curtailment engages even though
# the balancer nominally "allocated" the surplus (it would not be honoured).
_CURTAIL_NEAR_FULL_MARGIN_PCT = 2.0
# Extra SoC drop required to RELEASE the near-full state once engaged (hysteresis):
# stops a SoC parked on the margin from flipping near_full — and so the PV limit and
# the no-charge floor — every tick (which made the PV oscillate when nearly full).
_CURTAIL_NEAR_FULL_HYST_PCT = 3.0
# EMA smoothing of the non-controllable (cloud) battery charge before it drives the
# cloud guards. A dumb cloud battery charges in short bursts; ~0.2 (≈ 90 s at a 10 s
# tick) averages them so the guards react to a sustained charge, not each blip.
_NC_CHARGE_EMA_ALPHA = 0.2
# Consecutive ticks the smoothed cloud-charge must stay well below the threshold before
# the "cloud is charging" latch releases. A near-full cloud battery charges in decaying
# bursts; without this the latch (and so no_charge_floor / no_feed) flapped tick-to-tick,
# slamming the STREAM between charging and dumping its PV.
_NC_CHARGING_RELEASE_DWELL_TICKS = 3
# SoC-equaliser PV-routing back-off: shrink the allowance (decay) on a sustained
# export (cloud not absorbing the routed PV), grow it (recover) only when there is
# import headroom, hold in the grid deadband. Small steps so the output moves gently
# (no yoyo); decay > recover so it backs off faster than it re-opens.
_EQ_PV_RELAX_DECAY = 0.12
_EQ_PV_RELAX_RECOVER = 0.06
# Hold the PV-routing floor (and so the STREAM setpoint) for this many ticks between
# re-evaluations, to give the slow cloud battery time to react before moving it again.
_EQ_PV_RELAX_DWELL_TICKS = 6
# Verify (read-back) the power setpoint writes this often (ticks), not every tick:
# the box is slow over BLE, so a just-sent value needs time to read back.
_VERIFY_WRITE_EVERY_TICKS = 5
# Night cloud-relief (anti-round-trip): a controllable fleet must be at least this much
# higher in SoC than a cloud battery before SB discharges it to cover the home (spares
# the lower cloud battery instead of letting it discharge into the higher one).
_CLOUD_RELIEF_SOC_MARGIN_PCT = 5.0
# Below this home consumption (W) there is nothing worth relieving.
_CLOUD_RELIEF_MIN_W = 50.0
# EMA smoothing for the fleet battery power used by the time-to-full/empty estimates,
# so a passing cloud doesn't make the remaining-time jump around.
_BATTERY_POWER_EMA_ALPHA = 0.2
# Below this |smoothed power| (W) the fleet is treated as idle → time remaining is N/A
# (dividing the energy by ~0 is meaningless).
_TIME_REMAINING_MIN_POWER_W = 50.0

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


@dataclass(frozen=True)
class ForceChargeRequest:
    """A manual 'charge now' request for one load (overrides solar-following).

    ``start_kwh`` is the load's delivered-today energy when the request began, so
    progress is measured per session. The request ends when ``target_kwh`` is
    reached (if set), ``until`` passes (if set), or the user cancels it.
    """

    start_kwh: float
    target_kwh: float | None = None
    until: datetime | None = None


_REASON_TEXT: dict[str, dict[str, str]] = {
    "fr": {
        "vacation_prefix": "Mode vacances — ",
        "paused": "En pause — aucune régulation active.",
        "storm": "Mode tempête — remplissage des batteries en cours.",
        "manual_override": "Override manuel — consigne batterie imposée.",
        "tempo_red_prep": "Pré-charge avant jour rouge Tempo (charge réseau en heures creuses).",
        "charge_surplus": "Batteries en charge — surplus solaire stocké.",
        "charge_offpeak": "Batteries en charge — fenêtre tarifaire basse (heures creuses).",
        "charge_generic": "Batteries en charge.",
        "discharge_expensive": "Batteries en décharge — prix élevé (heures pleines).",
        "discharge_no_pv": "Batteries en décharge — peu de solaire, couvre la maison.",
        "discharge_selfconsume": "Batteries en décharge — autoconsommation.",
        "idle": "Équilibre — peu d'échange avec le réseau.",
    },
    "en": {
        "vacation_prefix": "Vacation mode — ",
        "paused": "Paused — no active regulation.",
        "storm": "Storm mode — filling the batteries.",
        "manual_override": "Manual override — battery setpoint forced.",
        "tempo_red_prep": "Pre-charging before a Tempo red day (off-peak grid charge).",
        "charge_surplus": "Batteries charging — storing the solar surplus.",
        "charge_offpeak": "Batteries charging — cheap tariff window (off-peak).",
        "charge_generic": "Batteries charging.",
        "discharge_expensive": "Batteries discharging — expensive window (peak hours).",
        "discharge_no_pv": "Batteries discharging — little solar, covering the home.",
        "discharge_selfconsume": "Batteries discharging — self-consumption.",
        "idle": "Balanced — little grid exchange.",
    },
}


@dataclass(frozen=True)
class RegulationDiagnostics:
    """Last-tick internal regulation values, exposed as diagnostic sensors."""

    grid_filtered_w: float = 0.0
    zero_injection_correction_w: float = 0.0
    equaliser_offer_w: float = 0.0
    fleet_target_w: float = 0.0
    regulating: bool = False
    pv_limit_w: float = 0.0
    natural_grid_w: float = 0.0
    autotune_zi_kp: float = 0.0
    autotune_equaliser_step_w: float = 0.0
    # Which clamp set the fleet target this tick ("base" when nothing clamped).
    regulation_binding: str = "base"
    # Detected sudden PV drop (W, a passing cloud); 0 when none.
    pv_drop_w: float = 0.0
    # PV a full battery hides by auto-curtailing its array, estimated from the peer
    # inverter (W); what the SoC equaliser can route by commanding a discharge.
    eq_hidden_pv_w: float = 0.0
    # SoC-equaliser PV-routing back-off factor (1.0 = fully allowed, 0 = fully
    # backed off because the cloud battery isn't absorbing the routed PV).
    eq_pv_route_relax: float = 1.0
    # Extra per-tick internals for the live "debug" dashboard view (the tick log line):
    loop_base_w: float = 0.0  # velocity-form base (last commanded total); windup shows here
    current_fleet_w: float = 0.0  # measured controllable fleet power
    controllable_mppt_w: float = 0.0
    unallocated_w: float = 0.0  # aggregate the balancer could not place (saturation)
    nc_charge_w: float = 0.0  # smoothed non-controllable (cloud) charge
    settle_active: bool = False
    noncontrollable_charging: bool = False
    # Anticipatory curtailment (forecast pre-brake):
    sink_budget_w: float = 0.0  # what the sinks can absorb over the horizon
    forecast_surplus_w: float = 0.0  # forecast PV - predicted consumption
    anticipation_active: bool = False
    preemptive_pv_limit_w: float = 0.0  # ceiling handed to curtailment (0 = none)
    time_to_saturation_s: float | None = None  # when the sinks run out, at this rate
    # Grid readings held back this session because physics ruled them out.
    grid_rejects: int = 0
    # Which meter answered this tick: primary | backup | none.
    grid_source: str = "primary"
    # Solar-only fallback while the grid meter is missing.
    solar_fallback_active: bool = False
    solar_fallback_w: float = 0.0
    solar_fallback_reason: str = "disabled"
    # Plain-language account of this tick (key for a UI, text for logbook/attribute).
    explain_key: str = ""
    explain_text: str = ""
    # Evening reserve held for the predictable peak.
    evening_reserve_kwh: float = 0.0
    evening_reserve_active: bool = False


def _ui_tariff_spec(cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build a tariff spec dict from the UI options, or None for a flat tariff."""
    kind = str(cfg.get(CONF_TARIFF_TYPE, DEFAULT_TARIFF_TYPE))
    if kind == "hc_hp":
        hc_start = str(cfg.get(CONF_HC_START, DEFAULT_HC_START))
        hc_end = str(cfg.get(CONF_HC_END, DEFAULT_HC_END))
        hc_price = float(cfg.get(CONF_HC_PRICE, DEFAULT_HC_PRICE))
        hp_price = float(cfg.get(CONF_HP_PRICE, DEFAULT_HP_PRICE))
        # HC window + HP for the rest of the day (overnight HC handled by the slot).
        return {
            "type": "hc_hp",
            "slots": [
                {"start": hc_start, "end": hc_end, "price": hc_price},
                {"start": hc_end, "end": hc_start, "price": hp_price},
            ],
        }
    if kind == "tempo":
        return {
            "type": "tempo",
            "color_entity": cfg.get(CONF_TEMPO_COLOR_ENTITY) or None,
            "color_tomorrow_entity": cfg.get(CONF_TEMPO_COLOR_TOMORROW_ENTITY) or None,
        }
    if kind == "spot":
        return {
            "type": "spot",
            "price_entity": cfg.get(CONF_SPOT_PRICE_ENTITY) or None,
            "markup": float(cfg.get(CONF_SPOT_MARKUP, DEFAULT_SPOT_MARKUP)),
        }
    return None


def _load_nominal_w(load: Load) -> float:
    """Representative power (W) of a pilotable load for shedding decisions."""
    if load.control_type is LoadControlType.ON_OFF:
        return float(load.nominal_power_w or 0)
    if load.control_type is LoadControlType.STEPPED:
        return float(max((s.power_w for s in load.steps), default=0))
    return float(load.max_power_w or 0)  # modulating


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
        forecast: ForecastConfig | None = None,
        tariff_spec: dict[str, Any] | None = None,
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
        # Loads the user has temporarily exempted from shedding (evening-shed +
        # fast-charge inefficiency pause). Toggled by per-load switch entities.
        self._shed_exempt: set[str] = set()
        # Active manual "charge now" requests, keyed by load name.
        self._force_charge_req: dict[str, ForceChargeRequest] = {}
        # Loads restricted to cheap/off-peak tariff windows only.
        self._off_peak_only: set[str] = set()
        # Loads allowed to run only on real PV surplus (e.g. pool pump).
        self._solar_only: set[str] = set()
        # Last applied command per load (for per-load status sensors).
        self._last_load_commands: dict[str, LoadCommand] = {}
        # Tariff resolution priority: explicit object (tests) > YAML tariff: block
        # > UI tariff options > flat configurable import/export prices (defaults so
        # cost/savings accounting works out of the box).
        flat_import = float(cfg.get(CONF_IMPORT_PRICE, DEFAULT_IMPORT_PRICE))
        flat_export = float(cfg.get(CONF_EXPORT_PRICE, DEFAULT_EXPORT_PRICE))
        flat_tariff = TariffConfig(
            default_import_price=flat_import, default_export_price=flat_export
        )
        spec = dict(tariff_spec) if tariff_spec else _ui_tariff_spec(cfg)
        self._tariff_degraded = False
        if tariff is not None:
            self._tariff = tariff
        elif spec:
            spec.setdefault("export_price", flat_export)
            spec.setdefault("import_price", flat_import)
            color_entity = spec.get("color_entity")
            price_entity = spec.get("price_entity")
            try:
                self._tariff = build_tariff(
                    spec,
                    color_provider=self._make_tempo_color_provider(color_entity)
                    if color_entity
                    else None,
                    spot_price_provider=self._make_spot_price_provider(price_entity)
                    if price_entity
                    else None,
                )
            except (ValueError, KeyError, TypeError) as exc:
                # Misconfigured tariff (e.g. tempo/spot without its entity, or a
                # malformed HC/HP time): degrade to the flat tariff instead of
                # failing the whole integration setup.
                _LOGGER.warning(
                    "SolarBalance: invalid tariff config (%s) — falling back to flat prices",
                    exc,
                )
                self._tariff = flat_tariff
                self._tariff_degraded = True
                spec = None
        else:
            self._tariff = flat_tariff
        self._forecast = forecast
        self._pv_forecast_entity: str | None = cfg.get("pv_forecast_entity") or None
        self._pv_forecast_tomorrow_entity: str | None = (
            cfg.get(CONF_PV_FORECAST_TOMORROW_ENTITY) or None
        )
        self._forecast_safety_factor = float(
            cfg.get(CONF_FORECAST_SAFETY_FACTOR, DEFAULT_FORECAST_SAFETY_FACTOR)
        )
        self._mode: HemsMode = HemsMode.NORMAL
        self._pre_degraded_mode: HemsMode = HemsMode.NORMAL
        self._battery_override: _BatteryOverride | None = None
        self._zi_state: ZeroInjectionState | PerPhaseZeroInjectionState = ZeroInjectionState()
        self._negative_baseline_ticks: int = 0
        self._baseline_notification_sent: bool = False
        # Smoothed/floored baseline for display + a flag when an implausible baseline is
        # attributable to a stale (timeout) cloud battery discharging into the fleet.
        self._baseline_display_w: float | None = None
        self._baseline_cloud_timeout: bool = False
        self._notifications_enabled = bool(cfg.get(CONF_NOTIFICATIONS_ENABLED, True))
        self._alerts_sent: dict[str, bool] = {}
        self._pv_limits_by_device: dict[str, float] = {}
        # Rolling ring buffer of structured per-tick records for offline replay of a
        # regulation glitch (the `capture_debug` service dumps it to a JSONL). Sized to
        # hold ~2 h at the default 10 s tick so an event can be captured well after it
        # happened, without any live watching. Cheap: one small dict appended per tick.
        self._tick_history: deque[dict[str, Any]] = deque(maxlen=_TICK_HISTORY_MAXLEN)
        self._autotune_suggested: dict[str, float] = {}
        self._event_edges: dict[str, bool] = {}
        self._daily_history: list[dict[str, Any]] = []
        # Cumulative savings, reset on month/year rollover (persisted).
        self._savings_month_eur: float = 0.0
        self._savings_year_eur: float = 0.0
        self._savings_month: str | None = None  # "YYYY-MM" of the running month total
        self._savings_year: int | None = None  # year of the running year total
        self._storm_expires_at: datetime | None = None
        self._storm_manual: bool = False

        self._reader = EntityReader(
            hass,
            devices,
            meters,
            loads,
            pv_forecast_entity=self._pv_forecast_entity,
            grid_backup_entity=cfg.get(CONF_GRID_BACKUP_ENTITY) or None,
            weather_warning_entity=cfg.get("weather_warning_entity") or None,
            weather_phenomena=cfg.get(CONF_WEATHER_PHENOMENA, ()) or (),
            weather_min_rank=level_rank(
                str(cfg.get(CONF_WEATHER_MIN_LEVEL, DEFAULT_WEATHER_MIN_LEVEL))
            )
            or 2,
            local_ac_load_entities=cfg.get(CONF_LOCAL_AC_LOAD_ENTITIES, ()) or (),
            noncontrollable_stale_s=float(
                cfg.get(CONF_NONCONTROLLABLE_STALE_S, DEFAULT_NONCONTROLLABLE_STALE_S)
            ),
        )
        self._publisher = DecisionPublisher()
        self._balancing = BalancingController(devices, alpha=DEFAULT_BALANCING_ALPHA)
        self._load_dispatch = LoadDispatchController(loads)
        self._load_publisher = LoadPublisher(
            hass, loads, enabled=bool(cfg.get(CONF_LOAD_CONTROL_ENABLED, False))
        )
        self._predictive_control_enabled = bool(cfg.get(CONF_PREDICTIVE_CONTROL_ENABLED, False))
        self._dry_run = bool(cfg.get(CONF_DRY_RUN, DEFAULT_DRY_RUN))
        self._no_battery_export = bool(cfg.get(CONF_NO_BATTERY_EXPORT, DEFAULT_NO_BATTERY_EXPORT))
        # Integration version, set by async_setup_entry from the manifest; shown as
        # the device sw_version (no manual bump needed).
        self.version: str | None = None
        self._evening_shed_enabled = bool(cfg.get(CONF_EVENING_SHED_ENABLED, False))
        self._overload_protection_enabled = bool(
            cfg.get(CONF_OVERLOAD_PROTECTION_ENABLED, DEFAULT_OVERLOAD_PROTECTION_ENABLED)
        )
        self._tempo_red_prep_enabled = bool(cfg.get(CONF_TEMPO_RED_PREP_ENABLED, False))
        self._tempo_red_prep_soc_pct = float(
            cfg.get(CONF_TEMPO_RED_PREP_SOC_PCT, DEFAULT_TEMPO_RED_PREP_SOC_PCT)
        )
        self._tempo_color_tomorrow_entity: str | None = (spec or {}).get(
            "color_tomorrow_entity"
        ) or None
        self._vacation_soc_max_pct = float(
            cfg.get(CONF_VACATION_SOC_MAX_PCT, DEFAULT_VACATION_SOC_MAX_PCT)
        )
        self._evening_shed_min_power_w = float(
            cfg.get(CONF_EVENING_SHED_MIN_POWER_W, DEFAULT_EVENING_SHED_MIN_POWER_W)
        )
        self._evening_shed: ShedDecision | None = None
        self._fast_charge: dict[str, FastChargeDecision] = {}
        self._ev_deadline: dict[str, DeadlineDecision] = {}
        self._load_energy_kwh: dict[str, float] = {}
        self._load_energy_day: date | None = None
        self._load_energy_last_ts: datetime | None = None

        # Indirect SoC equaliser — only meaningful when at least one battery is
        # declared non-controllable (reports state but cannot be commanded).
        self._controllable_battery_names = frozenset(
            d.name for d in devices if d.battery is not None and d.battery.controllable
        )
        # Velocity-form ZI base (integrate on the last command, not the measured fleet)
        # only when an actively-controlled mode-switch battery is present: those (a
        # STREAM) charge their own PV on the DC side, so the measured fleet power is
        # decoupled from the written setpoint and a measured-base loop can't converge.
        # Normal batteries keep the battle-tested measured-form (self-limiting, no
        # wind-up if the plant can't follow). See resolve_fleet_target_w.
        self._velocity_form_zi = any(
            d.battery is not None
            and d.battery.active_control_enabled
            and d.battery.mode_setpoint_entity is not None
            for d in devices
        )
        # Usable capacity (kWh) per battery device, for capacity-weighted SoC means
        # and energy sensors. Chemistry-adjusted effective usable capacity (a 2 kWh
        # @ 75 % and a 4 kWh @ 25 % pack do not average to 50 %).
        self._usable_capacity_by_device = {
            d.name: d.battery.effective_usable_capacity_kwh
            for d in devices
            if d.battery is not None
        }
        uncontrollable = [
            (d.name, d.battery)
            for d in devices
            if d.battery is not None and not d.battery.controllable
        ]
        self._eq_min_pv_w = float(
            cfg.get(CONF_SOC_EQUALISER_MIN_PV_W, DEFAULT_SOC_EQUALISER_MIN_PV_W)
        )
        self._soc_equaliser: SocEqualiserController | None = None
        if uncontrollable and bool(cfg.get(CONF_SOC_EQUALISER_ENABLED, False)):
            self._soc_equaliser = SocEqualiserController(
                uncontrollable,
                kp_w_per_pct=float(
                    cfg.get(CONF_SOC_EQUALISER_KP_W_PER_PCT, DEFAULT_SOC_EQUALISER_KP_W_PER_PCT)
                ),
                max_offer_w=float(cfg.get(CONF_SOC_EQUALISER_MAX_W, DEFAULT_SOC_EQUALISER_MAX_W)),
                soc_deadband_pct=float(
                    cfg.get(CONF_SOC_EQUALISER_DEADBAND_PCT, DEFAULT_SOC_EQUALISER_DEADBAND_PCT)
                ),
                step_w=float(
                    cfg.get(CONF_SOC_EQUALISER_PROBE_STEP_W, DEFAULT_SOC_EQUALISER_PROBE_STEP_W)
                ),
                cadence_ticks=int(
                    cfg.get(CONF_SOC_EQUALISER_CADENCE_TICKS, DEFAULT_SOC_EQUALISER_CADENCE_TICKS)
                ),
                adaptive_cadence=bool(
                    cfg.get(
                        CONF_SOC_EQUALISER_ADAPTIVE_CADENCE,
                        DEFAULT_SOC_EQUALISER_ADAPTIVE_CADENCE,
                    )
                ),
                min_pv_w=float(
                    cfg.get(CONF_SOC_EQUALISER_MIN_PV_W, DEFAULT_SOC_EQUALISER_MIN_PV_W)
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
        # EMA state for the smoothed non-controllable (cloud) battery charge.
        self._nc_charge_smoothed_w: float | None = None
        # Hysteretic latch for "a cloud battery is charging" + its release dwell counter.
        self._nc_charging_latch: bool = False
        self._nc_charging_release_ticks: int = 0
        # EMA of the whole-fleet battery power (W, + = charge) for the remaining-time
        # estimates; None until the first tick.
        self._battery_power_smoothed_w: float | None = None
        # Throttle for the PV-limit write-verification (every _VERIFY_WRITE_EVERY_TICKS).
        self._verify_tick: int = 0
        # Near-full latch (with release hysteresis): drives both the PV curtailment
        # and the no-charge-floor skip (charge gently toward 100 % near full).
        self._curtail_near_full: bool = False
        # SoC-equaliser PV-routing back-off state (see the tick): 1.0 = allow output
        # down to the full solar input; shrinks toward 0 if the cloud doesn't absorb.
        # The floor is held across a dwell so the setpoint stays put long enough for
        # the slow cloud battery to react.
        self._eq_pv_relax: float = 1.0
        self._eq_pv_relax_active: bool = False
        self._eq_floor_w: float | None = None
        self._eq_relax_dwell: int = 0

        # PV curtailment — zero-injection's last resort when batteries saturate.
        self._curtailable_mppts: tuple[tuple[str, float], ...] = tuple(
            (d.name, float(d.mppt.peak_power_w))
            for d in devices
            if d.mppt is not None and d.mppt.active_control_enabled
        )
        self._curtailment: CurtailmentController | None = (
            CurtailmentController(
                peak_total_w=sum(peak for _, peak in self._curtailable_mppts),
                deadband_w=float(
                    cfg.get(CONF_CURTAILMENT_DEADBAND_W, DEFAULT_CURTAILMENT_DEADBAND_W)
                ),
                ramp_w=float(cfg.get(CONF_CURTAILMENT_RAMP_W, DEFAULT_CURTAILMENT_RAMP_W)),
                settle_ticks=int(
                    cfg.get(CONF_CURTAILMENT_SETTLE_TICKS, DEFAULT_CURTAILMENT_SETTLE_TICKS)
                ),
            )
            if self._curtailable_mppts
            else None
        )
        # Anticipatory curtailment: pre-brake the array from the forecast, before the
        # sinks saturate. Opt-in; inert without a curtailable inverter to brake.
        self._anticipation_enabled = bool(
            cfg.get(CONF_ANTICIPATORY_CURTAILMENT_ENABLED, False)
        ) and bool(self._curtailable_mppts)
        self._anticipation_horizon_s = (
            float(cfg.get(CONF_ANTICIPATION_HORIZON_MIN, DEFAULT_ANTICIPATION_HORIZON_MIN)) * 60.0
        )
        self._anticipation_margin_w = float(
            cfg.get(CONF_ANTICIPATION_MARGIN_W, DEFAULT_ANTICIPATION_MARGIN_W)
        )
        self._anticipation: AnticipationResult | None = None

        zi_enabled = bool(cfg.get(CONF_ZERO_INJECTION_ENABLED, True))
        self._zi_enabled = zi_enabled
        pdl = next((m for m in meters if m.kind is MeterKind.PDL), None)
        self._per_phase_zi = bool(pdl and pdl.per_phase_zi and pdl.phases == 3)
        hysteresis = float(
            cfg.get(CONF_ZERO_INJECTION_HYSTERESIS_W, DEFAULT_ZERO_INJECTION_HYSTERESIS_W)
        )
        self._zi_hysteresis_w = hysteresis
        # ki=0: the fleet-power recursion (target = measured fleet + correction)
        # already integrates the error. A second integrator would double-count and
        # oscillate — the source of the residual limit cycle.
        zi_kp = float(cfg.get(CONF_ZERO_INJECTION_KP, DEFAULT_ZERO_INJECTION_KP))
        if self._per_phase_zi:
            self._zi_controller: ZeroInjectionController | PerPhaseZeroInjectionController = (
                PerPhaseZeroInjectionController(kp=zi_kp, ki=0.0, hysteresis_w=hysteresis)
            )
            self._zi_state = PerPhaseZeroInjectionState()
        else:
            self._zi_controller = ZeroInjectionController(kp=zi_kp, ki=0.0, hysteresis_w=hysteresis)
        self._zi_setpoint_w = float(cfg.get(CONF_ZERO_INJECTION_SETPOINT_W, 0))
        self._tick_s = tick

        # Supervisory auto-tuner (always on): damps the ZI kp and the equaliser step
        # cap when they oscillate, restores them when calm. Bounded to the configured
        # values, so it can only make a loop gentler, never harsher -- there is no
        # reason to expose a toggle that, when off, just lets the loops oscillate.
        self._zi_tuner: RegulationAutoTuner | None = None
        self._eq_tuner: RegulationAutoTuner | None = None
        if zi_kp > AUTOTUNE_ZI_KP_MIN:
            self._zi_tuner = RegulationAutoTuner(default=zi_kp, min_value=AUTOTUNE_ZI_KP_MIN)
        if self._soc_equaliser is not None:
            eq_step = float(
                cfg.get(CONF_SOC_EQUALISER_PROBE_STEP_W, DEFAULT_SOC_EQUALISER_PROBE_STEP_W)
            )
            if eq_step > AUTOTUNE_EQ_STEP_MIN_W:
                self._eq_tuner = RegulationAutoTuner(
                    default=eq_step, min_value=AUTOTUNE_EQ_STEP_MIN_W
                )

        # Anti-yoyo: after a big load is dropped, freeze the ZI loop for a few
        # ticks and feed-forward the lost power onto the fleet target so the loop
        # does not slam the batteries on the resulting export transient.
        self._zi_settle_ticks = int(cfg.get(CONF_ZI_SETTLE_TICKS, DEFAULT_ZI_SETTLE_TICKS))
        self._zi_settle_min_drop_w = float(
            cfg.get(CONF_ZI_SETTLE_MIN_DROP_W, DEFAULT_ZI_SETTLE_MIN_DROP_W)
        )
        self._settle_state = SettleState()
        self._prev_load_power_w: dict[str, float] = {}

        # Rolling-median filter on the grid reading fed to the regulator (B):
        # rejects single-tick sensor glitches and brief load steps. The displayed
        # grid sensor keeps the raw value.
        grid_samples = int(cfg.get(CONF_GRID_FILTER_SAMPLES, DEFAULT_GRID_FILTER_SAMPLES))
        self._grid_filter = RollingMedian(grid_samples)
        self._grid_filter_l1 = RollingMedian(grid_samples)
        self._grid_filter_l2 = RollingMedian(grid_samples)
        self._grid_filter_l3 = RollingMedian(grid_samples)
        # Filter the controllable-fleet power (the regulator's base) with the same
        # window, so grid and base are time-aligned despite async cloud sensors.
        self._fleet_filter = RollingMedian(grid_samples)
        # Adaptive volatility damper (always on): when the grid is agitated (motor
        # loads), smooth it more so the battery tracks the slow average instead of
        # chasing the swings (which yoyos). It self-disengages when the grid is calm,
        # so there is no reason to expose a toggle.
        self._grid_damper = AdaptiveVolatilityDamper()
        # Same damper on the fleet base: a noisy MPPT (morning, clouds) enters
        # current_fleet (= battery - mppt) and would otherwise jitter the ZI target
        # even with the grid smoothed.
        self._fleet_damper = AdaptiveVolatilityDamper()

        # Daily energy integration (fallback when no vendor daily_energy_entity),
        # persisted across restarts via the HA Store.
        self._energy = DailyEnergyAccumulator()
        self._baseline_est = NightBaselineEstimator(
            window_start_h=int(
                cfg.get(CONF_BASELINE_WINDOW_START_H, DEFAULT_BASELINE_WINDOW_START_H)
            ),
            window_end_h=int(cfg.get(CONF_BASELINE_WINDOW_END_H, DEFAULT_BASELINE_WINDOW_END_H)),
        )
        self._baseline_floor_margin_w = float(
            cfg.get(CONF_BASELINE_FLOOR_MARGIN_W, DEFAULT_BASELINE_FLOOR_MARGIN_W)
        )
        self._fleet_reversal_dwell_s = float(
            cfg.get(CONF_FLEET_REVERSAL_DWELL_S, DEFAULT_FLEET_REVERSAL_DWELL_S)
        )
        self._fleet_dir = 0  # last committed fleet direction: +1 charge / -1 discharge / 0
        self._fleet_dir_at: datetime | None = None
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)

        self._diagnostics = RegulationDiagnostics()

        # Advisory predictive planner (V2, no control): aggregates the controllable
        # fleet into one equivalent battery and plans a 24 h cost-optimal schedule
        # for observation only. Built once; re-run on a slow cadence in the tick.
        fleet = [
            BatteryConstraints(
                capacity_kwh=d.battery.effective_usable_capacity_kwh,
                max_charge_w=float(d.battery.max_charge_power_w),
                max_discharge_w=float(d.battery.max_discharge_power_w),
                soc_min_pct=float(d.battery.soc_min_pct),
                soc_max_pct=float(d.battery.soc_max_pct),
            )
            for d in devices
            if d.battery is not None and d.battery.controllable
        ]
        aggregate = aggregate_battery_constraints(fleet)
        self._scheduler = PredictiveScheduler(aggregate) if aggregate is not None else None
        self._plan: PlanningResult | None = None
        self._plan_tick = 0
        # Learned hour-of-day background-consumption profile (predictive input):
        # replaces the flat night-talon in the planner so it anticipates the
        # morning/evening peaks. Learned online, persisted, restored on start.
        self._consumption_profile = ConsumptionProfile()
        # Observed (not controlled) appliances whose cycles we learn, so the panel can
        # advise when running one would actually be covered by the sun.
        self._appliance_entities: list[str] = [
            e for e in (cfg.get(CONF_APPLIANCE_POWER_ENTITIES) or []) if isinstance(e, str)
        ]
        self._appliance_cycles = ApplianceCycles()
        # Last grid reading that passed the physical-plausibility check, held when a
        # later one turns out to be impossible (see core/plausibility.py).
        self._last_plausible_grid_w: float | None = None
        self._grid_rejects: int = 0
        # Solar-only fallback: keep storing PV when the grid meter is unavailable
        # rather than idling. Opt-in — it commands on an estimate, not a measurement.
        self._solar_fallback_enabled = bool(cfg.get(CONF_SOLAR_FALLBACK_ENABLED, False))
        self._solar_fallback_safety = (
            float(cfg.get(CONF_SOLAR_FALLBACK_SAFETY_PCT, DEFAULT_SOLAR_FALLBACK_SAFETY_PCT))
            / 100.0
        )
        self._solar_fallback: SolarFallbackResult | None = None
        self._explanation: Explanation | None = None
        # Evening reserve: hold what the predictable peak will need. Opt-in — it
        # withholds energy the afternoon could otherwise use.
        self._evening_reserve_enabled = bool(cfg.get(CONF_EVENING_RESERVE_ENABLED, False))
        self._evening_peak_start_h = int(
            cfg.get(CONF_EVENING_PEAK_START_H, DEFAULT_EVENING_PEAK_START_H)
        )
        self._evening_peak_end_h = int(cfg.get(CONF_EVENING_PEAK_END_H, DEFAULT_EVENING_PEAK_END_H))
        self._evening_reserve_max = (
            float(cfg.get(CONF_EVENING_RESERVE_MAX_PCT, DEFAULT_EVENING_RESERVE_MAX_PCT)) / 100.0
        )
        self._evening_reserve: EveningReserve | None = None
        # Real-time PV-drop detector (passing cloud) — exposed for observability,
        # and (opt-in) feeds a fast discharge feed-forward via the settle window.
        self._pv_drop = PvDropDetector()
        self._pv_drop_compensation = bool(
            cfg.get(CONF_PV_DROP_COMPENSATION_ENABLED, DEFAULT_PV_DROP_COMPENSATION_ENABLED)
        )
        self._baseline_ema_w: float | None = None

        # Watchdog — entity lists built from config
        (
            self._critical_entity_ids,
            self._monitored_entity_ids,
            self._optional_entity_ids,
        ) = self._collect_entity_ids(devices, meters)
        self._watchdog = EntityWatchdog(hass)

        # Build ordered strategy list from config
        priorities: list[str] = cfg.get(CONF_PRIORITIES, list(_STRATEGY_CLASSES))
        subscribed_kva = int(cfg.get(CONF_SUBSCRIBED_POWER_KVA, 6))
        self._subscribed_power_w = float(subscribed_kva * 1000) if subscribed_kva > 0 else None
        self._backup_reserve_soc_pct = float(
            cfg.get(CONF_BACKUP_RESERVE_SOC_PCT, DEFAULT_BACKUP_RESERVE_SOC_PCT)
        )
        self._arbiter = self._build_arbiter(
            priorities, devices, loads, tariff, subscribed_kva, self._backup_reserve_soc_pct
        )

    # ------------------------------------------------------------------ public

    @property
    def mode(self) -> HemsMode:
        return self._mode

    @mode.setter
    def mode(self, value: HemsMode) -> None:
        if self._mode != value:
            _LOGGER.info("SolarBalance mode: %s → %s", self._mode.value, value.value)
            old = self._mode
            self._mode = value
            self.hass.bus.async_fire(EVENT_MODE_CHANGED, {"old": old.value, "new": value.value})

    @property
    def publisher(self) -> DecisionPublisher:
        return self._publisher

    @property
    def diagnostics(self) -> RegulationDiagnostics:
        """Last-tick internal regulation values for diagnostic sensors."""
        return self._diagnostics

    @property
    def advisory_plan(self) -> PlanningResult | None:
        """Latest advisory predictive plan (observation only, no control)."""
        return self._plan

    @property
    def predicted_consumption_now_w(self) -> float | None:
        """Learned typical background consumption for the current segment/hour (W)."""
        now = dt_util.now()
        return self._consumption_profile.predict(segment_for(now.weekday()), now.hour)

    @property
    def consumption_forecast_error_w(self) -> float | None:
        """Forecast minus actual background consumption (W): >0 over-predicted."""
        predicted = self.predicted_consumption_now_w
        snap = self.data
        if predicted is None or snap is None:
            return None
        return predicted - snap.baseline_consumption_w

    @property
    def is_degraded(self) -> bool:
        """True when the HEMS is in degraded mode."""
        return self._mode is HemsMode.DEGRADED

    async def async_restore(self) -> None:
        """Restore persisted state (daily energy counters) from the HA Store.

        Called once at setup before the first refresh. A stale day is harmless:
        the next integration tick resets the counters when the date has changed.
        """
        data = await self._store.async_load()
        baseline = (data or {}).get("baseline")
        if baseline and baseline.get("talon_w") is not None:
            with contextlib.suppress(ValueError, TypeError):
                self._baseline_est.restore(float(baseline["talon_w"]))
        history = (data or {}).get("daily_history")
        if isinstance(history, list):
            self._daily_history = [h for h in history if isinstance(h, dict)][-30:]
        cum = (data or {}).get("cumulative_savings")
        if isinstance(cum, dict):
            with contextlib.suppress(ValueError, TypeError):
                self._savings_month = cum.get("month")
                self._savings_month_eur = float(cum.get("month_eur", 0.0))
                self._savings_year = cum.get("year")
                self._savings_year_eur = float(cum.get("year_eur", 0.0))
        le = (data or {}).get("load_energy")
        if le and le.get("day"):
            with contextlib.suppress(ValueError, TypeError):
                self._load_energy_day = date.fromisoformat(le["day"])
                self._load_energy_kwh = {str(k): float(v) for k, v in (le.get("kwh") or {}).items()}
        ac = (data or {}).get("appliance_cycles")
        if isinstance(ac, dict):
            with contextlib.suppress(Exception):
                self._appliance_cycles = ApplianceCycles.from_dict(ac)
        cp = (data or {}).get("consumption_profile")
        if isinstance(cp, dict):
            with contextlib.suppress(ValueError, TypeError):
                self._consumption_profile = ConsumptionProfile.from_dict(cp)
        energy = (data or {}).get("energy")
        if not energy:
            return
        try:
            self._energy.restore(
                day=date.fromisoformat(energy["day"]),
                pv_kwh=float(energy["pv_kwh"]),
                grid_import_kwh=float(energy["grid_import_kwh"]),
                grid_export_kwh=float(energy.get("grid_export_kwh", 0.0)),
                consumption_kwh=float(energy.get("consumption_kwh", 0.0)),
                import_cost_eur=float(energy.get("import_cost_eur", 0.0)),
                export_revenue_eur=float(energy.get("export_revenue_eur", 0.0)),
                avoided_import_eur=float(energy.get("avoided_import_eur", 0.0)),
            )
        except (KeyError, ValueError, TypeError):
            _LOGGER.warning("SolarBalance: could not restore persisted daily energy")

        # Prefer recomputing today's totals from the recorder (covers a reload
        # mid-day more accurately than the periodic Store snapshot). Falls back
        # silently to the Store value above when no history is available.
        await self._recompute_daily_from_recorder()
        # Bootstrap the consumption profile from history (accurate from day one for
        # returning users); online learning fills the rest.
        await self._seed_consumption_profile()

    async def _seed_consumption_profile(self) -> None:
        """Seed unlearned consumption-profile hours from the baseline sensor history."""
        if self._consumption_profile.learned_hours >= 24:
            return
        from homeassistant.helpers import entity_registry as er

        reg = er.async_get(self.hass)
        statistic_id = reg.async_get_entity_id(
            "sensor", DOMAIN, f"{self._entry.entry_id}_baseline_consumption"
        )
        if statistic_id is None:
            return
        await seed_consumption_from_statistics(self.hass, statistic_id, self._consumption_profile)

    async def _recompute_daily_from_recorder(self) -> None:
        """Rebuild today's daily totals by replaying recorder history since midnight.

        Reads the integration's own aggregate sensors (pv/grid/battery power),
        which carry exactly the values the live integrator uses. A merged,
        forward-filled timeline is replayed through :class:`DailyEnergyAccumulator`
        so PV / import / export / consumption are consistent. No history → no-op
        (the Store-restored value stands).
        """
        from homeassistant.components.recorder import get_instance, history
        from homeassistant.helpers import entity_registry as er

        reg = er.async_get(self.hass)
        ids: dict[str, str] = {}
        for suffix in ("pv_power", "grid_power", "battery_power"):
            eid = reg.async_get_entity_id("sensor", DOMAIN, f"{self._entry.entry_id}_{suffix}")
            if eid is None:
                return  # our sensors not registered yet — keep Store value
            ids[suffix] = eid

        now = dt_util.now()
        midnight = dt_util.start_of_local_day(now)
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                history.get_significant_states,
                self.hass,
                midnight,
                now,
                list(ids.values()),
                None,  # filters
                True,  # include_start_time_state: carry the value as of midnight
                False,  # significant_changes_only: integrate every change accurately
            )
        except (HomeAssistantError, KeyError, ValueError, TypeError):
            return
        if not states:
            return

        # Build a merged, time-sorted event stream: (timestamp, signal, value).
        events: list[tuple[datetime, str, float]] = []
        for suffix, eid in ids.items():
            for st in states.get(eid, []):
                if st.state in ("unknown", "unavailable", "", None):
                    continue
                with contextlib.suppress(ValueError, TypeError):
                    events.append((st.last_updated, suffix, float(st.state)))
        if not events:
            return
        events.sort(key=lambda e: e[0])

        # Reset today's counters and replay forward-filled samples from midnight.
        self._energy.restore(
            day=midnight.date(),
            pv_kwh=0.0,
            grid_import_kwh=0.0,
            grid_export_kwh=0.0,
            consumption_kwh=0.0,
        )
        last = {"pv_power": 0.0, "grid_power": 0.0, "battery_power": 0.0}
        for ts, signal, value in events:
            last[signal] = value
            self._energy.update(
                now=ts,
                local_date=dt_util.as_local(ts).date(),
                pv_w=last["pv_power"],
                grid_w=last["grid_power"],
                battery_w=last["battery_power"],
                import_price=self._tariff.current_import_price(dt_util.as_local(ts)),
                export_price=self._tariff.current_export_price(dt_util.as_local(ts)),
            )
        _LOGGER.debug(
            "Recomputed daily energy from recorder: pv=%.2f import=%.2f export=%.2f conso=%.2f kWh",
            self._energy.pv_kwh,
            self._energy.grid_import_kwh,
            self._energy.grid_export_kwh,
            self._energy.consumption_kwh,
        )

    async def async_persist_now(self) -> None:
        """Flush persisted state to the Store immediately.

        The per-tick ``async_delay_save`` keeps rescheduling and only flushes on a
        clean HA shutdown — not on an integration reload. Calling this on unload
        guarantees the talon, daily counters and history survive a reload.
        """
        await self._store.async_save(self._persisted_state())

    def _persisted_state(self) -> dict[str, Any]:
        """Build the dict written to the Store (daily energy counters)."""
        return {
            "energy": {
                "day": self._energy.day.isoformat() if self._energy.day else None,
                "pv_kwh": round(self._energy.pv_kwh, 4),
                "grid_import_kwh": round(self._energy.grid_import_kwh, 4),
                "grid_export_kwh": round(self._energy.grid_export_kwh, 4),
                "consumption_kwh": round(self._energy.consumption_kwh, 4),
                "import_cost_eur": round(self._energy.import_cost_eur, 4),
                "export_revenue_eur": round(self._energy.export_revenue_eur, 4),
                "avoided_import_eur": round(self._energy.avoided_import_eur, 4),
            },
            "baseline": {
                "talon_w": (
                    round(self._baseline_est.talon_w, 1)
                    if self._baseline_est.talon_w is not None
                    else None
                ),
            },
            "load_energy": {
                "day": self._load_energy_day.isoformat() if self._load_energy_day else None,
                "kwh": {k: round(v, 4) for k, v in self._load_energy_kwh.items()},
            },
            "daily_history": self._daily_history,
            "cumulative_savings": {
                "month": self._savings_month,
                "month_eur": round(self._savings_month_eur, 4),
                "year": self._savings_year,
                "year_eur": round(self._savings_year_eur, 4),
            },
            "consumption_profile": self._consumption_profile.to_dict(),
            "appliance_cycles": self._appliance_cycles.to_dict(),
        }

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

    @property
    def daily_grid_export_kwh(self) -> float | None:
        """Today's grid export (injection) energy (kWh), integrated internally.

        Prefers the PDL meter's ``daily_export_energy_entity`` when declared.
        """
        for meter in self._meters:
            if meter.kind is MeterKind.PDL and meter.daily_export_energy_entity:
                state = self.hass.states.get(meter.daily_export_energy_entity)
                if state and state.state not in {"unavailable", "unknown", ""}:
                    try:
                        return round(float(state.state), 3)
                    except (ValueError, TypeError):
                        pass
        return round(self._energy.grid_export_kwh, 3)

    @property
    def daily_consumption_kwh(self) -> float | None:
        """Today's total house consumption energy (kWh), integrated internally."""
        return round(self._energy.consumption_kwh, 3)

    @property
    def daily_cost_eur(self) -> float:
        """Today's net grid cost (EUR): import cost minus export revenue."""
        return round(self._energy.import_cost_eur - self._energy.export_revenue_eur, 3)

    @property
    def daily_savings_eur(self) -> float:
        """Today's value created by PV + battery (EUR): avoided import + export revenue."""
        return round(self._energy.avoided_import_eur + self._energy.export_revenue_eur, 3)

    @property
    def daily_history(self) -> list[dict[str, Any]]:
        """Archived per-day energy/cost totals (last 30 days, oldest first)."""
        return self._daily_history

    def _maybe_archive_day(self, local_date: date) -> None:
        """On a local-date rollover, snapshot the finished day's totals (last 30 kept)."""
        day = self._energy.day
        if day is None or day == local_date:
            return
        pv = self._energy.pv_kwh
        used = self._energy.consumption_kwh
        imp = self._energy.grid_import_kwh
        autonomy = round(max(0.0, (used - imp)) / used * 100.0, 1) if used > 0 else 0.0
        self._daily_history.append(
            {
                "day": day.isoformat(),
                "pv": round(pv, 2),
                "import": round(imp, 2),
                "export": round(self._energy.grid_export_kwh, 2),
                "consumption": round(used, 2),
                "cost": round(self._energy.import_cost_eur - self._energy.export_revenue_eur, 2),
                "savings": round(
                    self._energy.avoided_import_eur + self._energy.export_revenue_eur, 2
                ),
                "autonomy": autonomy,
            }
        )
        self._daily_history = self._daily_history[-30:]
        self._accumulate_savings(day, self._daily_history[-1]["savings"])

    def _accumulate_savings(self, day: date, savings_eur: float) -> None:
        """Add a finished day's savings to the month/year totals, resetting on rollover."""
        month_key = f"{day.year:04d}-{day.month:02d}"
        if self._savings_month != month_key:
            self._savings_month = month_key
            self._savings_month_eur = 0.0
        self._savings_month_eur += savings_eur
        if self._savings_year != day.year:
            self._savings_year = day.year
            self._savings_year_eur = 0.0
        self._savings_year_eur += savings_eur

    @property
    def savings_month_eur(self) -> float:
        """Cumulative estimated savings for the current calendar month (EUR)."""
        return round(self._savings_month_eur, 2)

    @property
    def savings_year_eur(self) -> float:
        """Cumulative estimated savings for the current calendar year (EUR)."""
        return round(self._savings_year_eur, 2)

    @property
    def savings_month_start(self) -> datetime | None:
        """Local start of the tracked month (last_reset for the month total)."""
        if not self._savings_month:
            return None
        year, month = (int(x) for x in self._savings_month.split("-"))
        return dt_util.start_of_local_day(date(year, month, 1))

    @property
    def savings_year_start(self) -> datetime | None:
        """Local start of the tracked year (last_reset for the year total)."""
        if self._savings_year is None:
            return None
        return dt_util.start_of_local_day(date(self._savings_year, 1, 1))

    @property
    def daily_import_cost_eur(self) -> float:
        """Today's grid-import cost (EUR)."""
        return round(self._energy.import_cost_eur, 3)

    @property
    def current_import_price(self) -> float | None:
        """Current import price (EUR/kWh) from the active tariff."""
        return self._tariff.current_import_price(dt_util.now())

    @property
    def tariff_time_varying(self) -> bool:
        """True when the tariff has time-of-use windows (HC/HP, Tempo, spot).

        A flat ``TariffConfig`` (no slots) gives no arbitrage signal, so the
        advisory plan is meaningless and the panel hides it.
        """
        return not (isinstance(self._tariff, TariffConfig) and not self._tariff.slots)

    @property
    def config_issues(self) -> list[str]:
        """Human-readable list of likely configuration problems (empty = healthy)."""
        issues: list[str] = []
        if self._baseline_notification_sent:
            issues.append(
                "Consommation de fond négative en continu — convention de signe "
                "probablement inversée (vérifier power_sign_convention)."
            )
        if self.is_degraded:
            issues.append("Mode dégradé — une entité critique est indisponible.")
        if self._tariff_degraded:
            issues.append("Tarif invalide → repli sur prix plat (vérifier le type/les entités).")
        snap = self.data
        if self._pv_forecast_entity and snap is not None:
            hour = dt_util.as_local(snap.timestamp).hour
            if 10 <= hour <= 16:
                profile = self._entity_pv_forecast_by_hour(snap.timestamp)
                if not profile or max(profile) <= 0.0:
                    issues.append(
                        "Prévision PV vide en pleine journée — vérifier l'entité de prévision."
                    )
        issues.extend(self._static_config_issues())
        return issues

    @property
    def decision_reason_code(self) -> str:
        """Stable code for the current battery action (language-independent)."""
        snap = self.data
        if snap is None:
            return "unknown"
        if self._mode is HemsMode.PAUSED:
            return "paused"
        if self._mode is HemsMode.STORM:
            return "storm"
        if self._mode is HemsMode.MANUAL_OVERRIDE:
            return "manual_override"
        if self._mode is HemsMode.NORMAL and self._red_prep_active(snap):
            return "tempo_red_prep"
        prefix = "vacation_" if self._mode is HemsMode.VACATION else ""
        ts = dt_util.as_local(snap.timestamp)
        cheap = self._tariff.is_cheap_window(ts, threshold=DEFAULT_COST_MIN_CHEAP_THRESHOLD)
        expensive = self._tariff.is_expensive_window(
            ts, threshold=DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD
        )
        fleet = snap.battery_power_total_w
        pv = snap.pv_total_w
        if fleet > 50:
            if pv > 200 and not expensive:
                return prefix + "charge_surplus"
            if cheap:
                return prefix + "charge_offpeak"
            return prefix + "charge_generic"
        if fleet < -50:
            if expensive:
                return prefix + "discharge_expensive"
            if pv < 100:
                return prefix + "discharge_no_pv"
            return prefix + "discharge_selfconsume"
        return prefix + "idle"

    @property
    def decision_reason(self) -> str:
        """One-sentence explanation of the current battery action, localised."""
        snap = self.data
        if snap is None:
            return ""
        code = self.decision_reason_code
        lang = "fr" if (self.hass.config.language or "en").startswith("fr") else "en"
        texts = _REASON_TEXT[lang]
        prefix = ""
        if code.startswith("vacation_"):
            prefix = texts["vacation_prefix"]
            code = code[len("vacation_") :]
        return prefix + texts.get(code, texts["idle"])

    def _static_config_issues(self) -> list[str]:
        """Configuration mistakes detectable from the declared equipment alone."""
        issues: list[str] = []
        ac_devices = [
            d.name
            for d in self._devices
            if (d.battery is not None and d.battery.active_control_enabled)
            or (d.mppt is not None and d.mppt.active_control_enabled)
        ]
        if ac_devices and not self._active_control_enabled:
            issues.append(
                "Pilotage actif configuré sur "
                + ", ".join(f"« {n} »" for n in ac_devices)
                + " mais l'option globale « Pilotage actif » est désactivée → "
                "les consignes ne sont PAS écrites sur le matériel "
                "(Configurer → Régulation)."
            )
        elif ac_devices and self._dry_run:
            issues.append(
                "Pilotage actif configuré mais mode Simulation (dry_run) actif → "
                "les consignes sont calculées mais jamais écrites."
            )
        for device in self._devices:
            battery = device.battery
            if battery is None:
                continue
            usable = battery.usable_capacity_kwh or battery.capacity_kwh
            if not usable or usable <= 0.0:
                issues.append(
                    f"Batterie « {device.name} » : capacité (capacity_kwh) absente ou nulle — "
                    "la charge rapide et le délestage ne peuvent pas estimer la récupérabilité."
                )
            if battery.soc_max_pct <= battery.soc_min_pct:
                issues.append(
                    f"Batterie « {device.name} » : soc_max_pct <= soc_min_pct "
                    "(plage de SoC invalide)."
                )
        for load in self._loads:
            if load.fast_charge:
                if not load.min_charge_w or load.min_charge_w <= 0:
                    issues.append(
                        f"Consommateur « {load.name} » : fast_charge activé sans min_charge_w — "
                        "la charge rapide assistée est inopérante."
                    )
                if _load_nominal_w(load) <= 0:
                    issues.append(
                        f"Consommateur « {load.name} » : fast_charge activé sans puissance "
                        "nominale (nominal_power_w / steps / max_power_w)."
                    )
        return issues

    @property
    def daily_export_revenue_eur(self) -> float:
        """Today's export revenue (EUR)."""
        return round(self._energy.export_revenue_eur, 3)

    @property
    def evening_shed(self) -> ShedDecision | None:
        """Last evening battery-priority shedding decision (None before first tick)."""
        return self._evening_shed

    def configured_entity_ids(self) -> list[str]:
        """All HA entity_ids referenced by the configured devices / meters / loads."""
        import dataclasses

        out: set[str] = set()

        def _collect(obj: object) -> None:
            if obj is None or not dataclasses.is_dataclass(obj):
                return
            for f in dataclasses.fields(obj):
                val = getattr(obj, f.name, None)
                if f.name.endswith("_entity") and isinstance(val, str) and "." in val:
                    out.add(val)

        for device in self._devices:
            for role in (device.battery, device.mppt, device.inverter):
                _collect(role)
        for meter in self._meters:
            _collect(meter)
        for load in self._loads:
            _collect(load)
        for entity in (self._pv_forecast_entity, self._pv_forecast_tomorrow_entity):
            if entity:
                out.add(entity)
        return sorted(out)

    def is_shed_exempt(self, load_name: str) -> bool:
        """True when the user temporarily exempted this load from shedding."""
        return load_name in self._shed_exempt

    def set_shed_exempt(self, load_name: str, exempt: bool) -> None:
        """Add/remove a load from the temporary shedding-exemption set."""
        if exempt:
            self._shed_exempt.add(load_name)
        else:
            self._shed_exempt.discard(load_name)

    @property
    def time_to_full_h(self) -> float | None:
        """Hours to fill the fleet at the smoothed charge power; None when not charging."""
        return self._time_remaining_h(charging=True)

    @property
    def time_to_empty_h(self) -> float | None:
        """Hours to the SoC floor at the smoothed discharge power; None when idle."""
        return self._time_remaining_h(charging=False)

    def _time_remaining_h(self, *, charging: bool) -> float | None:
        """Energy to the ceiling/floor over the smoothed fleet power (None if idle)."""
        snap = self.data
        power_w = self._battery_power_smoothed_w
        if snap is None or power_w is None:
            return None
        if charging and power_w <= _TIME_REMAINING_MIN_POWER_W:
            return None
        if not charging and power_w >= -_TIME_REMAINING_MIN_POWER_W:
            return None
        roles = {d.name: d.battery for d in self._devices if d.battery is not None}
        energy_kwh = 0.0
        for b in snap.batteries:
            role = roles.get(b.device_name)
            if role is None or not b.available:
                continue
            usable = role.effective_usable_capacity_kwh
            if charging:
                energy_kwh += max(0.0, (role.soc_max_pct - b.soc_pct) / 100.0 * usable)
            else:
                energy_kwh += max(0.0, (b.soc_pct - role.soc_min_pct) / 100.0 * usable)
        power_kw = abs(power_w) / 1000.0
        if power_kw <= 0.0:
            return None
        return round(energy_kwh / power_kw, 2)

    async def reset_baseline_talon(self) -> None:
        """Discard the standby-baseline talon and persist the reset (service handler).

        Use after a one-off big night load (e.g. EV charging) polluted it: until the
        next clean night re-estimates, the talon reads None — no baseline subtraction
        in the evening shed — so it stops shedding on a wrong, inflated talon now.
        """
        self._baseline_est.reset()
        await self.async_persist_now()
        _LOGGER.info("SolarBalance: night-baseline talon reset on request")

    async def capture_debug(self, *, minutes: float | None = None) -> dict[str, Any]:
        """Dump the rolling per-tick history to a JSONL file for offline replay.

        The buffer fills every tick (~2 h deep), so an event can be captured well
        after it happened — call this once you notice a glitch. Returns the written
        path and the covered span so the service response is self-explanatory.
        ``minutes`` optionally keeps only the most recent window.
        """
        import json
        import os

        records = list(self._tick_history)
        if minutes is not None and minutes > 0:
            cutoff = dt_util.now() - timedelta(minutes=minutes)
            records = [
                r for r in records if (ts := dt_util.parse_datetime(r["t"])) is None or ts >= cutoff
            ]
        if not records:
            return {"path": None, "ticks": 0, "from": None, "to": None}

        directory = self.hass.config.path("solarbalance_debug")
        path = os.path.join(directory, f"tick-{dt_util.now():%Y%m%dT%H%M%S}.jsonl")

        def _write() -> None:
            os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                for rec in records:
                    fh.write(json.dumps(rec, default=str))
                    fh.write("\n")

        await self.hass.async_add_executor_job(_write)
        _LOGGER.info("SolarBalance: captured %d ticks to %s", len(records), path)
        return {
            "path": path,
            "ticks": len(records),
            "from": records[0]["t"],
            "to": records[-1]["t"],
        }

    def force_charge_load_active(self, load_name: str) -> bool:
        """True when a manual 'charge now' request is active for this load."""
        return load_name in self._force_charge_req

    def request_force_charge_load(
        self, load_name: str, *, kwh: float | None = None, hours: float | None = None
    ) -> None:
        """Start a manual 'charge now' for a load (full power, even from grid).

        ``kwh`` caps the session energy; ``hours`` caps the duration. With
        neither, it charges until cancelled. Unknown load names are ignored.
        """
        if load_name not in {ld.name for ld in self._loads}:
            _LOGGER.warning("force_charge_load: unknown load %r", load_name)
            return
        until = dt_util.utcnow() + timedelta(hours=hours) if hours and hours > 0 else None
        self._force_charge_req[load_name] = ForceChargeRequest(
            start_kwh=self._load_energy_kwh.get(load_name, 0.0),
            target_kwh=kwh if kwh and kwh > 0 else None,
            until=until,
        )

    def cancel_force_charge_load(self, load_name: str) -> None:
        """Cancel a manual 'charge now' request for a load."""
        self._force_charge_req.pop(load_name, None)

    def is_off_peak_only(self, load_name: str) -> bool:
        """True when this load is restricted to cheap/off-peak windows."""
        return load_name in self._off_peak_only

    def set_off_peak_only(self, load_name: str, enabled: bool) -> None:
        """Restrict (or not) a load to cheap/off-peak tariff windows."""
        if enabled:
            self._off_peak_only.add(load_name)
        else:
            self._off_peak_only.discard(load_name)

    def is_solar_only(self, load_name: str) -> bool:
        """True when this load may run only on real PV surplus."""
        return load_name in self._solar_only

    def set_solar_only(self, load_name: str, enabled: bool) -> None:
        """Restrict (or not) a load to running only on PV surplus."""
        if enabled:
            self._solar_only.add(load_name)
        else:
            self._solar_only.discard(load_name)

    def load_energy_today_kwh(self, load_name: str) -> float:
        """Energy delivered to a load since local midnight (kWh)."""
        return round(self._load_energy_kwh.get(load_name, 0.0), 3)

    def load_status(self, load_name: str) -> str:
        """Stable status token of a controllable load (translated by the frontend).

        One of: ``force_charge`` / ``shed`` / ``off_peak_wait`` / ``active`` /
        ``inactive`` / ``unknown``.
        """
        if load_name in self._force_charge_req:
            return "force_charge"
        shed = self._evening_shed
        if shed is not None and shed.active and load_name in shed.shed_load_names:
            return "shed"
        snap = self.data
        if load_name in self._off_peak_only and snap is not None:
            ts = dt_util.as_local(snap.timestamp)
            if not self._tariff.is_cheap_window(ts, threshold=DEFAULT_COST_MIN_CHEAP_THRESHOLD):
                return "off_peak_wait"
        cmd = self._last_load_commands.get(load_name)
        if cmd is None:
            return "unknown"
        return "active" if cmd.on else "inactive"

    @property
    def fast_charge(self) -> dict[str, FastChargeDecision]:
        """Last EV fast-charge decisions, keyed by load name."""
        return self._fast_charge

    @property
    def ev_deadline(self) -> dict[str, DeadlineDecision]:
        """Last departure-deadline decisions, keyed by load name."""
        return self._ev_deadline

    @property
    def subscribed_power_w(self) -> float | None:
        """Subscribed grid power (W), from the configured kVA. None if unset."""
        return self._subscribed_power_w

    @property
    def baseline_night_w(self) -> float | None:
        """Standby baseline (talon) averaged over the night window, or None."""
        talon = self._baseline_est.talon_w
        return round(talon, 1) if talon is not None else None

    @property
    def remaining_pv_today_kwh(self) -> float | None:
        """Forecast PV energy left until local midnight today (kWh), or None."""
        snap = self.data
        if snap is None:
            return None
        pv_by_hour = self._forecast_pv_by_hour(snap)
        if not pv_by_hour:
            return None
        local = dt_util.as_local(snap.timestamp)
        frac_left = max(0.0, 1.0 - local.minute / 60.0)
        hours_to_midnight = 24 - local.hour  # hourly slots from now to midnight
        total = 0.0
        for h, w in enumerate(pv_by_hour):
            if h >= hours_to_midnight:
                break
            total += w * (frac_left if h == 0 else 1.0) / 1000.0
        return round(total, 2)

    @property
    def pv_forecast_hourly(self) -> list[dict[str, float | str]]:
        """Hourly PV power forecast from the configured ``forecast`` block.

        Each item is ``{"start": ISO8601 hour start, "w": forecast power}``.
        Hour 0 is the current hour. Empty when no forecast is configured.
        """
        snap = self.data
        if snap is None:
            return []
        pv_by_hour = self._forecast_pv_by_hour(snap)
        if not pv_by_hour:
            return []
        base = snap.timestamp.replace(minute=0, second=0, microsecond=0)
        return [
            {"start": (base + timedelta(hours=h)).isoformat(), "w": round(v, 1)}
            for h, v in enumerate(pv_by_hour)
        ]

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

        # --- Baseline: floored/eased display value + negative-mapping sanity check ---
        self._update_baseline_display(snapshot)
        self._check_baseline(snapshot)

        # --- Daily energy integration (fallback when no vendor daily entity) ---
        local_now = dt_util.as_local(snapshot.timestamp)
        self._maybe_archive_day(local_now.date())
        self._energy.update(
            now=snapshot.timestamp,
            local_date=local_now.date(),
            pv_w=snapshot.pv_total_w,
            grid_w=snapshot.grid_power_w,
            battery_w=snapshot.battery_power_total_w,
            import_price=self._tariff.current_import_price(local_now),
            export_price=self._tariff.current_export_price(local_now),
        )
        self._baseline_est.update(
            local_time=local_now.time(),
            local_date=local_now.date(),
            baseline_w=snapshot.baseline_consumption_w,
        )
        self._track_load_energy(snapshot, local_now.date())
        self._store.async_delay_save(self._persisted_state, _STORE_SAVE_DELAY_S)
        self._run_advisory_plan(snapshot)
        self._observe_appliances(snapshot)

        # --- Physical plausibility (A): a reading the installation could not have
        # produced (more export than PV + battery discharge) is a sensor fault, not
        # information. Held *before* the median so the loop never sees it — a median
        # only rejects a lone sample, and the real glitch lasted two. ---
        plausible = check_grid_reading(
            snapshot.grid_power_w,
            pv_w=snapshot.pv_total_w,
            battery_w=snapshot.battery_power_total_w,
            last_valid_w=self._last_plausible_grid_w,
        )
        if plausible.rejected:
            self._grid_rejects += 1
            _LOGGER.warning(
                "Grid reading %.0f W is physically impossible (max export %.0f W with "
                "PV %.0f W and battery %+.0f W) — holding %.0f W",
                snapshot.grid_power_w,
                plausible.max_export_w,
                snapshot.pv_total_w,
                snapshot.battery_power_total_w,
                plausible.grid_w,
            )
        else:
            self._last_plausible_grid_w = plausible.grid_w

        # --- Grid median filter (B): clean the value handed to the regulator;
        # the displayed grid sensor keeps snapshot.grid_power_w (raw). ---
        grid_filtered_w = self._grid_filter.update(plausible.grid_w)
        if self._grid_damper is not None:
            # Smooth more when volatile (motor loads) so the loop tracks the slow
            # average and the grid absorbs the fast swings instead of yoyoing.
            grid_filtered_w = self._grid_damper.update(grid_filtered_w)
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
        wd = self._watchdog.check(
            self._critical_entity_ids,
            self._monitored_entity_ids,
            self._optional_entity_ids,
        )
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
        elif (
            self._mode is HemsMode.NORMAL
            and snapshot.weather_warning_active
            and not self._storm_manual
        ):
            self.mode = HemsMode.STORM
        elif (
            self._mode is HemsMode.NORMAL
            and not snapshot.weather_warning_active
            and self._storm_manual
        ):
            # Warning cleared after a timer-based exit — re-arm auto-trigger for future events.
            self._storm_manual = False

        # Resolve current tariff prices (local wall-clock — tariff windows are
        # defined in local time, while snapshot.timestamp is UTC).
        local_ts = dt_util.as_local(snapshot.timestamp)
        import_price = self._tariff.current_import_price(local_ts)
        export_price = self._tariff.current_export_price(local_ts)

        snapshot = replace(
            snapshot,
            current_import_price=import_price,
            current_export_price=export_price,
        )

        # --- Strategy execution or manual override ---
        red_prep = self._mode is HemsMode.NORMAL and self._red_prep_active(snapshot)
        if self._mode is HemsMode.MANUAL_OVERRIDE and self._battery_override is not None:
            result: ArbitrationResult = self._build_override_result(snapshot)
        elif self._mode is HemsMode.STORM:
            result = self._build_storm_result(snapshot)
        elif red_prep:
            # Tempo: grid-charge the controllable fleet to full during the cheap
            # HC window before a red day, so it covers the expensive red peak.
            result = self._build_charge_result(
                snapshot, self._tempo_red_prep_soc_pct, "tempo: pre-charge before red day"
            )
        else:
            result = self._arbiter.run(snapshot)

        # Apply zero-injection correction when it owns regulation: in NORMAL and
        # VACATION (self-consume from solar, never grid-charge), but not while
        # pre-charging from the grid for a red day (storm / override / red-prep
        # drive batteries with explicit intent).
        # Controllable fleet's *grid-facing AC contribution* (filtered), computed
        # before the ZI step so the setpoint guards can reason about the grid
        # without the fleet's action (grid_filtered - current_fleet).
        #
        # The fleet exports to the grid its battery discharge PLUS its own solar
        # passthrough; on a "solar-first" inverter (EcoFlow STREAM) a discharge
        # setpoint is met by PV before the cells. So the contribution is the AC
        # output, not the battery cell power:
        #     output = mppt - battery_power   (battery_power: + charge / - discharge)
        #     current_fleet (= -output)       = battery_power - mppt
        # At night (mppt = 0) this equals the battery power, so it is unchanged.
        controllable_battery_w = sum(
            b.power_w
            for b in snapshot.batteries
            if b.available and b.device_name in self._controllable_battery_names
        )
        controllable_mppt_w = sum(
            m.power_w
            for m in snapshot.mppts
            if m.available and m.device_name in self._controllable_battery_names
        )
        # PV a full battery hides by auto-curtailing its own array (estimated from the
        # peer inverter). Computed once: used by the equaliser PV-routing floor below
        # and surfaced as a diagnostic so the routing is observable, not guessed.
        hidden_pv_w = self._estimated_suppressed_pv_w(snapshot)
        # Exclude any declared local AC load (served by the fleet but off-meter, e.g.
        # the STREAM's AC socket): output = mppt - battery, of which local_ac_load is
        # consumed locally, so the *grid-facing* output = output - local_ac_load and
        # current_fleet (= -grid-facing) = (battery - mppt) + local_ac_load. This
        # stops the socket's on/off cycling from disturbing the ZI loop.
        current_fleet_w = self._fleet_filter.update(
            controllable_battery_w - controllable_mppt_w + snapshot.local_ac_load_w
        )
        if self._fleet_damper is not None:
            # Smooth the fleet base when volatile (noisy MPPT / battery hunting) so
            # the ZI target doesn't jitter through current_fleet.
            current_fleet_w = self._fleet_damper.update(current_fleet_w)
        # Natural grid = the grid the fleet would face if it did nothing. Invariant
        # to the fleet's own action, so it is the reference for deficit detection
        # and the cloud-charge guards (the raw grid sits at ~0 once the fleet covers
        # the house). Computed once and reused.
        natural_grid_w = grid_filtered_w - current_fleet_w
        # Real-time PV-drop detection (passing cloud).
        pv_drop_w = self._pv_drop.update(snapshot.pv_total_w)
        # Opt-in fast reaction: arm the settle with a negative feed-forward (discharge
        # the lost PV's worth) so the fleet covers a sudden drop immediately instead
        # of waiting for the PI. Reuses the proven settle (freezes the PI → no
        # double-count); skipped if a settle is already active or it is disabled.
        if (
            self._pv_drop_compensation
            and pv_drop_w > 0.0
            and self._zi_settle_ticks > 0
            and not self._settle_state.active
        ):
            self._settle_state = SettleState(
                ticks_remaining=self._zi_settle_ticks, feedforward_w=-pv_drop_w
            )
        # Smoothed non-controllable (cloud) battery charge. A dumb cloud battery
        # (Jackery) charges in short bursts (0↔~110 W, ~30 s); reacting tick-by-tick
        # made the cloud guards (no-feed / stop-cloud) chop the fleet discharge
        # (0↔300 W) even though the grid stayed fine. An EMA (~90 s) averages the
        # bursts to a stable value so the guards engage only on a *sustained* cloud
        # charge, not on each blip. Used by every cloud guard below.
        nc_charge_raw_w = sum(
            max(0.0, b.power_w)
            for b in snapshot.batteries
            if b.available and not b.stale and b.device_name not in self._controllable_battery_names
        )
        if self._nc_charge_smoothed_w is None:
            self._nc_charge_smoothed_w = nc_charge_raw_w
        else:
            self._nc_charge_smoothed_w += _NC_CHARGE_EMA_ALPHA * (
                nc_charge_raw_w - self._nc_charge_smoothed_w
            )
        nc_charge_w = self._nc_charge_smoothed_w
        # Hysteretic cloud-charging state. A near-full cloud battery charges in decaying
        # bursts, so the smoothed value crosses the threshold repeatedly; latching it
        # (engage above the hysteresis, release only after it stays below half for a
        # dwell) stops the cloud guards (no_charge_floor / no_feed) — and so the STREAM
        # setpoint — from flapping between charging and dumping its PV.
        if nc_charge_w > self._zi_hysteresis_w:
            self._nc_charging_latch = True
            self._nc_charging_release_ticks = 0
        elif self._nc_charging_latch:
            if nc_charge_w < self._zi_hysteresis_w * 0.5:
                self._nc_charging_release_ticks += 1
                if self._nc_charging_release_ticks >= _NC_CHARGING_RELEASE_DWELL_TICKS:
                    self._nc_charging_latch = False
            else:
                self._nc_charging_release_ticks = 0
        # Smoothed whole-fleet battery power for the time-to-full/empty estimates.
        total_battery_w = sum(b.power_w for b in snapshot.batteries if b.available)
        if self._battery_power_smoothed_w is None:
            self._battery_power_smoothed_w = total_battery_w
        else:
            self._battery_power_smoothed_w += _BATTERY_POWER_EMA_ALPHA * (
                total_battery_w - self._battery_power_smoothed_w
            )
        zi_correction_w = 0.0
        eq_bias_w = 0.0
        eq_discharge_floor_w: float | None = None
        nc_charge_offset_w = 0.0
        force_offset_w = 0.0
        cloud_relief_w = 0.0
        effective_setpoint_w = self._zi_setpoint_w
        zi_regulating = (
            self._zi_enabled and self._mode in (HemsMode.NORMAL, HemsMode.VACATION) and not red_prep
        )
        # Anti-yoyo: while a settle window is active (a big load was just dropped),
        # keep ZI "regulating" (so the target tracks the measured fleet) but freeze
        # the PI loop and inject only the one-shot feed-forward — the fleet is told
        # to discharge the lost load's worth less, instead of the loop slamming it.
        zi_settling = zi_regulating and self._settle_state.active
        if zi_settling:
            zi_correction_w, self._settle_state = advance_settle(self._settle_state)
            _LOGGER.debug(
                "ZI settle hold: feed-forward %.0fW, %d tick(s) left",
                zi_correction_w,
                self._settle_state.ticks_remaining,
            )
        elif zi_regulating:
            # Indirect SoC equaliser (cascaded): offer a surplus/deficit by biasing
            # the ZI setpoint, so the single ZI loop produces the extra fleet
            # discharge/charge. 0 when the equaliser is off. Requires ZI.
            # Deficit = the house needs more than the fleet provides. Detected on
            # the *natural* grid (grid - fleet), invariant to what the fleet does
            # (the raw grid sits at ~0 because the batteries cover the house).
            is_deficit = natural_grid_w > self._zi_hysteresis_w
            eq_bias_w = self._equaliser_bias(snapshot, grid_filtered_w, deficit=is_deficit)
            # In a deficit the offer steers the discharge share to converge SoC
            # (higher-SoC battery carries more): only let the fleet discharge MORE
            # when it is higher (offer >= 0), sparing the lower battery without
            # provoking grid import (no bidirectional mode -- offloading onto a cloud
            # battery could briefly import, which is never wanted).
            if is_deficit:
                eq_bias_w = max(0.0, eq_bias_w)
            if self._eq_tuner is not None and self._soc_equaliser is not None:
                # Damp the equaliser step cap if the offer is oscillating.
                self._soc_equaliser.set_max_step_w(self._eq_tuner.step(eq_bias_w))
            # Night cloud-relief (anti-round-trip): no PV but a higher-SoC fleet would let
            # a lower cloud battery discharge into it. Force the fleet to discharge to
            # cover the home (cloud rests), capped at the home load — never charging the
            # cloud. Reuses the same back-off/floor below (capacity = the home load here).
            cloud_relief_w = self._cloud_relief_w(snapshot, controllable_mppt_w)
            if cloud_relief_w > 0.0 and eq_bias_w <= 0.0:
                eq_bias_w = cloud_relief_w
            # SoC equaliser PV-routing: when the equaliser wants the fleet to
            # discharge (it is the higher-SoC side), let it output its OWN PV out past
            # the no-export point (down to -mppt) toward the lower-SoC cloud battery —
            # the battery is never drained (output <= solar input). A back-off shrinks
            # the allowance if the cloud doesn't absorb it (the grid keeps exporting),
            # so it can't keep dumping PV to the grid for nothing.
            # Dwell: re-evaluate the allowance only every _EQ_PV_RELAX_DWELL_TICKS, and
            # HOLD the floor in between, so the STREAM setpoint stays put long enough
            # for the slow (cloud) battery to react before we move it again. At the
            # re-evaluation, a grid deadband decides the step: shrink only on a real
            # export (cloud not absorbing), grow only with import headroom, hold when
            # balanced — so it settles instead of hunting.
            self._eq_relax_dwell += 1
            reevaluate = self._eq_relax_dwell >= _EQ_PV_RELAX_DWELL_TICKS
            if reevaluate:
                self._eq_relax_dwell = 0
                if self._eq_pv_relax_active and grid_filtered_w < -self._zi_hysteresis_w:
                    self._eq_pv_relax = max(0.0, self._eq_pv_relax - _EQ_PV_RELAX_DECAY)
                elif grid_filtered_w > self._zi_hysteresis_w:
                    self._eq_pv_relax = min(1.0, self._eq_pv_relax + _EQ_PV_RELAX_RECOVER)
            # Routing capacity = measured controllable PV + PV hidden by a full
            # battery's auto-curtailment (estimated from the peer inverter). The latter
            # lets the equaliser route a *full* STREAM's invisible PV: it commands the
            # discharge that un-curtails the array. ~0 unless an array is suppressed.
            # Discharge capacity the equaliser floor may use: measured PV + PV hidden by
            # a full battery (daytime routing), or the home load (night cloud-relief).
            eq_capacity_w = max(controllable_mppt_w + hidden_pv_w, cloud_relief_w)
            if eq_bias_w > 0.0 and eq_capacity_w > 0.0:
                if reevaluate or self._eq_floor_w is None:
                    self._eq_floor_w = -eq_capacity_w * self._eq_pv_relax
                # Hold the floor across the dwell; cap at the capacity so a falling
                # PV/peer-yield/home-load never turns it into a deeper battery drain.
                eq_discharge_floor_w = max(self._eq_floor_w, -eq_capacity_w)
            else:
                self._eq_floor_w = None
            self._eq_pv_relax_active = eq_discharge_floor_w is not None and self._eq_pv_relax > 0.01
            # Grid-only force-charge: raise the ZI target by the forced loads'
            # power so the battery doesn't discharge to feed them (the grid does).
            # The equaliser offer is NOT biased into the ZI setpoint anymore (it
            # could not force a discharge against local PV charging); it is applied
            # as a direct floor on the fleet target below (apply_equaliser_offer).
            force_offset_w = self._force_charge_grid_offset_w(snapshot)
            # Only feed the cloud guards while the (hysteretic) latch says the cloud is
            # charging, so a between-bursts dip can't drop the no_feed floor for a tick.
            nc_charge_offset_w = (
                self._noncontrollable_charge_offset_w(nc_charge_w, natural_grid_w, force_offset_w)
                if self._nc_charging_latch
                else 0.0
            )
            effective_setpoint_w = self._zi_setpoint_w + force_offset_w + nc_charge_offset_w
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
                    sp = effective_setpoint_w / 3.0
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
                    setpoint_w=effective_setpoint_w,
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
                        effective_setpoint_w,
                    )
            if self._zi_tuner is not None:
                # Damp the ZI gain when the correction oscillates (pumping).
                self._zi_controller.set_kp(self._zi_tuner.step(zi_correction_w))

        # Resolve a single aggregate target. When zero-injection regulates, it
        # owns the grid loop (target = current fleet power + PI delta); otherwise
        # the strategies' absolute target drives the fleet. Summing both is what
        # caused the tick-frequency limit cycle. See core/controllers/regulation.
        absolute_target_w = sum(
            t.preferred_power_w or 0.0 for t in result.decision.battery_targets.values()
        )
        # Active predictive control: nudge the fleet toward the planner setpoint,
        # but only in the tariff-beneficial direction (charge in cheap windows,
        # discharge in expensive ones). Inert with a flat tariff. The equaliser
        # itself acts via the ZI setpoint, not this power bias.
        steering_w = 0.0
        if self._predictive_control_enabled and self._plan is not None:
            base_target_w = (
                current_fleet_w + zi_correction_w if zi_regulating else absolute_target_w
            )
            ts = dt_util.as_local(snapshot.timestamp)
            steering_w = predictive_steering_w(
                base_target_w=base_target_w,
                planner_w=self._plan.first_setpoint_w,
                is_cheap=self._tariff.is_cheap_window(
                    ts, threshold=DEFAULT_COST_MIN_CHEAP_THRESHOLD
                ),
                is_expensive=self._tariff.is_expensive_window(
                    ts, threshold=DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD
                ),
            )
        # The hysteretic cloud-charging latch (computed above) feeds the no-charge floor
        # and the no-feed guard inside the clamp pipeline.
        # Whole aggregate-target clamp pipeline, extracted to a single pure function
        # (base target → equaliser offer → no-export → no-charge floor → no-feed /
        # stop-cloud → grid constraints). See core/controllers/regulation.
        gc = result.decision.grid_constraint
        # Near-full latch (hysteretic), shared by the no-charge-floor skip (charge
        # gently toward 100 %) and the PV curtailment (trim the excess to baseline).
        near_full = self._fleet_near_full(snapshot)
        # Charge-priority pull: when a low charge-priority battery (River 2) is below its
        # target and there is genuine PV surplus (natural export), force the fleet to charge
        # that surplus so the balancer routes it to the priority battery first — instead of
        # it being soaked by the big fleet in self-powered mode or spent on an equaliser
        # discharge. Zero otherwise (no incidence on setups without a priority battery).
        charge_priority_pull_w = 0.0
        if zi_regulating and natural_grid_w < -self._zi_hysteresis_w:
            soc_by_name = {b.device_name: b for b in snapshot.batteries}
            if any(
                d.battery is not None
                and d.battery.controllable
                and d.battery.charge_priority_target_soc_pct is not None
                and (bs := soc_by_name.get(d.name)) is not None
                and bs.available
                and bs.soc_pct < d.battery.charge_priority_target_soc_pct
                for d in self._devices
            ):
                charge_priority_pull_w = -natural_grid_w
        regulation_result = resolve_total_power(
            RegulationInputs(
                zi_regulating=zi_regulating,
                current_fleet_w=current_fleet_w,
                # Velocity-form base (mode-switch active-control batteries only):
                # integrate on the last *commanded* target, not the measured fleet
                # power, so the loop self-discovers the right setpoint even when the
                # actuator is decoupled from the measurement (a STREAM charging its own
                # PV on the DC side). natural_grid + the clamps still use the measured
                # current_fleet_w. None elsewhere → measured-form. See
                # resolve_fleet_target_w.
                loop_base_w=self._last_total_power_w if self._velocity_form_zi else None,
                zi_correction_w=zi_correction_w,
                absolute_target_w=absolute_target_w,
                steering_w=steering_w,
                eq_bias_w=eq_bias_w,
                eq_discharge_floor_w=eq_discharge_floor_w,
                charge_priority_pull_w=charge_priority_pull_w,
                fleet_near_full=near_full,
                grid_filtered_w=grid_filtered_w,
                controllable_mppt_w=controllable_mppt_w,
                nc_charge_offset_w=nc_charge_offset_w,
                noncontrollable_charging=self._nc_charging_latch,
                zi_hysteresis_w=self._zi_hysteresis_w,
                no_battery_export=self._no_battery_export,
                max_import_w=gc.max_import_w,
                max_export_w=gc.max_export_w,
            )
        )
        total_power_w = regulation_result.total_w

        # Vacation mode: cap charging at the vacation SoC ceiling to limit calendar
        # ageing while away. Discharge stays allowed; only the charge direction is
        # blocked once the controllable fleet reaches the ceiling.
        if self._mode is HemsMode.VACATION:
            avg_soc = self._controllable_avg_soc(snapshot)
            if avg_soc is not None and avg_soc >= self._vacation_soc_max_pct:
                total_power_w = min(total_power_w, 0.0)

        # Fleet direction-reversal dwell: a solar-first STREAM must physically switch mode
        # (self_powered <-> scheduled, slow over BLE) to cross charge<->discharge. Near
        # house == PV the sign flips every ~minute, thrashing the mode and overshooting on
        # each slow switch. Once the fleet commits to a direction, hold it (idle rather than
        # reverse) until the opposite demand persists past the dwell, so the mode is stable.
        # Evening reserve: once the stock is down to what the predictable peak needs,
        # stop discharging — the remainder is for tonight, not for this afternoon.
        # Only ever blocks a discharge; it never forces a charge.
        self._evening_reserve = self._evaluate_evening_reserve(snapshot)
        if self._evening_reserve.active and total_power_w < 0.0:
            stored_kwh = self._stored_above_min_kwh(snapshot)
            if stored_kwh <= self._evening_reserve.reserve_kwh:
                total_power_w = 0.0

        total_power_w = self._apply_reversal_dwell(total_power_w, snapshot.timestamp)

        # Slew-rate limit: cap how far the command may move per tick. Hard safety
        # belt against limit cycles given the battery's actuation lag.
        total_power_w = apply_slew_limit(total_power_w, self._last_total_power_w, self._max_ramp_w)

        # Dispatch loads using the unallocated surplus
        battery_states = {b.device_name: b for b in snapshot.batteries}
        # Cap each battery's charge allocation at what its setpoint entity will actually
        # accept (e.g. a STREAM charging_power_limit maxing at 1050 W). Commanding more is
        # silently clamped on write, so without this the velocity-form loop winds up past
        # the physical limit (unalloc never reflecting the clamp). Reading the entity max
        # into the allocation keeps unalloc — and the anti-windup below — honest.
        # Grid meter gone: rather than idling under a full sun, estimate the surplus
        # from measured PV minus the learned house load and charge a fraction of it.
        # Charge-only and heavily derated — see core/controllers/solar_fallback.py.
        self._solar_fallback = None
        if self._mode is HemsMode.DEGRADED:
            pv_fresh = any(m.available for m in snapshot.mppts)
            headroom = sum(n.deficit_kwh for n in self._battery_charge_needs(snapshot))
            self._solar_fallback = solar_only_target_w(
                enabled=self._solar_fallback_enabled,
                pv_available=pv_fresh,
                controllable_mppt_w=controllable_mppt_w,
                predicted_house_w=self.predicted_consumption_now_w,
                headroom_kwh=headroom,
                safety_factor=self._solar_fallback_safety,
            )
            total_power_w = self._solar_fallback.charge_w if self._solar_fallback.active else 0.0

        charge_caps: dict[str, float] = {}
        for device in self._devices:
            batt = device.battery
            if batt is None or not batt.controllable:
                continue
            cap = float(batt.max_charge_power_w)
            limit = self._active_control.charge_limit_w(device.name)
            if limit is not None:
                cap = min(cap, limit)
            charge_caps[device.name] = cap
        balancing_result = self._balancing.allocate(
            total_power_w=total_power_w,
            states=battery_states,
            now=snapshot.timestamp,
            charge_caps=charge_caps,
        )
        # Anti-windup for the velocity-form loop: it integrates on the last *commanded*
        # total, so if the balancer could not place all of it — the command exceeds the
        # batteries' charge/discharge *rate* (max_*_power), not their SoC — integrating
        # the un-achievable excess winds the loop up tick after tick. That inflates the
        # command, reports the fleet "saturated" (unallocated > 0) and curtails PV even
        # far from full. Store only what was actually allocatable as the loop base, so
        # the integrator can wind up at most to the physical rate.
        self._last_total_power_w = total_power_w - balancing_result.unallocated_w

        # Anticipatory curtailment: from the forecast and the sink budget (batteries —
        # cloud ones included — plus the commandable loads), decide whether the surplus
        # about to arrive has anywhere to go. Reuses this tick's charge_caps so the
        # controllable batteries' absorb ceiling matches what the balancer honours.
        anticipation = self._evaluate_anticipation(snapshot, charge_caps)
        self._anticipation = anticipation

        # PV curtailment: zero-injection's last resort when the batteries cannot
        # absorb the surplus. Computes a per-inverter output limit (W).
        pv_limits, pv_limit_total = self._compute_pv_limits(
            snapshot, total_power_w, balancing_result, grid_filtered_w, near_full, anticipation
        )
        # Expose the per-inverter applied limit for the per-MPPT diagnostic sensor.
        self._pv_limits_by_device = dict(pv_limits)

        explanation: Explanation = explain_tick(
            target_w=total_power_w,
            house_w=natural_grid_w,
            pv_w=controllable_mppt_w,
            binding=regulation_result.binding,
            # How far the clamp actually moved the target — a clamp that merely
            # grazed it decided nothing and must not be named as a cause.
            binding_moved_w=abs(regulation_result.total_w - regulation_result.base_w),
            degraded=self._mode is HemsMode.DEGRADED,
            grid_source=self._reader.grid_source,
            solar_fallback_active=bool(self._solar_fallback and self._solar_fallback.active),
            solar_fallback_w=(self._solar_fallback.charge_w if self._solar_fallback else 0.0),
            settle_active=self._settle_state.active,
            near_full=near_full,
            anticipating=anticipation.active,
        )
        self._explanation = explanation
        self._diagnostics = RegulationDiagnostics(
            grid_filtered_w=grid_filtered_w,
            zero_injection_correction_w=zi_correction_w,
            equaliser_offer_w=eq_bias_w,
            fleet_target_w=total_power_w,
            regulating=zi_regulating,
            pv_limit_w=pv_limit_total,
            natural_grid_w=natural_grid_w,
            regulation_binding=regulation_result.binding,
            pv_drop_w=pv_drop_w,
            eq_hidden_pv_w=hidden_pv_w,
            eq_pv_route_relax=self._eq_pv_relax,
            autotune_zi_kp=self._zi_tuner.value if self._zi_tuner else 0.0,
            autotune_equaliser_step_w=self._eq_tuner.value if self._eq_tuner else 0.0,
            loop_base_w=self._last_total_power_w,
            current_fleet_w=current_fleet_w,
            controllable_mppt_w=controllable_mppt_w,
            unallocated_w=balancing_result.unallocated_w,
            nc_charge_w=nc_charge_w,
            settle_active=self._settle_state.active,
            noncontrollable_charging=self._nc_charging_latch,
            sink_budget_w=anticipation.sink_budget_w,
            forecast_surplus_w=anticipation.forecast_surplus_w,
            anticipation_active=anticipation.active,
            preemptive_pv_limit_w=anticipation.preemptive_limit_w or 0.0,
            time_to_saturation_s=anticipation.time_to_saturation_s,
            grid_rejects=self._grid_rejects,
            grid_source=self._reader.grid_source,
            solar_fallback_active=bool(self._solar_fallback and self._solar_fallback.active),
            solar_fallback_w=(self._solar_fallback.charge_w if self._solar_fallback else 0.0),
            solar_fallback_reason=(
                self._solar_fallback.reason if self._solar_fallback else "disabled"
            ),
            explain_key=explanation.key,
            explain_text=explanation.text,
            evening_reserve_kwh=(
                self._evening_reserve.reserve_kwh if self._evening_reserve else 0.0
            ),
            evening_reserve_active=bool(self._evening_reserve and self._evening_reserve.active),
        )
        self._autotune_suggestions()

        # Snapshot the settle flag as it stood during regulation: the load dispatch
        # below can re-arm it, but the per-tick debug line (emitted after the writes,
        # so it can also report what was actually commanded to each battery) must show
        # the value that gated *this* tick's regulation.
        settle_active_dbg = self._settle_state.active

        # Surplus available to pilotable loads: the export we would still have
        # after the controllable fleet takes its allocated charge. Uses the
        # controllable fleet's current power (matching per_battery_w), not all
        # batteries, so the automatic battery's power does not leak in.
        load_states = {ls.name: ls for ls in snapshot.loads}
        surplus_w = max(
            0.0,
            -snapshot.grid_power_w - sum(balancing_result.per_battery_w.values()) + current_fleet_w,
        )
        dispatch_result = self._load_dispatch.dispatch(
            available_surplus_w=surplus_w,
            states=load_states,
            now=snapshot.timestamp,
        )
        commands = dispatch_result.commands
        # EV fast-charge assist: prefer an efficient (battery-assisted) charge rate
        # over a lossy slow charge, while the forecast can still refill the batteries.
        commands = self._apply_fast_charge(commands, snapshot, surplus_w)
        # Evening battery-priority shedding: force big interruptible loads off so
        # the remaining PV charges the batteries to SoC max. Always evaluated for
        # observability; only applied when load control is enabled.
        shed = self._evaluate_evening_shed(snapshot)
        self._evening_shed = shed
        if shed.active:
            commands = tuple(
                LoadCommand(load_name=c.load_name, on=False, rationale="evening_shed")
                if c.load_name in shed.shed_load_names
                else c
                for c in commands
            )
        # Off-peak-only loads: forbid running outside cheap tariff windows
        # (overridable by the deadline guarantee and manual force-charge below).
        commands = self._apply_off_peak(commands, snapshot)
        commands = self._apply_solar_only(commands, surplus_w)
        # Departure deadline has the final say: a grid-backed charge to meet the
        # required energy by the target time overrides shedding/fast-charge.
        commands = self._apply_deadline(commands, snapshot)
        # Manual "charge now" is the strongest override: force full power even
        # without surplus, regardless of shed / fast-charge / dispatch.
        commands = self._apply_force_charge(commands, snapshot)
        # Final safety net: keep grid import under the breaker, shedding the least
        # important loads first (overrides everything, including force-charge).
        commands = self._apply_overload_protection(commands, snapshot, grid_filtered_w)
        self._last_load_commands = {c.load_name: c for c in commands}
        if not self._dry_run:
            await self._load_publisher.apply(commands)
        self._update_load_settle(commands)

        self._publisher.publish(result, balancing_result=balancing_result)
        soc_by_device = {b.device_name: b.soc_pct for b in snapshot.batteries}
        await self._apply_active_control(balancing_result.per_battery_w, soc_by_device, pv_limits)

        # Structured per-tick record for the rolling debug history (dumped by the
        # capture_debug service). Kept unconditionally — the point is to have the data
        # already in memory when a glitch is noticed, without DEBUG logging on. Raw
        # numbers only (no formatting) so it round-trips cleanly to JSONL.
        self._tick_history.append(
            {
                "t": dt_util.as_local(snapshot.timestamp).isoformat(),
                "mode": self._mode.value,
                "zi_reg": zi_regulating,
                "settle": settle_active_dbg,
                "grid": round(grid_filtered_w, 1),
                "nat": round(natural_grid_w, 1),
                "setpt": round(effective_setpoint_w, 1),
                "force_off": round(force_offset_w, 1),
                "nc_off": round(nc_charge_offset_w, 1),
                "fleet": round(current_fleet_w, 1),
                "mppt": round(controllable_mppt_w, 1),
                "hidden_pv": round(hidden_pv_w, 1),
                "nc_charge": round(nc_charge_w, 1),
                "nc_latch": self._nc_charging_latch,
                "loop_base": round(self._last_total_power_w, 1),
                "zi": round(zi_correction_w, 1),
                "eq": round(eq_bias_w, 1),
                "relief": round(cloud_relief_w, 1),
                "eq_floor": (
                    round(eq_discharge_floor_w, 1) if eq_discharge_floor_w is not None else None
                ),
                "relax": round(self._eq_pv_relax, 3),
                "nearfull": near_full,
                "target": round(total_power_w, 1),
                "bind": regulation_result.binding,
                "unalloc": round(balancing_result.unallocated_w, 1),
                "pvlim": round(pv_limit_total, 1),
                "antic": anticipation.reason,
                "sink_budget": round(anticipation.sink_budget_w, 1),
                "fsurp": round(anticipation.forecast_surplus_w, 1),
                "prelim": (
                    round(anticipation.preemptive_limit_w, 1)
                    if anticipation.preemptive_limit_w is not None
                    else None
                ),
                "t2sat_s": (
                    round(anticipation.time_to_saturation_s)
                    if anticipation.time_to_saturation_s is not None
                    else None
                ),
                "per": {k: round(v, 1) for k, v in balancing_result.per_battery_w.items()},
                "wr": {
                    n: {"c": round(c, 1), "d": round(d, 1)}
                    for n, (c, d) in self._active_control.written_setpoints().items()
                },
                "batt": [
                    {
                        "name": b.device_name,
                        "soc": b.soc_pct,
                        "power": b.power_w,
                        "stale": b.stale,
                        "avail": b.available,
                        "stale_reason": b.stale_reason,
                        "stale_age_s": b.stale_age_s,
                    }
                    for b in snapshot.batteries
                ],
            }
        )

        # One comprehensive per-tick line for debugging the regulation (enable DEBUG on
        # custom_components.solarbalance). Everything that decides the fleet target and
        # the binding, correlated on the same tick — so a yoyo is explainable from logs
        # alone. Per battery: "soc%/power" (+charge/-discharge), "!" = stale, "x" =
        # unavailable. loop_base = velocity-form base for next tick (windup shows here).
        # wr = what was actually commanded to each battery this tick, "<charge>c<discharge>d"
        # (post SoC-cut, post discharge-mirror) — so the write is diagnosable in-line.
        if _LOGGER.isEnabledFor(logging.DEBUG):
            batt = {
                b.device_name: (
                    f"{b.soc_pct:.0f}%/{b.power_w:+.0f}"
                    + ("!" if b.stale else "")
                    + ("x" if not b.available else "")
                )
                for b in snapshot.batteries
            }
            wr = {
                n: f"{c:+.0f}c{d:+.0f}d"
                for n, (c, d) in self._active_control.written_setpoints().items()
            }
            _LOGGER.debug(
                "tick mode=%s zi_reg=%s settle=%s | grid=%.0f nat=%.0f setpt=%.0f "
                "(force=%.0f nc_off=%.0f) | fleet=%.0f mppt=%.0f hidden=%.0f batt=%s | "
                "nc=%.0f latch=%s | loop_base=%.0f zi=%.0f eq=%.0f relief=%.0f floor=%s "
                "relax=%.2f nearfull=%s | target=%.0f bind=%s | per=%s unalloc=%.0f "
                "pvlim=%.0f | antic=%s budget=%.0f fsurp=%.0f prelim=%s t2sat=%s | wr=%s",
                self._mode.value,
                zi_regulating,
                settle_active_dbg,
                grid_filtered_w,
                natural_grid_w,
                effective_setpoint_w,
                force_offset_w,
                nc_charge_offset_w,
                current_fleet_w,
                controllable_mppt_w,
                hidden_pv_w,
                batt,
                nc_charge_w,
                self._nc_charging_latch,
                self._last_total_power_w,
                zi_correction_w,
                eq_bias_w,
                cloud_relief_w,
                f"{eq_discharge_floor_w:.0f}" if eq_discharge_floor_w is not None else "-",
                self._eq_pv_relax,
                near_full,
                total_power_w,
                regulation_result.binding,
                {k: round(v) for k, v in balancing_result.per_battery_w.items()},
                balancing_result.unallocated_w,
                pv_limit_total,
                anticipation.reason,
                anticipation.sink_budget_w,
                anticipation.forecast_surplus_w,
                (
                    f"{anticipation.preemptive_limit_w:.0f}"
                    if anticipation.preemptive_limit_w is not None
                    else "-"
                ),
                (
                    f"{anticipation.time_to_saturation_s / 60.0:.0f}m"
                    if anticipation.time_to_saturation_s is not None
                    else "-"
                ),
                wr,
            )
        self._check_alerts(snapshot)
        self._fire_edge_events(snapshot)
        return snapshot

    # ------------------------------------------------------------------ helpers

    def _stored_above_min_kwh(self, snapshot: Snapshot) -> float:
        """Energy the controllable fleet still holds above its own SoC floor (kWh)."""
        total = 0.0
        soc_by_device = {b.device_name: b for b in snapshot.batteries}
        for device in self._devices:
            battery = device.battery
            if battery is None or device.name not in self._controllable_battery_names:
                continue
            state = soc_by_device.get(device.name)
            if state is None or not state.available:
                continue
            usable = self._usable_capacity_by_device.get(device.name, 0.0)
            total += max(0.0, (state.soc_pct - battery.soc_min_pct) / 100.0 * usable)
        return total

    def _evaluate_evening_reserve(self, snapshot: Snapshot) -> EveningReserve:
        """How much to keep for tonight, from the learned evening and the PV forecast."""
        local = dt_util.as_local(snapshot.timestamp)
        house = self._consumption_profile.by_hour(
            segment_for(local.weekday()), float(self._baseline_ema_w or 0.0)
        )
        learned = self._consumption_profile.learned_hours > 0
        pv_by_hour = self._forecast_pv_by_hour(snapshot)
        # The forecast is indexed from the current hour; the reserve reasons in
        # hour-of-day, so realign it before comparing the two.
        pv_by_day_hour: list[float] = [0.0] * 24
        for i, value in enumerate(pv_by_hour[:24]):
            pv_by_day_hour[(local.hour + i) % 24] = value
        capacity = sum(
            self._usable_capacity_by_device.get(d.name, 0.0)
            for d in self._devices
            if d.battery is not None and d.name in self._controllable_battery_names
        )
        soc_min = min(
            (
                float(d.battery.soc_min_pct)
                for d in self._devices
                if d.battery is not None and d.name in self._controllable_battery_names
            ),
            default=10.0,
        )
        return evening_reserve(
            enabled=self._evening_reserve_enabled,
            hour=local.hour,
            house_by_hour=house if learned else None,
            pv_by_hour=pv_by_day_hour if pv_by_hour else None,
            usable_capacity_kwh=capacity,
            soc_min_pct=soc_min,
            peak_start_hour=self._evening_peak_start_h,
            peak_end_hour=self._evening_peak_end_h,
            max_share=self._evening_reserve_max,
        )

    def _observe_appliances(self, snapshot: Snapshot) -> None:
        """Feed each observed appliance's power into the cycle learner (one float/tick).

        The program label is read only when a cycle closes: appliance integrations
        identify it well into the run, which is useless for predicting but exactly
        what is needed to file the finished cycle. A sibling ``*_program`` entity is
        used when it exists; otherwise the cycle is filed as unknown and everything
        still works.
        """
        if not self._appliance_entities:
            return
        now_s = snapshot.timestamp.timestamp()
        for entity_id in self._appliance_entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable", ""):
                continue
            try:
                power_w = float(state.state)
            except (TypeError, ValueError):
                continue
            name = self._appliance_name(entity_id)
            closed = self._appliance_cycles.observe(name, now_s, power_w)
            if closed is None:
                continue
            _LOGGER.debug("SolarBalance: appliance %s finished a cycle", name)
            # A finished cycle resembling none of the known ones is worth a word: a dead
            # heater or a blocked drain shows up here long before anywhere else. Silent
            # until there is enough history to judge — crying wolf on two samples would
            # just train the user to ignore it.
            score = self._appliance_cycles.anomaly_confidence(name, closed)
            if score is not None and score < _APPLIANCE_ANOMALY_CONFIDENCE:
                _LOGGER.warning(
                    "SolarBalance: %s ran an unusual cycle (%.0f min, %.2f kWh) — "
                    "it resembles none of the previous ones",
                    name,
                    closed.duration_s / 60.0,
                    closed.energy_kwh,
                )
                self.hass.bus.async_fire(
                    EVENT_APPLIANCE_ANOMALY,
                    {
                        "appliance": name,
                        "duration_min": round(closed.duration_s / 60.0),
                        "energy_kwh": round(closed.energy_kwh, 2),
                        "similarity": round(score, 2),
                    },
                )

    @staticmethod
    def _appliance_name(entity_id: str) -> str:
        """Readable appliance name from its power entity id."""
        base = entity_id.split(".", 1)[-1]
        for suffix in ("_current_power", "_power", "_puissance"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return base.replace("_", " ").strip() or entity_id

    @property
    def appliance_advice(self) -> list[dict[str, Any]]:
        """Per-appliance recording state, typical cycle, and its solar coverage.

        Every configured appliance is reported, including one that has not been
        learned yet: an empty list would otherwise be ambiguous between "nothing
        learned so far" and "nothing configured", which is exactly what you need to
        tell apart right after setting this up. Solar figures appear only once a
        cycle has actually been learned — an invented percentage would send someone
        to run a 2 kWh cycle off the grid.
        """
        if not self._appliance_entities:
            return []
        snap = self.data
        pv_by_hour = self._forecast_pv_by_hour(snap) if snap is not None else []
        local = dt_util.now()
        house_by_hour: list[float] = []
        if pv_by_hour:
            house = self._consumption_profile.by_hour(
                segment_for(local.weekday()), float(self._baseline_ema_w or 0.0)
            )
            # Align the house profile (hour-of-day) with the forecast (0 = current hour).
            house_by_hour = [house[(local.hour + i) % 24] for i in range(len(pv_by_hour))]
        now_s = snap.timestamp.timestamp() if snap is not None else 0.0

        out: list[dict[str, Any]] = []
        for entity_id in self._appliance_entities:
            name = self._appliance_name(entity_id)
            running = self._appliance_cycles.is_running(name)
            item: dict[str, Any] = {"name": name, "running": running, "samples": 0}
            elapsed = self._appliance_cycles.elapsed_s(name, now_s)
            if running and elapsed is not None:
                item["elapsed_min"] = round(elapsed / 60.0)
            summary = self._appliance_cycles.summary(name)
            if summary is not None:
                item.update(
                    {
                        "program": summary.program,
                        "samples": summary.samples,
                        "duration_min": round(summary.duration_s / 60.0),
                        "energy_kwh": round(summary.energy_kwh, 2),
                    }
                )
                if pv_by_hour:
                    now_share = estimate_solar_share(
                        summary.curve_w, summary.duration_s, 0, pv_by_hour, house_by_hour
                    )
                    item["solar_now_pct"] = round(now_share.solar_fraction * 100)
                    item["truncated"] = now_share.truncated
                    best = best_start(
                        summary.curve_w, summary.duration_s, pv_by_hour, house_by_hour
                    )
                    if best is not None:
                        item["best_hour"] = (local.hour + best.start_hour) % 24
                        item["best_pct"] = round(best.solar_fraction * 100)
            out.append(item)
        return out

    def _run_advisory_plan(self, snapshot: Snapshot) -> None:
        """Re-run the advisory predictive plan (observation only, no control).

        Maintains a slow background-load estimate and re-runs the DP planner on a
        coarse cadence. The plan is published via :attr:`advisory_plan` but never
        fed into the control loop. The PV series comes from the configured
        ``forecast`` block (hourly entities); without it, a flat estimate is used.
        """
        baseline = snapshot.baseline_consumption_w
        # Learn the (segment, hour) consumption profile every tick (even without a
        # planner — it is also a diagnostic and a seed for predictive control).
        local_now = dt_util.as_local(snapshot.timestamp)
        self._consumption_profile.observe(
            segment_for(local_now.weekday()), local_now.hour, max(0.0, baseline)
        )
        if self._scheduler is None:
            return
        self._baseline_ema_w = (
            baseline
            if self._baseline_ema_w is None
            else _BASELINE_EMA_ALPHA * baseline + (1 - _BASELINE_EMA_ALPHA) * self._baseline_ema_w
        )
        self._plan_tick += 1
        if self._plan is not None and self._plan_tick % _PLAN_EVERY_TICKS != 0:
            return
        # The planner models the controllable fleet as one aggregate battery, so
        # its starting SoC must be capacity-weighted (energy-true), not a plain
        # mean of percentages.
        avg_soc = self._controllable_avg_soc(snapshot)
        if avg_soc is None:
            return
        baseline_w = max(0.0, self._baseline_ema_w)
        start = dt_util.as_local(snapshot.timestamp)
        # Per-slot predicted consumption: each future slot uses its own day-segment
        # (weekday/weekend) and hour, falling back to the flat baseline when unlearned.
        consumption_by_slot = [
            self._consumption_profile.predict(
                segment_for((start + timedelta(hours=h)).weekday()),
                (start + timedelta(hours=h)).hour,
            )
            or baseline_w
            for h in range(24)
        ]
        slots = build_forecast_slots(
            start=start,
            n_hours=24,
            pv_w_by_hour=self._forecast_pv_by_hour(snapshot),
            baseline_w=baseline_w,
            tariff=self._tariff,
            consumption_by_slot=consumption_by_slot,
        )
        self._plan = self._scheduler.plan(slots, avg_soc)

    def _forecast_pv_by_hour(self, snapshot: Snapshot) -> list[float]:
        """Per-hour PV power (W) for the planner, from the configured forecast.

        Falls back to a flat current value when no ``forecast`` block is declared.
        """
        if self._forecast is not None:
            values: dict[str, float] = {}
            for entity_id in self._forecast.entities:
                state = self.hass.states.get(entity_id)
                if state is None or state.state in {"unavailable", "unknown", ""}:
                    continue
                with contextlib.suppress(ValueError, TypeError):
                    values[entity_id] = float(state.state)
            return build_pv_w_by_hour(self._forecast, values, horizon_h=24)
        # No manual forecast block: derive an hourly profile from a Solcast /
        # Forecast.Solar entity attribute when available, else a flat estimate.
        entity_profile = self._entity_pv_forecast_by_hour(snapshot.timestamp)
        if entity_profile:
            return entity_profile
        return [snapshot.pv_forecast_now_w] if snapshot.pv_forecast_now_w is not None else []

    def _make_tempo_color_provider(self, entity_id: str) -> Callable[[datetime], TempoColor]:
        """Build a Tempo colour provider reading the configured HA entity live."""

        def _provider(_dt: datetime) -> TempoColor:
            state = self.hass.states.get(entity_id)
            return parse_tempo_color(state.state if state else None)

        return _provider

    def _make_spot_price_provider(self, entity_id: str) -> Callable[[datetime], float | None]:
        """Build a spot-price provider reading the configured price sensor (€/kWh).

        Prefers the hourly ``raw_today`` / ``raw_tomorrow`` attributes (Nordpool /
        EPEX) so the price is resolved for the *requested* hour — this is what
        lets the planner arbitrage on a dynamic tariff. Falls back to the sensor's
        current state value when no hourly data matches.
        """

        def _hourly(state_attrs: Mapping[str, Any], dt: datetime) -> float | None:
            for key in ("raw_today", "raw_tomorrow"):
                raw = state_attrs.get(key)
                if not isinstance(raw, list):
                    continue
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    start = self._coerce_dt(item.get("start"))
                    end = self._coerce_dt(item.get("end"))
                    value = item.get("value")
                    if start is None or end is None or value is None:
                        continue
                    # Guard the comparison too: a naive/aware mismatch (some
                    # integrations expose tz-less timestamps) would otherwise
                    # raise and crash the update loop — skip the bad item instead.
                    with contextlib.suppress(ValueError, TypeError):
                        if start <= dt < end:
                            return float(value)
            return None

        def _provider(dt: datetime) -> float | None:
            state = self.hass.states.get(entity_id)
            if state is None:
                return None
            hourly = _hourly(state.attributes, dt)
            if hourly is not None:
                return hourly
            if state.state in {"unavailable", "unknown", ""}:
                return None
            try:
                return float(state.state)
            except (ValueError, TypeError):
                return None

        return _provider

    @staticmethod
    def _coerce_dt(value: object) -> datetime | None:
        """Best-effort parse of a forecast timestamp (datetime or ISO string)."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return dt_util.parse_datetime(value)
        return None

    def _entity_pv_forecast_by_hour(
        self, now: datetime, *, estimate: str = "pv_estimate"
    ) -> list[float]:
        """Hourly PV power (W, 24 h from the current hour) from the forecast entities.

        Reads the today (and optional tomorrow) entities and concatenates them.
        Supports Solcast (``detailedHourly`` / ``detailedForecast`` with
        ``pv_estimate`` in kW; ``estimate`` selects ``pv_estimate`` /
        ``pv_estimate10``) and Forecast.Solar (``watts`` dict, W — P50 only).
        Returns an empty list when nothing usable is found.
        """
        samples: list[tuple[datetime, float]] = []
        for entity_id in (self._pv_forecast_entity, self._pv_forecast_tomorrow_entity):
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            attrs = state.attributes
            found_list = False
            for key in ("detailedHourly", "detailedForecast", "forecast"):
                seq = attrs.get(key)
                if isinstance(seq, list) and seq:
                    found_list = True
                    for item in seq:
                        if not isinstance(item, dict):
                            continue
                        dt = self._coerce_dt(
                            item.get("period_start") or item.get("datetime") or item.get("time")
                        )
                        raw = item.get(estimate)
                        in_kw = raw is not None
                        if raw is None and estimate == "pv_estimate":
                            raw = item.get("power") or item.get("watts") or item.get("value")
                        if dt is None or raw is None:
                            continue
                        with contextlib.suppress(TypeError, ValueError):
                            w = float(raw) * (1000.0 if in_kw else 1.0)
                            samples.append((dt, max(0.0, w)))
                    break
            watts = attrs.get("watts")
            if not found_list and estimate == "pv_estimate" and isinstance(watts, dict):
                for key_dt, val in watts.items():
                    dt = self._coerce_dt(key_dt)
                    if dt is None:
                        continue
                    with contextlib.suppress(TypeError, ValueError):
                        samples.append((dt, max(0.0, float(val))))
        if not samples:
            return []
        hour0 = dt_util.as_local(now).replace(minute=0, second=0, microsecond=0)
        buckets = [0.0] * 24
        counts = [0] * 24
        for dt, w in samples:
            offset = int((dt_util.as_local(dt) - hour0).total_seconds() // 3600)
            if 0 <= offset < 24:
                buckets[offset] += w
                counts[offset] += 1
        return [buckets[i] / counts[i] if counts[i] else 0.0 for i in range(24)]

    @staticmethod
    def _integrate_remaining(
        pv_by_hour: list[float], frac_left: float, max_slots: int | None = None
    ) -> tuple[float, float]:
        """Sum a per-hour W profile into (kWh, hours), weighting the current hour.

        ``max_slots`` caps the horizon (slot 0 = current hour); pass the number
        of hourly slots left until local midnight so the integral covers only
        *today's* remaining production and never rolls into tomorrow's sun.
        """
        kwh = 0.0
        hours = 0.0
        for h, w in enumerate(pv_by_hour):
            if max_slots is not None and h >= max_slots:
                break
            if w <= 0.0:
                continue
            weight = frac_left if h == 0 else 1.0
            kwh += w * weight / 1000.0
            hours += weight
        return kwh, hours

    def _remaining_production(self, snapshot: Snapshot) -> tuple[float, float]:
        """Conservative remaining PV (kWh) and production hours from now.

        Uses the P50 profile for the hour count, but a *conservative* energy
        estimate for decisions: the populated Solcast P10 when available, else
        the P50 discounted by ``forecast_safety_factor`` — so shed / fast-charge
        decisions don't over-trust an optimistic forecast.
        """
        local = dt_util.as_local(snapshot.timestamp)
        frac_left = max(0.0, 1.0 - local.minute / 60.0)
        # Only count production left *today* (slots from now to local midnight);
        # tomorrow's sun cannot recover a battery drained tonight.
        slots_to_midnight = 24 - local.hour
        p50_kwh, hours = self._integrate_remaining(
            self._forecast_pv_by_hour(snapshot), frac_left, slots_to_midnight
        )
        p10 = self._entity_pv_forecast_by_hour(snapshot.timestamp, estimate="pv_estimate10")
        p10_kwh, _ = (
            self._integrate_remaining(p10, frac_left, slots_to_midnight) if p10 else (0.0, 0.0)
        )
        # Use P10 only when it is meaningfully populated (free Solcast often
        # returns all-zero P10); otherwise discount the P50.
        if p10_kwh >= 0.3 * p50_kwh and p10_kwh > 0.0:
            conservative_kwh = p10_kwh
        else:
            conservative_kwh = p50_kwh * self._forecast_safety_factor
        return conservative_kwh, hours

    def _battery_charge_needs(self, snapshot: Snapshot) -> list[BatteryChargeNeed]:
        """Charge headroom of each available controllable battery."""
        soc_by_device = {b.device_name: b for b in snapshot.batteries}
        needs: list[BatteryChargeNeed] = []
        for device in self._devices:
            battery = device.battery
            if battery is None or device.name not in self._controllable_battery_names:
                continue
            state = soc_by_device.get(device.name)
            if state is None or not state.available:
                continue
            usable = battery.usable_capacity_kwh or battery.capacity_kwh
            needs.append(
                BatteryChargeNeed(
                    soc_pct=state.soc_pct,
                    soc_max_pct=float(battery.soc_max_pct),
                    usable_capacity_kwh=float(usable),
                )
            )
        return needs

    def _collect_sinks(self, snapshot: Snapshot, charge_caps: Mapping[str, float]) -> list[Sink]:
        """Everything that can still absorb PV surplus, right now.

        Unlike :meth:`_battery_charge_needs` this counts the **non-controllable
        (cloud) batteries too**: we cannot command them, but we do know how much they
        can take, and a cloud battery still charging is a real sink — pre-curtailing
        as if it were not there would throw away solar it would have absorbed.

        Loads that are merely *observed* (an EV charging outside Home Assistant, the
        local AC load, the standby talon) are deliberately absent: their draw already
        sits inside the consumption forecast the budget is compared against, so
        listing them here would count them twice.
        """
        sinks: list[Sink] = []
        battery_states = {b.device_name: b for b in snapshot.batteries}
        for device in self._devices:
            battery = device.battery
            if battery is None:
                continue
            state = battery_states.get(device.name)
            if state is None or not state.available:
                continue
            if state.soc_pct >= float(battery.soc_max_pct):
                continue  # at its ceiling: no longer a sink
            headroom_kwh = (
                (float(battery.soc_max_pct) - state.soc_pct)
                / 100.0
                * battery.effective_usable_capacity_kwh
            )
            if device.name in self._controllable_battery_names:
                # The cap the balancer itself honours (entity max included).
                absorb_w = charge_caps.get(device.name, float(battery.max_charge_power_w))
                kind = SINK_CONTROLLABLE_BATTERY
            else:
                if state.stale:
                    continue  # cannot trust its SoC/power — don't bank on it absorbing
                absorb_w = float(
                    battery.ac_charge_limit_w
                    if battery.ac_charge_limit_w is not None
                    else battery.max_charge_power_w
                )
                kind = SINK_CLOUD_BATTERY
            sinks.append(
                Sink(
                    name=device.name,
                    kind=kind,
                    absorb_w=max(0.0, absorb_w),
                    headroom_kwh=max(0.0, headroom_kwh),
                )
            )

        load_states = {ls.name: ls for ls in snapshot.loads}
        for load in self._loads:
            state_l = load_states.get(load.name)
            if not load_eligible(load, state_l, snapshot.timestamp):
                continue
            drawn_w = state_l.actual_power_w if state_l is not None else 0.0
            spare_w = _load_nominal_w(load) - max(0.0, drawn_w)
            if spare_w <= 0.0:
                continue
            sinks.append(
                Sink(
                    name=load.name,
                    kind=SINK_LOAD,
                    absorb_w=spare_w,
                    # A load has no energy ceiling on an anticipation horizon: it can
                    # keep drawing its power for as long as it is on.
                    headroom_kwh=math.inf,
                )
            )
        return sinks

    def _forecast_pv_horizon_w(self, snapshot: Snapshot) -> float | None:
        """PV power (W) expected over the anticipation horizon, or None if unknown.

        Returns the worst (highest) of the hours the horizon spans: the brake exists
        for the surplus that is *about* to arrive, so straddling the top of the hour
        must not average the coming peak away.
        """
        pv_by_hour = self._forecast_pv_by_hour(snapshot)
        if not pv_by_hour:
            return None  # no forecast configured → stay purely reactive
        local_now = dt_util.as_local(snapshot.timestamp)
        horizon_h = self._anticipation_horizon_s / 3600.0
        spans_next_hour = local_now.minute / 60.0 + horizon_h > 1.0
        if spans_next_hour and len(pv_by_hour) > 1:
            return max(pv_by_hour[0], pv_by_hour[1])
        return pv_by_hour[0]

    def _evaluate_anticipation(
        self, snapshot: Snapshot, charge_caps: Mapping[str, float]
    ) -> AnticipationResult:
        """Decide whether to pre-curtail the array from the forecast."""
        budget = compute_sink_budget(
            self._collect_sinks(snapshot, charge_caps),
            horizon_s=self._anticipation_horizon_s,
        )
        pv_horizon_w = self._forecast_pv_horizon_w(snapshot) if self._anticipation_enabled else None
        consumption_w = self.predicted_consumption_now_w
        if consumption_w is None:
            consumption_w = max(0.0, self._baseline_ema_w or snapshot.baseline_consumption_w)
        # A running appliance is about to draw a known amount. The hour-of-day profile
        # averages it away across days that mostly had no cycle at all, so it badly
        # understates a live one. Fold in the predicted remaining draw. The appliance's
        # own (diluted) share of that average is then counted twice, which is deliberate:
        # over-stating consumption only ever makes the brake *less* eager, and keeping
        # solar is the safe side of that error.
        appliance_w = 0.0
        for entity_id in self._appliance_entities:
            predicted = self._appliance_cycles.predict_power_w(
                self._appliance_name(entity_id),
                snapshot.timestamp.timestamp(),
                _APPLIANCE_FORECAST_HORIZON_S,
            )
            if predicted:
                appliance_w += predicted
        consumption_w = max(0.0, consumption_w) + appliance_w

        net_charge_w = sum(b.power_w for b in snapshot.batteries if b.available and b.power_w > 0.0)
        return evaluate_anticipation(
            AnticipationInputs(
                enabled=self._anticipation_enabled,
                forecast_available=pv_horizon_w is not None,
                forecast_pv_w=pv_horizon_w or 0.0,
                predicted_consumption_w=max(0.0, consumption_w),
                budget=budget,
                current_net_charge_w=net_charge_w,
                margin_w=self._anticipation_margin_w,
            )
        )

    def _weighted_soc(self, snapshot: Snapshot, *, controllable_only: bool) -> float | None:
        """Capacity-weighted mean SoC (%) of available batteries, or None.

        Weighted by usable capacity so a small full pack and a large empty one do
        not average to a misleading 50 % (the energy-true figure). When
        ``controllable_only`` is set, the non-controllable fleet is excluded.
        """
        entries: list[tuple[float, float]] = []
        for b in snapshot.batteries:
            if not b.available:
                continue
            if controllable_only and b.device_name not in self._controllable_battery_names:
                continue
            cap = self._usable_capacity_by_device.get(b.device_name)
            if cap is not None:
                entries.append((b.soc_pct, cap))
        return capacity_weighted_soc_pct(entries)

    def weighted_battery_soc_pct(self) -> float | None:
        """Capacity-weighted SoC (%) across all available batteries, for the sensor."""
        snapshot = self.data
        if snapshot is None:
            return None
        return self._weighted_soc(snapshot, controllable_only=False)

    def remaining_battery_energy_kwh(self) -> float | None:
        """Stored usable energy (kWh) across available batteries, for the sensor.

        Energy currently held: sum(soc/100 * effective usable capacity).
        """
        snapshot = self.data
        if snapshot is None:
            return None
        entries: list[tuple[float, float]] = []
        for b in snapshot.batteries:
            if not b.available:
                continue
            cap = self._usable_capacity_by_device.get(b.device_name)
            if cap is not None:
                entries.append((b.soc_pct, cap))
        return round(stored_energy_kwh(entries), 2) if entries else None

    def usable_battery_window_kwh(self) -> float | None:
        """Exploitable energy window (kWh) across available batteries, for the sensor.

        sum((soc_max - soc_min)/100 * effective usable capacity) -- the span the
        HEMS may move between the configured floor and ceiling.
        """
        snapshot = self.data
        if snapshot is None:
            return None
        available = {b.device_name for b in snapshot.batteries if b.available}
        entries: list[tuple[float, float, float]] = []
        for device in self._devices:
            battery = device.battery
            if battery is None or device.name not in available:
                continue
            entries.append(
                (
                    float(battery.soc_min_pct),
                    float(battery.soc_max_pct),
                    battery.effective_usable_capacity_kwh,
                )
            )
        return round(usable_window_kwh(entries), 2) if entries else None

    def _controllable_avg_soc(self, snapshot: Snapshot) -> float | None:
        """Capacity-weighted SoC of the available controllable battery fleet, or None."""
        return self._weighted_soc(snapshot, controllable_only=True)

    def _apply_reversal_dwell(self, total_power_w: float, now: datetime) -> float:
        """Block a charge<->discharge reversal until the new direction persists past a dwell.

        A solar-first STREAM must physically switch strategy (self_powered <-> scheduled,
        slow over BLE) to cross between charging and discharging. Near ``house == PV`` the
        sign of the target flips every ~minute, thrashing the mode and overshooting on each
        slow switch. Once the fleet has committed to a direction, hold it — command 0
        (idle: let the box self-consume) rather than reverse — until the opposite demand has
        persisted longer than ``fleet_reversal_dwell_s``. A small band (the ZI hysteresis)
        keeps near-zero targets from counting as a direction. ``dwell <= 0`` disables it.
        """
        dwell = self._fleet_reversal_dwell_s
        if dwell <= 0:
            return total_power_w
        band = self._zi_hysteresis_w
        new_dir = 1 if total_power_w > band else (-1 if total_power_w < -band else 0)
        if new_dir == 0:
            return total_power_w  # near zero: no direction commitment, don't reset the clock
        if (
            self._fleet_dir != 0
            and new_dir != self._fleet_dir
            and self._fleet_dir_at is not None
            and (now - self._fleet_dir_at).total_seconds() < dwell
        ):
            return 0.0  # too soon to reverse the slow mode — idle instead of flipping
        if new_dir != self._fleet_dir:
            self._fleet_dir = new_dir
            self._fleet_dir_at = now
        return total_power_w

    def _cloud_relief_w(self, snapshot: Snapshot, controllable_mppt_w: float) -> float:
        """Discharge (W) a higher-SoC controllable fleet should provide to cover the home.

        Stops a lower-SoC cloud battery from discharging into the higher controllable
        fleet at night (a round-trip that drains the low battery into the high one). The
        fleet covers the home load instead, so the cloud rests. Capped at the home
        consumption — it covers the load, never charges the cloud (that would be a lossy
        battery-to-battery transfer). Zero unless the SoC equaliser is on, there is no PV
        (daytime is handled by PV-routing), an available + fresh cloud battery is
        meaningfully lower-SoC than the fleet, and there is a home load to cover.
        """
        if self._soc_equaliser is None or controllable_mppt_w > self._eq_min_pv_w:
            return 0.0
        fleet_soc = self._controllable_avg_soc(snapshot)
        cloud = [
            b
            for b in snapshot.batteries
            if b.available and not b.stale and b.device_name not in self._controllable_battery_names
        ]
        if fleet_soc is None or not cloud:
            return 0.0
        cloud_soc = sum(b.soc_pct for b in cloud) / len(cloud)
        if fleet_soc <= cloud_soc + _CLOUD_RELIEF_SOC_MARGIN_PCT:
            return 0.0
        pv_total = sum(m.power_w for m in snapshot.mppts if m.available)
        total_battery_w = sum(b.power_w for b in snapshot.batteries if b.available)
        # consumption = generation + grid_import - net battery charge.
        consumption_w = pv_total + snapshot.grid_power_w - total_battery_w
        return consumption_w if consumption_w > _CLOUD_RELIEF_MIN_W else 0.0

    def _command_load_powers(self, commands: tuple[LoadCommand, ...]) -> dict[str, float]:
        """Power (W) each load command applies — 0 when off, else commanded/nominal."""
        load_by_name = {ld.name: ld for ld in self._loads}
        powers: dict[str, float] = {}
        for c in commands:
            if not c.on:
                powers[c.load_name] = 0.0
            elif c.power_w is not None:
                powers[c.load_name] = float(c.power_w)
            else:
                ld = load_by_name.get(c.load_name)
                powers[c.load_name] = float(_load_nominal_w(ld)) if ld is not None else 0.0
        return powers

    def _update_load_settle(self, commands: tuple[LoadCommand, ...]) -> None:
        """Arm the anti-yoyo settle window when this tick dropped a big load.

        Only meaningful when load control actually drives the loads; otherwise
        the "drop" is hypothetical and must not feed-forward onto the batteries.
        """
        current = self._command_load_powers(commands)
        if self._load_publisher.enabled:
            armed = arm_settle(
                prev_loads=self._prev_load_power_w,
                current_loads=current,
                settle_ticks=self._zi_settle_ticks,
                min_drop_w=self._zi_settle_min_drop_w,
            )
            if armed is not None:
                self._settle_state = armed
                _LOGGER.debug("ZI settle armed: %.0fW load dropped", armed.feedforward_w)
        self._prev_load_power_w = current

    def _evaluate_evening_shed(self, snapshot: Snapshot) -> ShedDecision:
        """Assemble inputs and evaluate the evening battery-priority shedding."""
        remaining_pv_kwh, remaining_hours = self._remaining_production(snapshot)
        sheddable = [
            (load.name, float(_load_nominal_w(load)), int(load.priority))
            for load in self._loads
            if load.interruptible and load.name not in self._shed_exempt
        ]
        return evaluate_evening_shed(
            enabled=self._evening_shed_enabled,
            batteries=self._battery_charge_needs(snapshot),
            remaining_pv_kwh=remaining_pv_kwh,
            remaining_hours=remaining_hours,
            talon_w=self._baseline_est.talon_w,
            sheddable=sheddable,
            min_shed_power_w=self._evening_shed_min_power_w,
        )

    def _apply_fast_charge(
        self, commands: tuple[LoadCommand, ...], snapshot: Snapshot, surplus_w: float
    ) -> tuple[LoadCommand, ...]:
        """Override fast-charge EV commands to prefer an efficient (battery-assisted) rate."""
        # Loads the user exempted from shedding also bypass the fast-charge
        # inefficiency pause: charge them at the dispatched rate instead.
        ev_loads = [
            load for load in self._loads if load.fast_charge and load.name not in self._shed_exempt
        ]
        if not ev_loads:
            self._fast_charge = {}
            return commands

        remaining_pv_kwh, remaining_hours = self._remaining_production(snapshot)
        needs = self._battery_charge_needs(snapshot)
        avg_soc = self._controllable_avg_soc(snapshot)
        by_name = {c.load_name: c for c in commands}
        decisions: dict[str, FastChargeDecision] = {}
        for load in ev_loads:
            min_charge_w = float(load.min_charge_w or 0)
            max_charge_w = _load_nominal_w(load)
            if min_charge_w <= 0.0 or max_charge_w <= 0.0:
                continue  # mis-declared; leave dispatch untouched
            floor = (
                load.assist_floor_soc_pct
                if load.assist_floor_soc_pct is not None
                else self._backup_reserve_soc_pct
            )
            decision = evaluate_fast_charge(
                enabled=True,
                surplus_w=surplus_w,
                min_charge_w=min_charge_w,
                max_charge_w=max_charge_w,
                batteries=needs,
                avg_soc_pct=avg_soc,
                assist_floor_soc_pct=float(floor),
                remaining_pv_kwh=remaining_pv_kwh,
                remaining_hours=remaining_hours,
                talon_w=self._baseline_est.talon_w,
                pause_when_inefficient=load.pause_when_inefficient,
            )
            decisions[load.name] = decision
            if decision.override:
                by_name[load.name] = self._command_for_power(load, decision.target_w)
        self._fast_charge = decisions
        return tuple(by_name.values())

    @staticmethod
    def _command_for_power(load: Load, target_w: float) -> LoadCommand:
        """Build a LoadCommand realising ``target_w`` for a stepped/modulating load."""
        if target_w <= 0.0:
            return LoadCommand(
                load_name=load.name, on=False, step_level=0, rationale="fast_charge_pause"
            )
        if load.control_type is LoadControlType.STEPPED and load.steps:
            fitting = [s for s in load.steps if s.power_w <= target_w]
            step = (
                max(fitting, key=lambda s: s.power_w)
                if fitting
                else min(load.steps, key=lambda s: s.power_w)
            )
            return LoadCommand(
                load_name=load.name,
                on=True,
                step_level=step.level,
                power_w=float(step.power_w),
                rationale="fast_charge",
            )
        return LoadCommand(load_name=load.name, on=True, power_w=target_w, rationale="fast_charge")

    def _track_load_energy(self, snapshot: Snapshot, local_date: date) -> None:
        """Integrate energy delivered to each load today (for deadline tracking)."""
        if self._load_energy_day != local_date:
            self._load_energy_kwh = {}
            self._load_energy_day = local_date
            self._load_energy_last_ts = snapshot.timestamp
            return
        if self._load_energy_last_ts is None:
            self._load_energy_last_ts = snapshot.timestamp
            return
        dt_s = (snapshot.timestamp - self._load_energy_last_ts).total_seconds()
        self._load_energy_last_ts = snapshot.timestamp
        if dt_s <= 0.0 or dt_s > 1800.0:
            return
        dt_h = dt_s / 3600.0
        for ls in snapshot.loads:
            self._load_energy_kwh[ls.name] = (
                self._load_energy_kwh.get(ls.name, 0.0)
                + max(0.0, ls.actual_power_w) * dt_h / 1000.0
            )

    def _apply_deadline(
        self, commands: tuple[LoadCommand, ...], snapshot: Snapshot
    ) -> tuple[LoadCommand, ...]:
        """Force a grid-backed charge on deadline loads at risk of missing their target."""
        deadline_loads = [load for load in self._loads if load.deadline_constraint is not None]
        if not deadline_loads:
            self._ev_deadline = {}
            return commands
        local_now = dt_util.as_local(snapshot.timestamp)
        by_name = {c.load_name: c for c in commands}
        decisions: dict[str, DeadlineDecision] = {}
        for load in deadline_loads:
            dc = load.deadline_constraint
            assert dc is not None  # for type-checkers; filtered above
            decision = evaluate_deadline(
                now=local_now,
                before_time=dc.before_time,
                required_kwh=dc.kwh_required,
                delivered_kwh=self._load_energy_kwh.get(load.name, 0.0),
                max_charge_w=_load_nominal_w(load),
            )
            decisions[load.name] = decision
            if decision.force:
                by_name[load.name] = self._command_for_power(load, decision.target_w)
        self._ev_deadline = decisions
        return tuple(by_name.values())

    def _force_charge_grid_offset_w(self, snapshot: Snapshot) -> float:
        """Grid feed-forward for force-charged loads (grid-only, battery spared).

        Uses each forced load's *measured* power — which already flows through the
        grid meter — so raising the ZI target by it exactly cancels the load's
        grid contribution: the battery is neither discharged to feed it nor
        charged from the grid to "reach" it. Clamped to the load's nominal power
        as a safety bound, and ignores it until the load actually draws.
        """
        if not self._force_charge_req:
            return 0.0
        measured = {ls.name: ls.actual_power_w for ls in snapshot.loads}
        total = 0.0
        for load in self._loads:
            if load.name not in self._force_charge_req:
                continue
            draw = max(0.0, measured.get(load.name, 0.0))
            total += min(draw, float(_load_nominal_w(load)))
        return total

    def _noncontrollable_charge_offset_w(
        self, charge_w: float, natural_grid_w: float, force_offset_w: float
    ) -> float:
        """Don't drain the controllable fleet to feed a self-charging cloud battery.

        A non-controllable (e.g. cloud) battery -- one without active control --
        may decide to charge on its own. Its charge power flows through the grid
        meter, so the zero-injection loop would otherwise discharge the
        controllable fleet to cover it: a lossy battery-to-battery transfer, worst
        at night with no PV. Raising the ZI setpoint by that charge power makes the
        loop tolerate it instead, so the cloud battery draws from the grid (single
        conversion) rather than draining the fleet.

        ``natural_grid_w`` is the grid power *without* the controllable fleet's
        contribution (``grid_filtered - current_fleet``) -- the import the fleet
        would face if it did nothing. It must be used (not the raw grid) because in
        steady state the fleet already discharges to cover the cloud charge, so the
        raw grid reads ~0 and the guard would never engage (marginal stability).
        Capped at that natural import (after the force-charge feed-forward) so it
        never makes the fleet charge from the grid during a PV surplus.

        **Always applied** (no longer behind a setting): the offset is itself
        PV-safe -- it is 0 during a PV surplus (the natural grid exports, so the cap
        is 0) and so never blocks feeding the cloud battery from PV; it only engages
        on a real grid import (e.g. at night), where draining the fleet to feed a
        cloud battery is pure round-trip loss -- never something a user would want.
        """
        return noncontrollable_charge_offset_w(charge_w, natural_grid_w, force_offset_w)

    def _load_floor_w(self, load: Load) -> tuple[float, bool]:
        """Return (floor_w, reducible) for overload relief — how low a load may run."""
        if load.control_type is LoadControlType.MODULATING:
            return float(load.min_power_w or 0), True
        if load.control_type is LoadControlType.STEPPED and load.steps:
            return float(min(s.power_w for s in load.steps)), True
        return 0.0, False  # on/off: all-or-nothing

    def _apply_overload_protection(
        self, commands: tuple[LoadCommand, ...], snapshot: Snapshot, grid_filtered_w: float
    ) -> tuple[LoadCommand, ...]:
        """Reduce/cut the least important loads to keep grid import under the breaker."""
        if not (self._overload_protection_enabled and self._load_publisher.enabled):
            return commands
        if not self._subscribed_power_w:
            return commands
        safe_limit = self._subscribed_power_w * OVERLOAD_PROTECTION_FRACTION
        excess = grid_filtered_w - safe_limit
        if excess <= 0:
            return commands
        measured = {ls.name: ls.actual_power_w for ls in snapshot.loads}
        load_by_name = {ld.name: ld for ld in self._loads}
        candidates: list[SheddableLoad] = []
        for load in self._loads:
            current = max(0.0, measured.get(load.name, 0.0))
            if current <= 0:
                continue
            floor, reducible = self._load_floor_w(load)
            candidates.append(
                SheddableLoad(
                    name=load.name,
                    priority=load.priority,
                    current_w=current,
                    floor_w=floor,
                    interruptible=load.interruptible,
                    reducible=reducible,
                )
            )
        targets, uncovered = relieve_overload(candidates, excess)
        if not targets:
            return commands
        _LOGGER.warning(
            "Overload protection: grid %.0fW > %.0fW limit — reducing %s (%.0fW uncovered)",
            grid_filtered_w,
            safe_limit,
            ", ".join(targets),
            uncovered,
        )
        by_name = {c.load_name: c for c in commands}
        for name, target_w in targets.items():
            by_name[name] = self._command_for_power(load_by_name[name], target_w)
        return tuple(by_name.values())

    def _apply_off_peak(
        self, commands: tuple[LoadCommand, ...], snapshot: Snapshot
    ) -> tuple[LoadCommand, ...]:
        """Force off-peak-only loads off while the tariff window is not cheap."""
        if not self._off_peak_only:
            return commands
        ts = dt_util.as_local(snapshot.timestamp)
        if self._tariff.is_cheap_window(ts, threshold=DEFAULT_COST_MIN_CHEAP_THRESHOLD):
            return commands  # cheap window → loads may run normally
        return tuple(
            LoadCommand(load_name=c.load_name, on=False, rationale="off_peak_only")
            if c.load_name in self._off_peak_only
            else c
            for c in commands
        )

    def _apply_solar_only(
        self, commands: tuple[LoadCommand, ...], surplus_w: float
    ) -> tuple[LoadCommand, ...]:
        """Force solar-only loads off unless the PV surplus covers their power."""
        if not self._solar_only:
            return commands
        nominal = {ld.name: _load_nominal_w(ld) for ld in self._loads}
        return tuple(
            LoadCommand(load_name=c.load_name, on=False, rationale="solar_only")
            if c.load_name in self._solar_only and surplus_w < nominal.get(c.load_name, 0.0)
            else c
            for c in commands
        )

    def _apply_force_charge(
        self, commands: tuple[LoadCommand, ...], snapshot: Snapshot
    ) -> tuple[LoadCommand, ...]:
        """Force active 'charge now' loads to full power; clear finished requests."""
        if not self._force_charge_req:
            return commands
        now = snapshot.timestamp
        load_by_name = {ld.name: ld for ld in self._loads}
        by_name = {c.load_name: c for c in commands}
        for name, req in list(self._force_charge_req.items()):
            load = load_by_name.get(name)
            if load is None:
                self._force_charge_req.pop(name, None)
                continue
            delivered = self._load_energy_kwh.get(name, 0.0) - req.start_kwh
            done = (req.target_kwh is not None and delivered >= req.target_kwh) or (
                req.until is not None and now >= req.until
            )
            if done:
                self._force_charge_req.pop(name, None)
                continue
            by_name[name] = self._command_for_power(load, _load_nominal_w(load))
        return tuple(by_name.values())

    def _equaliser_bias(self, snapshot: Snapshot, grid_w: float, *, deficit: bool = False) -> float:
        """Grid-setpoint offer from the SoC equaliser (0 W when inactive).

        Positive offers a surplus (charges the automatic battery); negative offers
        a deficit (discharges it). Subtracted from the ZI setpoint by the caller.

        ``deficit`` (the house needs more than the fleet provides): the offer then
        steers the **discharge share** to converge SoC -- the higher-SoC battery
        carries more. The PV gate/cap is lifted because the extra discharge feeds
        the **house** (not the cloud battery), so it is not a lossy battery-to-
        battery transfer. In a surplus the PV cap stays (redistribute solar only).
        """
        if self._soc_equaliser is None:
            return 0.0
        controllable = [
            b for b in snapshot.batteries if b.device_name in self._controllable_battery_names
        ]
        uncontrollable = {
            b.device_name: b
            for b in snapshot.batteries
            if b.device_name not in self._controllable_battery_names
        }
        # PV produced by the controllable fleet itself (its own MPPTs): the equaliser
        # only redistributes this solar, never drains the fleet battery into the
        # automatic one (round-trip loss).
        available_pv_w = sum(
            m.power_w
            for m in snapshot.mppts
            if m.available and m.device_name in self._controllable_battery_names
        )
        # In a deficit, lift the PV gate/cap: the offer steers the discharge share
        # to feed the house (no lossy battery-to-battery transfer), bounded by the
        # equaliser's own max-offer. In a surplus, keep the real PV (beta.13).
        pv_for_offer = 1e9 if deficit else available_pv_w
        result = self._soc_equaliser.step(
            controllable_states=controllable,
            uncontrollable_states=uncontrollable,
            grid_w=grid_w,
            available_pv_w=pv_for_offer,
        )
        if not result.in_deadband:
            _LOGGER.debug(
                "SoC equaliser offer %.0fW (fleet target=%.1f%%, cadence=%d ticks, lag=%s)",
                result.grid_setpoint_bias_w,
                result.target_soc_pct,
                result.cadence_ticks,
                f"{result.lag_ticks:.1f} ticks" if result.lag_ticks is not None else "unmeasured",
            )
        return result.grid_setpoint_bias_w

    def _fleet_near_full(self, snapshot: Snapshot) -> bool:
        """Every controllable battery near its SoC ceiling, with release hysteresis.

        Engage at ``_CURTAIL_NEAR_FULL_MARGIN_PCT`` below the ceiling; once engaged,
        hold until the SoC drops a further ``_CURTAIL_NEAR_FULL_HYST_PCT`` — so a SoC
        sitting on the margin can't flip the state (and the PV limit + the no-charge
        floor) every tick. Drives both PV curtailment and the gentle near-full charge.
        """
        soc_max_by_device = {
            d.name: float(d.battery.soc_max_pct)
            for d in self._devices
            if d.battery is not None and d.battery.controllable
        }
        socs = [
            (b.soc_pct, soc_max_by_device[b.device_name])
            for b in snapshot.batteries
            if b.available and b.device_name in soc_max_by_device
        ]
        if not socs:
            self._curtail_near_full = False
            return False
        margin = _CURTAIL_NEAR_FULL_MARGIN_PCT + (
            _CURTAIL_NEAR_FULL_HYST_PCT if self._curtail_near_full else 0.0
        )
        self._curtail_near_full = all(soc >= soc_max - margin for soc, soc_max in socs)
        return self._curtail_near_full

    def _estimated_suppressed_pv_w(self, snapshot: Snapshot) -> float:
        """Estimate PV hidden by a full battery auto-curtailing its own array.

        Uses the yield (W produced per W installed) of the still-producing managed
        arrays — same sun, comparable panels (e.g. a STREAM + its side micro-inverter,
        both ~1 kWc).

        A STREAM whose battery is full stops showing solar production, so the SoC
        equaliser would see no PV to route. This estimates that invisible PV from the
        peer inverter so the equaliser CAN route it: commanding the full battery to
        discharge un-curtails its array, topping up a lower-SoC cloud battery. The
        estimate is the peer's production scaled by the installed-peak ratio, minus
        whatever the suppressed array still shows — so it is ~0 unless the array is
        genuinely curtailed, and it tapers on its own as the sun (peer yield) drops.
        """
        curtailable = {n for n, _ in self._curtailable_mppts}
        producing_w = producing_peak_w = 0.0
        suppressed_peak_w = suppressed_measured_w = 0.0
        for device in self._devices:
            mppt = device.mppt
            peak = float(mppt.peak_power_w) if mppt is not None else 0.0
            if peak <= 0.0:
                continue
            managed = device.name in self._controllable_battery_names or device.name in curtailable
            if not managed:
                continue
            measured = next(
                (m.power_w for m in snapshot.mppts if m.available and m.device_name == device.name),
                0.0,
            )
            soc = next(
                (
                    b.soc_pct
                    for b in snapshot.batteries
                    if b.available and b.device_name == device.name
                ),
                None,
            )
            near_full = (
                device.battery is not None
                and soc is not None
                and soc >= float(device.battery.soc_max_pct) - _CURTAIL_NEAR_FULL_MARGIN_PCT
            )
            if near_full:
                suppressed_peak_w += peak
                suppressed_measured_w += measured
            else:
                producing_w += measured
                producing_peak_w += peak
        if suppressed_peak_w <= 0.0 or producing_peak_w <= 0.0:
            return 0.0
        yield_ratio = max(0.0, producing_w / producing_peak_w)
        return max(0.0, yield_ratio * suppressed_peak_w - suppressed_measured_w)

    def _compute_pv_limits(
        self,
        snapshot: Snapshot,
        total_power_w: float,
        balancing_result: BalancingResult,
        grid_w: float,
        near_full: bool,
        anticipation: AnticipationResult | None = None,
    ) -> tuple[dict[str, float], float]:
        """Per-inverter PV output limits and the aggregate limit (W).

        Curtailment engages only when the batteries could not absorb the charge
        demand (saturated) and the grid is exporting past its setpoint. ``near_full``
        (the shared, hysteretic latch) treats a battery that can't absorb anymore as
        saturated even when the balancer still reports it allocated (charge tapering).

        That reactive path can only move once an export has been *measured*.
        ``anticipation`` adds a forecast-derived ceiling that lowers the limit before
        the surplus lands; the two compose as a ``min`` (both only ever lower it).
        """
        if self._curtailment is None:
            return {}, 0.0
        names = {n for n, _ in self._curtailable_mppts}
        pv_total = sum(m.power_w for m in snapshot.mppts if m.available and m.device_name in names)
        saturated = (total_power_w > 0.0 and balancing_result.unallocated_w > 1.0) or near_full
        result = self._curtailment.step(
            pv_total_w=pv_total,
            grid_w=grid_w,
            setpoint_w=self._zi_setpoint_w,
            batteries_saturated=saturated,
            preemptive_limit_w=(anticipation.preemptive_limit_w if anticipation else None),
        )
        limits = dict(distribute_pv_limit(result.limit_total_w, self._curtailable_mppts))
        return limits, result.limit_total_w

    async def _apply_active_control(
        self,
        per_battery_w: Mapping[str, float],
        soc_by_device: Mapping[str, float],
        pv_limits: Mapping[str, float],
    ) -> None:
        """Write setpoints to equipment when active control is enabled.

        Suspended in DEGRADED mode (stale entities): managed setpoints are reset
        to 0 W and PV curtailment is released once, then left untouched until the
        entities recover.
        """
        if self._dry_run:
            return  # observe-only: compute setpoints/sensors but never write
        if not (self._active_control_enabled and self._active_control.enabled):
            return
        fallback_active = self._solar_fallback is not None and self._solar_fallback.active
        if self._mode is HemsMode.DEGRADED and not fallback_active:
            if not self._active_control_suspended:
                await self._active_control.reset()
                if self._curtailment is not None:
                    self._curtailment.reset_to_unlimited()
                    await self._active_control.apply_pv_limits(
                        dict(
                            distribute_pv_limit(self._curtailment.limit_w, self._curtailable_mppts)
                        )
                    )
                self._active_control_suspended = True
            return
        self._active_control_suspended = False
        await self._active_control.apply(per_battery_w, soc_by_device)
        await self._active_control.apply_pv_limits(pv_limits)
        await self._active_control.apply_reserve(self._reserve_setpoints())
        # Periodically read back the power setpoints (PV limit + battery charge/discharge)
        # and re-assert any that didn't land (a wrong/intermittent entity, or a box that
        # reverted the value — a STREAM dropping its charging_power_limit). Not every tick.
        self._verify_tick += 1
        if self._verify_tick >= _VERIFY_WRITE_EVERY_TICKS:
            self._verify_tick = 0
            await self._active_control.verify_writes()

    def _reserve_setpoints(self) -> dict[str, float]:
        """Per-battery backup-reserve setpoint (%): storm target in storm, else backup reserve."""
        storm = self._mode is HemsMode.STORM
        out: dict[str, float] = {}
        for device in self._devices:
            battery = device.battery
            if battery is None or battery.reserve_soc_setpoint_entity is None:
                continue
            out[device.name] = (
                min(DEFAULT_STORM_TARGET_SOC_PCT, float(battery.soc_max_pct))
                if storm
                else self._backup_reserve_soc_pct
            )
        return out

    def _red_prep_active(self, snapshot: Snapshot) -> bool:
        """True during the Tempo off-peak window preceding a red day (pre-charge)."""
        if not self._tempo_red_prep_enabled or self._tempo_color_tomorrow_entity is None:
            return False
        if not isinstance(self._tariff, TempoTariff):
            return False
        if not self._tariff.is_off_peak(dt_util.as_local(snapshot.timestamp)):
            return False
        state = self.hass.states.get(self._tempo_color_tomorrow_entity)
        tomorrow = parse_tempo_color(state.state if state else None)
        return tomorrow is TempoColor.RED

    def _build_charge_result(
        self, snapshot: Snapshot, target_soc_pct: float, rationale: str
    ) -> ArbitrationResult:
        """Charge all batteries toward ``target_soc_pct`` (grid-backed); fall back when reached."""
        # Each battery can only reach its own soc_max, so "reached" must compare
        # against min(target, soc_max) — otherwise a target above soc_max (e.g. the
        # 100% default vs a 95% ceiling) is never satisfied and normal arbitration
        # is bypassed for the whole window.
        soc_max_by_device = {
            d.name: float(d.battery.soc_max_pct) for d in self._devices if d.battery is not None
        }
        available = [b for b in snapshot.batteries if b.available]
        if available and all(
            b.soc_pct >= min(target_soc_pct, soc_max_by_device.get(b.device_name, 100.0))
            for b in available
        ):
            return self._arbiter.run(snapshot)
        targets: dict[str, BatteryTarget] = {}
        for device in self._devices:
            if device.battery is None:
                continue
            bat = device.battery
            targets[device.name] = BatteryTarget(
                soc_min_pct=float(bat.soc_min_pct),
                soc_max_pct=min(target_soc_pct, float(bat.soc_max_pct)),
                preferred_power_w=float(bat.max_charge_power_w),
            )
        return ArbitrationResult(
            decision=Decision(battery_targets=targets, confidence=1.0, rationale=rationale),
            dominant_strategy="tempo_red_prep",
            per_strategy=(),
        )

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
            # Raise the discharge floor to the storm target: batteries we cannot
            # command to charge (discharge-only controllable, e.g. an all-in-one
            # station) are then never discharged and fill from PV surplus on their
            # own — the only lever we have to push them toward SoC max.
            storm_floor = min(DEFAULT_STORM_TARGET_SOC_PCT, float(bat.soc_max_pct))
            targets[device.name] = BatteryTarget(
                soc_min_pct=storm_floor,
                soc_max_pct=float(bat.soc_max_pct),
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
    # Display baseline is floored at ``max(0, talon - margin)`` and eases gently toward
    # that floor when the raw value dips below it (e.g. a stale cloud battery discharging
    # into the fleet: the grid sees it, its frozen power reading doesn't, so the raw
    # baseline reads negative). The margin is configurable (CONF_BASELINE_FLOOR_MARGIN_W);
    # the floor tracks the learned night standby (talon).
    _BASELINE_CONVERGE_ALPHA = 0.1  # gentle per-tick easing toward the floor
    _BASELINE_NOTIFICATION_ID = "solarbalance_baseline_negative"

    def _cloud_battery_stale(self, snapshot: Snapshot) -> bool:
        """True when a non-controllable (cloud) battery is stale (in timeout).

        Its real discharge still moves the grid while its frozen power reading does not,
        so the raw baseline reads implausibly low — this identifies that cause so the
        baseline floor and the alert can treat it as a known transient, not a mapping error.
        """
        return any(
            b.stale and b.device_name not in self._controllable_battery_names
            for b in snapshot.batteries
        )

    def _update_baseline_display(self, snapshot: Snapshot) -> None:
        """Compute the floored/eased display baseline (see _BASELINE_FLOOR_MARGIN_W).

        Tracks the raw baseline while it is plausible; when it dips below the floor
        (``max(0, talon - margin)``) it eases gently toward the floor instead of following
        a bogus negative (a stale cloud battery discharging into the fleet).
        """
        raw = snapshot.baseline_consumption_w
        talon = self.baseline_night_w
        floor = max(0.0, talon - self._baseline_floor_margin_w) if talon is not None else 0.0
        self._baseline_cloud_timeout = raw < floor and self._cloud_battery_stale(snapshot)
        if raw >= floor:
            self._baseline_display_w = raw  # plausible → track reality, no lag
            return
        base = self._baseline_display_w if self._baseline_display_w is not None else max(raw, floor)
        # Gentle convergence toward the floor (never snap to the bogus raw value).
        self._baseline_display_w = base + self._BASELINE_CONVERGE_ALPHA * (floor - base)

    @property
    def baseline_display_w(self) -> float:
        """Baseline for display/alerts — floored + eased (falls back to raw before first tick)."""
        if self._baseline_display_w is not None:
            return self._baseline_display_w
        snap = self.data
        return snap.baseline_consumption_w if snap is not None else 0.0

    @property
    def baseline_cloud_timeout(self) -> bool:
        """True when the current low baseline is attributed to a stale cloud battery."""
        return self._baseline_cloud_timeout

    def _check_baseline(self, snapshot: Snapshot) -> None:
        """Fire (or dismiss) a persistent notification when baseline is persistently negative.

        A negative baseline means the sign convention of at least one entity is wrong —
        UNLESS it is explained by a stale (timeout) cloud battery discharging into the
        fleet, which is a known transient (surfaced as info on the dashboard, not an alert).
        We wait for 3 consecutive ticks to avoid spurious alerts during transients.
        """
        from homeassistant.components.persistent_notification import async_create, async_dismiss

        genuine_negative = (
            snapshot.baseline_consumption_w < self._BASELINE_NEGATIVE_THRESHOLD_W
            and not self._cloud_battery_stale(snapshot)
        )
        if genuine_negative:
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

    def _autotune_suggestions(self) -> None:
        """Suggest a new configured value when a tuner keeps fighting the default.

        When the auto-tuner has had to adapt a gain repeatedly and settles away
        from the configured value, propose that operating point as a persistent
        notification (debounced; dismissed when it no longer suggests anything).
        """
        if not self._notifications_enabled:
            return
        from homeassistant.components.persistent_notification import async_create, async_dismiss

        for name, tuner, option, suggested_text in (
            ("zi_kp", self._zi_tuner, "zero_injection_kp", lambda v: f"{v:.2f}"),
            (
                "eq_step",
                self._eq_tuner,
                "soc_equaliser_probe_step_w",
                lambda v: f"{v:.0f} W",
            ),
        ):
            notif_id = f"solarbalance_autotune_{name}"
            suggested = tuner.suggested_value() if tuner is not None else None
            if suggested is None:
                if self._autotune_suggested.pop(name, None) is not None:
                    async_dismiss(self.hass, notif_id)
                continue
            last = self._autotune_suggested.get(name)
            if last is not None and abs(suggested - last) < 0.05 * max(abs(last), 1.0):
                continue  # already notified ~this value
            self._autotune_suggested[name] = suggested
            async_create(
                self.hass,
                f"L'auto-réglage ajuste souvent **{option}**. Valeur suggérée : "
                f"**{suggested_text(suggested)}**. Tu peux la définir dans "
                f"Configurer → Régulation (l'auto-réglage repartira de cette base).",
                title="SolarBalance — réglage suggéré",
                notification_id=notif_id,
            )

    def _fire_alert(self, notif_id: str, active: bool, *, title: str, message: str) -> None:
        """Create a persistent notification on the rising edge, dismiss on the falling edge."""
        from homeassistant.components.persistent_notification import async_create, async_dismiss

        was_sent = self._alerts_sent.get(notif_id, False)
        if active and not was_sent:
            async_create(self.hass, message, title=title, notification_id=notif_id)
            self._alerts_sent[notif_id] = True
        elif not active and was_sent:
            async_dismiss(self.hass, notif_id)
            self._alerts_sent[notif_id] = False

    # Grid import fraction of the subscription that raises / clears the overload alert.
    _OVERLOAD_ON = 0.90
    _OVERLOAD_OFF = 0.80

    def _fire_edge_events(self, snapshot: Snapshot) -> None:
        """Fire bus events on state transitions (for automations / blueprints / logbook)."""

        def edge(key: str, active: bool) -> str | None:
            """Return 'started'/'stopped' on a transition, else None."""
            was = self._event_edges.get(key, False)
            if active == was:
                return None
            self._event_edges[key] = active
            return "started" if active else "stopped"

        shed = self._evening_shed
        shed_active = bool(shed and shed.active)
        if (action := edge("shedding", shed_active)) is not None:
            self.hass.bus.async_fire(
                EVENT_SHEDDING,
                {"action": action, "loads": sorted(shed.shed_load_names) if shed else []},
            )

        red = self._mode is HemsMode.NORMAL and self._red_prep_active(snapshot)
        if (action := edge("tempo_red_day", red)) is not None:
            self.hass.bus.async_fire(EVENT_TEMPO_RED_DAY, {"action": action})

        fc_active = bool(self._force_charge_req)
        if (action := edge("force_charge", fc_active)) is not None:
            self.hass.bus.async_fire(
                EVENT_FORCE_CHARGE,
                {"action": action, "loads": sorted(self._force_charge_req)},
            )

    def _check_alerts(self, snapshot: Snapshot) -> None:
        """Edge-triggered persistent notifications for degraded / overload / shedding."""
        if not self._notifications_enabled:
            return

        self._fire_alert(
            "solarbalance_degraded",
            self.is_degraded,
            title="SolarBalance — Mode dégradé",
            message=(
                "Le HEMS est en **mode dégradé** : une ou plusieurs entités critiques "
                "sont indisponibles. Le pilotage est suspendu jusqu'au rétablissement."
            ),
        )

        sub = self._subscribed_power_w
        if sub:
            frac = max(0.0, snapshot.grid_power_w) / sub
            sent = self._alerts_sent.get("solarbalance_overload", False)
            # Hysteresis: trigger at 90 %, clear below 80 %.
            active = frac >= self._OVERLOAD_ON or (sent and frac >= self._OVERLOAD_OFF)
            self._fire_alert(
                "solarbalance_overload",
                active,
                title="SolarBalance — Puissance souscrite",
                message=(
                    f"Le soutirage réseau atteint **{snapshot.grid_power_w / 1000:.1f} kW** "
                    f"(souscrit {sub / 1000:.0f} kW). Risque de dépassement / disjonction."
                ),
            )

        shed = self._evening_shed
        self._fire_alert(
            "solarbalance_evening_shed",
            bool(shed and shed.active),
            title="SolarBalance — Délestage priorité batterie",
            message=(
                "Les gros consommateurs sont **délestés** pour laisser le solaire restant "
                "recharger les batteries (production prévue insuffisante pour faire les deux)."
            ),
        )

        # Static config mistakes only (degraded/overload/shed have their own alerts).
        issues = self._static_config_issues()
        self._fire_alert(
            "solarbalance_config",
            bool(issues),
            title="SolarBalance — Problème de configuration",
            message=(
                "Un ou plusieurs problèmes de configuration ont été détectés :\n\n"
                + "\n".join(f"- {issue}" for issue in issues)
            ),
        )

    @staticmethod
    def _collect_entity_ids(
        devices: list[Device], meters: list[Meter]
    ) -> tuple[list[str], list[str], list[str]]:
        """Return (critical_ids, monitored_ids, optional_ids) derived from config.

        Critical: PDL meter power entity — its staleness triggers DEGRADED.
        Monitored: battery SoC/power and non-PDL meter entities (should be present).
        Optional: MPPT/inverter entities — these legitimately go away when the device
        is off (a micro-inverter at night), so being unavailable is *expected*, not a
        fault; only a frozen value is flagged.
        """
        critical: list[str] = []
        monitored: list[str] = []
        optional: list[str] = []
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
                optional.extend(d.mppt.power_entities)
            if d.inverter:
                optional.append(d.inverter.ac_output_power_entity)
        return critical, monitored, optional

    @staticmethod
    def _build_arbiter(
        priorities: list[str],
        devices: list[Device],
        loads: list[Load],
        tariff: TariffConfig | None,
        subscribed_power_kva: int = 6,
        backup_reserve_soc_pct: float = DEFAULT_BACKUP_RESERVE_SOC_PCT,
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
                strat = cls(devices, loads, reserve_soc_pct=backup_reserve_soc_pct)
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
