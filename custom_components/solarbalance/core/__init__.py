"""HA-agnostic core engine of SolarBalance.

This package must remain importable without Home Assistant. CI enforces
this via `scripts/check_core_purity.py`. All HA coupling lives in
`custom_components.solarbalance.adapters`.
"""
