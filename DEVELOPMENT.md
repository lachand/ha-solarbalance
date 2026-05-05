# Quick Start for Developers

## Prerequisites

- **Python 3.13+** (aligned with HA 2026.1+)
- **Git** and **Make** (or run commands manually)

## Setup

```bash
# Clone the repository
git clone https://github.com/solarbalance/ha-solarbalance.git
cd ha-solarbalance

# Automated setup (creates venv, installs deps, installs pre-commit)
bash scripts/setup.sh

# Activate the venv
source .venv/bin/activate
```

## Development workflow

```bash
# Run all checks before committing
make check

# Format code
make format

# Run tests
make test          # all tests
make test-core     # core tests only (fast)

# Type check the core
make typecheck
```

## VS Code

Open the folder in VS Code. Recommended extensions will be suggested automatically.

- **Python extension**: debugging and testing via UI
- **Ruff extension**: format-on-save configured in `.vscode/settings.json`
- **Claude Code extension**: for AI-assisted development

### Debugging

Use the pre-configured launch configurations in `.vscode/launch.json`:

- "Python: Pytest (current file)" — debug the test file currently open
- "Python: Pytest (all core tests)" — debug the full core test suite

## Structure

See [AGENTS.md](AGENTS.md) for code organization conventions, especially:

- `custom_components/solarbalance/core/` must **not** import from `homeassistant.*`
- Strategies produce `Decision` dataclasses, never write to HA entities directly
- The adapter layer (`adapters/`) is the **only** bridge between HA and core

## Running in Home Assistant

### Option 1: Symlink to your HA config

```bash
ln -s $(pwd)/custom_components/solarbalance ~/.homeassistant/custom_components/solarbalance
```

Then restart Home Assistant.

### Option 2: Docker dev container

A `devcontainer.json` will land in v0.2 for one-click HA test environments.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Commit message conventions (Conventional Commits)
- PR workflow
- Code review expectations

## Getting help

- **Issues**: https://github.com/solarbalance/ha-solarbalance/issues
- **Discussions**: https://github.com/solarbalance/ha-solarbalance/discussions
- **Documentation**: [docs/](docs/)
