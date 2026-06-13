"""Apply load-dispatch commands to real Home Assistant entities.

The :class:`~..core.controllers.load_dispatch.LoadDispatchController` is pure: it
returns a :class:`LoadDispatchResult` of per-load commands. This adapter
translates those commands into HA service calls:

- ``on_off``    -> ``homeassistant.turn_on`` / ``turn_off`` on ``switch_entity``
  (works for ``switch.*`` and ``input_boolean.*``).
- ``stepped``   -> ``set_value`` on ``level_entity`` (number / input_number).
- ``modulating``-> ``set_value`` on ``power_set_entity``.

Writes are de-duplicated: a command that matches the last applied value is
skipped, so HEMS does not spam the bus or fight manual control every tick.

Control is gated by an ``enabled`` flag (the ``load_control_enabled`` option),
off by default — SolarBalance never touches the user's switches unless asked.
"""

import logging
from collections.abc import Sequence

from homeassistant.core import HomeAssistant

from ..core.controllers.load_dispatch import LoadCommand
from ..core.models import Load, LoadControlType

_LOGGER = logging.getLogger(__name__)
_WRITE_EPSILON_W = 1.0


class LoadPublisher:
    """Translate load-dispatch commands into HA entity writes."""

    def __init__(self, hass: HomeAssistant, loads: Sequence[Load], *, enabled: bool) -> None:
        self._hass = hass
        self._loads = {load.name: load for load in loads}
        self._enabled = enabled
        self._last_on: dict[str, bool] = {}
        self._last_value: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        """True when load control is allowed to write to entities."""
        return self._enabled

    async def apply(self, commands: Sequence[LoadCommand]) -> None:
        """Apply each command to its load's control entity (no-op when disabled)."""
        if not self._enabled:
            return
        for cmd in commands:
            load = self._loads.get(cmd.load_name)
            if load is None:
                continue
            if load.control_type is LoadControlType.ON_OFF:
                await self._write_switch(load.switch_entity, cmd.on)
            elif load.control_type is LoadControlType.STEPPED:
                if load.level_entity is not None and cmd.step_level is not None:
                    await self._write_value(load.level_entity, float(cmd.step_level))
            elif load.control_type is LoadControlType.MODULATING:
                target = cmd.power_w if cmd.on and cmd.power_w is not None else 0.0
                if load.power_set_entity is not None:
                    await self._write_value(load.power_set_entity, target)

    async def reset(self) -> None:
        """Turn every managed on/off load OFF (e.g. when the HEMS is paused)."""
        if not self._enabled:
            return
        for load in self._loads.values():
            if load.control_type is LoadControlType.ON_OFF:
                await self._write_switch(load.switch_entity, False)

    async def _write_switch(self, entity_id: str | None, on: bool) -> None:
        if entity_id is None or self._last_on.get(entity_id) == on:
            return
        service = "turn_on" if on else "turn_off"
        try:
            await self._hass.services.async_call(
                "homeassistant", service, {"entity_id": entity_id}, blocking=False
            )
        except Exception:
            _LOGGER.exception("Load control: failed to %s %s", service, entity_id)
            return
        self._last_on[entity_id] = on
        _LOGGER.debug("Load control: %s <- %s", entity_id, "on" if on else "off")

    async def _write_value(self, entity_id: str, value: float) -> None:
        last = self._last_value.get(entity_id)
        if last is not None and abs(last - value) < _WRITE_EPSILON_W:
            return
        service_domain = "input_number" if entity_id.startswith("input_number.") else "number"
        try:
            await self._hass.services.async_call(
                service_domain,
                "set_value",
                {"entity_id": entity_id, "value": round(value, 1)},
                blocking=False,
            )
        except Exception:
            _LOGGER.exception("Load control: failed to write %s = %.0f", entity_id, value)
            return
        self._last_value[entity_id] = value
        _LOGGER.debug("Load control: %s <- %.0f", entity_id, value)
