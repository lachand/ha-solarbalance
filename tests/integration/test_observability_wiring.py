"""Installation score and anomaly timeline, wired through the coordinator (F3/F4)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.const import DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import BatteryRole, Device, HemsMode


def _coord(hass: HomeAssistant) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
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
async def test_a_clean_install_scores_high(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    coord._reader = MagicMock()
    coord._reader.grid_source = "primary"
    res = coord.installation_score
    assert res.score >= 90.0
    assert res.verdict == "healthy"


@pytest.mark.asyncio
async def test_the_backup_meter_and_degraded_pull_the_score_down(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    coord._reader = MagicMock()
    coord._reader.grid_source = "backup"
    backup = coord.installation_score.score
    assert backup < 90.0

    coord._mode = HemsMode.DEGRADED
    assert coord.installation_score.score < backup


@pytest.mark.asyncio
async def test_a_rejected_grid_reading_lands_on_the_timeline(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    now = dt_util.utcnow().timestamp()
    coord._event_log.record(now, "grid_rejected", "Impossible export rejected")
    timeline = coord.anomaly_timeline
    assert timeline[0]["kind"] == "grid_rejected"
    assert timeline[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_meter_loss_is_recorded_once_on_the_edge(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    coord._reader = MagicMock()
    coord._mode = HemsMode.NORMAL
    snap = SimpleNamespace(timestamp=dt_util.utcnow())

    coord._reader.grid_source = "primary"
    coord._record_health_transitions(snap)  # first tick: establishes the baseline
    coord._reader.grid_source = "none"
    coord._record_health_transitions(snap)
    coord._record_health_transitions(snap)  # still gone — must not add a second row

    lost = [e for e in coord.anomaly_timeline if e["kind"] == "meter_lost"]
    assert len(lost) == 1


@pytest.mark.asyncio
async def test_the_timeline_survives_a_restart(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    coord._event_log.record(dt_util.utcnow().timestamp(), "meter_lost", "gone")
    fresh = _coord(hass)
    await fresh._store.async_save(coord._persisted_state())
    await fresh.async_restore()
    assert [e["kind"] for e in fresh.anomaly_timeline] == ["meter_lost"]
