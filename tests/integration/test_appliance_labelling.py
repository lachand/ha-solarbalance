"""Labelling learned cycles, end to end: the panel data and the two service handlers."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import CONF_APPLIANCE_POWER_ENTITIES, DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.appliance_cycles import CycleTemplate


def _coord(hass: HomeAssistant, entities: list[str]) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_APPLIANCE_POWER_ENTITIES: entities})
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, [], [], [])


def _cold() -> CycleTemplate:
    return CycleTemplate(2400.0, 0.3, tuple([200.0] * 24))


def _hot() -> CycleTemplate:
    return CycleTemplate(5400.0, 1.6, tuple([1400.0] * 24))


@pytest.mark.asyncio
async def test_the_advice_flags_unlabelled_cycles_and_shows_the_last_one(
    hass: HomeAssistant,
) -> None:
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    coord._appliance_cycles.add_template("machine a laver", _cold())
    coord._appliance_cycles.add_template("machine a laver", _hot())

    item = next(a for a in coord.appliance_advice if a["name"] == "machine a laver")
    assert item["unlabelled"] == 2
    # The last cycle is reported on its own — the hot wash — not the blend of both.
    assert item["last_unlabelled"]["energy_kwh"] > 1.0
    assert item["last_unlabelled"]["duration_min"] == 90


@pytest.mark.asyncio
async def test_labelling_the_last_cycle_moves_exactly_one(hass: HomeAssistant) -> None:
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    for _ in range(3):
        coord._appliance_cycles.add_template("machine a laver", _cold())
    coord._appliance_cycles.add_template("machine a laver", _hot())

    # Case-insensitive on the readable name, like the rename handler.
    ok = await coord.label_last_appliance_cycle("Machine A Laver", "Coton 60")
    assert ok is True

    item = next(a for a in coord.appliance_advice if a["name"] == "machine a laver")
    assert item["unlabelled"] == 3
    programs = {p["program"]: p for p in item["programs"]}
    assert programs["Coton 60"]["samples"] == 1
    assert programs["Coton 60"]["energy_kwh"] > 1.0


@pytest.mark.asyncio
async def test_labelling_with_nothing_to_move_reports_false(hass: HomeAssistant) -> None:
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    coord._appliance_cycles.add_template("machine a laver", _hot(), program="Coton 60")
    assert await coord.label_last_appliance_cycle("machine a laver", "Coton 40") is False


@pytest.mark.asyncio
async def test_no_unlabelled_key_when_the_bucket_is_empty(hass: HomeAssistant) -> None:
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    coord._appliance_cycles.add_template("machine a laver", _hot(), program="Coton 60")
    item = next(a for a in coord.appliance_advice if a["name"] == "machine a laver")
    assert "unlabelled" not in item


@pytest.mark.asyncio
async def test_a_label_survives_a_restart(hass: HomeAssistant) -> None:
    coord = _coord(hass, ["sensor.machine_a_laver_power"])
    coord._appliance_cycles.add_template("machine a laver", _hot())
    await coord.label_last_appliance_cycle("machine a laver", "Coton 60")

    fresh = _coord(hass, ["sensor.machine_a_laver_power"])
    await fresh._store.async_save(coord._persisted_state())
    await fresh.async_restore()
    item = next(a for a in fresh.appliance_advice if a["name"] == "machine a laver")
    assert [p["program"] for p in item["programs"]] == ["Coton 60"]
