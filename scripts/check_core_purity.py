#!/usr/bin/env python3
"""Verify that custom_components/solarbalance/core/ stays HA-agnostic.

The core engine must not depend on Home Assistant. This is checked at
commit time and in CI to prevent accidental coupling.
"""

import ast
import sys
from pathlib import Path

CORE_DIR = Path("custom_components/solarbalance/core")
FORBIDDEN_PREFIXES = ("homeassistant", "voluptuous")


def find_forbidden_imports(file_path: Path) -> list[tuple[int, str]]:
    """Return (line, module) for any forbidden import in the file."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(FORBIDDEN_PREFIXES):
                    findings.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(FORBIDDEN_PREFIXES):
                findings.append((node.lineno, module))

    return findings


def main() -> int:
    if not CORE_DIR.is_dir():
        print(f"error: {CORE_DIR} not found", file=sys.stderr)
        return 1

    violations: list[str] = []
    for py_file in CORE_DIR.rglob("*.py"):
        for line, module in find_forbidden_imports(py_file):
            violations.append(f"{py_file}:{line}: forbidden import {module!r}")

    if violations:
        print("Core purity check FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\ncore/ must remain HA-agnostic (see AGENTS.md). "
            "Move HA-coupled code to adapters/.",
            file=sys.stderr,
        )
        return 1

    print(f"Core purity check OK ({sum(1 for _ in CORE_DIR.rglob('*.py'))} files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
