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
- ``sensor.solarbalance_battery_soc_avg``    — average SoC across batteries (%)
- ``sensor.solarbalance_pv_energy_today``    — daily PV energy (kWh, optional)
- ``sensor.solarbalance_grid_import_today``  — daily grid import (kWh, optional)
- ``sensor.solarbalance_{device}_setpoint_charge``   — per-battery charge setpoint (W)
- ``sensor.solarbalance_{device}_setpoint_discharge`` — per-battery discharge setpoint (W)
"""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
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
        SolarBalanceBatterySocAvgSensor(coordinator, entry),
        SolarBalancePvEnergyTodaySensor(coordinator, entry),
        SolarBalanceGridImportTodaySensor(coordinator, entry),
        SolarBalanceGridExportTodaySensor(coordinator, entry),
        SolarBalanceBaselineNightSensor(coordinator, entry),
    ]

    # Per-battery setpoint + state (SoC / power / temperature) sensors
    for device in coordinator._devices:
        if device.battery is not None:
            entities += [
                SolarBalanceBatterySetpointSensor(coordinator, entry, device.name, "charge"),
                SolarBalanceBatterySetpointSensor(coordinator, entry, device.name, "discharge"),
                SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "soc"),
                SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "power"),
            ]
            if device.battery.temperature_entity is not None:
                entities.append(
                    SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "temperature")
                )

    # Regulation diagnostics (help tune the loop; entity-category diagnostic)
    entities += [
        SolarBalanceRegulationDiagnosticSensor(
            coordinator, entry, "fleet_target_w", "regulation_target", "mdi:target"
        ),
        SolarBalanceRegulationDiagnosticSensor(
            coordinator, entry, "zero_injection_correction_w", "zi_correction", "mdi:sine-wave"
        ),
        SolarBalanceRegulationDiagnosticSensor(
            coordinator, entry, "equaliser_offer_w", "equaliser_offer", "mdi:scale-balance"
        ),
        SolarBalanceRegulationDiagnosticSensor(
            coordinator, entry, "grid_filtered_w", "grid_filtered", "mdi:filter-variant"
        ),
    ]
    if coordinator._curtailment is not None:
        entities.append(
            SolarBalanceRegulationDiagnosticSensor(
                coordinator, entry, "pv_limit_w", "pv_output_limit", "mdi:solar-power-variant"
            )
        )

    # Advisory predictive plan (observation only) — when a controllable fleet exists.
    if coordinator._scheduler is not None:
        entities += [
            SolarBalancePlannerRecommendedPowerSensor(coordinator, entry),
            SolarBalancePlannerExpectedCostSensor(coordinator, entry),
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


def _battery_device_info(entry: ConfigEntry, device_name: str) -> DeviceInfo:
    """A per-battery sub-device so its sensors group together (language-agnostic)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_battery_{device_name}")},
        name=device_name,
        manufacturer="SolarBalance",
        via_device=(DOMAIN, DOMAIN),
    )


class _SolarBalanceSensor(CoordinatorEntity[SolarBalanceCoordinator], SensorEntity):
    """Base sensor for SolarBalance."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
        *,
        device_info: DeviceInfo | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = device_info or _DEVICE_INFO


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

    @property
    def extra_state_attributes(self) -> dict[str, float] | None:
        """Expose subscribed grid power so the panel can draw a load gauge."""
        sub = self.coordinator.subscribed_power_w
        return {"subscribed_power_w": sub} if sub is not None else None


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

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Expose the hourly PV forecast so the panel can overlay it."""
        fc = self.coordinator.pv_forecast_hourly
        return {"pv_forecast_hourly": fc} if fc else None


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
# SoC average + daily energy sensors
# ---------------------------------------------------------------------------


class SolarBalanceBatterySocAvgSensor(_SolarBalanceSensor):
    """Average state of charge across all available batteries."""

    _attr_translation_key = "battery_soc_avg"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-medium"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "battery_soc_avg")

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        if snap is None:
            return None
        available = [b.soc_pct for b in snap.batteries if b.available]
        if not available:
            return None
        return round(sum(available) / len(available), 1)


class SolarBalancePvEnergyTodaySensor(_SolarBalanceSensor):
    """Total PV energy produced today (sum of all MPPT daily_energy_entity values)."""

    _attr_translation_key = "pv_energy_today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:solar-power"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pv_energy_today")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.daily_pv_energy_kwh


