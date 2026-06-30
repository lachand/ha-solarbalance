"""Replay building blocks: historical snapshot reconstruction + forward-fill."""

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance import COORDINATOR_KEY, YAML_CONFIG_KEY
from custom_components.solarbalance.adapters.entity_reader import EntityReader
from custom_components.solarbalance.const import (
    CONF_PHASES,
    CONF_PRIORITIES,
    CONF_SUBSCRIBED_POWER_KVA,
    CONF_TICK_INTERVAL_S,
    DOMAIN,
)
from custom_components.solarbalance.core.models import (
    BatteryRole,
    Device,
    Meter,
    MeterKind,
    StrategyKind,
)
from custom_components.solarbalance.replay import _values_at, async_replay_day


def test_values_at_forward_fills_last_known() -> None:
    t0 = datetime(2026, 6, 14, 0, 0, tzinfo=UTC)
    timelines = {
        "sensor.grid": [(t0, "100"), (t0 + timedelta(hours=2), "300")],
    }
    # Before any change after t0+1h → still 100; after t0+2h → 300.
    assert _values_at(timelines, t0 + timedelta(hours=1)) == {"sensor.grid": "100"}
    assert _values_at(timelines, t0 + timedelta(hours=3)) == {"sensor.grid": "300"}
    # Before the first sample → entity absent.
    assert _values_at(timelines, t0 - timedelta(hours=1)) == {}


def test_entity_reader_builds_snapshot_from_historical_states() -> None:
    devices = [
        Device(
            name="batt",
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=2000,
                max_discharge_power_w=2000,
                soc_entity="sensor.soc",
                power_entity="sensor.bp",
            ),
        )
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid")]
    historical = {"sensor.grid": "-1500", "sensor.soc": "62", "sensor.bp": "400"}
    reader = EntityReader(
        None,
        devices,
        meters,
        [],
        state_getter=lambda eid: State(eid, historical[eid]) if eid in historical else None,
    )
    when = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
    snap = reader.snapshot(timestamp=when)
    assert snap.timestamp == when
    assert snap.grid_power_w == -1500.0
    assert snap.batteries[0].soc_pct == 62.0
    assert snap.batteries[0].power_w == 400.0
    assert snap.batteries[0].available is True


def test_shared_power_entity_split_across_battery_devices() -> None:
    # Two STREAM batteries declared as 2 devices but reporting only one *system* power
    # entity: the reading is split so the fleet sum counts it once, not twice.
    def _batt(name: str, soc: str) -> Device:
        return Device(
            name=name,
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=2000,
                max_discharge_power_w=2000,
                soc_entity=soc,
                power_entity="sensor.stream_system_power",  # shared by both devices
            ),
        )

    devices = [_batt("stream_a", "sensor.soc_a"), _batt("stream_b", "sensor.soc_b")]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid")]
    historical = {
        "sensor.grid": "0",
        "sensor.soc_a": "60",
        "sensor.soc_b": "62",
        "sensor.stream_system_power": "800",
    }
    reader = EntityReader(
        None,
        devices,
        meters,
        [],
        state_getter=lambda eid: State(eid, historical[eid]) if eid in historical else None,
    )
    snap = reader.snapshot(timestamp=datetime(2026, 6, 14, 12, 0, tzinfo=UTC))
    powers = {b.device_name: b.power_w for b in snap.batteries}
    assert powers["stream_a"] == 400.0  # 800 / 2 sharers
    assert powers["stream_b"] == 400.0
    assert sum(b.power_w for b in snap.batteries) == 800.0  # system power counted once
    assert all(b.available for b in snap.batteries)  # per-battery SoC + power present


@pytest.mark.asyncio
async def test_async_replay_day_runs_arbiter_and_summarises(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Full replay loop: recorder history → snapshots → arbiter → hourly summary.

    Regression: the loop read result.decision.dominant_strategy (does not exist)
    instead of result.dominant_strategy → the service failed with "Unknown error".
    """
    devices = [
        Device(
            name="batt",
            battery=BatteryRole(
                capacity_kwh=5.0,
                max_charge_power_w=2000,
                max_discharge_power_w=2000,
                soc_entity="sensor.soc",
                power_entity="sensor.bp",
            ),
        )
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid")]
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = (devices, meters, [], None, None)
    hass.states.async_set("sensor.grid", "-1000")
    hass.states.async_set("sensor.soc", "50")
    hass.states.async_set("sensor.bp", "0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TICK_INTERVAL_S: 10,
            CONF_PHASES: 1,
            CONF_SUBSCRIBED_POWER_KVA: 6,
            CONF_PRIORITIES: [k.value for k in StrategyKind],
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]

    # Stub the recorder: a couple of history points across today.
    midnight = dt_util.start_of_local_day(dt_util.now())
    hist = {
        "sensor.grid": [
            State("sensor.grid", "-1500", last_updated=midnight),
            State("sensor.grid", "800", last_updated=midnight + timedelta(hours=3)),
        ],
        "sensor.soc": [State("sensor.soc", "55", last_updated=midnight)],
        "sensor.bp": [State("sensor.bp", "0", last_updated=midnight)],
    }

    class _FakeRecorder:
        async def async_add_executor_job(self, func, *args):
            return hist

    import homeassistant.components.recorder as rec

    monkeypatch.setattr(rec, "get_instance", lambda _hass: _FakeRecorder())

    res = await async_replay_day(hass, coord, day=dt_util.now().date(), step_minutes=30)
    assert "error" not in res, res
    assert res["samples"] > 0
    assert res["hourly"]  # at least one hour bucket
    assert "strategy" in res["hourly"][0]  # would AttributeError before the fix
