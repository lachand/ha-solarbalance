# Contributing to SolarBalance

Thank you for your interest in SolarBalance. Please read this short guide before opening a PR.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.

## Quick start

```bash
git clone https://github.com/solarbalance/ha-solarbalance.git
cd ha-solarbalance
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Development workflow

1. Open an **issue** first for non-trivial changes — discussion saves rework.
2. Fork the repo, create a topic branch (`feat/storm-mode-hysteresis`, `fix/balancing-saturation`).
3. Write code following [`AGENTS.md`](AGENTS.md) — Python 3.13, ruff-clean, mypy-strict on `core/`.
4. Add or update tests. Coverage on `core/` should not regress.
5. Update `docs/` and `CHANGELOG.md` if behavior or API changes.
6. Run the full check before pushing:
   ```bash
   ruff check . && ruff format --check .
   mypy custom_components/solarbalance/core/
   python scripts/check_core_purity.py
   pytest --cov
   ```
7. Open a PR. Reference the issue. Once a reviewer engages, **do not amend or force-push** — add follow-up commits instead.

## Architectural rules

- `custom_components/solarbalance/core/` must not import from `homeassistant`. CI enforces this.
- HA → core translation lives in `adapters/`. Keep the boundary clean.
- New strategies inherit from `core.strategies.base.Strategy` and produce `Decision` objects only.
- See [SPECIFICATIONS.md](docs/SPECIFICATIONS.md) for the design source of truth.

## Adding device support

If you have an inverter or battery that doesn't fit existing examples:

1. Open a [device support issue](.github/ISSUE_TEMPLATE/device_support.yml).
2. Once accepted, contribute an example mapping to `examples/config/devices/<brand>-<model>.yaml`.
3. (Future) Profiles will be auto-suggested in the config flow — your example becomes the seed.

## Reporting security issues

Do NOT open public issues for security vulnerabilities. Email the maintainers privately (see SECURITY.md, coming soon).
