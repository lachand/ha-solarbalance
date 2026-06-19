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

## [2.0.7-beta2] — 2026-06-17

### Fixed

- **Régression du yoyo nocturne corrigée — l'autotuner est restauré.** En 2.0.4,
  retirer l'auto-réglage supervisé avait **supprimé l'anti-pompage** : c'était lui
  qui amortissait l'oscillation due au **temps mort de l'EcoFlow** (il détecte les
  inversions de sens et baisse le gain de façon réactive). Le gain progressif qui
  l'avait remplacé ne détecte rien — pire, il **monte** le gain quand l'erreur est
  grande, ce qui **entretenait** le cycle. Retour à l'état connu-stable :
  **autotuner + kp fixe** (`zero_injection_kp`), suppression du gain progressif
  (`kp_min`/`knee`). Capteur diagnostic kp = de nouveau le **kp auto-réglé**.

### Kept

- Capteurs **MPPT** (PV power / PV output limit, 2.0.5) et **réseau naturel**
  (hors parc) conservés. Liens doc `lachand/ha-solarbalance` (2.0.6) conservés.

## [2.0.7-beta1] — 2026-06-17

### Added

- **Diagnostics de régulation pour le réglage à vue** (consolidation, pas de
  nouvelle feature) :
  - **`Zero-injection effective gain (Kp)`** — le gain **progressif effectif** au
    tick courant (entre `kp_min` et `kp_max` selon l'erreur). Permet de voir le
    gain réagir et de régler `kp_min` / `kp_max` / `knee` à vue.
  - **`Natural grid (without the fleet)`** — le réseau **sans la contribution du
    parc** (`grid filtré − puissance parc`), grandeur au cœur des garde-fous
    (anti-export, anti-drain batterie cloud). Aide à comprendre ce que « voit »
    réellement la régulation.

## [2.0.6] — 2026-06-17

### Fixed

- **Lien « ? » de la doc** — le manifest pointait vers un dépôt inexistant
  (`solarbalance/ha-solarbalance`). `documentation`, `issue_tracker` et
  `codeowners` pointent désormais vers **`lachand/ha-solarbalance`**, donc le « ? »
  du panneau de configuration ouvre la bonne page.

### Changed

- **README** : suppression de la section *Companion frontend* ; lien HACS corrigé
  vers `github.com/lachand/ha-solarbalance`.

## [2.0.5] — 2026-06-17

### Added

- **Capteurs par micro-onduleur / MPPT** — un appareil MPPT (onduleur seul)
  n'avait **aucune entité** associée. Il expose désormais **`PV power`** (sa
  production) et, s'il est bridable (pilotage actif + entité de limite), **`PV
  output limit`** (la limite réellement appliquée par l'écrêtage). Pour un
  appareil combiné batterie+onduleur, ces capteurs se rangent sous le même
  appareil. Rend l'écrêtage **observable**.

### Notes

- **Pourquoi le micro-onduleur ne se bride pas toujours** : l'écrêtage est le
  **dernier recours** de la zéro-injection. Il n'agit que si les **batteries sont
  saturées** (pleines) **et** que le réseau exporterait encore. Tant qu'une
  batterie a de la place, SolarBalance **stocke le surplus** (sans perte) plutôt
  que de **brider les panneaux** (perte sèche). Le capteur `PV output limit`
  reste donc au pic et ne descend que quand les batteries ne peuvent plus absorber.

## [2.0.4] — 2026-06-17

### Added

- **Gain progressif de la zéro-injection** — `kp` n'est plus constant : il vaut
  `zero_injection_kp_min` (défaut 0,2) près de la bande morte et monte
  linéairement jusqu'à `zero_injection_kp` (= kp max, défaut 0,6) atteint à
  `zero_injection_knee_w` (défaut 600 W). → **doux près de l'équilibre** (plus de
  pompage contre le temps mort de l'EcoFlow) et **nerveux sur un gros déficit/une
  grosse injection** (correction rapide, fini les longues minutes pour revenir de
  −780 W). Deux nouveaux réglages dans *Configurer → Régulation*.

### Removed

- **Auto-réglage supervisé (autotuner) retiré** — il rabaissait *tout* le gain
  ZI dès qu'il y avait du pompage en zone basse (kp tombé à ~0,23), rendant les
  gros écarts trop lents. Le gain progressif gère nativement l'anti-pompage, sans
  brider les grosses corrections. Supprime l'option `autotune_enabled`, les
  capteurs de diagnostic d'auto-réglage et les notifications de suggestion.

## [2.0.3] — 2026-06-16

### Added

- **Option « Autoconsommation stricte : ne jamais décharger la batterie vers le
  réseau »** (désactivée par défaut). Quand elle est active, une **butée par
  projection directe** plafonne la décharge du parc pour que le réseau **ne passe
  pas en export** (`grid ≥ 0` côté batterie) **en un seul tick** — utile quand la
  ZI met trop longtemps à arrêter une sur-décharge (elle suit `puissance mesurée
  + correction` et l'EcoFlow rampe lentement). Elle ne fait que **réduire une
  décharge** (jamais forcer une charge) → le **surplus PV continue d'exporter**
  et, en import, la décharge couvre normalement la maison. **Laissée désactivée**,
  l'injection reste possible (ex. pour forcer la charge d'une batterie cloud).

## [2.0.2] — 2026-06-16

### Fixed

- **Garde-fou « batterie non-pilotable » : plafonnage sur le réseau *naturel***
  (correctif de la 2.0.1). Le garde-fou était plafonné par l'import réseau *brut*
  ; or en régime établi, la ZI décharge déjà le parc pour couvrir la batterie
  cloud → le compteur lit ~0 → le garde-fou voyait « pas d'import » et n'agissait
  jamais (stabilité marginale). Il utilise désormais le réseau **sans la
  contribution du parc** (`grid − puissance du parc`), invariant à ce que fait le
  parc : le vrai import (ex. 4 − (−1461) = 1465 W) est révélé et la décharge du
  parc pour nourrir la batterie cloud est bien neutralisée.

## [2.0.1] — 2026-06-16

### Added

- **Ne pas décharger le parc pour nourrir une batterie non-pilotable qui se
  recharge seule** — une batterie cloud (sans pilotage actif) peut décider de se
  recharger toute seule ; sa charge passe par le compteur, donc la zéro-injection
  déchargeait le parc pilotable pour la couvrir (transfert batterie→batterie en
  pertes, pire la nuit sans PV). Le setpoint ZI est désormais relevé de la
  puissance de charge de cette batterie (plafonné à l'import réseau, après le
  feed-forward de charge forcée) → la batterie cloud tire **sur le réseau**
  (une seule conversion) au lieu de **vider le parc**. Activé par défaut, option
  *« Ne pas décharger le parc pour alimenter une batterie non-pilotable (cloud)
  qui se recharge seule »* dans *Configurer → Régulation*.

### Changed

- **`sw_version` du device lu depuis le manifest** — la version logicielle de
  l'appareil HEMS est lue automatiquement au démarrage (plus de valeur en dur).

## [2.0.0] — 2026-06-16

Première version **stable de la v2** (Vague 4, étape 1) — consolide les
pré-releases `2.0.0-beta.1` → `2.0.0-beta.13`. Faits marquants depuis la 1.11 :

- **Pilotage actif** des batteries/onduleurs (écriture des consignes charge /
  décharge / mode + écrêtage micro-onduleur), opt-in global et par appareil, avec
  garde-fou si configuré mais non activé.
- **Équaliseur SoC** robuste pour batterie non-pilotable (cloud) : offre
  proportionnelle, cadence lente **adaptative** au retard mesuré, anti-windup
  conscient du temps mort, **plancher de décharge direct** (pousse le PV vers la
  batterie auto même en charge), **gate & plafond sur la production PV** (ne
  redistribue que du solaire, jamais de transvasement lossy).
- **Auto-réglage supervisé** des gains ZI/équaliseur (amortit le pompage, restaure
  au calme, borné) + **suggestion** de nouvelles valeurs.
- **Observabilité énergie** : SoC moyen **pondéré par capacité**, capteurs
  `battery_remaining` / `battery_usable`, diagnostics auto-réglage.
- **Mapping batterie** : capteur signé **ou** couple charge/décharge, dans l'UI.
- **Filtre vigilances Météo-France par phénomène** (ex. exclure Canicule).
- **Corrections UI** (création batterie/compteur/load en float) + intégration
  continue au vert.

## [2.0.0-beta.13] — 2026-06-16

### Added

- **Équaliseur SoC : gate & plafond sur la production PV** — l'équaliseur ne
  redistribue désormais que du **solaire**. Il n'agit que si la **PV du parc
  pilotable** (ses propres MPPT) dépasse `soc_equaliser_min_pv_w` (défaut 200 W),
  et l'offre est **plafonnée à cette production**. Évite de transvaser une batterie
  dans une autre en perte (~15-25 % aller-retour) et d'agir la nuit ; ne décharge
  jamais le parc au-delà de sa propre production PV.

## [2.0.0-beta.12] — 2026-06-16

### Changed

- **Équaliseur SoC : l'offre devient un plancher de décharge direct** (au lieu d'un
  biais du setpoint zéro-injection). En **surplus**, l'ancien mécanisme laissait la
  cible parc positive (le parc charge depuis son PV) → consigne de décharge à 0 →
  l'énergie PV du parc pilotable n'était jamais poussée vers la batterie auto vide.
  Désormais l'offre force **au moins `offer` de décharge** du parc pilotable
  (`apply_equaliser_offer`), ce qui transfère réellement le PV vers la batterie auto.
  Plancher **absolu** (pas d'intégration/runaway) ; borné par l'offre proportionnelle
  et l'anti-fuite. **Requiert le pilotage actif** avec une entité de consigne de
  décharge sur le parc pilotable pour être effectif.

## [2.0.0-beta.11] — 2026-06-16

### Added

- **Garde-fou pilotage actif** — si un appareil a `active_control_enabled` mais que
  l'option **globale** est désactivée (ou que `dry_run` est actif), un diagnostic
  `config_health` + notification persistante avertit que **les consignes ne sont
  pas écrites**. Évite le piège « device coché mais global off → rien ne se passe ».

## [2.0.0-beta.10] — 2026-06-16

### Added

- **Suggestion de réglage par l'auto-tuner** — quand l'auto-réglage ajuste souvent
  un gain et se stabilise nettement loin de la valeur configurée, une notification
  persistante **propose la nouvelle valeur** (`zero_injection_kp` /
  `soc_equaliser_probe_step_w`) à définir dans *Configurer → Régulation*. Débouncée,
  retirée quand elle n'a plus lieu d'être.

### Changed

- **Intégration continue au vert** — `ruff` (lint + format), `mypy --strict` sur
  `core/` et tests core tous propres : tri d'imports, `datetime.UTC`, unicode ASCII
  dans docstrings/commentaires, typage du parseur de tarif, docstrings de protocole,
  per-file-ignores D102 pour les plateformes HA. Aucun changement fonctionnel.

## [2.0.0-beta.9] — 2026-06-16

### Added

- **Auto-réglage supervisé des boucles** (`autotune_enabled`, **on par défaut**) —
  un superviseur surveille les **inversions de sens** de la correction zéro-injection
  et de l'offre de l'équaliseur sur une fenêtre glissante. En cas d'**oscillation**
  (pompage), il **amortit** le gain (`kp` ZI ×0,8 plancher 0,2 ; plafond de pas
  équaliseur ×0,8 plancher 100 W) ; au **calme**, il le **restaure** lentement vers
  la valeur configurée. Borné aux valeurs configurées → ne peut que rendre une
  boucle **plus douce**, jamais plus agressive (sûr par défaut). Module pur
  `core/autotuner.py` + tests ; capteurs/log d'observabilité.

## [2.0.0-beta.8] — 2026-06-16

### Added

- **Filtre des vigilances Météo-France par phénomène (réintégré)** — deux options
  *Régulation* : `weather_phenomena` (multi-sélection : quels phénomènes
  déclenchent le mode Tempête — ex. exclure *Canicule*) et `weather_min_level`
  (`jaune`/`orange`/`rouge`, défaut orange). Lit les **attributs** de l'entité
  Météo-France (`sensor.<dept>_weather_alert`, un par phénomène), avec un
  appariement tolérant (casse/accents/séparateurs). Repli inchangé sur un
  `binary_sensor` simple. Module pur `core/weather.py` + tests. (Le passage en
  dégradé observé en beta.6 venait d'une **entité temporairement absente**, pas du
  code.)

## [2.0.0-beta.7] — 2026-06-16

### Changed

- **Équaliseur SoC — pas proportionnel à l'écart** : l'offre fait des **gros pas
  quand le SoC est loin de la cible** (un grand écart se corrige en quelques
  minutes au lieu de ~30) et des **pas doux près de l'équilibre** (anti-pompage
  conservé). Plafond `soc_equaliser_probe_step_w` relevé (défaut 150 → 600 W ;
  c'est désormais la borne haute du pas, pas un pas fixe).

### Reverted

- **Filtre vigilances Météo-France par phénomène (beta.6)** — passage en dégradé
  (entité temporairement absente) ; réintégré en beta.8.

## [2.0.0-beta.5] — 2026-06-16

### Fixed

- **Création d'une batterie (et compteur/consommateur) via l'UI échouait** —
  *« expected int … soc_min_pct »*. Le `NumberSelector` de HA renvoie des floats
  (`10.0`) alors que le loader exigeait un `int` strict. Les champs entiers
  (`soc_min_pct`, `soc_max_pct`, `phases`, `priority`, `hour`) sont désormais
  **coercés** (acceptent int YAML et float UI).

## [2.0.0-beta.4] — 2026-06-16

### Changed

- **La raison brute s'affiche dans l'erreur de config d'un appareil** — quand la
  validation échoue pour une cause non catégorisée, le formulaire montre désormais
  le message d'exception exact (`{reason}`) au lieu du seul texte générique, pour
  diagnostiquer sans avoir à fouiller les logs.

## [2.0.0-beta.3] — 2026-06-16

### Changed

- **Messages d'erreur de config batterie spécifiques** — au lieu du texte
  générique « Invalid battery configuration… », le formulaire indique désormais la
  cause exacte : *capteur de puissance manquant* (renseigner Puissance signée OU
  Charge + Décharge), *pilotage actif sans consigne*, ou *pilotage actif sans
  batterie pilotable*. (FR/EN, types Batterie et Batterie + onduleur.)

## [2.0.0-beta.2] — 2026-06-16

> Vague 4 (étape 1, **pré-release**) — capteurs d'énergie, mapping 2 capteurs en
> UI, allègement du panneau.

### Added

- **Capteur `sensor.solarbalance_battery_usable`** — fenêtre d'énergie exploitable
  du parc (kWh) = Σ (SoC_max − SoC_min) × capacité utilisable effective.
- **Couple de capteurs charge/décharge dans l'UI** — le formulaire *Batterie* (et
  *Batterie + onduleur*) expose désormais `charge_power_entity` /
  `discharge_power_entity` en alternative au `power_entity` signé, pour les
  batteries à deux capteurs de puissance distincts. (Déjà géré en YAML ; manquait
  dans le Config Flow.)

### Changed

- **`sensor.solarbalance_battery_energy_available` renommé en
  `sensor.solarbalance_battery_remaining`** (même valeur : énergie stockée). Les
  capteurs d'énergie utilisent désormais la capacité utilisable **effective**
  (ratio chimie si non explicite) — sans effet sur le SoC moyen (le ratio
  s'annule), mais plus juste en kWh.
- **Panneau** : capteurs *Restant* et *Exploitable* ajoutés à la carte « Flux
  instantané » ; sections *Historique (N derniers jours)*, *Coûts & économies
  (€/jour)* et *Plan prédictif (advisory)* retirées de la vue.

## [2.0.0-beta.1] — 2026-06-16

> Vague 4 (étape 1, **pré-release**) — stabilisation de l'équaliseur SoC +
> fiabilisation des moyennes de SoC. À valider par replay avant pilotage.
> (Restent : prévision de conso, throttle SoH, détection chute PV.)

### Added

- **Capteur `sensor.solarbalance_battery_energy_available`** — énergie utilisable
  **stockée** dans le parc (kWh, `device_class: energy_storage`) = Σ (SoC × capacité
  utilisable) sur les batteries disponibles.
- **Réglages équaliseur dans l'UI** — `soc_equaliser_cadence_ticks` (cadence,
  plancher de ticks entre mouvements) et `soc_equaliser_adaptive_cadence` (cadence
  dérivée du retard mesuré) exposés dans *Configurer → Régulation*.

### Fixed

- **SoC moyen pondéré par capacité** — `sensor.solarbalance_battery_soc_avg` faisait
  une moyenne **arithmétique** des pourcentages : une batterie 2 kWh à 75 % + une
  3,96 kWh à 25 % donnaient 50 % au lieu du SoC énergie-vrai (~42 %). Désormais
  pondéré par capacité utilisable, tout comme le SoC agrégé fourni au **planner
  prédictif** (qui modélise le parc comme une batterie unique). Le déficit du
  délestage de fin de journée était déjà correct (calcul par batterie en kWh).

### Changed

- **Équaliseur SoC indirect réécrit (anti-pompage)** — sur batterie automatique
  *cloud* (ex. Jackery), l'ancien équaliseur partait en **cycle limite** : l'offre
  (intégrateur) montait en rampe jusqu'à son plafond puis s'effondrait, fouettant
  le parc pilotable entre charge et décharge pleines et projetant des pics réseau
  de ±1,3 à 2,7 kW (injection visible) toutes les ~5 min, pour un SoC qui ne
  convergeait pas. La nouvelle version :
  - **offre proportionnelle à l'écart de SoC** (plus d'intégrateur → plus de
    windup) ;
  - **cadence lente** : l'offre ne bouge que toutes les *N* ticks, *N* étant
    **dérivé du retard de réponse mesuré** de la batterie cloud
    (`soc_equaliser_adaptive_cadence`, défaut on ; plancher
    `soc_equaliser_cadence_ticks`, défaut 6) ;
  - **anti-windup conscient du temps mort** : un export/import n'est rétracté que
    s'il **persiste** *et* que la puissance mesurée de la batterie auto **ne
    progresse pas** (on distingue « fuite réseau » de « la ZI exécute l'offre
    pendant le délai cloud ») ;
  - **pente symétrique** (resets inclus, fini les sauts à 0) et **hystérésis
    d'arrêt** (reprise seulement au-delà de la bande morte + marge).
  La ZI elle-même (P-seul) était saine et n'est pas modifiée.

## [1.11.1] — 2026-06-15

### Fixed

- **`solarbalance.replay` échouait (« Unknown error »)** — la boucle lisait `result.decision.dominant_strategy` (inexistant) au lieu de `result.dominant_strategy` → `AttributeError`. Corrigé + le service renvoie désormais un message d'erreur explicite plutôt que « Unknown error ». Couvert par un test de bout en bout de la boucle de replay.

## [1.11.0] — 2026-06-15

> Vague 3 de la [roadmap](docs/BACKLOG.md) — replay. (Restent : détection auto d'entités + assistant de 1er setup.)

### Added

- **Replay d'une journée passée** — service `solarbalance.replay` (`date`, `step_minutes`) : rejoue une journée depuis l'historique du recorder à travers le moteur de décision (lecture seule, **aucune écriture**) et renvoie un **résumé horaire** (puissance réseau, cible batterie, stratégie dominante, coût) + les totaux import/export/coût. Idéal pour comprendre/valider ce qu'aurait fait le HEMS.

### Changed

- **`EntityReader` accepte un fournisseur d'états** (`state_getter`) — le lecteur peut reconstruire un `Snapshot` depuis des états historiques au lieu du live ; aucun changement de comportement en fonctionnement normal.

## [1.10.0] — 2026-06-15

> Vague 3 de la [roadmap](docs/BACKLOG.md) — outils de confiance (1/2). Le **replay** et l'assistant de 1er setup suivront dans une prochaine release de la vague 3.

### Added

- **Mode simulation (dry-run)** — option *Régulation* `dry_run` : le moteur calcule tout (décisions, consignes, capteurs, panneau) mais **n'écrit jamais** sur le matériel, même contrôle actif/loads armés. Idéal pour observer une journée entière en confiance avant d'activer le pilotage réel. Exposé aussi dans l'export de diagnostic.
- **Service `solarbalance.test_mapping`** — vérifie chaque entité configurée (appareils/compteurs/consommateurs + prévision) et renvoie la liste **ok / indisponible / manquante** (données de réponse), pour valider un mapping fraîchement saisi.

## [1.9.0] — 2026-06-15

> Vague 2 de la [roadmap](docs/BACKLOG.md) — délestage intelligent & protection réseau.

### Added

- **Protection active de la puissance souscrite** (`overload_protection_enabled`, off par défaut) — quand l'import réseau dépasse 95 % de la puissance souscrite, les consommateurs les **moins prioritaires** sont **réduits puis coupés en cascade** jusqu'à repasser sous le seuil. Surcharge réseau évitée avant la disjonction. Appliqué en dernier (prioritaire sur la charge forcée).
- **Load-balancing EV** — les consommateurs modulables/à paliers (chargeur EV) sont **réduits vers leur plancher** (baisse d'ampérage) **avant** d'être coupés, par la même cascade.
- **Mode « Solaire seulement » par consommateur** — interrupteur `switch.solarbalance_<load>_solar_only` (+ toggle panneau) : n'autorise le consommateur (ex. pompe piscine) que lorsque le **surplus PV** couvre sa puissance. Restauré au redémarrage.

### Changed

- **Délestage fin de journée en cascade** — l'`evening_shed` ne coupe plus tout d'un bloc : il déleste les consommateurs **par priorité croissante** et **seulement assez** pour combler le déficit de charge batterie.

## [1.8.0] — 2026-06-15

> Vague 1 de la [roadmap](docs/BACKLOG.md) — plomberie & intégration HA.

### Added

- **Événements de bus HA** pour les automatisations : `solarbalance_mode_changed`, `solarbalance_shedding` (`started`/`stopped` + loads), `solarbalance_tempo_red_day`, `solarbalance_force_charge`. Déclenchés sur transition (front montant/descendant).
- **Entrées Logbook** lisibles pour ces événements (FR/EN selon la langue de HA).
- **Blueprints d'automatisation** (`blueprints/automation/solarbalance/`) : charger l'EV la nuit en HC, alerte jour rouge Tempo, **notification mobile actionnable** (« Charger maintenant » / « Annuler » appelant les services).

### Changed

- **Panneau internationalisé (FR/EN)** — titres de cartes, tuiles, légendes, tableaux et libellés du diagramme suivent la langue de Home Assistant (avant : FR codé en dur).

## [1.7.0] — 2026-06-15

### Added

- **Fenêtres horaires par consommateur dans l'UI** — le formulaire d'un load expose `time_window` (début/fin HH:MM) : le load n'est autorisé que dans cette plage.
- **Sauvegarde/restauration de la configuration** — services `solarbalance.export_config` (renvoie les sub-entries en données de réponse) et `solarbalance.import_config` (recrée des appareils/loads depuis cette liste), pour migrer ou repartir d'une base.

### Changed

- **États traduisibles (EN/FR)** — `sensor.<load>_status` devient un capteur `enum` traduit par le frontend (`actif`/`active`, `délesté`/`shed`…) ; l'attribut `reason` du capteur de mode suit désormais la langue de Home Assistant. Fini les chaînes françaises codées en dur.

### Tests

- **Couverture de bout en bout sur tick réel** — off-peak (load coupé hors heures creuses), charge forcée (switch commandé `on`), anti-yoyo (gel ZI + feed-forward sur ticks consécutifs), export/import de config.

## [1.6.1] — 2026-06-15

### Fixed

- **Charge forcée réseau — feed-forward sur la puissance mesurée** — l'offset zéro-injection utilisait la puissance *nominale* du consommateur (calculée avant qu'il ne consomme), ce qui pouvait faire **charger la batterie depuis le réseau** au démarrage (la nuit) ou quand la charge réelle était inférieure au nominal. Il suit désormais la puissance **mesurée** du consommateur forcé (plafonnée au nominal) : la batterie n'est ni déchargée pour l'alimenter, ni chargée depuis le réseau pour « atteindre » la consigne. La batterie continue de couvrir le reste de la maison. Vérifié par un test de tick complet de bout en bout.

## [1.6.0] — 2026-06-14

### Added

- **Charge forcée strictement réseau** — pendant un « Charger maintenant », la consigne zéro-injection est relevée de la puissance du consommateur forcé : la **batterie ne se décharge plus** pour l'alimenter, le réseau s'en charge (fin du yo-yo batterie→voiture).
- **Capteurs par consommateur** — `sensor.solarbalance_<load>_energy_today` (énergie du jour, kWh) et `sensor.solarbalance_<load>_status` (`actif` / `inactif` / `délesté` / `attente heures creuses` / `charge forcée`), regroupés sous l'appareil du consommateur.
- **Économies dans le Energy Dashboard** — `savings_this_month` / `savings_this_year` passent en `device_class: monetary` + `state_class: total` avec `last_reset`, donc utilisables nativement dans les tableaux énergie/coûts de HA.
- **Notification des problèmes de configuration** — les défauts détectés (capacité batterie nulle, plage SoC invalide, `fast_charge` sans `min_charge_w`/puissance) remontent en notification persistante, pas seulement dans le binary_sensor.

### Changed

- Documentation mise à jour (README + référence de configuration) : config UI sans YAML, switches par consommateur, services `force_charge_load`, capteurs d'économies/par-load, diagnostics.
- Test d'intégration de l'anti-yoyo (armement de la fenêtre de stabilisation sur chute de charge) en plus des tests unitaires.

## [1.5.0] — 2026-06-14

### Added

- **Mode « Heures creuses seulement » par consommateur** — interrupteur `switch.solarbalance_<load>_off_peak_only` (et toggle panneau) qui n'autorise un consommateur que dans les fenêtres tarifaires basses (HC / prix spot bas / Tempo non-rouge). Restauré au redémarrage ; outrepassé par l'échéance de départ et la charge forcée.
- **Économies cumulées** — capteurs `sensor.solarbalance_savings_this_month` / `...this_year` (€, remis à zéro au changement de mois/année, persistés) + tuiles dans le panneau.
- **Graphe coûts & économies (€/jour)** dans le panneau — barres coût réseau net vs économies sur les 30 derniers jours, avec totaux.
- **Raison de décision lisible** — phrase explicative (« Batteries en décharge — prix élevé… ») exposée en attribut `reason` du capteur de mode et affichée en tête du panneau.
- **Diagnostic de configuration enrichi** — `binary_sensor` de santé/`config_issues` détecte désormais une capacité batterie absente/nulle, une plage SoC invalide, et un `fast_charge` sans `min_charge_w` ou sans puissance nominale.
- **Export de diagnostic HA** — Paramètres → Appareils → Télécharger les diagnostics (état du moteur, config, snapshot, régulation) pour faciliter le support.

### Changed

- **Formulaire d'options scindé en sections** — un menu « Régulation & comportements / Prévision PV / Tarif & prix » remplace le formulaire unique très long ; chaque section enregistre sans toucher aux autres.

## [1.4.0] — 2026-06-14

### Added

- **« Charger maintenant » par consommateur (force charge réseau)** — chaque load reçoit un interrupteur `switch.solarbalance_<load>_force_charge` qui force la charge à pleine puissance immédiatement, **même sans surplus solaire**, en passant outre le délestage, la pause charge-rapide et le suivi solaire. Complément du « Ne pas délester ». Disponible aussi en bandeau-bouton dans le panneau (carte « Consommateurs »).
- **Services `solarbalance.force_charge_load` / `cancel_force_charge_load`** — version paramétrable pour les automatisations : `load` (nom), `kwh` (énergie cible de la session) et/ou `hours` (durée max). Sans limite, charge jusqu'à annulation. Le switch est l'équivalent « jusqu'à annulation ».

## [1.3.5] — 2026-06-14

### Added

- **Toggles « Ne pas délester » dans le panneau** — une carte « Consommateurs » liste chaque consommateur interruptible avec un bouton bascule pour activer/couper l'exemption de délestage directement depuis le panneau (appelle le service `switch.toggle` sur l'entité correspondante).

## [1.3.4] — 2026-06-14

### Added

- **Switch « Ne pas délester » par consommateur** — chaque load interruptible reçoit un interrupteur (`switch.solarbalance_<load>_shed_exempt`) qui l'exempte temporairement du délestage : ni coupé par le délestage fin de journée (priorité batterie), ni mis en pause par la charge rapide pour cause d'inefficacité. Idéal pour « je veux vraiment charger ma voiture maintenant ». L'état est restauré au redémarrage. Le load reste alimenté par le surplus dispatché (pas de charge réseau forcée — voir `deadline_constraint` pour ça). Le switch est rattaché au subentry du load.

## [1.3.3] — 2026-06-14

### Added

- **Capteurs batterie rattachés à leur subentry** — les capteurs par batterie (consigne charge/décharge, SoC, puissance, température, cycles, SoH) sont désormais enregistrés sous le subentry de l'appareil correspondant, donc regroupés sous cet appareil dans l'UI au lieu d'apparaître sous « Devices that don't belong to a sub-entry ». Repli sur l'appareil principal pour les équipements venant du YAML (sans subentry).

## [1.3.2] — 2026-06-14

### Added

- **Anti-yoyo après coupure d'un consommateur** — quand le contrôleur coupe un gros load (ex. pause de la voiture), la régulation zéro-injection est **figée pendant N ticks** (option `zi_settle_ticks`, défaut 2) et un **feed-forward one-shot** réduit la consigne de décharge des batteries du montant coupé, au lieu de laisser la boucle PI s'emballer sur le transitoire d'export. Seuil d'armement configurable (`zi_settle_min_drop_w`, défaut 300 W). Les batteries non pilotables ne reçoivent pas le feed-forward mais bénéficient du gel de la boucle.
- **Menus déroulants pour les entités d'options** — `pv_forecast_entity`, `pv_forecast_tomorrow_entity`, entités Tempo, prix spot et vigilance météo sont des sélecteurs d'entités (plus des champs texte). Forecast et tarif sont donc pleinement configurables dans l'UI (le YAML reste prioritaire s'il est présent — retirer `forecast:`/`tariff:` du YAML pour basculer sur l'UI).

### Fixed

- **Configuration UI : champs optionnels vides** — éditer/créer un appareil échouait avec « Entity is neither a valid entity ID nor a valid UUID » (ou « expected float ») dès qu'un champ entité/nombre **optionnel** était laissé vide. Les sélecteurs acceptent désormais le vide ; les champs requis restent validés par le builder (erreur claire au lieu d'un blocage).

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

[2.0.7-beta2]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta1...v2.0.7-beta2
[2.0.7-beta1]: https://github.com/lachand/ha-solarbalance/compare/v2.0.6...v2.0.7-beta1
[2.0.6]: https://github.com/lachand/ha-solarbalance/compare/v2.0.5...v2.0.6
[2.0.5]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.4...v2.0.5
[2.0.4]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.3...v2.0.4
[2.0.3]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.13...v2.0.0
[2.0.0-beta.13]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.12...v2.0.0-beta.13
[2.0.0-beta.12]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.11...v2.0.0-beta.12
[2.0.0-beta.11]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.10...v2.0.0-beta.11
[2.0.0-beta.10]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.9...v2.0.0-beta.10
[2.0.0-beta.9]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.8...v2.0.0-beta.9
[2.0.0-beta.8]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.7...v2.0.0-beta.8
[2.0.0-beta.7]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.5...v2.0.0-beta.7
[2.0.0-beta.5]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.4...v2.0.0-beta.5
[2.0.0-beta.4]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.3...v2.0.0-beta.4
[2.0.0-beta.3]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.2...v2.0.0-beta.3
[2.0.0-beta.2]: https://github.com/solarbalance/ha-solarbalance/compare/v2.0.0-beta.1...v2.0.0-beta.2
[2.0.0-beta.1]: https://github.com/solarbalance/ha-solarbalance/compare/v1.11.1...v2.0.0-beta.1
[1.11.1]: https://github.com/solarbalance/ha-solarbalance/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/solarbalance/ha-solarbalance/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.5...v1.4.0
[1.3.5]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.4...v1.3.5
[1.3.4]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.3...v1.3.4
[1.3.3]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/solarbalance/ha-solarbalance/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/solarbalance/ha-solarbalance/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/solarbalance/ha-solarbalance/releases/tag/v1.0.0
