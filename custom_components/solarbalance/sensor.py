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
from datetime import datetime
from typing import ClassVar

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
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator
from .core.models import Chemistry, Snapshot, estimate_soh_pct

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance sensors from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]

    # Service-level sensors live on the main HEMS device (no subentry).
    entities: list[SensorEntity] = [
        SolarBalanceModeSensor(coordinator, entry),
        SolarBalanceDominantStrategySensor(coordinator, entry),
        SolarBalanceGridPowerSensor(coordinator, entry),
        SolarBalancePvPowerSensor(coordinator, entry),
        SolarBalanceBatteryPowerSensor(coordinator, entry),
        SolarBalanceBaselineConsumptionSensor(coordinator, entry),
        SolarBalanceBatterySocAvgSensor(coordinator, entry),
        SolarBalanceBatteryRemainingSensor(coordinator, entry),
        SolarBalanceBatteryUsableSensor(coordinator, entry),
        SolarBalanceTimeToFullSensor(coordinator, entry),
        SolarBalanceTimeToEmptySensor(coordinator, entry),
        SolarBalancePvEnergyTodaySensor(coordinator, entry),
        SolarBalanceGridImportTodaySensor(coordinator, entry),
        SolarBalanceGridExportTodaySensor(coordinator, entry),
        SolarBalanceConsumptionTodaySensor(coordinator, entry),
        SolarBalancePvRemainingTodaySensor(coordinator, entry),
        SolarBalanceBaselineNightSensor(coordinator, entry),
        SolarBalanceDailyCostSensor(coordinator, entry),
        SolarBalanceDailySavingsSensor(coordinator, entry),
        SolarBalanceSavingsMonthSensor(coordinator, entry),
        SolarBalanceSavingsYearSensor(coordinator, entry),
        SolarBalanceCurrentImportPriceSensor(coordinator, entry),
    ]

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
        SolarBalanceRegulationDiagnosticSensor(
            coordinator, entry, "natural_grid_w", "natural_grid", "mdi:transmission-tower"
        ),
        SolarBalanceRegulationBindingSensor(coordinator, entry),
        SolarBalanceConsumptionForecastSensor(coordinator, entry),
        SolarBalanceConsumptionForecastErrorSensor(coordinator, entry),
    ]
    if coordinator._curtailment is not None:
        entities.append(
            SolarBalanceRegulationDiagnosticSensor(
                coordinator, entry, "pv_limit_w", "pv_output_limit", "mdi:solar-power-variant"
            )
        )
    if coordinator._zi_tuner is not None:
        entities.append(SolarBalanceAutotuneKpSensor(coordinator, entry))
    if coordinator._eq_tuner is not None:
        entities.append(
            SolarBalanceRegulationDiagnosticSensor(
                coordinator,
                entry,
                "autotune_equaliser_step_w",
                "autotune_equaliser_step",
                "mdi:tune-variant",
            )
        )
    # SoC-equaliser PV-routing observability: the PV a full battery hides (estimated
    # from the peer inverter) and the back-off factor throttling the routing.
    if coordinator._soc_equaliser is not None:
        entities += [
            SolarBalanceRegulationDiagnosticSensor(
                coordinator, entry, "eq_hidden_pv_w", "eq_hidden_pv", "mdi:solar-power"
            ),
            SolarBalanceEqPvRouteRelaxSensor(coordinator, entry),
        ]

    # Advisory predictive plan (observation only) — when a controllable fleet exists.
    if coordinator._scheduler is not None:
        entities += [
            SolarBalancePlannerRecommendedPowerSensor(coordinator, entry),
            SolarBalancePlannerExpectedCostSensor(coordinator, entry),
        ]

    async_add_entities(entities)

    # Per-battery setpoint + state sensors, attached to the device's UI subentry
    # so they group under that device (instead of "no sub-entry"). Falls back to
    # the main device when the equipment came from YAML (no subentry).
    sub_by_name = {
        sub.data["name"]: sub_id for sub_id, sub in entry.subentries.items() if sub.data.get("name")
    }
    for device in coordinator._devices:
        if device.battery is None and device.mppt is None:
            continue
        # MPPT sensors group with the battery device on a combined unit, else on a
        # dedicated per-inverter sub-device (so an MPPT-only device is not empty).
        dev_info = (
            _battery_device_info(entry, device.name)
            if device.battery is not None
            else _mppt_device_info(entry, device.name)
        )
        dev_entities: list[SensorEntity] = []
        if device.battery is not None:
            dev_entities += [
                SolarBalanceBatterySetpointSensor(coordinator, entry, device.name, "charge"),
                SolarBalanceBatterySetpointSensor(coordinator, entry, device.name, "discharge"),
                SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "soc"),
                SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "power"),
            ]
            if device.battery.temperature_entity is not None:
                dev_entities.append(
                    SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "temperature")
                )
            if device.battery.cycles_entity is not None:
                dev_entities += [
                    SolarBalanceBatteryMetricSensor(coordinator, entry, device.name, "cycles"),
                    SolarBalanceBatterySohSensor(coordinator, entry, device.name),
                ]
        if device.mppt is not None:
            dev_entities.append(
                SolarBalanceMpptPowerSensor(coordinator, entry, device.name, dev_info)
            )
            if device.mppt.temperature_entity is not None:
                dev_entities.append(
                    SolarBalanceMpptTemperatureSensor(coordinator, entry, device.name, dev_info)
                )
            # PV output limit is only meaningful for a curtailable inverter.
            if device.mppt.active_control_enabled and (
                device.mppt.power_limit_setpoint_entity is not None
            ):
                dev_entities.append(
                    SolarBalanceMpptLimitSensor(coordinator, entry, device.name, dev_info)
                )
        sub_id = sub_by_name.get(device.name)
        if sub_id is not None:
            async_add_entities(dev_entities, config_subentry_id=sub_id)
        else:
            async_add_entities(dev_entities)

    # Per-load: energy delivered today + current status, grouped under the load.
    for load in coordinator._loads:
        load_entities: list[SensorEntity] = [
            SolarBalanceLoadEnergyTodaySensor(coordinator, entry, load.name),
            SolarBalanceLoadStatusSensor(coordinator, entry, load.name),
        ]
        sub_id = sub_by_name.get(load.name)
        if sub_id is not None:
            async_add_entities(load_entities, config_subentry_id=sub_id)
        else:
            async_add_entities(load_entities)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


