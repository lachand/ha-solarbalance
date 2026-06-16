"""Tests for the load dispatch controller."""

from datetime import UTC, datetime

import pytest

from custom_components.solarbalance.core.controllers.load_dispatch import (
    LoadDispatchController,
)
from custom_components.solarbalance.core.models import (
    Load,
    LoadControlType,
    LoadState,
    LoadStep,
    TimeWindow,
)


def _on_off_load(name: str = "boiler", priority: int = 1, power: int = 2000) -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.ON_OFF,
        priority=priority,
        nominal_power_w=power,
        switch_entity=f"switch.{name}",
    )


def _modulating_load(
    name: str = "ev", priority: int = 1, min_w: int = 1380, max_w: int = 7360
) -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.MODULATING,
        priority=priority,
        min_power_w=min_w,
        max_power_w=max_w,
        step_w=230,
        power_set_entity="number.ev_power",
    )


def _stepped_load(name: str = "fan", priority: int = 1) -> Load:
    return Load(
        name=name,
        control_type=LoadControlType.STEPPED,
        priority=priority,
        steps=(
            LoadStep(level=1, power_w=100),
            LoadStep(level=2, power_w=200),
            LoadStep(level=3, power_w=300),
        ),
        level_entity="number.fan_level",
    )


def _now() -> datetime:
    return datetime(2026, 5, 4, 14, 0, tzinfo=UTC)


class TestLoadDispatchController:
    def test_activates_on_off_load_within_surplus(self) -> None:
        ctrl = LoadDispatchController([_on_off_load(power=1000)])
        result = ctrl.dispatch(available_surplus_w=2000.0, states={}, now=_now())
        cmd = result.commands[0]
        assert cmd.on is True
        assert result.allocated_w == pytest.approx(1000.0)

    def test_does_not_activate_if_surplus_insufficient(self) -> None:
        ctrl = LoadDispatchController([_on_off_load(power=2000)])
        result = ctrl.dispatch(available_surplus_w=500.0, states={}, now=_now())
        assert result.commands[0].on is False
        assert result.allocated_w == pytest.approx(0.0)
        assert result.unallocated_surplus_w == pytest.approx(500.0)

    def test_priority_order_respected(self) -> None:
        boiler = _on_off_load("boiler", priority=1, power=1500)
        ev = _on_off_load("ev", priority=2, power=1500)
        ctrl = LoadDispatchController([ev, boiler])  # deliberately reversed order
        result = ctrl.dispatch(available_surplus_w=2000.0, states={}, now=_now())
        cmds = {c.load_name: c for c in result.commands}
        # boiler (priority=1) should be on, ev (priority=2) off
        assert cmds["boiler"].on is True
        assert cmds["ev"].on is False

    def test_modulating_load_clamped_to_max(self) -> None:
        ctrl = LoadDispatchController([_modulating_load(min_w=1000, max_w=3000)])
        result = ctrl.dispatch(available_surplus_w=10000.0, states={}, now=_now())
        cmd = result.commands[0]
        assert cmd.on is True
        assert cmd.power_w is not None
        assert cmd.power_w <= 3000.0

    def test_modulating_load_off_below_min(self) -> None:
        ctrl = LoadDispatchController([_modulating_load(min_w=1380, max_w=7360)])
        result = ctrl.dispatch(available_surplus_w=500.0, states={}, now=_now())
        assert result.commands[0].on is False

    def test_stepped_load_picks_highest_fitting_step(self) -> None:
        ctrl = LoadDispatchController([_stepped_load()])
        result = ctrl.dispatch(available_surplus_w=250.0, states={}, now=_now())
        cmd = result.commands[0]
        assert cmd.on is True
        assert cmd.step_level == 2  # level 2 = 200W ≤ 250W, level 3 = 300W > 250W

    def test_time_window_excludes_load(self) -> None:
        load = Load(
            name="boiler",
            control_type=LoadControlType.ON_OFF,
            priority=1,
            nominal_power_w=2000,
            switch_entity="switch.boiler",
            time_window=TimeWindow(start="06:00", end="08:00"),
        )
        ctrl = LoadDispatchController([load])
        # _now() returns 14:00 which is outside 06:00-08:00
        result = ctrl.dispatch(available_surplus_w=5000.0, states={}, now=_now())
        assert result.commands[0].on is False

    def test_min_off_duration_prevents_restart(self) -> None:
        load = Load(
            name="boiler",
            control_type=LoadControlType.ON_OFF,
            priority=1,
            nominal_power_w=2000,
            switch_entity="switch.boiler",
            min_off_duration_s=300,
        )
        now = _now()
        from datetime import timedelta

        state = LoadState(
            name="boiler",
            actual_power_w=0.0,
            last_off_at=now - timedelta(seconds=60),  # only 60s ago, guard is 300s
        )
        ctrl = LoadDispatchController([load])
        result = ctrl.dispatch(available_surplus_w=5000.0, states={"boiler": state}, now=now)
        assert result.commands[0].on is False

    def test_zero_surplus_turns_off_interruptible_load(self) -> None:
        load = _on_off_load(power=1500)
        state = LoadState(name="boiler", actual_power_w=1500.0)
        ctrl = LoadDispatchController([load])
        result = ctrl.dispatch(available_surplus_w=0.0, states={"boiler": state}, now=_now())
        assert result.commands[0].on is False
