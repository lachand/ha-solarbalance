"""Link health, end to end: the reader labels the links, the coordinator scores them."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarbalance.adapters.entity_reader import EntityReader
from custom_components.solarbalance.const import DOMAIN
from custom_components.solarbalance.coordinator import SolarBalanceCoordinator
from custom_components.solarbalance.core.models import (
    BatteryRole,
    Device,
    Meter,
    MeterKind,
    MpptRole,
    MpptState,
)


def _state(
    value: object, *, age_s: float = 2.0, reported_age_s: float | None = None
) -> SimpleNamespace:
    now = dt_util.utcnow()
    return SimpleNamespace(
        state=str(value),
        attributes={},
        last_updated=now - timedelta(seconds=age_s),
        last_reported=now - timedelta(seconds=age_s if reported_age_s is None else reported_age_s),
    )


def _device() -> Device:
    return Device(
        name="stream",
        battery=BatteryRole(
            capacity_kwh=4.0,
            max_charge_power_w=1200,
            max_discharge_power_w=1200,
            soc_entity="sensor.stream_soc",
            power_entity="sensor.stream_power",
            controllable=True,
        ),
        mppt=MpptRole(peak_power_w=800, power_entity="sensor.stream_pv"),
    )


def _reader(states: dict[str, object]) -> EntityReader:
    return EntityReader(
        MagicMock(),
        [_device()],
        [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.pdl")],
        grid_backup_entity="sensor.backup",
        state_getter=lambda eid: states.get(eid),  # type: ignore[arg-type]
    )


def test_the_reader_labels_every_link_the_loop_depends_on() -> None:
    ages = _reader(
        {
            "sensor.pdl": _state(100.0),
            "sensor.backup": _state(100.0),
            "sensor.stream_soc": _state(55.0),
            "sensor.stream_power": _state(-300.0),
            "sensor.stream_pv": _state(700.0),
        }
    ).link_ages()

    assert set(ages) == {
        "grid/pdl",
        "grid/backup",
        "stream/soc",
        "stream/power",
        "stream/mppt",
    }
    assert all(age is not None and age < 10.0 for age in ages.values())


def test_an_unavailable_entity_reads_as_a_gap_not_as_a_large_age() -> None:
    """The distinction the score is built on: silence is not lateness."""
    ages = _reader(
        {
            "sensor.pdl": _state("unavailable"),
            "sensor.stream_soc": _state(55.0),
            "sensor.stream_power": _state(-300.0),
            "sensor.stream_pv": _state(700.0),
        }
    ).link_ages()

    assert ages["grid/pdl"] is None
    assert ages["stream/soc"] is not None


def test_a_battery_reporting_through_any_of_its_entities_counts_as_fresh() -> None:
    """The STREAM moves its system-power sensor between the two batteries.

    Scoring each candidate separately would report a permanent 50 % outage on
    hardware that is in fact reporting perfectly.
    """
    ages = _reader(
        {
            "sensor.pdl": _state(100.0),
            "sensor.stream_soc": _state(55.0),
            "sensor.stream_power": _state(-300.0, age_s=1.0),
            "sensor.stream_pv": _state(700.0),
        }
    ).link_ages()

    assert ages["stream/power"] is not None
    assert ages["stream/power"] < 5.0


def test_undeclared_links_are_not_watched() -> None:
    """A backup that was never configured must not score as a permanently dead link."""
    reader = EntityReader(
        MagicMock(),
        [],
        [Meter(name="pdl", kind=MeterKind.PDL, power_entity="sensor.pdl")],
        state_getter=lambda eid: {"sensor.pdl": _state(100.0)}.get(eid),  # type: ignore[arg-type]
    )
    assert "grid/backup" not in reader.link_ages()


def _coordinator(hass: HomeAssistant) -> SolarBalanceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return SolarBalanceCoordinator(hass, entry, [_device()], [], [])


@pytest.mark.asyncio
async def test_the_coordinator_scores_what_the_reader_reports(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    coord._reader = MagicMock()  # type: ignore[assignment]
    coord._reader.link_ages.return_value = {"grid/pdl": 3.0, "stream/soc": None}

    now = dt_util.utcnow()
    for i in range(60):
        coord._observe_links(SimpleNamespace(timestamp=now + timedelta(seconds=10 * i)))

    rows = {s.key: s for s in coord.link_health}
    assert rows["grid/pdl"].available_pct == 100.0
    assert rows["stream/soc"].available_pct == 0.0
    worst = coord.weakest_link
    assert worst is not None and worst.key == "stream/soc"


@pytest.mark.asyncio
async def test_a_reader_failure_never_breaks_the_tick(hass: HomeAssistant) -> None:
    """A diagnostic that can stop regulation is worse than no diagnostic."""
    coord = _coordinator(hass)
    coord._reader = MagicMock()  # type: ignore[assignment]
    coord._reader.link_ages.side_effect = RuntimeError("boom")

    coord._observe_links(SimpleNamespace(timestamp=dt_util.utcnow()))
    assert coord.link_health == []


@pytest.mark.asyncio
async def test_removing_a_device_drops_its_link_row(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    coord._reader = MagicMock()  # type: ignore[assignment]
    now = dt_util.utcnow()

    coord._reader.link_ages.return_value = {"grid/pdl": 3.0, "old/soc": 3.0}
    coord._observe_links(SimpleNamespace(timestamp=now))
    assert {s.key for s in coord.link_health} == {"grid/pdl", "old/soc"}

    coord._reader.link_ages.return_value = {"grid/pdl": 3.0}
    coord._observe_links(SimpleNamespace(timestamp=now + timedelta(seconds=10)))
    assert {s.key for s in coord.link_health} == {"grid/pdl"}


@pytest.mark.asyncio
async def test_the_record_is_persisted_and_restored(hass: HomeAssistant) -> None:
    coord = _coordinator(hass)
    coord._reader = MagicMock()  # type: ignore[assignment]
    coord._reader.link_ages.return_value = {"grid/pdl": 3.0}
    now = dt_util.utcnow()
    for i in range(60):
        coord._observe_links(SimpleNamespace(timestamp=now + timedelta(seconds=10 * i)))

    payload = coord._persisted_state()
    assert payload["link_health"]["links"]["grid/pdl"]

    fresh = _coordinator(hass)
    await fresh._store.async_save(payload)
    await fresh.async_restore()
    assert fresh.link_health[0].samples == 60


@pytest.mark.parametrize(
    ("link", "entity"),
    [
        ("stream/soc", "sensor.stream_soc"),
        ("stream/mppt", "sensor.stream_pv"),
        ("stream/power", "sensor.stream_power"),
        ("grid/pdl", "sensor.pdl"),
        ("grid/backup", "sensor.backup"),
    ],
)
def test_an_unchanged_value_still_rewritten_is_a_live_link(link: str, entity: str) -> None:
    """A SoC parked at 34 % or a PV at 0 W overnight is old by ``last_updated`` only."""
    states = {
        "sensor.pdl": _state(100.0),
        "sensor.backup": _state(100.0),
        "sensor.stream_soc": _state(50),
        "sensor.stream_power": _state(-100),
        "sensor.stream_pv": _state(0),
    }
    states[entity] = _state(0, age_s=14_400.0, reported_age_s=5.0)
    assert _reader(states).link_ages()[link] == pytest.approx(5.0, abs=1.0)


def test_a_link_nothing_has_written_to_is_old() -> None:
    states = {
        "sensor.pdl": _state(100.0),
        "sensor.stream_soc": _state(50, age_s=14_400.0),
        "sensor.stream_power": _state(-100),
        "sensor.stream_pv": _state(0),
    }
    assert _reader(states).link_ages()["stream/soc"] == pytest.approx(14_400.0, abs=1.0)


# ---- a micro-inverter that sleeps at night -----------------------------------------


def _snapshot(now: object, *, others_w: float | None, forecast_w: float | None) -> SimpleNamespace:
    mppts = (
        ()
        if others_w is None
        else (MpptState(device_name="other", power_w=others_w, available=True),)
    )
    return SimpleNamespace(timestamp=now, mppts=mppts, pv_forecast_now_w=forecast_w)


def _micro_inverter_coordinator(hass: HomeAssistant) -> SolarBalanceCoordinator:
    coord = _coordinator(hass)
    coord._reader = MagicMock()  # type: ignore[assignment]
    return coord


@pytest.mark.parametrize(
    ("others_w", "forecast_w", "expected"),
    [
        (0.0, 0.0, False),  # night: nothing producing, forecast dark
        (100.0, 0.0, False),  # bogus ~50 W per STREAM at night, forecast says dark
        (400.0, 30.0, True),  # other panels producing under a gloomy forecast
        (0.0, 800.0, True),  # the forecast says sun, the others have not started yet
        (None, 800.0, True),  # a lone MPPT: the forecast alone decides
        (None, 0.0, False),
        (0.0, None, False),  # no forecast configured: the other MPPTs alone decide
        (400.0, None, True),
        (None, None, True),  # no evidence at all: judged as before, never silently excused
    ],
)
@pytest.mark.asyncio
async def test_light_is_expected_from_the_other_panels_or_the_forecast(
    hass: HomeAssistant, others_w: float | None, forecast_w: float | None, expected: bool
) -> None:
    coord = _micro_inverter_coordinator(hass)
    snap = _snapshot(dt_util.utcnow(), others_w=others_w, forecast_w=forecast_w)

    assert coord._solar_expected(snap, "stream", forecast_w) is expected


@pytest.mark.asyncio
async def test_a_micro_inverter_silent_all_night_is_not_flagged(hass: HomeAssistant) -> None:
    coord = _micro_inverter_coordinator(hass)
    coord._reader.link_ages.return_value = {"inverter/mppt": None}  # type: ignore[attr-defined]
    coord._forecast_pv_by_hour = lambda snap: [0.0]  # type: ignore[method-assign]
    now = dt_util.utcnow()

    # Answers by day, silent from dusk through the night, back at dawn.
    for i in range(0, 60):
        coord._reader.link_ages.return_value = {"inverter/mppt": 4.0}  # type: ignore[attr-defined]
        coord._forecast_pv_by_hour = lambda snap: [600.0]  # type: ignore[method-assign]
        coord._observe_links(
            _snapshot(now + timedelta(seconds=10 * i), others_w=500.0, forecast_w=600.0)
        )
    for i in range(60, 2000):
        coord._reader.link_ages.return_value = {"inverter/mppt": None}  # type: ignore[attr-defined]
        coord._forecast_pv_by_hour = lambda snap: [0.0]  # type: ignore[method-assign]
        coord._observe_links(
            _snapshot(now + timedelta(seconds=10 * i), others_w=0.0, forecast_w=0.0)
        )

    row = next(s for s in coord.link_health if s.key == "inverter/mppt")
    assert row.conditional is True
    assert row.available_pct == 100.0
    assert row.longest_gap_s == 0.0
    assert row.verdict == "healthy"


@pytest.mark.asyncio
async def test_a_silent_micro_inverter_is_flagged_while_the_sun_is_up(hass: HomeAssistant) -> None:
    coord = _micro_inverter_coordinator(hass)
    coord._reader.link_ages.return_value = {"inverter/mppt": None}  # type: ignore[attr-defined]
    coord._forecast_pv_by_hour = lambda snap: [900.0]  # type: ignore[method-assign]
    now = dt_util.utcnow()

    for i in range(0, 400):
        coord._observe_links(
            _snapshot(now + timedelta(seconds=10 * i), others_w=700.0, forecast_w=900.0)
        )

    row = next(s for s in coord.link_health if s.key == "inverter/mppt")
    assert row.available_pct == 0.0
    assert row.verdict == "unreliable"


@pytest.mark.asyncio
async def test_the_wake_up_grace_spares_a_late_riser(hass: HomeAssistant) -> None:
    """The micro-inverter starts minutes after the others: that is not an outage."""
    coord = _micro_inverter_coordinator(hass)
    now = dt_util.utcnow()
    coord._forecast_pv_by_hour = lambda snap: [0.0]  # type: ignore[method-assign]
    coord._reader.link_ages.return_value = {"inverter/mppt": None}  # type: ignore[attr-defined]
    for i in range(0, 100):  # night
        coord._observe_links(
            _snapshot(now + timedelta(seconds=10 * i), others_w=0.0, forecast_w=0.0)
        )

    coord._forecast_pv_by_hour = lambda snap: [500.0]  # type: ignore[method-assign]
    for i in range(100, 160):  # 10 min of light, inverter still asleep (within the 15 min grace)
        coord._observe_links(
            _snapshot(now + timedelta(seconds=10 * i), others_w=400.0, forecast_w=500.0)
        )
    coord._reader.link_ages.return_value = {"inverter/mppt": 3.0}  # type: ignore[attr-defined]
    for i in range(160, 200):
        coord._observe_links(
            _snapshot(now + timedelta(seconds=10 * i), others_w=400.0, forecast_w=500.0)
        )

    row = next(s for s in coord.link_health if s.key == "inverter/mppt")
    assert row.dropouts == 0
    assert row.available_pct == 100.0
