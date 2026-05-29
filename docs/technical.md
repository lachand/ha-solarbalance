# SolarBalance — Documentation Technique

> Version cible : **0.1.x (v1)**  
> Home Assistant : **2026.1+** — Python : **3.14+**

---

## Table des matières

1. [Vue d'ensemble de l'architecture](#1-vue-densemble-de-larchitecture)
2. [Boucle d'orchestration](#2-boucle-dorchestration)
3. [Modèles de données](#3-modèles-de-données)
4. [Stratégies d'optimisation](#4-stratégies-doptimisation)
5. [Algorithme d'arbitrage](#5-algorithme-darbitrage)
6. [Contrôleur de balancement hybride](#6-contrôleur-de-balancement-hybride)
7. [Régulateur PI zéro-injection](#7-régulateur-pi-zéro-injection)
8. [Planificateur prédictif 24h](#8-planificateur-prédictif-24h)
9. [Dispatch des charges pilotables](#9-dispatch-des-charges-pilotables)
10. [Adaptateurs Home Assistant](#10-adaptateurs-home-assistant)
11. [Gestion des modes et dégradation gracieuse](#11-gestion-des-modes-et-dégradation-gracieuse)

---

## 1. Vue d'ensemble de l'architecture

SolarBalance est structuré en trois couches strictement isolées :

```
┌─────────────────────────────────────────────────────────┐
│            Home Assistant platforms                      │
│   sensor · binary_sensor · select · number · switch      │
│   config_flow · coordinator                              │
└──────────────────────────┬──────────────────────────────┘
                           │  via adapters uniquement
┌──────────────────────────▼──────────────────────────────┐
│                   Adapters (bridge)                      │
│   entity_reader · decision_publisher · forecast          │
│   watchdog                                               │
└──────────────────────────┬──────────────────────────────┘
                           │  dataclasses purs seulement
┌──────────────────────────▼──────────────────────────────┐
│                      Core (pur Python)                   │
│   models · arbitrer · strategies · controllers · tariff  │
│   planner · active_control                               │
└─────────────────────────────────────────────────────────┘
```

**Règle d'isolation** : `core/` ne contient aucun import `homeassistant.*`. Toute donnée provenant de HA transite sous forme de dataclasses (`Snapshot`, `Decision`, …). Cette séparation permet :
- Tests unitaires rapides sur le core sans démarrer HA.
- Extraction future en bibliothèque standalone.
- Simulation hors-ligne.

---

## 2. Boucle d'orchestration

Le `SolarBalanceCoordinator` (sous-classe de `DataUpdateCoordinator`) pilote une boucle cadencée par `tick_interval_s` (défaut 10 s).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  tick N                                                                     │
│                                                                             │
│  1. EntityReader.snapshot()  ──────────────────────►  Snapshot              │
│                                                                             │
│  2. Sanity checks                                                           │
│     ├─ baseline_consumption < -100 W × 3 ticks → notification               │
│     └─ watchdog (entités critiques stales) → mode DEGRADED                  │
│                                                                             │
│  3. Storm mode logic                                                        │
│     ├─ weather_warning → activer STORM                                      │
│     └─ warning cleared + hysteresis → retour NORMAL                        │
│                                                                             │
│  4. Tariff resolution → Snapshot enrichi (prix import/export)               │
│                                                                             │
│  5a. [MANUAL_OVERRIDE] → Decision forcée (charge/décharge)                  │
│  5b. [autres modes]                                                         │
│       ├─ Strategy_1.compute(snapshot) → Decision_1                         │
│       ├─ Strategy_2.compute(snapshot) → Decision_2                         │
│       ├─ ...                                                                │
│       └─ Arbiter.arbitrate([D1, D2, ...]) → ArbitrationResult               │
│                                                                             │
│  6. ZeroInjectionController.step() → correction_w                          │
│     (mono-phase ou tri-phase selon config)                                  │
│                                                                             │
│  7. BalancingController.allocate(total_w) → per-battery setpoints           │
│                                                                             │
│  8. LoadDispatchController.dispatch(surplus_w) → commandes loads            │
│                                                                             │
│  9. DecisionPublisher.publish(result) → mise à jour entités HA              │
│                                                                             │
│  10. return Snapshot → coordinateur notifie les entités                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Performance** : chaque tick doit compléter en < 100 ms pour un setup 2 batteries × 24 slots DP. Le DP du planificateur s'exécute en dehors du tick principal (tâche différée).

---

## 3. Modèles de données

### 3.1 Hiérarchie de configuration

```
Device
 ├─ BatteryRole    capacity_kwh, soc_min/max, power limits, entities
 ├─ MpptRole       peak_power_w, power_entity, feeds
 └─ InverterRole   nominal_power_w, EPS capability

Meter             kind (PDL/PV/CONSUMPTION/SUBCIRCUIT), phases, entities

Load              control_type (on_off/stepped/modulating), priority,
                  constraints (time_window, deadline, daily caps)
```

### 3.2 Convention de signe

| Grandeur | Convention interne | Note |
|---|---|---|
| Puissance batterie (`BatteryState.power_w`) | **positif = charge** | Normalisé depuis `power_sign_convention` déclarée par l'utilisateur |
| Puissance réseau (`grid_power_w`) | **positif = soutirage** | Convention PDL (EDF) |
| `preferred_power_w` dans `BatteryTarget` | positif = charger | Intent de la stratégie |
| `correction_w` du PI ZI | positif = charger davantage | Correction ajoutée à la puissance agrégée |

### 3.3 Snapshot — état temps réel du système

```python
Snapshot
 ├─ timestamp          datetime
 ├─ grid_power_w       float   # positif = soutirage
 ├─ batteries          tuple[BatteryState, ...]
 ├─ mppts              tuple[MpptState, ...]
 ├─ inverters          tuple[InverterState, ...]
 ├─ loads              tuple[LoadState, ...]
 ├─ pv_forecast_now_w  float | None
 ├─ weather_warning_active bool
 ├─ current_import_price   float | None  # €/kWh
 ├─ current_export_price   float | None
 └─ grid_power_l1/l2/l3_w  float | None  # triphasé

# Propriétés calculées
baseline_consumption_w = grid_power + pv_total - battery_total - loads_total
```

La `baseline_consumption_w` représente la **consommation non pilotable** (fond de puissance). Une valeur négative persistante signale une erreur de convention de signe.

### 3.4 Capacité utile par chimie

| Chimie | Ratio de capacité utile |
|---|---|
| LiFePO4 | 95 % |
| NMC | 85 % |
| Plomb-acide | 50 % |
| Autre | 90 % |

Peut être surchargé par `usable_capacity_kwh` explicite dans `BatteryRole`.

---

## 4. Stratégies d'optimisation

Toutes les stratégies héritent de `Strategy` et implémentent `compute(snapshot) -> Decision`. Elles sont **sans état** et sans effet de bord.

### 4.1 Tableau récapitulatif

| Stratégie | Objectif | Paramètres | Contrainte grid |
|---|---|---|---|
| `self_consumption` | Maximiser l'autoconsommation | — | `max_export_w = 0` |
| `cost_min` | Minimiser le coût électrique | `cheap_threshold`, `expensive_threshold`, `charge_soc_target_pct` | neutre |
| `backup` | Maintenir une réserve d'autonomie | `reserve_soc_pct` (défaut 30 %) | — |
| `longevity` | Préserver la vie de la batterie | `override_soc_min/max_pct` (optionnel) | — |
| `peak_shaving` | Écrêter les pointes de soutirage | `max_import_w` | `max_import_w` |
| `revenue_max` | Arbitrage revente / achat | `export_premium`, `cheap_import_threshold` | neutre |

### 4.2 Self-consumption

```
net_grid = snapshot.grid_power_w          # positif si on importe

preferred_power_w = -net_grid             # exporte → charger, importe → décharger
max_export_w = 0                          # interdire l'injection réseau
```

**Exemple** : si le réseau exporte 500 W (production PV excédentaire), `preferred_power_w = +500 W` → batteries se chargent de cet excédent.

### 4.3 Cost-min

```
price = snapshot.current_import_price

if price <= cheap_threshold:
    preferred = CHARGE vers charge_soc_target_pct
elif price >= expensive_threshold:
    preferred = DISCHARGE depuis discharge_soc_floor_pct
else:
    preferred = None  # pas d'opinion, confidence=0.5
```

### 4.4 Backup

Impose un plancher de SoC plus élevé. Comme l'arbitre ne fait que **restreindre** les fenêtres SoC, ce plancher est infranchissable par les stratégies moins prioritaires.

```
soc_min = max(reserve_soc_pct, device.battery.soc_min_pct)
```

### 4.5 Longevity

Rétrécit la fenêtre SoC pour réduire le stress électrochimique :

| Chimie | SoC min recommandé | SoC max recommandé |
|---|---|---|
| LiFePO4 | 20 % | 90 % |
| NMC | 20 % | 85 % |
| Plomb-acide | 30 % | 80 % |
| Autre | 20 % | 85 % |

La stratégie ne **jamais élargit** au-delà des bornes utilisateur (`soc_min_pct`, `soc_max_pct`).

### 4.6 Peak-shaving

Émet uniquement une `GridConstraint(max_import_w=X)`. L'arbitre intersecte avec les autres contraintes. Le contrôleur de balancement est responsable de décharger suffisamment pour satisfaire la contrainte.

### 4.7 Revenue-max

```
if export_price > import_price + export_premium:
    preferred = DISCHARGE
elif import_price < cheap_import_threshold:
    preferred = CHARGE
else:
    confidence = 0.5  # abstention
```

---

## 5. Algorithme d'arbitrage

L'`Arbiter` fusionne N décisions (dans l'ordre des stratégies, de la plus prioritaire à la moins prioritaire) en une seule décision consolidée.

### 5.1 Fusion des battery targets

Pour chaque batterie référencée dans au moins une décision :

```
soc_min = max(soc_min_1, soc_min_2, ...)   # borne la plus haute
soc_max = min(soc_max_1, soc_max_2, ...)   # borne la plus basse
preferred_w = première opinion non-None (priorité décroissante)

# Cas dégénéré : soc_min > soc_max (contraintes contradictoires)
→ collapse au midpoint = (soc_min + soc_max) / 2
```

### 5.2 Fusion des grid constraints

Intersection (AND le plus restrictif) :

```
max_import_w  = min(toutes les max_import_w non-None)
max_export_w  = min(toutes les max_export_w non-None)
```

### 5.3 Fusion des priorités de charge

Moyenne pondérée avec décroissance exponentielle par rang de stratégie :

$$w_r = 2^{-(r-1)} \quad (r=1 \to 1.0,\ r=2 \to 0.5,\ r=3 \to 0.25, \ldots)$$

$$\text{priorité}_{\text{charge}} = \frac{\sum_r w_r \cdot p_{r,\text{charge}}}{\sum_r w_r}$$

### 5.4 Confidence et rationale

```
confidence  = min(confidence_1, ..., confidence_N)
rationale   = concat("[strategy_1] rationale_1 | [strategy_2] rationale_2 | ...")
dominant_strategy = strategies[0].kind
```

---

## 6. Contrôleur de balancement hybride

Le `BalancingController` distribue une puissance agrégée $P_{\text{total}}$ (positive = charge) entre N batteries hétérogènes.

### 6.1 Poids hybrides

$$w_i = \alpha \cdot w_{\text{cap},i} + (1-\alpha) \cdot w_{\text{eq},i}$$

**Poids capacité** (alpha = 1 → pur proportionnel) :
$$w_{\text{cap},i} = \frac{C_i}{\sum_j C_j}$$

**Poids égalisation SoC** (alpha = 0 → rattrapage des batteries en retard) :
$$w_{\text{eq},i} = \max\!\left(0,\ \overline{\text{SoC}} - \text{SoC}_i + \varepsilon\right) \quad \text{(en charge)}$$
$$w_{\text{eq},i} = \max\!\left(0,\ \text{SoC}_i - \overline{\text{SoC}} + \varepsilon\right) \quad \text{(en décharge)}$$

avec $\varepsilon = 10^{-3}$ pour éviter les poids nuls à SoC identiques.

Valeur par défaut : **alpha = 0.6** (60 % capacité, 40 % égalisation).

### 6.2 Boucle d'allocation itérative

```
eligible = batteries non saturées, disponibles, pas en dwell anti-court-cycle
remaining = P_total

while |remaining| > 1 W et iterations < 32:
    weights = compute_weights(eligible, charging=(remaining > 0))
    pour chaque batterie i:
        share = remaining × (w_i / Σw)
        proposed = per_battery[i] + share
        clamped  = clamp(proposed, -max_discharge_w, +max_charge_w)
        per_battery[i] = clamped
        si |clamped - proposed| > 1 W → batterie saturée → retirer d'eligible

    remaining = P_total - Σper_battery
    si aucune saturation → break

return BalancingResult(per_battery_w, unallocated_w, iterations)
```

**Convergence** : en pratique 2–4 itérations suffisent. La borne de 32 itérations évite les boucles infinies théoriques (batteries toutes saturées sauf une).

### 6.3 Garde anti-court-cycle

Lors d'un changement de direction (charge → décharge ou vice-versa), la batterie est maintenue à 0 W pendant `min_dwell_s` (défaut 60 s). Cela évite les oscillations de charge/décharge causées par des fluctuations de puissance réseau autour de 0 W.

---

## 7. Régulateur PI zéro-injection

Le `ZeroInjectionController` maintient la puissance réseau à un setpoint (typiquement 0 W) en calculant une correction à appliquer à la puissance agrégée des batteries.

### 7.1 Équations discrètes

À chaque tick (période $\Delta t$) :

$$e[k] = P_{\text{grid}}[k] - P_{\text{setpoint}}$$

**Zone morte** (hysteresis) :
$$\text{si}\ |e[k]| \leq H_{\text{hyst}} \Rightarrow \text{correction} = 0,\ \text{in\_deadband} = \text{True}$$

**Accumulateur intégral** (avec anti-windup) :
$$I[k] = \text{clamp}\!\left(I[k-1] + e[k] \cdot \Delta t,\ -I_{\max},\ +I_{\max}\right)$$

**Correction** (signe : positif → charger davantage) :
$$\text{correction}[k] = -\left(K_p \cdot e[k] + K_i \cdot I[k]\right)$$

**Paramètres par défaut** :

| Paramètre | Valeur | Unité |
|---|---|---|
| $K_p$ | 0.6 | — |
| $K_i$ | 0.05 | 1/s |
| $H_{\text{hyst}}$ | 50 | W |
| $I_{\max}$ | 1 000 000 | W·s |

### 7.2 Variante triphasée

Le `PerPhaseZeroInjectionController` instancie trois boucles PI indépendantes (L1, L2, L3). La `correction_w` agrégée est la somme des trois corrections de phase, transmise telle quelle au `BalancingController` qui répartit ensuite sur les batteries disponibles.

```
PerPhaseZeroInjectionResult.correction_w = correction_L1 + correction_L2 + correction_L3
```

L'état du régulateur (`ZeroInjectionState.integral_w_s`) est persisté entre les ticks via le coordinateur.

---

## 8. Planificateur prédictif 24h

Le `PredictiveScheduler` calcule le programme charge/décharge optimal sur 24 h par **programmation dynamique (DP)** sur une grille de SoC discrétisée.

### 8.1 Modélisation

**État** : SoC en kWh, discrétisé en $N$ niveaux ($N = 50$ par défaut) :
$$\text{SoC grid} = \left\{ E_i \mid E_i = E_{\min} + i \cdot \frac{E_{\max} - E_{\min}}{N-1},\ i = 0 \ldots N-1 \right\}$$

**Transition** (d'un slot $t$ avec SoC $E_s$ en choisissant puissance $P_{\text{bat}}$) :

Si $P_{\text{bat}} \geq 0$ (charge) :
$$E_{s+1} = E_s + P_{\text{bat}} \cdot \Delta t \cdot \eta_{\text{charge}}$$

Si $P_{\text{bat}} < 0$ (décharge) :
$$E_{s+1} = E_s + P_{\text{bat}} \cdot \Delta t / \eta_{\text{discharge}}$$

avec $\eta_{\text{charge}} = \eta_{\text{discharge}} = \sqrt{\eta_{\text{RT}}}$ (efficacité aller-retour partagée équitablement).

**Puissance réseau** :
$$P_{\text{grid}} = P_{\text{net\_load}} + P_{\text{bat}}$$

**Coût du slot** :
$$C_t = \frac{P_{\text{grid}} \cdot \Delta t}{1000} \times \begin{cases} \text{prix\_import} & P_{\text{grid}} \geq 0 \\ \text{prix\_export} & P_{\text{grid}} < 0 \end{cases}$$

### 8.2 DP backward

```
cost[T][s] = 0  pour tout s   (pas de coût futur au terminus)

pour t = T-1 downto 0:
    pour chaque état s:
        best_cost = +∞
        pour chaque puissance P ∈ {fractions de max_charge, max_discharge}:
            E_next = transition(E_s, P, Δt)
            si E_next hors [E_min, E_max]: skip
            s_next  = nearest_grid_index(E_next)
            total   = C_t(P) + cost[t+1][s_next]
            si total < best_cost:
                best_cost = total
                best_choice[t][s] = (s_next, P)
        cost[t][s] = best_cost
```

### 8.3 Reconstruction du planning (passe forward)

```
s_cur = nearest_grid_index(current_soc_kwh)
pour t = 0 to T-1:
    (s_next, P) = best_choice[t][s_cur]
    schedule.append(ScheduleSlot(start=slots[t].start, battery_power_w=P, ...))
    s_cur = s_next
```

**Résultat** : `PlanningResult.first_setpoint_w` donne le setpoint pour le slot courant. Le planning complet est disponible pour l'observabilité.

**Complexité** : $O(T \cdot N \cdot M)$ avec $T = 24$, $N = 50$, $M = 20$ → ~24 000 opérations, < 1 ms.

---

## 9. Dispatch des charges pilotables

Le `LoadDispatchController` alloue le surplus disponible aux charges pilotables par ordre de priorité décroissant.

### 9.1 Éligibilité d'une charge

Une charge est éligible au tick courant si :
1. **Fenêtre temporelle** : `time_window` absente ou heure courante dans `[start, end[`
2. **Durée quotidienne** : `daily_runtime_s` < `max_daily_runtime_s` (si défini)
3. **Énergie quotidienne** : `daily_energy_kwh` < `max_daily_energy_kwh` (si définie)
4. **Anti-court-cycle** :
   - Si la charge est ON : `time_since_on >= min_on_duration_s`
   - Si la charge est OFF : `time_since_off >= min_off_duration_s`
5. **Deadline** : si `deadline_constraint` et l'heure approche, la charge monte en priorité 0 (urgence)

### 9.2 Allocation par type de contrôle

```
charges triées par priorité (1 = premier servi)

pour chaque charge éligible:
    surplus_restant = surplus_total - Σ(allocations précédentes)

    [ON_OFF]
        si nominal_power_w ≤ surplus_restant + tolérance:
            commande = ON (+ nominal_power_w)
        sinon: skip

    [STEPPED]
        palier = highest step tel que step.power_w ≤ surplus_restant
        si palier trouvé: commande = palier

    [MODULATING]
        si surplus_restant < min_power_w: skip
        puissance = min(max_power_w, surplus_restant)
        arrondi au step_w le plus proche
        commande = puissance
```

---

## 10. Adaptateurs Home Assistant

### 10.1 EntityReader

Lit l'état des entités HA, normalise les conventions de signe, et construit un `Snapshot` complet.

**Normalisation de la puissance batterie** :

```python
# Convention DISCHARGE_POSITIVE → inverser le signe
if role.power_sign_convention == DISCHARGE_POSITIVE:
    power_w = -raw_value

# Entités séparées charge/décharge
if charge_power_entity and discharge_power_entity:
    power_w = charge_power - discharge_power  # charge_positive
```

**Dégradation gracieuse** : entité absente ou indisponible → valeur par défaut (`0.0` pour les puissances, `None` pour les optionnels).

### 10.2 DecisionPublisher

Cache le dernier `ArbitrationResult` et expose les setpoints comme propriétés :

```python
setpoint_charge_per_battery_w     # dict[str, float], positif
setpoint_discharge_per_battery_w  # dict[str, float], positif (stocké négatif)
```

Ces valeurs alimentent les sensors `sensor.solarbalance_{device}_setpoint_charge_w`.

### 10.3 ForecastReader

- `pv_forecast_now_w()` : lit une entité HA exprimant la puissance PV prévue en W (entité utilisateur, typiquement depuis Solcast, Forecast.Solar, ou OpenMeteo via template).
- `weather_warning_active()` : supporte les `binary_sensor` (ON/OFF) et les `sensor` textuels avec niveaux Météo-France (`orange`, `red`, `rouge`).

### 10.4 Watchdog

Vérifie la fraîcheur des entités (via `state.last_updated`). Timeout par défaut : **300 s**.

| Entité | Criticité | Conséquence si stale |
|---|---|---|
| PDL `power_entity` | Critique | Mode DEGRADED |
| Batteries SoC/power | Surveillée | Warning log, non-bloquant |
| MPPT power | Surveillée | Warning log |

---

## 11. Gestion des modes et dégradation gracieuse

### 11.1 Diagramme d'états des modes HEMS

```
                ┌──────────────────────┐
                │       NORMAL         │◄───────────────────────┐
                └─────────┬────────────┘                        │
                          │                                      │
         weather_warning  │      user → pause                    │ user/auto
                ┌─────────▼────────────┐     ┌─────────────────┐│
                │        STORM         │     │     PAUSED       ││
                └─────────┬────────────┘     └─────────────────┘│
                          │                                      │
         warning cleared  │ + hysteresis                        │
                          │                    user → manual     │
                ┌─────────▼────────────┐     ┌─────────────────┐│
                │      VACATION        │     │  MANUAL_OVERRIDE ├┘
                └──────────────────────┘     └─────────────────┘
                          
                ┌──────────────────────┐
                │      DEGRADED        │  ← watchdog entité critique stale
                └──────────────────────┘    (auto-recovery si entité se rétablit)
```

### 11.2 Mode STORM

Déclenché automatiquement si `weather_warning_active = True` dans le Snapshot. Cible `DEFAULT_STORM_TARGET_SOC_PCT = 95 %` avec une avance de `DEFAULT_STORM_LEAD_TIME_H = 6 h`. Le mode persiste jusqu'à disparition de l'alerte + délai d'hystérésis configurable.

### 11.3 Mode DEGRADED

Déclenché par le watchdog quand une entité critique est stale depuis plus de 300 s. Le coordinateur continue de tourner mais émet uniquement des décisions neutres (pas de charge ni décharge forcée). Retour automatique en NORMAL si l'entité se rétablit.

### 11.4 Baseline sanity check

$$\text{baseline}_{\text{W}} = P_{\text{grid}} + P_{\text{PV}} - P_{\text{bat}} - P_{\text{loads}}$$

Si `baseline_w < -100 W` pendant 3 ticks consécutifs → notification persistante HA suggérant de vérifier `power_sign_convention`. Une valeur négative signifie que le bilan d'énergie est incohérent (plus d'énergie sortante que d'entrante comptabilisée).
