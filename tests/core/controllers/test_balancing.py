"""Tests for the hybrid balancing controller."""

import pytest

from custom_components.solarbalance.core.controllers.balancing import BalancingController
from custom_components.solarbalance.core.models import BatteryState, Device


def _state(device_name: str, soc_pct: float, *, available: bool = True) -> BatteryState:
    return BatteryState(device_name=device_name, soc_pct=soc_pct, power_w=0.0, available=available)


class TestBalancingController:
    @pytest.mark.parametrize("alpha", [-0.1, 1.5])
    def test_alpha_must_be_in_unit_interval(
        self, alpha: float, ecoflow_device: Device
    ) -> None:
        with pytest.raises(ValueError, match="alpha"):
            BalancingController([ecoflow_device], alpha=alpha)

    def test_no_eligible_batteries_returns_unallocated(
        self, ecoflow_device: Device
    ) -> None:
        controller = BalancingController([ecoflow_device], alpha=0.6)
        result = controller.allocate(
            total_power_w=500.0,
            states={"ecoflow_living_room": _state("ecoflow_living_room", 95.0)},
        )
        assert result.unallocated_w == 500.0
        assert result.per_battery_w == {}

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
