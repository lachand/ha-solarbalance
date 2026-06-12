# SolarBalance — Documentation Développeur

> Pour contribuer au projet : lire aussi [CONTRIBUTING.md](../CONTRIBUTING.md) et [AGENTS.md](../AGENTS.md).

---

## Table des matières

1. [Prérequis et installation](#1-prérequis-et-installation)
2. [Structure du dépôt](#2-structure-du-dépôt)
3. [Conventions de code](#3-conventions-de-code)
4. [Ajouter une stratégie](#4-ajouter-une-stratégie)
5. [Ajouter un adaptateur](#5-ajouter-un-adaptateur)
6. [Tests](#6-tests)
7. [CI/CD](#7-cicd)
8. [Frontend (solarbalance-card)](#8-frontend-solarbalance-card)
9. [Conventions Git](#9-conventions-git)

---

## 1. Prérequis et installation

### Versions requises

| Outil | Version minimale |
|---|---|
| Python | **3.13** |
| Home Assistant (test) | **2026.1** |
| Node.js (frontend) | **20** |

### Mise en place locale

```bash
git clone https://github.com/lachand/ha-solarbalance.git
cd ha-solarbalance

# Environnement Python
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Hooks pre-commit
pre-commit install

# Frontend (optionnel)
cd frontend/solarbalance-card
npm install
```

Le `Makefile` expose les cibles courantes :

```bash
make test        # pytest tests/core/ -q
make lint        # ruff check + mypy
make format      # ruff format
make test-all    # pytest tests/ (core + integration)
```

---

## 2. Structure du dépôt

```
ha-solarbalance/
│
├─ custom_components/solarbalance/
│   ├─ __init__.py           # async_setup, async_setup_entry, services
│   ├─ config_flow.py        # UI Config Flow + Options Flow
│   ├─ coordinator.py        # DataUpdateCoordinator — boucle principale
│   ├─ sensor.py             # Entités sensor
│   ├─ binary_sensor.py      # Entités binary_sensor
│   ├─ select.py             # select.solarbalance_hems_mode
│   ├─ number.py             # number.solarbalance_zi_*
│   ├─ switch.py             # switch.solarbalance_zero_injection
│   ├─ const.py              # Constantes et clés de config
│   ├─ yaml_loader.py        # Parser voluptuous du bloc YAML
│   │
│   ├─ core/                 # ★ PUR PYTHON — zéro import homeassistant ★
│   │   ├─ models.py         # Dataclasses (Device, Snapshot, Decision, …)
│   │   ├─ arbitrer.py       # Fusion N décisions → 1 décision
│   │   ├─ tariff.py         # Modèles de tarifs (HC/HP, Tempo, EPEX)
│   │   ├─ planner.py        # Planificateur prédictif DP 24h
│   │   ├─ active_control.py # Modèles de contrôle actif (v2)
│   │   ├─ controllers/
│   │   │   ├─ balancing.py      # Répartition hybride multi-batteries
│   │   │   ├─ zero_injection.py # PI zéro-injection mono/tri-phase
│   │   │   └─ load_dispatch.py  # Dispatch des charges pilotables
│   │   └─ strategies/
│   │       ├─ base.py           # Classe abstraite Strategy
│   │       ├─ self_consumption.py
│   │       ├─ cost_min.py
│   │       ├─ backup.py
│   │       ├─ longevity.py
│   │       ├─ peak_shaving.py
│   │       └─ revenue_max.py
│   │
│   ├─ adapters/             # Bridge HA ↔ core
│   │   ├─ entity_reader.py  # Lecture entités + normalisation → Snapshot
│   │   ├─ decision_publisher.py # Cache + exposition des setpoints
│   │   ├─ forecast.py       # Lecture PV forecast + météo HA
│   │   └─ watchdog.py       # Détection entités stales
│   │
│   ├─ translations/
│   │   ├─ fr.json
│   │   └─ en.json
│   └─ www/
│       └─ solarbalance-card.js  # Bundle Lovelace (pre-compilé)
│
├─ frontend/solarbalance-card/
│   ├─ src/solarbalance-card.ts  # Composant Lit custom element
│   ├─ vite.config.ts
│   └─ package.json
│
├─ tests/
│   ├─ core/                 # Pytest pur (sans HA)
│   └─ integration/          # pytest-homeassistant-custom-component
│
├─ docs/
│   ├─ SPECIFICATIONS.md     # Spécifications fonctionnelles (référence)
│   ├─ technical.md          # Ce document
│   ├─ developer.md          # ← vous êtes ici
│   └─ user-guide.md         # Guide utilisateur
│
├─ scripts/
│   ├─ check_core_purity.py  # Vérifie qu'aucun import HA n'entre dans core/
│   └─ setup.sh
└─ pyproject.toml            # Config ruff, mypy, pytest, coverage
```

### Règle de layering — critique

```
core/   →  ne peut importer QUE stdlib + autres modules core/
adapters/ →  peut importer core/ + homeassistant.*
platforms/ →  peut importer adapters/ + core/ + homeassistant.*
```

Le script `scripts/check_core_purity.py` vérifie cela à chaque commit (hook pre-commit). Toute violation fait échouer la CI.

---

## 3. Conventions de code

### Typing

- **`mypy --strict`** est obligatoire sur `core/`. Adapters et plateformes : mypy standard.
- Les annotations sont **obligatoires** sur toutes les fonctions et méthodes publiques.
- Cible **Python 3.13** : pas de syntaxe 3.14-only (toujours parenthéser les `except (A, B):` — PEP 758 casse en 3.13). Pour les forward references évaluées au runtime, ajoutez `from __future__ import annotations` si besoin.

```python
from __future__ import annotations  # si une annotation référence un type défini plus bas

def compute(self, snapshot: Snapshot) -> Decision: ...
```

### Linting & formatage

**Ruff** est l'unique outil de lint et format (config dans `pyproject.toml`).

```bash
ruff check custom_components/   # lint
ruff format custom_components/  # format in-place
```

Règles notables activées :
- `RUF009` : pas de valeurs mutables par défaut dans les dataclasses `frozen=True` → utiliser `field(default_factory=...)`
- `RUF003` : pas de caractères Unicode `×` ou `–` dans les commentaires → utiliser `x` et `-`

### Logging

```python
_LOGGER = logging.getLogger(__name__)

_LOGGER.debug("tick: snapshot=%s", snapshot)    # niveau tick
_LOGGER.info("mode changed: %s → %s", old, new) # transitions d'état
_LOGGER.warning("entity stale: %s", entity_id)  # problème récupérable
_LOGGER.error("YAML parse error: %s", exc)       # échec
```

### Docstrings

- `core/` : Google style obligatoire sur les APIs publiques.
- Plateformes HA : convention HA (une ligne pour les entités simples).
- **Interdits** : commentaires qui répètent le code (`# Check if initialized` au-dessus de `if self.initialized:`). Les commentaires expliquent le **pourquoi**, pas le quoi.

---

## 4. Ajouter une stratégie

### Étape 1 — Créer le fichier

```python
# custom_components/solarbalance/core/strategies/my_strategy.py
from ..models import Decision, Snapshot, StrategyKind
from .base import Strategy


class MyStrategy(Strategy):
    """Description en une ligne.

    Args:
        devices: Injected by base class from coordinator config.
        my_param: Description du paramètre.
    """

    kind = StrategyKind.MY_STRATEGY.value  # à ajouter à l'enum

    def __init__(self, *args: object, my_param: float = 42.0, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._my_param = my_param

    def compute(self, snapshot: Snapshot) -> Decision:
        # Logique pure, sans état persistant, sans IO
        return Decision(rationale=f"my_strategy: param={self._my_param}")
```

### Étape 2 — Enregistrer dans l'enum

Dans `core/models.py` :

```python
class StrategyKind(StrEnum):
    ...
    MY_STRATEGY = "my_strategy"  # ← ajouter
```

### Étape 3 — Instancier dans le coordinateur

Dans `coordinator.py`, dans `_build_strategies()` :

```python
case StrategyKind.MY_STRATEGY:
    strategies.append(MyStrategy(devices=self._devices, my_param=...))
```

### Étape 4 — Exposer dans le Config Flow

Dans `config_flow.py`, ajouter l'option dans la liste `CONF_PRIORITIES` et dans les traductions `fr.json` / `en.json`.

### Étape 5 — Tester

```python
# tests/core/strategies/test_my_strategy.py
from custom_components.solarbalance.core.strategies.my_strategy import MyStrategy

def test_my_strategy_basic(snapshot: Snapshot) -> None:
    strategy = MyStrategy(devices=[...])
    decision = strategy.compute(snapshot)
    assert decision.confidence == 1.0
    # assertions sur battery_targets, grid_constraint, etc.
```

---

## 5. Ajouter un adaptateur

Les adaptateurs vivent dans `adapters/` et peuvent importer `homeassistant.*`.

```python
# custom_components/solarbalance/adapters/my_adapter.py
import logging
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class MyAdapter:
    """Bridge entre une source HA externe et le core."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    def read_value(self) -> float | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in {"unavailable", "unknown", ""}:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            _LOGGER.debug("Entity %s: unparseable state %r", self._entity_id, state.state)
            return None
```

**Règles** :
- Retourner `None` ou une valeur par défaut sur entité absente/indisponible — ne jamais lever d'exception vers le coordinateur.
- Ne jamais écrire dans des entités d'équipement utilisateur en v1 (voir `AGENTS.md` §SolarBalance-specific rules).

---

## 6. Tests

### Organisation

```
tests/
├─ core/                        # Pytest pur, AUCUN import homeassistant
│   ├─ conftest.py              # Fixtures partagées (snapshots, devices, …)
│   ├─ test_arbitrer.py
│   ├─ test_models.py
│   ├─ controllers/
│   │   ├─ test_balancing.py
│   │   └─ test_zero_injection.py
│   └─ strategies/
│       └─ test_self_consumption.py
└─ integration/
    ├─ conftest.py              # hass fixture, MockConfigEntry
    └─ (tests nécessitant HA)
```

### Exécuter les tests

```bash
# Tests core seulement (rapides, ~0.5 s)
source .venv/bin/activate
python -m pytest tests/core/ -q

# Tests complets
python -m pytest tests/ -q

# Avec coverage
python -m pytest tests/core/ --cov=custom_components/solarbalance/core --cov-report=term-missing
```

### Règles de tests

**Annotations obligatoires sur les paramètres** :

```python
# ✓
def test_balancing_two_batteries(snapshot: Snapshot, devices: list[Device]) -> None: ...

# ✗
def test_balancing_two_batteries(snapshot, devices): ...
```

**Pas de branchement dans les tests** :

```python
# ✗ — if dans un test
def test_strategy(mode: str) -> None:
    if mode == "storm":
        ...

# ✓ — parametrize
@pytest.mark.parametrize("mode,expected", [
    ("storm", 95.0),
    ("normal", 30.0),
])
def test_strategy(mode: str, expected: float) -> None:
    ...
```

**Tests dupliqués** → fusionner avec `@pytest.mark.parametrize`.

### Objectifs de couverture

| Zone | Cible |
|---|---|
| `core/` | **> 80 %** |
| `adapters/` | > 60 % |
| Plateformes HA | > 40 % |

### Fixtures disponibles (`tests/core/conftest.py`)

```python
@pytest.fixture
def minimal_snapshot() -> Snapshot: ...      # Snapshot mono-batterie minimal

@pytest.fixture
def two_battery_devices() -> list[Device]: . # LiFePO4 3.6 kWh + 2 kWh

@pytest.fixture
def balancing_ctrl() -> BalancingController: # alpha=0.6, min_dwell_s=0
```

---

## 7. CI/CD

### Workflows GitHub Actions

| Workflow | Déclencheur | Actions |
|---|---|---|
| `ci.yml` | push / PR sur `main` | ruff lint, mypy, pytest core, pytest integration |
| `build-frontend.yml` | push `main` si `frontend/` modifié | `npm run build` → commit bundle → push |
| `release.yml` | création d'un release tag `v*` | build frontend, upload `solarbalance-card.js` comme release asset |

### Publier une release

1. Mettre à jour `CHANGELOG.md` (section `[Unreleased]` → `[x.y.z]`)
2. Bumper `version` dans `manifest.json`
3. Créer et pousser un tag `vx.y.z` :
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. Le workflow `release.yml` construit le frontend et crée la release GitHub.

---

## 8. Frontend (solarbalance-card)

### Stack

- **Lit 3** — custom elements
- **TypeScript**
- **Vite 5** — bundler, output ESM

### Build

```bash
cd frontend/solarbalance-card
npm run build
# → custom_components/solarbalance/www/solarbalance-card.js
```

Le bundle est **commité dans le dépôt** afin d'être distribué par HACS sans nécessiter de build côté utilisateur.

### Structure de la carte

```typescript
// src/solarbalance-card.ts
@customElement("solarbalance-card")
class SolarBalanceCard extends LitElement {
    @property() hass!: HomeAssistant;
    @state() private _config!: CardConfig;

    setConfig(config: CardConfig): void { ... }
    render(): TemplateResult { ... }  // SVG Sankey + mode badge + SoC bar
}

// Auto-déclaration pour le picker Lovelace
window.customCards.push({ type: "solarbalance-card", name: "SolarBalance Card", ... });
```

### Personnaliser la carte

La carte lit les entités SolarBalance via `hass.states`. Pour ajouter un élément visuel :

1. Modifier `src/solarbalance-card.ts`
2. `npm run build`
3. Commiter `www/solarbalance-card.js`

### Enregistrement côté HA

Dans `__init__.py`, `_register_card_frontend()` :
1. Enregistre `www/` comme chemin statique HTTP → `/solarbalance_card/...`
2. Appelle `frontend.add_extra_js_url(hass, "/solarbalance_card/solarbalance-card.js")` → le module est chargé automatiquement dans le frontend HA

---

## 9. Conventions Git

### Format de commit (Conventional Commits)

```
<type>(<scope>): <description courte>

[corps optionnel]

[footer optionnel: Fixes #123]
```

**Types** : `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

**Scopes** : `core`, `adapter`, `frontend`, `ci`, `config`, `tests`

**Exemples** :
```
feat(core): add hybrid balancing controller with anti-short-cycle guard
fix(adapter): handle missing soc entity gracefully
test(core): add parametrized tests for arbitrer edge cases
docs: add developer guide
```

### Politique de branches

- `main` : branche stable, toujours verte en CI.
- Feature branches : `feat/nom-fonctionnalite`
- Fix branches : `fix/description-courte`

### Règles PR

- **Ne pas amender, squasher ni rebaser** des commits déjà poussés sur une branche de PR ouverte.
- Un commit = un changement logique.
- Ne pas mélanger des refactorings et des corrections de bug dans le même commit.
- Référencer l'issue ou la section de `SPECIFICATIONS.md` dans le corps du commit pour tout changement algorithmique.
