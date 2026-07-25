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

## [2.0.8-beta85] — 2026-07-25

### Added

- **Réglage de boucle calé sur l'actionneur** (D1, opt-in). Le gain proportionnel zéro-injection
  a une valeur sûre qui **dépend du temps mort** entre la consigne et sa lecture au compteur :
  un gain calme sur un onduleur qui répond en un tick devient un gain qui dépasse et oscille
  sur un EcoFlow STREAM à ~30 s en BLE — la boucle continue de pousser parce que les trois
  dernières commandes ne sont pas encore arrivées, puis rebondit quand elles arrivent d'un
  coup. `core/controllers/loop_tuning.py` (pur) dérive le gain du retard :
  `kp = kp_config / (retard / tick)`, borné. Un actionneur qui répond en un tick garde le gain
  configuré (donc comportement identique à aujourd'hui), et le gain n'est **jamais** relevé
  au-dessus du réglage ni abaissé sous un plancher où la boucle ne corrigerait plus. C'est le
  gain de *base* — l'auto-tuner amortit toujours à partir de là, avec moins à défaire.

### Note

- **G2** (charge modulante) et **G3** (arbitrage tarifaire) restaient déjà couverts par le type
  de charge `modulating` et le contrôle prédictif existants — voir beta83. Le lot demandé
  (D1, E1, E4, E3, G2, G3, F3, F4) est ainsi complet.

## [2.0.8-beta84] — 2026-07-25

### Added

- **Frise d'anomalies** (F3). Chaque incident du mois se terminait pareil : quelqu'un
  remontait le journal HA pour reconstituer *quand* le compteur s'est tu, *quand* la batterie
  cloud a lâché, *quand* cette lecture d'export impossible a été rejetée. Les signaux
  existaient tous, mais éparpillés. Un anneau borné (`core/event_log.py`, pur) rassemble
  désormais l'essentiel — compteur perdu/revenu, lecture rejetée, liaison peu fiable, cycle
  d'appareil inhabituel — chaque ligne datée, avec une gravité, **dé-dupliquée** (un compteur
  qui clignote incrémente un compteur au lieu d'inonder la frise). Persistée, exposée en
  capteur et en carte de panneau.

- **Score de santé de l'installation** (F4). Un seul nombre 0-100 (`core/install_score.py`,
  pur) qui agrège ce qui existait déjà — santé des liaisons, garde-fou de plausibilité,
  problèmes de configuration, source du compteur, mode dégradé — **avec la liste de ce qui l'a
  fait baisser**, la déduction la plus lourde d'abord. Perdre le compteur (primaire ET
  secours) coûte le plus, le secours seul est une dégradation survivable, une liaison
  instable coûte au prorata de ce qu'elle a réellement perdu. Capteur + carte de panneau qui
  ne s'affiche que quand quelque chose cloche.

## [2.0.8-beta83] — 2026-07-25

### Added

