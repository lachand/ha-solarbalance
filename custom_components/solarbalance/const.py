"""Constants for the SolarBalance integration."""

from typing import Final

DOMAIN: Final = "solarbalance"

# Configuration keys
CONF_PRIORITIES: Final = "priorities"
CONF_TICK_INTERVAL_S: Final = "tick_interval_s"
CONF_ZERO_INJECTION_ENABLED: Final = "zero_injection_enabled"
CONF_ZERO_INJECTION_SETPOINT_W: Final = "zero_injection_setpoint_w"
CONF_ZERO_INJECTION_HYSTERESIS_W: Final = "zero_injection_hysteresis_w"
CONF_ZERO_INJECTION_KP: Final = "zero_injection_kp"
CONF_PHASES: Final = "phases"
CONF_SUBSCRIBED_POWER_KVA: Final = "subscribed_power_kva"
CONF_PV_FORECAST_ENTITY: Final = "pv_forecast_entity"
CONF_WEATHER_WARNING_ENTITY: Final = "weather_warning_entity"
CONF_WEATHER_PHENOMENA: Final = "weather_phenomena"
CONF_WEATHER_MIN_LEVEL: Final = "weather_min_level"
CONF_SOC_EQUALISER_ENABLED: Final = "soc_equaliser_enabled"
CONF_SOC_EQUALISER_MAX_W: Final = "soc_equaliser_max_w"
CONF_SOC_EQUALISER_KP_W_PER_PCT: Final = "soc_equaliser_kp_w_per_pct"
CONF_SOC_EQUALISER_DEADBAND_PCT: Final = "soc_equaliser_deadband_pct"
CONF_SOC_EQUALISER_PROBE_STEP_W: Final = "soc_equaliser_probe_step_w"
CONF_SOC_EQUALISER_CADENCE_TICKS: Final = "soc_equaliser_cadence_ticks"
CONF_SOC_EQUALISER_ADAPTIVE_CADENCE: Final = "soc_equaliser_adaptive_cadence"
CONF_SOC_EQUALISER_MIN_PV_W: Final = "soc_equaliser_min_pv_w"
# Equaliser discharge-share in a deficit: bidirectional also reduces the fleet's
# discharge when it is LOWER than the cloud battery (shifts the deficit onto the
# cloud battery, may briefly import); unidirectional (default) only makes the
# fleet discharge MORE when it is higher (spares the lower battery, no provoked
# import).
CONF_ACTIVE_CONTROL_ENABLED: Final = "active_control_enabled"
CONF_MAX_RAMP_W: Final = "max_ramp_w"
CONF_GRID_FILTER_SAMPLES: Final = "grid_filter_samples"
CONF_ZI_SETTLE_TICKS: Final = "zi_settle_ticks"
CONF_ZI_SETTLE_MIN_DROP_W: Final = "zi_settle_min_drop_w"
CONF_CURTAILMENT_RAMP_W: Final = "curtailment_ramp_w"
CONF_CURTAILMENT_DEADBAND_W: Final = "curtailment_deadband_w"
CONF_CURTAILMENT_SETTLE_TICKS: Final = "curtailment_settle_ticks"
CONF_ANTICIPATORY_CURTAILMENT_ENABLED: Final = "anticipatory_curtailment_enabled"
CONF_ANTICIPATION_HORIZON_MIN: Final = "anticipation_horizon_min"
CONF_ANTICIPATION_MARGIN_W: Final = "anticipation_margin_w"
CONF_BACKUP_RESERVE_SOC_PCT: Final = "backup_reserve_soc_pct"
CONF_BASELINE_WINDOW_START_H: Final = "baseline_window_start_h"
CONF_BASELINE_WINDOW_END_H: Final = "baseline_window_end_h"
CONF_BASELINE_FLOOR_MARGIN_W: Final = "baseline_floor_margin_w"
CONF_FLEET_REVERSAL_DWELL_S: Final = "fleet_reversal_dwell_s"
CONF_LOAD_CONTROL_ENABLED: Final = "load_control_enabled"
CONF_EVENING_SHED_ENABLED: Final = "evening_shed_enabled"
CONF_EVENING_SHED_MIN_POWER_W: Final = "evening_shed_min_power_w"
CONF_IMPORT_PRICE: Final = "import_price"
CONF_EXPORT_PRICE: Final = "export_price"
# Tariff defined from the UI (alternative to the YAML tariff: block).
CONF_TARIFF_TYPE: Final = "tariff_type"  # flat | hc_hp | tempo | spot
CONF_HC_START: Final = "hc_start"  # HC window start (HH:MM), HP is the rest
CONF_HC_END: Final = "hc_end"
CONF_HC_PRICE: Final = "hc_price"
CONF_HP_PRICE: Final = "hp_price"
CONF_TEMPO_COLOR_ENTITY: Final = "tempo_color_entity"
CONF_TEMPO_COLOR_TOMORROW_ENTITY: Final = "tempo_color_tomorrow_entity"
CONF_SPOT_PRICE_ENTITY: Final = "spot_price_entity"
CONF_SPOT_MARKUP: Final = "spot_markup"
CONF_PREDICTIVE_CONTROL_ENABLED: Final = "predictive_control_enabled"
CONF_PV_FORECAST_TOMORROW_ENTITY: Final = "pv_forecast_tomorrow_entity"
CONF_FORECAST_SAFETY_FACTOR: Final = "forecast_safety_factor"
CONF_NOTIFICATIONS_ENABLED: Final = "notifications_enabled"
CONF_TEMPO_RED_PREP_ENABLED: Final = "tempo_red_prep_enabled"
CONF_TEMPO_RED_PREP_SOC_PCT: Final = "tempo_red_prep_soc_pct"
CONF_VACATION_SOC_MAX_PCT: Final = "vacation_soc_max_pct"

