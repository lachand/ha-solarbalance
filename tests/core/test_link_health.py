"""Tests for the per-entity link health score."""

from custom_components.solarbalance.core.link_health import LinkHealth

_T0 = 1_753_300_000.0  # arbitrary epoch anchor; only differences matter
_TICK_S = 10.0


def _run(
    health: LinkHealth,
    key: str,
    ages: list[float | None],
    *,
    start_s: float = _T0,
    tick_s: float = _TICK_S,
) -> float:
    """Feed a sequence of per-tick ages; return the timestamp of the last one."""
    now = start_s
    for age in ages:
        health.observe(key, now, age)
        now += tick_s
    return now - tick_s


def test_a_link_that_always_answers_scores_full_marks() -> None:
    health = LinkHealth()
    end = _run(health, "pdl/power", [3.0] * 200)

    stats = health.stats("pdl/power", end)
    assert stats.available_pct == 100.0
    assert stats.score == 100.0
    assert stats.dropouts == 0
    assert stats.longest_gap_s == 0.0
    assert stats.verdict == "healthy"


def test_the_2026_07_24_meter_outage_is_visible_in_the_score() -> None:
    """The incident this module exists for.

    The PDL went silent 06:58 -> 07:36 and regulation was suspended through
    sunrise. Availability alone barely moves (38 min out of a day), so the score
    has to weigh the *shape* of the loss, not just its size.
    """
    health = LinkHealth()
    # ~3 h of watching, with one 38-minute hole in the middle.
    before = [4.0] * 360
    outage = [None] * int(38 * 60 / _TICK_S)
    after = [4.0] * 360
    end = _run(health, "pdl/power", before + outage + after)

    stats = health.stats("pdl/power", end)
    assert stats.dropouts == 1
    assert 2250 <= stats.longest_gap_s <= 2300  # 38 min, within one tick
    assert stats.available_pct > 75.0, "the outage is a small share of the samples"
    assert stats.verdict == "unreliable", "but it cost the whole morning, and must show"


def test_scattered_noise_is_not_judged_like_one_long_hole() -> None:
    """Same amount of missing data, very different consequence.

    A meter that drops one sample here and there is absorbed by the median filter;
    a meter that drops the same number of samples in one run stops the house
    regulating. The score has to separate them or it is not worth reading.
    """
    scattered = LinkHealth()
    burst = LinkHealth()

    pattern: list[float | None] = []
    for i in range(600):
        pattern.append(None if i % 10 == 0 else 4.0)  # 10 % missing, never twice running
    end_a = _run(scattered, "link", pattern)

    run: list[float | None] = [4.0] * 540 + [None] * 60  # same 10 %, all in one go
    end_b = _run(burst, "link", run)

    assert scattered.stats("link", end_a).available_pct == burst.stats("link", end_b).available_pct
    assert scattered.stats("link", end_a).score > burst.stats("link", end_b).score


def test_a_gap_still_running_is_already_counted() -> None:
    """An outage in progress is the one worth seeing.

    Closing the gap only when the link returns would hide precisely the case
    someone is staring at the dashboard for.
    """
    health = LinkHealth()
    end = _run(health, "cloud/soc", [4.0] * 60 + [None] * 120)

    stats = health.stats("cloud/soc", end)
    assert stats.longest_gap_s >= 1190.0
    assert stats.dropouts == 1


def test_dropouts_count_transitions_not_missing_samples() -> None:
    health = LinkHealth()
    end = _run(health, "link", [4.0] * 30 + [None] * 30 + [4.0] * 30 + [None] * 30 + [4.0] * 30)

    assert health.stats("link", end).dropouts == 2


def test_a_slow_but_never_absent_link_is_still_available() -> None:
    """Late is not the same as gone, as long as it stays inside the stale window."""
    health = LinkHealth(stale_s=300.0)
    end = _run(health, "cloud/soc", [280.0] * 200)

    stats = health.stats("cloud/soc", end)
    assert stats.available_pct == 100.0
    assert stats.median_age_s == 300.0  # the bucket's upper edge, not an invention
    assert stats.verdict == "healthy"


