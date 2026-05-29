"""Constants for the SolarBalance integration."""

from typing import Final

DOMAIN: Final = "solarbalance"

# Configuration keys
CONF_PRIORITIES: Final = "priorities"
CONF_TICK_INTERVAL_S: Final = "tick_interval_s"
CONF_ZERO_INJECTION_ENABLED: Final = "zero_injection_enabled"
CONF_ZERO_INJECTION_SETPOINT_W: Final = "zero_injection_setpoint_w"
CONF_ZERO_INJECTION_HYSTERESIS_W: Final = "zero_injection_hysteresis_w"
CONF_PHASES: Final = "phases"
CONF_SUBSCRIBED_POWER_KVA: Final = "subscribed_power_kva"
CONF_PV_FORECAST_ENTITY: Final = "pv_forecast_entity"
CONF_WEATHER_WARNING_ENTITY: Final = "weather_warning_entity"

# Defaults
DEFAULT_TICK_INTERVAL_S: Final = 10
DEFAULT_ZERO_INJECTION_HYSTERESIS_W: Final = 50
DEFAULT_PHASES: Final = 1
DEFAULT_BALANCING_ALPHA: Final = 0.6
DEFAULT_STORM_TARGET_SOC_PCT: Final = 95
DEFAULT_STORM_LEAD_TIME_H: Final = 6
DEFAULT_STORM_RELEASE_HYSTERESIS_H: Final = 1

# Strategy defaults — see SPECIFICATIONS §6.1 and docs/technical.md
DEFAULT_BACKUP_RESERVE_SOC_PCT: Final = 30.0
DEFAULT_COST_MIN_CHEAP_THRESHOLD: Final = 0.15   # €/kWh
DEFAULT_COST_MIN_EXPENSIVE_THRESHOLD: Final = 0.25  # €/kWh

# Persistent store
STORE_KEY: Final = "solarbalance.state"
STORE_VERSION: Final = 1
