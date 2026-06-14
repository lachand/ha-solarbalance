"""Switch platform for SolarBalance — on/off toggles."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import COORDINATOR_KEY
from .const import DOMAIN
from .coordinator import SolarBalanceCoordinator

_LOGGER = logging.getLogger(__name__)

_DEVICE_INFO = DeviceInfo(identifiers={(DOMAIN, DOMAIN)}, name="SolarBalance")


def _load_device_info(entry: ConfigEntry, load_name: str) -> DeviceInfo:
    """A per-load sub-device so its controls group together (language-agnostic)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_load_{load_name}")},
        name=load_name,
        manufacturer="SolarBalance",
        via_device=(DOMAIN, DOMAIN),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolarBalance switch entities from a config entry."""
    coordinator: SolarBalanceCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_KEY]
    async_add_entities([ZeroInjectionSwitch(coordinator, entry)])

    # Per-load "do not shed" override, attached to the load's UI subentry when it
    # has one (so it groups under that load), else the main device.
    sub_by_name = {
        sub.data["name"]: sub_id
        for sub_id, sub in entry.subentries.items()
        if sub.data.get("name")
    }
    for load in coordinator._loads:
        switches: list[SwitchEntity] = [LoadForceChargeSwitch(coordinator, entry, load.name)]
        if load.interruptible:
            switches.append(LoadShedExemptSwitch(coordinator, entry, load.name))
        sub_id = sub_by_name.get(load.name)
        if sub_id is not None:
            async_add_entities(switches, config_subentry_id=sub_id)
        else:
            async_add_entities(switches)


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


class LoadShedExemptSwitch(
    CoordinatorEntity[SolarBalanceCoordinator], SwitchEntity, RestoreEntity
):
    """Temporarily exempt a load from shedding (evening-shed + fast-charge pause).

    When on, the load is never forced off for battery priority nor paused for
    charging inefficiency — e.g. "charge my car now". It still only runs on the
    surplus the dispatcher allocates; it is not force-charged from the grid.
    The choice is restored across restarts.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "shed_exempt"
    _attr_icon = "mdi:shield-off-outline"

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, load_name: str
    ) -> None:
        super().__init__(coordinator)
        self._load_name = load_name
        self._attr_unique_id = f"{entry.entry_id}_load_{load_name}_shed_exempt"
        self._attr_device_info = _load_device_info(entry, load_name)

    async def async_added_to_hass(self) -> None:
        """Restore the last on/off choice and re-apply it to the coordinator."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_ON:
            self.coordinator.set_shed_exempt(self._load_name, True)

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_shed_exempt(self._load_name)

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.set_shed_exempt(self._load_name, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.set_shed_exempt(self._load_name, False)
        self.async_write_ha_state()


class LoadForceChargeSwitch(CoordinatorEntity[SolarBalanceCoordinator], SwitchEntity):
    """Force a load to charge now at full power (grid-backed, even without surplus).

    A momentary override: on starts charging now regardless of shedding, the
    fast-charge inefficiency pause or available surplus; off returns to normal.
    Not restored across restarts (it is a "now" action). For an energy/time-bound
    charge, use the ``solarbalance.force_charge_load`` service.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "force_charge_now"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(
        self, coordinator: SolarBalanceCoordinator, entry: ConfigEntry, load_name: str
    ) -> None:
        super().__init__(coordinator)
        self._load_name = load_name
        self._attr_unique_id = f"{entry.entry_id}_load_{load_name}_force_charge"
        self._attr_device_info = _load_device_info(entry, load_name)

    @property
    def is_on(self) -> bool:
        return self.coordinator.force_charge_load_active(self._load_name)

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.request_force_charge_load(self._load_name)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.cancel_force_charge_load(self._load_name)
        self.async_write_ha_state()
