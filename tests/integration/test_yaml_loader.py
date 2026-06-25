"""Tests for the YAML loader (forecast block)."""

import pytest
from homeassistant.exceptions import ConfigEntryError

from custom_components.solarbalance.core.forecast import ForecastUnit
from custom_components.solarbalance.yaml_loader import parse_yaml_config


def test_parse_forecast_block() -> None:
    raw = {
        "forecast": {
            "unit": "kwh",
            "hours": [
                {"hour": 0, "entity": "sensor.pv_this_hour"},
                {"hour": 1, "entity": "sensor.pv_next_hour"},
            ],
        }
    }
    _devices, _meters, _loads, forecast, _tariff = parse_yaml_config(raw)
    assert forecast is not None
    assert forecast.unit is ForecastUnit.KWH
    assert forecast.hour_entities == ((0, "sensor.pv_this_hour"), (1, "sensor.pv_next_hour"))


def test_forecast_unit_defaults_to_watt() -> None:
    raw = {"forecast": {"hours": [{"hour": 0, "entity": "sensor.now"}]}}
    _devices, _meters, _loads, forecast, _tariff = parse_yaml_config(raw)
    assert forecast is not None
    assert forecast.unit is ForecastUnit.W


def test_no_forecast_block_is_none() -> None:
    _devices, _meters, _loads, forecast, tariff = parse_yaml_config({})
    assert forecast is None
    assert tariff is None


def test_parse_hc_hp_tariff_block() -> None:
    raw = {
        "tariff": {
            "type": "hc_hp",
            "export_price": 0.13,
            "slots": [
                {"start": "22:00", "end": "06:00", "price": 0.2068},
                {"start": "06:00", "end": "22:00", "price": 0.27},
            ],
        }
    }
    *_rest, tariff = parse_yaml_config(raw)
    assert tariff is not None
    assert tariff["type"] == "hc_hp"
    assert len(tariff["slots"]) == 2


def test_parse_tempo_tariff_block() -> None:
    raw = {
        "tariff": {
            "type": "tempo",
            "color_entity": "sensor.tempo",
            "prices": {"red": {"hc": 0.16, "hp": 0.76}},
        }
    }
    *_rest, tariff = parse_yaml_config(raw)
    assert tariff is not None and tariff["type"] == "tempo"
    assert tariff["color_entity"] == "sensor.tempo"


def test_invalid_forecast_unit_rejected() -> None:
    raw = {"forecast": {"unit": "joules", "hours": [{"hour": 0, "entity": "sensor.now"}]}}
    with pytest.raises(ConfigEntryError):
        parse_yaml_config(raw)


def _stream_battery(reserve: str) -> dict:
    return {
        "devices": [
            {
                "name": "stream",
                "roles": {
                    "battery": {
                        "capacity_kwh": 3.9,
                        "max_charge_power_w": 1200,
                        "max_discharge_power_w": 2300,
                        "soc_entity": "sensor.stream_soc",
                        "power_entity": "sensor.stream_power",
                        "reserve_soc_setpoint_entity": reserve,
                    }
                },
            }
        ]
    }


def test_setpoint_entity_without_domain_rejected() -> None:
    # The exact bug class: "ef_xxxxxx_backup_reserve" (no domain) must be rejected.
    with pytest.raises(ConfigEntryError):
        parse_yaml_config(_stream_battery("ef_xxxxxx_backup_reserve"))


def test_valid_setpoint_entity_accepted() -> None:
    devices, *_rest = parse_yaml_config(_stream_battery("number.ef_xxxxxx_backup_reserve"))
    assert devices[0].battery.reserve_soc_setpoint_entity == "number.ef_xxxxxx_backup_reserve"


def test_mppt_temperature_entity_round_trips() -> None:
    cfg = {
        "devices": [
            {
                "name": "inverter",
                "roles": {
                    "mppt": {
                        "peak_power_w": 800,
                        "power_entity": "sensor.ef_bkxxxx_grid_power",
                        "temperature_entity": "sensor.ef_bkxxxx_temperature",
                    }
                },
            }
        ]
    }
    devices, *_rest = parse_yaml_config(cfg)
    assert devices[0].mppt.temperature_entity == "sensor.ef_bkxxxx_temperature"


def test_mppt_extra_power_entities_round_trip() -> None:
    cfg = {
        "devices": [
            {
                "name": "indevolt",
                "roles": {
                    "mppt": {
                        "peak_power_w": 2000,
                        "power_entity": "sensor.indevolt_mppt1",
                        "extra_power_entities": [
                            "sensor.indevolt_mppt2",
                            "sensor.indevolt_mppt3",
                        ],
                    }
                },
            }
        ]
    }
    devices, *_rest = parse_yaml_config(cfg)
    assert devices[0].mppt.power_entities == (
        "sensor.indevolt_mppt1",
        "sensor.indevolt_mppt2",
        "sensor.indevolt_mppt3",
    )


def test_meter_invert_sign_round_trip() -> None:
    cfg = {
        "meters": [
            {"name": "huawei", "kind": "pdl", "power_entity": "sensor.huawei", "invert_sign": True}
        ]
    }
    _devices, meters, *_rest = parse_yaml_config(cfg)
    assert meters[0].invert_sign is True


def test_meter_invert_sign_defaults_false() -> None:
    cfg = {"meters": [{"name": "pdl", "kind": "pdl", "power_entity": "sensor.grid"}]}
    _devices, meters, *_rest = parse_yaml_config(cfg)
    assert meters[0].invert_sign is False