# Defaults
DEFAULT_TICK_INTERVAL_S: Final = 10
DEFAULT_ZERO_INJECTION_HYSTERESIS_W: Final = 50
# Proportional gain of the zero-injection loop. The integral is disabled (ki=0):
# the fleet-power recursion (target = measured fleet + correction) already
# integrates, so a second integrator would double-count and oscillate. Lower kp
# (0.3-0.4) for slow/cloud batteries with actuation lag. See SPECIFICATIONS §6.3.
DEFAULT_ZERO_INJECTION_KP: Final = 0.6
DEFAULT_PHASES: Final = 1
# Minimum Météo-France colour that triggers storm mode (jaune | orange | rouge).
DEFAULT_WEATHER_MIN_LEVEL: Final = "orange"
DEFAULT_BALANCING_ALPHA: Final = 0.6
DEFAULT_SOC_EQUALISER_MAX_W: Final = 1500
DEFAULT_SOC_EQUALISER_KP_W_PER_PCT: Final = 80.0
DEFAULT_SOC_EQUALISER_DEADBAND_PCT: Final = 2.0
# Upper bound on the steering-offer change per move (W). The step is proportional
# to the remaining gap (fast when far, gentle near equilibrium), capped here.
# See SPECIFICATIONS §6.6.
DEFAULT_SOC_EQUALISER_PROBE_STEP_W: Final = 600.0
# Min ticks between offer moves (slow outer loop). With adaptive cadence on, the
# effective value tracks the automatic battery's measured response lag.
DEFAULT_SOC_EQUALISER_CADENCE_TICKS: Final = 6
# Derive the cadence from the measured cloud-battery response lag (vs the floor).
DEFAULT_SOC_EQUALISER_ADAPTIVE_CADENCE: Final = True
# Min PV (W) from the controllable fleet's own MPPTs to run the equaliser: it only
# redistributes solar, never drains a battery into another (round-trip loss). Also
# caps the offer to this PV power.
DEFAULT_SOC_EQUALISER_MIN_PV_W: Final = 200.0
# Supervisory auto-tuner: damps the ZI kp and the equaliser step cap when they
# oscillate, restores them toward the configured values when calm. Never more
# aggressive than configured, hence safe on by default. Floors below.
AUTOTUNE_ZI_KP_MIN: Final = 0.2
AUTOTUNE_EQ_STEP_MIN_W: Final = 100.0
# Max change of the aggregate battery target per tick (W). Caps regulation
# swings; 0 disables the limit. See docs/SPECIFICATIONS.md §6.3.
DEFAULT_MAX_RAMP_W: Final = 800
# Rolling-median window (ticks) on the grid reading fed to the regulator.
# Rejects single-tick sensor glitches and brief load steps; 1 disables it.
DEFAULT_GRID_FILTER_SAMPLES: Final = 3
# Anti-yoyo: after the controller drops a big load, freeze the zero-injection PI
# for this many ticks and apply a one-shot feed-forward (reduce battery discharge
# by the dropped power) so the loop doesn't slam the batteries on the transient.
# 0 disables the behaviour.
DEFAULT_ZI_SETTLE_TICKS: Final = 2
# Only load drops at/above this power (W) arm the settle hold; smaller steps are
# left to the normal regulation + grid median filter.
DEFAULT_ZI_SETTLE_MIN_DROP_W: Final = 300
# PV curtailment anti-yoyo: max change of the inverter output limit per move (W),
# the export deadband around the setpoint, and the settle window (ticks held after
# each move so the inverter's dead-time + the meter catch up). Gradual + settle
# converge the limit on the balance instead of slamming between 0 and peak.
DEFAULT_CURTAILMENT_RAMP_W: Final = 150
DEFAULT_CURTAILMENT_DEADBAND_W: Final = 50
DEFAULT_CURTAILMENT_SETTLE_TICKS: Final = 3
# Anticipatory curtailment: how far ahead the sink budget is projected. Long enough
# that a nearly-full battery stops counting as a sink before it actually fills, short
# enough that the hourly forecast still describes the surplus about to arrive.
DEFAULT_ANTICIPATION_HORIZON_MIN: Final = 12
# Projected export must beat the sink budget by this much before pre-curtailing —
# keeps forecast noise from braking the array for nothing.
DEFAULT_ANTICIPATION_MARGIN_W: Final = 100
# Fraction (%) of the *estimated* surplus commanded by the solar-only fallback. Well
# under 100 so an underestimated house load eats the margin, not the grid.
DEFAULT_SOLAR_FALLBACK_SAFETY_PCT: Final = 70
DEFAULT_STORM_TARGET_SOC_PCT: Final = 95
DEFAULT_STORM_LEAD_TIME_H: Final = 6
DEFAULT_STORM_RELEASE_HYSTERESIS_H: Final = 1

