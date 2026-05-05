# Getting started

This guide walks you through your first SolarBalance setup in about 15 minutes.

## Prerequisites

- Home Assistant **2026.1.0** or later
- HACS installed (recommended; manual install is also documented in the README)
- Your inverters and batteries already integrated into Home Assistant — SolarBalance does not talk to hardware directly, it consumes existing entities
- A power meter at your delivery point (Shelly 3EM is the reference; any sensor exposing signed grid power works)

## Step 1 — Install the integration

Via HACS:

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/solarbalance/ha-solarbalance` as Integration
3. Install **SolarBalance**, then restart Home Assistant

## Step 2 — Identify your entities

For each device, note down the entity IDs you'll need to map:

- **Battery**: SoC (`%`), battery power (`W`)
- **MPPT** (if present): solar input power (`W`)
- **Inverter** (if applicable): AC output power (`W`), EPS active (binary)
- **Grid meter**: signed power at PDL (`W`, positive = import)

Quick way to find them: Developer Tools → States → filter by your device name.

## Step 3 — Declare your devices in YAML

Add to `configuration.yaml` (or include from a separate file):

```yaml
solarbalance:
  devices:
    - name: my_station
      roles:
        battery:
          capacity_kwh: 3.6
          max_charge_power_w: 1800
          max_discharge_power_w: 1800
          soc_entity: sensor.my_station_soc
          power_entity: sensor.my_station_battery_power
          power_sign_convention: charge_positive   # or discharge_positive
        mppt:
          peak_power_w: 1000
          power_entity: sensor.my_station_solar_input
        inverter:
          nominal_power_w: 2400
          ac_output_power_entity: sensor.my_station_ac_output

  meters:
    - name: pdl
      kind: pdl
      power_entity: sensor.shelly_3em_total_power
```

See `examples/config/` for more elaborate setups (multiple devices, pilotable loads).

## Step 4 — Add the integration via UI

Settings → Devices & Services → **Add Integration** → search "SolarBalance".

You'll be asked for global parameters:

- **Priority order** — drag to reorder. The first one is the dominant strategy.
- **Tick interval** (default 10 s)
- **Zero injection** — enable, set the target (typically 0 W) and hysteresis (50 W)
- **PV forecast entity** (optional — picks up Solcast / Forecast.Solar / OpenMeteo)
- **Weather warning entity** (optional — Météo-France)
- **Tariff configuration** — at minimum a default import price

## Step 5 — Read the entities, validate behavior

After setup, SolarBalance starts publishing read-only **calculated setpoints** as sensors:

- `sensor.solarbalance_setpoint_charge_my_station` — what it would charge
- `sensor.solarbalance_setpoint_discharge_my_station` — what it would discharge
- `sensor.solarbalance_zero_injection_error` — current ZI deviation
- `sensor.solarbalance_arbitration_log` — last decision rationale

**v0.1 does not write to your hardware.** This is intentional: observe the published setpoints and confirm they match your intuition before activating direct control (planned for v2). You can also wire your own automations on these sensors today.

## Step 6 — Add the dashboard

Copy `examples/lovelace/dashboard.yaml` into a new Lovelace view. Recommended companion HACS cards: `power-flow-card-plus`, `apexcharts-card`, `mushroom`.

## Where to next

- [Device mapping guide](device-mapping.md) — examples per brand
- [Strategies](strategies.md) — how each priority computes its decision
- [API reference](api.md) — all services and entities
- [Troubleshooting](troubleshooting.md)
