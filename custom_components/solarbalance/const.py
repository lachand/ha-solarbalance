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
CONF_SOC_EQUALISER_ENABLED: Final = "soc_equaliser_enabled"
CONF_SOC_EQUALISER_MAX_W: Final = "soc_equaliser_max_w"
CONF_SOC_EQUALISER_KP_W_PER_PCT: Final = "soc_equaliser_kp_w_per_pct"
CONF_SOC_EQUALISER_DEADBAND_PCT: Final = "soc_equaliser_deadband_pct"
CONF_SOC_EQUALISER_PROBE_STEP_W: Final = "soc_equaliser_probe_step_w"
CONF_ACTIVE_CONTROL_ENABLED: Final = "active_control_enabled"
CONF_MAX_RAMP_W: Final = "max_ramp_w"
CONF_GRID_FILTER_SAMPLES: Final = "grid_filter_samples"
CONF_ZI_SETTLE_TICKS: Final = "zi_settle_ticks"
CONF_ZI_SETTLE_MIN_DROP_W: Final = "zi_settle_min_drop_w"
CONF_BACKUP_RESERVE_SOC_PCT: Final = "backup_reserve_soc_pct"
CONF_BASELINE_WINDOW_START_H: Final = "baseline_window_start_h"
CONF_BASELINE_WINDOW_END_H: Final = "baseline_window_end_h"
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
# (0.3–0.4) for slow/cloud batteries with actuation lag. See SPECIFICATIONS §6.3.
DEFAULT_ZERO_INJECTION_KP: Final = 0.6
DEFAULT_PHASES: Final = 1
DEFAULT_BALANCING_ALPHA: Final = 0.6
DEFAULT_SOC_EQUALISER_MAX_W: Final = 1500
DEFAULT_SOC_EQUALISER_KP_W_PER_PCT: Final = 80.0
DEFAULT_SOC_EQUALISER_DEADBAND_PCT: Final = 2.0
# Initial steering step (W); grows geometrically per tick while the automatic
# battery follows, capped by its AC absorption capacity. See SPECIFICATIONS §6.6.
DEFAULT_SOC_EQUALISER_PROBE_STEP_W: Final = 150.0
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
DEFAULT_STORM_TARGET_SOC_PCT: Final = 95
DEFAULT_STORM_LEAD_TIME_H: Final = 6
DEFAULT_STORM_RELEASE_HYSTERESIS_H: Final = 1

# Night-window over which the standby baseline (talon) is averaged (local hours).
DEFAULT_BASELINE_WINDOW_START_H: Final = 2
DEFAULT_BASELINE_WINDOW_END_H: Final = 5

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
DEFAULT_COST_MIN_CHEAP_THRESHOLD: Final = 0.15   # €/kWh
DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD: Final = 0.25  # €/kWh

# Persistent store
STORE_KEY: Final = "solarbalance.state"
STORE_VERSION: Final = 1