# Night-window over which the standby baseline (talon) is averaged (local hours).
DEFAULT_BASELINE_WINDOW_START_H: Final = 2
DEFAULT_BASELINE_WINDOW_END_H: Final = 5
# Margin below the talon for the displayed-baseline floor: baseline is floored at
# max(0, talon - margin) so a stale cloud battery discharging into the fleet can't
# drive it negative. Lower = closer to the talon (more reactive floor).
DEFAULT_BASELINE_FLOOR_MARGIN_W: Final = 50
# Minimum seconds the controllable fleet must stay in one direction before it may
# reverse charge<->discharge. Sized above a solar-first box's mode-switch + BLE latency
# so it does not thrash self_powered<->scheduled near house == PV. 0 disables.
DEFAULT_FLEET_REVERSAL_DWELL_S: Final = 120

# Evening battery-priority shedding: only interruptible loads at or above this
# power are considered "big" and shed to let the PV charge the batteries.
DEFAULT_EVENING_SHED_MIN_POWER_W: Final = 500

# Flat fallback tariff (EUR/kWh) used for cost/savings accounting and the
# planner when no richer tariff is configured. User-editable in the options.
DEFAULT_IMPORT_PRICE: Final = 0.25
DEFAULT_EXPORT_PRICE: Final = 0.10
# UI tariff defaults (HC/HP common in France).
DEFAULT_TARIFF_TYPE: Final = "flat"
DEFAULT_HC_START: Final = "22:00"
DEFAULT_HC_END: Final = "06:00"
DEFAULT_HC_PRICE: Final = 0.20
DEFAULT_HP_PRICE: Final = 0.27
DEFAULT_SPOT_MARKUP: Final = 0.0

# Conservative discount applied to the P50 PV forecast for shed / fast-charge
# decisions (when a populated P10 is unavailable). 1.0 = trust P50 fully.
DEFAULT_FORECAST_SAFETY_FACTOR: Final = 0.85

# Target SoC to pre-charge controllable batteries to, during the off-peak window
# preceding a Tempo red day (grid-charged at the cheap HC price).
DEFAULT_TEMPO_RED_PREP_SOC_PCT: Final = 100.0

# Vacation mode: cap charging at this SoC to limit calendar ageing while away
# (self-consume from solar, never grid-charge).
DEFAULT_VACATION_SOC_MAX_PCT: Final = 60.0