class SolarBalanceGridImportTodaySensor(_SolarBalanceSensor):
    """Grid energy imported today (from PDL meter daily_import_energy_entity)."""

    _attr_translation_key = "grid_import_today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:transmission-tower-import"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "grid_import_today")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.daily_grid_import_kwh


class SolarBalanceBaselineNightSensor(_SolarBalanceSensor):
    """Standby baseline (talon) averaged over the quiet night window (W)."""

    _attr_translation_key = "baseline_night"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:sleep"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "baseline_night")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.baseline_night_w


class SolarBalanceGridExportTodaySensor(_SolarBalanceSensor):
    """Grid energy exported (injected) today, integrated internally."""

    _attr_translation_key = "grid_export_today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:transmission-tower-export"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "grid_export_today")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.daily_grid_export_kwh


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
        super().__init__(
            coordinator, entry, suffix, device_info=_battery_device_info(entry, device_name)
        )
        self._device_name = device_name
        self._direction = direction
        self._attr_translation_key = f"battery_setpoint_{direction}"
        self._attr_icon = (
            "mdi:battery-arrow-up" if direction == "charge" else "mdi:battery-arrow-down"
        )

    @property
    def native_value(self) -> float | None:
        balancing = self.coordinator.publisher.latest_balancing
        if balancing is not None:
            pw = balancing.per_battery_w.get(self._device_name, 0.0)
            if self._direction == "charge":
                return round(max(0.0, pw), 1)
            return round(max(0.0, -pw), 1)
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


_BATTERY_METRIC_META: dict[str, tuple[str, SensorDeviceClass]] = {
    "soc": (PERCENTAGE, SensorDeviceClass.BATTERY),
    "power": (UnitOfPower.WATT, SensorDeviceClass.POWER),
    "temperature": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
}


class SolarBalanceBatteryMetricSensor(_SolarBalanceSensor):
    """Per-device battery state (SoC %, power W, or temperature °C)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        device_name: str,
        metric: str,  # "soc" | "power" | "temperature"
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"{device_name}_{metric}",
            device_info=_battery_device_info(entry, device_name),
        )
        self._device_name = device_name
        self._metric = metric
        unit, device_class = _BATTERY_METRIC_META[metric]
        self._attr_translation_key = f"batt_{metric}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        if snap is None:
            return None
        state = next((b for b in snap.batteries if b.device_name == self._device_name), None)
        if state is None or not state.available:
            return None
        if self._metric == "soc":
            return round(state.soc_pct, 1)
        if self._metric == "power":
            return round(state.power_w, 1)
        return round(state.temperature_c, 1) if state.temperature_c is not None else None


# ---------------------------------------------------------------------------
# Regulation diagnostics
# ---------------------------------------------------------------------------


class SolarBalanceRegulationDiagnosticSensor(_SolarBalanceSensor):
    """Internal regulation value from the last tick (diagnostic, in W)."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        attr: str,
        translation_key: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator, entry, f"diag_{attr}")
        self._diag_attr = attr
        self._attr_translation_key = translation_key
        self._attr_icon = icon

    @property
    def native_value(self) -> float:
        return round(float(getattr(self.coordinator.diagnostics, self._diag_attr)), 1)


# ---------------------------------------------------------------------------
# Advisory predictive plan (observation only)
# ---------------------------------------------------------------------------


class SolarBalancePlannerRecommendedPowerSensor(_SolarBalanceSensor):
    """Battery power the advisory planner recommends for the current slot (W)."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chart-timeline-variant"

    _attr_translation_key = "planner_recommended_power"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "planner_recommended_power")

    @property
    def native_value(self) -> float | None:
        plan = self.coordinator.advisory_plan
        return round(plan.first_setpoint_w, 1) if plan is not None else None


class SolarBalancePlannerExpectedCostSensor(_SolarBalanceSensor):
    """Expected electricity cost over the planning horizon (EUR; negative = revenue)."""

    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cash"
    _attr_suggested_display_precision = 2
    _attr_translation_key = "planner_expected_cost"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "planner_expected_cost")

    @property
    def native_value(self) -> float | None:
        plan = self.coordinator.advisory_plan
        return round(plan.total_cost_eur, 2) if plan is not None else None
