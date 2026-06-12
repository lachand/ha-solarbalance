"""Write computed setpoints to controllable battery entities (V2).

This is the active-control counterpart of the read-only ``DecisionPublisher``: it
is the **only** component that writes to user equipment. Gated behind the global
``active_control_enabled`` option and the per-device ``active_control_enabled``
flag.

It writes, per device, whichever setpoint entities are declared:

- ``discharge_power_setpoint_entity`` -- discharge power (W);
- ``charge_power_setpoint_entity`` -- charge power (W);
- ``mode_setpoint_entity`` -- a select/input_select set to ``charge`` / ``discharge``
  / ``idle`` (canonical strings; bridge to vendor labels with a template select).

Per-battery sign comes from the balancing allocation (positive = charge). A
battery at/below its SoC floor is never told to discharge; at/above its SoC
ceiling it is never told to charge.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..core.models import Device

_LOGGER = logging.getLogger(__name__)

# Skip a service call when the setpoint barely moved -- reduces entity churn.
_WRITE_EPSILON_W = 5.0
# SoC margin around the floor/ceiling at which discharge/charge is cut, covering
# a one-tick SoC lag on cloud batteries.
_SOC_MARGIN_PCT = 0.5


@dataclass(slots=True, frozen=True)
class _Managed:
    """Active-control setpoint entities and SoC bounds for one device."""

    charge_entity: str | None
    discharge_entity: str | None
    mode_entity: str | None
    soc_floor: float
    soc_ceiling: float


class ActiveControlPublisher:
    """Translate per-battery allocations into HA entity writes."""

    def __init__(self, hass: HomeAssistant, devices: Sequence[Device]) -> None:
        self._hass = hass
        managed: dict[str, _Managed] = {}
        for device in devices:
            battery = device.battery
            if battery is None or not battery.active_control_enabled:
                continue
            managed[device.name] = _Managed(
                charge_entity=battery.charge_power_setpoint_entity,
                discharge_entity=battery.discharge_power_setpoint_entity,
                mode_entity=battery.mode_setpoint_entity,
                soc_floor=float(battery.soc_min_pct) + _SOC_MARGIN_PCT,
                soc_ceiling=float(battery.soc_max_pct) - _SOC_MARGIN_PCT,
            )
        self._managed = managed
        self._last_power: dict[str, float] = {}
        self._last_mode: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        """True when at least one device has an active-control entity."""
        return bool(self._managed)

    async def apply(
        self,
        per_battery_w: Mapping[str, float],
        soc_by_device: Mapping[str, float],
    ) -> None:
        """Write charge/discharge/mode setpoints from a balancing allocation.

        Args:
            per_battery_w: Per-battery signed power (positive = charge).
            soc_by_device: Current SoC (%) per device, for the floor/ceiling cuts.
        """
        for name, m in self._managed.items():
            allocated = per_battery_w.get(name, 0.0)
            charge_w = max(0.0, allocated)
            discharge_w = max(0.0, -allocated)
            soc = soc_by_device.get(name)
            if soc is not None:
                if soc <= m.soc_floor:
                    discharge_w = 0.0
                if soc >= m.soc_ceiling:
                    charge_w = 0.0
            if m.discharge_entity is not None:
                await self._write_power(m.discharge_entity, discharge_w)
            if m.charge_entity is not None:
                await self._write_power(m.charge_entity, charge_w)
            if m.mode_entity is not None:
                mode = (
                    "charge"
                    if charge_w > _WRITE_EPSILON_W
                    else "discharge"
                    if discharge_w > _WRITE_EPSILON_W
                    else "idle"
                )
                await self._write_mode(m.mode_entity, mode)

    async def reset(self) -> None:
        """Command all managed power setpoints to 0 W (e.g. when suspended)."""
        for m in self._managed.values():
            if m.discharge_entity is not None:
                await self._write_power(m.discharge_entity, 0.0)
            if m.charge_entity is not None:
                await self._write_power(m.charge_entity, 0.0)

    async def _write_power(self, entity_id: str, value_w: float) -> None:
        last = self._last_power.get(entity_id)
        if last is not None and abs(last - value_w) < _WRITE_EPSILON_W:
            return
        service_domain = "input_number" if entity_id.startswith("input_number.") else "number"
        try:
            await self._hass.services.async_call(
                service_domain,
                "set_value",
                {"entity_id": entity_id, "value": round(value_w, 1)},
                blocking=False,
            )
        except Exception:
            _LOGGER.exception("Active control: failed to write %s = %.0f W", entity_id, value_w)
            return
        self._last_power[entity_id] = value_w
        _LOGGER.debug("Active control: %s <- %.0f W", entity_id, value_w)

    async def _write_mode(self, entity_id: str, mode: str) -> None:
        if self._last_mode.get(entity_id) == mode:
            return
        service_domain = "input_select" if entity_id.startswith("input_select.") else "select"
        try:
            await self._hass.services.async_call(
                service_domain,
                "select_option",
                {"entity_id": entity_id, "option": mode},
                blocking=False,
            )
        except Exception:
            _LOGGER.exception("Active control: failed to set %s mode = %s", entity_id, mode)
            return
        self._last_mode[entity_id] = mode
        _LOGGER.debug("Active control: %s <- mode %s", entity_id, mode)
