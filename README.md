# SolarBalance

> Home Energy Management System (HEMS) for Home Assistant — vendor-agnostic, configurable, and ready to grow with your setup.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

SolarBalance orchestrates photovoltaic production, battery storage, and electrical loads in your home to meet one or several energy goals (self-consumption, cost minimization, autonomy, hardware longevity), while adapting to dynamic context (tariffs, weather, grid alerts).

> **Status**: stable **v2.0.7**; pre-release **v2.0.8-beta55** (enable beta versions in HACS) starts **Wave 4 — predictive**: a learned hour-of-day **consumption forecast** now feeds the planner. Core engine, all strategies, **active hardware control** (incl. mode-switch batteries like the EcoFlow STREAM), a **device-preset add wizard** (auto-detects matching entities), zero-injection (auto-tuned, AC-output-aware), the **SoC equaliser** (PV-gated), watchdog, services and Lovelace examples are functional. The consumption profile is **recorder-seeded** (accurate from day one) and refined online. Next in Wave 4: real-time PV-drop detection, battery-health throttling.

## Highlights

- **Vendor-agnostic** — declare any inverter, battery or charger via Home Assistant entity mapping. Tested with Ecoflow, Jackery; works with Victron, Deye, etc.
- **No-YAML configuration** — add batteries, inverters, meters and loads from the UI (integration → **Add**), each as an editable sub-entry. Existing YAML is migrated automatically on first start.
- **Multi-strategy arbitration** — order strategies by priority (self-consumption, cost-min, backup, longevity, peak-shaving, revenue-max) and let the arbiter combine them.
- **Zero-injection regulation** — software PI controller targeting your grid meter (Shelly 3EM or any signed-power sensor at the PDL), with an anti-yoyo settle window when a big load drops.
- **Active control (v2)** — optionally write charge/discharge/mode setpoints to your batteries and curtail a micro-inverter, through the single `ActiveControlPublisher` (off by default, per-device opt-in).
- **SoC equaliser** — indirectly steer a non-controllable (e.g. cloud) battery toward the controllable fleet's mean SoC via the zero-injection setpoint; proportional, slow, dead-time-aware (no pumping).
- **Battery mapping flexibility** — declare battery power as a single signed sensor *or* a separate charge + discharge pair; capacity-weighted (energy-true) average SoC, plus remaining/usable energy sensors (kWh).
- **Per-load controls** — each load gets switches: **Charge now** (grid-backed force charge, battery spared), **Keep running** (exempt from shedding), **Off-peak only** (run only in cheap/HC/non-red windows). Reachable from the panel too.
- **Tariffs** — flat / HC-HP / EDF Tempo / spot (Nordpool/EPEX), in YAML or UI; cost & savings tracking with month/year cumulative sensors wired to the HA Energy dashboard.
- **Storm mode** — automatic SoC ramp-up on Météo-France weather warnings.
- **Forecast-aware** — integrates with existing Solcast / Forecast.Solar / OpenMeteo PV forecasts.
- **Diagnostics** — `config_health` binary sensor + persistent notifications for config mistakes (zero battery capacity, missing `min_charge_w`…), plus a downloadable HA diagnostics export.
- **HA services** — `pause`, `resume`, `force_charge`, `force_discharge`, `force_charge_load`, `cancel_force_charge_load`, `set_mode`, `activate_storm_mode` callable from automations or the dashboard.

## Installation

### HACS (recommended once published)

1. HACS → Integrations → Custom repositories → add `https://github.com/lachand/ha-solarbalance` (Integration).
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

YAML is optional: you can instead add every device/meter/load from the UI
(integration → **Add a battery / inverter / load / meter**) and edit them later
with the ✏️ button. Global parameters live in the integration's **Configure**
options, split into **Regulation & behaviours / PV forecast / Tariff & prices**.

Full guide: [`docs/getting-started.md`](docs/getting-started.md).

## Documentation

- [Specifications](docs/SPECIFICATIONS.md) — full design document
- [Configuration reference](docs/configuration-reference.md) — every option (UI + YAML)
- [Getting started](docs/getting-started.md) — first setup in 15 minutes
- [Device mapping](docs/device-mapping.md) — guide per equipment type
- [Strategies](docs/strategies.md) — algorithm details
- [API reference](docs/api.md) — services and exposed entities
- [Troubleshooting](docs/troubleshooting.md)
- [Backlog & roadmap](docs/BACKLOG.md) — planned features and implementation order

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## License

Apache 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
