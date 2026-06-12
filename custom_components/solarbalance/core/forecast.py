"""Assemble predictive-planner inputs from available forecasts (advisory).

The :class:`~.planner.PredictiveScheduler` needs a per-slot series of net load
and prices. This module builds that series from what SolarBalance has today:

- per-hour PV forecast (W) when available, else a flat fallback;
- a background-load estimate (W), e.g. a rolling average of baseline consumption;
- import/export prices from the tariff configuration, evaluated per slot.

``net_load_w = baseline_w - pv_w`` (positive = the home draws, negative =
surplus). This is a first-step estimate — a flat baseline and a coarse PV series
make the plan **advisory only**; it is not fed into the control loop.

Pure module — no Home Assistant imports.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from .planner import BatteryConstraints, ForecastSlot
from .tariff import TariffConfig

_DEFAULT_IMPORT_PRICE = 0.20
_DEFAULT_EXPORT_PRICE = 0.10


def build_forecast_slots(
    *,
    start: datetime,
    n_hours: int,
    pv_w_by_hour: Sequence[float],
    baseline_w: float,
    tariff: TariffConfig,
    slot_s: float = 3600.0,
) -> tuple[ForecastSlot, ...]:
    """Build hourly forecast slots for the planner.

    Args:
        start: Wall-clock start of the horizon (slot 0).
        n_hours: Number of hourly slots to build.
        pv_w_by_hour: Forecast PV power (W) per hour. Shorter sequences repeat
            their last value; empty means no PV (0 W).
        baseline_w: Estimated background load (W), held flat across the horizon.
        tariff: Tariff used to price each slot (evaluated at the slot start).
        slot_s: Slot duration in seconds.
    """
    slots: list[ForecastSlot] = []
    for h in range(n_hours):
        slot_start = start + timedelta(hours=h)
        if pv_w_by_hour:
            pv_w = pv_w_by_hour[h] if h < len(pv_w_by_hour) else pv_w_by_hour[-1]
        else:
            pv_w = 0.0
        import_price = tariff.current_import_price(slot_start)
        export_price = tariff.current_export_price(slot_start)
        slots.append(
            ForecastSlot(
                start=slot_start,
                duration_s=slot_s,
                net_load_w=baseline_w - pv_w,
                import_price=import_price if import_price is not None else _DEFAULT_IMPORT_PRICE,
                export_price=export_price if export_price is not None else _DEFAULT_EXPORT_PRICE,
            )
        )
    return tuple(slots)


def aggregate_battery_constraints(
    fleet: Sequence[BatteryConstraints],
) -> BatteryConstraints | None:
    """Combine a controllable fleet into one equivalent battery for planning.

    Capacities and power limits sum; SoC bounds take the most restrictive
    (highest min, lowest max). Returns ``None`` for an empty fleet.
    """
    if not fleet:
        return None
    return BatteryConstraints(
        capacity_kwh=sum(b.capacity_kwh for b in fleet),
        max_charge_w=sum(b.max_charge_w for b in fleet),
        max_discharge_w=sum(b.max_discharge_w for b in fleet),
        soc_min_pct=max(b.soc_min_pct for b in fleet),
        soc_max_pct=min(b.soc_max_pct for b in fleet),
    )
