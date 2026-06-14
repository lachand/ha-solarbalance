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

## [1.1.0] — 2026-05-10

### Added

- **`sensor.solarbalance_battery_soc_avg`** — SoC moyen de toutes les batteries disponibles (%).
- **`sensor.solarbalance_pv_energy_today`** — énergie PV totale du jour (somme des `daily_energy_entity` MPPT, kWh).
- **`sensor.solarbalance_grid_import_today`** — soutirage réseau du jour (depuis `daily_import_energy_entity` du compteur PDL, kWh).
- Propriétés `daily_pv_energy_kwh` et `daily_grid_import_kwh` sur le coordinator.
- **Notification baseline négative** — alerte persistante HA si `baseline_consumption_w < -100 W` pendant 3 cycles consécutifs (indique un mapping d'entité incorrect). Disparaît automatiquement quand la baseline revient positive.
- **Stratégie `revenue_max` implémentée** — décharge les batteries quand le prix d'export dépasse le prix d'import + prime configurable (`export_premium`, défaut 5 ct/kWh) ; charge quand le prix d'import est inférieur au seuil `cheap_import_threshold` (défaut 10 ct/kWh). 11 tests unitaires.
- **Storm mode `duration_h`** — le service `activate_storm_mode` accepte maintenant un champ `duration_h` (heures). Le coordinator quitte automatiquement le mode storm à l'expiry. Le storm déclenché par vigilance météo reste auto-géré (quitte quand la vigilance disparaît).
- **Anti-court-cycle** (`min_dwell_s=60 s`) — `BalancingController` bloque l'inversion de direction d'une batterie pendant 60 secondes après un changement. Évite les oscillations charge/décharge sur une fluctuation réseau. 5 nouveaux tests unitaires.
- **Exemples YAML** — `examples/config/ecoflow_stream.yaml` (EcoFlow STREAM Ultra 2 + STREAM Tiny, triphasé Shelly 3EM) et `examples/config/jackery.yaml` (Jackery HomePower 2000 Ultra, monophasé Shelly 1PM).
- **Tests d'intégration** — `tests/integration/test_config_flow.py` (création entry, abort single_instance) et `tests/integration/test_coordinator.py` (setup, mode par défaut, unload). 5 nouveaux tests d'intégration HA.

## [Unreleased]

## [1.3.1] — 2026-06-14

### Added

- **Reconfiguration des appareils dans l'UI** — chaque subentry (batterie, batterie+onduleur, onduleur, consommateur, compteur) est désormais **éditable** via le bouton ✏️ de l'intégration (étape `reconfigure`), avec ses valeurs pré-remplies. Avant, seul l'ajout était possible.

### Fixed

- **Charge rapide EV : récupérabilité bornée à aujourd'hui** — le gate de récupérabilité intégrait 24 h glissantes, donc le soir il comptait le soleil de **demain** (ex. `pv_recovery_kwh: 11.13` au lieu de ~0,3 kWh restant) et autorisait à tort la batterie à assister la voiture alors qu'elle ne pourrait pas se recharger. L'intégration s'arrête maintenant à minuit local, comme la tuile « PV restant ».

## [1.3.0] — 2026-06-14

### Added

- **Configuration des appareils dans l'UI (config subentries)** — ajout via « + Ajouter » de l'intégration, sans YAML ni redémarrage : types **Batterie**, **Batterie + onduleur**, **Onduleur / MPPT**, **Consommateur** (on/off, stepped, modulating) et **Compteur** (PDL/PV/conso). Listes déroulantes d'entités filtrées par domaine + infobulles par champ. Validé/construit par les mêmes builders que le YAML.
- **Migration YAML → UI** — au premier démarrage, les `devices`/`meters`/`loads` du YAML sont convertis en subentries éditables ; les subentries deviennent ensuite la source de référence (remplacement du YAML).
- **Vue « Journée »** du panneau — sélecteur 1 h / 6 h / 24 h / **Jour** (minuit → minuit), avec la prévision PV jusqu'à la fin de journée.
- **Production PV restante** — `sensor.solarbalance_pv_remaining_today` (énergie prévue jusqu'à minuit) + tuile « PV restant » dans le panneau.

### Fixed

- **Fenêtres tarifaires en heure locale** — le tick passait `snapshot.timestamp` (UTC) au tarif, qui compare l'heure locale ; HC/HP, Tempo, cheap/expensive, pré-charge jour rouge et le coût étaient décalés de l'offset UTC. Conversion en heure locale à tous les sites d'appel.
- **Talon persistant au reload** — flush du Store au déchargement de l'intégration (le talon devenait indisponible après un rechargement).
- **`reset()` arrête tous les loads** — il ne coupait que les loads on/off ; les loads stepped (EV) / modulating restaient actifs après une pause/suspension.
- **Pré-charge Tempo** — comparaison « cible atteinte » contre `min(cible, soc_max)` (une batterie plafonnée à 95 % restait sinon en charge réseau toute la fenêtre HC).
- **Tarif spot** — comparaison horaire robuste aux horodatages sans fuseau (évite un plantage de la boucle).
- **Résumé du plan (panneau)** — plages trop courtes d'un créneau (« 02h–04h » → « 02h–05h »).

## [1.2.0] — 2026-06-14

### Added

- **Pilotage actif des batteries & onduleurs** — l'`ActiveControlPublisher` écrit réellement les consignes de charge/décharge/mode et la limite de sortie PV (curtailment) ; bridage micro-onduleur quand les batteries sont pleines.
- **Contrôle des consommateurs** — `LoadPublisher` applique le dispatch aux switches/number réels (`load_control_enabled`). Loads `on_off` / `stepped` (ampérage EV) / `modulating`, un `switch_entity` peut couper un load stepped.
- **Charge rapide EV assistée** (`fast_charge`) — plancher de rendement + assistance batterie bornée par la récupérabilité PV (P10/P50 + talon), pause plutôt que charge lente.
- **Échéance de départ EV** (`deadline_constraint`) — garantie d'énergie par une heure cible, charge réseau forcée en dernier recours (prioritaire sur shed/fast-charge).
- **Délestage fin de journée** — coupe les gros consommateurs pour charger les batteries au SoC max, calcul énergétique auto-temporisé (prévision restante − talon).
- **Contrôle prédictif actif** (`predictive_control_enabled`) — le planner pilote les batteries dans la direction tarifaire (charge HC, décharge HP) ; inerte en tarif plat.
- **Tarifs** — bloc YAML `tariff:` et **config UI** (flat / HC-HP / Tempo / spot) ; **pré-charge avant jour rouge Tempo** ; prix **spot horaires** (Nordpool/EPEX `raw_today`/`raw_tomorrow`) pour l'arbitrage.
- **Coûts & économies €** — coût réseau net, revenu d'injection, import évité, par jour ; tuiles panneau.
- **Énergie** — compteur consommation totale, **recalcul depuis le recorder au démarrage** (couvre les coupures), historique journalier 30 j.
- **Talon de consommation** — estimation sur fenêtre nuit calme, persistée.
- **Mode tempête** — relève le plancher de décharge + écrit la réserve device (`reserve_soc_setpoint_entity`) pour remplir les batteries non pilotables en charge.
- **Mode vacances réel** — plafond de charge bas (longévité), jamais de charge réseau.
- **Prévision PV** — lecture Solcast (`detailedHourly`) / Forecast.Solar (`watts`), entité demain, alimente planner/shed/fast-charge.
- **Santé batterie** — capteurs Cycles et SoH estimé par chimie.
- **Diagnostic** — `binary_sensor.config_health` (signe inversé, prévision vide, tarif en repli, mode dégradé) ; notifications HA.
- **Panneau plein écran** — diagramme de flux animé, graphique puissance + prévision PV, prédictions (graphe SoC + tableau + résumé en clair), donuts autoconso/autonomie, jauge puissance souscrite, historique.
- **Validation YAML stricte** des entity_id de contrôle (domaine requis) ; **référence de configuration** complète (`docs/configuration-reference.md`).

### Changed

- Réserve backup configurable (défaut 20 %) ; gros attributs panneau exclus du recorder.

### Earlier V2 groundwork

- **Pilotage actif onduleurs** (`core/active_control.py`, V2) — modèles `ActiveControlCommand` (device, mode, power_w, soc_target_pct, priority), `ActiveControlResult`, `DeviceControlCapability` (entités setpoint par device, modes supportés). Feature-flagged : aucune écriture HA en v1. 12 tests unitaires.
- **Planificateur prédictif 24h** (`core/planner.py`, V2) — `PredictiveScheduler` : optimisation par programmation dynamique sur grille SoC discrète. Calcule la séquence optimale charge/décharge pour minimiser le coût électrique sur un horizon multi-horaire (typiquement 24 créneaux d'1 h). Prend en compte efficacité aller-retour, contraintes SoC min/max, prix import/export par créneau. 11 nouveaux tests unitaires.
- **`solarbalance-card`** (Lovelace custom card) — `frontend/solarbalance-card/` : composant Lit + TypeScript compilé via Vite vers `custom_components/solarbalance/www/solarbalance-card.js`. Affiche un diagramme Sankey temps réel (solaire / batterie / maison / réseau) avec badge mode HEMS, métriques puissances, jauge SoC batterie. Configuration YAML minimale : `type: custom:solarbalance-card`. Nouvelle cible `make build-frontend`.
- **Tarifs dynamiques EDF Tempo** (`TempoTariff`) — résolution HC/HP combinée avec la couleur du jour (bleu/blanc/rouge). Prix 2025-2026 intégrés par défaut. 13 tests unitaires.
- **Tarifs spot EPEX/Nordpool** (`EpexSpotTariff`) — pass-through du prix spot horaire avec markup, `price_cap`, `price_floor`. 7 tests unitaires.

### Added (triphasé — commit précédent)

- **ZI triphasé** (`PerPhaseZeroInjectionController`) — trois contrôleurs PI indépendants L1/L2/L3 via `per_phase_zi: true`.
- Modèles : `grid_power_l{1,2,3}_w` sur `Snapshot` ; `per_phase_zi` sur `Meter`.
- 4 nouveaux tests unitaires ZI triphasé.

[1.3.1]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/solarbalance/ha-solarbalance/releases/tag/v1.0.0
