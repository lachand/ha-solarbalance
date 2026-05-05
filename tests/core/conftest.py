"""Shared fixtures for core tests."""

from datetime import UTC, datetime

import pytest

from custom_components.solarbalance.core.models import (
    BatteryRole,
    BatteryState,
    Chemistry,
    Device,
    InverterRole,
    InverterState,
    MpptRole,
    MpptState,
    Snapshot,
)


@pytest.fixture
def ecoflow_device() -> Device:
    """A typical all-in-one station (battery + MPPT + inverter)."""
    return Device(
        name="ecoflow_living_room",
        battery=BatteryRole(
            capacity_kwh=3.6,
            max_charge_power_w=1800,
            max_discharge_power_w=1800,
            soc_entity="sensor.eco_soc",
            power_entity="sensor.eco_power",
            chemistry=Chemistry.LIFEPO4,
        ),
        mppt=MpptRole(peak_power_w=1000, power_entity="sensor.eco_pv"),
        inverter=InverterRole(nominal_power_w=2400, ac_output_power_entity="sensor.eco_ac"),
    )


@pytest.fixture
def jackery_device() -> Device:
    """A second smaller station, different capacity."""
    return Device(
        name="jackery_garage",
        battery=BatteryRole(
            capacity_kwh=2.0,
            max_charge_power_w=1000,
            max_discharge_power_w=1000,
            soc_entity="sensor.jack_soc",
            power_entity="sensor.jack_power",
            chemistry=Chemistry.LIFEPO4,
        ),
    )


@pytest.fixture
def empty_snapshot() -> Snapshot:
    """A snapshot with no devices, no grid activity — for trivial tests."""
    return Snapshot(
        timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        grid_power_w=0.0,
        batteries=(),
        mppts=(),
        inverters=(),
        loads=(),
    )


def make_snapshot(
    *,
    grid_w: float,
    batteries: tuple[BatteryState, ...] = (),
    mppts: tuple[MpptState, ...] = (),
    inverters: tuple[InverterState, ...] = (),
) -> Snapshot:
    """Helper to build a snapshot at a fixed timestamp."""
    return Snapshot(
        timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        grid_power_w=grid_w,
        batteries=batteries,
        mppts=mppts,
        inverters=inverters,
        loads=(),
    )
