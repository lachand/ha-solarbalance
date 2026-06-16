"""Options flow: sectioned menu (general / forecast / tariff)."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TARIFF_TYPE,
    CONF_TICK_INTERVAL_S,
    DOMAIN,
)
from custom_components.solarbalance.core.models import StrategyKind


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    e = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10,
            CONF_PHASES: 1,
            CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
    )
    e.add_to_hass(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def test_export_then_import_config_roundtrip(hass: HomeAssistant) -> None:
    """export_config returns the sub-entries; import_config re-creates them."""
    from homeassistant.config_entries import ConfigSubentryData

    battery = ConfigSubentryData(
        subentry_type="battery",
        title="stream",
        unique_id=None,
        data={
            "name": "stream",
            "roles": {
                "battery": {
                    "capacity_kwh": 3.92,
                    "max_charge_power_w": 1200,
                    "max_discharge_power_w": 2300,
                    "soc_entity": "sensor.soc",
                    "power_entity": "sensor.bp",
                }
            },
        },
    )
    src = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10,
            CONF_PHASES: 1,
            CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
        subentries_data=[battery],
    )
    src.add_to_hass(hass)
    await hass.config_entries.async_setup(src.entry_id)
    await hass.async_block_till_done()

    exported = await hass.services.async_call(
        DOMAIN, "export_config", {}, blocking=True, return_response=True
    )
    assert len(exported["subentries"]) == 1
    assert exported["subentries"][0]["data"]["name"] == "stream"

    res = await hass.services.async_call(
        DOMAIN,
        "import_config",
        {
            "subentries": [
                {
                    "type": "load",
                    "title": "wh",
                    "data": {
                        "name": "wh",
                        "control_type": "on_off",
                        "priority": 3,
                        "nominal_power_w": 2000,
                        "switch_entity": "switch.wh",
                    },
                }
            ]
        },
        blocking=True,
        return_response=True,
    )
    assert res["imported"] == 1
    await hass.async_block_till_done()
    titles = {s.title for s in src.subentries.values()}
    assert {"stream", "wh"} <= titles


async def test_test_mapping_reports_entity_availability(hass: HomeAssistant) -> None:
    from homeassistant.config_entries import ConfigSubentryData

    battery = ConfigSubentryData(
        subentry_type="battery",
        title="stream",
        unique_id=None,
        data={
            "name": "stream",
            "roles": {
                "battery": {
                    "capacity_kwh": 3.9,
                    "max_charge_power_w": 1200,
                    "max_discharge_power_w": 2300,
                    "soc_entity": "sensor.ecoflow_soc",
                    "power_entity": "sensor.ecoflow_batt_power",
                }
            },
        },
    )
    e = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10,
            CONF_PHASES: 1,
            CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
        subentries_data=[battery],
    )
    e.add_to_hass(hass)
    hass.states.async_set("sensor.ecoflow_soc", "55")  # present
    # sensor.ecoflow_batt_power left missing on purpose
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN, "test_mapping", {}, blocking=True, return_response=True
    )
    assert "sensor.ecoflow_soc" in res["ok"]
    assert "sensor.ecoflow_batt_power" in res["missing"]


async def test_options_menu_then_tariff_section_merges(hass, entry) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert set(result["menu_options"]) == {"general", "forecast", "tariff"}

    # Pick the tariff section.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tariff"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "tariff"

    # Submit it; the section is merged into the entry options.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TARIFF_TYPE: "hc_hp"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TARIFF_TYPE] == "hc_hp"
