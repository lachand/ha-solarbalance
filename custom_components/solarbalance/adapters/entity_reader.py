"""Read mapped HA entities and build a core `Snapshot`.

The reader is the only place that translates HA `State` objects into the
core's normalised dataclasses. It applies sign-convention normalisation,
unit coercion, and watchdog/availability handling.
"""

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from ..core.models import (
    BatteryState,
    Device,
    InverterState,
    Load,
    LoadControlType,
    LoadState,
    Meter,
    MeterKind,
    MpptState,
    PowerSignConvention,
    Snapshot,
)
from ..core.weather import PHENOMENA, normalize_phenomenon, weather_warning_active

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
        weather_phenomena: Sequence[str] = (),
        weather_min_rank: int = 2,
        current_import_price: float | None = None,
        current_export_price: float | None = None,
        local_ac_load_entities: Sequence[str] = (),
        grid_backup_entity: str | None = None,
        noncontrollable_stale_s: float = 300.0,
        state_getter: Callable[[str], State | None] | None = None,
    ) -> None:
        self._hass = hass
        self._grid_backup_entity = grid_backup_entity or None
        # Which source the last grid reading came from: primary | backup | none.
        self.grid_source: str = "primary"
        self._devices = tuple(devices)
        self._meters = tuple(meters)
        self._loads = tuple(loads or [])
        self._local_ac_load_entities = tuple(local_ac_load_entities)
        self._stale_s = noncontrollable_stale_s
        self._pv_forecast_entity = pv_forecast_entity
        self._weather_warning_entity = weather_warning_entity
        self._weather_phenomena = tuple(weather_phenomena)
        self._weather_min_rank = weather_min_rank
        self._current_import_price = current_import_price
        self._current_export_price = current_export_price
        # Indirection so a replay can feed historical states instead of live ones.
        self._get_state = state_getter or (lambda eid: self._hass.states.get(eid))
        # How many battery devices share each power_entity. When >1 (e.g. an EcoFlow
        # STREAM that reports only a *system* power for its 2 batteries declared as 2
        # devices), the reading is split evenly so the fleet sum counts it once instead
        # of N times (which would double-count current_fleet).
        # Keyed by the candidate *set* (tuple) so two STREAM devices that list the same
        # system-power candidates share the count even when the live entity hops between
        # them (EcoFlow BLE moves the system-power sensor from battery 1 to battery 2).
        self._power_entity_shares = Counter(
            d.battery.power_entities
            for d in self._devices
            if d.battery is not None and d.battery.power_entities
        )

    def snapshot(self, timestamp: datetime | None = None) -> Snapshot:
        """Read all entities once and assemble a snapshot (``timestamp`` for replay)."""
        return Snapshot(
            timestamp=timestamp or dt_util.utcnow(),
            grid_power_w=self._read_grid_power(),
            batteries=self._read_batteries(),
            mppts=self._read_mppts(),
            inverters=self._read_inverters(),
            loads=self._read_loads(),
            pv_forecast_now_w=self._read_pv_forecast(),
            weather_warning_active=self._read_weather_warning(),
            current_import_price=self._current_import_price,
            current_export_price=self._current_export_price,
            local_ac_load_w=self._read_local_ac_load(),
            **self._read_grid_power_per_phase(),
        )

    def _read_local_ac_load(self) -> float:
        """Sum the declared local AC-load entities (behind the fleet, off-meter)."""
        return sum(
            max(0.0, self._read_float(eid, default=0.0) or 0.0)
            for eid in self._local_ac_load_entities
        )

    def _read_grid_power(self) -> float:
        """Grid power, falling back to the backup sensor when the PDL is unavailable.

        A meter dropout used to suspend regulation entirely (observed 2026-07-24:
        38 min at sunrise). A declared backup keeps the loop measuring instead. The
        backup is read with its own sign convention assumed identical to the PDL's,
        and ``grid_source`` records which one answered so it can be diagnosed.
        """
        pdl = next((m for m in self._meters if m.kind is MeterKind.PDL), None)
        if pdl is None:
            _LOGGER.warning("No PDL meter declared — grid power defaulting to 0")
            self.grid_source = "none"
            return 0.0
        raw = self._read_float(pdl.power_entity, default=None)
        if raw is not None:
            if self.grid_source != "primary":
                _LOGGER.info("Grid meter %s is back — leaving the backup", pdl.power_entity)
            self.grid_source = "primary"
            return -raw if pdl.invert_sign else raw

        backup = self._read_float(self._grid_backup_entity, default=None)
        if backup is not None:
            if self.grid_source != "backup":
                _LOGGER.warning(
                    "Grid meter %s unavailable — falling back to %s",
                    pdl.power_entity,
                    self._grid_backup_entity,
                )
            self.grid_source = "backup"
            return -backup if pdl.invert_sign else backup

        self.grid_source = "none"
        return 0.0

    def _read_grid_power_per_phase(self) -> dict[str, float | None]:
        """Return per-phase grid power dict for Snapshot keyword args.

        Only populated when the PDL meter declares L1/L2/L3 power entities.
        Returns a dict with None values when entities are absent. Negated together
        with the aggregate when the meter uses the export-positive convention.
        """
        pdl = next((m for m in self._meters if m.kind is MeterKind.PDL), None)
        if pdl is None:
            return {"grid_power_l1_w": None, "grid_power_l2_w": None, "grid_power_l3_w": None}

        def _phase(entity: str | None) -> float | None:
            value = self._read_float(entity, default=None)
            if value is None:
                return None
            return -value if pdl.invert_sign else value

        return {
            "grid_power_l1_w": _phase(pdl.power_l1_entity),
            "grid_power_l2_w": _phase(pdl.power_l2_entity),
            "grid_power_l3_w": _phase(pdl.power_l3_entity),
        }

    def _read_batteries(self) -> tuple[BatteryState, ...]:
        states: list[BatteryState] = []
        for device in self._devices:
            if device.battery is None:
                continue
            soc = self._read_float(device.battery.soc_entity, default=None)
            power = self._read_battery_power(device)
            available = soc is not None and power is not None
            temperature = (
                self._read_float(device.battery.temperature_entity, default=None)
                if device.battery.temperature_entity
                else None
            )
            cycles = (
                self._read_float(device.battery.cycles_entity, default=None)
                if device.battery.cycles_entity
                else None
            )
            reason, age_s = self._battery_staleness(device.battery)
            states.append(
                BatteryState(
                    device_name=device.name,
                    soc_pct=soc if soc is not None else 0.0,
                    power_w=power if power is not None else 0.0,
                    temperature_c=temperature,
                    cycles=cycles,
                    available=available,
                    stale=reason is not None,
                    stale_reason=reason,
                    stale_age_s=age_s,
                )
            )
        return tuple(states)

    def _battery_staleness(self, battery: object) -> tuple[str | None, float | None]:
        """Return ``(reason, age_s)`` when the battery's data is stale, else ``(None, None)``.

        ``reason`` is ``"soc"`` or ``"power"`` — the signal that timed out — and ``age_s`` its
        age. Lets the dashboard show *why* a battery is offline. ``stale_s <= 0`` disables it.

        SoC is the signal the equaliser and the cloud-charge guards steer on: an unplugged
        cloud station keeps reporting its *last* SoC, so an old SoC alone means stale — its
        dead value must not drive PV-routing (else the offer flutters on/off). The power
        sources keep the "any fresh source = alive" rule (they may update at different
        cadences), so they flag stale only when *every* present power entity is old.
        """
        if self._stale_s <= 0:
            return (None, None)
        soc_entity = getattr(battery, "soc_entity", None)
        soc_age = self._entity_age_s(soc_entity) if soc_entity else None
        if soc_age is not None and soc_age > self._stale_s:
            return ("soc", soc_age)
        entities = [
            *getattr(battery, "power_entities", ()),
            getattr(battery, "charge_power_entity", None),
            getattr(battery, "discharge_power_entity", None),
        ]
        ages = [age for e in entities if e for age in (self._entity_age_s(e),) if age is not None]
        # Stale only if every present power source is old (a missing entity is not
        # evidence of freshness, but at least one fresh source means not stale).
        if ages and min(ages) > self._stale_s:
            return ("power", min(ages))
        return (None, None)

    def _entity_age_s(self, entity_id: str) -> float | None:
        """Seconds since the entity last updated, or None if it has no state."""
        state = self._get_state(entity_id)
        if state is None or state.state in _INVALID_STATES:
            return None
        return (dt_util.utcnow() - state.last_updated).total_seconds()

    def _read_battery_power(self, device: Device) -> float | None:
        battery = device.battery
        assert battery is not None  # guarded by caller
        if battery.power_entity is not None:
            # Use the first *available* candidate — the STREAM system-power sensor can hop
            # between the two batteries' entities, so follow whichever is currently live.
            raw = None
            for eid in battery.power_entities:
                raw = self._read_float(eid, default=None)
                if raw is not None:
                    break
            if raw is None:
                return None
            if battery.power_sign_convention is PowerSignConvention.DISCHARGE_POSITIVE:
                raw = -raw
            # Split a power entity shared by several battery devices (system-level
            # reporting) so the fleet sum counts it once, not once per device.
            return raw / self._power_entity_shares[battery.power_entities]
        # Two-entity case.
        charge = self._read_float(battery.charge_power_entity, default=0.0) or 0.0
        discharge = self._read_float(battery.discharge_power_entity, default=0.0) or 0.0
        return charge - discharge

    def _read_mppts(self) -> tuple[MpptState, ...]:
        states: list[MpptState] = []
        for device in self._devices:
            if device.mppt is None:
                continue
            # Sum every declared production sensor (inverters that expose one entity per
            # string, e.g. Indevolt). Available as long as at least one reads back, so a
            # single sensor blip undercounts briefly rather than zeroing the whole array.
            readings = [
                v
                for entity in device.mppt.power_entities
                if (v := self._read_float(entity, default=None)) is not None
            ]
            temperature = (
                self._read_float(device.mppt.temperature_entity, default=None)
                if device.mppt.temperature_entity
                else None
            )
            states.append(
                MpptState(
                    device_name=device.name,
                    power_w=sum(readings),
                    temperature_c=temperature,
                    available=bool(readings),
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
                eps_state = self._get_state(device.inverter.eps_active_entity)
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
            elif load.control_type is LoadControlType.ON_OFF and load.switch_entity:
                sw = self._get_state(load.switch_entity)
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
        state = self._get_state(self._weather_warning_entity)
        if state is None:
            return False
        # Météo-France weather_alert exposes one attribute per phenomenon (e.g.
        # "Vent violent": "Orange"). When present, filter by the watched phenomena
        # and minimum level so e.g. a Canicule alert does not trigger storm mode.
        if any(normalize_phenomenon(k) in PHENOMENA for k in state.attributes):
            return weather_warning_active(
                state.attributes,
                watched=self._weather_phenomena,
                min_rank=self._weather_min_rank,
            )
        # Plain binary_sensor (on/off) or a single-level sensor.
        if state.state == "on":
            return True
        if state.state == "off":
            return False
        return state.state.lower() in {"orange", "red", "rouge"}

    def _read_float(self, entity_id: str | None, *, default: float | None) -> float | None:
        if entity_id is None:
            return default
        state: State | None = self._get_state(entity_id)
        if state is None or state.state in _INVALID_STATES:
            return default
        try:
            return float(state.state)
        except (TypeError, ValueError):
            _LOGGER.debug("Entity %s state %r is not numeric", entity_id, state.state)
            return default
