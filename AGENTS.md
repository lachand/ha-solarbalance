# Agent Instructions for SolarBalance

This repository hosts **SolarBalance**, a Home Assistant custom component for home energy management (HEMS). It targets **Home Assistant 2026.1+** and **Python 3.14+**, aligned with HA core requirements.

These instructions apply to GitHub Copilot, Claude Code, and any other AI assistant contributing to this repository.

## Project structure conventions

- `custom_components/solarbalance/core/` — pure Python, **must not import from `homeassistant.*`**. This isolation enables fast unit tests, future extraction as a standalone library, and offline simulation.
- `custom_components/solarbalance/adapters/` — bridge between HA APIs and the core (entity reading, decision publishing, forecast wrappers).
- `custom_components/solarbalance/` (top level) — HA platform implementations (sensors, selects, numbers, switches, config flow, coordinator).
- `tests/core/` — pure pytest, no `pytest-homeassistant-custom-component`.
- `tests/integration/` — HA-aware tests using `pytest-homeassistant-custom-component`.

When proposing code, **respect this layering**. A change to `core/` that imports HA APIs must instead live in `adapters/` or be refactored to pass HA-derived data through dataclasses.

## Python syntax and language features

- Python 3.14 is the **minimum supported version**. Do not flag syntax or features requiring 3.14 as issues, and do not suggest workarounds for older Python versions.
- Python 3.14 explicitly allows `except TypeA, TypeB:` without parentheses. Never flag this as an issue.
- Python 3.14 evaluates annotations lazily (PEP 649). Forward references in annotations do **not** need to be quoted, and `from __future__ import annotations` is **not** required. Do not flag unquoted forward references as issues.
- Type annotations are **mandatory** on all public functions and methods, and on test parameters.

## Code quality

- **Strict typing on `core/`** — `mypy --strict` must pass on the core module. Adapters and HA platform code follow standard `mypy` strictness.
- **Ruff** is the single source of truth for linting and formatting. Configuration lives in `pyproject.toml`. Do not introduce additional linters.
- **Docstrings** in Google style on public APIs of `core/`. HA platform classes follow HA docstring conventions.
- **Logging**: use `_LOGGER = logging.getLogger(__name__)` per module. Use the appropriate level (`debug` for tick-level events, `info` for state transitions, `warning` for recoverable issues, `error` for failures).

## Testing

- All test function parameters must have **type annotations**. Prefer concrete types (`HomeAssistant`, `MockConfigEntry`, `Snapshot`, `Decision`) over `Any`.
- **Avoid branching inside tests.** If a test would need an `if`, either split it into multiple tests or use `pytest.mark.parametrize` to cover the cases.
- If multiple tests share most of their code, **use `pytest.mark.parametrize`** to merge them into a single parameterized test instead of duplicating the body.
- **Core tests must run without HA**. Any test under `tests/core/` that depends on HA must move to `tests/integration/`.
- Aim for **>80% coverage on `core/`**. Adapters and platforms target 60%+ as full integration testing is slower.

## Good practices

- Do not add **defensive checks for input fields already validated by Home Assistant's service/entity schemas**. Suggest extra guards only when data bypasses those validators or is transformed into a less-safe form.
- When validation guarantees a dict key exists, **prefer direct key access** (`data["key"]`) over `.get("key")` so contract violations surface instead of being silently masked.
- Do **not** add comments that restate the code on the following line(s) (e.g. `# Check if initialized` above `if self.initialized:`). Comments should explain **why** — non-obvious constraints, surprising behavior, workarounds — never **what**.
- Look for inspiration in **HA Platinum/Gold** integrations (level indicated in their `manifest.json`).

## SolarBalance-specific rules

### Hardware and entity assumptions

- The codebase is **vendor-agnostic**. Never hardcode references to Ecoflow, Jackery, Victron or any specific brand in `core/`. Vendor-specific hints belong only to documentation and (later, v1.5+) to optional pre-filled mapping profiles in `adapters/profiles/`.
- The base **power sign convention** internally is always `charge_positive` (positive = battery charging, negative = discharging). Adapters normalize external entity values to this convention based on user-declared `power_sign_convention`.
- The `pdl` meter convention is **positive = soutirage / grid import**, negative = injection / export. Document this in user-facing strings, never the inverse.

### Decision flow

- All algorithmic decisions are produced by `core/strategies/` and combined by `core/arbitrer.py`. Strategies must produce a `Decision` dataclass — never write directly to HA entities.
- The `DecisionPublisher` adapter is the **only** component that converts `Decision` instances into observability sensor states. Do not bypass it.
- The component **always** publishes computed setpoints as its own sensor entities for observability, regardless of active control.
- **Active control (v2):** writing setpoints to user-mapped equipment is allowed, but only through the `ActiveControlPublisher` adapter — the **single** component permitted to write to user equipment. It is gated by the global `active_control_enabled` option (default off) plus the per-device `active_control_enabled` flag. Do not add equipment writes anywhere else. (First step is discharge-only — see `docs/SPECIFICATIONS.md` §6.6.)

### Configuration

- The split is: **Config Flow (UI) for global parameters**, **YAML for device/load declarations**. Do not add device declaration to the Config Flow without explicit design discussion (it gets unwieldy fast for multi-device setups).
- All numeric defaults exposed in config must be documented in `docs/SPECIFICATIONS.md` and reflected in the corresponding `voluptuous` schema with `vol.Optional(..., default=...)`.

## Git workflow

- **Do not amend, squash, or rebase commits already pushed to a PR branch** after the PR is opened. Reviewers need the commit history to follow incremental changes.
- Conventional Commits format for commit messages: `feat(core): add hybrid balancing controller`, `fix(adapter): handle missing soc entity gracefully`.
- One logical change per commit. Avoid mixing unrelated fixes.

## When uncertain

- Ask in the PR description rather than guessing on architecture-level decisions.
- For algorithm changes, justify with a reference to `docs/SPECIFICATIONS.md` or open an issue first to amend the spec.
