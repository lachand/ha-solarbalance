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
        EveningShedBinarySensor(coordinator, entry),
        EvFastChargeBinarySensor(coordinator, entry),
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


class EveningShedBinarySensor(_SBBinarySensor):
    """True when big loads are being shed to prioritise battery charging."""

    _attr_translation_key = "evening_shed"
    _attr_icon = "mdi:transmission-tower-off"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "evening_shed")

    @property
    def is_on(self) -> bool:
        shed = self.coordinator.evening_shed
        return bool(shed and shed.active)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        shed = self.coordinator.evening_shed
        if shed is None:
            return None
        return {
            "shed_loads": sorted(shed.shed_load_names),
            "battery_deficit_kwh": round(shed.deficit_kwh, 2),
            "pv_for_charge_kwh": round(shed.pv_for_charge_kwh, 2),
            "reason": shed.reason,
        }


class EvFastChargeBinarySensor(_SBBinarySensor):
    """True when an EV is being fast-charged with battery assistance."""

    _attr_translation_key = "ev_fast_charge"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ev_fast_charge")

    @property
    def is_on(self) -> bool:
        return any(d.reason == "assist" for d in self.coordinator.fast_charge.values())

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        decisions = self.coordinator.fast_charge
        if not decisions:
            return None
        return {
            name: {
                "target_w": round(d.target_w, 0),
                "reason": d.reason,
                "gate_ok": d.gate_ok,
                "battery_deficit_kwh": round(d.battery_deficit_kwh, 2),
                "pv_recovery_kwh": round(d.pv_recovery_kwh, 2),
            }
            for name, d in decisions.items()
        }
