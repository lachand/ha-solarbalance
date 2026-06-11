"""Write computed discharge setpoints to controllable battery entities (V2).

This is the active-control counterpart of the read-only `DecisionPublisher`: it
is the **only** component that writes to user equipment. Per AGENTS.md the v1
component is read-only; active control is gated behind the global
``active_control_enabled`` option and the per-device ``active_control_enabled``
flag, and must be tagged for the v2 milestone.

First step is **discharge-only**. Steering the controllable batteries' discharge
shifts the AC-bus balance, which in turn drives the automatic (non-controllable)
battery's charge — "it's the discharge that controls the charge". Charge
setpoints are intentionally not written yet.
"""

import logging
from collections.abc import Mapping, Sequence

from homeassistant.core import HomeAssistant

from ..core.models import Device

_LOGGER = logging.getLogger(__name__)

# Skip a service call when the setpoint barely moved — reduces entity churn.
_WRITE_EPSILON_W = 5.0
# Stop commanding discharge slightly above the battery's floor, so a one-tick
# SoC lag (cloud batteries) never keeps draining a battery already at its limit.
_SOC_CUTOFF_MARGIN_PCT = 0.5


class ActiveControlPublisher:
    """Translate per-battery discharge allocations into HA entity writes."""

    def __init__(self, hass: HomeAssistant, devices: Sequence[Device]) -> None:
        self._hass = hass
        # device_name -> (discharge setpoint entity, soc floor below which discharge is cut)
        managed: dict[str, tuple[str, float]] = {}
        for device in devices:
            battery = device.battery
            if (
                battery is not None
                and battery.active_control_enabled
                and battery.discharge_power_setpoint_entity is not None
            ):
                managed[device.name] = (
                    battery.discharge_power_setpoint_entity,
                    float(battery.soc_min_pct) + _SOC_CUTOFF_MARGIN_PCT,
                )
        self._managed = managed
        self._last_written: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        """True when at least one device declares a discharge setpoint entity."""
        return bool(self._managed)

    async def apply(
        self,
        per_battery_w: Mapping[str, float],
        soc_by_device: Mapping[str, float],
    ) -> None:
        """Write discharge setpoints derived from a balancing allocation.

        Args:
            per_battery_w: Per-battery signed power (positive = charge, negative =
                discharge). Only the discharge magnitude is written; a battery
                that is charging or idle is commanded to 0 W discharge.
            soc_by_device: Current SoC (%) per device; a battery at or below its
                floor (``soc_min_pct + 0.5``) is forced to 0 W discharge.
        """
        for name, (entity_id, soc_floor) in self._managed.items():
            allocated = per_battery_w.get(name, 0.0)
            discharge_w = -allocated if allocated < 0 else 0.0
            soc = soc_by_device.get(name)
            if soc is not None and soc <= soc_floor:
                discharge_w = 0.0
            await self._write(entity_id, discharge_w)

    async def reset(self) -> None:
        """Command all managed discharge setpoints to 0 W.

        Used when active control is suspended (paused / degraded) so equipment is
        left in a neutral state rather than holding a stale setpoint.
        """
        for entity_id, _ in self._managed.values():
            await self._write(entity_id, 0.0)

    async def _write(self, entity_id: str, value_w: float) -> None:
        last = self._last_written.get(entity_id)
        if last is not None and abs(last - value_w) < _WRITE_EPSILON_W:
            return
        # number.set_value / input_number.set_value share the same signature.
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
        self._last_written[entity_id] = value_w
        _LOGGER.debug("Active control: %s ← %.0f W discharge", entity_id, value_w)
