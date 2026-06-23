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
    charge_option: str
    discharge_option: str
    idle_option: str | None
    mode_zeroes_opposite: bool
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
                charge_option=battery.charge_mode_option,
                discharge_option=battery.discharge_mode_option,
                idle_option=battery.idle_mode_option,
                mode_zeroes_opposite=battery.mode_switch_zeroes_opposite,
                soc_floor=float(battery.soc_min_pct) + _SOC_MARGIN_PCT,
                soc_ceiling=float(battery.soc_max_pct) - _SOC_MARGIN_PCT,
            )
        self._managed = managed
        # device_name -> PV output-limit entity (curtailable micro-inverters)
        self._pv_limit_entities: dict[str, str] = {
            device.name: device.mppt.power_limit_setpoint_entity
            for device in devices
            if device.mppt is not None
            and device.mppt.active_control_enabled
            and device.mppt.power_limit_setpoint_entity is not None
        }
        # device_name -> backup-reserve / min-SoC setpoint entity (% number)
        self._reserve_entities: dict[str, str] = {
            device.name: device.battery.reserve_soc_setpoint_entity
            for device in devices
            if device.battery is not None and device.battery.reserve_soc_setpoint_entity is not None
        }
        self._last_power: dict[str, float] = {}
        self._last_mode: dict[str, str] = {}
        self._last_reserve: dict[str, float] = {}

        # Catch a common misconfiguration early: a setpoint entity_id without a
        # domain (e.g. "ef_xxxxxx_backup_reserve" instead of "number.ef_...").
        for name, m in managed.items():
            for label, eid in (
                ("charge", m.charge_entity),
                ("discharge", m.discharge_entity),
                ("mode", m.mode_entity),
            ):
                if eid is not None and "." not in eid:
                    _LOGGER.warning(
                        "Active control: %s %s_setpoint_entity %r has no domain "
                        "(expected e.g. number.%s) — writes will fail",
                        name,
                        label,
                        eid,
                        eid,
                    )
        for name, eid in {**self._pv_limit_entities, **self._reserve_entities}.items():
            if "." not in eid:
                _LOGGER.warning(
                    "Active control: %s setpoint entity %r has no domain "
                    "(expected e.g. number.%s) — writes will fail",
                    name,
                    eid,
                    eid,
                )

    @property
    def enabled(self) -> bool:
        """True when at least one device has an active-control entity."""
        return bool(self._managed) or bool(self._pv_limit_entities) or bool(self._reserve_entities)

    async def apply_reserve(self, soc_by_device: Mapping[str, float]) -> None:
        """Write each battery's backup-reserve / min-SoC setpoint (%)."""
        for name, entity_id in self._reserve_entities.items():
            if name in soc_by_device:
                await self._write_reserve(entity_id, soc_by_device[name])

    async def _write_reserve(self, entity_id: str, value_pct: float) -> None:
        last = self._last_reserve.get(entity_id)
        if last is not None and abs(last - value_pct) < 0.5:
            return
        service_domain = "input_number" if entity_id.startswith("input_number.") else "number"
        try:
            await self._hass.services.async_call(
                service_domain,
                "set_value",
                {"entity_id": entity_id, "value": round(value_pct, 1)},
                blocking=False,
            )
        except Exception:
            _LOGGER.exception(
                "Active control: failed to set %s reserve = %.0f%%", entity_id, value_pct
            )
            return
        self._last_reserve[entity_id] = value_pct
        _LOGGER.debug("Active control: %s <- reserve %.0f%%", entity_id, value_pct)

    @property
    def pv_curtailment_enabled(self) -> bool:
        """True when at least one micro-inverter exposes a PV output limit."""
        return bool(self._pv_limit_entities)

    async def apply_pv_limits(self, limit_by_device: Mapping[str, float]) -> None:
        """Write per-inverter output-power limits (W) for PV curtailment."""
        for name, entity_id in self._pv_limit_entities.items():
            if name in limit_by_device:
                await self._write_power(entity_id, limit_by_device[name])

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
            if m.mode_entity is not None:
                await self._apply_mode_battery(m, charge_w, discharge_w)
            else:
                if m.discharge_entity is not None:
                    await self._write_power(m.discharge_entity, discharge_w)
                if m.charge_entity is not None:
                    await self._write_power(m.charge_entity, charge_w)

    async def _apply_mode_battery(self, m: _Managed, charge_w: float, discharge_w: float) -> None:
        """Drive a mode-based battery (e.g. STREAM): one direction at a time.

        On a mode change the opposite-direction power is zeroed and the mode is
        switched **before** the new direction's power is set, in order, blocking —
        a one-direction-at-a-time inverter ignores a power written in the wrong
        mode. The opposite direction is **re-asserted to 0 every tick** (not only on
        the switch): a STREAM re-imposes its own base load, so without this it would
        charge and discharge at once (e.g. charging 1000 W while still outputting
        399 W). In steady state these writes are cheap (latched / skipped when the
        device already reads 0).
        """
        assert m.mode_entity is not None
        if charge_w > _WRITE_EPSILON_W:
            option, active_entity, active_w, opposite = (
                m.charge_option,
                m.charge_entity,
                charge_w,
                m.discharge_entity,
            )
        elif discharge_w > _WRITE_EPSILON_W:
            option, active_entity, active_w, opposite = (
                m.discharge_option,
                m.discharge_entity,
                discharge_w,
                m.charge_entity,
            )
        else:  # idle — zero both, optionally switch to an idle mode
            if m.discharge_entity is not None:
                await self._ensure_zero(m.discharge_entity)
            if m.charge_entity is not None:
                await self._ensure_zero(m.charge_entity)
            if m.idle_option is not None:
                await self._write_mode(m.mode_entity, m.idle_option)
            return

        switching = self._last_mode.get(m.mode_entity) != option
        if m.mode_zeroes_opposite and opposite is not None:
            if switching:
                await self._write_power(opposite, 0.0, blocking=True)
            else:
                # Re-assert 0 against the device's self-imposed base load.
                await self._ensure_zero(opposite)
        await self._write_mode(m.mode_entity, option, blocking=switching)
        if active_entity is not None:
            await self._write_power(active_entity, active_w, blocking=switching)

    async def _ensure_zero(self, entity_id: str) -> None:
        """Force the power setpoint back to 0 when the device reads non-zero.

        The latch in ``_write_power`` tracks what *we* last wrote, so a value the
        device sets on its own (a STREAM's base load) is never corrected. This reads
        the entity's actual state and re-writes 0 only when it has drifted, so the
        opposite direction truly stays off while charging/discharging.
        """
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return
        try:
            current = float(state.state)
        except (TypeError, ValueError):
            return
        if abs(current) > _WRITE_EPSILON_W:
            await self._write_power(entity_id, 0.0, force=True)

    async def reset(self) -> None:
        """Command all managed power setpoints to 0 W (e.g. when suspended)."""
        for m in self._managed.values():
            if m.discharge_entity is not None:
                await self._write_power(m.discharge_entity, 0.0)
            if m.charge_entity is not None:
                await self._write_power(m.charge_entity, 0.0)

    async def _write_power(
        self, entity_id: str, value_w: float, *, blocking: bool = False, force: bool = False
    ) -> None:
        last = self._last_power.get(entity_id)
        if not force and last is not None and abs(last - value_w) < _WRITE_EPSILON_W:
            return
        service_domain = "input_number" if entity_id.startswith("input_number.") else "number"
        try:
            await self._hass.services.async_call(
                service_domain,
                "set_value",
                {"entity_id": entity_id, "value": round(value_w, 1)},
                blocking=blocking,
            )
        except Exception:
            _LOGGER.exception("Active control: failed to write %s = %.0f W", entity_id, value_w)
            return
        self._last_power[entity_id] = value_w
        _LOGGER.debug("Active control: %s <- %.0f W", entity_id, value_w)

    async def _write_mode(self, entity_id: str, mode: str, *, blocking: bool = False) -> None:
        if self._last_mode.get(entity_id) == mode:
            return
        service_domain = "input_select" if entity_id.startswith("input_select.") else "select"
        try:
            await self._hass.services.async_call(
                service_domain,
                "select_option",
                {"entity_id": entity_id, "option": mode},
                blocking=blocking,
            )
        except Exception:
            _LOGGER.exception("Active control: failed to set %s mode = %s", entity_id, mode)
            return
        self._last_mode[entity_id] = mode
        _LOGGER.debug("Active control: %s <- mode %s", entity_id, mode)
