"""Data models for the SolarBalance core engine.

These dataclasses describe the configuration (Device, Role, Load), the
runtime state (Snapshot), and the output of strategies (Decision). They
are pure value objects — no IO, no side effects, no Home Assistant.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Chemistry(StrEnum):
    """Battery chemistry. Drives default usable-capacity ratio and longevity bounds."""

    LIFEPO4 = "lifepo4"
    NMC = "nmc"
    LEADACID = "leadacid"
    OTHER = "other"


class PowerSignConvention(StrEnum):
    """Sign convention of a battery power entity as exposed by HA.

    The core normalises everything internally to `CHARGE_POSITIVE`.
    """

    CHARGE_POSITIVE = "charge_positive"
    DISCHARGE_POSITIVE = "discharge_positive"


class LoadControlType(StrEnum):
    """Control granularity of a pilotable load."""

    ON_OFF = "on_off"
    STEPPED = "stepped"
    MODULATING = "modulating"


class MeterKind(StrEnum):
    """What a meter measures."""

    PDL = "pdl"
    PV = "pv"
    CONSUMPTION = "consumption"
    SUBCIRCUIT = "subcircuit"


class HemsMode(StrEnum):
    """Top-level operating mode of the HEMS."""

    NORMAL = "normal"
    STORM = "storm"
    VACATION = "vacation"
    PAUSED = "paused"
    DEGRADED = "degraded"
    MANUAL_OVERRIDE = "manual_override"


class StrategyKind(StrEnum):
    """Available optimisation strategies."""

    SELF_CONSUMPTION = "self_consumption"
    COST_MIN = "cost_min"
    BACKUP = "backup"
    LONGEVITY = "longevity"
    PEAK_SHAVING = "peak_shaving"
    REVENUE_MAX = "revenue_max"


# ---------------------------------------------------------------------------
# Default usable-capacity ratios per chemistry (see SPECIFICATIONS §3.2)
# ---------------------------------------------------------------------------

USABLE_CAPACITY_RATIO: Mapping[Chemistry, float] = {
    Chemistry.LIFEPO4: 0.95,
    Chemistry.NMC: 0.85,
    Chemistry.LEADACID: 0.50,
    Chemistry.OTHER: 0.90,
}


# ---------------------------------------------------------------------------
# Configuration: roles
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class BatteryRole:
    """Configuration of a battery role attached to a device."""

    capacity_kwh: float
    max_charge_power_w: int
    max_discharge_power_w: int
    soc_entity: str
    power_entity: str | None = None
    charge_power_entity: str | None = None
    discharge_power_entity: str | None = None
    temperature_entity: str | None = None
    cycles_entity: str | None = None
    soc_min_pct: int = 10
    soc_max_pct: int = 95
    chemistry: Chemistry = Chemistry.LIFEPO4
    power_sign_convention: PowerSignConvention = PowerSignConvention.CHARGE_POSITIVE
    usable_capacity_kwh: float | None = None
    controllable: bool = True
    """When False, the battery reports its state but cannot be commanded
    charge/discharge over HA. It is excluded from the balancing controller and
    steered indirectly by the SoC equaliser (see core/controllers/soc_equaliser).
    """
    active_control_enabled: bool = False
    """When True (and global active control is on), the adapter writes computed
    setpoints to this device's setpoint entities. Requires a controllable battery.
    """
    ac_charge_limit_w: int | None = None
    """Max power this battery can absorb from the AC bus (W).

    Used by the SoC equaliser to bound how hard the controllable fleet may
    discharge to charge this (non-controllable) battery — never push more than it
    can take, or the excess spills to the grid. Defaults to ``max_charge_power_w``
    when unset (correct for an AC-only battery with no DC/solar input).
    """
    discharge_power_setpoint_entity: str | None = None
    """HA entity (number/input_number) receiving the discharge power setpoint (W)."""
    charge_power_setpoint_entity: str | None = None
    """HA entity (number/input_number) receiving the charge power setpoint (W)."""
    mode_setpoint_entity: str | None = None
    """HA select/input_select receiving the operating mode (charge/discharge/idle)."""

    def __post_init__(self) -> None:
        if self.power_entity is None and (
            self.charge_power_entity is None or self.discharge_power_entity is None
        ):
            raise ValueError(
                "BatteryRole requires either power_entity or both "
                "charge_power_entity and discharge_power_entity"
            )
        if self.active_control_enabled:
            if not self.controllable:
                raise ValueError(
                    "active_control_enabled requires controllable=true"
                )
            if (
                self.discharge_power_setpoint_entity is None
                and self.charge_power_setpoint_entity is None
                and self.mode_setpoint_entity is None
            ):
                raise ValueError(
                    "active_control_enabled requires at least one of "
                    "discharge_power_setpoint_entity, charge_power_setpoint_entity, "
                    "mode_setpoint_entity"
                )

    @property
    def effective_usable_capacity_kwh(self) -> float:
        """Resolve usable capacity, falling back to chemistry default ratio."""
        if self.usable_capacity_kwh is not None:
            return self.usable_capacity_kwh
        return self.capacity_kwh * USABLE_CAPACITY_RATIO[self.chemistry]


@dataclass(slots=True, frozen=True)
class MpptRole:
    """Configuration of a solar MPPT / micro-inverter role."""

    peak_power_w: int
    power_entity: str
    daily_energy_entity: str | None = None
    voltage_entity: str | None = None
    current_entity: str | None = None
    feeds: tuple[str, ...] = ()
    active_control_enabled: bool = False
    """When True (and global active control is on), SolarBalance caps this
    inverter's output for zero-injection via power_limit_setpoint_entity.
    """
    power_limit_setpoint_entity: str | None = None
    """HA entity (number/input_number) receiving the max output power (W)."""

    def __post_init__(self) -> None:
        if self.active_control_enabled and self.power_limit_setpoint_entity is None:
            raise ValueError(
                "MpptRole active_control_enabled requires power_limit_setpoint_entity"
            )


@dataclass(slots=True, frozen=True)
class InverterRole:
    """Configuration of an inverter role."""

    nominal_power_w: int
    ac_output_power_entity: str
    ac_input_power_entity: str | None = None
    eps_capable: bool = False
    eps_active_entity: str | None = None
    eps_circuits: tuple[str, ...] = ()
    temperature_entity: str | None = None


@dataclass(slots=True, frozen=True)
class Device:
    """A configured device aggregating one or more roles."""

    name: str
    battery: BatteryRole | None = None
    mppt: MpptRole | None = None
    inverter: InverterRole | None = None

    def __post_init__(self) -> None:
        if not any((self.battery, self.mppt, self.inverter)):
            raise ValueError(f"Device {self.name!r} must declare at least one role")


# ---------------------------------------------------------------------------
# Configuration: meters and loads
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Meter:
    """Power meter at a measurement point."""

    name: str
    kind: MeterKind
    power_entity: str
    phases: int = 1
    per_phase_zi: bool = False
    power_l1_entity: str | None = None
    power_l2_entity: str | None = None
    power_l3_entity: str | None = None
    daily_import_energy_entity: str | None = None
    daily_export_energy_entity: str | None = None


@dataclass(slots=True, frozen=True)
class TimeWindow:
    """A start/end time-of-day window (HH:MM strings, inclusive of start, exclusive of end)."""

    start: str
    end: str


@dataclass(slots=True, frozen=True)
class DeadlineConstraint:
    """Energy delivery requirement before a given time-of-day."""

    kwh_required: float
    before_time: str


@dataclass(slots=True, frozen=True)
class LoadStep:
    """One discrete level for a stepped load."""

    level: int
    power_w: int


@dataclass(slots=True, frozen=True)
class Load:
    """A pilotable electrical load with a control granularity."""

    name: str
    control_type: LoadControlType
    priority: int
    interruptible: bool = True
    min_on_duration_s: int = 0
    min_off_duration_s: int = 0
    max_daily_runtime_s: int | None = None
    max_daily_energy_kwh: float | None = None
    time_window: TimeWindow | None = None
    deadline_constraint: DeadlineConstraint | None = None

    nominal_power_w: int | None = None
    switch_entity: str | None = None
    steps: tuple[LoadStep, ...] = ()
    level_entity: str | None = None
    min_power_w: int | None = None
    max_power_w: int | None = None
    step_w: int = 1
    power_set_entity: str | None = None
    actual_power_entity: str | None = None

    def __post_init__(self) -> None:
        if self.control_type is LoadControlType.ON_OFF:
            if self.nominal_power_w is None or self.switch_entity is None:
                raise ValueError(
                    f"Load {self.name!r} (on_off) requires nominal_power_w and switch_entity"
                )
        elif self.control_type is LoadControlType.STEPPED:
            if not self.steps or self.level_entity is None:
                raise ValueError(f"Load {self.name!r} (stepped) requires steps and level_entity")
        elif self.control_type is LoadControlType.MODULATING and (
            self.min_power_w is None or self.max_power_w is None or self.power_set_entity is None
        ):
            raise ValueError(
                f"Load {self.name!r} (modulating) requires min_power_w, "
                "max_power_w and power_set_entity"
            )


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class BatteryState:
    """Instantaneous state of one battery role."""

    device_name: str
    soc_pct: float
    power_w: float  # normalised: positive = charging, negative = discharging
    temperature_c: float | None = None
    available: bool = True


@dataclass(slots=True, frozen=True)
class MpptState:
    """Instantaneous state of one MPPT role."""

    device_name: str
    power_w: float
    available: bool = True


@dataclass(slots=True, frozen=True)
class InverterState:
    """Instantaneous state of one inverter role."""

    device_name: str
    ac_output_w: float
    ac_input_w: float | None = None
    eps_active: bool = False
    available: bool = True


@dataclass(slots=True, frozen=True)
class LoadState:
    """Instantaneous state of one pilotable load."""

    name: str
    actual_power_w: float
    last_on_at: datetime | None = None
    last_off_at: datetime | None = None
    daily_runtime_s: int = 0
    daily_energy_kwh: float = 0.0


@dataclass(slots=True, frozen=True)
class Snapshot:
    """Full system state at a single tick."""

    timestamp: datetime
    grid_power_w: float  # positive = import, negative = export
    batteries: tuple[BatteryState, ...]
    mppts: tuple[MpptState, ...]
    inverters: tuple[InverterState, ...]
    loads: tuple[LoadState, ...]
    pv_forecast_now_w: float | None = None
    weather_warning_active: bool = False
    current_import_price: float | None = None
    current_export_price: float | None = None
    # Per-phase grid power (None when meter is single-phase or L1/L2/L3 entities
    # are not declared). Positive = import, negative = export — same convention as
    # grid_power_w. grid_power_w always carries the aggregate regardless.
    grid_power_l1_w: float | None = None
    grid_power_l2_w: float | None = None
    grid_power_l3_w: float | None = None

    @property
    def pv_total_w(self) -> float:
        """Sum of all available MPPT powers."""
        return sum(m.power_w for m in self.mppts if m.available)

    @property
    def battery_power_total_w(self) -> float:
        """Sum of all available battery powers (positive = aggregate charging)."""
        return sum(b.power_w for b in self.batteries if b.available)

    @property
    def loads_power_total_w(self) -> float:
        """Sum of all pilotable-load actual powers."""
        return sum(load.actual_power_w for load in self.loads)

    @property
    def baseline_consumption_w(self) -> float:
        """Deduced background consumption (see SPECIFICATIONS §3.4).

        baseline = grid + pv - battery_charge - loads_pilotables
        (with battery_power positive on charge, grid positive on import)
        """
        return (
            self.grid_power_w
            + self.pv_total_w
            - self.battery_power_total_w
            - self.loads_power_total_w
        )


# ---------------------------------------------------------------------------
# Decisions and arbitration
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class BatteryTarget:
    """Per-battery target produced by a strategy.

    `soc_min_pct` and `soc_max_pct` define the comfort window; `preferred_power_w`
    expresses the strategy's directional intent (positive = wants to charge,
    negative = wants to discharge, None = no opinion).
    """

    soc_min_pct: float
    soc_max_pct: float
    preferred_power_w: float | None = None


@dataclass(slots=True, frozen=True)
class GridConstraint:
    """Per-strategy authorisation envelope on grid exchange.

    `None` means "no opinion"; the arbiter intersects opinions to find the most
    restrictive envelope.
    """

    max_import_w: float | None = None
    max_export_w: float | None = None


@dataclass(slots=True, frozen=True)
class Decision:
    """Output of a strategy for one tick."""

    battery_targets: Mapping[str, BatteryTarget] = field(default_factory=dict)
    grid_constraint: GridConstraint = field(default_factory=GridConstraint)
    load_priorities: Mapping[str, int] = field(default_factory=dict)
    confidence: float = 1.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
