.PHONY: help install test lint format typecheck clean dev

help:
	@echo "SolarBalance development commands:"
	@echo "  make install    - Install dev dependencies"
	@echo "  make test       - Run all tests"
	@echo "  make test-core  - Run core tests only (fast)"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Format code with ruff"
	@echo "  make typecheck  - Run mypy on core/"
	@echo "  make check      - Run lint + typecheck + test"
	@echo "  make clean      - Remove caches and build artifacts"
	@echo "  make dev        - Install in editable mode"

install:
	python -m pip install --upgrade pip
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest tests/ -v

test-core:
	pytest tests/core/ -v --cov=custom_components/solarbalance/core

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy custom_components/solarbalance/core/

check: lint typecheck test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/

dev: install
	@echo "✓ Development environment ready"
	@echo "Run 'make test' to verify installation"
