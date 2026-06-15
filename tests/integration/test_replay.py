"""Replay building blocks: historical snapshot reconstruction + forward-fill."""

from datetime import datetime, timedelta, timezone

from homeassistant.core import State

from custom_components.solarbalance.adapters.entity_reader import EntityReader
from custom_components.solarbalance.core.models import (
    BatteryRole,
    Device,
    Meter,
    MeterKind,
)
from custom_components.solarbalance.replay import _values_at


def test_values_at_forward_fills_last_known() -> None:
    t0 = datetime(2026, 6, 14, 0, 0, tzinfo=timezone.utc)
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
                capacity_kwh=5.0, max_charge_power_w=2000, max_discharge_power_w=2000,
                soc_entity="sensor.soc", power_entity="sensor.bp",
            ),
        )
    ]
    meters = [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.grid")]
    historical = {"sensor.grid": "-1500", "sensor.soc": "62", "sensor.bp": "400"}
    reader = EntityReader(
        None, devices, meters, [],
        state_getter=lambda eid: State(eid, historical[eid]) if eid in historical else None,
    )
    when = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
    snap = reader.snapshot(timestamp=when)
    assert snap.timestamp == when
    assert snap.grid_power_w == -1500.0
    assert snap.batteries[0].soc_pct == 62.0
    assert snap.batteries[0].power_w == 400.0
    assert snap.batteries[0].available is True
