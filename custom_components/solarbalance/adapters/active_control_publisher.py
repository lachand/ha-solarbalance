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
# Quantise the charge setpoint to this step (W): a STREAM is slow over BLE and the
# fine PI ripple is meaningless to it, so round to 10 W and skip the in-between writes.
_CHARGE_STEP_W = 10.0
# A PV output-limit whose actual reading drifts from what we commanded by more than
# this (W) is re-written (verify+retry) — catches a write that silently didn't land
# (a wrong/intermittent entity, or an inverter that reverted it).
_WRITE_VERIFY_TOLERANCE_W = 20.0


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
    discharge_mirror_group: str | None


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
                discharge_mirror_group=battery.discharge_mirror_group or None,
            )
        self._managed = managed
        # Groups whose discharge is a shared total mirrored to each member (e.g. the two
        # EcoFlow STREAM base-loads: same value written to both = that value total).
        self._discharge_groups: dict[str, list[str]] = {}
        for name, m in managed.items():
            if m.discharge_mirror_group:
                self._discharge_groups.setdefault(m.discharge_mirror_group, []).append(name)
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
        # Final (charge_w, discharge_w) actually commanded per device — post SoC-cut and
        # post discharge-mirror — so a diagnostic shows what was *written*, not the raw
        # balancer split (mirrored group members read the same discharge, e.g. STREAM).
        self._last_setpoints: dict[str, tuple[float, float]] = {}

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

    def last_setpoint_w(self, device_name: str, *, charge: bool) -> float | None:
        """Last charge (or discharge) power actually commanded for a device, or None.

        Reflects what was *written* (after the SoC cut and the discharge mirror), so a
        diagnostic shows the real setpoint — for a mirrored group, members read the same
        discharge total, not the balancer's internal per-battery split.
        """
        pair = self._last_setpoints.get(device_name)
        if pair is None:
            return None
        return pair[0] if charge else pair[1]

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

    async def verify_writes(self) -> None:
        """Re-assert any power setpoint whose actual reading drifted from what we sent.

        Covers every latched power write — PV output limits AND battery charge/discharge
        setpoints (e.g. a STREAM's charging_power_limit). The latch in ``_write_power``
        tracks what *we* last sent, so a call that silently didn't land — a wrong or
        intermittent entity, or a box that accepted it then reverted the value — is never
        retried on its own. This reads the actual back and re-writes the commanded value.

        Meant to be called *throttled* (every N ticks), not every tick: the box is slow
        over BLE so a just-sent value needs time to read back. Logs a warning so a
        setpoint that never sticks is visible, not silent.
        """
        for entity_id, commanded in list(self._last_power.items()):
            state = self._hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                continue  # can't verify now; retried when it returns
            try:
                actual = float(state.state)
            except (TypeError, ValueError):
                continue
            if abs(actual - commanded) > _WRITE_VERIFY_TOLERANCE_W:
                _LOGGER.warning(
                    "Active control: %s reads %.0f W but we commanded %.0f W — "
                    "re-writing (is the entity correct and controllable?)",
                    entity_id,
                    actual,
                    commanded,
                )
                await self._write_power(entity_id, commanded, force=True)

    async def apply(
        self,
        per_battery_w: Mapping[str, float],
        soc_by_device: Mapping[str, float],
    ) -> None:
        """Write charge/discharge/mode setpoints from a balancing allocation.

        The per-battery target is written **as-is** (charge setpoint = the allocation,
        quantised to ``_CHARGE_STEP_W``) — no PV is added and nothing is divided by a
        battery count. The regulator drives this in *velocity form* (it integrates on
        the last commanded value and re-reads it), so the setpoint self-discovers the
        right magnitude — including the battery's own PV and any per-battery scaling —
        from the grid error alone (mirrors the community EcoFlow STREAM PI controller).
        Quantising avoids spamming a slow BLE box with sub-step PI ripple.

        Args:
            per_battery_w: Per-battery signed power (positive = charge).
            soc_by_device: Current SoC (%) per device, for the floor/ceiling cuts.
        """
        # Phase 1 — per-device charge/discharge with the SoC floor/ceiling cuts.
        charge: dict[str, float] = {}
        discharge: dict[str, float] = {}
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
            charge[name] = round(charge_w / _CHARGE_STEP_W) * _CHARGE_STEP_W
            discharge[name] = discharge_w
        # Phase 2 — mirror each discharge group: the group TOTAL goes to every member's
        # discharge entity (the EcoFlow STREAM mirrors a per-battery base-load to one
        # group total). A member cut to 0 by its SoC floor is excluded from the total.
        for members in self._discharge_groups.values():
            total = sum(discharge[n] for n in members if n in discharge)
            for n in members:
                if n in discharge:
                    discharge[n] = total
        self._last_setpoints = {n: (charge[n], discharge[n]) for n in self._managed}
        # Phase 3 — write.
        for name, m in self._managed.items():
            charge_w, discharge_w = charge[name], discharge[name]
            _LOGGER.debug(
                "active-control %s: alloc=%+.0fW soc=%s -> charge=%.0fW discharge=%.0fW",
                name,
                per_battery_w.get(name, 0.0),
                f"{soc_by_device[name]:.0f}" if name in soc_by_device else "?",
                charge_w,
                discharge_w,
            )
            if m.mode_entity is not None:
                await self._apply_mode_battery(m, charge_w, discharge_w)
            else:
                if m.discharge_entity is not None:
                    await self._write_power(m.discharge_entity, discharge_w)
                if m.charge_entity is not None:
                    await self._write_power(m.charge_entity, charge_w)

    async def _apply_mode_battery(self, m: _Managed, charge_w: float, discharge_w: float) -> None:
        """Drive a mode-based battery (e.g. STREAM): one direction at a time.

        The box (BLE, slow) applies its actuators one at a time and only honours a
        power setpoint once it is *actually* in the matching strategy. So the switch
        is performed as **one mutation per tick, in order, each gated on the device's
        ACTUAL state and stopping until it lands**: (1) zero the opposite direction,
        (2) switch the strategy, (3) set the active power. Cramming the three writes
        into one pass (even blocking) leaves ``charging_power_limit`` ignored — it is
        written while the box is still in ``self_powered``. This mirrors the
        community EcoFlow STREAM PI controller, which stops after each step.

        In steady state the first two gates pass through (opposite already 0, strategy
        already set) and only the power is updated. A base load the box re-imposes on
        its own, or a strategy it silently reverts to ``self_powered``, is re-asserted
        — and the active power held back — until it sticks.
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

        if _LOGGER.isEnabledFor(logging.DEBUG):
            mode_state = self._hass.states.get(m.mode_entity)
            opp_state = self._hass.states.get(opposite) if opposite else None
            _LOGGER.debug(
                "mode-battery (%s): want %s %.0fW | actual mode=%s opposite(%s)=%s",
                active_entity,
                option,
                active_w,
                mode_state.state if mode_state else "?",
                opposite,
                opp_state.state if opp_state else "-",
            )
        # 1. Zero the opposite direction first; stop until it actually reads 0.
        if m.mode_zeroes_opposite and opposite is not None and self._reads_nonzero(opposite):
            _LOGGER.debug("mode-battery: step 1 — zero opposite %s", opposite)
            await self._write_power(opposite, 0.0, force=True, blocking=True)
            return
        # 2. Switch the strategy; stop until the box reports it (it may revert alone).
        if not self._mode_is(m.mode_entity, option):
            _LOGGER.debug("mode-battery: step 2 — switch %s -> %s", m.mode_entity, option)
            await self._write_mode(m.mode_entity, option, blocking=True, force=True)
            return
        # 3. Opposite is 0 and the strategy is in place → set the active power.
        if active_entity is not None:
            _LOGGER.debug("mode-battery: step 3 — set %s = %.0fW", active_entity, active_w)
            await self._write_power(active_entity, active_w)

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

    def _reads_nonzero(self, entity_id: str) -> bool:
        """True when the entity reports a non-zero power (so it still needs zeroing).

        Reads the device's ACTUAL state, not the write latch, so a base load the box
        re-imposes on its own is detected. Unknown/unavailable → ``False`` (cannot
        confirm, so do not block the sequence on it).
        """
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return False
        try:
            return abs(float(state.state)) > _WRITE_EPSILON_W
        except (TypeError, ValueError):
            return False

    def _mode_is(self, entity_id: str, option: str) -> bool:
        """True when the select is already on ``option``.

        Uses the device's ACTUAL state so a strategy the box silently reverts (a
        STREAM dropping back to ``self_powered``) is detected; falls back to the
        write latch only when the state is unreadable.
        """
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return self._last_mode.get(entity_id) == option
        return state.state == option

    def _entity_available(self, entity_id: str) -> bool:
        """False when the target entity is explicitly unavailable/unknown.

        A BLE device (a STREAM inverter) drops off the bus at night and its entities
        go ``unavailable``: writing to them then just logs "missing or not currently
        available" and does nothing, so skip it (no log spam, no pretend-action). A
        ``None`` state (entity not in the state machine yet) is treated as writable —
        let the service call surface a genuine misconfiguration.
        """
        state = self._hass.states.get(entity_id)
        return state is None or state.state not in ("unknown", "unavailable")

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
        if not self._entity_available(entity_id):
            _LOGGER.debug(
                "Active control: skip %s = %.0f W (entity unavailable)", entity_id, value_w
            )
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

    async def _write_mode(
        self, entity_id: str, mode: str, *, blocking: bool = False, force: bool = False
    ) -> None:
        if not force and self._last_mode.get(entity_id) == mode:
            return
        if not self._entity_available(entity_id):
            _LOGGER.debug("Active control: skip %s mode %s (entity unavailable)", entity_id, mode)
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
