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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .planner import BatteryConstraints, ForecastSlot
from .tariff import TariffConfig

_DEFAULT_IMPORT_PRICE = 0.20
_DEFAULT_EXPORT_PRICE = 0.10


class ForecastUnit(StrEnum):
    """How a configured PV-forecast entity expresses its value."""

    W = "w"  # average power over the hour (W)
    WH = "wh"  # energy over the hour (Wh) — numerically the average W
    KWH = "kwh"  # energy over the hour (kWh)


@dataclass(slots=True, frozen=True)
class ForecastConfig:
    """User-declared mapping of PV-forecast entities to hour offsets.

    ``hour_entities`` pairs an hour offset (0 = the current hour, 1 = next hour,
    …) with the HA entity giving the forecast for that hour. Vendor-agnostic: the
    user maps whatever forecast entities they have.
    """

    unit: ForecastUnit
    hour_entities: tuple[tuple[int, str], ...]

    @property
    def entities(self) -> tuple[str, ...]:
        """Distinct entity IDs to read."""
        return tuple(dict.fromkeys(e for _, e in self.hour_entities))

    def to_power_w(self, value: float) -> float:
        """Convert a forecast value to average power (W) for its hour."""
        if self.unit is ForecastUnit.KWH:
            return value * 1000.0
        return value  # W, or Wh-per-hour which equals the average W numerically


def build_pv_w_by_hour(
    config: ForecastConfig,
    values_by_entity: Mapping[str, float],
    *,
    horizon_h: int,
) -> list[float]:
    """Per-hour PV power (W) from configured forecast entities.

    Declared hours are filled (converted to W, clamped ≥ 0); undeclared hours are
    0 (conservative — no assumed production). Length is ``horizon_h``.
    """
    pv = [0.0] * horizon_h
    for hour, entity in config.hour_entities:
        if 0 <= hour < horizon_h:
            value = values_by_entity.get(entity)
            if value is not None:
                pv[hour] = max(0.0, config.to_power_w(value))
    return pv


def build_forecast_slots(
    *,
    start: datetime,
    n_hours: int,
    pv_w_by_hour: Sequence[float],
    baseline_w: float,
    tariff: TariffConfig,
    slot_s: float = 3600.0,
    consumption_by_hour: Sequence[float] | None = None,
) -> tuple[ForecastSlot, ...]:
    """Build hourly forecast slots for the planner.

    Args:
        start: Wall-clock start of the horizon (slot 0).
        n_hours: Number of hourly slots to build.
        pv_w_by_hour: Forecast PV power (W) per hour. Shorter sequences repeat
            their last value; empty means no PV (0 W).
        baseline_w: Estimated background load (W); the flat fallback used when no
            learned hour-of-day profile is supplied.
        tariff: Tariff used to price each slot (evaluated at the slot start).
        slot_s: Slot duration in seconds.
        consumption_by_hour: Optional 24-length hour-of-day consumption profile (W)
            from the learned consumption profile. When given, each slot uses the
            value for its wall-clock hour instead of the flat ``baseline_w`` — so
            the plan anticipates the morning/evening peaks.
    """
    slots: list[ForecastSlot] = []
    for h in range(n_hours):
        slot_start = start + timedelta(hours=h)
        if pv_w_by_hour:
            pv_w = pv_w_by_hour[h] if h < len(pv_w_by_hour) else pv_w_by_hour[-1]
        else:
            pv_w = 0.0
        if consumption_by_hour and slot_start.hour < len(consumption_by_hour):
            load_w = consumption_by_hour[slot_start.hour]
        else:
            load_w = baseline_w
        import_price = tariff.current_import_price(slot_start)
        export_price = tariff.current_export_price(slot_start)
        slots.append(
            ForecastSlot(
                start=slot_start,
                duration_s=slot_s,
                net_load_w=load_w - pv_w,
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
