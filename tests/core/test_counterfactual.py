"""Tests for the counterfactual: orchestration measured against plain self-consumption."""

from datetime import date, datetime, timedelta

from custom_components.solarbalance.core.counterfactual import Counterfactual

_DAY = date(2026, 7, 24)
_T0 = datetime(2026, 7, 24, 6, 0)


def _fleet(**kw) -> Counterfactual:
    base = {
        "usable_capacity_kwh": 6.0,
        "max_charge_w": 2000.0,
        "max_discharge_w": 2000.0,
        "round_trip": 1.0,  # lossless unless a test is about losses
    }
    base.update(kw)
    return Counterfactual(**base)


def _feed(
    cf: Counterfactual,
    ticks: list[tuple[float, float, float]],
    *,
    stored_kwh: float = 3.0,
    step_s: int = 60,
    import_price: float | None = 0.25,
    export_price: float | None = 0.10,
    start: datetime = _T0,
) -> None:
    """Feed ``(pv_w, grid_w, battery_w)`` samples; ``stored_kwh`` anchors the real fleet."""
    now = start
    cf.update(
        now=now,
        local_date=_DAY,
        pv_w=0.0,
        grid_w=0.0,
        battery_w=0.0,
        stored_kwh=stored_kwh,
        import_price=import_price,
        export_price=export_price,
    )
    for pv_w, grid_w, battery_w in ticks:
        now += timedelta(seconds=step_s)
        stored_kwh += battery_w * (step_s / 3600.0) / 1000.0
        stored_kwh = max(0.0, min(cf.usable_capacity_kwh, stored_kwh))
        cf.update(
            now=now,
            local_date=_DAY,
            pv_w=pv_w,
            grid_w=grid_w,
            battery_w=battery_w,
            stored_kwh=stored_kwh,
            import_price=import_price,
            export_price=export_price,
        )


def test_a_system_doing_exactly_what_the_naive_one_would_shows_no_gain() -> None:
    """The load-bearing sanity check.

    If the real fleet already charges every watt of surplus, orchestration adds
    nothing and the figure must say so. A comparison that flatters itself here
    would flatter itself everywhere.
    """
    cf = _fleet()
    # 1200 W of PV, 400 W house, fleet absorbing the whole 800 W surplus: grid at 0.
    _feed(cf, [(1200.0, 0.0, 800.0)] * 60)

    res = cf.result()
    assert abs(res.savings_eur) < 0.005
    assert abs(res.actual_import_kwh - res.naive_import_kwh) < 0.01


def test_exporting_what_a_battery_could_have_stored_shows_up_as_a_loss() -> None:
    """The shadow is not a rubber stamp: it must be able to beat the real system."""
    cf = _fleet()
    # Same 800 W surplus, but the real fleet sits idle and it all goes to the grid.
    _feed(cf, [(1200.0, -800.0, 0.0)] * 60)

    res = cf.result()
    assert res.savings_eur < 0.0, "idling through a surplus is worse than self-consuming"
    assert res.naive_export_kwh < res.actual_export_kwh


def test_deferring_a_discharge_is_neutral_under_a_flat_tariff() -> None:
    """A consequence of settling the stored energy, and a true one.

    On a flat tariff a kilowatt-hour kept is worth exactly the import it will
    avoid later, so choosing *when* to spend it earns nothing. The value of the
    battery comes from absorbing solar that would otherwise leave at export
    price — and this figure must not pretend otherwise.
    """
    spent = _fleet()
    _feed(spent, [(0.0, 0.0, -900.0)] * 60)  # real fleet covers the house

    held = _fleet()
    _feed(held, [(0.0, 900.0, 0.0)] * 60)  # real fleet holds, house imports

    assert abs(spent.result().savings_eur) < 0.02
    assert abs(held.result().savings_eur) < 0.02
    # The bill really is worse; it is the retained charge that makes it a wash.
    assert held.result().actual_cost_eur > spent.result().actual_cost_eur
    assert held.result().stored_delta_kwh > 0.8


