"""Anticipatory PV curtailment — pre-brake before the batteries saturate.

Reactive curtailment (:mod:`.curtailment`) only trims PV *after* the grid already
exports past its setpoint. Between the export starting and the limit converging sit
the grid median filter, the settle window and the ramp — on a fast solar rise into
a near-full fleet that latency shows up as a large export transient.

This module computes, from the forecast, whether the surplus about to arrive can
still be absorbed. If it cannot, it hands the curtailment controller a **pre-limit**
so the inverter is already capped when the surplus lands.

The decision rests on a **sink budget**: everything that can still soak surplus.

    sinks = controllable batteries + cloud (non-controllable) batteries + commandable loads
    budget = Σ min(absorb_w, headroom_kwh / horizon_h * 1000)

The ``min`` is what makes this anticipatory rather than reactive. A nearly-full
battery still advertises its full charge *rate* (``absorb_w``), but its remaining
*energy* (``headroom_kwh``) collapses; averaged over the horizon its contribution
falls toward zero **before** SoC reaches ``soc_max``. The pre-limit therefore comes
down while the battery is still charging, not once it is full. A load has no energy
ceiling on this horizon (``headroom_kwh = inf``) and always contributes its full
``absorb_w``.

Then::

    surplus  = forecast_pv_w - predicted_consumption_w
    export   = surplus - budget          # what nothing can absorb
    pre-limit = predicted_consumption_w + budget   (only when export > margin_w)

Two properties matter and are enforced here:

* **Solar is never thrown away while a sink has room.** When ``surplus`` fits in the
  budget the result is inactive and no pre-limit is emitted.
* **The pre-limit can never force import or export.** It is never below what the
  house plus its sinks consume, and it only ever *lowers* the PV limit.

Loads that are measured but not commandable (an EV charging outside Home Assistant,
the local AC load, the standby talon) are **not** sinks: their draw is already inside
``predicted_consumption_w``. Counting them again would inflate the budget and delay
the brake.

Pure module — no Home Assistant imports.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

SINK_CONTROLLABLE_BATTERY = "controllable_battery"
SINK_CLOUD_BATTERY = "cloud_battery"
SINK_LOAD = "load"

# Below this the fleet is not really charging: a time-to-saturation from it would be
# meaningless (and divide by ~0).
_MIN_NET_CHARGE_W = 1.0


@dataclass(slots=True, frozen=True)
class Sink:
    """One thing that can still absorb PV surplus.

    Attributes:
        name: Device/load name (diagnostics).
        kind: One of the ``SINK_*`` constants.
        absorb_w: Power it can still take right now (W, never negative).
        headroom_kwh: Energy it can take before it saturates. ``math.inf`` for a
            load, which has no energy ceiling over an anticipation horizon.
    """

    name: str
    kind: str
    absorb_w: float
    headroom_kwh: float

    def effective_absorb_w(self, horizon_h: float) -> float:
        """Power it can sustain *for the whole horizon* (W).

        A battery that can take 1500 W but only holds 0.05 kWh more cannot sustain
        1500 W for 12 minutes — over that horizon it is worth 250 W. This is the
        term that makes the brake anticipatory.
        """
        absorb = max(0.0, self.absorb_w)
        if not math.isfinite(self.headroom_kwh):
            return absorb
        if horizon_h <= 0:
            return absorb
        sustainable_w = max(0.0, self.headroom_kwh) / horizon_h * 1000.0
        return min(absorb, sustainable_w)


@dataclass(slots=True, frozen=True)
class SinkBudget:
    """How much surplus the whole system can absorb over the horizon."""

    total_absorb_w: float
    instantaneous_absorb_w: float
    total_headroom_kwh: float
    by_kind_w: Mapping[str, float] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AnticipationInputs:
    """Everything the anticipation decision needs, already gathered."""

    enabled: bool
    forecast_available: bool
    forecast_pv_w: float
    predicted_consumption_w: float
    budget: SinkBudget
    current_net_charge_w: float
    margin_w: float


@dataclass(slots=True, frozen=True)
class AnticipationResult:
    """Outcome of one anticipation evaluation."""

    active: bool
    preemptive_limit_w: float | None
    sink_budget_w: float
    forecast_surplus_w: float
    projected_export_w: float
    time_to_saturation_s: float | None
    reason: str


def compute_sink_budget(sinks: Sequence[Sink], *, horizon_s: float) -> SinkBudget:
    """Aggregate what the sinks can absorb, averaged over the horizon.

    Args:
        sinks: Every sink that can still take surplus. Saturated batteries (at their
            SoC ceiling) and stale/unavailable devices must simply not be listed.
        horizon_s: How far ahead the brake looks (s).

    Returns:
        A :class:`SinkBudget`. ``total_absorb_w`` is the horizon-averaged figure the
        decision uses; ``instantaneous_absorb_w`` is the raw sum, for diagnostics.
    """
    horizon_h = max(0.0, horizon_s) / 3600.0
    by_kind: dict[str, float] = {}
    total = 0.0
    instantaneous = 0.0
    headroom = 0.0
    for sink in sinks:
        effective = sink.effective_absorb_w(horizon_h)
        total += effective
        instantaneous += max(0.0, sink.absorb_w)
        if math.isfinite(sink.headroom_kwh):
            headroom += max(0.0, sink.headroom_kwh)
        by_kind[sink.kind] = by_kind.get(sink.kind, 0.0) + effective
    return SinkBudget(
        total_absorb_w=total,
        instantaneous_absorb_w=instantaneous,
        total_headroom_kwh=headroom,
        by_kind_w=by_kind,
    )


def evaluate_anticipation(inp: AnticipationInputs) -> AnticipationResult:
    """Decide whether to pre-curtail, and to what limit.

    Returns a result whose ``preemptive_limit_w`` is ``None`` whenever the brake must
    stay out of the way — disabled, no forecast, or the sinks can still take the
    surplus. Only when the forecast surplus beats the sink budget by more than
    ``margin_w`` does it emit a limit, and that limit is the level at which the house
    and its sinks consume everything the array makes.
    """
    budget_w = inp.budget.total_absorb_w
    surplus_w = inp.forecast_pv_w - inp.predicted_consumption_w
    projected_export_w = surplus_w - budget_w

    time_to_saturation_s: float | None = None
    if inp.current_net_charge_w > _MIN_NET_CHARGE_W and math.isfinite(
        inp.budget.total_headroom_kwh
    ):
        time_to_saturation_s = (
            inp.budget.total_headroom_kwh * 3_600_000.0 / inp.current_net_charge_w
        )

    if not inp.enabled:
        reason = "disabled"
    elif not inp.forecast_available:
        reason = "no_forecast"
    elif projected_export_w <= inp.margin_w:
        reason = "sinks_have_room"
    else:
        reason = "anticipating"

    active = reason == "anticipating"
    # The house and its sinks together absorb this much — capping PV here spills
    # nothing to the grid, and being >= consumption it can never force an import.
    limit_w = max(0.0, inp.predicted_consumption_w + budget_w) if active else None

    return AnticipationResult(
        active=active,
        preemptive_limit_w=limit_w,
        sink_budget_w=budget_w,
        forecast_surplus_w=surplus_w,
        projected_export_w=projected_export_w,
        time_to_saturation_s=time_to_saturation_s,
        reason=reason,
    )