- **Rendement aller-retour mesuré, par batterie** (E4). Le planificateur et le contrefactuel
  supposent 90 % à plat ; un parc tombé à 82 % fausse silencieusement tous leurs calculs, et
  rien ne le mesurait. SolarBalance intègre désormais l'énergie **entrée** et **sortie** de
  chaque batterie et en tire le rendement réel — **corrigé de la charge encore stockée** (un
  parc qui finit plus plein a *gardé* de l'énergie, pas perdu), ce qui rend l'estimation
  exacte sur n'importe quelle fenêtre. Affiché une fois assez d'énergie passée pour que le
  chiffre veuille dire quelque chose.

- **Cycles complets équivalents + SoH sans compteur constructeur** (E3). À partir du même
  bilan d'énergie, l'énergie délivrée sur une capacité utile donne les cycles équivalents —
  et donc une estimation d'**état de santé** pour les batteries qui n'exposent aucun compteur
  de cycles (jusqu'ici SoH restait *inconnu* pour elles). Deux capteurs de diagnostic par
  batterie (rendement, cycles équivalents), totaux persistés.

- **Coût par cycle d'appareil** (E1). Chaque programme appris affiche ce qu'il **coûte** au
  tarif courant : euros s'il tournait maintenant (selon la part solaire du moment) vs euros
  **économisés en attendant** l'heure la plus ensoleillée. Visible sur chaque ligne de
  programme du panneau.

### Note

- **G2** (charge modulante : ballon / PAC) et **G3** (arbitrage tarifaire) étaient **déjà
  implémentés** — respectivement le type de charge `modulating` (dispatch continu du surplus
  vers `power_set_entity`) et le *contrôle prédictif* (`predictive_steering_w`, option
  existante) qui charge en heures creuses / décharge en heures pleines vers la consigne du
  planificateur. Rien à ajouter.

## [2.0.8-beta82] — 2026-07-24

### Changed

- **Icône affinée** : fond **entièrement transparent** (plus de disque bleu), et le
  **wordmark « SOLARBALANCE » retiré** — seul le graphique de la balance (maison + batterie
  face au solaire) est conservé, recadré pour **remplir le carré**, donc bien plus lisible en
  petite taille. Détourage piloté par le trait lui-même (les traits saturés restent, le fond
  pâle disparaît) avec un rééchantillonnage prémultiplié pour des bords nets sans halo.

## [2.0.8-beta81] — 2026-07-24

### Added

- **Étiquetage des cycles depuis le panneau.** Un montage sur prise ne remonte que la
  puissance, jamais le programme, donc tous les cycles appris atterrissaient dans un seul sac
  `unknown` — un 40° et un 20° mélangés, impossibles à distinguer, et le seul moyen de
  renommer était un appel de service dans les Outils de développement. Deux affordances
  arrivent dans la carte 🧺 :
  - un **✏️ par programme** qui le renomme (appelle `rename_appliance_program` pour vous) ;
  - un bouton **« Étiqueter le dernier »** quand des cycles `unknown` existent : il nomme
    **uniquement le cycle qui vient de se terminer** — celui que vous reconnaissez comme « la
    lessive que je viens de lancer » — et le sort du sac `unknown`. Répété après chaque
    lessive, il **sépare les programmes un cycle à la fois**. Sa durée et son énergie sont
    affichées pour le reconnaître (ce n'est pas la médiane du sac, mais bien le dernier).

  Nouveau service **`solarbalance.label_last_cycle`** (`appliance`, `program`, `from_program`
  optionnel pour corriger un mauvais libellé). Le libellé est persisté immédiatement et
  survit à un redémarrage. La docstring qui prétendait qu'une entité `*_program` était lue
  automatiquement décrivait un câblage inexistant — corrigée.

### Changed

- **Nouvelle icône** (le logo SolarBalance V2 : maison + batterie en équilibre face au
  solaire). Le damier de transparence était incrusté dans le JPEG, y compris **sous** le
  disque : il est retiré partout, le fond du disque est aplati en un bleu pâle uni et les
  coins redeviennent transparents.

## [2.0.8-beta80] — 2026-07-24

### Added

- **Hystérésis au point d'équilibre** (opt-in, *Régulation & comportements*). La bande morte
  zéro-injection n'a **qu'un seuil** : agir au-delà de 50 W, ne rien faire en deçà. Ce n'est
  pas une hystérésis, c'est un seuil sans mémoire — une erreur qui oscille *autour* fait
  basculer la boucle entre régulation et repos **à chaque tick**. Et chaque bascule est un
  ordre réel envoyé à du matériel qui met ~30 s à répondre : trois autres ticks arrivent avant
  que le premier n'apparaisse au compteur. C'est le yoyo qui revient dans les logs autour de
  l'équilibre, là où l'erreur est petite par définition.

  Deux seuils au lieu d'un : on se **pose** quand l'erreur entre dans la bande morte, on ne
  **repart** qu'au-delà d'un seuil plus large. Entre les deux, la boucle tient sa dernière
  commande — exactement ce dont un actionneur lent a besoin. L'élargissement vient du retard
  de l'actionneur (nouveau réglage *Retard de l'actionneur*, 30 s par défaut, mesuré sur le
  STREAM en BLE) : un matériel qui répond en un tick n'obtient **aucun** élargissement et le
  comportement est alors identique à aujourd'hui. Le facteur est plafonné — une bande large
  est une boucle aveugle.

  **Asymétrique, volontairement** : l'élargissement s'applique **au soutirage uniquement**.
  Tolérer 50 W de soutirage de plus quelques secondes coûte une fraction de centime ; tolérer
  50 W d'**injection** de plus, c'est renoncer à la seule chose que le zéro-injection existe
  pour faire. Le côté injection garde donc le seuil de base et réagit aussi vite qu'avant.

  Le tick silencieux est **expliqué** (« Au point d'équilibre : … ») plutôt que de donner
  l'impression d'une boucle à l'arrêt, et les seuils apparaissent dans les diagnostics HA.

## [2.0.8-beta79] — 2026-07-24

### Added

- **Score de santé des liaisons (24 h).** Trois incidents cette semaine étaient des pannes
  de capteur déguisées en bugs de régulation — dont les 38 minutes de compteur muet au lever
  du soleil le 24/07. Rien n'enregistrait *à quelle fréquence une liaison répond*, seulement
  si elle répondait à l'instant. Chaque entité dont dépend la boucle (compteur PDL et son
  secours, SoC et puissance de chaque batterie, MPPT) est désormais suivie : **% de
  disponibilité, âge médian, plus long trou, nombre de coupures**, sur une fenêtre glissante
  de 24 h persistée entre redémarrages.

  Le score n'est pas la disponibilité. Un compteur qui rate 3 % des relevés dispersés ne
  coûte rien — le filtre médian les absorbe ; les mêmes 3 % **en un seul trou de 40 minutes**
  arrêtent la maison. Le score pénalise donc le plus long trou en plus du taux, et un
  incident réel passe devant n'importe quelle quantité de bruit. Nouveau capteur de
  diagnostic (état = la liaison **la plus faible**, jamais une moyenne qui laisserait neuf
  capteurs sains masquer celui qui a lâché), carte de panneau qui **ne s'affiche que quand
  quelque chose ne va pas**, et export dans les diagnostics HA.

- **Apport réel de l'orchestration** (`sensor.solarbalance_orchestration_gain_today`).
  Le chiffre d'économies existant compare « PV + batterie » à « rien du tout » — mais
  débranchez SolarBalance et les batteries continuent l'autoconsommation toutes seules :
  l'essentiel de ce gain survit. La question qui compte est marginale : *qu'apporte le
  pilotage face au même matériel laissé à lui-même ?*

  Un contrôleur fantôme tourne donc en parallèle, avec **exactement** les limites de
  puissance et la plage de SoC du parc réel, face à la **même** maison et à la **même**
  production (les deux dérivées des mêmes mesures : aucun scénario n'a une journée plus
  facile). Ses flux réseau sont facturés au même tarif, et l'écart entre les deux factures
  est la réponse. L'énergie encore stockée de part et d'autre est **valorisée** à la fin :
  sans cela, la réserve du soir apparaîtrait comme une perte sèche jusqu'à 18 h. La
  production non bridée n'est pas modélisée, ce qui rend l'estimation **conservatrice** —
  jamais flatteuse.

### Fixed

- Un numéro de série réel (`stream_60605`) traînait encore dans un test — remplacé par un
  placeholder.

## [2.0.8-beta78] — 2026-07-24

### Fixed

- **Un cycle d'appareil en cours survit désormais à un redémarrage.** Le tampon du cycle
  n'était pas persisté : une lessive de deux heures commencée avant une mise à jour était
  perdue et jamais apprise (constaté le 24/07). Il est maintenant enregistré avec les
  gabarits. Un tampon corrompu n'empêche jamais la restauration des gabarits, et il est
  **plafonné** (échantillonnage divisé par deux au-delà de 1500 points, en gardant le début
  du cycle qui est ce qui l'identifie) — sans quoi un appareil resté allumé ferait grossir
  le Store sans limite.

- **`ruff` épinglé** à `>=0.16,<0.17`. Il était déclaré `>=0.7` : la sortie de 0.16, qui
  s'est mise à formater les blocs Python dans les `.md`, a cassé la CI **sans le moindre
  changement de code**. Les correctifs passent, les versions mineures non.

### Changed

- **`capture_debug` peut renvoyer les ticks dans la réponse** (`include_records: true`).
  Le fichier JSONL atterrit sur la machine Home Assistant, illisible pour une automatisation
  ou une analyse distante — le chemin seul ne leur sert à rien. Réponse **plafonnée à 240
  ticks** (avec `records_truncated`), le fichier gardant toujours l'intégralité.

## [2.0.8-beta77] — 2026-07-24

### Added

- **Chaque programme d'un appareil est désormais suivi et affiché séparément.** La base le
  permettait déjà (`templates[appareil][programme]`), mais l'interface ne montrait que le
  programme le plus fréquent et jetait les autres. Le panneau liste maintenant, par appareil :
  **chaque programme**, son **nombre de cycles enregistrés**, sa **durée**, son **énergie**,
  son **% solaire** propre et son meilleur créneau. Un 60° et un 20° diffèrent de plus d'un
  ordre de grandeur en énergie — une seule valeur pour l'appareil n'en décrivait aucun.

- **Courbe type de chaque programme** tracée dans le panneau (profil de puissance médian des
  cycles enregistrés). Chaque courbe est mise à l'échelle de **son propre pic** : ce sont des
  *formes* qu'on compare, la valeur en kWh à côté portant la magnitude. La chauffe d'un 60°
  se distingue ainsi d'un coup d'œil du plat d'un 20°.

- **Service `solarbalance.rename_appliance_program`** — réétiqueter les cycles appris, surtout
  ceux que l'intégration d'appareils n'a jamais su identifier (rangés en `unknown`). Fusionne
  avec la destination si elle existe déjà, et persiste immédiatement : un réétiquetage perdu
  au redémarrage serait pire que pas de service du tout.

## [2.0.8-beta76] — 2026-07-24

### Added

- **Réserve du soir pilotée par la prévision** (option *Keep back what the evening peak
  will need*, désactivée par défaut). Les batteries se vidaient au gré de l'après-midi, et
  le pic du soir — le plus prévisible de la journée — était servi par le réseau. La réserve
  dimensionne ce qu'il faut garder :

      besoin = Σ sur les heures du pic de max(0, conso apprise − PV prévue)

  puis **interdit la décharge** une fois le stock retombé à ce niveau, et **libère tout au
  début du pic** — une réserve jamais dépensée n'est qu'une batterie plus petite.

  Ce que ça change par rapport à l'existant : `predictive_steering_w`, le seul crochet du
  planificateur vers le contrôle, est **conditionné au tarif** et donc **inerte en tarif
  plat**. Garder de l'énergie pour le soir vaut le coup quel que soit le prix, puisque
  c'est la différence entre couvrir le pic depuis la batterie ou depuis le réseau.

  Trois refus intégrés : elle ne **force jamais une charge** (sinon un après-midi nuageux
  se mettrait à importer pour remplir une batterie), elle ne réclame **jamais plus qu'une
  part configurable** de la capacité utile (60 % par défaut — un soir prévu coûteux ne doit
  pas figer tout le parc), et elle ne descend **jamais sous le plancher SoC** de la
  batterie. Sans profil appris, elle s'abstient plutôt que de deviner.

## [2.0.8-beta75] — 2026-07-24

### Added

- **Un cycle en cours affine la prévision de consommation du bridage anticipé.** Le profil
  horaire moyenne un appareil sur des journées qui, pour la plupart, n'en faisaient pas
  tourner — il sous-estime donc lourdement un cycle en cours. Quand un cycle est apparié
  avec assez de confiance, sa **courbe restante** est repliée dans la conso prévue : plus
  de pré-bridage cinq minutes avant une chauffe de 1,8 kW.
  *Choix assumé* : la part (diluée) du même appareil déjà présente dans la moyenne est
  alors comptée deux fois. Surestimer la consommation ne fait que rendre le frein **moins**
  empressé — et garder du solaire est le bon côté de cette erreur.
  *(Correction d'une première intention : compter l'appareil comme « puits » aurait été un
  double-comptage bien plus grave, un puits absorbant le surplus de façon optionnelle alors
  qu'une machine tourne de toute façon.)*

- **Détection d'anomalie de cycle** — nouvel événement `solarbalance_appliance_anomaly`.
  Un cycle terminé qui ne ressemble à **aucun** des précédents (résistance morte, vidange
  bouchée, porte mal fermée) déclenche un avertissement et un événement exploitable en
  automatisation. Deux garde-fous : le module reste **muet tant qu'il n'a pas au moins
  3 cycles** de référence — alerter sur deux échantillons apprendrait juste à ignorer
  l'alerte — et le cycle jugé est **exclu par identité** de la comparaison, sans quoi il se
  ressemblerait parfaitement à lui-même et rien ne serait jamais signalé.

## [2.0.8-beta74] — 2026-07-24

### Added

- **Le système explique lui-même ce qu'il fait**, en une phrase, dans le panneau et en
  attribut du capteur de régulation. Lire l'état demandait jusqu'ici de savoir ce que
  signifient `binding`, `no_charge_floor` ou `unalloc` — chaque incident de la semaine
  s'est terminé par une traduction manuelle de ce jargon.
  Exemple : *« Décharge 800 W : la maison tire 900 W, le solaire en couvre 100 ;
  plafonné au solaire du parc, donc rien n'est chargé depuis le réseau. »*

  Deux choix de conception :
  - Le cœur renvoie une **clé + des paramètres**, pas une phrase toute faite : il n'a pas
    à contenir de texte français ou anglais, et une interface a de toute façon besoin des
    nombres séparément pour les formater. Le panneau rend la phrase dans ta langue.
  - **Un clamp n'est nommé que s'il a réellement déplacé la cible** (> 10 W). Le
    clignotement cosmétique `base ↔ no_charge_floor` corrigé en beta62 avait un plancher à
    2 W de la cible : le nommer comme cause aurait laissé croire qu'il décidait quelque
    chose. Un `binding` inconnu n'est simplement pas mentionné, jamais affiché brut.

  Quand le compteur manque, la phrase **ne cite pas** la consommation maison : celle-ci
  est dérivée de la mesure absente, et l'annoncer serait une précision qui n'existe pas.

## [2.0.8-beta73] — 2026-07-24

### Added

- **Repli « solaire seul » quand le compteur réseau manque** (option *Keep storing solar…*,
  désactivée par défaut). Perdre le compteur rend la zéro-injection impossible — mais pas
  aveugle pour autant : la PV reste mesurée aux onduleurs, et le profil de consommation
  horaire sait à peu près ce que tire la maison. Le repli estime donc le surplus
  (`PV mesurée − conso apprise`) et en charge une **part minorée** (70 % par défaut,
  réglable). Le 24/07, ça aurait transformé **38 minutes d'inaction en plein soleil** en
  38 minutes de stockage.

  Conçu autour du fait que l'estimation peut être fausse :
  - **charge uniquement, jamais de décharge** — sans compteur, une injection passerait inaperçue ;
  - **une fraction seulement** du surplus estimé, pour qu'une conso sous-estimée mange la
    marge au lieu de tirer sur le réseau ;
  - **rien sous un plancher** (150 W), un petit surplus étant indiscernable de l'erreur de profil ;
  - **rien sans télémétrie PV fraîche**, ni sans profil appris, ni batterie pleine.

  L'état du repli (actif, puissance, raison) est exposé en diagnostic. Sans activation
  explicite, le comportement reste **exactement celui d'avant**.

## [2.0.8-beta72] — 2026-07-24

### Added

- **Compteur réseau de secours** (option *Backup grid sensor*). Le 24/07, l'entité du
  compteur PDL est passée `unavailable` de **06:58 à 07:36** : comme c'est la **seule**
  entité dont la péremption est critique, SolarBalance a suspendu toute régulation pendant
  **38 minutes, en plein lever de soleil**. Une source de secours déclarée prend désormais
  le relais automatiquement, puis rend la main au retour du compteur principal. La
  convention de signe du PDL s'applique aussi au secours (sinon un basculement inverserait
  silencieusement le signe de toute la boucle). La source active (`primary` / `backup` /
  `none`) est exposée en diagnostic — un « 0 W » n'est plus indiscernable d'une panne.

- **Garde-fou de plausibilité physique sur la lecture réseau** (`core/plausibility.py`, pur).
  Le compteur rapporte parfois une valeur que l'installation **ne peut pas produire** :
  observé le 23/07 à 17:46, **−2032 W d'export** alors que la PV faisait 1638 W et que les
  batteries **chargeaient** 1479 W — l'export maximal réel était de **159 W**, soit une
  impossibilité de 1,87 kW. La règle est un **bilan d'énergie**, pas un seuil :
  `export ≤ PV + décharge batterie`. Hors bornes → on **tient la dernière valeur fiable**.
  Appliqué **avant** le filtre médian, parce que le glitch réel durait **deux échantillons**
  et qu'une médiane-de-3 ne rejette qu'un point isolé. Ce n'est **pas** un lissage : une
  valeur plausible, même bruitée, passe intacte. Compteur de rejets en diagnostic.

## [2.0.8-beta71] — 2026-07-24

### Fixed

- **On peut enfin vérifier qu'un appareil est bien en cours d'enregistrement.** Le conseil
  appareils sautait tout appareil sans cycle appris, si bien qu'une liste vide voulait dire
  indifféremment « rien appris pour l'instant » **ou** « rien configuré » — impossible de
  confirmer que la configuration avait pris. Chaque appareil configuré est désormais publié,
  avec `running` et `elapsed_min` quand un cycle est en cours, et la carte affiche
  « apprentissage — aucun cycle complet enregistré ». Les chiffres solaires n'apparaissent
  toujours qu'une fois un cycle réellement appris : aucun pourcentage inventé.

## [2.0.8-beta70] — 2026-07-24

### Fixed

- **L'option « Entités de puissance des appareils » n'avait pas de libellé** : elle s'affichait
  sous sa clé brute `appliance_power_entities` dans *Regulation & behaviour*. Libellés EN/FR
  ajoutés, précisant que ces appareils sont **observés, jamais pilotés**.

## [2.0.8-beta69] — 2026-07-24

### Added

- **Cycles d'appareils : « récupérable solaire » au dashboard.** Deux nouveaux modules purs
  apprennent la **courbe de puissance** des cycles (machine à laver, lave-vaisselle) depuis
  une simple entité de puissance de prise connectée, puis répondent à la question utile :
  *si je lance ce cycle maintenant, quelle part sera couverte par le soleil — et vaut-il mieux
  attendre ?* La carte affiche, par appareil, la **durée** et l'**énergie** typiques, le
  **% solaire si lancé maintenant**, et le **meilleur créneau** — proposé uniquement s'il
  gagne au moins 10 points, pour ne pas faire patienter pour rien.
  - Nouvelle option **Entités de puissance des appareils** (multi-capteurs). Les appareils
    sont **observés, jamais pilotés**.
  - **Pas de machine learning** : quelques dizaines de cycles et un processus *déterministe*
    (automate à états) — un appariement de gabarits au plus proche voisin fait mieux,
    sans dépendance, reste interprétable, et **ne prédit rien** sous son seuil de confiance.
  - Deux points de conception tirés des vraies données : un cycle se **clôt sur une absence
    prolongée**, pas sur un zéro (un vrai cycle lave-vaisselle passe une heure à ~75 W avec des
    creux à ~1 W qui, sinon, le découperaient en plusieurs faux cycles) ; et le **label de
    programme est lu à la clôture** — les intégrations d'appareils ne l'identifient que très
    tard (observé : 2 h après le début), ce qui est inutile pour *prédire* mais parfaitement
    bon pour *ranger* un cycle terminé. Sans label, tout fonctionne quand même.
  - Rien n'est affiché tant que rien n'a été appris : un pourcentage inventé enverrait
    quelqu'un lancer 2 kWh sur le réseau.

## [2.0.8-beta68] — 2026-07-24

### Fixed

- **Dent de scie sur la consigne de décharge des STREAM : SolarBalance se battait contre
  la régulation interne de l'appareil.** En `self_powered`, une STREAM **module elle-même**
  son `base_load_power` pour suivre la charge maison réelle. `verify_writes()` — conçu pour
  rattraper une écriture qui *n'a jamais abouti* — voyait cette baisse comme un échec et
  **ré-écrivait la valeur en force** dès 20 W d'écart. Résultat observé en direct
  (07:36-07:46) : `275 → 232 → 178 → 121 → 82`, puis retour brutal à 275, **période ~40 s,
  amplitude ~190 W**, 94 écritures en 15 min — alors que la cible calculée était
  parfaitement lisse (`unalloc = 0`, allocation monotone). Le réseau oscillait ±130 W.
  Désormais, sur un setpoint que l'appareil **module légitimement** (la consigne de
  décharge d'une batterie mode-switch), une dérive **vers le bas** n'est plus ré-assertée :
  la boucle réseau répond déjà de l'écart. **Atténuations conservées** : on ré-écrit
  toujours si la valeur **s'effondre** (< 10 W — signature d'une écriture perdue ou
  annulée) et toujours si elle **dépasse** la commande (un surplus de sortie peut injecter).
  Les autres setpoints — limites PV notamment, où une lecture basse signifie une production
  bridée à tort — restent vérifiés à l'identique.

## [2.0.8-beta67] — 2026-07-23

### Added

- **Icône de marque embarquée** (`custom_components/solarbalance/brand/icon.png` 256×256 +
  `icon@2x.png` 512×512). Depuis **Home Assistant 2026.3**, une intégration personnalisée
  fournit ses images de marque **directement dans son dossier** — le dépôt
  `home-assistant/brands` n'accepte plus les icônes de custom integrations (dossier marqué
  *legacy* ; les PR y sont systématiquement fermées avec ce motif). L'icône s'affiche donc
  dans l'UI sans PR externe ni délai de cache CDN, et satisfait au passage le contrôle
  `brands` de HACS.

### Fixed

- **Clés du `manifest.json` triées** comme l'exige hassfest (`domain`, `name`, puis ordre
  alphabétique). Cette erreur n'est apparue qu'une fois les deux précédentes levées.
  **La CI est désormais entièrement verte** : hassfest OK et HACS **9/9**.

