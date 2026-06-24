"""Number platform for SolarBalance — tunable parameters."""

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator
from .core.controllers.zero_injection import (
    PerPhaseZeroInjectionController,
    ZeroInjectionController,
)

_LOGGER = logging.getLogger(__name__)

_DEVICE_INFO = DeviceInfo(identifiers={(DOMAIN, DOMAIN)}, name="SolarBalance")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance number entities from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    async_add_entities(
        [
            ZeroInjectionSetpointNumber(coordinator, entry),
            ZeroInjectionHysteresisNumber(coordinator, entry),
            ManualChargePowerNumber(coordinator, entry),
        ]
    )


class _SBNumber(CoordinatorEntity[SolarBalanceCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, suffix: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = _DEVICE_INFO


class ZeroInjectionSetpointNumber(_SBNumber):
    """Target grid power setpoint for zero-injection control (W)."""

    _attr_translation_key = "zi_setpoint"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = -500.0
    _attr_native_max_value = 500.0
    _attr_native_step = 10.0
    _attr_icon = "mdi:target"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "zi_setpoint")

    @property
    def native_value(self) -> float:
        return self.coordinator._zi_setpoint_w

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator._zi_setpoint_w = value
        self.async_write_ha_state()


class ManualChargePowerNumber(_SBNumber):
    """Manual grid charge/discharge power for testing (W).

    ``> 0`` charges the controllable fleet from the grid at that power, ``< 0``
    discharges to the grid, ``0`` returns to normal. Drives the existing
    ``MANUAL_OVERRIDE`` mode (zero-injection OFF), so you can see exactly how the
    batteries respond to a forced setpoint — e.g. test a night-time grid charge.
    The setpoint is still written through the normal active-control path (mode-switch
    sequence included), so it tests the real write chain, not a raw bypass.
    """

    _attr_translation_key = "manual_charge_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = -3000.0
    _attr_native_max_value = 3000.0
    _attr_native_step = 10.0
    _attr_icon = "mdi:hand-back-right"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "manual_charge_power")

    @property
    def native_value(self) -> float:
        ovr = self.coordinator._battery_override
        if ovr is None:
            return 0.0
        power = float(ovr.power_w or 0.0)
        return power if ovr.kind == "charge" else -power

    async def async_set_native_value(self, value: float) -> None:
        if abs(value) < 1.0:
            self.coordinator.clear_force_override()
        elif value > 0:
            # target_soc 100 % so it keeps charging for the whole test.
            self.coordinator.set_force_override(kind="charge", target_soc_pct=100.0, power_w=value)
        else:
            self.coordinator.set_force_override(
                kind="discharge", target_soc_pct=0.0, power_w=-value
            )
        self.async_write_ha_state()


class ZeroInjectionHysteresisNumber(_SBNumber):
    """Deadband width around the ZI setpoint (W)."""

    _attr_translation_key = "zi_hysteresis"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = 0.0
    _attr_native_max_value = 500.0
    _attr_native_step = 10.0
    _attr_icon = "mdi:arrow-expand-horizontal"

    def __init__(self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "zi_hysteresis")
        ctrl = coordinator._zi_controller
        self._value: float = (
            ctrl._ctrl._hysteresis_w
            if isinstance(ctrl, PerPhaseZeroInjectionController)
            else ctrl._hysteresis_w
        )

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        ctrl = self.coordinator._zi_controller
        if isinstance(ctrl, PerPhaseZeroInjectionController):
            # Per-phase controller: kp/ki/clamp are on the inner _ctrl instance.
            inner = ctrl._ctrl
            self.coordinator._zi_controller = PerPhaseZeroInjectionController(
                kp=inner._kp,
                ki=inner._ki,
                hysteresis_w=value,
                integral_clamp_w_s=inner._integral_clamp,
            )
        else:
            self.coordinator._zi_controller = ZeroInjectionController(
                kp=ctrl._kp,
                ki=ctrl._ki,
                hysteresis_w=value,
                integral_clamp_w_s=ctrl._integral_clamp,
            )
        self.async_write_ha_state()
