"""Tests for the generic tariff model."""

from datetime import UTC, datetime, time

import pytest

from custom_components.solarbalance.core.tariff import (
    TariffConfig,
    TariffSlot,
    TempoColor,
    build_tariff,
    make_hchp_tariff,
    parse_tempo_color,
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
            weekdays=(0, 1, 2, 3, 4),  # Mon-Fri
        )
        assert slot.applies_at(_dt(12)) is True

    def test_weekday_filter_no_match(self) -> None:
        slot = TariffSlot(
            name="weekend",
            start=time(0, 0),
            end=time(23, 59),
            import_price=0.18,
            weekdays=(5, 6),  # Sat-Sun
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

    def test_end_24h_raises_value_error(self) -> None:
        """'24:00' as end time creates a permanently-active slot; reject it early."""
        with pytest.raises(ValueError, match="24:00"):
            make_hchp_tariff([("22:00", "24:00", 0.15)])


class TestParseTempoColor:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("Rouge", TempoColor.RED),
            ("red", TempoColor.RED),
            ("BLANC", TempoColor.WHITE),
            ("Bleu", TempoColor.BLUE),
            ("3", TempoColor.RED),
            (None, TempoColor.UNKNOWN),
            ("unknown", TempoColor.UNKNOWN),
        ],
    )
    def test_mapping(self, state: str | None, expected: TempoColor) -> None:
        assert parse_tempo_color(state) is expected


class TestBuildTariff:
    def test_flat(self) -> None:
        t = build_tariff({"type": "flat", "import_price": 0.25, "export_price": 0.10})
        assert t.current_import_price(_dt(12)) == pytest.approx(0.25)
        assert t.current_export_price(_dt(12)) == pytest.approx(0.10)

    def test_hc_hp(self) -> None:
        t = build_tariff(
            {
                "type": "hc_hp",
                "export_price": 0.13,
                "slots": [
                    {"start": "22:00", "end": "06:00", "price": 0.20},
                    {"start": "06:00", "end": "22:00", "price": 0.27},
                ],
            }
        )
        assert t.current_import_price(_dt(3)) == pytest.approx(0.20)
        assert t.current_import_price(_dt(12)) == pytest.approx(0.27)

    def test_tempo_red_hp_is_expensive(self) -> None:
        t = build_tariff(
            {
                "type": "tempo",
                "export_price": 0.13,
                "prices": {"red": {"hc": 0.16, "hp": 0.76}},
            },
            color_provider=lambda _dt: TempoColor.RED,
        )
        # 12:00 is HP for the red day -> expensive.
        assert t.current_import_price(_dt(12)) == pytest.approx(0.76)
        assert t.is_expensive_window(_dt(12), threshold=0.25) is True
        # 03:00 is HC -> cheaper.
        assert t.current_import_price(_dt(3)) == pytest.approx(0.16)

    def test_tempo_requires_color_provider(self) -> None:
        with pytest.raises(ValueError, match="color_provider"):
            build_tariff({"type": "tempo"})

    def test_tempo_off_peak_window(self) -> None:
        t = build_tariff({"type": "tempo"}, color_provider=lambda _dt: TempoColor.BLUE)
        assert t.is_off_peak(_dt(3)) is True  # 03:00 in HC (22:00-06:00)
        assert t.is_off_peak(_dt(23)) is True  # 23:00 in HC
        assert t.is_off_peak(_dt(12)) is False  # midday is HP
