"""SolarBalance — Home Energy Management System integration."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.loader import async_get_integration

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

    from .coordinator import SolarBalanceCoordinator

from .const import DOMAIN
from .core.models import HemsMode

_LOGGER = logging.getLogger(__name__)

# Plain strings — Platform is a StrEnum so HA accepts both forms.
PLATFORMS: list[str] = [
    "sensor",
    "binary_sensor",
    "select",
    "number",
    "switch",
]

# Key used to store the coordinator in hass.data[DOMAIN][entry_id]
COORDINATOR_KEY = "coordinator"
# Key used to store YAML-parsed config (devices, meters, loads) set by async_setup
YAML_CONFIG_KEY = "yaml_config"
YAML_RAW_KEY = "yaml_raw"

_CARD_URL = "/solarbalance_card/solarbalance-card.js"
_CARD_REGISTERED_KEY = "_card_frontend_registered"
_PANEL_URL = "/solarbalance_card/solarbalance-panel.js"
_PANEL_REGISTERED_KEY = "_panel_registered"


def _register_card_frontend(hass: HomeAssistant) -> None:
    """Register the static path and JS module URL with the HA frontend.

    Idempotent — safe to call from both async_setup and async_setup_entry.
    """
    if hass.data.get(DOMAIN, {}).get(_CARD_REGISTERED_KEY):
        return

    import pathlib

    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    www_path = pathlib.Path(__file__).parent / "www"
    hass.async_create_task(
        hass.http.async_register_static_paths(
            [StaticPathConfig("/solarbalance_card", str(www_path), cache_headers=False)]
        )
    )
    add_extra_js_url(hass, _CARD_URL)
    hass.data.setdefault(DOMAIN, {})[_CARD_REGISTERED_KEY] = True
    _LOGGER.info(
        "SolarBalance: carte Lovelace disponible à %s — ajoutez une carte custom:solarbalance-card",
        _CARD_URL,
    )


async def _register_panel(hass: HomeAssistant) -> None:
    """Register the full-page SolarBalance custom panel (sidebar entry), once.

    Wrapped defensively: a panel-API mismatch must not break integration setup —
    the panel simply won't appear.
    """
    if hass.data.get(DOMAIN, {}).get(_PANEL_REGISTERED_KEY):
        return
    try:
        from homeassistant.components import panel_custom

        await panel_custom.async_register_panel(
            hass,
            frontend_url_path="solarbalance",
            webcomponent_name="solarbalance-panel",
            module_url=_PANEL_URL,
            sidebar_title="SolarBalance",
            sidebar_icon="mdi:solar-power-variant",
            require_admin=False,
        )
    except Exception as exc:
        _LOGGER.warning("SolarBalance: could not register custom panel: %s", exc)
        return
    hass.data.setdefault(DOMAIN, {})[_PANEL_REGISTERED_KEY] = True
    _LOGGER.info("SolarBalance: panneau plein écran disponible dans la barre latérale")


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Parse the YAML ``solarbalance:`` block if present and register services."""
    from .yaml_loader import parse_yaml_config

    hass.data.setdefault(DOMAIN, {})
    _register_card_frontend(hass)
    await _register_panel(hass)
    raw = config.get(DOMAIN)
    if raw:
        from .yaml_loader import SOLARBALANCE_SCHEMA

        try:
            devices, meters, loads, forecast, tariff_spec = parse_yaml_config(raw)
        except Exception as exc:
            _LOGGER.error("SolarBalance YAML error: %s", exc)
            return False
        hass.data[DOMAIN][YAML_CONFIG_KEY] = (devices, meters, loads, forecast, tariff_spec)
        # Keep the validated raw dicts for a one-time YAML → UI subentry migration.
        with contextlib.suppress(Exception):
            hass.data[DOMAIN][YAML_RAW_KEY] = SOLARBALANCE_SCHEMA(dict(raw))
        _LOGGER.debug(
            "SolarBalance YAML: %d device(s), %d meter(s), %d load(s)",
            len(devices),
            len(meters),
            len(loads),
        )

    _register_services(hass)
    return True


