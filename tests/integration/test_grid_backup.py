"""Fallback to a backup grid sensor when the PDL meter goes away.

Observed 2026-07-24: the PDL power entity was ``unavailable`` from 06:58 to 07:36 —
38 minutes at sunrise during which SolarBalance suspended regulation entirely,
because the PDL is the only entity whose staleness is treated as critical. A
declared backup keeps the loop measuring instead of stopping.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.solarbalance.adapters.entity_reader import EntityReader
from custom_components.solarbalance.core.models import Meter, MeterKind


def _pdl(invert: bool = False) -> Meter:
    return Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.pdl", invert_sign=invert)


def _reader(states: dict[str, object], *, backup: str | None = "sensor.backup") -> EntityReader:
    return EntityReader(
        MagicMock(),
        [],
        [_pdl()],
        grid_backup_entity=backup,
        state_getter=lambda eid: states.get(eid),  # type: ignore[arg-type]
    )


def _s(value: object) -> SimpleNamespace:
    return SimpleNamespace(state=str(value), attributes={})


def test_primary_is_used_when_available() -> None:
    reader = _reader({"sensor.pdl": _s(120.0), "sensor.backup": _s(-999.0)})
    assert reader._read_grid_power() == 120.0
    assert reader.grid_source == "primary"


def test_falls_back_when_the_pdl_is_unavailable() -> None:
    reader = _reader({"sensor.pdl": _s("unavailable"), "sensor.backup": _s(85.0)})
    assert reader._read_grid_power() == 85.0
    assert reader.grid_source == "backup"


def test_recovers_to_the_primary_when_it_returns() -> None:
    states: dict[str, object] = {"sensor.pdl": _s("unavailable"), "sensor.backup": _s(85.0)}
    reader = _reader(states)
    assert reader._read_grid_power() == 85.0
    assert reader.grid_source == "backup"
    states["sensor.pdl"] = _s(140.0)
    assert reader._read_grid_power() == 140.0
    assert reader.grid_source == "primary"


def test_without_a_backup_the_reading_is_zero_and_flagged() -> None:
    # No fallback declared: behaviour is unchanged from before, but the source is
    # reported as "none" so the cause is visible instead of looking like a real 0 W.
    reader = _reader({"sensor.pdl": _s("unavailable")}, backup=None)
    assert reader._read_grid_power() == 0.0
    assert reader.grid_source == "none"


def test_backup_also_missing_is_reported_as_none() -> None:
    reader = _reader({"sensor.pdl": _s("unavailable"), "sensor.backup": _s("unknown")})
    assert reader._read_grid_power() == 0.0
    assert reader.grid_source == "none"


def test_the_meter_sign_convention_applies_to_the_backup_too() -> None:
    # An export-positive PDL negates its reading; the backup must be read the same
    # way or a fallback would silently invert the sign of the whole loop.
    states = {"sensor.pdl": _s("unavailable"), "sensor.backup": _s(85.0)}
    reader = EntityReader(
        MagicMock(),
        [],
        [_pdl(invert=True)],
        grid_backup_entity="sensor.backup",
        state_getter=lambda eid: states.get(eid),  # type: ignore[arg-type]
    )
    assert reader._read_grid_power() == -85.0


# --- solar-only fallback ---------------------------------------------------


def test_fallback_charges_when_blind_but_sunny() -> None:
    """The 2026-07-24 case: meter gone at sunrise, PV available, batteries with room.

    Rather than idling for 38 minutes, command a derated share of the estimated
    surplus. The estimate is PV minus the learned house load for this hour.
    """
    from custom_components.solarbalance.core.controllers.solar_fallback import (
        solar_only_target_w,
    )

    res = solar_only_target_w(
        enabled=True,
        pv_available=True,
        controllable_mppt_w=1200.0,
        predicted_house_w=300.0,
        headroom_kwh=3.0,
        safety_factor=0.7,
    )
    assert res.active is True
    assert res.charge_w == 630.0  # 70 % of the 900 W estimated surplus
    assert res.charge_w > 0, "a charge-only fallback must never command a discharge"


def test_fallback_stays_out_of_the_way_when_disabled() -> None:
    """Default behaviour is unchanged: no config, no blind commands."""
    from custom_components.solarbalance.core.controllers.solar_fallback import (
        solar_only_target_w,
    )

    res = solar_only_target_w(
        enabled=False,
        pv_available=True,
        controllable_mppt_w=1200.0,
        predicted_house_w=300.0,
        headroom_kwh=3.0,
    )
    assert res.active is False
    assert res.charge_w == 0.0
