"""Read mapped HA entities and build a core `Snapshot`.

The reader is the only place that translates HA `State` objects into the
core's normalised dataclasses. It applies sign-convention normalisation,
unit coercion, and watchdog/availability handling.
"""

import logging
from collections.abc import Sequence

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from ..core.models import (
    BatteryState,
    Device,
    InverterState,
    Load,
    LoadState,
    Meter,
    MpptState,
    PowerSignConvention,
    Snapshot,
)

_LOGGER = logging.getLogger(__name__)
_INVALID_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""}


class EntityReader:
    """Build a `Snapshot` from currently-mapped HA entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        devices: Sequence[Device],
        meters: Sequence[Meter],
        loads: Sequence[Load] | None = None,
        *,
        pv_forecast_entity: str | None = None,
        weather_warning_entity: str | None = None,
        current_import_price: float | None = None,
        current_export_price: float | None = None,
    ) -> None:
        self._hass = hass
        self._devices = tuple(devices)
        self._meters = tuple(meters)
        self._loads = tuple(loads or [])
        self._pv_forecast_entity = pv_forecast_entity
        self._weather_warning_entity = weather_warning_entity
        self._current_import_price = current_import_price
        self._current_export_price = current_export_price

    def snapshot(self) -> Snapshot:
        """Read all entities once and assemble a snapshot."""
        return Snapshot(
            timestamp=dt_util.utcnow(),
            grid_power_w=self._read_grid_power(),
            batteries=self._read_batteries(),
            mppts=self._read_mppts(),
            inverters=self._read_inverters(),
            loads=self._read_loads(),
            pv_forecast_now_w=self._read_pv_forecast(),
            weather_warning_active=self._read_weather_warning(),
            current_import_price=self._current_import_price,
            current_export_price=self._current_export_price,
        )

    def _read_grid_power(self) -> float:
        pdl = next((m for m in self._meters if m.kind.value == "pdl"), None)
        if pdl is None:
            _LOGGER.warning("No PDL meter declared — grid power defaulting to 0")
            return 0.0
        return self._read_float(pdl.power_entity, default=0.0)

    def _read_batteries(self) -> tuple[BatteryState, ...]:
        states: list[BatteryState] = []
        for device in self._devices:
            if device.battery is None:
                continue
            soc = self._read_float(device.battery.soc_entity, default=None)
            power = self._read_battery_power(device)
            available = soc is not None and power is not None
            states.append(
                BatteryState(
                    device_name=device.name,
                    soc_pct=soc if soc is not None else 0.0,
                    power_w=power if power is not None else 0.0,
                    available=available,
                )
            )
        return tuple(states)

    def _read_battery_power(self, device: Device) -> float | None:
        battery = device.battery
        assert battery is not None  # guarded by caller
        if battery.power_entity is not None:
            raw = self._read_float(battery.power_entity, default=None)
            if raw is None:
                return None
            if battery.power_sign_convention is PowerSignConvention.DISCHARGE_POSITIVE:
                return -raw
            return raw
        # Two-entity case.
        charge = self._read_float(battery.charge_power_entity, default=0.0) or 0.0
        discharge = self._read_float(battery.discharge_power_entity, default=0.0) or 0.0
        return charge - discharge

    def _read_mppts(self) -> tuple[MpptState, ...]:
        states: list[MpptState] = []
        for device in self._devices:
            if device.mppt is None:
                continue
            power = self._read_float(device.mppt.power_entity, default=None)
            states.append(
                MpptState(
                    device_name=device.name,
                    power_w=power if power is not None else 0.0,
                    available=power is not None,
                )
            )
        return tuple(states)

    def _read_inverters(self) -> tuple[InverterState, ...]:
        states: list[InverterState] = []
        for device in self._devices:
            if device.inverter is None:
                continue
            ac_out = self._read_float(device.inverter.ac_output_power_entity, default=None)
            ac_in = (
                self._read_float(device.inverter.ac_input_power_entity, default=None)
                if device.inverter.ac_input_power_entity
                else None
            )
            eps_active = False
            if device.inverter.eps_active_entity:
                eps_state = self._hass.states.get(device.inverter.eps_active_entity)
                eps_active = eps_state is not None and eps_state.state == "on"
            states.append(
                InverterState(
                    device_name=device.name,
                    ac_output_w=ac_out if ac_out is not None else 0.0,
                    ac_input_w=ac_in,
                    eps_active=eps_active,
                    available=ac_out is not None,
                )
            )
        return tuple(states)

    def _read_loads(self) -> tuple[LoadState, ...]:
        """Build minimal LoadState entries from actual_power_entity when available."""
        states: list[LoadState] = []
        for load in self._loads:
            power: float = 0.0
            if load.actual_power_entity:
                power = self._read_float(load.actual_power_entity, default=0.0) or 0.0
            elif load.control_type.value == "on_off" and load.switch_entity:
                sw = self._hass.states.get(load.switch_entity)
                if sw is not None and sw.state == "on":
                    power = float(load.nominal_power_w or 0)
            states.append(
                LoadState(
                    name=load.name,
                    actual_power_w=power,
                )
            )
        return tuple(states)

    def _read_pv_forecast(self) -> float | None:
        if self._pv_forecast_entity is None:
            return None
        return self._read_float(self._pv_forecast_entity, default=None)

    def _read_weather_warning(self) -> bool:
        if self._weather_warning_entity is None:
            return False
        state = self._hass.states.get(self._weather_warning_entity)
        if state is None:
            return False
        if state.state == "on":
            return True
        if state.state == "off":
            return False
        return state.state.lower() in {"orange", "red", "rouge"}

    def _read_float(self, entity_id: str | None, *, default: float | None) -> float | None:
        if entity_id is None:
            return default
        state: State | None = self._hass.states.get(entity_id)
        if state is None or state.state in _INVALID_STATES:
            return default
        try:
            return float(state.state)
        except (TypeError, ValueError):
            _LOGGER.debug("Entity %s state %r is not numeric", entity_id, state.state)
            return default
