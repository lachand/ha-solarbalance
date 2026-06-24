"""Tests for the learned consumption profile (by segment & hour)."""

from custom_components.solarbalance.core.consumption_profile import (
    ConsumptionProfile,
    mean_by_hour,
    segment_for,
)


def test_segment_for_splits_weekday_and_weekend() -> None:
    assert segment_for(0) == "weekday"  # Monday
    assert segment_for(4) == "weekday"  # Friday
    assert segment_for(5) == "weekend"  # Saturday
    assert segment_for(6) == "weekend"  # Sunday


def test_unlearned_hour_predicts_none() -> None:
    assert ConsumptionProfile().predict("weekday", 8) is None


def test_hour_mean_is_committed_on_rollover() -> None:
    p = ConsumptionProfile()
    p.observe("weekday", 8, 200.0)
    p.observe("weekday", 8, 400.0)
    assert p.predict("weekday", 8) is None  # not committed yet
    p.observe("weekday", 9, 100.0)  # rollover → commit hour 8 = mean(200,400)=300
    assert p.predict("weekday", 8) == 300.0


def test_segments_are_independent() -> None:
    p = ConsumptionProfile()
    p.observe("weekday", 8, 300.0)
    p.observe("weekend", 8, 900.0)  # rollover (segment change) commits weekday 8
    p.observe("weekend", 9, 0.0)  # commit weekend 8
    assert p.predict("weekday", 8) == 300.0
    assert p.predict("weekend", 8) == 900.0


def test_cross_day_ema_blends_days() -> None:
    p = ConsumptionProfile(day_alpha=0.5)
    p.observe("weekday", 8, 300.0)
    p.observe("weekday", 9, 0.0)  # commit hour 8 = 300
    p.observe("weekday", 8, 500.0)
    p.observe("weekday", 9, 0.0)  # commit hour 8 → 300 + 0.5*(500-300) = 400
    assert p.predict("weekday", 8) == 400.0


def test_by_hour_fills_unknown_with_fallback() -> None:
    p = ConsumptionProfile()
    p.observe("weekday", 8, 250.0)
    p.observe("weekday", 9, 0.0)  # commit hour 8 = 250
    by_hour = p.by_hour("weekday", fallback_w=120.0)
    assert len(by_hour) == 24
    assert by_hour[8] == 250.0
    assert by_hour[0] == 120.0  # unlearned → fallback


def test_seed_missing_only_fills_unlearned_hours() -> None:
    p = ConsumptionProfile()
    p.seed("weekday", 8, 999.0)
    seeded = p.seed_missing("weekday", {8: 100.0, 9: 250.0})
    assert seeded == 1  # only hour 9 filled
    assert p.predict("weekday", 8) == 999.0
    assert p.predict("weekday", 9) == 250.0


def test_mean_by_hour_averages_per_hour() -> None:
    assert mean_by_hour([(8, 200.0), (8, 400.0), (20, 1000.0)]) == {8: 300.0, 20: 1000.0}


def test_roundtrip_serialisation() -> None:
    p = ConsumptionProfile(day_alpha=0.4)
    p.seed("weekday", 6, 150.0)
    p.seed("weekend", 18, 900.0)
    restored = ConsumptionProfile.from_dict(p.to_dict())
    assert restored.day_alpha == 0.4
    assert restored.predict("weekday", 6) == 150.0
    assert restored.predict("weekend", 18) == 900.0
    assert restored.learned_hours == 2


def test_from_dict_migrates_old_flat_format() -> None:
    flat = [None] * 24
    flat[7] = 800.0
    restored = ConsumptionProfile.from_dict({"buckets": flat})
    # Old single-segment payload is copied into both segments.
    assert restored.predict("weekday", 7) == 800.0
    assert restored.predict("weekend", 7) == 800.0


def test_from_dict_tolerates_garbage() -> None:
    assert ConsumptionProfile.from_dict({}).learned_hours == 0
    assert ConsumptionProfile.from_dict({"buckets": "nope"}).learned_hours == 0
