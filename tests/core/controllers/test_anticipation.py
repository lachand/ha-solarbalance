"""Tests for the anticipatory-curtailment controller (sink budget + pre-brake)."""

import math

from custom_components.solarbalance.core.controllers.anticipation import (
    SINK_CLOUD_BATTERY,
    SINK_CONTROLLABLE_BATTERY,
    SINK_LOAD,
    AnticipationInputs,
    Sink,
    SinkBudget,
    compute_sink_budget,
    evaluate_anticipation,
)

_HORIZON_S = 12 * 60.0  # 12 min, the default horizon


def _battery(absorb_w: float, headroom_kwh: float, name: str = "batt") -> Sink:
    return Sink(
        name=name,
        kind=SINK_CONTROLLABLE_BATTERY,
        absorb_w=absorb_w,
        headroom_kwh=headroom_kwh,
    )


def _load(absorb_w: float, name: str = "ev") -> Sink:
    return Sink(name=name, kind=SINK_LOAD, absorb_w=absorb_w, headroom_kwh=math.inf)


def _inputs(
    *,
    budget: SinkBudget,
    forecast_pv_w: float = 3000.0,
    consumption_w: float = 400.0,
    enabled: bool = True,
    forecast_available: bool = True,
    net_charge_w: float = 0.0,
    margin_w: float = 100.0,
) -> AnticipationInputs:
    return AnticipationInputs(
        enabled=enabled,
        forecast_available=forecast_available,
        forecast_pv_w=forecast_pv_w,
        predicted_consumption_w=consumption_w,
        budget=budget,
        current_net_charge_w=net_charge_w,
        margin_w=margin_w,
    )


# ----------------------------------------------------------------- sink budget


def test_roomy_battery_contributes_its_full_rate() -> None:
    # 2 kWh of headroom at 1500 W: it can sustain 1500 W well beyond the horizon.
    budget = compute_sink_budget([_battery(1500.0, 2.0)], horizon_s=_HORIZON_S)
    assert budget.total_absorb_w == 1500.0
    assert budget.instantaneous_absorb_w == 1500.0


def test_nearly_full_battery_collapses_before_it_is_full() -> None:
    # This is the whole point of the feature: the battery still *takes* 1500 W, but
    # only holds 0.05 kWh more — over 12 min that is worth 250 W, not 1500 W. The
    # brake therefore comes down while it is still charging, not once it is full.
    budget = compute_sink_budget([_battery(1500.0, 0.05)], horizon_s=_HORIZON_S)
    assert budget.total_absorb_w == 250.0  # 0.05 kWh / 0.2 h * 1000
    assert budget.instantaneous_absorb_w == 1500.0  # the reactive view, unchanged


def test_load_has_no_energy_ceiling_and_contributes_fully() -> None:
    budget = compute_sink_budget([_load(2000.0)], horizon_s=_HORIZON_S)
    assert budget.total_absorb_w == 2000.0
    assert budget.total_headroom_kwh == 0.0  # inf headroom is not summed


def test_budget_sums_batteries_cloud_and_loads_by_kind() -> None:
    sinks = [
        _battery(1000.0, 5.0, name="stream"),
        Sink(name="jackery", kind=SINK_CLOUD_BATTERY, absorb_w=600.0, headroom_kwh=3.0),
        _load(800.0),
    ]
    budget = compute_sink_budget(sinks, horizon_s=_HORIZON_S)
    assert budget.total_absorb_w == 2400.0
    assert budget.by_kind_w[SINK_CONTROLLABLE_BATTERY] == 1000.0
    assert budget.by_kind_w[SINK_CLOUD_BATTERY] == 600.0
    assert budget.by_kind_w[SINK_LOAD] == 800.0
    assert budget.total_headroom_kwh == 8.0


def test_empty_sinks_give_a_zero_budget() -> None:
    budget = compute_sink_budget([], horizon_s=_HORIZON_S)
    assert budget.total_absorb_w == 0.0
    assert budget.total_headroom_kwh == 0.0


# ------------------------------------------------------------------- decision


def test_no_pre_curtail_while_the_sinks_have_room() -> None:
    # 3000 W forecast, 400 W house, 3000 W of sinks → nothing to spill. Solar must
    # not be thrown away just because the batteries will eventually fill.
    budget = compute_sink_budget([_battery(3000.0, 5.0)], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget))
    assert r.active is False
    assert r.preemptive_limit_w is None
    assert r.reason == "sinks_have_room"


def test_pre_curtails_when_forecast_surplus_beats_the_budget() -> None:
    # Nearly-full battery: 250 W of effective budget against a 2600 W surplus.
    budget = compute_sink_budget([_battery(1500.0, 0.05)], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget, forecast_pv_w=3000.0, consumption_w=400.0))
    assert r.active is True
    assert r.reason == "anticipating"
    # Cap PV at what the house + its sinks actually absorb → nothing spills.
    assert r.preemptive_limit_w == 650.0  # 400 consumption + 250 budget
    assert r.forecast_surplus_w == 2600.0
    assert r.projected_export_w == 2350.0


def test_margin_absorbs_forecast_noise() -> None:
    # Surplus beats the budget by only 80 W — inside the 100 W margin, so no brake.
    budget = compute_sink_budget([_battery(2000.0, 5.0)], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(
        _inputs(budget=budget, forecast_pv_w=2480.0, consumption_w=400.0, margin_w=100.0)
    )
    assert r.projected_export_w == 80.0
    assert r.active is False
    assert r.reason == "sinks_have_room"


def test_pre_limit_never_forces_an_import() -> None:
    # Even with no sinks at all, the limit is never below what the house draws.
    budget = compute_sink_budget([], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget, forecast_pv_w=3000.0, consumption_w=400.0))
    assert r.active is True
    assert r.preemptive_limit_w == 400.0


def test_disabled_is_inert() -> None:
    budget = compute_sink_budget([], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget, enabled=False))
    assert r.active is False
    assert r.preemptive_limit_w is None
    assert r.reason == "disabled"


def test_without_a_forecast_it_stays_out_of_the_way() -> None:
    # No PV forecast entity configured → fall back to purely reactive curtailment.
    budget = compute_sink_budget([], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget, forecast_available=False))
    assert r.active is False
    assert r.preemptive_limit_w is None
    assert r.reason == "no_forecast"


def test_time_to_saturation_from_the_current_charge_rate() -> None:
    budget = compute_sink_budget([_battery(1500.0, 1.0)], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget, net_charge_w=1000.0))
    assert r.time_to_saturation_s == 3600.0  # 1 kWh at 1 kW → 1 h


def test_time_to_saturation_is_unknown_when_not_charging() -> None:
    budget = compute_sink_budget([_battery(1500.0, 1.0)], horizon_s=_HORIZON_S)
    r = evaluate_anticipation(_inputs(budget=budget, net_charge_w=0.0))
    assert r.time_to_saturation_s is None