def _main_device_info(version: str | None) -> DeviceInfo:
    """Main HEMS device; ``sw_version`` is read from the manifest at setup."""
    return DeviceInfo(
        identifiers={(DOMAIN, DOMAIN)},
        name="SolarBalance",
        manufacturer="SolarBalance",
        model="HEMS",
        sw_version=version,
    )


def _battery_device_info(entry: ConfigEntry, device_name: str) -> DeviceInfo:
    """A per-battery sub-device so its sensors group together (language-agnostic)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_battery_{device_name}")},
        name=device_name,
        manufacturer="SolarBalance",
        via_device=(DOMAIN, DOMAIN),
    )


def _mppt_device_info(entry: ConfigEntry, device_name: str) -> DeviceInfo:
    """A per-inverter sub-device for an MPPT-only device (no battery role)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_mppt_{device_name}")},
        name=device_name,
        manufacturer="SolarBalance",
        via_device=(DOMAIN, DOMAIN),
    )


def _load_device_info(entry: ConfigEntry, load_name: str) -> DeviceInfo:
    """Per-load sub-device (shared with the load's control switches)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_load_{load_name}")},
        name=load_name,
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
        self._attr_device_info = device_info or _main_device_info(coordinator.version)


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

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"reason": self.coordinator.decision_reason}


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

    # The hourly forecast is large and rewritten every tick — keep it live but
    # out of the recorder history.
    _unrecorded_attributes = frozenset({"pv_forecast_hourly"})
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
        # Capacity-weighted (energy-true): a small full pack and a large empty one
        # must not average to a misleading 50 %. See coordinator.
        weighted = self.coordinator.weighted_battery_soc_pct()
        return round(weighted, 1) if weighted is not None else None


class SolarBalanceBatteryRemainingSensor(_SolarBalanceSensor):
    """Stored usable energy currently held across all available batteries (kWh)."""

    _attr_translation_key = "battery_remaining"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-charging-high"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "battery_remaining")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.remaining_battery_energy_kwh()


class SolarBalanceBatteryUsableSensor(_SolarBalanceSensor):
    """Exploitable energy window across all available batteries (kWh)."""

    _attr_translation_key = "battery_usable"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "battery_usable")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.usable_battery_window_kwh()


class SolarBalanceTimeToFullSensor(_SolarBalanceSensor):
    """Estimated time to fill the fleet at the current charge power (h).

    ``unknown`` while the fleet is not charging — there is no meaningful estimate then.
    """

    _attr_translation_key = "time_to_full"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-clock"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "time_to_full")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.time_to_full_h


class SolarBalanceTimeToEmptySensor(_SolarBalanceSensor):
    """Estimated time to the SoC floor at the current discharge power (h).

    ``unknown`` while the fleet is not discharging.
    """

    _attr_translation_key = "time_to_empty"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-clock-outline"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "time_to_empty")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.time_to_empty_h


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


class SolarBalanceConsumptionTodaySensor(_SolarBalanceSensor):
    """Total house consumption energy today (pv + grid - battery), integrated."""

    _attr_translation_key = "consumption_today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "consumption_today")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.daily_consumption_kwh


class SolarBalanceDailyCostSensor(_SolarBalanceSensor):
    """Today's net grid cost in euros (import cost minus export revenue)."""

    _attr_translation_key = "daily_cost"
    _attr_native_unit_of_measurement = "EUR"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-minus"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "daily_cost")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.daily_cost_eur

    @property
    def extra_state_attributes(self) -> dict[str, float]:
        return {
            "import_cost_eur": self.coordinator.daily_import_cost_eur,
            "export_revenue_eur": self.coordinator.daily_export_revenue_eur,
        }


