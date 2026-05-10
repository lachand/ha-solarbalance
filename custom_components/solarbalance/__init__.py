"""SolarBalance — Home Energy Management System integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

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


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Parse the YAML ``solarbalance:`` block if present and register services."""
    from .yaml_loader import parse_yaml_config

    hass.data.setdefault(DOMAIN, {})
    raw = config.get(DOMAIN)
    if raw:
        try:
            devices, meters, loads = parse_yaml_config(raw)
        except Exception as exc:
            _LOGGER.error("SolarBalance YAML error: %s", exc)
            return False
        hass.data[DOMAIN][YAML_CONFIG_KEY] = (devices, meters, loads)
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
            coord.mode = HemsMode(call.data["mode"])
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

    async def handle_activate_storm_mode(call: ServiceCall) -> None:
        coord = _get_coordinator(hass)
        if coord:
            coord.mode = HemsMode.STORM
            coord.async_update_listeners()

    hass.services.async_register(DOMAIN, "pause", handle_pause)
    hass.services.async_register(DOMAIN, "resume", handle_resume)
    hass.services.async_register(DOMAIN, "set_mode", handle_set_mode)
    hass.services.async_register(DOMAIN, "force_charge", handle_force_charge)
    hass.services.async_register(DOMAIN, "force_discharge", handle_force_discharge)
    hass.services.async_register(DOMAIN, "activate_storm_mode", handle_activate_storm_mode)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarBalance from a config entry."""
    from .coordinator import SolarBalanceCoordinator

    _LOGGER.debug("Setting up SolarBalance entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    yaml_cfg = hass.data[DOMAIN].get(YAML_CONFIG_KEY)
    devices, meters, loads = yaml_cfg if yaml_cfg else ([], [], [])

    coordinator = SolarBalanceCoordinator(hass, entry, devices, meters, loads)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {COORDINATOR_KEY: coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
