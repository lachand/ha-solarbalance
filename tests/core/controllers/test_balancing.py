"""Tests for the hybrid balancing controller."""

from dataclasses import replace

import pytest

from custom_components.solarbalance.core.controllers.balancing import BalancingController
from custom_components.solarbalance.core.models import BatteryRole, BatteryState, Device


def _state(device_name: str, soc_pct: float, *, available: bool = True) -> BatteryState:
    return BatteryState(device_name=device_name, soc_pct=soc_pct, power_w=0.0, available=available)


def test_discharge_excluded_within_soc_margin_of_floor() -> None:
    # A battery just above its floor gets no discharge (anti-windup margin) — the box
    # won't discharge that close to its reserve, so commanding it only winds the loop up.
    dev = Device(
        name="b",
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="sensor.s",
            power_entity="sensor.p",
            soc_min_pct=20,
            controllable=True,
        ),
    )
    ctrl = BalancingController([dev], alpha=1.0)
    # 21 % is within the 2 % margin of the 20 % floor → excluded (loop can relax).
    near = ctrl.allocate(total_power_w=-500.0, states={"b": _state("b", 21.0)})
    assert near.per_battery_w == {}
    assert near.unallocated_w == -500.0
    # Clear of the margin → discharge allocated normally.
    clear = ctrl.allocate(total_power_w=-500.0, states={"b": _state("b", 25.0)})
    assert clear.per_battery_w["b"] == pytest.approx(-500.0, abs=2.0)


def _discharge_dev(name: str = "b", *, soc_min_pct: int = 20) -> Device:
    return Device(
        name=name,
        battery=BatteryRole(
            capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="sensor.s",
            power_entity="sensor.p",
            soc_min_pct=soc_min_pct,
            controllable=True,
        ),
    )


def test_charge_cap_limits_allocation_and_reports_saturation() -> None:
    # The entity accepts at most 1050 W even though max_charge_power_w is 2000: the
    # allocation is capped at 1050 and the rest is reported as unallocated, so the
    # velocity-form anti-windup sees the real saturation (no wind-up past the limit).
    ctrl = BalancingController([_discharge_dev(soc_min_pct=10)], alpha=1.0)
    res = ctrl.allocate(
        total_power_w=2000.0,
        states={"b": _state("b", 50.0)},
        charge_caps={"b": 1050.0},
    )
    assert res.per_battery_w["b"] == pytest.approx(1050.0, abs=2.0)
    assert res.unallocated_w == pytest.approx(950.0, abs=2.0)


def _priority_pair() -> list[Device]:
    small = Device(
        name="river",
        battery=BatteryRole(
            capacity_kwh=0.256,
            max_charge_power_w=360,
            max_discharge_power_w=0,
            soc_entity="s1",
            power_entity="p1",
            soc_min_pct=5,
            soc_max_pct=100,
            controllable=True,
            charge_priority_target_soc_pct=90,
        ),
    )
    big = Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=3.84,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            soc_entity="s2",
            power_entity="p2",
            soc_min_pct=10,
            controllable=True,
        ),
    )
    return [small, big]


def test_charge_priority_fills_priority_battery_first() -> None:
    # The River (0.256 kWh) would normally get ~6 % of the surplus; with a charge-priority
    # target it takes the surplus first, up to its 360 W cap, before the big STREAM.
    ctrl = BalancingController(_priority_pair(), alpha=1.0)
    res = ctrl.allocate(
        total_power_w=1000.0,
        states={"river": _state("river", 50.0), "stream": _state("stream", 50.0)},
    )
    assert res.per_battery_w["river"] == pytest.approx(360.0, abs=2.0)
    assert res.per_battery_w["stream"] == pytest.approx(640.0, abs=2.0)


def test_charge_priority_inactive_at_target() -> None:
    # At/above its target SoC the priority no longer applies → normal ~6 % share.
    ctrl = BalancingController(_priority_pair(), alpha=1.0)
    res = ctrl.allocate(
        total_power_w=1000.0,
        states={"river": _state("river", 90.0), "stream": _state("stream", 50.0)},
    )
    assert res.per_battery_w["river"] < 100.0
    assert res.per_battery_w["stream"] > 900.0


