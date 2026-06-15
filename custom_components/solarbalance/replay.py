"""Replay a past day through the decision engine, from recorder history.

Reconstructs a :class:`Snapshot` at regular samples across a chosen day using the
recorder's historical states (no live reads, no hardware writes), runs the
arbiter on each, and returns an hourly summary of what the engine *would* have
decided and what the grid cost would have been. Read-only.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .adapters.entity_reader import EntityReader

if TYPE_CHECKING:
    from .coordinator import SolarBalanceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_replay_day(
    hass: HomeAssistant,
    coordinator: SolarBalanceCoordinator,
    day: date | None = None,
    step_minutes: int = 30,
) -> dict[str, Any]:
    """Replay ``day`` (default yesterday) and return an hourly decision summary."""
    from homeassistant.components.recorder import get_instance, history

    step_minutes = max(5, min(60, int(step_minutes)))
    target = day or (dt_util.now().date() - timedelta(days=1))
    start = dt_util.start_of_local_day(target)
    end = min(start + timedelta(days=1), dt_util.now())
    if end <= start:
        return {"error": "day is in the future", "date": target.isoformat()}

    entity_ids = coordinator.configured_entity_ids()
    if not entity_ids:
        return {"error": "no configured entities", "date": target.isoformat()}

    try:
        states = await get_instance(hass).async_add_executor_job(
            history.get_significant_states,
            hass, start, end, entity_ids, None, True, False,
        )
    except (HomeAssistantError, RuntimeError, KeyError, ValueError, TypeError) as exc:
        return {"error": f"recorder unavailable: {exc}", "date": target.isoformat()}
    if not states:
        return {"error": "no recorder history for that day", "date": target.isoformat()}

    # Per-entity time-sorted (timestamp, value) timelines.
    timelines: dict[str, list[tuple[datetime, str]]] = {}
    for eid, entries in states.items():
        series = [
            (st.last_updated, st.state)
            for st in entries
            if st.state not in ("unknown", "unavailable", "", None)
        ]
        series.sort(key=lambda e: e[0])
        if series:
            timelines[eid] = series

    devices, meters, loads = coordinator._devices, coordinator._meters, coordinator._loads
    tariff = coordinator._tariff
    step_h = step_minutes / 60.0

    hours: dict[int, dict[str, Any]] = {}
    samples = 0
    t = start
    while t < end:
        value_at = _values_at(timelines, t)
        reader = EntityReader(
            hass, devices, meters, loads,
            state_getter=lambda eid, _v=value_at: (
                State(eid, _v[eid]) if eid in _v else None
            ),
        )
        snap = reader.snapshot(timestamp=t)
        result = coordinator._arbiter.run(snap)
        batt_target = sum(
            tt.preferred_power_w or 0.0 for tt in result.decision.battery_targets.values()
        )
        local = dt_util.as_local(t)
        price = tariff.current_import_price(local) or 0.0
        export_price = tariff.current_export_price(local) or 0.0
        imp_w = max(0.0, snap.grid_power_w)
        exp_w = max(0.0, -snap.grid_power_w)
        bucket = hours.setdefault(
            local.hour,
            {"grid_w": 0.0, "batt_target_w": 0.0, "cost_eur": 0.0,
             "import_kwh": 0.0, "export_kwh": 0.0, "_n": 0, "_strats": Counter()},
        )
        bucket["grid_w"] += snap.grid_power_w
        bucket["batt_target_w"] += batt_target
        bucket["import_kwh"] += imp_w / 1000.0 * step_h
        bucket["export_kwh"] += exp_w / 1000.0 * step_h
        bucket["cost_eur"] += (imp_w * price - exp_w * export_price) / 1000.0 * step_h
        bucket["_n"] += 1
        bucket["_strats"][result.dominant_strategy] += 1
        samples += 1
        t += timedelta(minutes=step_minutes)

    hourly = []
    tot_cost = tot_imp = tot_exp = 0.0
    for hour in sorted(hours):
        b = hours[hour]
        n = max(1, b["_n"])
        tot_cost += b["cost_eur"]
        tot_imp += b["import_kwh"]
        tot_exp += b["export_kwh"]
        hourly.append({
            "hour": hour,
            "grid_w": round(b["grid_w"] / n),
            "battery_target_w": round(b["batt_target_w"] / n),
            "strategy": b["_strats"].most_common(1)[0][0] if b["_strats"] else None,
            "cost_eur": round(b["cost_eur"], 3),
        })

    return {
        "date": target.isoformat(),
        "samples": samples,
        "step_minutes": step_minutes,
        "totals": {
            "cost_eur": round(tot_cost, 2),
            "import_kwh": round(tot_imp, 2),
            "export_kwh": round(tot_exp, 2),
        },
        "hourly": hourly,
    }


def _values_at(
    timelines: dict[str, list[tuple[datetime, str]]], t: datetime
) -> dict[str, str]:
    """Last known value of each entity at or before ``t`` (forward-filled)."""
    out: dict[str, str] = {}
    for eid, series in timelines.items():
        value: str | None = None
        for ts, val in series:
            if ts <= t:
                value = val
            else:
                break
        if value is not None:
            out[eid] = value
    return out