# Strategy defaults — see SPECIFICATIONS §6.1 and docs/technical.md
DEFAULT_BACKUP_RESERVE_SOC_PCT: Final = 20.0
DEFAULT_COST_MIN_CHEAP_THRESHOLD: Final = 0.15  # €/kWh
DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD: Final = 0.25  # €/kWh

# Persistent store
STORE_KEY: Final = "solarbalance.state"
STORE_VERSION: Final = 1

# Dry-run: compute everything but never write to hardware (observe-only).
CONF_DRY_RUN: Final = "dry_run"
DEFAULT_DRY_RUN: Final = False

# Don't discharge the controllable fleet to feed a self-charging non-controllable
# (cloud) battery: raise the ZI setpoint by that battery's charge power so the
# loop tolerates it (it draws from the grid) instead of draining the fleet.

# Strict self-consumption: never let the controllable fleet discharge into the
# grid (cap the discharge so the grid never exports). Off by default so injection
# stays possible (e.g. to force-charge a non-controllable battery from the fleet).
CONF_NO_BATTERY_EXPORT: Final = "no_battery_export"
DEFAULT_NO_BATTERY_EXPORT: Final = False

# Stop a self-charging cloud battery by starving it: when a non-controllable
# battery charges and the fleet would otherwise feed it, force the fleet discharge
# to 0 (the house draws from the grid instead), removing the local output the cloud
# battery feeds on so it stops charging. Off by default (imports for the house
# while active; relies on the cloud battery reacting). Inert without a cloud battery.

# Local AC-load entities behind the controllable fleet (e.g. EcoFlow STREAM AC
# output sockets): served by the fleet but invisible to the grid meter. Declaring
# them lets SB exclude them from the fleet's grid-facing contribution so their
# on/off cycling does not disturb the zero-injection loop (and de-biases the
# derived home consumption).
CONF_LOCAL_AC_LOAD_ENTITIES: Final = "local_ac_load_entities"
# Power entities of appliances whose cycles are *observed* (washing machine,
# dishwasher…). Not controlled — only learned, to advise when to run them on solar.
CONF_APPLIANCE_POWER_ENTITIES: Final = "appliance_power_entities"
# Fallback grid-power sensor used when the PDL meter goes unavailable. Without it a
# meter dropout suspends regulation entirely (observed: 38 min lost at sunrise).
CONF_GRID_BACKUP_ENTITY: Final = "grid_backup_entity"
# Keep charging the estimated PV surplus when the grid meter is gone, instead of
# suspending everything. Commands hardware on an estimate, so opt-in.
CONF_SOLAR_FALLBACK_ENABLED: Final = "solar_fallback_enabled"
CONF_SOLAR_FALLBACK_SAFETY_PCT: Final = "solar_fallback_safety_pct"

# Adaptive volatility damper: smooth the grid signal fed to the regulation loop
# more when it is volatile (motor-type loads), so the battery tracks the slow
# average and the grid absorbs the fast swings (no yoyo). Off by default.
CONF_PV_DROP_COMPENSATION_ENABLED: Final = "pv_drop_compensation_enabled"
DEFAULT_PV_DROP_COMPENSATION_ENABLED: Final = False

# Staleness limit (s) for a non-controllable battery's data: beyond this its power
# is considered untrustworthy (e.g. a cloud battery lagging) and the power-based
# per-battery guards ignore it; the grid loop keeps regulating. 0 disables.
CONF_NONCONTROLLABLE_STALE_S: Final = "noncontrollable_stale_s"
DEFAULT_NONCONTROLLABLE_STALE_S: Final = 300

# Active grid-overload protection: shed/reduce loads before the breaker trips.
CONF_OVERLOAD_PROTECTION_ENABLED: Final = "overload_protection_enabled"
DEFAULT_OVERLOAD_PROTECTION_ENABLED: Final = False
# Act when projected import exceeds this fraction of the subscribed power.
OVERLOAD_PROTECTION_FRACTION: Final = 0.95

# Bus events (for automations / blueprints / logbook). Edge-triggered.
EVENT_MODE_CHANGED: Final = "solarbalance_mode_changed"
EVENT_SHEDDING: Final = "solarbalance_shedding"
EVENT_TEMPO_RED_DAY: Final = "solarbalance_tempo_red_day"
EVENT_FORCE_CHARGE: Final = "solarbalance_force_charge"
# A finished appliance cycle that resembles none of the known ones.
EVENT_APPLIANCE_ANOMALY: Final = "solarbalance_appliance_anomaly"
