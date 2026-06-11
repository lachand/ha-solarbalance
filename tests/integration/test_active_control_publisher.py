"""Tests for the discharge-only active control publisher."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.solarbalance.adapters.active_control_publisher import (
    ActiveControlPublisher,
)
from custom_components.solarbalance.core.models import BatteryRole, Device


def _device(
    name: str,
    *,
    active: bool = True,
    entity: str | None = "number.dis",
    controllable: bool = True,
) -> Device:
    return Device(
        name=name,
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="sensor.soc",
            power_entity="sensor.power",
            controllable=controllable,
            active_control_enabled=active,
            discharge_power_setpoint_entity=entity if active else None,
        ),
    )


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


def _calls(hass: MagicMock) -> list[tuple[str, str, dict[str, object]]]:
    return [(c.args[0], c.args[1], c.args[2]) for c in hass.services.async_call.call_args_list]


def test_enabled_only_when_a_device_declares_entity() -> None:
    assert ActiveControlPublisher(_hass(), [_device("a")]).enabled is True
    assert ActiveControlPublisher(_hass(), [_device("a", active=False)]).enabled is False


async def test_discharge_allocation_written_as_positive_value() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0})
    calls = _calls(hass)
    assert calls == [("number", "set_value", {"entity_id": "number.dis_a", "value": 800.0})]


async def test_charging_or_idle_writes_zero_discharge() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": 600.0})
    assert _calls(hass) == [
        ("number", "set_value", {"entity_id": "number.dis_a", "value": 0.0})
    ]


async def test_unchanged_setpoint_is_not_rewritten() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0})
    await pub.apply({"a": -802.0})  # within epsilon → skipped
    assert len(_calls(hass)) == 1


async def test_input_number_entity_uses_its_own_domain() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="input_number.dis_a")])
    await pub.apply({"a": -500.0})
    assert _calls(hass)[0][0] == "input_number"


async def test_reset_commands_zero() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0})
    await pub.reset()
    assert _calls(hass)[-1] == ("number", "set_value", {"entity_id": "number.dis_a", "value": 0.0})


async def test_only_active_control_devices_are_written() -> None:
    hass = _hass()
    pub = ActiveControlPublisher(
        hass,
        [_device("a", entity="number.dis_a"), _device("b", active=False)],
    )
    await pub.apply({"a": -300.0, "b": -300.0})
    written = {c[2]["entity_id"] for c in _calls(hass)}
    assert written == {"number.dis_a"}


async def test_service_failure_is_swallowed_and_not_cached() -> None:
    hass = _hass()
    hass.services.async_call.side_effect = RuntimeError("boom")
    pub = ActiveControlPublisher(hass, [_device("a", entity="number.dis_a")])
    await pub.apply({"a": -800.0})  # must not raise
    # failed write is not cached → a retry is attempted on the next tick
    hass.services.async_call.side_effect = None
    await pub.apply({"a": -800.0})
    assert len(_calls(hass)) == 2