def _get_coordinator(hass: HomeAssistant) -> SolarBalanceCoordinator | None:
    """Return the active coordinator from hass.data, or None."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and COORDINATOR_KEY in entry_data:
            return entry_data[COORDINATOR_KEY]  # type: ignore[return-value]
    return None


def _register_services(hass: HomeAssistant) -> None:
    """Register all SolarBalance services (idempotent — called once at domain setup)."""

    async def handle_pause(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            coord.mode = HemsMode.PAUSED
            coord.async_update_listeners()

    async def handle_resume(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord and coord.mode is HemsMode.PAUSED:
            coord.mode = HemsMode.NORMAL
            coord.async_update_listeners()

    async def handle_set_mode(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            mode = HemsMode(call.data["mode"])
            if mode is HemsMode.STORM:
                # Route through activate_storm_mode so _storm_manual is set,
                # preventing immediate auto-exit on the next tick.
                coord.activate_storm_mode()
            else:
                coord.mode = mode
            coord.async_update_listeners()

    async def handle_force_charge(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            deadline_raw = call.data.get("deadline")
            deadline: datetime | None = (
                datetime.fromisoformat(str(deadline_raw)) if deadline_raw else None
            )
            coord.set_force_override(
                kind="charge",
                target_soc_pct=float(call.data["target_soc_pct"]),
                power_w=call.data.get("power_w"),
                deadline=deadline,
            )
            coord.async_update_listeners()

    async def handle_force_discharge(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            coord.set_force_override(
                kind="discharge",
                target_soc_pct=float(call.data["target_soc_pct"]),
                power_w=call.data.get("power_w"),
            )
            coord.async_update_listeners()

    async def handle_force_charge_load(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            coord.request_force_charge_load(
                str(call.data["load"]),
                kwh=call.data.get("kwh"),
                hours=call.data.get("hours"),
            )
            coord.async_update_listeners()

    async def handle_cancel_force_charge_load(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            coord.cancel_force_charge_load(str(call.data["load"]))
            coord.async_update_listeners()

    async def handle_reset_baseline_talon(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            await coord.reset_baseline_talon()
            coord.async_update_listeners()

    async def handle_export_config(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass)
        if coord is None:
            return {"subentries": []}
        return {
            "subentries": [
                {"type": s.subentry_type, "title": s.title, "data": dict(s.data)}
                for s in coord.config_entry.subentries.values()
            ]
        }

    async def handle_import_config(call: ServiceCall) -> dict[str, Any]:
        import uuid

        from homeassistant.config_entries import ConfigSubentry

        coord = _get_coordinator(hass)
        if coord is None:
            return {"imported": 0}
        valid_types = {"battery", "mppt", "battery_mppt", "load", "meter", "device"}
        imported = 0
        for sub in call.data.get("subentries", []):
            stype = sub.get("type")
            data = sub.get("data")
            if stype not in valid_types or not isinstance(data, dict):
                _LOGGER.warning("import_config: skipping invalid sub-entry %r", sub)
                continue
            hass.config_entries.async_add_subentry(
                coord.config_entry,
                ConfigSubentry(
                    data=data,
                    subentry_type=stype,
                    title=str(sub.get("title") or data.get("name", stype)),
                    unique_id=None,
                    subentry_id=uuid.uuid4().hex,
                ),
            )
            imported += 1
        return {"imported": imported}

    async def handle_replay(call: ServiceCall) -> dict[str, Any]:
        from datetime import date as _date

        from .replay import async_replay_day

        coord = _get_coordinator(hass)
        if coord is None:
            return {"error": "not set up"}
        raw_day = call.data.get("date")
        day = _date.fromisoformat(str(raw_day)) if raw_day else None
        try:
            return await async_replay_day(
                hass, coord, day=day, step_minutes=int(call.data.get("step_minutes", 30))
            )
        except Exception as exc:  # surface a usable message, not "Unknown error"
            _LOGGER.exception("solarbalance.replay failed")
            return {"error": f"{type(exc).__name__}: {exc}"}

    async def handle_test_mapping(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass)
        if coord is None:
            return {"ok": [], "unavailable": [], "missing": []}
        ok: list[str] = []
        unavailable: list[str] = []
        missing: list[str] = []
        for eid in coord.configured_entity_ids():
            state = hass.states.get(eid)
            if state is None:
                missing.append(eid)
            elif state.state in ("unavailable", "unknown", ""):
                unavailable.append(eid)
            else:
                ok.append(eid)
        return {"ok": ok, "unavailable": unavailable, "missing": missing}

    async def handle_capture_debug(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass)
        if coord is None:
            return {"path": None, "ticks": 0}
        minutes = call.data.get("minutes")
        return await coord.capture_debug(
            minutes=float(minutes) if minutes is not None else None,
            include_records=bool(call.data.get("include_records", False)),
        )

    async def handle_rename_appliance_program(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass)
        if coord is None:
            return {"moved": 0}
        moved = await coord.rename_appliance_program(
            str(call.data.get("appliance", "")),
            str(call.data.get("from_program", "unknown")),
            str(call.data.get("to_program", "")),
        )
        return {"moved": moved}

    async def handle_activate_storm_mode(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            duration_h: float | None = call.data.get("duration_h")
            coord.activate_storm_mode(duration_h=duration_h)
            coord.async_update_listeners()

    hass.services.async_register(DOMAIN, "pause", handle_pause)
    hass.services.async_register(DOMAIN, "resume", handle_resume)
    hass.services.async_register(DOMAIN, "set_mode", handle_set_mode)
    hass.services.async_register(DOMAIN, "force_charge", handle_force_charge)
    hass.services.async_register(DOMAIN, "force_discharge", handle_force_discharge)
    hass.services.async_register(DOMAIN, "force_charge_load", handle_force_charge_load)
    hass.services.async_register(
        DOMAIN, "cancel_force_charge_load", handle_cancel_force_charge_load
    )
    hass.services.async_register(DOMAIN, "activate_storm_mode", handle_activate_storm_mode)
    hass.services.async_register(DOMAIN, "reset_baseline_talon", handle_reset_baseline_talon)

    from homeassistant.core import SupportsResponse

    hass.services.async_register(
        DOMAIN, "export_config", handle_export_config, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "import_config", handle_import_config, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, "test_mapping", handle_test_mapping, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "replay", handle_replay, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "capture_debug", handle_capture_debug, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN,
        "rename_appliance_program",
        handle_rename_appliance_program,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarBalance from a config entry."""
    from .coordinator import SolarBalanceCoordinator

    _LOGGER.debug("Setting up SolarBalance entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})
    _register_card_frontend(hass)

    yaml_cfg = hass.data[DOMAIN].get(YAML_CONFIG_KEY)
    yaml_devices, yaml_meters, yaml_loads, forecast, tariff_spec = (
        yaml_cfg if yaml_cfg else ([], [], [], None, None)
    )

    # One-time migration: if YAML declares equipment but no UI subentries exist
    # yet, convert the YAML into subentries so they become editable in the UI.
    if not entry.subentries and (yaml_devices or yaml_meters or yaml_loads):
        _migrate_yaml_to_subentries(hass, entry)

    # Subentries (UI) are authoritative once present and fully replace YAML;
    # otherwise fall back to the YAML-built equipment. Built with the same
    # builders either way, so the engine treats them identically.
    if entry.subentries:
        devices, meters, loads = _build_from_subentries(entry)
    else:
        devices, meters, loads = yaml_devices, yaml_meters, yaml_loads

    coordinator = SolarBalanceCoordinator(
        hass, entry, devices, meters, loads, forecast=forecast, tariff_spec=tariff_spec
    )
    coordinator.version = str((await async_get_integration(hass, DOMAIN)).version)
    await coordinator.async_restore()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {COORDINATOR_KEY: coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _build_from_subentries(
    entry: ConfigEntry,
) -> tuple[list[Any], list[Any], list[Any]]:
    """Build devices/meters/loads from UI config subentries (reusing YAML builders)."""
    import voluptuous as vol

    from .yaml_loader import build_device_from_dict, build_load_from_dict, build_meter_from_dict

    devices: list[Any] = []
    meters: list[Any] = []
    loads: list[Any] = []
    for sub in entry.subentries.values():
        try:
            if sub.subentry_type in ("battery", "mppt", "battery_mppt", "device"):
                devices.append(build_device_from_dict(sub.data))
            elif sub.subentry_type == "load":
                loads.append(build_load_from_dict(sub.data))
            elif sub.subentry_type == "meter":
                meters.append(build_meter_from_dict(sub.data))
        except (vol.Invalid, ValueError, KeyError) as exc:
            _LOGGER.error(
                "SolarBalance: invalid %s subentry %r — skipped: %s",
                sub.subentry_type,
                sub.title,
                exc,
            )
    return devices, meters, loads


def _migrate_yaml_to_subentries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create UI subentries from the validated YAML (one-time, on first setup)."""
    import uuid

    from homeassistant.config_entries import ConfigSubentry

    validated = hass.data.get(DOMAIN, {}).get(YAML_RAW_KEY)
    if not validated:
        return

    def _add(subentry_type: str, data: dict[str, Any], title: str) -> None:
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=data,
                subentry_type=subentry_type,
                title=title,
                unique_id=None,
                subentry_id=uuid.uuid4().hex,
            ),
        )

    for dev in validated.get("devices", []):
        roles = dev.get("roles", {})
        has_bat = "battery" in roles
        has_mppt = "mppt" in roles
        has_inv = "inverter" in roles
        if has_bat and has_mppt and not has_inv:
            stype = "battery_mppt"
        elif has_bat and not has_mppt and not has_inv:
            stype = "battery"
        elif has_mppt and not has_bat and not has_inv:
            stype = "mppt"
        else:
            stype = "device"  # inverter role: editable by delete+recreate
        _add(stype, dict(dev), str(dev.get("name", "device")))
    for load in validated.get("loads", []):
        _add("load", dict(load), str(load.get("name", "load")))
    for meter in validated.get("meters", []):
        _add("meter", dict(meter), str(meter.get("name", "meter")))
    _LOGGER.info(
        "SolarBalance: migrated YAML to %d UI subentries — you can now remove the "
        "devices/meters/loads from configuration.yaml",
        len(entry.subentries),
    )


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options or subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Flush persisted state (talon, daily counters, history) before unloading —
    # the per-tick delayed save otherwise only lands on a clean HA shutdown, so a
    # reload would lose it.
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(entry_data, dict) and (coordinator := entry_data.get(COORDINATOR_KEY)):
        await coordinator.async_persist_now()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