def test_discharge_rate_tapers_above_floor() -> None:
    # floor = 22 %, taper band 4 % → full at 26 %. At 24 % the cap is (24-22)/4 = 50 %
    # of the 2000 W rate = 1000 W, so a 1500 W request is clamped to 1000 W (not 0, not
    # full) — the setpoint eases in near the floor instead of snapping 0<->max.
    ctrl = BalancingController([_discharge_dev()], alpha=1.0)
    res = ctrl.allocate(total_power_w=-1500.0, states={"b": _state("b", 24.0)})
    assert res.per_battery_w["b"] == pytest.approx(-1000.0, abs=2.0)
    assert res.unallocated_w == pytest.approx(-500.0, abs=2.0)


def test_discharge_hysteresis_blocks_rearm_on_soc_flicker() -> None:
    # The morning yoyo: SoC quantises 22<->23 right at the floor. Once rested at 22 %,
    # a bounce to 23 % must NOT re-arm discharge (needs floor + rearm = 24 %).
    ctrl = BalancingController([_discharge_dev()], alpha=1.0)
    # Drop to the floor → rested (excluded).
    assert ctrl.allocate(total_power_w=-500.0, states={"b": _state("b", 22.0)}).per_battery_w == {}
    # Bounce to 23 % → still rested (hysteresis), no discharge.
    assert ctrl.allocate(total_power_w=-500.0, states={"b": _state("b", 23.0)}).per_battery_w == {}
    # Recover to 24 % → re-armed, discharge resumes (tapered).
    resumed = ctrl.allocate(total_power_w=-500.0, states={"b": _state("b", 24.0)})
    assert resumed.per_battery_w["b"] == pytest.approx(-500.0, abs=2.0)


class TestBalancingController:
    @pytest.mark.parametrize("alpha", [-0.1, 1.5])
    def test_alpha_must_be_in_unit_interval(self, alpha: float, ecoflow_device: Device) -> None:
        with pytest.raises(ValueError, match="alpha"):
            BalancingController([ecoflow_device], alpha=alpha)

    def test_no_eligible_batteries_returns_unallocated(self, ecoflow_device: Device) -> None:
        controller = BalancingController([ecoflow_device], alpha=0.6)
        result = controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 95.0)},
        )
        assert result.unallocated_w == 500.0
        assert result.per_battery_w == {}

    def test_non_controllable_battery_excluded_from_allocation(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        """A battery flagged controllable=false never receives an allocation."""
        assert jackery_device.battery is not None
        auto = replace(jackery_device, battery=replace(jackery_device.battery, controllable=False))
        controller = BalancingController([ecoflow_device, auto], alpha=1.0)
        result = controller.allocate(
            total_power_w=1000.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 50.0),
                "jackery_garage": _state("jackery_garage", 50.0),
            },
        )
        assert "jackery_garage" not in result.per_battery_w
        assert result.per_battery_w["ecoflow_living_room"] == pytest.approx(1000.0, abs=2.0)

    def test_two_batteries_balanced_charge(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        controller = BalancingController([ecoflow_device, jackery_device], alpha=1.0)
        result = controller.allocate(
            total_power_w=1000.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 50.0),
                "jackery_garage": _state("jackery_garage", 50.0),
            },
        )
        # alpha=1.0 (capacity-only), capacities 3.6 and 2.0 → ratio 64.3% / 35.7%
        assert result.per_battery_w["ecoflow_living_room"] == pytest.approx(643.0, abs=2.0)
        assert result.per_battery_w["jackery_garage"] == pytest.approx(357.0, abs=2.0)
        assert abs(result.unallocated_w) < 2.0

    def test_equalisation_favours_lagging_battery_on_charge(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        controller = BalancingController([ecoflow_device, jackery_device], alpha=0.0)
        result = controller.allocate(
            total_power_w=1000.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 80.0),
                "jackery_garage": _state("jackery_garage", 20.0),  # lagging
            },
        )
        # alpha=0 (equalisation only): the lagging battery gets the lion's share.
        assert result.per_battery_w["jackery_garage"] > result.per_battery_w["ecoflow_living_room"]

    def test_equalisation_favours_leading_battery_on_discharge(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        controller = BalancingController([ecoflow_device, jackery_device], alpha=0.0)
        result = controller.allocate(
            total_power_w=-1000.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 80.0),  # leading
                "jackery_garage": _state("jackery_garage", 20.0),
            },
        )
        # On discharge the leading battery should give more.
        assert abs(result.per_battery_w["ecoflow_living_room"]) > abs(
            result.per_battery_w["jackery_garage"]
        )

    def test_saturation_redistributes_to_non_saturated(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        # Both batteries must charge 5000 W aggregate.
        # Ecoflow caps at 1800 W, Jackery caps at 1000 W → max possible 2800 W.
        controller = BalancingController([ecoflow_device, jackery_device], alpha=0.6)
        result = controller.allocate(
            total_power_w=5000.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 50.0),
                "jackery_garage": _state("jackery_garage", 50.0),
            },
        )
        assert result.per_battery_w["ecoflow_living_room"] == pytest.approx(1800.0, abs=1.0)
        assert result.per_battery_w["jackery_garage"] == pytest.approx(1000.0, abs=1.0)
        assert result.unallocated_w == pytest.approx(2200.0, abs=2.0)

    def test_full_battery_excluded_from_charge_pool(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        controller = BalancingController([ecoflow_device, jackery_device], alpha=0.6)
        result = controller.allocate(
            total_power_w=500.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 95.0),  # at ceiling
                "jackery_garage": _state("jackery_garage", 50.0),
            },
        )
        assert result.per_battery_w["ecoflow_living_room"] == 0.0
        assert result.per_battery_w["jackery_garage"] == pytest.approx(500.0, abs=2.0)

    def test_unavailable_battery_excluded(
        self, ecoflow_device: Device, jackery_device: Device
    ) -> None:
        controller = BalancingController([ecoflow_device, jackery_device], alpha=0.6)
        result = controller.allocate(
            total_power_w=500.0,
            states={
                "ecoflow_living_room": _state("ecoflow_living_room", 50.0, available=False),
                "jackery_garage": _state("jackery_garage", 50.0),
            },
        )
        assert result.per_battery_w["ecoflow_living_room"] == 0.0
        assert result.per_battery_w["jackery_garage"] == pytest.approx(500.0, abs=2.0)


