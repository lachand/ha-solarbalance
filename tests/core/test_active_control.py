"""Tests for V2 active control models."""

import pytest

from custom_components.solarbalance.core.active_control import (
    ActiveControlCommand,
    ActiveControlResult,
    ControlMode,
    DeviceControlCapability,
)


class TestActiveControlCommand:
    def test_defaults(self) -> None:
        cmd = ActiveControlCommand(device_name="bat1", mode=ControlMode.CHARGE)
        assert cmd.power_w is None
        assert cmd.soc_target_pct is None
        assert cmd.priority == 50
        assert cmd.reason == ""

    def test_full_command(self) -> None:
        cmd = ActiveControlCommand(
            device_name="bat1",
            mode=ControlMode.DISCHARGE,
            power_w=2000.0,
            soc_target_pct=20.0,
            priority=80,
            reason="peak shaving",
        )
        assert cmd.power_w == pytest.approx(2000.0)
        assert cmd.soc_target_pct == pytest.approx(20.0)
        assert cmd.reason == "peak shaving"

    @pytest.mark.parametrize("mode", list(ControlMode))
    def test_all_modes_valid(self, mode: ControlMode) -> None:
        cmd = ActiveControlCommand(device_name="d", mode=mode)
        assert cmd.mode is mode


class TestActiveControlResult:
    def test_success(self) -> None:
        result = ActiveControlResult(
            device_name="bat1",
            success=True,
            entity_id="number.bat_charge_power",
            value_written=3000.0,
        )
        assert result.success
        assert result.error == ""

    def test_failure_captures_error(self) -> None:
        result = ActiveControlResult(
            device_name="bat1",
            success=False,
            entity_id="number.bat_charge_power",
            value_written=None,
            error="entity unavailable",
        )
        assert not result.success
        assert "unavailable" in result.error


class TestDeviceControlCapability:
    def test_supports_declared_mode(self) -> None:
        cap = DeviceControlCapability(
            device_name="bat1",
            supported_modes=frozenset({ControlMode.CHARGE, ControlMode.IDLE}),
        )
        assert cap.supports(ControlMode.CHARGE)
        assert cap.supports(ControlMode.IDLE)

    def test_does_not_support_undeclared_mode(self) -> None:
        cap = DeviceControlCapability(
            device_name="bat1",
            supported_modes=frozenset({ControlMode.CHARGE}),
        )
        assert not cap.supports(ControlMode.GRID_CHARGE)

    def test_default_supported_modes(self) -> None:
        cap = DeviceControlCapability(device_name="bat1")
        assert cap.supports(ControlMode.AUTO)
        assert cap.supports(ControlMode.CHARGE)
        assert cap.supports(ControlMode.DISCHARGE)
        assert cap.supports(ControlMode.IDLE)
        assert not cap.supports(ControlMode.GRID_CHARGE)
