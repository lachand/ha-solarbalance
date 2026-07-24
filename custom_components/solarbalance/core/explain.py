"""Say in one sentence why the fleet is doing what it is doing.

The regulator already reports *what* it decided — a target, a ``binding``, a pile of
diagnostics — but reading them takes knowing what ``no_charge_floor`` or ``unalloc``
mean. Every incident this week ended with someone having to translate that jargon
by hand. This module does the translating.

It returns a **key plus parameters**, not a finished sentence in one language: the
core has no business holding French or English copy, and a UI needs the numbers
separately anyway to format them. ``text`` is an English rendering, good enough for
a sensor attribute or a logbook line when no UI is doing the formatting.

The sentence is composed rather than picked from a table of whole phrases, so the
combinations stay manageable:

    <action, with its size>  :  <why, in measured terms>  <constraint, if one bound>

What comes first matters more than completeness. When the meter is gone, saying
"discharging 800 W because the house draws 900 W" would be a lie dressed as
precision — the house figure is derived from that missing meter. So the states
that invalidate the ordinary reasoning are checked first and answered on their own
terms.

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

# Below this the fleet is doing nothing worth narrating.
_IDLE_W = 40.0
# A clamp is only worth mentioning when it actually moved the target this much.
_BINDING_MENTION_W = 10.0


@dataclass(slots=True, frozen=True)
class Explanation:
    """One sentence about the current tick."""

    key: str
    """Stable identifier a UI can translate (``discharge``, ``degraded_no_meter``…)."""

    text: str
    """English rendering, for the sensor attribute and the logbook."""

    params: Mapping[str, float | str | bool] = field(default_factory=dict)


def _w(value: float) -> str:
    return f"{abs(value):.0f} W"


_CONSTRAINTS: dict[str, str] = {
    "no_charge_floor": "capped at the fleet's own solar, so nothing is charged from the grid",
    "no_export": "capped so the batteries never push power onto the grid",
    "no_feed": "capped so the batteries don't feed a self-charging cloud battery",
    "equaliser": "steered by the SoC equaliser toward the cloud battery",
    "eq_pv_route": "routing solar out to the cloud battery",
    "cloud_relief": "backing off because the cloud battery is charging",
    "charge_priority": "pulled up to fill the priority battery first",
    "grid_import": "capped by the import limit",
    "grid_export": "capped by the export limit",
}


def explain_tick(
    *,
    target_w: float,
    house_w: float,
    pv_w: float,
    binding: str = "base",
    binding_moved_w: float = 0.0,
    degraded: bool = False,
    grid_source: str = "primary",
    solar_fallback_active: bool = False,
    solar_fallback_w: float = 0.0,
    settle_active: bool = False,
    near_full: bool = False,
    anticipating: bool = False,
) -> Explanation:
    """Compose the explanation for one regulation tick.

    Args:
        target_w: Fleet target (positive = charge, negative = discharge).
        house_w: Household consumption (W) — the *natural* grid, fleet excluded.
        pv_w: Controllable PV production (W).
        binding: Which clamp set the target (``base`` when none did).
        binding_moved_w: How far that clamp moved the target; a clamp that merely
            grazed the value is not worth naming.
        degraded: The regulator has lost a critical measurement.
        grid_source: ``primary`` | ``backup`` | ``none``.
        solar_fallback_active: Blind solar-only charging is driving the fleet.
        solar_fallback_w: Power that fallback is commanding (W).
        settle_active: Holding after a big load drop.
        near_full: The fleet can no longer absorb.
        anticipating: Pre-curtailing from the forecast.

    Returns:
        An :class:`Explanation`. Never raises — an unknown ``binding`` is simply
        not mentioned rather than blocking the sentence.
    """
    params: dict[str, float | str | bool] = {
        "target_w": round(target_w),
        "house_w": round(house_w),
        "pv_w": round(pv_w),
        "binding": binding,
    }

    # States that invalidate the ordinary reasoning come first: with no meter, the
    # house figure is itself derived from the missing measurement.
    if degraded and solar_fallback_active:
        params["fallback_w"] = round(solar_fallback_w)
        return Explanation(
            "degraded_solar_fallback",
            f"Grid meter unavailable: storing an estimated {_w(solar_fallback_w)} of solar "
            "surplus, and never discharging while blind.",
            params,
        )
    if degraded:
        return Explanation(
            "degraded_no_meter",
            "Grid meter unavailable: control is suspended until it returns.",
            params,
        )

    prefix = ""
    if grid_source == "backup":
        prefix = "Running on the backup grid sensor. "

    if settle_active:
        return Explanation(
            "settle_hold",
            prefix + "Holding steady for a moment after a big load dropped, "
            "rather than chasing the transient.",
            params,
        )

    # Action.
    if abs(target_w) < _IDLE_W:
        action = "Fleet idle"
        key = "idle"
    elif target_w > 0:
        action = f"Charging {_w(target_w)}"
        key = "charge"
    else:
        action = f"Discharging {_w(target_w)}"
        key = "discharge"

    # Why, in measured terms.
    surplus_w = pv_w - house_w
    if target_w > 0 and surplus_w > 0:
        because = f"solar makes {_w(pv_w)} and the house draws {_w(house_w)}, leaving a surplus"
    elif target_w < 0:
        because = f"the house draws {_w(house_w)} and solar covers {_w(pv_w)} of it"
    else:
        because = f"solar ({_w(pv_w)}) and consumption ({_w(house_w)}) are balanced"

    # Constraint, only when a clamp genuinely moved the target.
    constraint = ""
    if binding != "base" and abs(binding_moved_w) > _BINDING_MENTION_W:
        phrase = _CONSTRAINTS.get(binding)
        if phrase:
            constraint = f"; {phrase}"
            key = f"{key}_{binding}"
    if near_full and not constraint:
        constraint = "; the batteries are nearly full"
    if anticipating:
        constraint += "; pre-curtailing because the forecast surplus exceeds what can absorb it"

    return Explanation(key, f"{prefix}{action}: {because}{constraint}.", params)