def test_spending_the_battery_in_the_expensive_hour_is_worth_real_money() -> None:
    """Where the orchestration actually earns its keep, and the shadow cannot.

    The shadow spends its charge on the first deficit it meets. Holding it for
    the peak instead leaves the shadow importing at the expensive rate while the
    real fleet covers itself.
    """
    cf = _fleet()
    stored = 1.0
    now = _T0
    cf.update(
        now=now,
        local_date=_DAY,
        pv_w=0.0,
        grid_w=0.0,
        battery_w=0.0,
        stored_kwh=stored,
        import_price=0.10,
        export_price=0.0,
    )
    # Cheap hour: the real fleet holds its charge and imports; the shadow drains.
    for _ in range(60):
        now += timedelta(minutes=1)
        cf.update(
            now=now,
            local_date=_DAY,
            pv_w=0.0,
            grid_w=900.0,
            battery_w=0.0,
            stored_kwh=stored,
            import_price=0.10,
            export_price=0.0,
        )
    # Peak hour: the real fleet covers the house from the charge it kept.
    for _ in range(60):
        now += timedelta(minutes=1)
        stored = max(0.0, stored - 900.0 / 60.0 / 1000.0)
        cf.update(
            now=now,
            local_date=_DAY,
            pv_w=0.0,
            grid_w=0.0,
            battery_w=-900.0,
            stored_kwh=stored,
            import_price=0.40,
            export_price=0.0,
        )

    res = cf.result()
    assert res.naive_cost_eur > res.actual_cost_eur, "the shadow paid peak price for its haste"
    assert res.savings_eur > 0.15


def test_energy_held_back_is_settled_not_written_off() -> None:
    """Why the evening reserve does not read as a loss all afternoon.

    Refusing to discharge costs money *now* and saves it later. Valuing the charge
    each scenario still holds is what stops the figure from punishing every
    mechanism whose payoff is later in the day.
    """
    cf = _fleet()
    # The house draws 900 W; the real fleet holds its charge and imports instead,
    # while the shadow spends its battery.
    _feed(cf, [(0.0, 900.0, 0.0)] * 60, stored_kwh=3.0)

    res = cf.result()
    assert res.stored_delta_kwh > 0.8, "the real fleet kept roughly the kWh it did not spend"
    # Unsettled the day looks like a straight loss; settled, it is nearly a wash.
    unsettled = res.naive_cost_eur - res.actual_cost_eur
    assert unsettled < -0.15
    assert res.savings_eur > unsettled + 0.15


def test_the_shadow_respects_the_capacity_it_was_given() -> None:
    """A shadow with an infinite battery would make every real system look bad."""
    cf = _fleet(usable_capacity_kwh=1.0)
    _feed(cf, [(3000.0, -2600.0, 0.0)] * 120, stored_kwh=0.0)

    assert cf.naive_stored_kwh <= 1.0 + 1e-9
    assert cf.result().naive_export_kwh > 0.0, "a full shadow battery must spill too"


def test_the_shadow_respects_the_power_limit_it_was_given() -> None:
    cf = _fleet(max_charge_w=500.0)
    _feed(cf, [(3000.0, -2600.0, 0.0)] * 60, stored_kwh=0.0)

    # One hour at 500 W, not at the 2600 W the surplus offered.
    assert abs(cf.naive_stored_kwh - 0.5) < 0.02


def test_the_shadow_never_charges_from_the_grid() -> None:
    """Plain self-consumption is the baseline; grid charging is orchestration."""
    cf = _fleet()
    _feed(cf, [(0.0, 800.0, 800.0)] * 60, stored_kwh=1.0)

    assert cf.naive_stored_kwh <= 1.0 + 1e-9


def test_round_trip_losses_are_charged_to_the_shadow_too() -> None:
    """A lossless shadow would be a straw man that no real fleet could match."""
    lossless = _fleet(round_trip=1.0)
    lossy = _fleet(round_trip=0.81)  # 0.9 on each leg
    for cf in (lossless, lossy):
        _feed(cf, [(1400.0, 0.0, 1000.0)] * 60, stored_kwh=0.0)

    assert lossy.naive_stored_kwh < lossless.naive_stored_kwh * 0.95


