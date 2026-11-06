"""Generate ``tokens.scoped.css`` from the vendored Signature tokens.

``:root`` never matches inside a shadow root, and the panel and card render in
shadow DOM. The vendored ``tokens.css`` must stay byte-identical to the upstream
copy, so the scoped variant is derived from it by this script, never edited by hand.

Usage:
    python scripts/scope_signature.py
"""

from __future__ import annotations

from pathlib import Path

VENDOR = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "solarbalance"
    / "www"
    / "vendor"
    / "signature"
)

REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (':root, [data-theme="light"] {', ':host, .sg-scope, .sg-scope[data-theme="light"] {'),
    ('[data-theme="dark"] {', '.sg-scope[data-theme="dark"] {'),
    ('[data-theme="contrast"] {', '.sg-scope[data-theme="contrast"] {'),
    (":root {", ":host, .sg-scope {"),
)

HEADER = "/* Généré par scripts/scope_signature.py depuis tokens.css : ne pas éditer. */\n"


def scope(css: str) -> str:
    """Return ``css`` with its global selectors rewritten for a shadow root."""
    out = css
    for old, new in REPLACEMENTS:
        if old not in out:
            raise ValueError(f"selector not found in tokens.css: {old!r}")
        out = out.replace(old, new)
    return HEADER + out


def main() -> None:
    """Write ``tokens.scoped.css`` next to ``tokens.css``."""
    source = (VENDOR / "tokens.css").read_text(encoding="utf-8")
    (VENDOR / "tokens.scoped.css").write_text(scope(source), encoding="utf-8")


if __name__ == "__main__":
    main()
