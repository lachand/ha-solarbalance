"""Binary sensor platform for SolarBalance."""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator
from .core.models import HemsMode, Snapshot

_LOGGER = logging.getLogger(__name__)

_DEVICE_INFO = DeviceInfo(identifiers={(DOMAIN, DOMAIN)}, name="SolarBalance")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance binary_sensor entities from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    async_add_entities([
        StormModeBinarySensor(coordinator, entry),
        WeatherWarningBinarySensor(coordinator, entry),
        DegradedBinarySensor(coordinator, entry),
    ])


class _SBBinarySensor(CoordinatorEntity[SolarBalanceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, suffix: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = _DEVICE_INFO


class StormModeBinarySensor(_SBBinarySensor):
    """True when the HEMS is in storm-preparation mode."""

    _attr_translation_key = "storm_mode"
    _attr_icon = "mdi:weather-lightning"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "storm_mode")

    @property
    def is_on(self) -> bool:
        return self.coordinator.mode is HemsMode.STORM


class WeatherWarningBinarySensor(_SBBinarySensor):
    """True when a Météo-France weather warning is active."""

    _attr_translation_key = "weather_warning"
    _attr_icon = "mdi:weather-cloudy-alert"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "weather_warning")

    @property
    def is_on(self) -> bool:
        snap: Snapshot | None = self.coordinator.data
        return snap.weather_warning_active if snap else False


class DegradedBinarySensor(_SBBinarySensor):
    """True when the HEMS is in degraded mode (stale critical entities)."""

    _attr_translation_key = "degraded"
    _attr_icon = "mdi:alert-circle"
    _attr_device_class = None

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "degraded")

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_degraded
