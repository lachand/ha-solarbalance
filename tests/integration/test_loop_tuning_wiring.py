"""D1 loop tuning, wired: off by default, derates the gain from the actuator lag."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_ACTUATOR_LAG_S,
    CONF_LOOP_TUNING_ENABLED,
    CONF_TICK_INTERVAL_S,
    CONF_ZERO_INJECTION_KP,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import BatteryRole, Device


def _coord(hass: HomeAssistant, **options) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options)
    entry.add_to_hass(hass)
    device = Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=4.0,
            max_charge_power_w=1200,
            max_discharge_power_w=1200,
            soc_entity="sensor.stream_soc",
            power_entity="sensor.stream_power",
            controllable=True,
        ),
    )
    return SolarBalanceCoordinator(hass, entry, [device], [], [])


@pytest.mark.asyncio
async def test_off_by_default_keeps_the_configured_gain(hass: HomeAssistant) -> None:
    coord = _coord(hass, **{CONF_ZERO_INJECTION_KP: 0.6})
    assert coord._loop_tuning_enabled is False
    assert coord._effective_zi_kp == coord._configured_zi_kp == 0.6


@pytest.mark.asyncio
async def test_enabled_it_derates_the_gain_for_a_slow_actuator(hass: HomeAssistant) -> None:
    coord = _coord(
        hass,
        **{
            CONF_LOOP_TUNING_ENABLED: True,
            CONF_ZERO_INJECTION_KP: 0.6,
            CONF_ACTUATOR_LAG_S: 30,
            CONF_TICK_INTERVAL_S: 10,
        },
    )
    # 30 s lag / 10 s tick = 3 commands in flight -> a third of the gain.
    assert abs(coord._effective_zi_kp - 0.2) < 1e-6
    assert coord._configured_zi_kp == 0.6


@pytest.mark.asyncio
async def test_a_one_tick_actuator_is_unchanged_even_when_enabled(hass: HomeAssistant) -> None:
    coord = _coord(
        hass,
        **{
            CONF_LOOP_TUNING_ENABLED: True,
            CONF_ZERO_INJECTION_KP: 0.6,
            CONF_ACTUATOR_LAG_S: 10,
            CONF_TICK_INTERVAL_S: 10,
        },
    )
    assert coord._effective_zi_kp == 0.6


@pytest.mark.asyncio
async def test_the_derated_gain_is_what_the_controller_and_tuner_start_from(
    hass: HomeAssistant,
) -> None:
    coord = _coord(
        hass,
        **{
            CONF_LOOP_TUNING_ENABLED: True,
            CONF_ZERO_INJECTION_KP: 0.8,
            CONF_ACTUATOR_LAG_S: 20,  # 2 ticks in flight -> half the gain = 0.4
            CONF_TICK_INTERVAL_S: 10,
        },
    )
    assert abs(coord._effective_zi_kp - 0.4) < 1e-6
    # The auto-tuner damps from the derated base, never back up to the configured 0.8.
    assert coord._zi_tuner is not None
    assert coord._zi_tuner.value <= 0.4 + 1e-6
