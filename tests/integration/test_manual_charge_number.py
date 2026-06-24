"""Tests for the manual charge-power number (forces a grid charge/discharge)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.solarbalance.number import ManualChargePowerNumber


def _entity() -> tuple[ManualChargePowerNumber, MagicMock]:
    coordinator = MagicMock()
    coordinator._battery_override = None
    entry = MagicMock()
    entry.entry_id = "e1"
    num = ManualChargePowerNumber(coordinator, entry)
    num.async_write_ha_state = MagicMock()
    return num, coordinator


async def test_positive_value_forces_charge() -> None:
    num, coord = _entity()
    await num.async_set_native_value(600.0)
    coord.set_force_override.assert_called_once_with(
        kind="charge", target_soc_pct=100.0, power_w=600.0
    )
    coord.clear_force_override.assert_not_called()


async def test_negative_value_forces_discharge() -> None:
    num, coord = _entity()
    await num.async_set_native_value(-400.0)
    coord.set_force_override.assert_called_once_with(
        kind="discharge", target_soc_pct=0.0, power_w=400.0
    )


async def test_zero_clears_override() -> None:
    num, coord = _entity()
    await num.async_set_native_value(0.0)
    coord.clear_force_override.assert_called_once()
    coord.set_force_override.assert_not_called()


def test_native_value_reflects_override() -> None:
    num, coord = _entity()
    assert num.native_value == 0.0
    coord._battery_override = SimpleNamespace(kind="charge", power_w=600.0)
    assert num.native_value == 600.0
    coord._battery_override = SimpleNamespace(kind="discharge", power_w=400.0)
    assert num.native_value == -400.0
