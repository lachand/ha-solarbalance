"""Sensor platform for SolarBalance.

Exposes the computed setpoints and system state as HA sensors so users can
observe decisions without any direct hardware control (v1 read-first model).

Sensors published:
- ``sensor.solarbalance_mode``               — current HEMS mode
- ``sensor.solarbalance_dominant_strategy``  — winning strategy this tick
- ``sensor.solarbalance_grid_power``         — last-read grid power (W)
- ``sensor.solarbalance_pv_power``           — total PV power (W)
- ``sensor.solarbalance_battery_power``      — aggregate battery power (W)
- ``sensor.solarbalance_baseline_consumption`` — deduced background load (W)
- ``sensor.solarbalance_{device}_setpoint_charge_w``   — per-battery charge setpoint (W)
- ``sensor.solarbalance_{device}_setpoint_discharge_w`` — per-battery discharge setpoint (W)
"""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator
from .core.models import Snapshot

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance sensors from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]

    entities: list[SensorEntity] = [
        SolarBalanceModeSensor(coordinator, entry),
        SolarBalanceDominantStrategySensor(coordinator, entry),
        SolarBalanceGridPowerSensor(coordinator, entry),
        SolarBalancePvPowerSensor(coordinator, entry),
        SolarBalanceBatteryPowerSensor(coordinator, entry),
        SolarBalanceBaselineConsumptionSensor(coordinator, entry),
    ]

    # Per-battery setpoint sensors
    for device in coordinator._devices:
        if device.battery is not None:
            entities += [
                SolarBalanceBatterySetpointSensor(coordinator, entry, device.name, "charge"),
                SolarBalanceBatterySetpointSensor(coordinator, entry, device.name, "discharge"),
            ]

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

_DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, DOMAIN)},
    name="SolarBalance",
    manufacturer="SolarBalance",
    model="HEMS v1",
)


class _SolarBalanceSensor(CoordinatorEntity[SolarBalanceCoordinator], SensorEntity):
    """Base sensor for SolarBalance."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = _DEVICE_INFO


# ---------------------------------------------------------------------------
# System-level sensors
# ---------------------------------------------------------------------------


class SolarBalanceModeSensor(_SolarBalanceSensor):
    """Current HEMS operating mode."""

    _attr_translation_key = "mode"
    _attr_icon = "mdi:cog-outline"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "mode")

    @property
    def native_value(self) -> str:
        return self.coordinator.mode.value


class SolarBalanceDominantStrategySensor(_SolarBalanceSensor):
    """Strategy that dominated the last arbitration."""

    _attr_translation_key = "dominant_strategy"
    _attr_icon = "mdi:strategy"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "dominant_strategy")

    @property
    def native_value(self) -> str | None:
        latest = self.coordinator.publisher.latest
        if latest is None:
            return None
        return latest.dominant_strategy


class SolarBalanceGridPowerSensor(_SolarBalanceSensor):
    """Grid power at PDL (positive = import)."""

    _attr_translation_key = "grid_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "grid_power")

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        return round(snap.grid_power_w, 1) if snap else None


class SolarBalancePvPowerSensor(_SolarBalanceSensor):
    """Total PV production power."""

    _attr_translation_key = "pv_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pv_power")

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        return round(snap.pv_total_w, 1) if snap else None


class SolarBalanceBatteryPowerSensor(_SolarBalanceSensor):
    """Aggregate battery power (positive = charging)."""

    _attr_translation_key = "battery_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "battery_power")

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        return round(snap.battery_power_total_w, 1) if snap else None


class SolarBalanceBaselineConsumptionSensor(_SolarBalanceSensor):
    """Deduced background (non-pilotable) consumption."""

    _attr_translation_key = "baseline_consumption"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "baseline_consumption")

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        return round(snap.baseline_consumption_w, 1) if snap else None


# ---------------------------------------------------------------------------
# Per-battery setpoint sensors
# ---------------------------------------------------------------------------


class SolarBalanceBatterySetpointSensor(_SolarBalanceSensor):
    """Computed charge or discharge setpoint for a single battery device."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        device_name: str,
        direction: str,  # "charge" or "discharge"
    ) -> None:
        suffix = f"{device_name}_{direction}"
        super().__init__(coordinator, entry, suffix)
        self._device_name = device_name
        self._direction = direction
        self._attr_translation_key = f"battery_setpoint_{direction}"
        self._attr_translation_placeholders = {"device": device_name}
        self._attr_icon = "mdi:battery-arrow-up" if direction == "charge" else "mdi:battery-arrow-down"

    @property
    def native_value(self) -> float | None:
        latest = self.coordinator.publisher.latest
        if latest is None:
            return None
        target = latest.decision.battery_targets.get(self._device_name)
        if target is None or target.preferred_power_w is None:
            return 0.0
        pw = target.preferred_power_w
        if self._direction == "charge":
            return round(max(0.0, pw), 1)
        return round(max(0.0, -pw), 1)
