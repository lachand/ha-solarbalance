# Backlog & roadmap

Fonctionnalités planifiées, regroupées en **vagues** d'implémentation. L'ordre
suit les dépendances (ce qui débloque le reste d'abord), puis le risque (les
changements de la boucle de contrôle après l'outil de *replay* qui permet de
les valider), et enfin l'effort/matériel.

Légende effort : 🟢 faible · 🟡 moyen · 🔴 élevé.

---

## Vague 1 — Plomberie & intégration HA (débloque le reste) → v1.8.0

| Item | Effort | Notes |
|---|---|---|
| **Événements HA** (`solarbalance_mode_changed`, `shed`, `red_day`, `force_charge`…) | 🟢 | Socle des blueprints, notifications actionnables et logbook. À faire en premier. |
| **Entrées Logbook** pour les décisions importantes | 🟢 | S'appuie sur les événements. |
| **Notifications actionnables** (boutons « Charger maintenant » / « Annuler ») | 🟡 | Utilise les événements + services existants. |
| **Blueprints d'automatisation** (charge EV la nuit en HC, forcer avant jour rouge…) | 🟢 | Triviaux une fois les événements + services en place. |
| **i18n du panneau** (titres de cartes encore en FR codé en dur) | 🟡 | Indépendant ; bon échauffement. |

## Vague 2 — Délestage intelligent & protection réseau → v1.9.0

| Item | Effort | Notes |
|---|---|---|
| **Délestage en cascade multi-niveaux** par priorité (pas tout-ou-rien) | 🟡 | Généralise l'`evening_shed` actuel ; base des deux suivants. |
| **Limite de puissance souscrite *active*** — couper des charges avant la disjonction | 🟡 | Transforme l'alerte de surcharge en action ; s'appuie sur la cascade. |
| **Load-balancing maison (EV)** — limiter le courant EV sous le disjoncteur | 🟡 | Lié à la puissance souscrite ; pilote le courant du chargeur. |
| **Pompe piscine sur surplus** (+ mode « éco solaire strict » par consommateur) | 🟢 | Surtout un nouveau mode de load (surplus PV uniquement). |

## Vague 3 — Outils de confiance & UX de configuration → v1.10.0

| Item | Effort | Notes |
|---|---|---|
| **Mode replay / dry-run** — rejouer une journée du recorder sans écrire | 🟡 | **Sert à valider la Vague 4** sans risque sur le matériel. |
| **Test du mapping en direct** — vérifier que chaque entité répond | 🟡 | UX de config. |
| **Détection auto d'entités** — suggérer le mapping (EcoFlow/Shelly/Jackery) | 🔴 | Heuristiques par marque. |
| **Assistant de 1er setup guidé** (wizard) | 🔴 | S'appuie sur la détection auto. |

## Vague 4 — Intelligence prédictive & santé (risqué → validé par le replay) → v2.0.0

| Item | Effort | Notes |
|---|---|---|
| **Détection de chute PV temps réel** (passage nuageux) → réaction rapide | 🟡 | Améliore la réactivité de la régulation. |
| **Prévision de conso — profil statistique** depuis le recorder | 🟡 | Profil journalier typique ; remplace le seul talon nuit pour shed/charge. |
| **Prévision de conso — ML léger** | 🔴 | Étape suivante du profil statistique (modèle simple). |
| **Auto-réglage du PI zéro-injection** (ajuster `kp` si oscillations) | 🔴 | Touche la boucle de contrôle → à faire **après** le replay. |
| **Throttle selon la santé batterie (SoH)** | 🟡 | Bride la puissance charge/décharge quand le SoH se dégrade. |

## Vague 5 — Résilience matérielle → v2.1.0

| Item | Effort | Notes |
|---|---|---|
| **Mode coupure réseau (EPS)** — détecter la perte réseau, basculer en priorités essentielles, gérer la réserve | 🔴 | Dépendant du matériel ; difficile à tester sans banc ; gardé pour la fin. |

---

## Pourquoi cet ordre

1. **Les événements d'abord** : blueprints, notifications actionnables et logbook en dépendent — un petit socle débloque quatre fonctionnalités.
2. **Le délestage en cascade ensuite** : la limite de puissance souscrite active et le load-balancing EV sont des spécialisations de la même mécanique de priorités.
3. **Le replay/dry-run avant l'intelligence** : il permet de valider l'auto-tuning du PI et la prévision de conso sur des journées réelles **sans toucher au matériel** (cohérent avec l'approche *read-first* du projet).
4. **L'EPS en dernier** : le plus gros morceau, fortement dépendant du matériel et le plus dur à tester.
