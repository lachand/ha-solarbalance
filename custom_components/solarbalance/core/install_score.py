"""One number for "is this installation healthy?", and why it isn't.

The pieces already exist — link health, the plausibility guard, the config-health
check, the degraded flag — but reading them means knowing where each lives and
what a good value looks like. This rolls them into a single 0-100 score plus the
list of what pulled it down, so the answer to "should I be worried?" is one glance
rather than a tour of the diagnostics.

The score starts at 100 and each problem subtracts a weight chosen by how much it
actually hurts. Losing the grid meter entirely (no primary, no backup) is close to
fatal to regulation, so it costs the most; running on the backup meter is a real
but survivable degradation; a flaky sensor link or a stale config warning cost
less. The deductions are additive and clamped, and every one that fired is
returned with its reason — a score with no explanation is just another number to
distrust.

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class Deduction:
    """One thing that lowered the score."""

    points: float
    reason: str


@dataclass(slots=True, frozen=True)
class InstallScore:
    """The overall health of the installation, and what dragged it down."""

    score: float
    """0-100, 100 being nothing wrong."""

    verdict: str
    """``healthy`` | ``fair`` | ``degraded``."""

    deductions: list[Deduction] = field(default_factory=list)
    """Everything that fired, largest first."""


def install_score(
    *,
    grid_source: str,
    degraded: bool,
    weakest_link_score: float | None,
    grid_reject_rate: float,
    config_issue_count: int,
    tariff_degraded: bool,
) -> InstallScore:
    """Aggregate the health signals into a single score.

    Args:
        grid_source: ``primary`` | ``backup`` | ``none`` — which meter is answering.
        degraded: The regulator has suspended control for lack of a measurement.
        weakest_link_score: Score (0-100) of the least reliable entity, or ``None``
            when nothing has been watched long enough to judge.
        grid_reject_rate: Fraction (0-1) of recent grid readings the plausibility
            guard had to reject — a proxy for a misbehaving meter.
        config_issue_count: Number of open configuration-health issues.
        tariff_degraded: The tariff source is unavailable, so cost/steering are blind.

    Returns:
        An :class:`InstallScore`; ``deductions`` explains any score below 100.
    """
    deductions: list[Deduction] = []

    if grid_source == "none":
        deductions.append(
            Deduction(45.0, "No grid meter is reporting (primary and backup both gone)")
        )
    elif grid_source == "backup":
        deductions.append(Deduction(15.0, "Running on the backup grid sensor"))

    if degraded:
        deductions.append(Deduction(30.0, "Regulation is suspended (degraded mode)"))

    # The weakest link only counts what it actually lost: a 100-score link deducts
    # nothing, a dead one deducts the full weight.
    if weakest_link_score is not None and weakest_link_score < 95.0:
        lost = (100.0 - weakest_link_score) / 100.0 * 20.0
        deductions.append(
            Deduction(round(lost, 1), f"Least reliable link at {weakest_link_score:.0f}/100")
        )

    if grid_reject_rate > 0.0:
        pts = min(20.0, grid_reject_rate * 100.0)
        deductions.append(
            Deduction(
                round(pts, 1),
                f"{grid_reject_rate * 100:.0f}% of grid readings rejected as impossible",
            )
        )

    if config_issue_count > 0:
        pts = min(15.0, config_issue_count * 5.0)
        deductions.append(Deduction(pts, f"{config_issue_count} configuration issue(s) open"))

    if tariff_degraded:
        deductions.append(Deduction(5.0, "Tariff source unavailable"))

    deductions.sort(key=lambda d: d.points, reverse=True)
    score = max(0.0, 100.0 - sum(d.points for d in deductions))

    if score >= 90.0:
        verdict = "healthy"
    elif score >= 65.0:
        verdict = "fair"
    else:
        verdict = "degraded"

    return InstallScore(score=round(score, 1), verdict=verdict, deductions=deductions)


def deductions_as_text(deductions: Sequence[Deduction]) -> list[str]:
    """Render deductions as ``"-N: reason"`` lines for a sensor attribute."""
    return [f"-{d.points:g}: {d.reason}" for d in deductions]