class SolarBalanceDailySavingsSensor(_SolarBalanceSensor):
    """Today's value created by PV + battery (avoided import + export revenue)."""

    _unrecorded_attributes = frozenset({"history"})
    _attr_translation_key = "daily_savings"
    _attr_native_unit_of_measurement = "EUR"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:piggy-bank"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "daily_savings")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.daily_savings_eur

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        history = self.coordinator.daily_history
        return {"history": history} if history else None


class SolarBalanceCurrentImportPriceSensor(_SolarBalanceSensor):
    """Current import price from the active tariff (EUR/kWh)."""

    _attr_translation_key = "current_import_price"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-clock"
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_import_price")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.current_import_price

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        return {"time_varying": self.coordinator.tariff_time_varying}


class SolarBalanceSavingsMonthSensor(_SolarBalanceSensor):
    """Cumulative estimated savings for the current calendar month (EUR).

    ``state_class=TOTAL`` + ``last_reset`` (1st of the month) so it integrates
    natively into the Home Assistant Energy dashboard.
    """

    _attr_translation_key = "savings_month"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-multiple"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "savings_month")

    @property
    def native_value(self) -> float:
        return self.coordinator.savings_month_eur

    @property
    def last_reset(self) -> datetime | None:
        return self.coordinator.savings_month_start


class SolarBalanceSavingsYearSensor(_SolarBalanceSensor):
    """Cumulative estimated savings for the current calendar year (EUR).

    ``state_class=TOTAL`` + ``last_reset`` (Jan 1st) for Energy-dashboard use.
    """

    _attr_translation_key = "savings_year"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-multiple"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "savings_year")

    @property
    def native_value(self) -> float:
        return self.coordinator.savings_year_eur

    @property
    def last_reset(self) -> datetime | None:
        return self.coordinator.savings_year_start


class SolarBalanceLoadEnergyTodaySensor(_SolarBalanceSensor):
    """Energy delivered to a controllable load since local midnight (kWh)."""

    _attr_translation_key = "load_energy_today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, load_name: str
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"load_{load_name}_energy_today",
            device_info=_load_device_info(entry, load_name),
        )
        self._load_name = load_name

    @property
    def native_value(self) -> float:
        return self.coordinator.load_energy_today_kwh(self._load_name)


