"""Wrappers around existing HA forecast and weather-warning integrations.

The reader resolves user-declared entity ids to typed values consumable by
the core. If the entity is missing or unparseable, returns a graceful
None / False fallback rather than raising — see SPECIFICATIONS §7.1, §7.2.
"""

import logging

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_INVALID = {STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""}


class ForecastReader:
    """Read PV and weather-warning entities exposed by other integrations."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        pv_forecast_entity: str | None,
        weather_warning_entity: str | None,
    ) -> None:
        self._hass = hass
        self._pv_entity = pv_forecast_entity
        self._weather_entity = weather_warning_entity

    def pv_forecast_now_w(self) -> float | None:
        """Read the currently-forecast PV power, in watts.

        Returns None if no entity is configured or the value is unavailable.
        Note: many integrations expose forecasts in kWh per slot rather than
        instantaneous W. This helper expects a watts-valued sensor; users
        relying on kWh-only sources should create a template sensor first.
        """
        if self._pv_entity is None:
            return None
        state = self._hass.states.get(self._pv_entity)
        if state is None or state.state in _INVALID:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            _LOGGER.debug("PV forecast entity %s state %r not numeric",
                          self._pv_entity, state.state)
            return None

    def weather_warning_active(self) -> bool:
        """Whether a configured Météo-France warning entity is currently active.

        Returns False on missing or unknown values (graceful degradation).
        """
        if self._weather_entity is None:
            return False
        state = self._hass.states.get(self._weather_entity)
        if state is None:
            return False
        # Tolerate both binary_sensor (on/off) and sensor with vigilance levels.
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        # Sensor with textual level — orange or red counts as active.
        return state.state.lower() in {"orange", "red", "rouge"}
