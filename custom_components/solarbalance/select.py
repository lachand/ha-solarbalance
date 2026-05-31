"""Select platform for SolarBalance — HEMS mode selector."""

import logging
from typing import ClassVar

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator
from .core.models import HemsMode

_LOGGER = logging.getLogger(__name__)

_DEVICE_INFO = DeviceInfo(identifiers={(DOMAIN, DOMAIN)}, name="SolarBalance")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance select entities from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    async_add_entities([SolarBalanceModeSelect(coordinator, entry)])


class SolarBalanceModeSelect(CoordinatorEntity[SolarBalanceCoordinator], SelectEntity):
    """Select entity for the global HEMS operating mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "hems_mode"
    _attr_icon = "mdi:cog"
    _attr_options: ClassVar[list[str]] = [m.value for m in HemsMode if m is not HemsMode.DEGRADED]

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_hems_mode"
        self._attr_device_info = _DEVICE_INFO

    @property
    def current_option(self) -> str:
        return self.coordinator.mode.value

    async def async_select_option(self, option: str) -> None:
        if option == HemsMode.STORM.value:
            # Route through activate_storm_mode so _storm_manual is set,
            # preventing immediate auto-exit on the next tick.
            self.coordinator.activate_storm_mode()
        else:
            self.coordinator.mode = HemsMode(option)
        self.async_write_ha_state()
