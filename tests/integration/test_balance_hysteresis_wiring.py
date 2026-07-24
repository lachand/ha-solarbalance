"""Balance-point hysteresis, wired: off by default, and it only ever holds still."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_ACTUATOR_LAG_S,
    CONF_BALANCE_HYSTERESIS_ENABLED,
    CONF_ZERO_INJECTION_HYSTERESIS_W,
    DOMAIN,
)
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.controllers.balance_point import (
    BalancePointState,
    balance_band,
)
from custom_components.solarbalance.core.models import BatteryRole, Device


def _coordinator(hass: HomeAssistant, **options) -> SolarBalanceCoordinator:
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
async def test_it_is_off_unless_asked_for(hass: HomeAssistant) -> None:
    """It touches control, so an existing install must see no change at all."""
    coord = _coordinator(hass)
    assert coord._balance_hysteresis_enabled is False

    band = balance_band(
        enabled=coord._balance_hysteresis_enabled,
        error_w=10.0,
        base_hysteresis_w=coord._zi_hysteresis_w,
        actuator_lag_s=coord._actuator_lag_s,
        tick_s=float(coord._tick_s),
        state=BalancePointState(),
    )
    assert band.settled is False
    assert band.reason == "disabled"


@pytest.mark.asyncio
async def test_the_options_reach_the_controller(hass: HomeAssistant) -> None:
    coord = _coordinator(
        hass,
        **{
            CONF_BALANCE_HYSTERESIS_ENABLED: True,
            CONF_ACTUATOR_LAG_S: 45,
            CONF_ZERO_INJECTION_HYSTERESIS_W: 60,
        },
    )
    assert coord._balance_hysteresis_enabled is True
    assert coord._actuator_lag_s == 45.0
    assert coord._zi_hysteresis_w == 60.0


@pytest.mark.asyncio
async def test_enabled_it_holds_across_the_ticks_that_used_to_dither(
    hass: HomeAssistant,
) -> None:
    """The wired version of the unit test, with the coordinator's own settings."""
    coord = _coordinator(
        hass,
        **{
            CONF_BALANCE_HYSTERESIS_ENABLED: True,
            CONF_ACTUATOR_LAG_S: 30,
            CONF_ZERO_INJECTION_HYSTERESIS_W: 50,
        },
    )
    state = coord._balance_state
    settled = []
    for error_w in [45.0, 55.0, 48.0, 60.0, 52.0]:
        band = balance_band(
            enabled=coord._balance_hysteresis_enabled,
            error_w=error_w,
            base_hysteresis_w=coord._zi_hysteresis_w,
            actuator_lag_s=coord._actuator_lag_s,
            tick_s=float(coord._tick_s),
            state=state,
        )
        state = band.new_state
        settled.append(band.settled)

    assert all(settled), "these errors used to flip the loop on and off every tick"


@pytest.mark.asyncio
async def test_an_export_excursion_still_breaks_the_hold(hass: HomeAssistant) -> None:
    """Whatever else it does, it must never sit on an export."""
    coord = _coordinator(
        hass,
        **{
            CONF_BALANCE_HYSTERESIS_ENABLED: True,
            CONF_ACTUATOR_LAG_S: 30,
            CONF_ZERO_INJECTION_HYSTERESIS_W: 50,
        },
    )
    settled = balance_band(
        enabled=True,
        error_w=10.0,
        base_hysteresis_w=coord._zi_hysteresis_w,
        actuator_lag_s=coord._actuator_lag_s,
        tick_s=float(coord._tick_s),
        state=coord._balance_state,
    )
    assert settled.settled is True

    exporting = balance_band(
        enabled=True,
        error_w=-70.0,  # 70 W of export: inside the import band, outside the export one
        base_hysteresis_w=coord._zi_hysteresis_w,
        actuator_lag_s=coord._actuator_lag_s,
        tick_s=float(coord._tick_s),
        state=settled.new_state,
    )
    assert exporting.settled is False