class SolarBalanceLoadStatusSensor(_SolarBalanceSensor):
    """Current control status of a load (enum, translated by the frontend)."""

    _attr_translation_key = "load_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = [
        "active",
        "inactive",
        "shed",
        "off_peak_wait",
        "force_charge",
        "unknown",
    ]
    _attr_icon = "mdi:power-plug"

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, load_name: str
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"load_{load_name}_status",
            device_info=_load_device_info(entry, load_name),
        )
        self._load_name = load_name

    @property
    def native_value(self) -> str:
        return self.coordinator.load_status(self._load_name)


class SolarBalancePvRemainingTodaySensor(_SolarBalanceSensor):
    """Forecast PV energy still expected before midnight today (kWh)."""

    _attr_translation_key = "pv_remaining_today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:solar-power"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pv_remaining_today")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.remaining_pv_today_kwh


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
        # Prefer the value actually written (post SoC-cut and discharge-mirror) so a
        # mirrored group (e.g. STREAM) shows the same discharge on each member, not the
        # balancer's internal per-battery split.
        written = self.coordinator._active_control.last_setpoint_w(
            self._device_name, charge=self._direction == "charge"
        )
        if written is not None:
            return round(written, 1)
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


_BATTERY_METRIC_META: dict[str, tuple[str | None, SensorDeviceClass | None]] = {
    "soc": (PERCENTAGE, SensorDeviceClass.BATTERY),
    "power": (UnitOfPower.WATT, SensorDeviceClass.POWER),
    "temperature": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "cycles": (None, None),
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
        if self._metric == "cycles":
            return round(state.cycles, 0) if state.cycles is not None else None
        return round(state.temperature_c, 1) if state.temperature_c is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, bool] | None:
        # Expose staleness so the UI can flag a battery whose SoC/power stopped
        # refreshing (e.g. a cloud station in timeout) — shown amber on the panel.
        snap: Snapshot | None = self.coordinator.data
        if snap is None:
            return None
        state = next((b for b in snap.batteries if b.device_name == self._device_name), None)
        if state is None:
            return None
        return {"stale": state.stale}


class SolarBalanceBatterySohSensor(_SolarBalanceSensor):
    """Estimated battery State of Health (%) from the reported cycle count."""

    _attr_translation_key = "batt_soh"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, device_name: str
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"{device_name}_soh",
            device_info=_battery_device_info(entry, device_name),
        )
        self._device_name = device_name
        self._chemistry = next(
            (
                d.battery.chemistry
                for d in coordinator._devices
                if d.name == device_name and d.battery is not None
            ),
            Chemistry.OTHER,
        )

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        if snap is None:
            return None
        state = next((b for b in snap.batteries if b.device_name == self._device_name), None)
        if state is None or not state.available:
            return None
        return estimate_soh_pct(state.cycles, self._chemistry)


class SolarBalanceMpptPowerSensor(_SolarBalanceSensor):
    """Per-inverter PV output power (W)."""

    _attr_translation_key = "mppt_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:solar-power"

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        device_name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator, entry, f"{device_name}_pv_power", device_info=device_info)
        self._device_name = device_name

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        if snap is None:
            return None
        state = next((m for m in snap.mppts if m.device_name == self._device_name), None)
        if state is None or not state.available:
            return None
        return round(state.power_w, 1)


class SolarBalanceMpptTemperatureSensor(_SolarBalanceSensor):
    """Per-inverter temperature (°C)."""

    _attr_translation_key = "mppt_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        device_name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator, entry, f"{device_name}_pv_temperature", device_info=device_info
        )
        self._device_name = device_name

    @property
    def native_value(self) -> float | None:
        snap: Snapshot | None = self.coordinator.data
        if snap is None:
            return None
        state = next((m for m in snap.mppts if m.device_name == self._device_name), None)
        if state is None or not state.available or state.temperature_c is None:
            return None
        return round(state.temperature_c, 1)


