"""Tests for the learned hour-of-day consumption profile."""

from custom_components.solarbalance.core.consumption_profile import ConsumptionProfile


def test_unlearned_hour_predicts_none() -> None:
    assert ConsumptionProfile().predict(8) is None


def test_hour_mean_is_committed_on_rollover() -> None:
    p = ConsumptionProfile()
    # Two samples in hour 8; the bucket is set when hour rolls over.
    p.observe(8, 200.0)
    p.observe(8, 400.0)
    assert p.predict(8) is None  # not committed yet (still in hour 8)
    p.observe(9, 100.0)  # rollover → commits hour 8 = mean(200,400) = 300
    assert p.predict(8) == 300.0


def test_cross_day_ema_blends_days() -> None:
    p = ConsumptionProfile(day_alpha=0.5)
    p.observe(8, 300.0)
    p.observe(9, 0.0)  # commit hour 8 = 300
    assert p.predict(8) == 300.0
    # Next "day": hour 8 sees 500 → EMA 300 + 0.5*(500-300) = 400
    p.observe(8, 500.0)
    p.observe(9, 0.0)  # commit hour 8 again
    assert p.predict(8) == 400.0


def test_by_hour_fills_unknown_with_fallback() -> None:
    p = ConsumptionProfile()
    p.observe(8, 250.0)
    p.observe(9, 0.0)  # commit hour 8 = 250
    by_hour = p.by_hour(fallback_w=120.0)
    assert len(by_hour) == 24
    assert by_hour[8] == 250.0
    assert by_hour[0] == 120.0  # never learned → fallback
    assert by_hour[9] == 120.0  # still accumulating (not committed) → fallback


def test_seed_sets_bucket_directly() -> None:
    p = ConsumptionProfile()
    p.seed(7, 800.0)
    assert p.predict(7) == 800.0
    assert p.learned_hours == 1


def test_roundtrip_serialisation() -> None:
    p = ConsumptionProfile(day_alpha=0.4)
    p.seed(6, 150.0)
    p.seed(18, 900.0)
    restored = ConsumptionProfile.from_dict(p.to_dict())
    assert restored.day_alpha == 0.4
    assert restored.predict(6) == 150.0
    assert restored.predict(18) == 900.0
    assert restored.learned_hours == 2


def test_from_dict_tolerates_garbage() -> None:
    assert ConsumptionProfile.from_dict({}).learned_hours == 0
    assert ConsumptionProfile.from_dict({"buckets": "nope"}).learned_hours == 0
