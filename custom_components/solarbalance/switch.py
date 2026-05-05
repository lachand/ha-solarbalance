"""Switch platform for SolarBalance — on/off toggles."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator

_LOGGER = logging.getLogger(__name__)

_DEVICE_INFO = DeviceInfo(identifiers={(DOMAIN, DOMAIN)}, name="SolarBalance")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance switch entities from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    async_add_entities([ZeroInjectionSwitch(coordinator, entry)])


class ZeroInjectionSwitch(CoordinatorEntity[SolarBalanceCoordinator], SwitchEntity):
    """Enable / disable the zero-injection PI controller."""

    _attr_has_entity_name = True
    _attr_translation_key = "zero_injection"
    _attr_icon = "mdi:transmission-tower-off"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_zero_injection"
        self._attr_device_info = _DEVICE_INFO

    @property
    def is_on(self) -> bool:
        return self.coordinator._zi_enabled

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._zi_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._zi_enabled = False
        self.async_write_ha_state()
