# Device mapping guide

SolarBalance is vendor-agnostic: it doesn't care what brand your hardware is, as long as you can map its Home Assistant entities to the SolarBalance roles. This guide gives mapping recipes for common families.

## Concepts recap

A **device** is a configuration container. It declares one or more **roles**:

- `battery` — a stockable energy reservoir
- `mppt` — a solar charge controller
- `inverter` — DC↔AC conversion (with optional EPS / backup outlets)

For a typical all-in-one portable station (Ecoflow, Jackery, BLUETTI), declare **one device with three roles**. For a split system (Victron, Deye + separate batteries), declare **multiple devices each with a single role**, and use `feeds` on the MPPT role to express the topology.

## Recipe — Ecoflow / Jackery (cloud integration)

These stations expose battery, solar input, and AC output as separate sensors via cloud integrations. Map them as a single device:

```yaml
- name: ecoflow_living_room
  roles:
    battery:
      capacity_kwh: 3.6                       # check your model's nominal
      chemistry: lifepo4                      # most modern Ecoflow / all Jackery
      max_charge_power_w: 1800
      max_discharge_power_w: 1800
      soc_entity: sensor.ecoflow_living_room_main_soc
      power_entity: sensor.ecoflow_living_room_battery_power
      power_sign_convention: charge_positive  # verify with your integration
    mppt:
      peak_power_w: 1000
      power_entity: sensor.ecoflow_living_room_solar_input_watts
    inverter:
      nominal_power_w: 2400
      eps_capable: true
      ac_output_power_entity: sensor.ecoflow_living_room_ac_output_watts
```

**Sign convention check**: in Developer Tools, observe the `power_entity` while the battery is clearly charging from the wall. If positive → `charge_positive`. If negative → `discharge_positive`.

## Recipe — Victron (separate MPPT + Multi + battery)

Victron systems are typically split. Declare each component as its own device:

```yaml
- name: mppt_roof_south
  roles:
    mppt:
      peak_power_w: 3000
      power_entity: sensor.mppt_south_pv_power
      feeds: ["battery_main"]                 # references the battery device

- name: mppt_roof_east
  roles:
    mppt:
      peak_power_w: 1500
      power_entity: sensor.mppt_east_pv_power
      feeds: ["battery_main"]

- name: battery_main
  roles:
    battery:
      capacity_kwh: 14.4
      chemistry: lifepo4
      max_charge_power_w: 5000
      max_discharge_power_w: 8000
      soc_entity: sensor.bmv_soc
      power_entity: sensor.bmv_power
      power_sign_convention: discharge_positive  # Victron default

- name: multiplus_main
  roles:
    inverter:
      nominal_power_w: 5000
      eps_capable: true
      ac_output_power_entity: sensor.multiplus_ac_out_power
      ac_input_power_entity: sensor.multiplus_ac_in_power
```

## Recipe — Hybrid inverter (Deye, Sungrow, Huawei, Solis)

These integrate battery, MPPT and inverter in one box. Single device with three roles:

```yaml
- name: hybrid_main
  roles:
    battery:
      capacity_kwh: 10.24
      chemistry: lifepo4
      max_charge_power_w: 5000
      max_discharge_power_w: 5000
      soc_entity: sensor.hybrid_main_battery_soc
      power_entity: sensor.hybrid_main_battery_power
    mppt:
      peak_power_w: 6000
      power_entity: sensor.hybrid_main_pv_total_power
    inverter:
      nominal_power_w: 5000
      ac_output_power_entity: sensor.hybrid_main_ac_output_power
```

If your hybrid exposes per-string MPPT (PV1, PV2, PV3), you can either sum them in a template sensor and use one MPPT role, or declare multiple MPPT-only devices linked via `feeds`. Single template is simpler for v0.1.

## Recipe — Battery without explicit power entity

If your integration only exposes separate `charge_power` and `discharge_power` (always positive), use the dual-entity form:

```yaml
battery:
  capacity_kwh: 5.0
  max_charge_power_w: 2500
  max_discharge_power_w: 2500
  soc_entity: sensor.bat_soc
  charge_power_entity: sensor.bat_charge_power      # always >= 0
  discharge_power_entity: sensor.bat_discharge_power # always >= 0
```

SolarBalance will compute `power = charge_power - discharge_power` internally.

## Verifying your mapping

After applying the YAML and reloading SolarBalance, check `sensor.solarbalance_baseline_consumption`:

- A reasonable value (between a few hundred W and a few kW for typical homes) means your power signs are consistent.
- A persistently negative or wildly large value means at least one entity has the wrong sign convention or is mismapped. The most common culprit is `power_sign_convention` on a battery role.

## Adding a new device family

If your hardware family isn't covered above, please [open a device support issue](https://github.com/solarbalance/ha-solarbalance/issues/new?template=device_support.yml) — community-contributed examples land in `examples/config/devices/` and seed the future config-flow assistant.
