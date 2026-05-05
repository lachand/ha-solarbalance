"""Tests for core data models."""

from datetime import UTC, datetime

import pytest

from custom_components.solarbalance.core.models import (
    BatteryRole,
    BatteryState,
    Chemistry,
    Device,
    InverterRole,
    Load,
    LoadControlType,
    LoadStep,
    MpptRole,
    MpptState,
    PowerSignConvention,
    Snapshot,
)


class TestBatteryRole:
    @pytest.mark.parametrize(
        ("chemistry", "capacity", "expected_usable"),
        [
            (Chemistry.LIFEPO4, 10.0, 9.5),
            (Chemistry.NMC, 10.0, 8.5),
            (Chemistry.LEADACID, 10.0, 5.0),
            (Chemistry.OTHER, 10.0, 9.0),
        ],
    )
    def test_default_usable_capacity_per_chemistry(
        self, chemistry: Chemistry, capacity: float, expected_usable: float
    ) -> None:
        role = BatteryRole(
            capacity_kwh=capacity,
            max_charge_power_w=1000,
            max_discharge_power_w=1000,
            soc_entity="sensor.s",
            power_entity="sensor.p",
            chemistry=chemistry,
        )
        assert role.effective_usable_capacity_kwh == pytest.approx(expected_usable)

    def test_explicit_usable_capacity_overrides_chemistry_default(self) -> None:
        role = BatteryRole(
            capacity_kwh=10.0,
            max_charge_power_w=1000,
            max_discharge_power_w=1000,
            soc_entity="sensor.s",
            power_entity="sensor.p",
            chemistry=Chemistry.LIFEPO4,
            usable_capacity_kwh=8.0,
        )
        assert role.effective_usable_capacity_kwh == 8.0

    def test_must_have_a_power_source(self) -> None:
        with pytest.raises(ValueError, match="power_entity"):
            BatteryRole(
                capacity_kwh=1.0,
                max_charge_power_w=100,
                max_discharge_power_w=100,
                soc_entity="sensor.s",
            )

    def test_separate_charge_discharge_entities_accepted(self) -> None:
        role = BatteryRole(
            capacity_kwh=1.0,
            max_charge_power_w=100,
            max_discharge_power_w=100,
            soc_entity="sensor.s",
            charge_power_entity="sensor.charge",
            discharge_power_entity="sensor.discharge",
        )
        assert role.charge_power_entity == "sensor.charge"

    @pytest.mark.parametrize(
        "convention",
        [PowerSignConvention.CHARGE_POSITIVE, PowerSignConvention.DISCHARGE_POSITIVE],
    )
    def test_power_sign_convention_is_stored(self, convention: PowerSignConvention) -> None:
        role = BatteryRole(
            capacity_kwh=1.0,
            max_charge_power_w=100,
            max_discharge_power_w=100,
            soc_entity="sensor.s",
            power_entity="sensor.p",
            power_sign_convention=convention,
        )
        assert role.power_sign_convention is convention


class TestDevice:
    def test_device_must_declare_at_least_one_role(self) -> None:
        with pytest.raises(ValueError, match="at least one role"):
            Device(name="empty")

    def test_battery_only_device(self, jackery_device: Device) -> None:
        assert jackery_device.battery is not None
        assert jackery_device.mppt is None
        assert jackery_device.inverter is None

    def test_multi_role_device(self, ecoflow_device: Device) -> None:
        assert ecoflow_device.battery is not None
        assert ecoflow_device.mppt is not None
        assert ecoflow_device.inverter is not None


class TestLoad:
    def test_on_off_requires_nominal_and_switch(self) -> None:
        with pytest.raises(ValueError, match="nominal_power_w"):
            Load(name="ballon", control_type=LoadControlType.ON_OFF, priority=1)

    def test_stepped_requires_steps_and_level_entity(self) -> None:
        with pytest.raises(ValueError, match="steps"):
            Load(name="rad", control_type=LoadControlType.STEPPED, priority=1)

    def test_modulating_requires_min_max_and_setter(self) -> None:
        with pytest.raises(ValueError, match="min_power_w"):
            Load(name="ve", control_type=LoadControlType.MODULATING, priority=1)

    def test_valid_modulating_load(self) -> None:
        load = Load(
            name="ve",
            control_type=LoadControlType.MODULATING,
            priority=1,
            min_power_w=1380,
            max_power_w=7360,
            step_w=230,
            power_set_entity="number.ve_set",
        )
        assert load.max_power_w == 7360

    def test_valid_stepped_load(self) -> None:
        load = Load(
            name="rad",
            control_type=LoadControlType.STEPPED,
            priority=2,
            steps=(LoadStep(0, 0), LoadStep(1, 750), LoadStep(2, 1500)),
            level_entity="select.rad_level",
        )
        assert load.steps[2].power_w == 1500


class TestSnapshot:
    def test_pv_total_sums_available_mppts_only(self) -> None:
        snap = Snapshot(
            timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
            grid_power_w=0.0,
            batteries=(),
            mppts=(
                MpptState(device_name="a", power_w=500.0, available=True),
                MpptState(device_name="b", power_w=300.0, available=False),
                MpptState(device_name="c", power_w=200.0, available=True),
            ),
            inverters=(),
            loads=(),
        )
        assert snap.pv_total_w == 700.0

    def test_baseline_consumption_formula(self) -> None:
        snap = Snapshot(
            timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
            grid_power_w=200.0,    # importing 200 W
            batteries=(BatteryState(device_name="a", soc_pct=50.0, power_w=-300.0),),
            mppts=(MpptState(device_name="a", power_w=500.0),),
            inverters=(),
            loads=(),
        )
        # baseline = grid + pv - battery_charge - loads
        #         = 200 + 500 - (-300) - 0 = 1000 W
        assert snap.baseline_consumption_w == 1000.0