class TestAntiShortCycle:
    """Tests for the min_dwell_s direction-reversal guard."""

    def test_first_direction_is_always_allowed(self, ecoflow_device: Device) -> None:
        from datetime import UTC, datetime

        controller = BalancingController([ecoflow_device], alpha=0.6, min_dwell_s=60.0)
        now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
        result = controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=now,
        )
        assert result.per_battery_w["ecoflow_living_room"] > 0.0

    def test_reversal_blocked_within_dwell(self, ecoflow_device: Device) -> None:
        from datetime import UTC, datetime, timedelta

        controller = BalancingController([ecoflow_device], alpha=0.6, min_dwell_s=60.0)
        t0 = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

        # First tick: charge
        controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=t0,
        )
        # 30 s later: try to discharge (within dwell window)
        t1 = t0 + timedelta(seconds=30)
        result = controller.allocate(
            total_power_w=-500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=t1,
        )
        # Battery should be excluded → unallocated
        assert result.per_battery_w == {}
        assert result.unallocated_w == pytest.approx(-500.0)

    def test_reversal_allowed_after_dwell(self, ecoflow_device: Device) -> None:
        from datetime import UTC, datetime, timedelta

        controller = BalancingController([ecoflow_device], alpha=0.6, min_dwell_s=60.0)
        t0 = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

        # First tick: charge
        controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=t0,
        )
        # 61 s later: try to discharge (past dwell window)
        t1 = t0 + timedelta(seconds=61)
        result = controller.allocate(
            total_power_w=-500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=t1,
        )
        assert result.per_battery_w["ecoflow_living_room"] < 0.0

    def test_no_guard_when_min_dwell_zero(self, ecoflow_device: Device) -> None:
        from datetime import UTC, datetime, timedelta

        controller = BalancingController([ecoflow_device], alpha=0.6, min_dwell_s=0.0)
        t0 = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
        controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=t0,
        )
        # Immediate reversal allowed when guard is disabled
        t1 = t0 + timedelta(seconds=1)
        result = controller.allocate(
            total_power_w=-500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=t1,
        )
        assert result.per_battery_w["ecoflow_living_room"] < 0.0

    def test_no_guard_when_now_is_none(self, ecoflow_device: Device) -> None:
        controller = BalancingController([ecoflow_device], alpha=0.6, min_dwell_s=60.0)
        # Charge with now=None (no tracking)
        controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=None,
        )
        # Immediate discharge also with now=None (guard skipped)
        result = controller.allocate(
            total_power_w=-500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 50.0)},
            now=None,
        )
        assert result.per_battery_w["ecoflow_living_room"] < 0.0
