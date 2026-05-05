"""Tests for the longevity strategy."""

import pytest

from custom_components.solarbalance.core.models import Chemistry, Device
from custom_components.solarbalance.core.strategies.longevity import LongevityStrategy
from tests.core.conftest import make_snapshot


class TestLongevityStrategy:
    def test_kind_identifier(self, ecoflow_device: Device) -> None:
        strat = LongevityStrategy([ecoflow_device], loads=[])
        assert strat.kind == "longevity"

    @pytest.mark.parametrize(
        ("chemistry", "expected_min", "expected_max"),
        [
            (Chemistry.LIFEPO4, 20.0, 90.0),
            (Chemistry.NMC, 20.0, 85.0),
            (Chemistry.LEADACID, 30.0, 80.0),
            (Chemistry.OTHER, 20.0, 85.0),
        ],
    )
    def test_comfort_window_per_chemistry(
        self,
        chemistry: Chemistry,
        expected_min: float,
        expected_max: float,
        ecoflow_device: Device,
    ) -> None:
        from dataclasses import replace
        from custom_components.solarbalance.core.models import BatteryRole

        # Rebuild device with the target chemistry
        new_battery = replace(ecoflow_device.battery, chemistry=chemistry)  # type: ignore[union-attr]
        device = replace(ecoflow_device, battery=new_battery)

        strat = LongevityStrategy([device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)

        target = decision.battery_targets[device.name]
        assert target.soc_min_pct == pytest.approx(expected_min)
        assert target.soc_max_pct == pytest.approx(expected_max)

    def test_override_soc_min_and_max(self, ecoflow_device: Device) -> None:
        strat = LongevityStrategy(
            [ecoflow_device], loads=[], override_soc_min_pct=25.0, override_soc_max_pct=88.0
        )
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        target = decision.battery_targets[ecoflow_device.name]
        assert target.soc_min_pct == pytest.approx(25.0)
        assert target.soc_max_pct == pytest.approx(88.0)

    def test_longevity_window_never_widens_absolute_bounds(self, ecoflow_device: Device) -> None:
        # Default ecoflow soc_min=10, soc_max=95. Longevity LiFePO4 = 20-90.
        # Longevity should win (narrower).
        strat = LongevityStrategy([ecoflow_device], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        target = decision.battery_targets[ecoflow_device.name]
        # Effective = max(20,10)=20, min(90,95)=90
        assert target.soc_min_pct == 20.0
        assert target.soc_max_pct == 90.0

    def test_no_batteries_returns_empty_targets(self) -> None:
        from custom_components.solarbalance.core.models import (
            MpptRole, Device as Dev,
        )
        mppt_only = Dev(name="mppt", mppt=MpptRole(peak_power_w=1000, power_entity="s.pv"))
        strat = LongevityStrategy([mppt_only], loads=[])
        snap = make_snapshot(grid_w=0.0)
        decision = strat.compute(snap)
        assert decision.battery_targets == {}
