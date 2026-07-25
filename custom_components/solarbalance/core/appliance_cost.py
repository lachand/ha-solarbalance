"""What a learned appliance cycle actually costs to run.

The cycle learner already knows each program's energy and, from the PV forecast,
how much of it the sun would cover if started now or at the best hour. Priced with
the current import tariff, that turns into the figure a household actually reasons
about: euros for this wash, and euros saved by waiting for the sun.

Deliberately an estimate from the *typical* cycle, not a per-run meter reading:
the point is to compare programs and to decide when to start one, and for that the
learned energy and solar share are exactly the right inputs. Export revenue is not
netted in — an appliance consumes, it does not export — so the number is a cost,
never a fictitious gain.

Pure module — no Home Assistant imports.
"""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CycleCost:
    """The cost of one cycle, three ways."""

    grid_only_eur: float
    """If every kilowatt-hour came from the grid — the no-solar baseline."""

    now_eur: float
    """Starting now, with the solar share the sun would cover at this hour."""

    best_eur: float
    """Starting at the best forecast hour, with its (larger) solar share."""

    saving_by_waiting_eur: float
    """``now_eur - best_eur`` — what waiting for the better hour is worth."""


def cycle_cost(
    *,
    energy_kwh: float,
    import_price_eur: float | None,
    solar_fraction_now: float | None,
    solar_fraction_best: float | None = None,
) -> CycleCost | None:
    """Cost a cycle at the current tariff, given how much solar covers it.

    Args:
        energy_kwh: The cycle's energy.
        import_price_eur: Current import price (EUR/kWh); ``None`` (no tariff) means
            no cost can be stated, so the whole result is ``None``.
        solar_fraction_now: Share (0-1) the sun covers if started now; ``None`` is
            treated as no solar, which only makes the cost larger.
        solar_fraction_best: Share at the best hour; defaults to ``now`` so a setup
            without a forecast simply reports no saving from waiting.

    Returns:
        A :class:`CycleCost`, or ``None`` when no price is available.
    """
    if import_price_eur is None or energy_kwh <= 0.0:
        return None

    def _grid_share(fraction: float | None) -> float:
        return 1.0 - max(0.0, min(1.0, fraction if fraction is not None else 0.0))

    now_frac = solar_fraction_now
    best_frac = solar_fraction_best if solar_fraction_best is not None else solar_fraction_now

    grid_only = energy_kwh * import_price_eur
    now_cost = energy_kwh * _grid_share(now_frac) * import_price_eur
    best_cost = energy_kwh * _grid_share(best_frac) * import_price_eur
    return CycleCost(
        grid_only_eur=round(grid_only, 3),
        now_eur=round(now_cost, 3),
        best_eur=round(best_cost, 3),
        saving_by_waiting_eur=round(max(0.0, now_cost - best_cost), 3),
    )
