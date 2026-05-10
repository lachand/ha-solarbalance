"""Tests for TempoTariff and EpexSpotTariff."""

from datetime import UTC, datetime

import pytest

from custom_components.solarbalance.core.tariff import (
    EpexSpotTariff,
    TempoColor,
    TempoSlotPrices,
    TempoTariff,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    """Build a UTC datetime on an arbitrary Monday."""
    return datetime(2026, 5, 4, hour, minute, tzinfo=UTC)


class TestTempoTariff:
    @pytest.mark.parametrize(
        ("hour", "expected_slot"),
        [
            (1, "hc"),  # 01:00 is in HC window (22:00 → 06:00)
            (5, "hc"),  # 05:00 still HC
            (6, "hp"),  # 06:00 starts HP
            (12, "hp"),  # noon is HP
            (22, "hc"),  # 22:00 starts HC again
        ],
    )
    def test_blue_day_hc_hp_detection(self, hour: int, expected_slot: str) -> None:
        tariff = TempoTariff(lambda _dt: TempoColor.BLUE)
        price = tariff.current_import_price(_dt(hour))
        prices = tariff._prices[TempoColor.BLUE]
        expected = prices.hc_price if expected_slot == "hc" else prices.hp_price
        assert price == pytest.approx(expected)

    @pytest.mark.parametrize("color", [TempoColor.BLUE, TempoColor.WHITE, TempoColor.RED])
    def test_hp_price_higher_than_hc_for_all_colours(self, color: TempoColor) -> None:
        tariff = TempoTariff(lambda _dt: color)
        hc = tariff.current_import_price(_dt(3))  # HC
        hp = tariff.current_import_price(_dt(12))  # HP
        assert hp is not None and hc is not None
        assert hp > hc

    def test_red_day_hp_much_higher_than_blue(self) -> None:
        tariff = TempoTariff(lambda _dt: TempoColor.RED)
        price = tariff.current_import_price(_dt(12))
        assert price is not None and price > 0.5

    def test_unknown_colour_returns_none(self) -> None:
        tariff = TempoTariff(lambda _dt: TempoColor.UNKNOWN)
        assert tariff.current_import_price(_dt(12)) is None

    def test_export_price_constant_regardless_of_colour(self) -> None:
        tariff = TempoTariff(lambda _dt: TempoColor.RED, export_price=0.13)
        assert tariff.current_export_price(_dt(12)) == pytest.approx(0.13)

    def test_custom_prices_override_defaults(self) -> None:
        custom = {TempoColor.BLUE: TempoSlotPrices(hc_price=0.05, hp_price=0.10)}
        tariff = TempoTariff(lambda _dt: TempoColor.BLUE, prices=custom)
        assert tariff.current_import_price(_dt(3)) == pytest.approx(0.05)
        assert tariff.current_import_price(_dt(12)) == pytest.approx(0.10)

    def test_as_tariff_config_snapshots_current_prices(self) -> None:
        tariff = TempoTariff(lambda _dt: TempoColor.BLUE)
        dt = _dt(12)
        cfg = tariff.as_tariff_config(dt)
        assert cfg.default_import_price == tariff.current_import_price(dt)


class TestEpexSpotTariff:
    def test_markup_added_to_spot_price(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: 0.10, markup=0.08)
        assert tariff.current_import_price(_dt(12)) == pytest.approx(0.18)

    def test_none_provider_returns_none(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: None, markup=0.08)
        assert tariff.current_import_price(_dt(12)) is None

    def test_price_cap_clips_high_values(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: 2.0, markup=0.0, price_cap=0.50)
        assert tariff.current_import_price(_dt(12)) == pytest.approx(0.50)

    def test_price_floor_clips_negative_spot(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: -0.05, markup=0.0, price_floor=0.0)
        assert tariff.current_import_price(_dt(12)) == pytest.approx(0.0)

    def test_export_price_constant(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: 0.10, markup=0.08, export_price=0.07)
        assert tariff.current_export_price(_dt(12)) == pytest.approx(0.07)

    def test_as_tariff_config_snapshots_prices(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: 0.15, markup=0.05, export_price=0.09)
        dt = _dt(9)
        cfg = tariff.as_tariff_config(dt)
        assert cfg.default_import_price == pytest.approx(0.20)
        assert cfg.default_export_price == pytest.approx(0.09)

    def test_both_cap_and_floor_apply(self) -> None:
        tariff = EpexSpotTariff(lambda _dt: 1.0, markup=0.0, price_cap=0.80, price_floor=0.05)
        assert tariff.current_import_price(_dt(0)) == pytest.approx(0.80)