class SolarBalanceMpptLimitSensor(_SolarBalanceSensor):
    """Per-inverter PV output limit applied by curtailment (W, diagnostic).

    Sits at the inverter peak when unrestricted and drops only when the batteries
    are saturated and the grid would otherwise export (curtailment is a last
    resort, after the batteries have stored what they can).
    """

    _attr_translation_key = "mppt_limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:solar-power-variant"

    def __init__(
        self,
        coordinator: SolarBalanceCoordinator,
        entry: ConfigEntry,
        device_name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator, entry, f"{device_name}_pv_limit", device_info=device_info)
        self._device_name = device_name

    @property
    def native_value(self) -> float | None:
        value = self.coordinator._pv_limits_by_device.get(self._device_name)
        return round(value, 1) if value is not None else None


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


class SolarBalanceEqPvRouteRelaxSensor(_SolarBalanceSensor):
    """SoC-equaliser PV-routing allowance (%, diagnostic).

    100 % = routing fully open; lower = backed off because the cloud battery is not
    absorbing the routed PV (the grid kept exporting), down to 0 % (routing throttled).
    """

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "eq_pv_route_relax"
    _attr_icon = "mdi:valve"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "diag_eq_pv_route_relax")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.diagnostics.eq_pv_route_relax * 100.0, 0)


class SolarBalanceConsumptionForecastSensor(_SolarBalanceSensor):
    """Learned typical background consumption for the current hour (W, diagnostic).

    Fills in as the hour-of-day profile is learned (unavailable until that hour has
    data); lets you see the prediction the planner uses.
    """

    _attr_translation_key = "consumption_forecast_now"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "diag_consumption_forecast_now")

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.predicted_consumption_now_w
        return round(value, 1) if value is not None else None


class SolarBalanceConsumptionForecastErrorSensor(_SolarBalanceSensor):
    """Forecast minus actual background consumption (W, diagnostic).

    Positive = the profile over-predicted, negative = under-predicted; near 0 means
    the learned profile tracks reality. Unavailable until the current hour is learned.
    """

    _attr_translation_key = "consumption_forecast_error"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:scale-unbalanced"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "diag_consumption_forecast_error")

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.consumption_forecast_error_w
        return round(value, 1) if value is not None else None


class SolarBalanceRegulationBindingSensor(_SolarBalanceSensor):
    """Which clamp set the fleet target this tick (diagnostic, text).

    One of: base / equaliser / no_export / no_charge_floor / no_feed / eq_pv_route /
    cloud_relief / grid_import / grid_export. Makes a surprising target self-explanatory
    (``eq_pv_route`` = the equaliser is routing the fleet's PV to a lower-SoC cloud
    battery; ``cloud_relief`` = at night the fleet covers the home so a lower-SoC cloud
    battery stops discharging into it — neither is being blocked).
    """

    _attr_translation_key = "regulation_binding"
    _attr_icon = "mdi:format-list-bulleted"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "diag_regulation_binding")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.regulation_binding


class SolarBalanceAutotuneKpSensor(_SolarBalanceSensor):
    """Auto-tuned zero-injection proportional gain (diagnostic, unitless)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:tune"
    _attr_translation_key = "autotune_zi_kp"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "autotune_zi_kp")

    @property
    def native_value(self) -> float:
        return round(float(self.coordinator.diagnostics.autotune_zi_kp), 3)


# ---------------------------------------------------------------------------
# Advisory predictive plan (observation only)
# ---------------------------------------------------------------------------


class SolarBalancePlannerRecommendedPowerSensor(_SolarBalanceSensor):
    """Battery power the advisory planner recommends for the current slot (W)."""

    _unrecorded_attributes = frozenset({"schedule"})

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

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Expose the hourly schedule so the panel can chart/tabulate it."""
        plan = self.coordinator.advisory_plan
        if plan is None or not plan.schedule:
            return None
        return {
            "schedule": [
                {
                    "start": slot.start.isoformat(),
                    "battery_power_w": round(slot.battery_power_w, 0),
                    "expected_grid_w": round(slot.expected_grid_w, 0),
                    "soc_end_pct": round(slot.soc_end_pct, 1),
                    "expected_cost_eur": round(slot.expected_cost_eur, 3),
                }
                for slot in plan.schedule
            ],
        }


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
