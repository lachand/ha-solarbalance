"""Diagnostics export for SolarBalance (Settings → Devices → Download diagnostics)."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return a redaction-free snapshot of the integration's state for support.

    Only configuration and computed values are exported (entity IDs, powers,
    SoC…) — no tokens or credentials are stored by this integration.
    """
    data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
            "subentries": [
                {"type": s.subentry_type, "title": s.title, "data": dict(s.data)}
                for s in entry.subentries.values()
            ],
        }
    }

    coord: SolarBalanceCoordinator | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get(COORDINATOR_KEY)
    )
    if coord is None:
        data["coordinator"] = "not set up"
        return data

    snap = coord.data
    data["coordinator"] = {
        "mode": getattr(coord.mode, "value", str(coord.mode)),
        "config_issues": coord.config_issues,
        "devices": [d.name for d in coord._devices],
        "meters": [m.name for m in coord._meters],
        "loads": [ld.name for ld in coord._loads],
        "shed_exempt": sorted(coord._shed_exempt),
        "force_charge_active": sorted(coord._force_charge_req),
        "baseline_talon_w": getattr(coord._baseline_est, "talon_w", None),
        "dry_run": coord._dry_run,
        "tariff_degraded": coord._tariff_degraded,
        "remaining_pv_today_kwh": coord.remaining_pv_today_kwh,
        "settle_ticks_remaining": coord._settle_state.ticks_remaining,
    }
    # 24 h of per-entity reporting record. First thing to read on any "it stopped
    # regulating" report: it distinguishes a control fault from a silent sensor,
    # which took hours to tell apart by hand.
    data["links"] = [
        {
            "key": s.key,
            "score": s.score,
            "available_pct": s.available_pct,
            "median_age_s": s.median_age_s,
            "longest_gap_s": s.longest_gap_s,
            "dropouts": s.dropouts,
            "samples": s.samples,
            "verdict": s.verdict,
        }
        for s in coord.link_health
    ]
    cf = coord.counterfactual
    data["counterfactual"] = {
        "savings_eur": cf.savings_eur,
        "actual_cost_eur": cf.actual_cost_eur,
        "naive_cost_eur": cf.naive_cost_eur,
        "actual_import_kwh": cf.actual_import_kwh,
        "naive_import_kwh": cf.naive_import_kwh,
        "actual_export_kwh": cf.actual_export_kwh,
        "naive_export_kwh": cf.naive_export_kwh,
        "stored_delta_kwh": cf.stored_delta_kwh,
        "hours": cf.hours,
    }
    band = coord._balance_band
    if band is not None:
        data["balance_point"] = {
            "settled": band.settled,
            "reason": band.reason,
            "enter_w": round(band.enter_w, 1),
            "exit_import_w": round(band.exit_import_w, 1),
            "exit_export_w": round(band.exit_export_w, 1),
            "actuator_lag_s": coord._actuator_lag_s,
        }
    diag = coord._diagnostics
    if diag is not None:
        data["regulation"] = {
            "grid_filtered_w": diag.grid_filtered_w,
            "zero_injection_correction_w": diag.zero_injection_correction_w,
            "equaliser_offer_w": diag.equaliser_offer_w,
            "fleet_target_w": diag.fleet_target_w,
            "regulating": diag.regulating,
            "pv_limit_w": diag.pv_limit_w,
        }
    if snap is not None:
        data["snapshot"] = {
            "timestamp": snap.timestamp.isoformat(),
            "grid_power_w": snap.grid_power_w,
            "pv_power_w": getattr(snap, "pv_power_w", None),
            "batteries": [
                {
                    "device": b.device_name,
                    "soc_pct": b.soc_pct,
                    "power_w": b.power_w,
                    "available": b.available,
                }
                for b in snap.batteries
            ],
        }
    return data
