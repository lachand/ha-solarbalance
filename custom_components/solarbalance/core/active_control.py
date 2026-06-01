"""Active control interface for V2 — write setpoints to inverter/battery entities.

In V1 SolarBalance is read-only: it publishes computed setpoints as its own
sensor entities but never writes to user equipment. This module introduces the
V2 active control layer, gated by the ``active_control_enabled`` config flag
(default ``False``).

When enabled, `ActiveControlCommand` instances are produced by strategies and
published by the `ActiveControlPublisher` adapter (HA layer, not in core/).

See SPECIFICATIONS §11 (roadmap v2.0) — Pilotage actif.
"""

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Command model
# ---------------------------------------------------------------------------


class ControlMode(StrEnum):
    """Operating mode to request from the inverter/battery."""

    AUTO = "auto"
    """Let the device decide (default / hands-off)."""

    CHARGE = "charge"
    """Force charge at the specified power."""

    DISCHARGE = "discharge"
    """Force discharge at the specified power."""

    IDLE = "idle"
    """Hold current SoC — neither charge nor discharge."""

    GRID_CHARGE = "grid_charge"
    """Charge from the grid (typically during cheap-rate periods)."""


@dataclass(slots=True, frozen=True)
class ActiveControlCommand:
    """Write command targeting a single device.

    Args:
        device_name: Matches ``Device.name`` in YAML configuration.
        mode: Requested control mode.
        power_w: Target power in W (absolute value; direction conveyed by
            ``mode``). ``None`` means «use device maximum».
        soc_target_pct: Optional SoC target in percent. When set, the device
            should stop the requested mode once this SoC is reached.
        priority: Higher priority commands take precedence when multiple
            strategies emit conflicting commands for the same device.
            Mirrors the arbitration priority used in the core arbiter.
        reason: Human-readable justification logged to HA for traceability.
    """

    device_name: str
    mode: ControlMode
    power_w: float | None = None
    soc_target_pct: float | None = None
    priority: int = 50
    reason: str = ""


@dataclass(slots=True, frozen=True)
class ActiveControlResult:
    """Result of applying an `ActiveControlCommand` to a HA entity.

    Args:
        device_name: Echoes the command's device name.
        success: Whether the HA service call succeeded.
        entity_id: The entity that was written.
        value_written: The numeric value written (W or %).
        error: Human-readable error message when ``success`` is False.
    """

    device_name: str
    success: bool
    entity_id: str
    value_written: float | None
    error: str = ""


# ---------------------------------------------------------------------------
# Capability declaration
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class DeviceControlCapability:
    """Describes which active-control features a device supports.

    Populated from YAML when ``active_control_enabled: true`` is set at the
    device level. The adapter validates that referenced entities exist before
    enabling writes.

    Args:
        device_name: Matches ``Device.name``.
        charge_power_setpoint_entity: HA entity_id to write the charge power (W).
        discharge_power_setpoint_entity: HA entity_id to write the discharge power.
        mode_setpoint_entity: HA entity_id to write the operating mode string.
        soc_target_entity: HA entity_id to write a SoC target (%).
        supported_modes: Set of ``ControlMode`` values this device accepts.
    """

    device_name: str
    charge_power_setpoint_entity: str | None = None
    discharge_power_setpoint_entity: str | None = None
    mode_setpoint_entity: str | None = None
    soc_target_entity: str | None = None
    supported_modes: frozenset[ControlMode] = frozenset(
        {ControlMode.AUTO, ControlMode.CHARGE, ControlMode.DISCHARGE, ControlMode.IDLE}
    )

    def supports(self, mode: ControlMode) -> bool:
        """Return True if this device declares support for ``mode``."""
        return mode in self.supported_modes
