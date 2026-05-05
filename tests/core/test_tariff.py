"""Tests for the generic tariff model."""

from datetime import datetime, time, UTC

import pytest

from custom_components.solarbalance.core.tariff import (
    TariffConfig,
    TariffSlot,
    make_hchp_tariff,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 4, hour, minute, tzinfo=UTC)


class TestTariffSlot:
    @pytest.mark.parametrize(
        ("start", "end", "query_hour", "expected"),
        [
            (6, 22, 10, True),   # inside daytime window
            (6, 22, 5, False),   # before start
            (6, 22, 22, False),  # end is exclusive
            (22, 6, 23, True),   # overnight: late evening
            (22, 6, 0, True),    # overnight: after midnight
            (22, 6, 6, False),   # overnight: end is exclusive
        ],
    )
    def test_applies_at(
        self, start: int, end: int, query_hour: int, expected: bool
    ) -> None:
        slot = TariffSlot(
            name="test",
            start=time(start, 0),
            end=time(end, 0),
            import_price=0.25,
        )
        assert slot.applies_at(_dt(query_hour)) is expected

    def test_weekday_filter_matches(self) -> None:
        # datetime(2026, 5, 4) is a Monday (weekday=0)
        slot = TariffSlot(
            name="weekday",
            start=time(0, 0),
            end=time(23, 59),
            import_price=0.20,
            weekdays=(0, 1, 2, 3, 4),  # Mon–Fri
        )
        assert slot.applies_at(_dt(12)) is True

    def test_weekday_filter_no_match(self) -> None:
        slot = TariffSlot(
            name="weekend",
            start=time(0, 0),
            end=time(23, 59),
            import_price=0.18,
            weekdays=(5, 6),  # Sat–Sun
        )
        assert slot.applies_at(_dt(12)) is False  # 2026-05-04 is Monday


class TestTariffConfig:
    def test_first_matching_slot_wins(self) -> None:
        cfg = TariffConfig(slots=[
            TariffSlot("hc", time(0), time(6), import_price=0.15),
            TariffSlot("hp", time(6), time(22), import_price=0.25),
        ])
        assert cfg.current_import_price(_dt(3)) == pytest.approx(0.15)
        assert cfg.current_import_price(_dt(10)) == pytest.approx(0.25)

    def test_no_match_returns_default(self) -> None:
        cfg = TariffConfig(
            slots=[TariffSlot("hc", time(0), time(6), import_price=0.15)],
            default_import_price=0.20,
        )
        assert cfg.current_import_price(_dt(10)) == pytest.approx(0.20)

    def test_no_match_no_default_returns_none(self) -> None:
        cfg = TariffConfig(slots=[TariffSlot("hc", time(0), time(6), import_price=0.15)])
        assert cfg.current_import_price(_dt(10)) is None

    def test_is_cheap_window(self) -> None:
        cfg = TariffConfig(slots=[TariffSlot("hc", time(0), time(6), import_price=0.15)])
        assert cfg.is_cheap_window(_dt(2), threshold=0.17) is True
        assert cfg.is_cheap_window(_dt(2), threshold=0.14) is False

    def test_is_expensive_window(self) -> None:
        cfg = TariffConfig(slots=[TariffSlot("hp", time(6), time(22), import_price=0.25)])
        assert cfg.is_expensive_window(_dt(10), threshold=0.20) is True
        assert cfg.is_expensive_window(_dt(10), threshold=0.30) is False

    def test_is_cheap_returns_false_when_no_price(self) -> None:
        cfg = TariffConfig()
        assert cfg.is_cheap_window(_dt(10), threshold=0.20) is False

    def test_is_expensive_returns_false_when_no_price(self) -> None:
        cfg = TariffConfig()
        assert cfg.is_expensive_window(_dt(10), threshold=0.20) is False


class TestMakeHchpTariff:
    def test_two_level_hchp(self) -> None:
        tariff = make_hchp_tariff(
            [("00:00", "06:00", 0.15), ("06:00", "22:00", 0.25)],
            export_price=0.13,
        )
        assert tariff.current_import_price(_dt(3)) == pytest.approx(0.15)
        assert tariff.current_import_price(_dt(10)) == pytest.approx(0.25)
        assert tariff.current_export_price(_dt(3)) == pytest.approx(0.13)