## [2.0.8-beta66] — 2026-07-23

### Fixed

- **Validation hassfest (CI) — deux erreurs de manifest.**
  - `"homeassistant": "2026.1.0"` retiré de `manifest.json` : cette clé n'est **pas valide**
    dans le manifest d'une *custom integration* (elle est réservée aux intégrations du
    core), ce qui faisait échouer hassfest sur `extra keys not allowed`. La contrainte de
    version minimale reste déclarée là où HACS la lit réellement : **`hacs.json`** — donc
    aucune perte de fonction.
  - **`after_dependencies: ["recorder"]` ajouté** : l'intégration importe
    `homeassistant.components.recorder` (rejeu d'une journée, amorçage du profil de
    consommation depuis les statistiques) sans le déclarer. Au-delà de faire taire
    hassfest, ça garantit que le recorder est chargé **avant** SolarBalance quand il est
    présent, ce qui fiabilise l'amorçage des statistiques.

## [2.0.8-beta65] — 2026-07-23

### Fixed

- **Deux yoyos réels de la puissance batterie, diagnostiqués sur données live.** Le parc
  oscillait ~170 fois (>300 W au compteur) entre 10 h et 17 h. Deux mécanismes distincts,
  tous deux dans le balancer — la *cible* de régulation, elle, était parfaitement stable :
  - **Dither du taper de décharge.** Les capteurs SoC sont quantifiés au 1 % et sautillent
    sur la frontière (une STREAM à ~23,5 % rapportait 23↔24 % toutes les ~10 s). Injecté tel
    quel dans la rampe linéaire du taper, ce 1 % faisait varier le cap d'un quart de la
    bande — **575 ↔ 1150 W** — donc la consigne écrite alternait **575 ↔ 870 W à chaque
    tick** (43 % des ticks, saut moyen 331 W). Le taper lit désormais un **SoC latché** :
    une **baisse est honorée immédiatement** (jamais retarder la protection d'une batterie
    qui se vide), une **hausse doit franchir 1,5 %** avant de relâcher le cap. Le dither ne
    déplace plus rien ; une vraie remontée relâche normalement.
  - **Batterie qui « cligne » hors du parc.** Une batterie en BLE disparaît un tick de temps
    en temps (entité indisponible, ou limite de charge lue à 0). Le balancer larguait alors
    toute sa part, `unallocated` explosait, et l'anti-windup prenait ce pic pour une vraie
    saturation : **la cible parc chutait d'autant** (marche de **1050 W** observée), puis
    remontait au retour de la batterie. Une batterie qui participait reste maintenant dans
    le parc **jusqu'à 3 ticks** avec son dernier état/cap connus. Une disparition durable
    la sort toujours, après le délai — on ne fait que **retarder le retrait** de capacité,
    jamais en inventer.

- **Dashboard : le bouton « Afficher les pics bruts » ne faisait rien.** L'attribut était
  écrit `data-toggle-raw` sans valeur → `dataset.toggleRaw === ""` (falsy) → le gestionnaire
  de clic ne le trouvait jamais. Corrigé en `data-toggle-raw="1"`.

## [2.0.8-beta64] — 2026-07-21

### Changed

- **Dashboard : les pics capteur d'un seul tick ne cassent plus le graphe de puissance.**
  Le compteur réseau rapporte parfois un pic ponctuel physiquement impossible (ex. un
  « export » de −2 kW alors qu'il n'y a que 1,6 kW de PV et que la batterie *charge*) qui
  écrasait toute l'auto-échelle. Le panneau **dé-glitche l'affichage** : un pic est masqué
  de la courbe **et** de l'échelle seulement s'il **récupère en ≤ ~2 ticks** (blip
  capteur). Une excursion plus longue — une vraie charge, ou **une batterie cloud qui
  cesse de remonter ses données** pendant plusieurs ticks — n'est **pas** un glitch et
  reste affichée telle quelle. Les pics masqués restent **identifiables** : un petit
  losange sur la courbe (survol = valeur brute + heure), un compteur « N pic(s) masqué(s) »
  dans la légende, et un bouton **« Afficher les pics bruts »** pour tout revoir.
  **Affichage uniquement** — la régulation, elle, les filtrait déjà (médian-de-3 + settle).

## [2.0.8-beta63] — 2026-07-21

### Added

- **Service `solarbalance.capture_debug` + historique de ticks structuré.** Le
  coordinateur garde en mémoire un **ring buffer** des ~720 derniers ticks (≈ 2 h à
  10 s), rempli à chaque tick avec l'état complet de régulation (grid, cible parc,
  `binding`, consignes par batterie, **staleness** de chaque batterie, anticipation,
  loop_base, zi, eq…). Le service `capture_debug` le **vide dans un JSONL** sous
  `config/solarbalance_debug/` (un objet JSON par ligne, un par tick) et renvoie
  `{path, ticks, from, to}`. Champ optionnel `minutes` pour ne garder que la fenêtre
  récente. But : capturer un incident **après** l'avoir remarqué (les données sont déjà
  bufferisées) pour le **rejouer hors-ligne** contre les contrôleurs purs — sans avoir
  à surveiller en direct ni activer le log DEBUG.

## [2.0.8-beta62] — 2026-07-21

### Fixed

- **Le binding ne clignote plus `base ↔ no_charge_floor` en régime stable.** En
  décharge stable (le parc couvre la maison), la cible se pose à ~2 W du plancher
  `−controllable_mppt` ; `min()` changeait alors d'étiquette **à chaque tick** sur du
  bruit sub-watt — spam du logbook, fausses alertes, et surtout **le vrai binding
  masqué** — alors que la commande écrite ne bougeait pas d'un watt (observé en live le
  21/07 : `base ↔ no_charge_floor` pendant 9 min avec grid tenu à 0). Un clamp ne
  **revendique** désormais le label `binding` que s'il déplace réellement la cible de
  plus de **10 W** (`_BINDING_DEADBAND_W`) ; en dessous il est **toujours appliqué**,
  il ne renomme simplement pas le binding. **Aucun impact sur le contrôle** — c'est
  purement l'observabilité.

## [2.0.8-beta61] — 2026-07-12

### Added

- **Bridage PV anticipé (pré-frein depuis la prévision)** — nouveau `core/controllers/anticipation.py`
  + option **Bridage PV anticipé** (opt-in, désactivé par défaut). Le bridage actuel est
  **purement réactif** : il ne réduit la PV qu'**après** un export mesuré, derrière le filtre
  médian grille (~30 s), la fenêtre de settle (3 ticks) et la rampe (150 W/mouvement) — soit
  près d'une minute de latence. Sur une montée solaire rapide vers un parc quasi-plein, ça
  produit un gros **transitoire d'export** (observé : **−2687 W** à midi).
  SolarBalance calcule maintenant un **bilan de puits** — tout ce qui peut encore absorber :
  batteries controllables **+ batteries cloud** (non pilotables mais on connaît leur capacité de
  charge) **+ loads pilotables** — et le compare au **surplus prévu** (prévision PV − consommation
  apprise). Chaque puits est **moyenné sur l'horizon** : une batterie presque pleine garde son
  plein *débit* mais son énergie restante s'effondre, donc elle cesse de compter **avant**
  d'atteindre `soc_max` → le frein descend pendant qu'elle charge encore, pas une fois pleine.
  Quand le surplus prévu dépasse le bilan de puits (d'au moins la marge), un **plafond
  `preemptive_limit_w`** (= conso + bilan de puits) est passé au contrôleur de bridage, qui
  l'atteint via sa machinerie sticky/rampe/settle habituelle — l'onduleur est donc **déjà bridé
  quand le surplus arrive**.
  Garanties : **on ne jette jamais de solaire tant qu'un puits a de la place** (surplus ≤ budget
  → aucun bridage) ; le plafond n'est **jamais** sous la consommation, et le frein **ne fait que
  baisser** la limite PV → il ne peut **jamais** forcer un import ou un export. Les charges
  seulement *observées* (voiture qui charge hors Home Assistant, `local_ac_load`, talon) ne sont
  **pas** des puits : elles sont déjà dans la consommation prévue (pas de double-comptage).
  Sans entité de prévision PV, retour au comportement réactif pur.
- **Diagnostics** — capteur **Bilan de puits** (`sink_budget`), binaire **Bridage anticipé**
  (avec `sink_budget_w` / `forecast_surplus_w` / `preemptive_pv_limit_w` /
  `time_to_saturation_min`), mêmes champs dans le capteur `regulation_debug`, et
  `antic= budget= fsurp= prelim= t2sat=` dans la ligne de log par tick.
- **Options** — *Horizon d'anticipation* (min, défaut **12**, 5–30) et *Marge d'anticipation*
  (W, défaut **100**) dans la section avancée.

## [2.0.8-beta60] — 2026-07-07

### Fixed

