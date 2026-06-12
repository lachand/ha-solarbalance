# SolarBalance

> Home Energy Management System (HEMS) for Home Assistant — vendor-agnostic, configurable, and ready to grow with your setup.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

SolarBalance orchestrates photovoltaic production, battery storage, and electrical loads in your home to meet one or several energy goals (self-consumption, cost minimization, autonomy, hardware longevity), while adapting to dynamic context (tariffs, weather, grid alerts).

> **Status**: v1.0 MVP — ready for early adopters. Core engine, all strategies, watchdog, services, and Lovelace examples are functional. Direct hardware control (writing to inverters) is scheduled for v2.

## Highlights

- **Vendor-agnostic** — declare any inverter, battery or charger via Home Assistant entity mapping. Tested with Ecoflow, Jackery; works with Victron, Deye, etc.
- **Read-first, write-later** — v1 computes and publishes setpoints as HA entities without writing to your hardware. Validate behavior before activating direct control in v2.
- **Multi-strategy arbitration** — order strategies by priority (self-consumption, cost-min, backup, longevity, peak-shaving, revenue-max) and let the arbiter combine them.
- **Zero-injection regulation** — software PI controller targeting your grid meter (Shelly 3EM or any signed-power sensor at the PDL).
- **Storm mode** — automatic SoC ramp-up on Météo-France weather warnings.
- **Loadable load types** — on/off, stepped, modulating (EV chargers, dimmable resistive loads).
- **Forecast-aware** — integrates with existing Solcast / Forecast.Solar / OpenMeteo PV forecasts.
- **Watchdog & graceful degradation** — stale entity detection auto-switches to `degraded` mode, then auto-recovers without restart.
- **HA services** — `pause`, `resume`, `force_charge`, `force_discharge`, `set_mode`, `activate_storm_mode` callable from automations or the dashboard.

## Companion frontend

Visualization is provided by:

- **v1**: composition of [`power-flow-card-plus`](https://github.com/flixlix/power-flow-card-plus), [`apexcharts-card`](https://github.com/RomRider/apexcharts-card), and [`mushroom`](https://github.com/piitaya/lovelace-mushroom). Example dashboards in [`examples/lovelace/`](examples/lovelace/).
- **v1.5+**: dedicated [`solarbalance-card`](https://github.com/<org>/solarbalance-card) (separate repo).

## Installation

### HACS (recommended once published)

1. HACS → Integrations → Custom repositories → add `https://github.com/<org>/ha-solarbalance` (Integration).
2. Install **SolarBalance**.
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → search "SolarBalance".

### Manual

Copy `custom_components/solarbalance/` into your HA `custom_components/` folder and restart.

## Quick start

Minimal `configuration.yaml` snippet declaring one Ecoflow station as a battery+MPPT+inverter device, and a Shelly 3EM as the grid meter:

```yaml
solarbalance:
  devices:
    - name: ecoflow_living_room
      roles:
        battery:
          capacity_kwh: 3.6
          max_charge_power_w: 1800
          max_discharge_power_w: 1800
          soc_entity: sensor.ecoflow_living_room_soc
          power_entity: sensor.ecoflow_living_room_battery_power
          power_sign_convention: charge_positive
        mppt:
          peak_power_w: 1000
          power_entity: sensor.ecoflow_living_room_solar_input
        inverter:
          nominal_power_w: 2400
          ac_output_power_entity: sensor.ecoflow_living_room_ac_output
  meters:
    - name: pdl
      kind: pdl
      power_entity: sensor.shelly_3em_total_power
```

Then add the integration via UI for global parameters (priorities, zero-injection settings, forecast sources).

Full guide: [`docs/getting-started.md`](docs/getting-started.md).

## Documentation

- [Specifications](docs/SPECIFICATIONS.md) — full design document
- [Getting started](docs/getting-started.md) — first setup in 15 minutes
- [Device mapping](docs/device-mapping.md) — guide per equipment type
- [Strategies](docs/strategies.md) — algorithm details
- [API reference](docs/api.md) — services and exposed entities
- [Troubleshooting](docs/troubleshooting.md)

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## License

Apache 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
