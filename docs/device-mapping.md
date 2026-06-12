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

## Recipe — Battery you can monitor but not control

Some batteries expose their SoC and power over Home Assistant but offer **no way
to command charge/discharge** — the only option is to leave them in their own
"automatic" mode. Declare such a battery with `controllable: false`:

```yaml
- name: battery_auto
  roles:
    battery:
      capacity_kwh: 5.0
      max_charge_power_w: 2500
      max_discharge_power_w: 2500
      soc_entity: sensor.batauto_soc
      power_entity: sensor.batauto_power
      controllable: false      # stats reported, but never commanded by the HEMS
      # ac_charge_limit_w: 800  # optional: max it can absorb from AC (defaults to
      #                         # max_charge_power_w). Bounds how hard the fleet
      #                         # discharges to charge it — keep it from spilling
      #                         # the surplus to the grid.
```

With this flag:

- The battery still feeds the snapshot (its SoC/power count toward
  `baseline_consumption` and the grid balance), so the HEMS reacts correctly
  around it.
- It is **excluded from the balancing controller** — it never receives a
  setpoint, and never appears in `setpoint_charge/discharge_per_battery_w`.
- An **indirect SoC equaliser** steers it toward the mean SoC of your
  controllable batteries by offering a surplus/deficit through the zero-injection
  setpoint: to charge it, the HEMS biases the grid setpoint so the controllable
  fleet discharges (surplus the automatic battery absorbs); to discharge it, the
  opposite. It closes the loop on the battery's **measured** power, ramps the
  offer slowly (`soc_equaliser_probe_step_w`, default 150 W/tick), and **backs
  off** if the surplus reaches the grid instead of the battery — so it never
  forces grid export/import. The target charge rate is bounded by
  `ac_charge_limit_w` (`/ max_discharge_power_w`) and the offer by
  `soc_equaliser_max_w` (default 1500 W). **Requires `zero_injection_enabled`**
  and is **off by default** — enable `soc_equaliser_enabled` once validated (on
  slow/cloud batteries it can still hunt).

Note that indirect steering shuffles energy through two extra conversions, so it
trades a little round-trip efficiency for SoC homogeneity across the fleet.

### Actively controlling your controllable batteries (v2)

The steering above only changes SolarBalance's *published* setpoints. To make it
actually drive your hardware, enable active control and declare whichever
setpoint entities your battery exposes — charge power, discharge power, and/or an
operating mode:

```yaml
- name: battery_main          # a controllable battery
  roles:
    battery:
      capacity_kwh: 5.0
      max_charge_power_w: 2500
      max_discharge_power_w: 2500
      soc_entity: sensor.main_soc
      power_entity: sensor.main_power
      active_control_enabled: true
      discharge_power_setpoint_entity: number.main_discharge_setpoint  # W
      charge_power_setpoint_entity: number.main_charge_setpoint        # W (optional)
      mode_setpoint_entity: select.main_mode    # charge|discharge|idle (optional)
```

Then turn on the global **`active_control_enabled`** option in the Config Flow
(off by default — it is the only thing that lets SolarBalance write to your
equipment). With both on, every tick the balancing controller's per-battery
power is written: charge power to `charge_power_setpoint_entity`, discharge power
to `discharge_power_setpoint_entity` (`number.set_value` / `input_number.set_value`),
and the mode (`charge` / `discharge` / `idle`) to `mode_setpoint_entity`
(`select.select_option`). A battery at its SoC floor is never told to discharge,
at its ceiling never to charge. Writes are suspended in degraded mode.

The **mode** strings are canonical (`charge`/`discharge`/`idle`); if your device's
select uses different labels, bridge them with a `template select`.

`active_control_enabled` requires `controllable: true` and at least one of the
three setpoint entities — it is rejected at load time otherwise.

### Curtailing a micro-inverter for zero-injection (v2)

When the controllable batteries are **full** and can no longer absorb PV surplus,
SolarBalance can cap a micro-inverter's output so production tracks consumption
(zero-injection's last resort, after the batteries). Declare a writable output
limit (W) on the `mppt` role:

```yaml
- name: micro_inverter_roof
  roles:
    mppt:
      peak_power_w: 800
      power_entity: sensor.micro_roof_power
      active_control_enabled: true
      power_limit_setpoint_entity: number.micro_roof_limit   # W, e.g. OpenDTU/AhoyDTU
```

With the global `active_control_enabled` on, SolarBalance writes a **sticky**
output limit: it lowers it only while the batteries are saturated and the grid
exports past its setpoint, and raises it again when the batteries can absorb
again or the grid imports. The limit is released (set to peak) in degraded mode.
Watch the `PV output limit` diagnostic sensor while tuning.

## Verifying your mapping

After applying the YAML and reloading SolarBalance, check `sensor.solarbalance_baseline_consumption`:

- A reasonable value (between a few hundred W and a few kW for typical homes) means your power signs are consistent.
- A persistently negative or wildly large value means at least one entity has the wrong sign convention or is mismapped. The most common culprit is `power_sign_convention` on a battery role.

## Adding a new device family

If your hardware family isn't covered above, please [open a device support issue](https://github.com/solarbalance/ha-solarbalance/issues/new?template=device_support.yml) — community-contributed examples land in `examples/config/devices/` and seed the future config-flow assistant.
