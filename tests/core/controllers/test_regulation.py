"""Tests for fleet-target resolution and slew limiting."""

import pytest

from custom_components.solarbalance.core.controllers.regulation import (
    RegulationInputs,
    apply_slew_limit,
    resolve_fleet_target_w,
    resolve_total_power,
)


def _inp(**kw: object) -> RegulationInputs:
    """RegulationInputs with neutral defaults; override per test."""
    base: dict[str, object] = {
        "zi_regulating": True,
        "current_fleet_w": 0.0,
        "zi_correction_w": 0.0,
        "absolute_target_w": 0.0,
        "steering_w": 0.0,
        "eq_bias_w": 0.0,
        "grid_filtered_w": 0.0,
        "controllable_mppt_w": 0.0,
        "nc_charge_offset_w": 0.0,
        "noncontrollable_charging": False,
        "noncontrollable_charge_w": 0.0,
        "zi_hysteresis_w": 50.0,
        "no_battery_export": False,
        "stop_cloud_charge": False,
        "max_import_w": None,
        "max_export_w": None,
    }
    base.update(kw)
    return RegulationInputs(**base)  # type: ignore[arg-type]


class TestResolveTotalPower:
    def test_surplus_charges_when_exporting(self) -> None:
        # Exporting (grid < -hyst) → no-charge floor is skipped → charge passes.
        out = resolve_total_power(_inp(grid_filtered_w=-800.0, zi_correction_w=800.0))
        assert out == pytest.approx(800.0)

    def test_no_charge_floor_at_balance_floors_to_own_solar(self) -> None:
        # grid ~0, no cloud charging → don't charge from grid: floor at -mppt.
        out = resolve_total_power(
            _inp(grid_filtered_w=0.0, zi_correction_w=500.0, controllable_mppt_w=200.0)
        )
        assert out == pytest.approx(-200.0)

    def test_no_charge_floor_bypassed_when_cloud_charging(self) -> None:
        out = resolve_total_power(
            _inp(
                grid_filtered_w=0.0,
                zi_correction_w=500.0,
                controllable_mppt_w=200.0,
                noncontrollable_charging=True,
            )
        )
        assert out == pytest.approx(500.0)

    def test_no_battery_export_caps_discharge_into_export(self) -> None:
        states = {"grid_filtered_w": -300.0, "zi_correction_w": -500.0}
        assert resolve_total_power(_inp(**states)) == pytest.approx(-500.0)
        assert resolve_total_power(_inp(no_battery_export=True, **states)) == pytest.approx(0.0)

    def test_no_feed_floor_covers_load_not_cloud_charge(self) -> None:
        # Import 600 of which 400 is the cloud charging: cover 200, leave 400.
        out = resolve_total_power(
            _inp(
                grid_filtered_w=600.0,
                zi_correction_w=-600.0,
                nc_charge_offset_w=400.0,
                noncontrollable_charge_w=400.0,
                noncontrollable_charging=True,
            )
        )
        assert out == pytest.approx(-200.0)

    def test_stop_cloud_charge_cuts_in_surplus(self) -> None:
        # Import ~= the cloud charge (no real load) → discharge cut to >= 0.
        out = resolve_total_power(
            _inp(
                grid_filtered_w=400.0,
                zi_correction_w=-400.0,
                nc_charge_offset_w=400.0,
                noncontrollable_charge_w=400.0,
                noncontrollable_charging=True,
                stop_cloud_charge=True,
            )
        )
        assert out == pytest.approx(0.0)

    def test_stop_cloud_charge_does_not_cut_under_real_load(self) -> None:
        # Big real load on top of the cloud charge → keep discharging to cover it.
        out = resolve_total_power(
            _inp(
                grid_filtered_w=1800.0,
                zi_correction_w=-1800.0,
                nc_charge_offset_w=400.0,
                noncontrollable_charge_w=400.0,
                noncontrollable_charging=True,
                stop_cloud_charge=True,
            )
        )
        assert out < 0.0

    def test_equaliser_offer_forces_discharge(self) -> None:
        # Positive offer forces at least that much discharge (exporting → no floor).
        out = resolve_total_power(_inp(grid_filtered_w=-800.0, eq_bias_w=300.0))
        assert out == pytest.approx(-300.0)

    def test_grid_constraint_caps_export(self) -> None:
        out = resolve_total_power(
            _inp(grid_filtered_w=0.0, zi_correction_w=-2000.0, max_export_w=500.0)
        )
        assert out == pytest.approx(-500.0)

    def test_not_regulating_uses_absolute_target_but_still_grid_clamped(self) -> None:
        out = resolve_total_power(
            _inp(zi_regulating=False, absolute_target_w=-1000.0, max_export_w=300.0)
        )
        assert out == pytest.approx(-300.0)


class TestResolveFleetTarget:
    def test_zi_regulating_uses_current_power_plus_correction(self) -> None:
        # Fleet currently discharging 300 W, PI asks for +500 → target -300+500.
        target = resolve_fleet_target_w(
            zi_regulating=True,
            current_fleet_w=-300.0,
            zi_correction_w=500.0,
            absolute_target_w=9999.0,  # must be ignored
            steering_w=0.0,
        )
        assert target == pytest.approx(200.0)

    def test_zi_not_regulating_uses_absolute_target(self) -> None:
        target = resolve_fleet_target_w(
            zi_regulating=False,
            current_fleet_w=-300.0,
            zi_correction_w=500.0,  # must be ignored
            absolute_target_w=1200.0,
            steering_w=0.0,
        )
        assert target == pytest.approx(1200.0)

    @pytest.mark.parametrize("zi_regulating", [True, False])
    def test_steering_is_always_added(self, zi_regulating: bool) -> None:
        target = resolve_fleet_target_w(
            zi_regulating=zi_regulating,
            current_fleet_w=0.0,
            zi_correction_w=0.0,
            absolute_target_w=0.0,
            steering_w=-150.0,
        )
        assert target == pytest.approx(-150.0)


class TestSlewLimit:
    def test_no_previous_command_passes_through(self) -> None:
        assert apply_slew_limit(2000.0, None, 800.0) == 2000.0

    def test_disabled_when_max_ramp_zero(self) -> None:
        assert apply_slew_limit(2000.0, 0.0, 0.0) == 2000.0

    def test_clamps_rising_step(self) -> None:
        assert apply_slew_limit(2000.0, 100.0, 800.0) == pytest.approx(900.0)

    def test_clamps_falling_step(self) -> None:
        assert apply_slew_limit(-2000.0, 100.0, 800.0) == pytest.approx(-700.0)

    def test_small_change_within_limit_unchanged(self) -> None:
        assert apply_slew_limit(300.0, 100.0, 800.0) == pytest.approx(300.0)

    def test_oscillation_is_damped_over_ticks(self) -> None:
        # A command oscillating between +2000 and -2000 is ramp-limited so the
        # actual command crawls instead of slamming between extremes.
        last = 0.0
        commands = []
        for desired in (2000.0, -2000.0, 2000.0, -2000.0):
            last = apply_slew_limit(desired, last, 800.0)
            commands.append(last)
        assert commands == [
            pytest.approx(800.0),
            pytest.approx(0.0),
            pytest.approx(800.0),
            pytest.approx(0.0),
        ]
