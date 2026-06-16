"""Fixtures for HA-aware integration tests.

These tests use `pytest-homeassistant-custom-component`. They are slower
than core unit tests; keep them focused on adapter and platform behaviour,
not on algorithmic correctness (which belongs in `tests/core/`).
"""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading of the custom integration in HA test environments."""
    yield
