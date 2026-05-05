#!/usr/bin/env bash
set -euo pipefail

echo "🔧 Setting up SolarBalance development environment..."

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.13"

if [[ "$PYTHON_VERSION" < "$REQUIRED_VERSION" ]]; then
    echo "❌ Python $REQUIRED_VERSION or higher required (found $PYTHON_VERSION)"
    exit 1
fi

# Create venv if missing
if [[ ! -d ".venv" ]]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip

# Install package in editable mode with dev deps
echo "📥 Installing dependencies..."
pip install -e ".[dev]"

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Verify installation
echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the environment: source .venv/bin/activate"
echo "To run tests: make test"
echo "To format code: make format"
echo "To check code: make check"
