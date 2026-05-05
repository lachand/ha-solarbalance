"""SolarBalance — Home Energy Management System integration."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator
from .yaml_loader import parse_yaml_config

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
]

# Key used to store the coordinator in hass.data[DOMAIN][entry_id]
COORDINATOR_KEY = "coordinator"
# Key used to store YAML-parsed config (devices, meters, loads) set by async_setup
YAML_CONFIG_KEY = "yaml_config"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Parse the YAML ``solarbalance:`` block if present."""
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
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarBalance from a config entry."""
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