def test_both_scenarios_face_the_same_house() -> None:
    """The comparison is only honest if neither side gets an easier day."""
    cf = _fleet()
    # PV 1000, grid +200 import, fleet discharging 300 -> house = 1000+200-(-300) = 1500.
    _feed(cf, [(1000.0, 200.0, -300.0)] * 30)

    # The shadow saw a 500 W deficit and covered it from its own battery, so it
    # imported nothing while the real one imported 200 W.
    res = cf.result()
    assert res.naive_import_kwh < res.actual_import_kwh


def test_a_long_gap_re_anchors_instead_of_inventing_a_tick() -> None:
    """A restart must not be billed to either scenario."""
    cf = _fleet()
    _feed(cf, [(1200.0, 0.0, 800.0)] * 10)
    before = cf.result()

    late = _T0 + timedelta(hours=3)
    cf.update(
        now=late,
        local_date=_DAY,
        pv_w=1200.0,
        grid_w=0.0,
        battery_w=800.0,
        stored_kwh=5.0,
        import_price=0.25,
        export_price=0.10,
    )
    after = cf.result()
    assert after.actual_import_kwh == before.actual_import_kwh
    assert after.naive_import_kwh == before.naive_import_kwh
    assert cf.naive_stored_kwh == 5.0, "the shadow is re-anchored on the real fleet"


def test_a_new_day_starts_both_scenarios_level() -> None:
    cf = _fleet()
    _feed(cf, [(1200.0, -800.0, 0.0)] * 60)
    assert cf.result().savings_eur != 0.0

    cf.update(
        now=_T0 + timedelta(days=1),
        local_date=date(2026, 7, 25),
        pv_w=0.0,
        grid_w=0.0,
        battery_w=0.0,
        stored_kwh=2.5,
        import_price=0.25,
        export_price=0.10,
    )
    res = cf.result()
    assert res.actual_cost_eur == 0.0
    assert res.naive_cost_eur == 0.0
    assert res.stored_delta_kwh == 0.0
    assert cf.day == date(2026, 7, 25)


def test_a_missing_price_advances_the_physics_without_inventing_a_bill() -> None:
    cf = _fleet()
    _feed(cf, [(1200.0, -800.0, 0.0)] * 60, import_price=None, export_price=None)

    res = cf.result()
    assert res.actual_cost_eur == 0.0
    assert res.naive_cost_eur == 0.0
    assert cf.naive_stored_kwh > 0.0, "the shadow battery still charged"


def test_no_fleet_means_the_two_scenarios_are_the_same_scenario() -> None:
    cf = _fleet(usable_capacity_kwh=0.0, max_charge_w=0.0, max_discharge_w=0.0)
    _feed(cf, [(400.0, 500.0, 0.0)] * 30, stored_kwh=0.0)

    res = cf.result()
    assert abs(res.savings_eur) < 1e-6


def test_the_running_day_survives_a_restart() -> None:
    cf = _fleet()
    _feed(cf, [(1200.0, -800.0, 0.0)] * 30)
    before = cf.result()

    restored = _fleet()
    restored.restore(cf.to_dict())
    assert restored.result() == before
    assert restored.day == _DAY


def test_a_payload_from_another_day_is_not_carried_forward() -> None:
    cf = _fleet()
    _feed(cf, [(1200.0, -800.0, 0.0)] * 30)
    payload = cf.to_dict()

    restored = _fleet()
    restored.restore(payload)
    restored.update(
        now=_T0 + timedelta(days=1),
        local_date=date(2026, 7, 25),
        pv_w=0.0,
        grid_w=0.0,
        battery_w=0.0,
        stored_kwh=2.0,
        import_price=0.25,
        export_price=0.10,
    )
    assert restored.result().naive_cost_eur == 0.0


def test_a_malformed_payload_leaves_the_day_untouched() -> None:
    cf = _fleet()
    cf.restore({"day": "not-a-date", "naive_cost_eur": 99.0})
    assert cf.day is None
    assert cf.result().naive_cost_eur == 0.0
