# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-05-05

### Added

- **Core engine** — models, strategies (self_consumption, cost_min, backup, longevity, peak_shaving), controllers (balancing, zero_injection, load_dispatch), arbiter.
- **Tariff module** — generic multi-slot tariff (HC/HP factory, weekday filter, overnight-aware, separate import/export prices).
- **Adapters** — `EntityReader` (HA → Snapshot), `DecisionPublisher` (ArbitrationResult → HA attributes), `ForecastReader` (PV forecast + weather warning).
- **Watchdog & degraded mode (F13)** — `EntityWatchdog` tracks entity last-update age (default 5 min). PDL meter staleness auto-triggers `HemsMode.DEGRADED`; auto-recovers when entities return. New `binary_sensor.solarbalance_degraded` entity.
- **HA services (F12)** — `solarbalance.pause`, `solarbalance.resume`, `solarbalance.set_mode`, `solarbalance.force_charge`, `solarbalance.force_discharge`, `solarbalance.activate_storm_mode` — all registered at domain setup and callable from automations or Lovelace.
- **Force override** — `force_charge`/`force_discharge` enter `HemsMode.MANUAL_OVERRIDE`, build battery targets directly (bypass arbiter), auto-clear on target-SoC reached or deadline expiry.
- **YAML device/meter/load parsing** — voluptuous schemas in `yaml_loader.py`, parsed in `async_setup`.
- **Config flow + options flow** — tick interval, zero-injection settings, forecast entities, strategy priorities.
- **HA platform entities** — sensors (mode, dominant strategy, grid/PV/battery power, baseline consumption, per-battery setpoints), binary sensors (storm mode, weather warning, degraded), select (HEMS mode), numbers (ZI setpoint, ZI hysteresis), switch (ZI enable).
- **Lovelace dashboard (F11)** — updated `examples/lovelace/dashboard.yaml` covering power-flow, 24h PV forecast, tariff chart, arbitration log, all override buttons (pause, resume, force charge/discharge, storm mode), ZI settings.
- **Translations** — full English (`en.json`) and French (`fr.json`) for all entities and services.
- **Core unit tests** — 95 tests covering tariff, longevity, cost_min, load_dispatch, balancing, zero_injection, arbitrer, models (≥80% core coverage).

## [Unreleased]

### Added

- **`sensor.solarbalance_battery_soc_avg`** — SoC moyen de toutes les batteries disponibles (%).
- **`sensor.solarbalance_pv_energy_today`** — énergie PV totale du jour (somme des `daily_energy_entity` MPPT, kWh).
- **`sensor.solarbalance_grid_import_today`** — soutirage réseau du jour (depuis `daily_import_energy_entity` du compteur PDL, kWh).
- Propriétés `daily_pv_energy_kwh` et `daily_grid_import_kwh` sur le coordinator.
- **Notification baseline négative** — alerte persistante HA si `baseline_consumption_w < -100 W` pendant 3 cycles consécutifs (indique un mapping d'entité incorrect). Disparaît automatiquement quand la baseline revient positive.
- **Stratégie `revenue_max` implémentée** — décharge les batteries quand le prix d'export dépasse le prix d'import + prime configurable (`export_premium`, défaut 5 ct/kWh) ; charge quand le prix d'import est inférieur au seuil `cheap_import_threshold` (défaut 10 ct/kWh). 11 tests unitaires.
- **Storm mode `duration_h`** — le service `activate_storm_mode` accepte maintenant un champ `duration_h` (heures). Le coordinator quitte automatiquement le mode storm à l'expiry. Le storm déclenché par vigilance météo reste auto-géré (quitte quand la vigilance disparaît).

[1.0.0]: https://github.com/solarbalance/ha-solarbalance/releases/tag/v1.0.0
[Unreleased]: https://github.com/solarbalance/ha-solarbalance/commits/main
