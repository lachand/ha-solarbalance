"""Tests for the aggregated installation health score."""

from custom_components.solarbalance.core.install_score import install_score


def _call(**kw):
    base = {
        "grid_source": "primary",
        "degraded": False,
        "weakest_link_score": 100.0,
        "grid_reject_rate": 0.0,
        "config_issue_count": 0,
        "tariff_degraded": False,
    }
    base.update(kw)
    return install_score(**base)  # type: ignore[arg-type]


def test_a_clean_installation_scores_full_marks() -> None:
    res = _call()
    assert res.score == 100.0
    assert res.verdict == "healthy"
    assert res.deductions == []


def test_losing_the_meter_entirely_is_the_heaviest_hit() -> None:
    no_meter = _call(grid_source="none").score
    on_backup = _call(grid_source="backup").score
    assert no_meter < on_backup < 100.0


def test_degraded_mode_is_called_out() -> None:
    res = _call(degraded=True)
    assert res.verdict in ("fair", "degraded")
    assert any("degraded" in d.reason.lower() for d in res.deductions)


def test_a_perfect_link_deducts_nothing_a_dead_one_the_full_weight() -> None:
    assert _call(weakest_link_score=100.0).score == 100.0
    assert _call(weakest_link_score=95.0).score == 100.0  # boundary: nothing lost
    partial = _call(weakest_link_score=50.0).score
    dead = _call(weakest_link_score=0.0).score
    assert dead < partial < 100.0


def test_rejected_readings_scale_the_deduction() -> None:
    light = _call(grid_reject_rate=0.05).score
    heavy = _call(grid_reject_rate=0.5).score
    assert heavy < light < 100.0
    # Capped: a totally broken meter cannot subtract more than its weight.
    assert _call(grid_reject_rate=1.0).score >= _call(grid_source="none").score - 100.0


def test_config_issues_and_tariff_each_cost_something() -> None:
    assert _call(config_issue_count=2).score < 100.0
    assert _call(tariff_degraded=True).score < 100.0


def test_deductions_are_sorted_heaviest_first() -> None:
    res = _call(grid_source="backup", tariff_degraded=True, config_issue_count=1)
    pts = [d.points for d in res.deductions]
    assert pts == sorted(pts, reverse=True)


def test_the_score_never_goes_negative() -> None:
    res = _call(
        grid_source="none",
        degraded=True,
        weakest_link_score=0.0,
        grid_reject_rate=1.0,
        config_issue_count=10,
        tariff_degraded=True,
    )
    assert res.score == 0.0
    assert res.verdict == "degraded"


def test_verdict_bands() -> None:
    assert _call().verdict == "healthy"
    assert _call(grid_source="backup", tariff_degraded=True).verdict in ("healthy", "fair")
    assert _call(grid_source="none").verdict in ("fair", "degraded")
