"""Tests for the per-cycle appliance cost estimate."""

from custom_components.solarbalance.core.appliance_cost import cycle_cost


def test_no_tariff_means_no_cost() -> None:
    assert cycle_cost(energy_kwh=1.0, import_price_eur=None, solar_fraction_now=0.5) is None


def test_a_fully_solar_cycle_costs_nothing_now() -> None:
    c = cycle_cost(energy_kwh=1.0, import_price_eur=0.25, solar_fraction_now=1.0)
    assert c is not None
    assert c.now_eur == 0.0
    assert c.grid_only_eur == 0.25  # the no-solar baseline is unchanged


def test_a_half_solar_cycle_costs_half_the_grid_price() -> None:
    c = cycle_cost(energy_kwh=2.0, import_price_eur=0.30, solar_fraction_now=0.5)
    assert c is not None
    assert abs(c.now_eur - 0.30) < 1e-9  # 2 kWh * 50 % grid * 0.30
    assert abs(c.grid_only_eur - 0.60) < 1e-9


def test_waiting_for_a_sunnier_hour_is_valued() -> None:
    c = cycle_cost(
        energy_kwh=2.0,
        import_price_eur=0.25,
        solar_fraction_now=0.2,
        solar_fraction_best=0.9,
    )
    assert c is not None
    assert c.best_eur < c.now_eur
    assert c.saving_by_waiting_eur > 0.0
    assert abs(c.saving_by_waiting_eur - (c.now_eur - c.best_eur)) < 1e-9


def test_a_missing_solar_share_is_treated_as_no_sun() -> None:
    c = cycle_cost(energy_kwh=1.0, import_price_eur=0.25, solar_fraction_now=None)
    assert c is not None
    assert c.now_eur == c.grid_only_eur  # nothing covered, full grid cost


def test_without_a_best_hour_there_is_no_saving_from_waiting() -> None:
    c = cycle_cost(energy_kwh=1.0, import_price_eur=0.25, solar_fraction_now=0.4)
    assert c is not None
    assert c.saving_by_waiting_eur == 0.0
    assert c.best_eur == c.now_eur


def test_a_zero_energy_cycle_has_no_cost() -> None:
    assert cycle_cost(energy_kwh=0.0, import_price_eur=0.25, solar_fraction_now=0.5) is None