- **La River (charge-priority) reçoit enfin le surplus PV, au lieu qu'il soit gobé par les
  STREAM.** La priorité de charge (beta58) ne s'appliquait qu'à la *répartition* d'une cible
  déjà positive ; or quand les grosses STREAM absorbent le surplus en self_powered (ou que
  l'équaliseur pousse une décharge pour alimenter une batterie cloud), la cible parc n'était
  jamais positive → la River restait à `+0`. Nouveau **charge-priority pull** : quand une
  batterie charge-priority est **sous sa cible** et qu'il y a un **surplus PV naturel**
  (export naturel), SolarBalance force la cible parc à **charger ce surplus** (override de la
  décharge équaliseur / d'un loop_base figé / du no-charge-floor). Le balancer route alors le
  surplus vers la River **en premier**, et le reste du parc passe en charge *bornée*
  (scheduled) au lieu de tout gober. Binding `charge_priority` dans la ligne de debug.
  Inactif (0) sans batterie charge-priority ou sans surplus → aucune incidence sur les autres
  setups.

## [2.0.8-beta59] — 2026-07-04

### Fixed

- **River 2 : le gate de charge se pilote via « Backup Reserve Level », pas « Max Charge
  Limit ».** Sur la River 2, le levier qui démarre/arrête réellement la charge réseau est la
  réserve de secours (Energy Backup/EPS actif). Le preset River 2 mappe donc désormais
  `charge_limit_soc_setpoint_entity` → `backup_reserve`. La logique du gate est inchangée
  (monter pour charger / redescendre au SoC courant pour stopper) — elle marche avec
  n'importe quelle entité %.
- **Libellés UI des nouveaux champs batterie.** `charge_limit_soc_setpoint_entity`,
  `charge_ceiling_soc_pct` et `charge_priority_target_soc_pct` ont enfin des labels/descriptions
  clairs (FR/EN), et la description de « Réserve / SoC mini » précise que **ce n'est pas** le
  gate de charge (à laisser vide sur une River 2 charge-only). Le gate et la priorité restent
  **opt-in par batterie** : aucune incidence sur les batteries qui ne les utilisent pas (STREAM,
  cloud).

## [2.0.8-beta58] — 2026-07-04

### Added

- **Priorité de charge (`charge_priority_target_soc_pct`).** Une petite batterie qu'on veut
  garder pleine (River 2 pour alimenter une box) se remplit **en premier** depuis le surplus,
  avant le reste du parc, tant que son SoC est sous la cible — au lieu de sa part minuscule au
  prorata de la capacité (~6 % face à la STREAM, qui n'ouvrait jamais le charge-gate). Elle
  sature à sa limite puis le reste du surplus repart vers le parc. Le preset River 2 met la
  cible à 90 %.

## [2.0.8-beta57] — 2026-07-04

### Fixed

- **Preset River 2 : bons noms d'entités ef_ble.** L'auto-détection visait `ac_charging_power`
  et `max_charge_level` ; les vrais sliders ef_ble sont **« AC Charging Speed »**
  (`ac_charging_speed`) et **« Max Charge Limit »** (`max_charge_limit`). Le preset (et la
  recette doc) sont corrigés — sans ça, les 2 consignes n'étaient pas auto-remplies et la
  charge ne s'écrivait nulle part.

## [2.0.8-beta56] — 2026-07-03

### Added

- **Preset « EcoFlow River 2 » dans l'assistant d'ajout** (comme la STREAM). Il pré-remplit la
  config charge-only (`max_discharge_power_w=0`, `charge_positive`, contrôlable, contrôle actif,
  capacité/puissance de la River 2 base ; ajuste pour Max/Pro) et **auto-détecte** les 4 entités
  ef_ble (`battery_level`, `ac_input_power`, `ac_charging_power`, `max_charge_level`) à partir du
  préfixe du device. Si le nommage diffère (autre intégration), les valeurs statiques restent
  appliquées et tu renseignes les entités à la main.

## [2.0.8-beta55] — 2026-07-03

### Added

- **Support des batteries « charge-only » (ex. EcoFlow River 2).** Une station qui charge
  (réseau + solaire) mais ne réinjecte pas se déclare simplement avec `max_discharge_power_w: 0`
  et une consigne de charge : le balancer ne lui alloue jamais de décharge, le publisher n'écrit
  que la charge en respectant le plafond SoC. Aucun nouveau « type » requis. Un garde-fou
  interdit désormais une consigne de décharge sur une batterie à `max_discharge_power_w=0`.
- **Charge-gate par limite SoC** (`charge_limit_soc_setpoint_entity` + `charge_ceiling_soc_pct`).
  Le slider « AC charging power » d'ef_ble (River 2) a un plancher de 100 W, donc impossible de
  commander 0. SolarBalance pilote alors la **limite de charge %** comme un interrupteur :
  surplus → limite au plafond + pilotage de la puissance ; plus de surplus → limite abaissée au
  SoC courant pour stopper (pas d'import fantôme ~100 W). Gate hystérétique pour ne pas clignoter.
  Recette complète : `docs/device-mapping.md` (« EcoFlow River 2 »).

## [2.0.8-beta54] — 2026-07-03

### Fixed

- **Puissance batterie STREAM lue à 0/`!` quand l'entité « saute » de device.** L'intégration
  EcoFlow BLE déplace parfois seule le capteur de puissance **système** de la batterie 1 vers
  la batterie 2 (et inversement) ; le `power_entity` figé pointait alors vers une entité morte
  → lecture 0/stale, batteries affichées à 0 alors qu'elles chargent. Une batterie accepte
  désormais **plusieurs entités de puissance candidates** (`extra_power_entities`) et le lecteur
  suit **celle qui est vivante**. La dé-duplication ÷N est indexée sur l'ensemble de candidats,
  donc deux batteries STREAM listant les deux mêmes capteurs comptent toujours la puissance
  système **une seule fois**, quelle que soit l'entité active.

  Config : sur **chaque** device batterie STREAM, mets les **deux** capteurs de puissance
  système dans « entités de puissance » (principale + candidates). YAML : `extra_power_entities`.

## [2.0.8-beta53] — 2026-07-03

> ⚠️ Les changements de la commit « 2.0.8-beta25 » (dwell anti-bascule) n'avaient jamais
> été publiés : le `manifest.json` était resté à beta52, donc HACS n'installait pas la
> nouveauté. Cette release les livre réellement.

### Added

- **Dwell anti-bascule charge↔décharge (`fleet_reversal_dwell_s`, Options → Avancé, défaut
  120 s).** Une STREAM solar-first doit changer de stratégie (`self_powered ↔ scheduled`,
  lent en BLE) pour passer de charge à décharge ; près de « maison = PV » le signe s'inverse
  chaque minute → thrash de mode + dépassement. Une fois le parc engagé dans une direction,
  il la garde (idle plutôt que d'inverser) tant que la demande opposée n'a pas persisté
  au-delà du dwell. `0` désactive.

### Fixed

- **Windup de charge borné à la vraie limite d'entité** (rappel beta52) : le balancer
  plafonne l'allocation de charge au `max` réel de l'entité (STREAM `charging_power_limit`),
  donc `unalloc` reflète la saturation et l'anti-windup ne s'emballe plus.

## [2.0.8] — 2026-06-25

> Cette version consolide les changements de la pré-release `2.0.8-beta24`.

### Changed (near-full curtailment redesign)

- **On charge maintenant doucement de 93 % à 100 %.** Près du plein, le garde-fou
  `no_charge_floor` forçait la batterie à **sortir son PV** au lieu de le charger →
  les derniers % ne se chargeaient pas. Désormais, près du plein, ce garde-fou est
  **désactivé** : la batterie **continue de charger son propre PV** (elle tape
  naturellement vers 100 %), et c'est le **bridage onduleur** qui rogne l'excédent.
- **Bridage au talon de consommation, plus de tout-ou-rien.** Comme la batterie
  charge (au lieu de couvrir la maison en sortant son PV), l'onduleur fournit la
  **consommation** et le bridage ne le coupe plus à 0 — il se cale sur le talon et
  ne rogne que le **vrai excédent** (moins de PV gaspillé).
- **Hystérésis near-full.** L'état « presque plein » s'enclenche à `soc_max − 2 %`
  mais ne se relâche qu'à `− 5 %` : un SoC posé sur le seuil ne fait plus **flipper**
  le bridage (et le no-charge-floor) à chaque tick → **fin du hunting** PV à plein.

### Changed

- **Routing PV équaliseur : consigne tenue (dwell) pour laisser la batterie cloud
  réagir.** L'autorisation de routing se réévaluait **chaque tick** → la consigne de
  la STREAM bougeait en continu et la Jackery (cloud, lente) n'avait jamais le temps
  de réagir. Désormais l'autorisation (et donc le plancher/la consigne) est **figée
  ~6 ticks** entre deux réévaluations ; entre-temps elle est plafonnée au PV courant
  (jamais de décharge batterie si le PV baisse).
- **Nouveau libellé de garde-fou `eq_pv_route`** : quand le parc route son PV vers une
  batterie cloud plus basse, le capteur « Garde-fou actif » affiche désormais
  `eq_pv_route` au lieu de `no_feed` — il **route**, il ne **bloque** pas. (Le
  « no_feed qui s'active trop vite » était surtout ce libellé trompeur + la
  réévaluation à chaque tick, tous deux corrigés ici.)

### Fixed

- **Yoyo du routing PV équaliseur (garde-fou qui basculait `equaliser` ↔ `no_feed`).**
  Le back-off de beta20 **remontait** l'autorisation (`_eq_pv_relax`) sur **tout** tick
  sans injection — y compris réseau ≈ 0 — donc elle **oscillait autour de 1.0** et la
  cible basculait entre « routage complet » et « bridé » toutes les 2-3 ticks → la
  STREAM yoyottait. Ajout d'une **bande morte** : l'autorisation **décroît** seulement
  sur une vraie injection (cloud n'absorbe pas), **remonte** seulement s'il y a de la
  marge d'import, et **tient** quand le réseau est équilibré. Pas plus de réglages,
  juste un comportement qui **se stabilise**. (Si la batterie cloud n'augmente pas sa
  charge en réponse au PV offert, l'autorisation se stabilise bas — pas de yoyo, mais
  la convergence dépend alors de la cloud, non-pilotable.)

### Fixed

- **Le routing PV de l'équaliseur était encore bloqué par l'anti-transfert
  (`no_feed`).** beta20 relaxait `no_export` et `grid_export` mais **pas** le garde-fou
  `no_feed` (anti-transfert batterie→cloud de beta16). Quand la batterie cloud
  **charge**, `no_feed` remontait la cible à ~0 (« ne décharge pas le parc pour
  alimenter une cloud qui se charge ») — exactement ce que l'équaliseur veut faire
  pour rééquilibrer. Désormais, quand l'équaliseur route du PV (`eq_discharge_floor_w`),
  `no_feed` autorise aussi la sortie jusqu'à `-mppt` : le parc peut router son **PV**
  (jamais sa batterie) vers la cloud plus basse. La STREAM va enfin sortir son PV dans
  la Jackery au lieu de se charger elle-même.

### Added

- **L'équaliseur SoC peut router le PV du parc vers une batterie cloud plus basse,
  jusqu'à l'entrée solaire.** Avant, l'anti-injection plafonnait la sortie du parc au
  point « réseau = 0 », calculé à partir du réseau **actuel** (qui inclut la décharge
  de la batterie cloud) : le parc **gardait son PV pour se charger lui-même** pendant
  que la batterie cloud (plus basse) se vidait pour couvrir la maison → SoC qui
  **divergent**. Désormais, quand l'équaliseur veut rééquilibrer (offre > 0), le parc
  peut **sortir son PV jusqu'à sa production solaire** (`-mppt`) — la **batterie n'est
  jamais vidée vers le réseau** (sortie ≤ entrée solaire) — pour soulager la batterie
  cloud et faire converger les SoC.
- **Bridage progressif** : si la batterie cloud n'absorbe pas (le réseau continue
  d'injecter sur plusieurs ticks), l'autorisation **rétrécit** (`_eq_pv_relax`) pour
  ne pas injecter du PV au réseau pour rien ; elle se **rouvre** doucement quand la
  cloud absorbe à nouveau. N'agit que **l'équaliseur actif** ; sinon anti-injection
  strict inchangé.

### Changed

- **Réglages avancés repliés dans une section (au lieu du Mode avancé global de
  HA).** Les knobs experts (tick, gain ZI, hystérésis, rampe max, fenêtre nuit,
  péremption cloud, dry-run) vivent maintenant dans une **section repliable
  « Avancé »** du formulaire de régulation, **fermée par défaut**. On la déplie d'un
  **clic, sur place** — plus besoin d'activer le « Mode avancé » global de HA dans
  son profil ni de rouvrir les options. Le mode simple reste épuré.
- **Fin de la dépréciation `show_advanced_options`** (que HA prévoit de supprimer en
  Core 2027.6) : SolarBalance n'en dépend plus.

### Changed (config diet — advanced knobs)

- **~12 réglages de tuning fin retirés du formulaire** (figés sur de bons défauts ;
  l'auto-réglage, toujours actif, les adapte en direct) :
  - **Équaliseur SoC** — ne reste que `on/off` + `offre max (W)` ; figés : gain,
    bande morte, pas de sonde, PV mini, cadence, cadence adaptative.
  - **Curtailment** — figés : pas de rampe, bande morte, settle ticks.
  - **ZI / anti-yoyo** — figés : filtre médian, settle ticks, seuil de settle
    (on garde `kp`, hystérésis, rampe max).
- **`dry_run` déplacé en mode avancé** (footgun : oublié sur ON, SB n'écrit jamais).

Les valeurs restent celles par défaut pour tout le monde ; le moteur les lit
toujours via leur défaut, seul le formulaire est allégé. Mode simple inchangé
(à part `dry_run` qui en sort), mode avancé nettement plus court.

### Removed (config simplification)

- **`stop_cloud_charge`** retiré : option niche et agressive (coupait la décharge du
  parc à 0 pour affamer une batterie cloud → forçait l'import maison), redondante
  avec l'anti-transfert désormais toujours actif (beta16).
- **`soc_equaliser_bidirectional`** retiré : pouvait provoquer un import bref
  (« déleste aussi sur la batterie cloud »). L'équaliseur reste unidirectionnel
  (ne décharge le parc que quand il est plus haut, jamais d'import provoqué).
- **`autotune_enabled`** retiré → l'auto-réglage des gains ZI/équaliseur est
  **toujours actif** (le désactiver ne faisait que laisser les boucles osciller).
- **`volatility_damper_enabled`** retiré → l'amortisseur de volatilité est
  **toujours actif** (anti-yoyo ; il se désengage seul quand le réseau est calme).
- **Contrôle manuel de charge** (entité `number` « Puissance de charge manuelle »)
  retiré : c'était un outil de diagnostic ponctuel (beta14), le comportement est
  compris, on n'encombre plus l'UI.

Quatre réglages et une entité de moins : config plus simple, moins de pièges.

### Changed

- **Anti-transfert batterie→batterie : toujours actif, réglage supprimé.** « Ne pas
  décharger le parc pour alimenter une batterie cloud qui se recharge seule »
  (`exclude_noncontrollable_charge`) est **retiré de la config** et le comportement
  est désormais **toujours appliqué**. C'était un piège : désactivé, le parc se
  vidait pour couvrir la charge d'une batterie cloud (transfert parc→réseau→cloud,
  ~30 % de pertes la nuit). La protection est **PV-safe** — nulle dès qu'il y a un
  surplus PV (n'a jamais bloqué l'injection PV vers la batterie cloud), elle n'agit
  que sur un import réseau réel. Un réglage de moins, zéro perte involontaire.

### Fixed

- **Ne plus écrire de consigne sur une entité indisponible.** La nuit, l'onduleur
  STREAM (BLE) décroche et ses entités passent en `unavailable` ; SB tentait quand
  même d'y écrire (consigne de charge / bridage de l'onduleur) → log spammé de
  « Referenced entities … are missing or not currently available » et écritures sans
  effet. `_write_power` / `_write_mode` sautent désormais une entité explicitement
  `unavailable` / `unknown` (une entité non encore chargée reste écrite, pour
  remonter une vraie erreur de config).

### Added

- **Entité « Puissance de charge manuelle (test) » (`number`).** Pour diagnostiquer
  le hardware : `> 0` force une **charge depuis le réseau** à cette puissance, `< 0`
  une décharge, `0` revient en normal. Pilote le mode `MANUAL_OVERRIDE` existant
  (**zéro-injection désactivée**) — la consigne est écrite par le **chemin de
  contrôle normal** (séquence mode-switch incluse), donc on teste la vraie chaîne
  d'écriture et on observe si/combien les batteries chargent. La cible SoC est 100 %
  (charge) / 0 % (décharge) pour ne pas s'arrêter pendant l'essai ; remettre à 0 pour
  rendre la main à la régulation.

### Fixed

- **Charge STREAM : la boucle zéro-injection passe en « forme vitesse » (intègre sur
  la dernière CONSIGNE, pas sur la puissance mesurée).** En s'appuyant sur le
  contrôleur PI EcoFlow STREAM communautaire (qui charge correctement), le constat
  est qu'il intègre sur `current_unified` (la consigne précédemment écrite), sans
  modéliser le PV ni diviser par quoi que ce soit : la consigne **converge toute
  seule** vers la valeur qui annule le réseau, peu importe ce qu'elle représente
  (PV + AC, total cellules…) ou un éventuel facteur d'échelle. SB se basait sur
  `current_fleet = batterie_mesurée − mppt`, **découplé de la commande** pour une
  STREAM (le PV charge en DC tout seul) → la boucle dérivait et ne montait jamais la
  charge. Désormais, **quand une batterie mode-switch en contrôle actif est
  présente**, la boucle intègre sur la **dernière consigne** (`_last_total_power_w`).
  Les batteries normales gardent la forme mesurée (éprouvée, auto-limitée). Le
  `réseau naturel` et les garde-fous continuent d'utiliser la puissance mesurée.

### Removed

- **Bricolages de consigne de charge abandonnés** (`+ PV propre`, division par
  `battery_count`, réglage `battery_count`) : la forme vitesse les rend **inutiles**
  (la boucle découvre la bonne valeur d'elle-même). La consigne de charge est de
  nouveau écrite **telle quelle** (arrondie à 10 W). Le séquençage mode-switch « une
  mutation par tick sur l'état réel » (beta8) et le log de debug par tick (beta12)
  sont conservés.

### Fixed

- **Consigne de charge = `surplus + PV / nombre de batteries`** (et non
  `(PV + surplus) / N`). Quand plusieurs batteries partagent une entité mais qu'**une
  seule est pilotable** (un seul `charging_power_limit`), cette batterie doit charger
  **sa part de PV** (`PV_total / N`, les autres chargent leur PV elles-mêmes) **plus
  la TOTALITÉ du surplus AC** à récupérer. beta11 divisait aussi le surplus → la
  batterie n'en absorbait que la moitié. La consigne de **décharge** n'est plus
  divisée non plus (la seule batterie pilotable porte toute la cible). `battery_count`
  garde le même sens (nombre de batteries derrière l'entité).

### Added

- **Log de debug par tick** (`custom_components.solarbalance: debug`) : la couche de
  contrôle imprime `alloc / PV / count / soc → charge / décharge` par batterie, et la
  séquence mode-switch (état réel du `select`, puissance opposée réelle, étape 1/2/3)
  — pour diagnostiquer pas à pas ce que SB écrit vs ce que la box applique.

### Changed

- **Consigne de charge = `(solaire batterie + surplus autres onduleurs) / nombre de
batteries`.** La box plafonne la **charge totale des cellules** (PV inclus), donc
  la consigne doit couvrir le PV que la batterie absorbe elle-même **plus** le
  surplus AC à récupérer des autres onduleurs. Toujours arrondie à 10 W. La consigne
  de décharge est elle aussi divisée par le nombre de batteries.

### Added

- **Réglage « nombre de batteries par entité » (`battery_count`, défaut 1).** Quand
  plusieurs batteries (ex. 2 EcoFlow STREAM) partagent un même jeu d'entités, la box
  applique la consigne **par batterie** ; SB divise donc la consigne écrite par ce
  nombre pour atteindre la cible du parc. Réglable dans le sous-formulaire batterie
  (UI) ou en YAML (`battery_count`).

### Changed

- **Consigne de charge quantifiée par pas de 10 W.** La consigne de charge reste
  le surplus à absorber (le surplus des autres onduleurs, repère AC), écrit **tel
  quel** (ni `+ PV propre`, ni divisé par le nombre de batteries), mais elle est
  désormais **arrondie à 10 W** : une box STREAM est lente en BLE et le micro-bruit
  du PI ne lui sert à rien — on évite ainsi de la spammer d'écritures inutiles.

## [2.0.8-beta9] — 2026-06-24

### Fixed

- **Revert de beta6 : la consigne de charge ne doit PAS ajouter le PV propre.** Sur
  une STREAM, `charging_power_limit` est la **charge depuis le réseau (AC)** — la
  box charge son PV toute seule côté DC. Ajouter le PV (beta6) faisait tirer
  `surplus + PV` **du réseau** → sur-import. La consigne de charge est de nouveau la
  **cible de régulation telle quelle** (le surplus à absorber depuis l'AC), donc on
  ne tire **que le surplus**, pas le PV. Suppression du paramètre `mppt_by_device`.

### Known limitation

- **Plusieurs batteries STREAM sur une seule entité** : la box applique
  `charging_power_limit` **par batterie**, donc écrire `S` tire `N·S` du réseau (ex.
  2 batteries : `100 W` → `200 W`). En attendant un réglage « nombre de batteries
  par entité », baisser le `max_charge` de l'entité (~`max/N`) pour éviter le
  sur-import pendant les tests.

### Fixed

- **Batterie mode-switch (STREAM) : la séquence de charge est désormais étalée sur
  plusieurs ticks (une mutation par tick), gardée sur l'état RÉEL.** Suite de
  beta7 : réaffirmer le mode ne suffisait pas, car SB écrivait le mode **et** la
  puissance dans le **même tick**. La box (BLE, lente) applique ses actionneurs
  **un à la fois** et n'honore `charging_power_limit` **qu'une fois réellement en
  `scheduled`** — écrit trop tôt, il est ignoré. `_apply_mode_battery` exécute
  maintenant **une seule mutation par tick, dans l'ordre, en lisant l'état réel de
  l'appareil et en s'arrêtant tant qu'elle n'a pas "pris"** : (1) `base_load_power`
  → 0, (2) `energy_strategy` → `scheduled`, (3) `charging_power_limit` → cible. En
  régime établi les deux premières étapes passent et seule la puissance est mise à
  jour ; un base load que la box se réimpose, ou une stratégie qu'elle repasse en
  `self_powered` toute seule, sont réaffirmés (puissance retenue) jusqu'à ce que ça
  tienne. Calqué sur le contrôleur PI EcoFlow STREAM communautaire (chaque étape
  suivie d'un `stop`).

## [2.0.8-beta7] — 2026-06-24

### Fixed

- **Batterie mode-switch (STREAM) : la consigne de charge était ignorée par la
  box.** Le `select` de mode (`energy_strategy`) était **latché** : SB ne le
  réécrivait que sur un _changement_ de direction. Or une STREAM **repasse
  `energy_strategy` en `self_powered` toute seule** (son défaut, après un temps ou
  une reconnexion BLE). SB croyait être resté en `scheduled` et **ne réaffirmait
  jamais** le mode → la box restait en `self_powered` → **`charging_power_limit`
  était ignoré même quand il était bien supérieur à la production PV** (consigne
  haute, batterie qui ne bouge pas). Nouveau `_ensure_mode` : à chaque tick, en
  régime établi, SB **lit l'état réel du select** et réaffirme l'option voulue si
  la box a dérivé — exactement comme `_ensure_zero` le fait déjà pour le
  `base_load_power` (beta28). Combiné à beta6, la STREAM charge enfin le surplus.

## [2.0.8-beta6] — 2026-06-24

### Fixed

- **Batterie avec ses propres panneaux : ne chargeait pas le surplus (export
  stable).** Pour une batterie qui a un **rôle MPPT sur le même appareil** (ex.
  STREAM avec son entrée solaire), la consigne de charge écrite était la cible de
  régulation en repère « sortie-AC » (`current_fleet = batterie − MPPT`), **sans
  rajouter le PV** que la batterie absorbe déjà toute seule. La **commande** était
  donc **déconnectée du réel** → la boucle ne montait jamais la charge AC pour
  avaler le surplus d'un autre producteur → **export stable** alors que la batterie
  avait de la place. Désormais la consigne de charge = **allocation + PV propre de
  l'appareil** (plafonnée à `max_charge_power_w`) : la batterie absorbe son PV **et**
  tire le surplus de l'AC, le repère redevient cohérent et la boucle **converge
  vers réseau = 0**. Sans effet pour une batterie sans panneaux propres, ni sur la
  décharge.

### Added

- **Prévision de conso par segment de jour (semaine / week-end).** Le profil n'est
  plus seulement « heure-de-la-journée » : il distingue **semaine** et **week-end**
  (souvent très différents — maison occupée la journée), pour chacun 24 cases
  horaires. Appris en ligne et **pré-chargé depuis l'historique par segment** ; le
  planner choisit le bon segment pour **chaque créneau** de l'horizon (y compris le
  passage à demain). L'ancien profil persisté (plat) est **migré** dans les deux
  segments.
- **Capteur d'écart prévu/réel** _« Écart prévu/réel (conso) »_ (diagnostic) =
  conso **prévue − réelle** de l'heure courante → tu vois en un coup d'œil si le
  profil colle à la réalité (≈ 0 = bon).

## [2.0.8-beta4] — 2026-06-24

### Added

- **Réaction à la chute PV (opt-in).** Quand une chute soudaine de PV est détectée
  (beta3), la nouvelle option **« Compensation chute PV »** fait **décharger
  immédiatement la perte** depuis la batterie au lieu d'attendre la boucle PI. Elle
  **réutilise le settle anti-yoyo éprouvé** (gèle le PI → pas de double-comptage,
  feed-forward one-shot borné), ne s'arme que si aucun settle n'est déjà actif, et
  est **désactivée par défaut**. _Configurer → Régulation → « Compensation chute
  PV »_.

## [2.0.8-beta3] — 2026-06-24

### Added

- **Détection de chute PV temps réel (passage nuageux) — observabilité.** Un
  détecteur compare la production PV au **pic des dernières mesures** : une **chute
  soudaine** (bord de nuage) ressort comme un grand écart `pic − actuel`, tandis
  qu'un **déclin graduel** (coucher de soleil) n'en déclenche pas. Exposé via un
  **binary sensor « Chute PV »** (catégorie diagnostic, attribut `drop_w`) pour
  voir quand/combien ça chute. La **réaction rapide** (couvrir la perte depuis la
  batterie sans attendre la boucle) sera ajoutée ensuite, calibrée sur ces mesures.

### Added

- **Prévision de conso — pré-chargement depuis l'historique (recorder).** Au
  démarrage, le profil de conso est **amorcé depuis les statistiques long-terme**
  (moyenne horaire) du capteur _consommation de fond_ → **précis dès le 1ᵉʳ jour**
  pour qui a déjà des semaines de données, au lieu d'attendre l'apprentissage en
  ligne. Ne remplit que les **heures encore inconnues** (le profil appris/persisté
  prime) ; tout échec recorder est un **no-op** (l'apprentissage en ligne prend le
  relais). Complète la beta1 (« les deux » : historique **+** en ligne).

## [2.0.8-beta1] — 2026-06-24

### Added

- **Prévision de conso — profil heure-par-heure appris (Wave 4, prédictif).** Le
  planner prédictif n'utilise plus seulement un **talon plat** : il s'appuie sur un
  profil de **conso de fond appris par heure de la journée** (EMA inter-jours,
  ~3 jours de mémoire), **persisté** et restauré au redémarrage → le plan
  **anticipe les pics matin/soir** au lieu de supposer une conso constante. Modèle
  pur `ConsumptionProfile` (testé), branché dans `build_forecast_slots`. Nouveau
  capteur diagnostic _« Conso prévue (heure courante) »_ pour voir le profil se
  remplir. Apprentissage **en ligne** pour l'instant ; le **pré-chargement depuis
  l'historique (recorder)** arrivera en beta2 (même modèle).

## [2.0.7] — 2026-06-24

Stable release consolidating the `2.0.7-beta1…29` line (full per-beta detail
below). Headline changes since **2.0.6**:

### Added

- **Active control of mode-switch batteries (EcoFlow STREAM).** Drive **charge and
  discharge** of a battery that exposes an operating-mode select instead of a signed
  setpoint, via configurable `mode_setpoint_entity` + `charge/discharge_mode_option`
  (e.g. `scheduled` / `self_powered`); generic, the STREAM is the first consumer.
- **Device-preset add wizard** — picking a model (EcoFlow STREAM / inverter,
  generic) pre-fills the form and **auto-detects matching entities** from the
  device prefix. Plus a **two-mode config** (simple / HA Advanced) and a
  **dependent-field wizard** (tariff & regulation details shown only when relevant).
- **MPPT/inverter temperature** sensor and mapping.
- **Observability — “Active clamp” diagnostic**: which guard set the fleet target
  each tick (`base` / `no_feed` / `stop_cloud` / `no_charge_floor` / `grid_*`).

### Fixed / hardened (regulation)

- Morning oscillation damping (fleet base + adaptive volatility damper) and a
  **smoothed cloud-charge signal** so a dumb cloud battery’s bursts no longer chop
  the fleet.
- **Gradual + settle PV curtailment** (no more 0↔peak sawtooth) and **near-full
  curtailment** when the fleet can no longer absorb a surplus.
- **Cloud-charge guards**: don’t drain the fleet to feed a self-charging cloud
  battery; _stop-cloud_ acts in **surplus only**, never under a real load (EV).
- Local AC-load compensation, non-controllable-battery staleness handling, and
  keeping a mode-switch battery’s opposite direction at 0 every tick (no
  simultaneous charge+discharge).

### Internal

- The whole aggregate-target clamp pipeline extracted to a **pure
  `resolve_total_power`** with an option-combination test matrix. **501 tests**,
  mypy `--strict` clean on `core/`, `core/` import-pure.

## [2.0.7-beta29] — 2026-06-23

### Tests

- **Régression du lissage cloud (beta27)** : test multi-tick qui vérifie qu'un
  à-coup de charge de la batterie cloud est amorti par l'EMA (~0.2 par tick) au
  lieu de passer en plein → fige le correctif anti-yoyo matinal. **501 tests**.

### Docs

- **Guide « EcoFlow STREAM (pilotage actif, via le wizard) »** dans
  [device-mapping](docs/device-mapping.md) : topologie en 2 appareils BLE
  (batterie `ef_xxxxxx` + onduleur `ef_bk…`), ajout via les presets, mode-switch
  charge/décharge (`scheduled`/`self_powered`), batterie cloud non-pilotable
  (Jackery) en complément, options de régulation recommandées, et débogage via le
  capteur « Garde-fou actif ».

### Fixed

- **Charge STREAM inefficace : charge ET décharge en même temps.** En mode charge,
  la STREAM **ré-imposait sa propre « base load »** (ex. `base_load_power` = 399 W
  alors qu'on chargeait à 1000 W) → elle **chargeait et déchargeait à la fois**, donc
  ne chargeait quasiment pas. Le publisher ne remettait la direction opposée à 0
  **qu'au changement de mode**, jamais ensuite. Désormais il **ré-affirme la
  direction opposée à 0 à chaque tick** : il **lit l'état réel** de l'entité et ne
  réécrit 0 **que** si elle a dérivé (la latch interne ne suivait que ce que SB avait
  écrit, jamais ce que l'appareil change seul). Plus de charge+décharge simultanée.

### Fixed

- **Yoyo matinal : lissage du signal de charge de la batterie cloud.** La trace
  « Garde-fou actif » l'a prouvé : une batterie cloud « bête » (Jackery) charge en
  **créneaux** (0↔~110 W, ~30 s), et réagir tick-par-tick faisait **hacher la
  décharge du parc** (0↔300 W) via `no_feed`/`stop_cloud` — alors que le **réseau
  restait bon** (preuve : dès que le Jackery arrête de pulser, la consigne redevient
  parfaitement lisse). La puissance de charge des batteries non-pilotables est
  désormais **lissée (EMA ~90 s)** avant d'alimenter les garde-fous cloud : ils
  s'engagent sur une charge cloud **soutenue**, plus sur chaque à-coup → fini le
  cyclage inutile de la STREAM le matin. Le signal de charge cloud est aussi
  **calculé une seule fois** et réutilisé (offset, plancher, no-feed, stop-cloud).

### Added

- **Observabilité : « Garde-fou actif » (quel clamp a fixé la cible).** La fonction
  pure `resolve_total_power` renvoie désormais **quel garde-fou** a déterminé la
  cible parc ce tick — `base` / `equaliser` / `no_export` / `no_charge_floor` /
  `no_feed` / `stop_cloud` / `grid_import` / `grid_export` — exposé en **capteur
  diagnostic** _« Garde-fou actif »_. Plus besoin de deviner depuis les courbes :
  une cible surprenante s'explique d'elle-même (« c'est le no-feed qui plafonne la
  décharge »). Capteur de débogage self-service pour ta carte Debug ZI.

### Tests

- +2 tests purs sur la trace (`binding`). **499 tests**, mypy `--strict` / `core/`
  pur OK.

### Changed

- **Régulation vérifiable : pipeline de clamps extraite en fonction pure
  (refactor, sans changement de comportement).** Toute la séquence qui résout la
  cible parc (cible de base → offre équaliseur → no-export → plancher no-charge →
  no-feed / stop-cloud → contraintes réseau) vit désormais dans une **fonction
  pure** `resolve_total_power(RegulationInputs)`
  ([core/controllers/regulation.py](custom_components/solarbalance/core/controllers/regulation.py)),
  au lieu d'être disséminée dans le tick du coordinator. Bénéfices : lisible d'un
  bloc, **testable unitairement** (mypy `--strict`, sans Home Assistant), et les
  **combinaisons d'options** sont enfin couvertes.
- **`natural_grid` unifié** : le « réseau naturel » (`grid − parc`, invariant à
  l'action du parc) est calculé **une seule fois** et réutilisé (détection de
  déficit, garde-fous cloud, diagnostic) au lieu de trois calculs séparés.

### Tests

- **Matrice de combinaisons d'options** (10 tests purs sur `resolve_total_power` :
  surplus/déficit, no-export, plancher no-charge, no-feed, stop-cloud
  surplus-vs-charge, offre équaliseur, contraintes réseau) + **4 tests de
  caractérisation e2e** figeant le comportement actuel. Filet anti-régression
  d'interactions. **497 tests** au total, mypy `--strict` et `core/` pur OK.

### Fixed

- **Yoyo pendant la charge voiture (VE) avec `stop_cloud_charge` activé.**
  L'option « Stopper une batterie cloud qui se charge » coupait la décharge du
  parc à 0 **dès que** la batterie cloud (Jackery) chargeait — **même en déficit**
  (grosse conso comme un VE). Or la Jackery charge **par à-coups** : couper →
  relâcher → couper… produisait une **dent de scie** (consigne décharge 0↔1100)
  alors que la voiture tirait une puissance **constante**, et ça ne stoppait même
  pas la Jackery (qui charge depuis le réseau). Désormais la coupure ne s'applique
  **que si l'import réseau correspond essentiellement à la charge du cloud**
  (contexte **surplus**) : `réseau_naturel − charge_cloud ≤ hystérésis`. En
  présence d'une **vraie conso**, le parc **continue de la couvrir** (plus de
  yoyo) ; le garde-fou « ne pas nourrir le cloud » (no-feed) reste actif et borne
  juste la décharge pour ne pas alimenter la charge du cloud.

## [2.0.7-beta23] — 2026-06-22

### Fixed

- **Yoyo d'injection / bridage onduleur en « tout ou rien » (0 ↔ pic).** Le
  curtailment **claquait** la limite à `production − excès` d'un coup, puis la
  **relâchait par paliers** ; combiné au **temps mort** de l'EcoFlow (BLE +
  onduleur) et à la latence du compteur, ça produisait une **dent de scie** (la
  limite sautait entre 0 et le pic), et près du plein la batterie ne pouvait plus
  amortir. Désormais le contrôleur :
  - bouge **graduellement** (≤ `ramp_w` par mouvement, dans les deux sens) → la
    limite **converge** sur l'équilibre au lieu de claquer ;
  - tient une **fenêtre de stabilisation** (`settle_ticks`, défaut **3**) après
    chaque mouvement, le temps que l'onduleur + la mesure rattrapent → fini la
    boucle dent-de-scie due au temps mort.
  - Réglages **mode expert** : _Bridage : pas max / bande morte / fenêtre de
    stabilisation_ dans _Configurer → Régulation_.
  - Effet de bord bénéfique : en ne coupant plus la production à 0, le **surplus
    reste disponible** pour charger la batterie pilotable.

## [2.0.7-beta22] — 2026-06-22

### Added

- **Température MPPT / onduleur.** Le rôle MPPT accepte désormais un
  `temperature_entity` — disponible dans la config **« onduleur seul »** ET
  **batterie+MPPT** (champ `mppt_temperature_entity`). Un capteur dédié l'expose
  (`mppt_temperature`, °C) et le panneau l'affiche dans « Par appareil ». Plombé de
  bout en bout (modèle, lecture, capteur, YAML, UI, traductions FR/EN).

## [2.0.7-beta21] — 2026-06-22

### Fixed

- **Panneau HTML — section « Par appareil » : les micro-onduleurs n'apparaissaient
  pas.** La collecte ne prenait que les métriques **batterie** (`batt_soc`,
  `batt_power`…) ; un appareil **MPPT seul** (micro-onduleur) n'avait aucune de ces
  entités → jamais affiché. Le panneau collecte désormais aussi `mppt_power` et
  `mppt_limit` → chaque onduleur s'affiche avec **Production solaire** et **Limite
  production** (et un appareil batterie+MPPT combiné montre ces lignes en plus).
  _(Rafraîchir la page / vider le cache si le panneau ne se met pas à jour.)_

## [2.0.7-beta20] — 2026-06-22

### Changed

- **Vie privée : suppression d'un n° de série de micro-onduleur réel du test.**
  `ef_bk1611` (exemple concret dans un test de preset) remplacé par le placeholder
  `ef_bkxxxx`. Aucun impact fonctionnel (préfixe découvert à l'exécution).

## [2.0.7-beta19] — 2026-06-22

### Added

- **Preset « EcoFlow STREAM (onduleur) » pour le flux « ajouter un onduleur ».**
  Le micro-onduleur de la STREAM est un **appareil BLE séparé** (préfixe `ef_bk…`)
  à ajouter en **MPPT uniquement**. Nouveau preset qui auto-détecte sa **puissance
  de sortie** (`grid_power`) et surtout sa **limite de production**
  (`maximum_output_power`), active le **pilotage actif** et propose `peak_power_w`
  800 W → le **bridage onduleur** (beta15) est câblé en 2 clics.
- **Presets filtrés par type d'équipement.** Chaque modèle ne s'affiche que pour
  les flux pertinents : _EcoFlow STREAM_ sur batterie / batterie+MPPT, _EcoFlow
  STREAM (onduleur)_ sur onduleur seul. Pas de collision de détection (probe sur
  une entité unique au modèle).

## [2.0.7-beta18] — 2026-06-22

### Changed

- **Vie privée : suppression d'un numéro de série réel des exemples.** Un préfixe
  d'appareil EcoFlow réel (`ef_60605`) servait d'exemple dans des descriptions de
  champs, commentaires et tests. Remplacé partout par le placeholder générique
  `ef_xxxxxx`. Aucun impact fonctionnel : le préfixe d'appareil est **découvert à
  l'exécution** chez chaque utilisateur, jamais codé en dur.

## [2.0.7-beta17] — 2026-06-22

### Added

- **Assistant « modèle d'appareil » à l'ajout d'une batterie / batterie+MPPT /
  MPPT.** Une 1ʳᵉ étape propose une **liste déroulante de modèles** (_Générique_,
  _EcoFlow STREAM_) ; au choix, le formulaire s'ouvre **pré-rempli** :
  - **valeurs par défaut** du modèle (puissances, `soc_min`/`soc_max`, convention
    de signe, pilotage actif, options de mode `scheduled`/`self_powered` pour la
    STREAM, `peak_power_w`…) ;
  - **entités auto-détectées** : SB repère le **préfixe d'appareil** (ex.
    `ef_xxxxxx`) via une entité unique au modèle, puis mappe chaque rôle par suffixe
    (`battery_level`→SoC, `charging_power_limit`→charge, `base_load_power`→décharge,
    `energy_strategy`→mode, `backup_reserve`→réserve, `pv_power_total`→MPPT…) et
    **suggère un nom** (« EcoFlow STREAM xxxxxx ») ;
  - tu **vérifies/ajustes** puis valides. _Générique_ = formulaire vide (inchangé).
  - La **reconfiguration** (édition) ne passe pas par l'étape modèle.
  - Architecture **générique** (registre de presets) : ajouter d'autres marques
    consistera à déclarer leurs defaults + patterns de suffixes.

## [2.0.7-beta16] — 2026-06-22

### Added

- **Contrôle de la charge des batteries « à changement de mode » (générique) —
  1ᵉʳ client : EcoFlow STREAM.** On peut désormais piloter la **charge** d'une
  batterie qui n'expose pas un setpoint signé mais un **sélecteur de mode** (ex.
  STREAM via l'intégration _Unofficial EcoFlow BLE_ : `energy_strategy`
  `scheduled`/`self_powered`). Le `mode_setpoint_entity` (déjà présent) reçoit des
  **options de mode configurables** :
  - `charge_mode_option` (défaut `charge`), `discharge_mode_option` (défaut
    `discharge`), `idle_mode_option` (défaut **vide** = mode laissé tel quel à
    l'arrêt), `mode_switch_zeroes_opposite` (défaut vrai).
  - Au **changement de direction**, le publisher exécute la séquence **dans
    l'ordre et en bloquant** : met à zéro la direction opposée → bascule le mode →
    écrit la puissance de la nouvelle direction (un onduleur mono-direction ignore
    une puissance écrite dans le mauvais mode). En régime établi, rien ne bascule
    (writes latchés). Le `backup_reserve` est déjà poussé chaque tick.
  - **Générique** : les batteries à setpoint signé simple sont **inchangées** ;
    n'importe quelle marque avec un select de mode se câble via ses propres
    options. Exemple STREAM : `mode_setpoint_entity=select.ef_..._energy_strategy`,
    `charge_mode_option=scheduled`, `discharge_mode_option=self_powered`,
    `charge_power_setpoint_entity=number.ef_..._charging_power_limit`,
    `discharge_power_setpoint_entity=number.ef_..._base_load_power`,
    `reserve_soc_setpoint_entity=number.ef_..._backup_reserve`.
  - Bénéfice : SB **stocke le surplus dans la STREAM** au lieu de brider l'onduleur
    (beta15) ou d'exporter → meilleure autoconso.

### Changed

- **Mode à l'arrêt** : par défaut, le `mode_setpoint_entity` n'est **plus** forcé à
  `idle` quand la batterie est au repos (un sélecteur de stratégie vendeur n'a
  souvent pas d'option « idle » → écriture en erreur). Les puissances sont mises à
  zéro de toute façon. Pour retrouver l'ancien comportement, définir
  `idle_mode_option: idle`.

## [2.0.7-beta15] — 2026-06-17

### Fixed

- **Bridage onduleur jamais déclenché batteries quasi-pleines → injection
  permanente.** Le curtailment ne s'enclenchait que si le balancer **n'arrivait
  pas à placer** la charge (`unallocated_w > 1`). Or une batterie n'est sortie de
  l'allocation qu'à `soc_pct ≥ soc_max` (défaut **95 %**) : à **94 %** elle est
  encore « éligible », le surplus est donc **alloué** dessus → `unallocated ≈ 0`
  → **jamais saturé** → aucun bridage, alors qu'on **injecte** (et la STREAM, dont
  la charge n'est pas pilotable, ne l'absorbe pas). Désormais la saturation se
  déclenche aussi quand **tout le parc pilotable est à moins de 2 % de son
  plafond** (la charge tapère/n'est pas honorée près du plein) : si on injecte
  au-delà de la consigne, **l'onduleur est bridé**. Le bridage ne se resserre
  toujours que pendant une injection réelle (pas de bridage intempestif).

## [2.0.7-beta14] — 2026-06-17

### Added

- **Configuration en assistant (wizard) — plus aucun champ inutile.** Les
  sections _Tarif_ et _Régulation_ affichent désormais les réglages dépendants
  **uniquement quand leur option est activée**, en **enchaînant des étapes** (pas
  de réouverture manuelle — tu valides et l'étape suivante apparaît) :
  - **Tarif** : étape 1 = prix + type ; puis selon le type → **HC/HP** (`hc_hp`),
    **Tempo** (`tempo`) ou **spot** (`spot`). En _flat_, aucune étape en plus.
  - **Régulation** : après l'écran principal, sous-étapes affichées seulement si
    le toggle correspondant est coché — **internes équaliseur** (équaliseur
    activé), **SoC cible Tempo rouge** (prép. Tempo rouge), **puissance mini
    délestage** (délestage activé), **phénomènes météo** (entité météo
    renseignée). Les sous-étapes s'enchaînent automatiquement.
  - Combiné au **Mode avancé** (beta13) : l'écran principal reste simple/expert,
    et les détails de fonctionnalités ne s'affichent que s'ils servent.

## [2.0.7-beta13] — 2026-06-17

### Added

- **Configuration en deux modes (simple / expert).** La section _Régulation_ est
  devenue dense. Elle s'appuie désormais sur le **Mode avancé natif de Home
  Assistant** (Profil → _Mode avancé_) :
  - **Simple** (toujours visible) : activer ZI + consigne, pilotage actif,
    contrôle des charges, puissance souscrite, phases, réserve backup, dry-run,
    notifications, équaliseur on/off, et les **comportements** (compensation prise
    AC, amortisseur volatilité, no-export, stop-cloud, exclusion charge cloud,
    prédictif, délestage, protection surcharge, Tempo, vacances, vigilance météo).
  - **Expert** (Mode avancé HA activé) : tous les **gains/filtres** (kp,
    hystérésis, max_ramp, fenêtre filtre réseau, settle, fenêtre baseline,
    péremption cloud, phénomènes météo) et les **internes équaliseur** (max, gain,
    bande morte, pas, cadence, min PV, bidirectionnel) + autotune.
  - Masquer un champ expert **ne réinitialise pas** sa valeur (fusion préservée).

## [2.0.7-beta12] — 2026-06-17

### Fixed

- **Oscillations matinales (solaire faible/variable) — l'amortisseur agit aussi
  sur la base ZI.** L'amortisseur de volatilité (beta10) ne lissait que le
  **réseau**, mais l'oscillation du matin passe par **`current_fleet`** (=
  batterie − MPPT) : le **MPPT bruité** du lever + la batterie qui hunt à la
  bascule charge↔décharge jittaient la cible ZI **sans passer par l'amortisseur**
  (d'où le `réseau naturel` qui oscillait encore plus que le réseau réel).
  L'amortisseur adaptatif s'applique désormais **aussi à `current_fleet`** (même
  option `volatility_damper_enabled`) → la base de la régulation est lissée quand
  c'est agité → fini le hunting de la zone de bascule matinale.

## [2.0.7-beta11] — 2026-06-17

### Fixed

- **Données batterie non-pilotable périmées → garde-fous gelés.** Une batterie
  cloud (Jackery) peut **mettre des minutes** à rafraîchir ses données dans HA →
  les garde-fous par-batterie (cloud-charge, no-feed, stop-cloud) agissaient sur
  une **puissance périmée** ≠ réalité → décisions à côté / yoyo, et un **gros saut
  à la mise à jour**. Désormais, au-delà du **seuil de péremption** (défaut
  **300 s = 5 min**, réglable, 0 désactive), la puissance de la batterie
  non-pilotable est jugée **non fiable** : les garde-fous **la sautent** et
  laissent la **ZI** (compteur PDL temps réel, qui reflète son effet réel) tenir
  la barre. L'équaliseur reste actif (basé SoC, qui ne « saute » pas).
  Réglage _« Péremption batterie non-pilotable (s) »_ dans _Configurer →
  Régulation_.

## [2.0.7-beta10] — 2026-06-17

### Added

- **Amortisseur de volatilité adaptatif** (option, défaut **désactivé**) — les
  charges **type moteur** (machine à laver, pompe) oscillent trop vite pour que
  la batterie suive ; la ZI courait après → **yoyo**. Le damper mesure la
  **volatilité** (EMA des variations tick-à-tick du réseau) et **lisse d'autant
  plus que c'est agité** : la batterie suit la **moyenne lente** (autoconso
  conservée) et le **réseau absorbe les à-coups** rapides. Quand c'est calme,
  réactivité normale (pas de retard sur les vraies variations lentes). Réglage
  _« Amortisseur de volatilité adaptatif »_ dans _Configurer → Régulation_.

## [2.0.7-beta9] — 2026-06-17

### Added

- **Compensation prise AC locale** — le **yoyo résiduel du réseau correspondait
  exactement aux cycles de la prise AC du stream.** Cause : une charge sur la
  sortie AC du parc est **servie par lui mais invisible au compteur** ; quand elle
  s'allume/s'éteint, la sortie du parc change brusquement → la ZI croit que le
  parc a bougé et **corrige (petit yoyo)**. Nouveau réglage _« Capteurs de conso
  prise AC locale »_ (multi-entités, ex. `Consommation AC stream`) : SB
  **retranche** cette charge de la **contribution réseau du parc**
  (`current_fleet = (batterie − MPPT) + conso_prise_AC`) → ses cycles **ne
  perturbent plus** la boucle de régulation. Vide par défaut (sans effet).

## [2.0.7-beta8] — 2026-06-17

### Added

- **Option « Stopper une batterie cloud qui se charge »** (défaut **désactivé**,
  opt-in). Quand une batterie **non-pilotable charge** et que le parc la
  nourrirait, on **coupe la décharge du parc à 0** : la maison passe sur le
  **réseau**, la production locale dont se nourrit la batterie cloud disparaît →
  elle **arrête de charger**. Plus agressif que le garde-fou par défaut (qui se
  contente de ne pas la nourrir, elle tire alors sur le réseau).
  - **Ciblé** : ne se déclenche que quand le parc nourrirait réellement la charge
    cloud (offset garde-fou > 0), pas à chaque fois qu'une cloud charge.
  - **Inerte pour un parc 100 % pilotable** (aucune batterie non-pilotable → la
    condition ne se déclenche jamais).
  - **À assumer** : importe pour la maison tant que c'est actif, et repose sur la
    réaction de la batterie cloud (elle arrête bien si elle se nourrissait de la
    sortie locale).

## [2.0.7-beta7] — 2026-06-17

### Fixed

- **Le parc ne nourrit plus, _instantanément_, une batterie cloud qui se charge
  seule.** Le garde-fou existant (2.0.1) passait par le **setpoint ZI** → la rampe
  PI lente (kp ~0,2) laissait le stream **décharger pour alimenter la charge de la
  Jackery** pendant un long transitoire (batterie basse → batterie haute, lossy).
  Ajout d'une **butée directe** (projection 1 tick) : la décharge du parc est
  plafonnée pour que le réseau reste ≥ l'import toléré de la batterie cloud → la
  batterie cloud **tire sur le réseau**, plus sur le parc. Effet immédiat au lieu
  de plusieurs minutes.

### Known limitation

- La batterie cloud (non pilotable) qui décide de charger à SoC élevé tire alors
  **sur le réseau** (on ne peut pas l'en empêcher) ; SB évite juste qu'elle vide
  le parc. Le vrai correctif est côté batterie cloud (ne pas charger à 94 %).

## [2.0.7-beta6] — 2026-06-17

### Fixed

- **Surplus masqué : le parc peut enfin charger son solaire au lieu de le donner
  à la batterie cloud déjà pleine.** Le plancher anti-charge (beta4) jugeait le
  surplus sur le **réseau brut** ; or une batterie non-pilotable (Jackery) qui
  **charge** absorbe le surplus et le **masque** au compteur (~0) → le plancher
  forçait le stream (SoC bas) à **sortir son solaire** au lieu de **charger**, et
  le surplus partait dans la Jackery (SoC haut). Le plancher est désormais **levé
  quand une batterie non-pilotable est en charge** (= surplus réel absorbé) → le
  stream charge son **propre solaire**.

### Known limitation

- La **charge du stream n'étant pas pilotable**, il ne peut charger que **son
  propre solaire** ; le surplus déjà présent sur le bus AC reste happé par la
  batterie cloud (non pilotable). Amélioration partielle, bornée par le matériel.

## [2.0.7-beta5] — 2026-06-17

### Added

- **Équaliseur : répartition de décharge pour converger les SoC.** En **déficit**
  (maison > solaire), l'équaliseur steer désormais la **part de décharge** entre
  le parc pilotable et la batterie cloud, pondérée par l'écart de SoC : la
  batterie la **plus haute décharge davantage** → les SoC **convergent** (ex.
  stream 70 % / Jackery 30 % → le stream décharge beaucoup plus, la Jackery est
  épargnée). En déficit le **plafond PV est levé** (la décharge supplémentaire
  alimente la **maison**, pas la batterie cloud → pas de transfert lossy) ; en
  **surplus** le plafond PV reste (on ne redistribue que du solaire, beta.13).
- **Option `Équaliseur : répartition bidirectionnelle`** (défaut **désactivé**) :
  - **désactivé (unidirectionnel)** : on ne fait que **décharger plus** le parc
    quand il est au-dessus de la batterie cloud (épargne la plus basse, **aucun
    import provoqué**) ;
  - **activé (bidirectionnel)** : on **réduit aussi** la décharge du parc quand il
    est en dessous (la batterie cloud porte plus) → convergence complète, **peut
    importer brièvement** le temps que la batterie cloud réagisse.

## [2.0.7-beta4] — 2026-06-17

### Fixed

- **Plus de transfert « batterie cloud → stream » en déficit.** En déficit (maison
  > solaire), le stream **chargeait son propre solaire** au lieu de le sortir, et
  > la Jackery (non pilotable) **sur-déchargeait** pour couvrir maison + charge du
  > stream → aller-retour batterie→batterie avec pertes. Nouveau garde-fou
  > d'autoconsommation : le parc pilotable **ne charge pas sans vrai surplus** — sa
  > sortie est plancher-née à sa **propre production solaire** (output ≥ PV, batterie
  > jamais en charge depuis le réseau / une autre batterie). → le stream sort tout
  > son solaire pour la maison, la Jackery ne décharge plus que le **vrai déficit**.

### Notes

- **Exceptions au plancher** (la charge reste permise) : quand le **réseau exporte**
  (vrai surplus à stocker) **ou** quand l'**équaliseur veut charger** le parc
  (offre négative : batterie cloud au-dessus de la moyenne → équilibrage SoC). La
  nuit (PV = 0) le plancher = pas de charge réseau, conforme à l'autoconso.

## [2.0.7-beta3] — 2026-06-17

### Fixed

- **Grosses consos en journée : le parc décharge enfin sa batterie pour couvrir
  l'import.** La ZI suivait la **puissance batterie (cellules)**, alors que sur un
  onduleur **« solaire d'abord »** (EcoFlow STREAM) la consigne de décharge = la
  **sortie AC**. Quand le solaire couvrait à lui seul la consigne, la batterie
  restait à 0 et la ZI, croyant le parc à contribution nulle, ne **poussait jamais
  la sortie au-dessus du solaire** → on importait du réseau alors que la batterie
  (ex. 59 %) pouvait aider. La base de la ZI est désormais la **contribution AC du
  parc** `Σ(puissance_batterie) − Σ(puissance_MPPT)` (= −sortie AC). **La nuit
  (PV = 0) c'est identique → l'anti-yoyo de la beta2 est préservé.**
- **Équaliseur suspendu en déficit** — quand le réseau **importe** (au-delà de
  l'hystérésis), l'offre est mise à 0 : il n'y a pas de surplus à redistribuer, et
  pousser le solaire vers la batterie cloud pendant qu'elle se décharge pour la
  maison était contre-productif. L'équaliseur ne redistribue plus que du **vrai
  surplus**.

### Known limitation

- Si la **sortie AC requise** dépasse la puissance de décharge max de la batterie,
  le plafond batterie peut limiter un peu la couverture (le solaire compte dans la
  sortie). Cas extrême, sans impact courant.

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

- **README** : suppression de la section _Companion frontend_ ; lien HACS corrigé
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
  −780 W). Deux nouveaux réglages dans _Configurer → Régulation_.

### Removed

- **Auto-réglage supervisé (autotuner) retiré** — il rabaissait _tout_ le gain
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
  - correction` et l'EcoFlow rampe lentement). Elle ne fait que **réduire une
    décharge** (jamais forcer une charge) → le **surplus PV continue d'exporter**
    et, en import, la décharge couvre normalement la maison. **Laissée désactivée**,
    l'injection reste possible (ex. pour forcer la charge d'une batterie cloud).

## [2.0.2] — 2026-06-16

### Fixed

- **Garde-fou « batterie non-pilotable » : plafonnage sur le réseau _naturel_**
  (correctif de la 2.0.1). Le garde-fou était plafonné par l'import réseau _brut_
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
  _« Ne pas décharger le parc pour alimenter une batterie non-pilotable (cloud)
  qui se recharge seule »_ dans _Configurer → Régulation_.

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
  `soc_equaliser_probe_step_w`) à définir dans _Configurer → Régulation_. Débouncée,
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
  _Régulation_ : `weather_phenomena` (multi-sélection : quels phénomènes
  déclenchent le mode Tempête — ex. exclure _Canicule_) et `weather_min_level`
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
  _« expected int … soc_min_pct »_. Le `NumberSelector` de HA renvoie des floats
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
  cause exacte : _capteur de puissance manquant_ (renseigner Puissance signée OU
  Charge + Décharge), _pilotage actif sans consigne_, ou _pilotage actif sans
  batterie pilotable_. (FR/EN, types Batterie et Batterie + onduleur.)

## [2.0.0-beta.2] — 2026-06-16

> Vague 4 (étape 1, **pré-release**) — capteurs d'énergie, mapping 2 capteurs en
> UI, allègement du panneau.

### Added

- **Capteur `sensor.solarbalance_battery_usable`** — fenêtre d'énergie exploitable
  du parc (kWh) = Σ (SoC_max − SoC_min) × capacité utilisable effective.
- **Couple de capteurs charge/décharge dans l'UI** — le formulaire _Batterie_ (et
  _Batterie + onduleur_) expose désormais `charge_power_entity` /
  `discharge_power_entity` en alternative au `power_entity` signé, pour les
  batteries à deux capteurs de puissance distincts. (Déjà géré en YAML ; manquait
  dans le Config Flow.)

### Changed

- **`sensor.solarbalance_battery_energy_available` renommé en
  `sensor.solarbalance_battery_remaining`** (même valeur : énergie stockée). Les
  capteurs d'énergie utilisent désormais la capacité utilisable **effective**
  (ratio chimie si non explicite) — sans effet sur le SoC moyen (le ratio
  s'annule), mais plus juste en kWh.
- **Panneau** : capteurs _Restant_ et _Exploitable_ ajoutés à la carte « Flux
  instantané » ; sections _Historique (N derniers jours)_, _Coûts & économies
  (€/jour)_ et _Plan prédictif (advisory)_ retirées de la vue.

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
  dérivée du retard mesuré) exposés dans _Configurer → Régulation_.

### Fixed

- **SoC moyen pondéré par capacité** — `sensor.solarbalance_battery_soc_avg` faisait
  une moyenne **arithmétique** des pourcentages : une batterie 2 kWh à 75 % + une
  3,96 kWh à 25 % donnaient 50 % au lieu du SoC énergie-vrai (~42 %). Désormais
  pondéré par capacité utilisable, tout comme le SoC agrégé fourni au **planner
  prédictif** (qui modélise le parc comme une batterie unique). Le déficit du
  délestage de fin de journée était déjà correct (calcul par batterie en kWh).

### Changed

- **Équaliseur SoC indirect réécrit (anti-pompage)** — sur batterie automatique
  _cloud_ (ex. Jackery), l'ancien équaliseur partait en **cycle limite** : l'offre
  (intégrateur) montait en rampe jusqu'à son plafond puis s'effondrait, fouettant
  le parc pilotable entre charge et décharge pleines et projetant des pics réseau
  de ±1,3 à 2,7 kW (injection visible) toutes les ~5 min, pour un SoC qui ne
  convergeait pas. La nouvelle version :
  - **offre proportionnelle à l'écart de SoC** (plus d'intégrateur → plus de
    windup) ;
  - **cadence lente** : l'offre ne bouge que toutes les _N_ ticks, _N_ étant
    **dérivé du retard de réponse mesuré** de la batterie cloud
    (`soc_equaliser_adaptive_cadence`, défaut on ; plancher
    `soc_equaliser_cadence_ticks`, défaut 6) ;
  - **anti-windup conscient du temps mort** : un export/import n'est rétracté que
    s'il **persiste** _et_ que la puissance mesurée de la batterie auto **ne
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

- **Mode simulation (dry-run)** — option _Régulation_ `dry_run` : le moteur calcule tout (décisions, consignes, capteurs, panneau) mais **n'écrit jamais** sur le matériel, même contrôle actif/loads armés. Idéal pour observer une journée entière en confiance avant d'activer le pilotage réel. Exposé aussi dans l'export de diagnostic.
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

- **Charge forcée réseau — feed-forward sur la puissance mesurée** — l'offset zéro-injection utilisait la puissance _nominale_ du consommateur (calculée avant qu'il ne consomme), ce qui pouvait faire **charger la batterie depuis le réseau** au démarrage (la nuit) ou quand la charge réelle était inférieure au nominal. Il suit désormais la puissance **mesurée** du consommateur forcé (plafonnée au nominal) : la batterie n'est ni déchargée pour l'alimenter, ni chargée depuis le réseau pour « atteindre » la consigne. La batterie continue de couvrir le reste de la maison. Vérifié par un test de tick complet de bout en bout.

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

[2.0.8-beta24]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta23...v2.0.8-beta24
[2.0.8-beta23]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta22...v2.0.8-beta23
[2.0.8-beta22]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta21...v2.0.8-beta22
[2.0.8-beta21]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta20...v2.0.8-beta21
[2.0.8-beta20]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta19...v2.0.8-beta20
[2.0.8-beta19]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta18...v2.0.8-beta19
[2.0.8-beta18]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta17...v2.0.8-beta18
[2.0.8-beta17]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta16...v2.0.8-beta17
[2.0.8-beta16]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta15...v2.0.8-beta16
[2.0.8-beta15]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta14...v2.0.8-beta15
[2.0.8-beta14]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta13...v2.0.8-beta14
[2.0.8-beta13]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta12...v2.0.8-beta13
[2.0.8-beta12]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta11...v2.0.8-beta12
[2.0.8-beta11]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta10...v2.0.8-beta11
[2.0.8-beta10]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta9...v2.0.8-beta10
[2.0.8-beta9]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta8...v2.0.8-beta9
[2.0.8-beta8]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta7...v2.0.8-beta8
[2.0.8-beta7]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta6...v2.0.8-beta7
[2.0.8-beta6]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta5...v2.0.8-beta6
[2.0.8-beta5]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta4...v2.0.8-beta5
[2.0.8-beta4]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta3...v2.0.8-beta4
[2.0.8-beta3]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta2...v2.0.8-beta3
[2.0.8-beta2]: https://github.com/lachand/ha-solarbalance/compare/v2.0.8-beta1...v2.0.8-beta2
[2.0.8-beta1]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7...v2.0.8-beta1
[2.0.7]: https://github.com/lachand/ha-solarbalance/compare/v2.0.6...v2.0.7
[2.0.7-beta29]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta28...v2.0.7-beta29
[2.0.7-beta28]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta27...v2.0.7-beta28
[2.0.7-beta27]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta26...v2.0.7-beta27
[2.0.7-beta26]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta25...v2.0.7-beta26
[2.0.7-beta25]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta24...v2.0.7-beta25
[2.0.7-beta24]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta23...v2.0.7-beta24
[2.0.7-beta23]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta22...v2.0.7-beta23
[2.0.7-beta22]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta21...v2.0.7-beta22
[2.0.7-beta21]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta20...v2.0.7-beta21
[2.0.7-beta20]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta19...v2.0.7-beta20
[2.0.7-beta19]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta18...v2.0.7-beta19
[2.0.7-beta18]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta17...v2.0.7-beta18
[2.0.7-beta17]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta16...v2.0.7-beta17
[2.0.7-beta16]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta15...v2.0.7-beta16
[2.0.7-beta15]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta14...v2.0.7-beta15
[2.0.7-beta14]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta13...v2.0.7-beta14
[2.0.7-beta13]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta12...v2.0.7-beta13
[2.0.7-beta12]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta11...v2.0.7-beta12
[2.0.7-beta11]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta10...v2.0.7-beta11
[2.0.7-beta10]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta9...v2.0.7-beta10
[2.0.7-beta9]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta8...v2.0.7-beta9
[2.0.7-beta8]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta7...v2.0.7-beta8
[2.0.7-beta7]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta6...v2.0.7-beta7
[2.0.7-beta6]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta5...v2.0.7-beta6
[2.0.7-beta5]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta4...v2.0.7-beta5
[2.0.7-beta4]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta3...v2.0.7-beta4
[2.0.7-beta3]: https://github.com/lachand/ha-solarbalance/compare/v2.0.7-beta2...v2.0.7-beta3
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