def test_an_age_beyond_the_stale_window_counts_as_absent() -> None:
    health = LinkHealth(stale_s=300.0)
    end = _run(health, "cloud/soc", [4.0] * 60 + [900.0] * 60)

    stats = health.stats("cloud/soc", end)
    assert stats.available_pct == 50.0
    assert stats.dropouts == 1


def test_too_few_samples_yields_no_verdict() -> None:
    """A score from five samples would be noise dressed as a diagnosis."""
    health = LinkHealth()
    end = _run(health, "link", [4.0] * 5)

    assert health.stats("link", end).verdict == "unknown"


def test_an_unwatched_entity_reports_nothing_rather_than_zero() -> None:
    health = LinkHealth()
    stats = health.stats("never/seen", _T0)
    assert stats.samples == 0
    assert stats.verdict == "unknown"
    assert stats.median_age_s is None


def test_observations_older_than_a_day_fall_out_of_the_window() -> None:
    health = LinkHealth()
    _run(health, "link", [None] * 100, start_s=_T0)  # a bad day
    end = _run(health, "link", [4.0] * 400, start_s=_T0 + 26 * 3600.0)  # then a good one

    stats = health.stats("link", end)
    assert stats.available_pct == 100.0
    assert stats.dropouts == 0, "yesterday's outage must not haunt today's score"


def test_the_bucket_list_stays_bounded() -> None:
    """Ten seconds a tick for weeks must not grow the record without limit."""
    health = LinkHealth()
    now = _T0
    for _ in range(400):  # 400 hours of samples, one per hour
        health.observe("link", now, 4.0)
        now += 3600.0
    assert len(health._buckets["link"]) <= 25


def test_the_summary_puts_the_worst_link_first() -> None:
    health = LinkHealth()
    end = _run(health, "good", [4.0] * 400)
    _run(health, "bad", [None] * 200 + [4.0] * 200)

    rows = health.summary(end)
    assert [r.key for r in rows] == ["bad", "good"]
    worst = health.worst(end)
    assert worst is not None and worst.key == "bad"


def test_unrated_links_never_masquerade_as_the_worst() -> None:
    """A brand-new entity has no score; ranking it first would point at the wrong thing."""
    health = LinkHealth()
    end = _run(health, "established", [4.0] * 200 + [None] * 100)
    _run(health, "brand_new", [4.0] * 3)

    worst = health.worst(end)
    assert worst is not None and worst.key == "established"
    assert health.summary(end)[-1].key == "brand_new"


def test_the_record_survives_a_restart() -> None:
    health = LinkHealth(stale_s=240.0)
    end = _run(health, "pdl/power", [4.0] * 200 + [None] * 60 + [4.0] * 100)
    before = health.stats("pdl/power", end)

    restored = LinkHealth.from_dict(health.to_dict())
    after = restored.stats("pdl/power", end)

    assert restored.stale_s == 240.0
    assert after == before


def test_a_malformed_payload_costs_nothing_but_that_entity() -> None:
    payload = {
        "stale_s": 300.0,
        "links": {"good": [{"hour": 1000, "samples": 5, "fresh": 5, "hist": "nope"}], "bad": 42},
    }
    restored = LinkHealth.from_dict(payload)
    assert "bad" not in restored._buckets
    assert restored._buckets["good"][0].samples == 5


def test_forgetting_an_entity_clears_its_in_flight_gap_too() -> None:
    """A removed device must not leave a gap timer that a re-add would inherit."""
    health = LinkHealth()
    _run(health, "gone", [4.0] * 30 + [None] * 30)
    health.forget({"kept"})

    assert "gone" not in health._buckets
    assert "gone" not in health._gap_start_s
    assert "gone" not in health._last_fresh
