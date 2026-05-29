# SolarBalance — Guide Utilisateur

> **SolarBalance** est un composant Home Assistant de gestion intelligente de l'énergie (HEMS). Il observe en temps réel la production solaire, l'état des batteries et la consommation du foyer, et calcule des consignes d'optimisation.

---

## Table des matières

1. [Ce que fait SolarBalance](#1-ce-que-fait-solarbalance)
2. [Prérequis](#2-prérequis)
3. [Installation via HACS](#3-installation-via-hacs)
4. [Configuration initiale — Interface graphique](#4-configuration-initiale--interface-graphique)
5. [Configuration des équipements — YAML](#5-configuration-des-équipements--yaml)
6. [Stratégies d'optimisation](#6-stratégies-doptimisation)
7. [Modes de fonctionnement](#7-modes-de-fonctionnement)
8. [Entités exposées](#8-entités-exposées)
9. [Services](#9-services)
10. [Carte Lovelace (solarbalance-card)](#10-carte-lovelace-solarbalance-card)
11. [Automatisations](#11-automatisations)
12. [Dépannage](#12-dépannage)
13. [FAQ](#13-faq)

---

## 1. Ce que fait SolarBalance

- **Optimise l'autoconsommation** : absorbe les excédents PV dans les batteries, décharge quand la maison importe.
- **Minimise la facture** : charge les batteries pendant les heures creuses, décharge pendant les heures pleines.
- **Protège les batteries** : adapte la fenêtre SoC à la chimie et limite les cycles court.
- **Écrête les pointes** : limite l'import réseau sous le seuil de puissance souscrite.
- **Anticipe les tempêtes** : charge les batteries à 95 % sur alerte Météo-France.
- **Publie des consignes** : expose des sensors de setpoint charge/décharge par batterie pour vos automatisations.

### Ce que SolarBalance ne fait PAS encore (v1)

> SolarBalance est en lecture seule en v1. Il **observe et calcule** mais **n'écrit pas** directement sur vos équipements (pas de commande API vers votre onduleur ou batterie). Les consignes calculées sont des sensors HA que vous pouvez exploiter dans vos automatisations. L'écriture active sera introduite en v2.

---

## 2. Prérequis

| Exigence | Détail |
|---|---|
| Home Assistant | **2026.1 ou supérieur** |
| Entité obligatoire | Compteur PDL avec puissance (W) — positif = soutirage réseau |
| Entité quasi-obligatoire | SoC batterie (%) par batterie configurée |
| Entités optionnelles | Puissance PV, puissance batterie, alerte météo, prévision PV |

SolarBalance est **agnostique** vis-à-vis du matériel. Il fonctionne avec tout équipement exposant ses mesures comme entités HA (Ecoflow, Jackery, Victron, Enphase, Huawei, Shelly, etc.).

---

## 3. Installation via HACS

1. Dans HACS → **Intégrations** → menu ⋮ → **Dépôts personnalisés**
2. Ajouter `https://github.com/lachand/ha-solarbalance` — catégorie **Intégration**
3. Rechercher **SolarBalance** dans HACS et cliquer **Télécharger**
4. Redémarrer Home Assistant
5. Aller dans **Paramètres → Intégrations → Ajouter une intégration** → rechercher **SolarBalance**

---

## 4. Configuration initiale — Interface graphique

Le Config Flow HA configure les **paramètres globaux**. Les équipements (batteries, MPPT, onduleurs, charges) se déclarent en YAML (voir section 5).

### Paramètres disponibles

| Paramètre | Défaut | Description |
|---|---|---|
| **Intervalle de tick** | 10 s | Fréquence de la boucle de calcul (5–60 s). Valeurs plus basses = réactivité accrue mais plus de charge CPU. |
| **Zéro-injection** | Activé | Active le régulateur PI qui maintient l'injection réseau à 0 W. |
| **Consigne zéro-injection** | 0 W | Puissance cible au PDL (typiquement 0 W ; valeur légèrement positive ajoute une marge de sécurité). |
| **Hystérésis ZI** | 50 W | Zone morte du régulateur : en dessous de cette valeur d'erreur, aucune correction n'est appliquée. |
| **Phases** | 1 | Nombre de phases (1 ou 3). En triphasé, le régulateur PI tourne par phase. |
| **Puissance souscrite** | 6 kVA | Puissance souscrite au contrat (3–36 kVA). Utilisée par la stratégie écrêtage de pointe. |
| **Entité prévision PV** | — (optionnel) | Sensor HA exprimant la puissance PV prévue *maintenant* (en W). Compatible Solcast, Forecast.Solar, OpenMeteo via template. |
| **Entité alerte météo** | — (optionnel) | `binary_sensor` ou `sensor` Météo-France vigilance. Déclenche le mode Tempête. |
| **Stratégies / priorités** | self_consumption en premier | Ordre des stratégies actives, de la plus prioritaire à la moins prioritaire. |

### Modifier les paramètres après installation

**Paramètres → Intégrations → SolarBalance → Configurer** (icône ⚙️).

---

## 5. Configuration des équipements — YAML

Les équipements se déclarent dans votre `configuration.yaml` HA sous la clé `solarbalance:`. Vous pouvez aussi utiliser l'inclusion YAML :

```yaml
# configuration.yaml
solarbalance: !include solarbalance.yaml
```

### 5.1 Configuration minimale

Un seul équipement avec batterie + MPPT solaire, et un compteur PDL :

```yaml
solarbalance:
  devices:
    - name: ma_batterie
      roles:
        battery:
          capacity_kwh: 3.6
          chemistry: lifepo4
          soc_min_pct: 10
          soc_max_pct: 95
          max_charge_power_w: 1800
          max_discharge_power_w: 1800
          soc_entity: sensor.ma_batterie_soc
          power_entity: sensor.ma_batterie_puissance
          power_sign_convention: charge_positive   # ou discharge_positive
        mppt:
          peak_power_w: 1000
          power_entity: sensor.ma_batterie_pv

  meters:
    - name: pdl
      kind: pdl
      power_entity: sensor.mon_compteur_puissance
```

### 5.2 Déclaration d'un device

```yaml
devices:
  - name: nom_unique       # Obligatoire — utilisé dans les sensor IDs
    roles:
      battery: { ... }    # Au moins un rôle requis
      mppt: { ... }
      inverter: { ... }
```

#### Rôle batterie (`battery`)

| Champ | Obligatoire | Défaut | Description |
|---|---|---|---|
| `capacity_kwh` | ✓ | — | Capacité totale en kWh |
| `max_charge_power_w` | ✓ | — | Puissance max de charge en W |
| `max_discharge_power_w` | ✓ | — | Puissance max de décharge en W |
| `soc_entity` | ✓ | — | Sensor SoC en % |
| `power_entity` | ✓* | — | Sensor puissance batterie en W (*ou charge+décharge séparés) |
| `charge_power_entity` | ✓* | — | Sensor puissance de charge uniquement |
| `discharge_power_entity` | ✓* | — | Sensor puissance de décharge uniquement |
| `power_sign_convention` | — | `discharge_positive` | `charge_positive` ou `discharge_positive` |
| `chemistry` | — | `lifepo4` | `lifepo4`, `nmc`, `leadacid`, `other` |
| `soc_min_pct` | — | `10` | SoC minimum autorisé (%) |
| `soc_max_pct` | — | `95` | SoC maximum autorisé (%) |
| `temperature_entity` | — | — | Sensor température batterie (°C) |
| `cycles_entity` | — | — | Sensor nombre de cycles |
| `usable_capacity_kwh` | — | — | Capacité utile explicite (surcharge le ratio par chimie) |

> **`power_sign_convention`** : la valeur la plus courante dépend de votre matériel. Ecoflow expose typiquement `charge_positive`, Victron expose souvent `discharge_positive`. Vérifiez dans les Outils de développement HA.

#### Rôle MPPT solaire (`mppt`)

| Champ | Obligatoire | Défaut | Description |
|---|---|---|---|
| `peak_power_w` | ✓ | — | Puissance crête installée en Wc |
| `power_entity` | ✓ | — | Sensor puissance PV actuelle (W) |
| `daily_energy_entity` | — | — | Sensor énergie produite aujourd'hui (kWh) |

#### Rôle onduleur (`inverter`)

| Champ | Obligatoire | Défaut | Description |
|---|---|---|---|
| `nominal_power_w` | ✓ | — | Puissance nominale AC en W |
| `ac_output_power_entity` | ✓ | — | Sensor puissance AC sortante (W) |
| `ac_input_power_entity` | — | — | Sensor puissance AC entrante (W) |
| `eps_capable` | — | `false` | L'onduleur supporte le mode EPS (secours) |
| `eps_active_entity` | — | — | `binary_sensor` indiquant le mode EPS actif |

### 5.3 Déclaration des compteurs

```yaml
meters:
  - name: pdl                         # Obligatoire — le PDL doit s'appeler "pdl"
    kind: pdl                         # pdl | pv | consumption | subcircuit
    power_entity: sensor.shelly_total_power
    phases: 1                         # 1 ou 3
    per_phase_zi: false               # true = ZI par phase (triphasé)
    power_l1_entity: sensor.shelly_l1  # Optionnel, triphasé
    power_l2_entity: sensor.shelly_l2
    power_l3_entity: sensor.shelly_l3
    daily_import_energy_entity: sensor.shelly_import_kwh
    daily_export_energy_entity: sensor.shelly_export_kwh
```

**Convention PDL** : `power_entity` doit être **positif en soutirage** (import réseau) et **négatif en injection** (export). C'est la convention standard des compteurs Linky et Shelly 3EM.

### 5.4 Déclaration des charges pilotables

```yaml
loads:
  # Charge ON/OFF simple (ex: ballon eau chaude)
  - name: ballon_ecs
    control_type: on_off
    priority: 2                       # 1 = plus prioritaire
    interruptible: false              # Ne pas couper une fois démarré
    min_on_duration_s: 1800           # 30 min minimum
    min_off_duration_s: 300           # 5 min off minimum après arrêt
    max_daily_runtime_s: 7200         # 2h max par jour
    nominal_power_w: 2200
    switch_entity: switch.contacteur_ballon
    time_window:
      start: "11:00"
      end: "16:00"

  # Charge modulante (ex: borne VE)
  - name: borne_ve
    control_type: modulating
    priority: 1
    min_power_w: 1380                 # 6 A × 230 V
    max_power_w: 7360                 # 32 A × 230 V
    step_w: 230                       # Résolution 1 A
    power_set_entity: number.borne_ve_consigne
    actual_power_entity: sensor.borne_ve_puissance
    deadline_constraint:
      kwh_required: 20               # 20 kWh requis
      before_time: "07:00"           # avant 7h du matin

  # Charge à paliers (ex: pompe piscine)
  - name: pompe_piscine
    control_type: stepped
    priority: 3
    level_entity: number.pompe_vitesse
    steps:
      - level: 1
        power_w: 200
      - level: 2
        power_w: 600
      - level: 3
        power_w: 1200
```

### 5.5 Exemple multi-équipements complet

```yaml
solarbalance:
  devices:
    - name: ecoflow_salon
      roles:
        battery:
          capacity_kwh: 3.6
          chemistry: lifepo4
          max_charge_power_w: 1800
          max_discharge_power_w: 1800
          soc_entity: sensor.ecoflow_salon_soc
          power_entity: sensor.ecoflow_salon_battery_power
          power_sign_convention: charge_positive
        mppt:
          peak_power_w: 1000
          power_entity: sensor.ecoflow_salon_solar_input
        inverter:
          nominal_power_w: 2400
          eps_capable: true
          ac_output_power_entity: sensor.ecoflow_salon_ac_output
          eps_active_entity: binary_sensor.ecoflow_salon_eps

    - name: jackery_garage
      roles:
        battery:
          capacity_kwh: 2.0
          chemistry: lifepo4
          max_charge_power_w: 1000
          max_discharge_power_w: 1000
          soc_entity: sensor.jackery_garage_soc
          power_entity: sensor.jackery_garage_battery_power

  meters:
    - name: pdl
      kind: pdl
      power_entity: sensor.shelly_3em_total_power
      daily_import_energy_entity: sensor.shelly_3em_import_kwh
      daily_export_energy_entity: sensor.shelly_3em_export_kwh

  loads:
    - name: ballon_ecs
      control_type: on_off
      priority: 2
      nominal_power_w: 2200
      switch_entity: switch.contacteur_ballon
      time_window:
        start: "11:00"
        end: "16:00"
```

---

## 6. Stratégies d'optimisation

Les stratégies déterminent ce que SolarBalance cherche à optimiser. Vous pouvez en activer plusieurs ; elles sont combinées par ordre de priorité.

### 6.1 Vue d'ensemble

| Stratégie | Objectif | Quand l'utiliser |
|---|---|---|
| **self_consumption** | Maximiser l'autoconsommation PV | Toujours recommandée en premier |
| **cost_min** | Minimiser la facture (HC/HP, Tempo, EPEX) | Contrats à tarif variable (EDF Tempo, heures creuses) |
| **backup** | Maintenir une réserve d'autonomie | Si risque de coupure réseau ou zone peu fiable |
| **longevity** | Préserver la longévité des batteries | Batteries NMC ou si priorité durée de vie sur performance |
| **peak_shaving** | Écrêter les pointes d'import | Contrats avec pénalité de dépassement ou abonnement juste au-dessus du besoin |
| **revenue_max** | Arbitrage revente sur prix spot | Tarif EPEX spot avec revente possible |

### 6.2 Choisir et ordonner les stratégies

L'ordre dans le Config Flow détermine la priorité. En cas de conflit, la stratégie **la plus haute l'emporte** sur la fenêtre SoC.

**Exemples de combinaisons** :

```
Autoconsommation pure :
  1. self_consumption
  2. backup (reserve_soc_pct: 20)

Contrat heures creuses :
  1. cost_min
  2. self_consumption
  3. backup

Réseau peu fiable + longévité :
  1. backup (reserve_soc_pct: 40)
  2. longevity
  3. self_consumption
```

### 6.3 Paramètres par stratégie

**self_consumption** : aucun paramètre.

**cost_min** :
- `cheap_threshold` : prix en €/kWh en dessous duquel on charge (ex: `0.08`)
- `expensive_threshold` : prix en €/kWh au-dessus duquel on décharge (ex: `0.25`)
- `charge_soc_target_pct` : SoC cible en heures creuses (ex: `90`)

**backup** :
- `reserve_soc_pct` : plancher de SoC réservé (défaut `30`)

**longevity** : aucun paramètre requis (fenêtres calculées par chimie).

**peak_shaving** :
- `max_import_w` : import maximal autorisé en W (ex: 80 % de la puissance souscrite)

**revenue_max** :
- `export_premium` : prime minimale en €/kWh pour déclencher la revente (ex: `0.05`)
- `cheap_import_threshold` : prix d'achat considéré "bon marché" pour charger

---

## 7. Modes de fonctionnement

Le mode HEMS est visible et modifiable via `select.solarbalance_hems_mode`.

### 7.1 Description des modes

| Mode | Icône | Déclenchement | Comportement |
|---|---|---|---|
| **Normal** | 🟢 | Défaut | Stratégies actives |
| **Tempête** | ⛈️ | Auto (alerte météo) ou manuel | Charge batteries à 95 %, priorité autonomie |
| **Vacances** | 🏖️ | Manuel | Stratégies actives, comportement neutre si batterie pleine |
| **Pause** | ⏸️ | Manuel | Boucle de calcul suspendue, aucune consigne émise |
| **Dégradé** | ⚠️ | Auto (entité critique perdue) | Décisions neutres, alerte dans les logs |
| **Supervision manuelle** | 🔧 | Service `set_mode` | Force charge ou décharge selon override actif |

### 7.2 Mode Tempête

Déclenché automatiquement quand l'entité d'alerte météo configurée passe active. Cible un SoC de 95 % avec une avance de 6 h sur l'arrivée prévue de la tempête.

Le mode reste actif jusqu'à disparition de l'alerte + délai d'hystérésis pour éviter les oscillations.

### 7.3 Mode Dégradé

Déclenché si l'entité de puissance du PDL devient indisponible ou stale depuis plus de 5 minutes. SolarBalance continue de fonctionner mais n'émet plus de setpoints. Récupération automatique dès que l'entité se rétablit.

---

## 8. Entités exposées

SolarBalance crée automatiquement les entités suivantes après ajout de l'intégration.

### 8.1 Sensors

| Entité | Unité | Description |
|---|---|---|
| `sensor.solarbalance_mode` | — | Mode HEMS courant |
| `sensor.solarbalance_dominant_strategy` | — | Stratégie dominante du dernier tick |
| `sensor.solarbalance_grid_power` | W | Puissance réseau (positif = soutirage) |
| `sensor.solarbalance_pv_power` | W | Puissance PV totale |
| `sensor.solarbalance_battery_power` | W | Puissance batterie agrégée (positif = charge) |
| `sensor.solarbalance_baseline_consumption` | W | Consommation non pilotable déduite |
| `sensor.solarbalance_battery_soc_avg` | % | SoC moyen de toutes les batteries |
| `sensor.solarbalance_pv_energy_today` | kWh | Énergie PV produite aujourd'hui |
| `sensor.solarbalance_grid_import_today` | kWh | Énergie importée aujourd'hui |

**Par batterie** (une paire par device avec rôle batterie) :

| Entité | Unité | Description |
|---|---|---|
| `sensor.solarbalance_{device}_setpoint_charge_w` | W | Consigne de charge recommandée |
| `sensor.solarbalance_{device}_setpoint_discharge_w` | W | Consigne de décharge recommandée |

### 8.2 Binary Sensors

| Entité | État `On` | Description |
|---|---|---|
| `binary_sensor.solarbalance_storm_mode` | Mode Tempête actif | Utile pour automatisations |
| `binary_sensor.solarbalance_weather_warning` | Alerte météo active | Miroir de l'entité configurée |
| `binary_sensor.solarbalance_degraded` | Mode Dégradé actif | Déclenche une alerte |

### 8.3 Contrôles

| Entité | Type | Description |
|---|---|---|
| `select.solarbalance_hems_mode` | Select | Changer le mode (Normal, Tempête, Vacances, Pause, Supervision) |
| `number.solarbalance_zi_setpoint` | Number (-500–+500 W) | Consigne zéro-injection |
| `number.solarbalance_zi_hysteresis` | Number (0–500 W) | Zone morte ZI |
| `switch.solarbalance_zero_injection` | Switch | Activer/désactiver le PI ZI |

---

## 9. Services

### `solarbalance.pause` / `solarbalance.resume`

Suspend ou reprend la boucle de calcul.

```yaml
service: solarbalance.pause
```

### `solarbalance.set_mode`

Changer le mode directement depuis une automatisation.

```yaml
service: solarbalance.set_mode
data:
  mode: vacation   # normal | storm | vacation | paused | manual_override
```

### `solarbalance.force_charge`

Force la charge d'une batterie jusqu'à un SoC cible, avec puissance et deadline optionnels.

```yaml
service: solarbalance.force_charge
data:
  target_soc_pct: 90
  power_w: 1500          # optionnel — utilise max_charge_power si absent
  deadline: "2026-05-29T07:00:00"  # optionnel
```

### `solarbalance.force_discharge`

Force la décharge.

```yaml
service: solarbalance.force_discharge
data:
  target_soc_pct: 20
  power_w: 1000          # optionnel
```

### `solarbalance.activate_storm_mode`

Déclenche manuellement le mode Tempête.

```yaml
service: solarbalance.activate_storm_mode
data:
  duration_h: 12    # optionnel — durée en heures ; sans durée : jusqu'à la fin de l'alerte
```

---

## 10. Carte Lovelace (solarbalance-card)

La carte `custom:solarbalance-card` affiche en temps réel :
- Un **diagramme de flux Sankey** (PV → batterie / maison / réseau)
- Le **mode HEMS** courant avec badge coloré
- Une **barre de SoC** agrégée

### 10.1 Ajout automatique

Après installation et redémarrage, la carte est enregistrée automatiquement dans le frontend HA. Elle apparaît dans le picker de cartes Lovelace sous **"SolarBalance Card"**.

### 10.2 Ajout via YAML (si automatique ne fonctionne pas)

Dans votre `configuration.yaml` :

```yaml
frontend:
  extra_module_url:
    - /solarbalance_card/solarbalance-card.js
```

Puis redémarrer HA.

### 10.3 Configuration de la carte

```yaml
type: custom:solarbalance-card
# Aucun paramètre obligatoire — la carte lit les entités solarbalance automatiquement
```

---

## 11. Automatisations

### Charger avant une tempête annoncée

```yaml
automation:
  alias: "SolarBalance — charge tempête manuelle"
  trigger:
    - platform: state
      entity_id: binary_sensor.vigilance_meteo_pluie
      to: "on"
  action:
    - service: solarbalance.activate_storm_mode
```

### Alerte mode dégradé

```yaml
automation:
  alias: "SolarBalance — alerte dégradé"
  trigger:
    - platform: state
      entity_id: binary_sensor.solarbalance_degraded
      to: "on"
  action:
    - service: notify.mobile_app
      data:
        message: "SolarBalance en mode dégradé — vérifier l'entité PDL"
```

### Exploiter les setpoints dans une automatisation (v1 — lecture seule)

```yaml
automation:
  alias: "Appliquer consigne charge Ecoflow"
  trigger:
    - platform: state
      entity_id: sensor.solarbalance_ecoflow_salon_setpoint_charge_w
  action:
    - service: number.set_value
      target:
        entity_id: number.ecoflow_salon_charge_power
      data:
        value: "{{ states('sensor.solarbalance_ecoflow_salon_setpoint_charge_w') | float }}"
```

---

## 12. Dépannage

### Mode Dégradé actif

**Cause** : l'entité de puissance du PDL est indisponible, stale (pas mise à jour depuis > 5 min) ou mal configurée.

**Actions** :
1. Vérifier dans **Outils de développement → États** que l'entité PDL est disponible et a une valeur numérique.
2. Vérifier que la valeur est **positive en soutirage** (si votre compteur expose l'inverse, créer un sensor template qui inverse le signe).
3. Consulter les logs HA : `Paramètres → Journaux → Filtrer "solarbalance"`.

### Baseline de consommation négative

**Symptôme** : notification persistante "SolarBalance — vérifier la convention de signe".

**Cause** : la somme `réseau + PV - batterie - charges` est négative, ce qui est physiquement impossible. L'une de vos entités a un signe inversé.

**Actions** :
1. Dans **Outils de développement**, vérifier :
   - `power_entity` de la batterie : **positif quand la batterie se charge** (si `power_sign_convention: charge_positive`) ou **positif quand elle se décharge** (si `discharge_positive`).
   - `power_entity` du PDL : **positif quand vous consommez** du réseau.
2. Corriger `power_sign_convention` dans le YAML ou créer un template sensor.

### Carte Lovelace non visible

1. Forcer le rechargement du cache navigateur : `Ctrl+Shift+R` (ou vider le cache navigateur).
2. Vérifier que `/solarbalance_card/solarbalance-card.js` est accessible : ouvrir l'URL dans le navigateur depuis votre instance HA.
3. Si inaccessible : vérifier que le dossier `custom_components/solarbalance/www/` contient bien `solarbalance-card.js`.
4. En dernier recours, ajouter manuellement dans `configuration.yaml` :
   ```yaml
   frontend:
     extra_module_url:
       - /solarbalance_card/solarbalance-card.js
   ```

### Zéro-injection ne fonctionne pas

1. Vérifier que `switch.solarbalance_zero_injection` est **ON**.
2. Vérifier que le mode n'est pas **Pause** ou **Dégradé**.
3. En triphasé : vérifier que `per_phase_zi: true` est défini sur le compteur PDL et que les entités `power_l1/l2/l3_entity` sont renseignées.
4. Augmenter temporairement `number.solarbalance_zi_hysteresis` à 200 W pour confirmer que le régulateur réagit.

### Logs utiles

```
# Activer les logs debug
logger:
  default: info
  logs:
    custom_components.solarbalance: debug
```

Filtres dans **Paramètres → Journaux** :
- `"SolarBalance"` : tous les messages
- `"setpoint"` : consignes calculées
- `"degraded"` : transitions mode dégradé
- `"baseline"` : résultats de la vérification de cohérence

---

## 13. FAQ

**Q : La convention de signe réseau est confuse. Qu'est-ce qui est positif ?**  
R : Le compteur PDL doit être **positif quand vous achetez de l'électricité** (soutirage, import) et **négatif quand vous en revendez** (injection, export). C'est la convention Linky et Shelly 3EM native.

**Q : Pourquoi ma batterie ne se charge pas pendant les heures creuses ?**  
R : La stratégie `cost_min` doit être activée avec un `cheap_threshold` adapté à votre contrat. Vérifiez aussi que `current_import_price` est bien renseigné dans le Snapshot (configurer une entité de tarif ou un tarif HA Energy).

**Q : Puis-je utiliser SolarBalance sans batterie ?**  
R : Oui, en mode lecture seule pour l'observabilité (sensors de puissance réseau/PV). Les stratégies de dispatch de charges fonctionnent aussi sans batterie si vous avez des charges pilotables.

**Q : La différence entre Config Flow et YAML ?**  
R : Le Config Flow (interface graphique) gère les **paramètres globaux** (tick, ZI, phases, stratégies). Le YAML déclare les **équipements** (batteries, MPPT, onduleurs, compteurs, charges). Cette séparation évite une interface graphique surchargée pour les configurations multi-équipements complexes.

**Q : SolarBalance est-il compatible avec mon équipement ?**  
R : Tout équipement exposant ses mesures comme entités HA est compatible. Il faut au minimum une entité SoC (%) et une entité puissance (W) pour la batterie. Les marques Ecoflow, Jackery, Victron, Huawei, Enphase, Fronius, et tout système avec intégration HACS/custom sont compatibles.

**Q : Mon abonnement est Tempo, comment configurer les prix ?**  
R : SolarBalance inclut un modèle `TempoTariff` (couleurs Bleu/Blanc/Rouge avec prix HC/HP par couleur). La liaison avec l'entité couleur du jour RTE est à configurer via le YAML `tariff:`. La documentation complète des tarifs sera disponible dans une prochaine version.

**Q : Le planificateur 24h est-il actif en v1 ?**  
R : Le `PredictiveScheduler` calcule un planning optimal mais son résultat est publié uniquement comme sensor d'observabilité en v1. L'injection effective dans la prise de décision est prévue pour v2.
