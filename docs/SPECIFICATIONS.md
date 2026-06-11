# SolarBalance — Cahier des charges

> Custom component Home Assistant pour la gestion énergétique multi-sources (HEMS).
> **Licence** : Apache 2.0
> **Statut** : v0 — document fondateur, susceptible d'évoluer

---

## Table des matières

1. [Vision et objectifs](#1-vision-et-objectifs)
2. [Périmètre fonctionnel](#2-périmètre-fonctionnel)
3. [Modèle de données et abstractions](#3-modèle-de-données-et-abstractions)
4. [Architecture logicielle](#4-architecture-logicielle)
5. [Configuration](#5-configuration)
6. [Algorithmes et stratégies](#6-algorithmes-et-stratégies)
7. [Sources externes](#7-sources-externes)
8. [Modes de fonctionnement et overrides](#8-modes-de-fonctionnement-et-overrides)
9. [Failsafe, watchdog et mode dégradé](#9-failsafe-watchdog-et-mode-dégradé)
10. [Interface utilisateur](#10-interface-utilisateur)
11. [Roadmap par versions](#11-roadmap-par-versions)
12. [Conventions du projet](#12-conventions-du-projet)
13. [Glossaire](#13-glossaire)

---

## 1. Vision et objectifs

### 1.1 Vision

SolarBalance est un **HEMS (Home Energy Management System)** intégré à Home Assistant sous forme de custom component. Il orchestre la production photovoltaïque, le stockage batterie et les charges électriques d'un foyer pour atteindre un ou plusieurs objectifs énergétiques (autoconsommation, coût, autonomie, longévité matérielle), tout en s'adaptant à des contextes externes (tarif, météo, vigilance).

### 1.2 Principes directeurs

- **Agnostique au matériel** : aucun modèle ou marque privilégié dans le cœur. Tout équipement exposant des entités HA peut être intégré via un mapping déclaratif.
- **Configuration explicite** : pas de profils préremplis par marque en v1. L'utilisateur déclare ses entités. Un assistant peut être ajouté plus tard.
- **Lecture d'abord, écriture ensuite** : la v1 calcule et publie ses décisions sans piloter directement. L'utilisateur observe via une carte dédiée, brancher ses propres automatisations sur les consignes, puis active la commande directe au fur et à mesure que les intégrations le supportent.
- **Découplage cœur / intégration HA** : le moteur décisionnel est testable indépendamment de Home Assistant.
- **Dégradation gracieuse** : aucune dépendance externe n'est bloquante (météo, prévision, tarif). Le HEMS bascule en mode dégradé documenté si une source manque.
- **Souplesse de phase** : architecture monophasée par défaut, extension triphasée via paramètres.

### 1.3 Non-objectifs (v1)

- Pas de pilotage direct des onduleurs (seulement publication des consignes).
- Pas de profils marque préremplis.
- Pas d'optimisation prédictive multi-horaire complexe (MILP, MPC) — heuristiques claires uniquement.
- Pas de gestion de revente / agrégation de marché.

---

## 2. Périmètre fonctionnel

### 2.1 Fonctions cœur

| ID  | Fonction                                                  | Version |
| --- | --------------------------------------------------------- | ------- |
| F1  | Mapping générique d'équipements via entités HA            | v1      |
| F2  | Agrégation et publication d'un état énergétique global    | v1      |
| F3  | Calcul de consignes de charge équilibrée multi-batteries  | v1      |
| F4  | Calcul de consignes de décharge équilibrée multi-batteries| v1      |
| F5  | Régulation zéro injection (calcul de consigne)            | v1      |
| F6  | Intégration prévisions PV via intégrations HA existantes  | v1      |
| F7  | Intégration vigilance Météo-France (mode tempête)         | v1      |
| F8  | Configuration tarifaire générique multi-plages            | v1      |
| F9  | Sélection ordonnée des priorités d'optimisation           | v1      |
| F10 | Pilotage de charges (on/off, paliers, modulant) — calcul  | v1      |
| F11 | Configurations Lovelace fournies (cartes HACS existantes)| v1      |
| F11b| Carte custom `solarbalance-card`                          | v1.5    |
| F12 | Overrides utilisateur (pause, force charge/décharge…)     | v1      |
| F13 | Watchdog par entité et mode dégradé                       | v1      |
| F14 | Pilotage effectif des onduleurs (écriture)                | v2      |
| F15 | Tarifs dynamiques avancés (Tempo, EPEX spot)              | v1.5    |
| F16 | Optimisation prédictive multi-horaire                     | v1.5    |
| F17 | Profils marque préremplis (assistant de config)           | v2+     |
| F18 | Triphasé complet                                          | v2      |
| F19 | Ouverture aux ajustements de service réseau              | v3+     |

### 2.2 Cas d'usage principaux

- **UC-01** : Foyer monophasé, plusieurs stations portables (Ecoflow / Jackery) avec MPPT intégrés, mesure PDL via Shelly 3EM, zéro injection strict obligatoire. Objectif principal : autoconsommation.
- **UC-02** : Foyer en HP/HC, charge des batteries en HC, décharge en HP, pilotage du ballon ECS sur surplus.
- **UC-03** : Mode tempête déclenché sur vigilance orange/rouge vent : SoC remonté à 95% en anticipation.
- **UC-04** : Pilotage d'une borne VE modulante (6-32 A) sur surplus PV exclusivement.
- **UC-05** : Foyer avec onduleur hybride distinct et MPPT séparés (setup type Victron) — déclaration multi-devices avec rôles séparés.

---

## 3. Modèle de données et abstractions

### 3.1 Concept central : Device à rôles

Un **Device** SolarBalance est un conteneur de configuration qui regroupe les entités HA d'un équipement physique. Un device porte un ou plusieurs **rôles** (`battery`, `mppt`, `inverter`, `meter`, `load`).

Cette modélisation couvre uniformément :
- les **stations tout-en-un** (Ecoflow, Jackery) : un seul device, plusieurs rôles agrégés ;
- les **systèmes éclatés** (Victron, Deye + BYD) : plusieurs devices, chacun avec un seul rôle, reliés par références.

### 3.2 Rôles

#### `battery`

Représente un stockage électrochimique adressable.

**Champs de configuration** :
- `name` (str, obligatoire)
- `capacity_kwh` (float, obligatoire) — capacité nominale
- `usable_capacity_kwh` (float, optionnel) — déduit automatiquement selon `chemistry` si absent (voir tableau ci-dessous)
- `soc_min_pct` (int, défaut 10) — SoC plancher absolu
- `soc_max_pct` (int, défaut 95) — SoC plafond absolu
- `max_charge_power_w` (int, obligatoire)
- `max_discharge_power_w` (int, obligatoire)
- `chemistry` (enum: `lifepo4`, `nmc`, `leadacid`, `other` — défaut `lifepo4`)
- `power_sign_convention` (enum, défaut `charge_positive`) :
  - `charge_positive` : entité positive lors de la charge, négative lors de la décharge
  - `discharge_positive` : entité positive lors de la décharge, négative lors de la charge
  - Le cœur normalise toujours en interne en `charge_positive`.

**Capacité utilisable par défaut selon chimie** (utilisé si `usable_capacity_kwh` absent) :

| Chimie     | Coefficient | Capacité utilisable      |
| ---------- | ----------- | ------------------------ |
| `lifepo4`  | 0.95        | 95% de `capacity_kwh`    |
| `nmc`      | 0.85        | 85% de `capacity_kwh`    |
| `leadacid` | 0.50        | 50% de `capacity_kwh`    |
| `other`    | 0.90        | 90% (valeur conservative)|

L'utilisateur peut surcharger via `usable_capacity_kwh` explicite. Une notification d'information est émise au démarrage indiquant la valeur calculée.

**Entités HA mappées (lecture)** :
- `soc_entity` (sensor %, obligatoire)
- `power_entity` (sensor W, signé selon `power_sign_convention`) — OU couple `charge_power_entity` + `discharge_power_entity` (deux entités distinctes, toujours positives)
- `temperature_entity` (sensor °C, optionnel)
- `cycles_entity` (sensor, optionnel)

**Entités HA mappées (commande, optionnelles, vides en v1)** :
- `target_soc_entity` (number)
- `charge_power_limit_entity` (number)
- `discharge_power_limit_entity` (number)
- `mode_entity` (select : `auto`, `force_charge`, `force_discharge`, `idle`)

#### `mppt`

Représente un point de production solaire.

**Champs de configuration** :
- `name` (str, obligatoire)
- `peak_power_w` (int, obligatoire) — puissance crête PV raccordée
- `feeds` (list[str], optionnel) — noms de batteries alimentées (utile en setup éclaté)

**Entités HA mappées (lecture)** :
- `power_entity` (sensor W, obligatoire)
- `daily_energy_entity` (sensor kWh, optionnel)
- `voltage_entity`, `current_entity` (optionnels)

#### `inverter`

Représente une conversion DC↔AC, avec ou sans capacité EPS.

**Champs de configuration** :
- `name` (str, obligatoire)
- `nominal_power_w` (int, obligatoire)
- `eps_capable` (bool, défaut false)
- `eps_circuits` (list[str], optionnel) — étiquettes des circuits secourus

**Entités HA mappées (lecture)** :
- `ac_output_power_entity` (sensor W, obligatoire)
- `ac_input_power_entity` (sensor W, optionnel)
- `eps_active_entity` (binary_sensor, si `eps_capable`)
- `temperature_entity` (optionnel)

#### `meter`

Compteur au point de livraison ou sur une dérivation.

**Champs de configuration** :
- `name` (str)
- `kind` (enum : `pdl`, `pv`, `consumption`, `subcircuit`)
- `phases` (int : 1 ou 3, défaut 1)

**Entités HA mappées (lecture)** :
- `power_entity` (sensor W, signé : positif = soutirage / consommation, négatif = injection / production)
- Par phase si triphasé : `power_l1_entity`, `power_l2_entity`, `power_l3_entity`
- `daily_import_energy_entity`, `daily_export_energy_entity` (optionnels)

#### `load` (charge pilotable)

**Champs de configuration** :
- `name` (str, obligatoire)
- `control_type` (enum : `on_off`, `stepped`, `modulating`)
- `priority` (int) — ordre dans la file de service du surplus (1 = plus prioritaire)
- `interruptible` (bool, défaut true)
- `min_on_duration_s` (int, défaut 0) — durée min ON avant coupure autorisée
- `min_off_duration_s` (int, défaut 0) — anti-court-cycle (PAC, climatiseurs)
- `max_daily_runtime_s` (int, optionnel)
- `max_daily_energy_kwh` (float, optionnel)
- `time_window` (optionnel) — `start`, `end` plages horaires d'éligibilité
- `deadline_constraint` (optionnel) — `kwh_required`, `before_time`

**Spécifique `on_off`** :
- `nominal_power_w` (int, obligatoire) — puissance estimée à l'enclenchement
- `switch_entity` (switch, obligatoire) — entité de commande

**Spécifique `stepped`** :
- `steps` (list[{level: int, power_w: int}]) — paliers déclarés
- `level_entity` (number ou select, obligatoire)

**Spécifique `modulating`** :
- `min_power_w`, `max_power_w` (int, obligatoires)
- `step_w` (int, défaut 1) — résolution du pas
- `power_set_entity` (number, obligatoire) — entité de commande
- `actual_power_entity` (sensor, recommandé) — feedback réel

### 3.3 Validations

- Tout device doit avoir au moins un rôle.
- Un rôle `battery` doit avoir un `soc_entity` et un mécanisme de mesure de puissance.
- Un setup valide pour le HEMS doit comprendre **au moins un meter de kind `pdl`** et **au moins un rôle `battery`**.
- Les sommes des `feeds` doivent être cohérentes (pas de batterie référencée par un MPPT inconnu).

### 3.4 Consommation de fond déduite

La **consommation de fond** (charges non pilotables : frigo, box internet, veilles, éclairage) n'est pas mesurée directement mais déduite par bilan de puissance à chaque tick :

```
P_baseline = P_pdl + P_pv_total + P_battery_discharge − P_battery_charge − Σ P_loads_pilotables
```

Avec les conventions :
- `P_pdl` positif = soutirage réseau, négatif = injection
- `P_pv_total` = somme des `mppt.power_entity`
- `P_loads_pilotables` = somme des puissances actuelles mesurées des charges pilotables (ou estimées via leur consigne si pas de feedback)

Ce bilan est **publié comme `sensor.solarbalance_baseline_consumption`** pour transparence et debug. Il sert également au calcul de surplus disponible et à la détection d'anomalies (valeur négative ou aberrante = mapping incohérent → notification).

---

## 4. Architecture logicielle

### 4.1 Découpage en modules

```
custom_components/solarbalance/
├── __init__.py              # Setup HA, registration
├── manifest.json
├── const.py                 # Constantes, enums
├── config_flow.py           # UI de configuration (paramètres globaux)
├── coordinator.py           # DataUpdateCoordinator HA
├── core/                    # Cœur métier, agnostique HA
│   ├── models.py            # Dataclasses Device, Role, Load, State, Snapshot
│   ├── strategies/          # Une classe par priorité
│   │   ├── base.py
│   │   ├── self_consumption.py
│   │   ├── cost_min.py
│   │   ├── backup.py
│   │   ├── longevity.py
│   │   ├── peak_shaving.py
│   │   └── revenue_max.py
│   ├── controllers/
│   │   ├── balancing.py     # Répartition charge/décharge inter-batteries
│   │   ├── zero_injection.py
│   │   └── load_dispatch.py # Distribution surplus aux loads
│   ├── tariff.py            # Modèle tarifaire générique
│   └── arbitrer.py          # Combine stratégies ordonnées
├── adapters/                # Pont HA ↔ core
│   ├── entity_reader.py
│   ├── decision_publisher.py # Publie consignes comme entités HA
│   └── forecast.py          # Wrappers prévisions PV / météo
├── sensor.py                # Sensors HA exposés (état + consignes)
├── select.py, number.py, switch.py, binary_sensor.py  # Entités de contrôle utilisateur
└── services.yaml            # Services HA (force_charge, etc.)
```

### 4.2 Séparation cœur / intégration HA

Le dossier `core/` n'importe **rien de Home Assistant**. Il manipule uniquement des dataclasses et primitives Python. Cela permet :
- **tests unitaires** rapides (pytest pur, sans `pytest-homeassistant-custom-component`) ;
- **réutilisation** future en lib indépendante (`pyhems` ou autre) ;
- **simulation** d'algorithmes hors ligne avec données historiques.

L'adaptation HA se fait en `adapters/` : lecture des entités, conversion en `Snapshot`, appel du moteur, publication des résultats.

### 4.3 Boucle d'orchestration

```
[Coordinator tick] (intervalle configurable, défaut 10s)
    ├─> EntityReader.snapshot()        # lit toutes les entités mappées
    ├─> Snapshot validate               # cohérence, watchdog
    ├─> Arbitrer.compute(snapshot, priorities, mode)
    │       ├─> chaque Strategy propose une décision partielle
    │       └─> arbitrage selon ordre de priorité utilisateur
    ├─> BalancingController             # raffine répartition multi-batteries
    ├─> ZeroInjectionController         # contrainte si activée
    ├─> LoadDispatchController          # affecte le solde aux loads
    └─> DecisionPublisher.publish()     # mise à jour des entités sortie
```

### 4.4 Performances et latence cible

- Tick par défaut : **10 s**, configurable de 5 s à 60 s.
- Latence acceptable de bout en bout (entrée Shelly → consigne publiée) : **≤ 15 s** en v1.
- Calcul d'un tick en mémoire : **< 100 ms** pour 10 devices et 20 charges (estimation à valider).

---

## 5. Configuration

### 5.1 Bipartition Config Flow + YAML

- **Config Flow (UI)** : paramètres globaux du HEMS.
  - Liste ordonnée des priorités
  - Sources externes (entités prévision PV, vigilance météo, prix)
  - Seuils globaux (zéro injection on/off, hystérésis, intervalle de tick)
  - Référence au meter PDL
- **YAML** : déclaration des devices, rôles et charges.
  - Plus dense, versionnable Git
  - Reload sans redémarrage HA

### 5.2 Exemple de configuration YAML

```yaml
solarbalance:
  devices:
    - name: ecoflow_salon
      roles:
        battery:
          capacity_kwh: 3.6
          soc_min_pct: 10
          soc_max_pct: 95
          max_charge_power_w: 1800
          max_discharge_power_w: 1800
          soc_entity: sensor.ecoflow_salon_soc
          power_entity: sensor.ecoflow_salon_battery_power
          temperature_entity: sensor.ecoflow_salon_temperature
        mppt:
          peak_power_w: 1000
          power_entity: sensor.ecoflow_salon_solar_input
        inverter:
          nominal_power_w: 2400
          eps_capable: true
          ac_output_power_entity: sensor.ecoflow_salon_ac_output

    - name: jackery_garage
      roles:
        battery:
          capacity_kwh: 2.0
          max_charge_power_w: 1000
          max_discharge_power_w: 1000
          soc_entity: sensor.jackery_garage_soc
          power_entity: sensor.jackery_garage_power

  meters:
    - name: pdl_principal
      kind: pdl
      phases: 1
      power_entity: sensor.shelly_3em_total_power

  loads:
    - name: ballon_ecs
      control_type: on_off
      priority: 2
      interruptible: false
      min_on_duration_s: 1800
      nominal_power_w: 2200
      switch_entity: switch.contacteur_ballon
      time_window:
        start: "11:00"
        end: "16:00"

    - name: borne_ve
      control_type: modulating
      priority: 1
      min_power_w: 1380   # 6 A x 230 V
      max_power_w: 7360   # 32 A x 230 V
      step_w: 230         # 1 A
      power_set_entity: number.borne_ve_puissance_consigne
      actual_power_entity: sensor.borne_ve_puissance_reelle
      deadline_constraint:
        kwh_required: 20
        before_time: "07:00"
```

### 5.3 Paramètres globaux (Config Flow)

- `priorities` (liste ordonnée) parmi : `self_consumption`, `cost_min`, `backup`, `longevity`, `peak_shaving`, `revenue_max`
- `tick_interval_s` (5–60, défaut 10)
- `zero_injection_enabled` (bool, défaut false)
- `zero_injection_setpoint_w` (int, défaut 0) — cible (peut être négative pour marge de sécurité)
- `zero_injection_hysteresis_w` (int, défaut 50)
- `max_ramp_w` (int, défaut 800) — variation max de la cible batterie agrégée par tick (0 = désactivé). Voir §6.3.
- `grid_filter_samples` (int ≥ 1, défaut 3) — fenêtre de médiane glissante (en ticks) sur la mesure réseau **envoyée au régulateur** ; rejette les glitches capteur 1-échantillon et les marches de charge brèves. `1` = désactivé. Le capteur réseau affiché reste la valeur brute.
- `phases` (1 ou 3, défaut 1)
- `subscribed_power_kva` (int) — puissance souscrite, sert au peak shaving
- `pv_forecast_entity` (entity_id, optionnel)
- `weather_warning_entity` (entity_id, optionnel)
- `active_control_enabled` (bool, défaut false) — autorise l'écriture de consignes vers le matériel (v2). Voir §6.6.
- `soc_equaliser_enabled` (bool, défaut true) — pilotage indirect des batteries `controllable: false`. Voir §6.6.
- `soc_equaliser_max_w` (int, défaut 1500) — biais de puissance maximal appliqué au parc pilotable
- `soc_equaliser_kp_w_per_pct` (float, défaut 80.0) — gain proportionnel (W par % d'écart de SoC)
- `soc_equaliser_deadband_pct` (float, défaut 2.0) — demi-largeur de la bande morte de SoC
- `soc_equaliser_probe_step_w` (float, défaut 150.0) — pas de steering initial ; croît géométriquement tant que la batterie auto suit (voir §6.6)
- `tariff_config` (sous-section, voir §7.3)

> Les constantes `storm_mode_target_soc_pct` (défaut 95 %) et `storm_mode_lead_time_h` (défaut 6 h) sont
> pour l'instant codées en dur dans `const.py` et ne sont pas exposées dans le Config Flow.

---

## 6. Algorithmes et stratégies

### 6.1 Stratégies disponibles

Chaque stratégie produit une `Decision` typée :

```python
@dataclass
class Decision:
    battery_targets: dict[str, BatteryTarget]   # device_name → cible (SoC, fenêtre min/max, puissance préférée)
    grid_constraint: GridConstraint              # autorisations soutirage/injection (max_import_w, max_export_w)
    load_priorities: dict[str, int]              # nom load → priorité ajustée (None = pas d'opinion)
    confidence: float                             # 0.0–1.0, force de la recommandation
    rationale: str                                # message de debug exposé en sensor
```

L'**arbitrer** combine les décisions des stratégies actives selon l'ordre déclaré par l'utilisateur :

- **`battery_targets`** : la stratégie de plus haute priorité fixe la cible centrale. Les stratégies suivantes ne peuvent que **resserrer la fenêtre** (ex : `backup` impose un plancher SoC même si `cost_min` voudrait décharger plus bas). Une stratégie ne peut jamais élargir une fenêtre établie par une priorité supérieure.
- **`grid_constraint`** : **intersection** des contraintes de toutes les stratégies — la plus restrictive l'emporte (équivalent d'un AND logique sur les autorisations).
- **`load_priorities`** : **première opinion gagne** (*first-wins*) — pour chaque charge, la stratégie de plus haute priorité qui exprime une opinion (valeur non-`None`) remporte la décision. Les stratégies suivantes ne peuvent pas surpasser ni affiner cet avis. Une stratégie n'exprimant pas d'opinion sur une charge (valeur `None`) est simplement ignorée pour cette charge.

Le résultat de l'arbitrage est lui-même publié sous forme d'attributs lisibles (`sensor.solarbalance_dominant_strategy`, `sensor.solarbalance_arbitration_log`) pour transparence et debug.

| Stratégie          | Logique principale                                                                    |
| ------------------ | ------------------------------------------------------------------------------------- |
| `self_consumption` | Maximise consommation locale du PV. Charge si surplus, décharge sur soutirage.        |
| `cost_min`         | Charge en plage tarifaire basse, décharge en plage haute. Nécessite tarif configuré.   |
| `backup`           | Maintient un SoC plancher de réserve. Refuse décharge sous le plancher.               |
| `longevity`        | Pénalise les cycles profonds (paramètres explicites, voir ci-dessous).                |
| `peak_shaving`     | Empêche soutirage > seuil (% puissance souscrite). Décharge batterie en compensation. |
| `revenue_max`      | Si vente : injecte plutôt que de stocker quand prix de revente > coût d'opportunité.  |

**Paramètres `longevity` exposés** (avec valeurs par défaut différenciées par chimie) :

| Paramètre                       | LiFePO4 | NMC  | Plomb | Description                                       |
| ------------------------------- | ------- | ---- | ----- | ------------------------------------------------- |
| `longevity_soc_floor_pct`       | 20      | 30   | 50    | Plancher de décharge confortable                  |
| `longevity_soc_ceiling_pct`     | 95      | 85   | 90    | Plafond de charge confortable                     |
| `longevity_max_c_rate`          | 0.5     | 0.5  | 0.2   | Taux de charge/décharge max (× capacité utile)    |
| `longevity_temp_throttle_start` | 35°C    | 35°C | 35°C  | Température au-delà de laquelle réduire courants  |

Tous surchargeables par device dans la config YAML.

### 6.2 Répartition équilibrée — algorithme hybride

Pour N batteries de capacité `C_i` (kWh), SoC `s_i` (%) et puissance max `P_i^{max}` (W), on cherche à répartir une demande globale `P_total` (charge ou décharge) :

**Phase 1 — Pondération hybride** :

```
poids_capacité_i = C_i / Σ C_j
poids_équilibrage_i = f(s_i, s̄)   # f favorise les écarts au SoC moyen
poids_i = α · poids_capacité_i + (1 − α) · poids_équilibrage_i
```

avec `α ∈ [0, 1]` paramétrable (défaut 0.6 — légèrement favorable à la répartition par capacité).

- En **charge** : `f(s_i, s̄) ∝ max(0, s̄ − s_i + ε)` (les batteries en retard chargent plus).
- En **décharge** : `f(s_i, s̄) ∝ max(0, s_i − s̄ + ε)` (les batteries en avance déchargent plus).

**Phase 2 — Saturation** :

```
P_i = poids_i · P_total
si P_i > P_i^{max} : on plafonne et redistribue le résidu sur les non saturées
si batterie au plancher (décharge) ou au plafond (charge) : exclue, redistribution
```

Itération jusqu'à stabilité ou écart résiduel < 1%.

### 6.3 Régulation zéro injection (v1, software pur)

Approche **PI à hystérésis** sur la mesure du meter PDL :

```
erreur_t = mesure_pdl_t − consigne_zi
intégrale_t = clamp(intégrale_{t-1} + erreur_t · Δt, ±I_max)
correction = Kp · erreur_t + Ki · intégrale_t
P_charge_total = max(0, P_charge_actuelle + correction)
```

Cette correction de puissance globale est ensuite répartie selon §6.2.

**Régulateur unique (important)** : quand la zéro-injection est active, c'est **elle seule** qui régule le réseau — la cible agrégée vaut `P_parc_pilotable_actuelle + correction`. Les stratégies (`self_consumption`…) n'apportent alors qu'une **direction**/des fenêtres SoC, jamais une seconde annulation absolue de l'écart réseau. Sommer la cible absolue de `self_consumption` (`−net_grid`, gain ≈ 1) avec le delta PI (Kp) donnait un gain proportionnel cumulé > 1 et, combiné au **retard d'actionnement d'un tick**, un cycle limite à la fréquence du tick. Quand la ZI est désactivée (ou en mode tempête/override), c'est la cible absolue des stratégies qui pilote.

**Limite de pente (anti cycle-limite)** : la cible agrégée ne peut varier de plus de `max_ramp_w` (défaut 800 W) par tick. Garde-fou matériel contre les emballements quels que soient les gains ; `0` désactive la limite.

**Hystérésis** : zone morte autour de `consigne_zi ± hysteresis_w`. Pas d'action si la mesure y reste.

**Anti-windup** : intégrale bornée `±I_max` pour éviter l'accumulation pendant les périodes où une saturation matérielle empêche la correction.

**Tuning par défaut** :
- `Kp = 0.6`, `Ki = 0.05` (à valider expérimentalement)
- `tick = 10 s`
- Hystérésis = 50 W
- `max_ramp_w = 800 W/tick`

**Cas batteries pleines (saturation amont)** : si toutes les batteries sont au plafond et que du PV continue d'arriver, l'injection devient inévitable sans écrêtage. Trois scénarios par ordre de préférence :

1. **MPPT pilotable en puissance** (entité `power_set_entity` déclarée sur le rôle MPPT) → consigne réduite pour suivre la consommation.
2. **Onduleur supportant la régulation de production** (entité dédiée à déclarer en v2+) → consigne d'écrêtage envoyée.
3. **Aucun moyen d'écrêter** → bascule en mode `degraded_zi`. Notification persistante demandant à l'utilisateur d'agir manuellement (déconnexion physique, lancement manuel d'une charge non prioritaire). La consigne ZI reste publiée à titre indicatif.

### 6.4 Distribution du surplus aux charges pilotables

Soit `P_surplus` la puissance disponible après arbitrage batteries (surplus PV non absorbable, ou décharge dirigée vers les loads).

**Algorithme** :
1. Filtrer les charges éligibles (fenêtre horaire, contraintes daily, anti-court-cycle satisfait).
2. Trier par priorité (1 = servi en premier).
3. Pour chaque charge dans l'ordre :
   - **Modulante** : alloue `min(P_max, P_surplus)`, déduit du surplus. Si solde < `P_min`, charge non servie.
   - **Stepped** : choisit le palier le plus élevé tel que `palier.power_w ≤ P_surplus`. Déduit.
   - **On/off** : si `nominal_power_w ≤ P_surplus + tolérance` et anti-court-cycle OK, allume. Déduit `nominal_power_w`.
4. Charges avec `deadline_constraint` non satisfaite : remontées en priorité 0 (override) si on s'approche de la deadline et qu'il manque encore l'énergie requise — peut imposer un soutirage réseau si tarif l'autorise.

**Préférence aux modulantes** : à priorité égale, une modulante est servie avant une on/off (granularité fine d'absorption).

**Anti-court-cycle prédictif (v1.5)** : pour les charges on/off avec `min_on_duration_s` long (PAC, climatiseurs), introduire un champ `predictive_horizon_s` qui consulte la tendance court-terme (régression linéaire des 5 dernières minutes du surplus, ou prévision sub-horaire si disponible). Si la tendance prédit un retour sous le seuil avant `min_on_duration_s`, la charge n'est pas allumée. Évite les démarrages voués à être annulés.

### 6.5 Mode tempête

Déclencheurs (composables, OU logique) :
- Vigilance Météo-France ≥ niveau utilisateur sur les phénomènes configurés.
- Override manuel `storm_mode = on`.
- Heuristique : prévision PV J+1 < seuil ET soutirage prévu élevé (peut être désactivée).

**Configuration par déclencheur** (chaque ligne définit un trigger indépendant ; la cible la plus exigeante l'emporte si plusieurs sont actifs) :

```yaml
storm_triggers:
  - phenomenon: wind            # vent violent
    min_level: orange           # yellow | orange | red
    target_soc_pct: 90
    lead_time_h: 6
  - phenomenon: thunderstorm
    min_level: red
    target_soc_pct: 100
    lead_time_h: 12
  - phenomenon: snow
    min_level: orange
    target_soc_pct: 95
    lead_time_h: 24
  - phenomenon: flood
    min_level: orange
    target_soc_pct: 95
    lead_time_h: 24
```

Chaque entrée mappe vers une entité Météo-France distincte (résolue automatiquement à partir du département configuré).

**Action** :
- SoC cible relevé à la valeur la plus élevée parmi les triggers actifs.
- Charge anticipée commencée `lead_time_h` heures avant l'heure de pointe ou de coupure prédite (utilise la prévision PV pour positionner l'effort sur la fenêtre de production maximale ; à défaut, charge linéaire jusqu'au déclenchement prévu).
- Charges pilotables non critiques : différées si soutirage nécessaire.

**Sortie du mode tempête (hystérésis)** : à la levée de la vigilance, le mode tempête reste actif pendant `storm_mode_release_hysteresis_h` (défaut 1 h) avant de revenir au mode normal. Évite les oscillations sur des vigilances qui clignotent à la limite du seuil.

### 6.6 Batteries non pilotables et équilibrage indirect

Certaines batteries remontent leur état (SoC, puissance) mais n'offrent **aucun moyen de commander** leur charge/décharge via Home Assistant — le seul mode possible est leur automatisme interne. On les déclare `controllable: false` (voir `docs/device-mapping.md`).

**Lecture seule, exclusion du pilotage** : une telle batterie alimente normalement le snapshot (son SoC/puissance comptent dans `baseline_consumption` et l'équilibre réseau), mais elle est **exclue du `BalancingController`** : elle ne reçoit jamais de consigne et n'apparaît pas dans `setpoint_charge/discharge_per_battery_w`.

**Équilibreur de SoC indirect** (`core/controllers/soc_equaliser.py`) : un correcteur proportionnel amène le SoC de la batterie automatique vers le SoC moyen du parc pilotable, en ajoutant un **biais** au `total_power_w` distribué par le `BalancingController` :

- biais < 0 → le parc pilotable décharge davantage → surplus AC → la batterie automatique charge ;
- biais > 0 → le parc pilotable charge davantage → déficit AC → la batterie automatique décharge.

Le biais vise `-kp × (soc_cible − soc_auto)` (bande morte `soc_equaliser_deadband_pct`, garde sur les bornes SoC propres de la batterie auto), mais il est borné par **trois limites imbriquées** pour ne jamais pousser plus que la batterie auto ne peut encaisser (sinon l'excédent part au réseau et fait osciller la zéro-injection) :

1. **Capacité AC** : `ac_charge_limit_w` (défaut = `max_charge_power_w`) en charge, `max_discharge_power_w` en décharge. Plafond physique.
2. **Autorisation adaptative** : démarre à `soc_equaliser_probe_step_w` (petit pas) et croît géométriquement (×1.5/tick) tant que le steering garde sa direction — petits pas d'abord, de plus en plus grands —, plafonnée par la capacité AC.
3. **Repli sur mesure** : si la batterie auto bouge **à contre-sens** de la demande (lu sur `power_entity`), l'autorisation est réinitialisée au petit pas (on ne force pas une batterie qui fait autre chose).

L'agrégat est ensuite borné à `±soc_equaliser_max_w`. **Sûreté** : les boucles zéro-injection / autoconsommation du même tick maintiennent le réseau à sa consigne ; combiné aux trois bornes ci-dessus, le biais ne crée pas d'excédent vers le réseau. Ce transfert paie deux conversions supplémentaires : compromis rendement ↔ homogénéité des SoC.

**Pilotage actif (v2, première étape — décharge seule)** : lorsque `active_control_enabled` est vrai globalement et au niveau d'un appareil (`active_control_enabled: true` + `discharge_power_setpoint_entity`), l'adapter `ActiveControlPublisher` écrit les consignes de **décharge** issues du `BalancingController` vers les entités `number`/`input_number` déclarées. Seule la décharge est pilotée pour l'instant : c'est la décharge du parc pilotable qui, via le bus AC, contrôle indirectement la charge de la batterie automatique. L'écriture est suspendue en mode dégradé (les consignes gérées sont remises à 0 W). C'est le **seul** composant autorisé à écrire vers le matériel utilisateur.

---

## 7. Sources externes

### 7.1 Prévisions PV

Réutilisation des intégrations HA existantes :
- **Solcast** (HACS, gratuit limité, recommandé)
- **Forecast.Solar** (officielle HA)
- **OpenMeteo Solar** (officielle HA)

L'utilisateur déclare dans le Config Flow l'entité produisant la prévision (typiquement `sensor.solcast_pv_forecast_forecast_today`). SolarBalance lit la courbe horaire et l'utilise dans les stratégies prédictives (cost_min, backup, mode tempête).

**Dégradation** : si l'entité est indisponible, les stratégies prédictives basculent sur une **prévision plate** (moyenne des 7 derniers jours, lue dans l'historique HA) avec un avertissement.

### 7.2 Vigilance météo

Intégration officielle **Météo-France** dans HA expose des entités de vigilance par département. SolarBalance déclare une dépendance optionnelle vers `sensor.meteofrance_<dept>_<phenomene>_warning`.

Phénomènes pris en compte par défaut :
- Vent violent
- Orages
- Neige-verglas
- Inondations (utile pour anticipation longue)

L'utilisateur configure :
- Liste des phénomènes surveillés
- Niveau seuil (jaune / orange / rouge)
- Action associée (mode tempête uniquement, ou mode tempête + verrou décharge)

### 7.3 Tarifs

Modèle tarifaire générique séparant import et export, avec types interchangeables :

```yaml
tariff_config:
  currency: EUR

  import:
    type: scheduled                # fixed | scheduled | external_entity
    default_price: 0.25            # €/kWh hors plages spécifiques
    schedules:
      - name: HC
        days: [mon, tue, wed, thu, fri, sat, sun]
        windows:
          - start: "22:00"
            end: "06:00"
        price: 0.18
      - name: HP
        days: [mon, tue, wed, thu, fri, sat, sun]
        windows:
          - start: "06:00"
            end: "22:00"
        price: 0.27

  export:
    type: fixed                    # fixed | scheduled | external_entity
    price: 0.10
```

**Types disponibles pour `import` et `export`** :
- `fixed` : un seul prix `price`.
- `scheduled` : `default_price` + `schedules` (plages avec jours et fenêtres).
- `external_entity` : lit le prix instantané depuis une entité HA (ex : `sensor.electricity_price_now` alimentée par une intégration tierce). Préparé pour Tempo, EPEX, Octopus en v2.

**Règle de chevauchement** : si plusieurs schedules matchent l'instant courant, **l'ordre de déclaration tranche, premier match gagnant**. Cette règle est volontairement simple et prévisible (pas de calcul de "spécificité" implicite). À l'utilisateur d'ordonner ses plages les plus spécifiques en premier.

**Évolutions v2** :
- Connecteurs natifs Tempo (RTE), EPEX spot via Nordpool, Octopus, Barry.
- Calendrier prévisionnel (prix J+1 connus la veille à 14h pour EPEX) pour optimisation prédictive.

### 7.4 Mesure réseau

- **v1** : Shelly 3EM (ou tout meter exposant une entité de puissance signée au PDL).
- **Triphasé v2** : agrégation des 3 phases par défaut (la régulation ZI vise la somme algébrique). Une option `per_phase_zi: true` sera disponible pour les contextes contractuels stricts imposant une absence d'injection sur chaque phase indépendamment ; cette option dégrade généralement l'autoconsommation et n'est activée qu'en cas de besoin documenté.

---

## 8. Modes de fonctionnement et overrides

### 8.1 Modes globaux

| Mode               | Description                                                            | Déclencheur          |
| ------------------ | ---------------------------------------------------------------------- | -------------------- |
| `normal`           | Stratégies actives selon priorités utilisateur                         | Défaut               |
| `storm`            | Charge prioritaire jusqu'au SoC tempête, charges non critiques différées | Vigilance ou manuel |
| `vacation`         | SoC stable autour d'une valeur cible, charges désactivées              | Manuel               |
| `paused`           | HEMS en sommeil, ne publie plus de consignes                           | Manuel               |
| `degraded`         | Une ou plusieurs entités critiques manquantes — voir §9                | Automatique          |
| `manual_override`  | Une consigne forcée court-circuite l'arbitrage                         | Service appelé       |

### 8.2 Overrides utilisateur (services HA)

```yaml
service: solarbalance.pause
# Met le HEMS en mode paused

service: solarbalance.resume
# Sort du mode paused

service: solarbalance.force_charge
data:
  target_soc_pct: 100
  power_w: 2000          # optionnel, défaut max
  deadline: "2026-05-04T22:00:00"   # optionnel
# Force la charge jusqu'à cible ou deadline

service: solarbalance.force_discharge
data:
  target_soc_pct: 30
  power_w: 1500

service: solarbalance.set_mode
data:
  mode: storm | vacation | normal

service: solarbalance.activate_storm_mode
data:
  duration_h: 24  # optionnel — sortie automatique après N heures
```

Tous ces services sont également exposés en boutons et inputs sur la carte Lovelace.

### 8.3 Reprise après redémarrage

Les onduleurs gardent leur dernière consigne (établie par leur logique propre ou par le HEMS en v2+). Au redémarrage de HA / SolarBalance :
1. Lecture de l'état persistant.
2. Restauration du mode actif au moment de l'arrêt.
3. Recalcul immédiat d'une consigne dès la première complétion du snapshot.

**État persistant via `Store` HA, sauvegardé à chaque changement significatif et au minimum toutes les 5 minutes** :

- **Mode actif** : `normal` / `storm` / `vacation` / `paused` / `manual_override`
- **Overrides en cours et leurs deadlines** : `force_charge`, `force_discharge`, `activate_storm_mode` avec leurs paramètres et heure d'expiration
- **Intégrale du PI zéro injection** : pour éviter un saut de consigne au redémarrage
- **Statistiques journalières par load** : runtime cumulé du jour, énergie cumulée du jour (réinitialisées à minuit local)
- **État anti-court-cycle des loads** : timestamp du dernier ON et du dernier OFF par load, pour vérifier `min_on_duration_s` / `min_off_duration_s` au tick suivant
- **Sortie de mode tempête en cours** : timestamp de levée de la dernière vigilance pour gérer l'hystérésis `storm_mode_release_hysteresis_h`
- **Snapshot précédent** (entrée + décision) : utile pour calcul de dérivées et debug, conservé en mémoire (non persistant strictement nécessaire mais recommandé)

**Versioning** : la structure de l'état persistant est versionnée (`store_version: int`). Une migration est appelée si la version du composant a évolué entre les redémarrages, avec fallback `mode = normal` et purge des overrides en cas d'incompatibilité.

---

## 9. Failsafe, watchdog et mode dégradé

### 9.1 Watchdog par entité

Chaque entité mappée a un **timeout d'inactivité** (défaut 5 minutes, configurable par device). Si pas d'update depuis le timeout :

| Type d'entité                  | Action                                                                            |
| ------------------------------ | --------------------------------------------------------------------------------- |
| `meter` PDL                    | Bascule en `degraded`. Zéro injection désactivé. Notification critique.           |
| `battery.soc_entity`           | Device exclu du pool. Si toutes les batteries exclues → `degraded`.               |
| `battery.power_entity`         | Device exclu du pool de balancing actif (lecture SoC seule conservée).            |
| `mppt.power_entity`            | Production de ce MPPT estimée à 0. Décisions prudentes (PV non comptabilisé).     |
| `inverter.ac_output_power`     | Charges de cet onduleur supposées à 0. Avertissement.                             |
| Source externe (météo, prévision) | Stratégie associée bascule en mode dégradé documenté (§7.1, §7.2).             |

### 9.2 Mode dégradé

Comportement par défaut en mode dégradé :
- Désactivation des optimisations prédictives (cost_min, mode tempête anticipé).
- Conservation de la régulation zéro injection si meter PDL OK.
- Conservation de la répartition charge/décharge sur batteries restantes.
- Notification persistante dans HA + indication visuelle sur la carte.

### 9.3 Sécurité

- **Pas d'écriture en v1** : le risque matériel est nul tant que F14 n'est pas implémentée.
- **Bornes physiques respectées** : toute consigne calculée passe par un clamp final aux limites physiques déclarées (`soc_min_pct`, `soc_max_pct`, `max_charge_power_w`…).
- **Logs structurés** : chaque décision tracée avec le snapshot d'entrée pour debugging post-mortem.

---

## 10. Interface utilisateur

### 10.1 Stratégie d'affichage v1 — composition de cartes existantes

Plutôt que développer une carte custom dès la v1, SolarBalance s'appuie sur des cartes HACS matures et fournit des **configurations Lovelace prêtes à l'emploi** (`examples/lovelace/*.yaml`) que l'utilisateur copie-colle.

**Vue principale — flux d'énergie** :
- Réutilisation de **`power-flow-card-plus`** (HACS), carte Sankey/diagramme de flux mature et largement adoptée dans la communauté HA.
- SolarBalance expose les sensors agrégés nécessaires (PV total, batterie nette, grid, baseline) ; la carte les consomme directement.
- Configuration exemple fournie dans `examples/lovelace/power-flow.yaml` avec mapping vers les entités SolarBalance.

**Vue décisions** :
- Tableau via `entities` standard ou `mushroom-template-card` pour la mise en forme.
- Affiche : mode actif, priorité dominante, consignes calculées par device, écart consigne/réel, dernière `rationale` de l'arbitrer.

**Vue prévisions** :
- **`apexcharts-card`** (HACS) pour la courbe PV prévue / réalisée 24 h glissantes, plages tarifaires en arrière-plan, vigilance météo en annotation.

**Vue overrides** :
- **`mushroom-*`** cards pour les boutons (pause, force charge, mode tempête) et inputs (sliders SoC, deadlines).
- Mappés sur les services HA exposés par le composant.

### 10.2 Carte custom v1.5 — `solarbalance-card`

Une carte dédiée sera développée en v1.5 pour les besoins spécifiques au HEMS que les cartes génériques couvrent mal :
- Affichage des consignes calculées **superposé aux flux réels** (flèches doublées : réel et théorique, écart visualisé).
- Vue de l'arbitrage : qui a décidé quoi, par stratégie, avec scores de confiance.
- Toggle "advanced view" pour exposer les `Decision` partielles avant fusion (debug / pédagogie).

Stack technique pressentie : Lit + TypeScript, D3 pour le Sankey custom, distribution via HACS frontend resource. Décision technique formalisée au moment du développement v1.5.

### 10.3 Dépendances frontend recommandées (v1)

- **`power-flow-card-plus`** (HACS) — diagramme de flux énergétique
- **`apexcharts-card`** (HACS) — graphes prévisions / historique
- **`mushroom`** (HACS) — esthétique des contrôles rapides

Ces dépendances sont **recommandées et documentées comme telles dans le README**, mais l'intégration fonctionne sans (toutes les entités sont exposées et utilisables avec n'importe quelle carte standard).

### 10.4 Entités HA exposées par SolarBalance

**Sensors** :
- `sensor.solarbalance_mode` — mode actif
- `sensor.solarbalance_dominant_strategy` — stratégie dominante au dernier tick d'arbitrage
- `sensor.solarbalance_pv_power` — production PV agrégée
- `sensor.solarbalance_battery_soc_avg` — SoC moyen pondéré (par capacité utilisable)
- `sensor.solarbalance_battery_power` — puissance batterie nette (signe = charge_positive)
- `sensor.solarbalance_grid_power` — relais du PDL
- `sensor.solarbalance_baseline_consumption` — consommation de fond déduite (§3.4)
- `sensor.solarbalance_pv_energy_today` — énergie PV produite sur la journée (kWh)
- `sensor.solarbalance_grid_import_today` — énergie soutirée sur la journée (kWh)
- `sensor.solarbalance_<device>_setpoint_charge` — consigne charge calculée
- `sensor.solarbalance_<device>_setpoint_discharge` — consigne décharge calculée
- `sensor.solarbalance_<load>_setpoint_load` — consigne par load *(v1.0)*
- `sensor.solarbalance_zero_injection_error` — écart entre mesure et consigne ZI *(v1.0)*
- `sensor.solarbalance_arbitration_log` — dernier rationale de l'arbitrer (texte court) *(v1.0)*

**Binary sensors** :
- `binary_sensor.solarbalance_storm_mode`
- `binary_sensor.solarbalance_weather_warning`
- `binary_sensor.solarbalance_degraded`
- `binary_sensor.solarbalance_zero_injection_active` *(v1.0)*
- `binary_sensor.solarbalance_zi_degraded` — ZI active mais incapable d'écrêter (cas batteries pleines, §6.3) *(v1.0)*

**Selects / Numbers / Switches** :
- `select.solarbalance_hems_mode` (normal, storm, vacation, paused)
- `number.solarbalance_zi_setpoint`
- `number.solarbalance_zi_hysteresis`
- `switch.solarbalance_zero_injection`

---

## 11. Roadmap par versions

### v0.1 — Squelette

- Custom component installable
- Config Flow basique (paramètres globaux)
- Schéma YAML validé
- Lecture des entités, agrégation, snapshot
- Configuration Lovelace exemple basée sur `power-flow-card-plus`

### v0.5 — Fonctions cœur

- Stratégie `self_consumption` complète
- Balancing hybride
- Zéro injection (PI software, lecture seule)
- Watchdog et mode dégradé
- Overrides via services
- Persistance d'état

### v1.0 — MVP partagé

- Stratégies `cost_min`, `backup`, `peak_shaving`, `longevity`
- Tarif générique multi-plages avec import/export séparés
- Prévisions PV (Solcast + Forecast.Solar)
- Vigilance Météo-France et mode tempête (avec hystérésis de sortie)
- Distribution surplus aux charges (3 types)
- Configurations Lovelace prêtes à l'emploi (`power-flow-card-plus` + `apexcharts-card` + `mushroom`)
- Documentation utilisateur, README, exemples
- Tests unitaires du cœur > 70% couverture
- Publication HACS

### v1.5 — Stabilisation et carte custom

- Retours utilisateurs intégrés
- Stratégie `revenue_max`
- Triphasé fonctionnel (agrégé par défaut, option `per_phase_zi`)
- **Carte custom `solarbalance-card`** (Lit + TypeScript, Sankey D3) avec affichage consignes vs réel
- Anti-court-cycle prédictif des charges on/off
- Profils marque préremplis assistés (Ecoflow, Jackery, Victron — sur la base de mappings communautaires)

### v2.0 — Pilotage actif

- Écriture sur les onduleurs (au fil de la disponibilité dans les intégrations)
- Tarifs dynamiques natifs (Tempo, Nordpool/EPEX)
- Optimisation prédictive multi-horaire (programmation dynamique simple)

### v3.0+ — Au-delà

- Optimisation avancée (MILP, MPC) sur horizon 24-48h
- Ouverture aux ajustements réseau (effacement, signaux distributeur)
- Multi-site / agrégation
- Lib `pyhems` extraite pour usage hors HA

---

## 12. Conventions du projet

### 12.1 Nom et identifiants

- **Nom canonique** : `SolarBalance` (CamelCase) ou `solarbalance` (technique)
- **Domaine HA** : `solarbalance`
- **Repo GitHub suggéré** : `solarbalance/solarbalance` ou `<user>/ha-solarbalance`
- **HACS category** : Integration + Frontend (deux ressources distinctes)

### 12.2 Licence et contributions

- **Licence** : Apache 2.0 (avec NOTICE)
- **Code of Conduct** : Contributor Covenant 2.1
- **Workflow** : PR via fork, revue obligatoire, CI verte avant merge
- **Issue templates** : bug / feature / question / device support

### 12.3 Qualité de code

- Python ≥ 3.14 (alignement HA core)
- **Typage strict** sur le cœur (`mypy --strict` sur `core/`)
- **Linting** : ruff
- **Formatting** : ruff format (équivalent black)
- **Tests** : pytest + pytest-homeassistant-custom-component
- **CI** : GitHub Actions (lint, type, tests, build manifest)
- **Logs** : `_LOGGER` standard HA, niveaux respectés

### 12.4 Documentation

- `README.md` : présentation, install, exemple minimal, screenshot
- `SPECIFICATIONS.md` : ce document
- `docs/` :
  - `getting-started.md` — premier setup en 15 minutes
  - `device-mapping.md` — guide de mapping par type d'équipement
  - `strategies.md` — détails des algorithmes
  - `troubleshooting.md`
  - `api.md` — services et entités exposées
- Exemples de configuration commentés dans `examples/`

### 12.5 Internationalisation

- Strings localisées (FR + EN dès la v1.0).
- Code et identifiants en anglais. Documentation FR + EN.

---

## 13. Glossaire

| Terme              | Définition                                                                       |
| ------------------ | -------------------------------------------------------------------------------- |
| HEMS               | Home Energy Management System                                                    |
| MPPT               | Maximum Power Point Tracker — régulateur de charge solaire                       |
| SoC                | State of Charge — état de charge d'une batterie en %                             |
| DoD                | Depth of Discharge — profondeur de décharge                                      |
| EPS                | Emergency Power Supply — sortie de secours en îlotage                            |
| PDL                | Point De Livraison — interface du compteur Linky / abonné                        |
| Zéro injection     | Régulation empêchant tout export d'énergie vers le réseau                        |
| Peak shaving       | Écrêtage de pointe — limiter le soutirage instantané sous un seuil               |
| Tempo              | Tarif EDF avec jours bleus / blancs / rouges et plages HP/HC                     |
| Surplus            | Production PV non immédiatement consommée et non absorbée par les batteries      |
| Tick               | Cycle d'orchestration du HEMS (lecture, calcul, publication)                     |
| Snapshot           | Image instantanée de l'état du système à un tick donné                           |
| Device             | Conteneur de configuration regroupant les entités d'un équipement physique       |
| Rôle               | Capacité fonctionnelle portée par un device (battery, mppt, inverter, meter)     |
| Load               | Charge électrique pilotable (on/off, paliers, modulant)                          |
| Stratégie          | Module produisant des décisions selon un objectif (autoconsommation, coût…)      |
| Arbitrer           | Composant combinant les décisions de plusieurs stratégies selon priorités        |
