"""The appliance advice must be able to say 'I am recording' before anything is learned."""

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import CONF_APPLIANCE_POWER_ENTITIES, DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator


def _coord(hass: HomeAssistant, entities: list[str]) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_APPLIANCE_POWER_ENTITIES: entities})
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, [], [], [])


@pytest.mark.asyncio
async def test_nothing_configured_reports_nothing(hass: HomeAssistant) -> None:
    assert _coord(hass, []).appliance_advice == []


@pytest.mark.asyncio
async def test_a_configured_appliance_shows_up_before_anything_is_learned(
    hass: HomeAssistant,
) -> None:
    # The gap this closes: an empty list used to mean both "nothing learned yet" and
    # "nothing configured", so there was no way to confirm recording had started.
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    advice = coord.appliance_advice
    assert len(advice) == 1
    assert advice[0]["name"] == "machine a laver"
    assert advice[0]["samples"] == 0
    assert advice[0]["running"] is False
    assert "solar_now_pct" not in advice[0]  # never invent a figure


@pytest.mark.asyncio
async def test_a_running_cycle_is_reported_as_running(hass: HomeAssistant) -> None:
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    t0 = datetime(2026, 7, 24, 10, 0, tzinfo=UTC).timestamp()
    coord._appliance_cycles.observe("machine a laver", t0, 117.0)
    coord._appliance_cycles.observe("machine a laver", t0 + 600.0, 120.0)

    advice = coord.appliance_advice
    assert advice[0]["running"] is True
