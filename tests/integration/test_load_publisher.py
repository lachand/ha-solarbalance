"""Tests for the load publisher (switch / level / power writes)."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.solarbalance.adapters.load_publisher import LoadPublisher
from custom_components.solarbalance.core.controllers.load_dispatch import LoadCommand
from custom_components.solarbalance.core.models import Load, LoadControlType, LoadStep


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


def _calls(hass: MagicMock) -> list[tuple[str, str, dict[str, object]]]:
    return [(c.args[0], c.args[1], c.args[2]) for c in hass.services.async_call.call_args_list]


def _on_off(name: str = "wh") -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.ON_OFF,
        priority=1,
        nominal_power_w=2000,
        switch_entity="switch.water_heater",
    )


def _stepped(name: str = "rad") -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.STEPPED,
        priority=1,
        level_entity="number.rad_level",
        steps=(LoadStep(level=1, power_w=500), LoadStep(level=2, power_w=1000)),
    )


def _modulating(name: str = "ev") -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.MODULATING,
        priority=1,
        min_power_w=1000,
        max_power_w=5000,
        power_set_entity="number.ev_power",
    )


async def test_disabled_publisher_writes_nothing() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_on_off()], enabled=False)
    assert pub.enabled is False
    await pub.apply([LoadCommand(load_name="wh", on=True)])
    assert _calls(hass) == []


async def test_on_off_turns_switch_on_then_off() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_on_off()], enabled=True)
    await pub.apply([LoadCommand(load_name="wh", on=True)])
    await pub.apply([LoadCommand(load_name="wh", on=False)])
    calls = _calls(hass)
    assert calls[0] == ("homeassistant", "turn_on", {"entity_id": "switch.water_heater"})
    assert calls[1] == ("homeassistant", "turn_off", {"entity_id": "switch.water_heater"})


async def test_redundant_command_is_deduplicated() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_on_off()], enabled=True)
    await pub.apply([LoadCommand(load_name="wh", on=True)])
    await pub.apply([LoadCommand(load_name="wh", on=True)])  # same state → no 2nd call
    assert len(_calls(hass)) == 1


async def test_stepped_writes_level() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_stepped()], enabled=True)
    await pub.apply([LoadCommand(load_name="rad", on=True, step_level=2)])
    assert _calls(hass)[0] == (
        "number",
        "set_value",
        {"entity_id": "number.rad_level", "value": 2.0},
    )


async def test_modulating_writes_power_then_zero_when_off() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_modulating()], enabled=True)
    await pub.apply([LoadCommand(load_name="ev", on=True, power_w=3000.0)])
    await pub.apply([LoadCommand(load_name="ev", on=False)])
    calls = _calls(hass)
    assert calls[0] == ("number", "set_value", {"entity_id": "number.ev_power", "value": 3000.0})
    assert calls[1] == ("number", "set_value", {"entity_id": "number.ev_power", "value": 0.0})


def _stepped_with_switch(name: str = "ev") -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.STEPPED,
        priority=5,
        level_entity="number.ev_amps",
        switch_entity="switch.ev",
        steps=(LoadStep(level=6, power_w=1380), LoadStep(level=16, power_w=3680)),
    )


async def test_stepped_with_switch_turns_on_and_sets_level() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_stepped_with_switch()], enabled=True)
    await pub.apply([LoadCommand(load_name="ev", on=True, step_level=16)])
    calls = _calls(hass)
    assert calls[0] == ("homeassistant", "turn_on", {"entity_id": "switch.ev"})
    assert calls[1] == ("number", "set_value", {"entity_id": "number.ev_amps", "value": 16.0})


async def test_stepped_with_switch_off_cuts_switch_without_setting_level() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_stepped_with_switch()], enabled=True)
    await pub.apply([LoadCommand(load_name="ev", on=False, step_level=0)])
    calls = _calls(hass)
    assert calls == [("homeassistant", "turn_off", {"entity_id": "switch.ev"})]


async def test_reset_turns_off_managed_switch() -> None:
    hass = _hass()
    pub = LoadPublisher(hass, [_on_off()], enabled=True)
    await pub.reset()
    assert _calls(hass)[0] == ("homeassistant", "turn_off", {"entity_id": "switch.water_heater"})
