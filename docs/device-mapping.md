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

## Recipe — EcoFlow STREAM (active control, via the add wizard)

The EcoFlow STREAM is **actively controllable** over local Bluetooth (Unofficial
EcoFlow BLE integration): SolarBalance can drive its **charge and discharge**, not
just read it. Two things make it special:

1. **It is exposed as two BLE devices.** Add them as **two separate SolarBalance
   devices**:
   - the **battery** — prefix `ef_xxxxxx` (its serial), added as **a battery**;
   - the **inverter** — prefix `ef_bk…`, added as **an inverter (MPPT) only**. It
     carries the curtailment knob `maximum_output_power`.
2. **Charge is a mode switch, not a single setpoint.** The box does one direction
   at a time via its `energy_strategy` select: `scheduled` (charge) /
   `self_powered` (discharge). SolarBalance handles the whole sequence for you
   (zero the opposite direction → switch the strategy → set the power), and keeps
   the opposite direction at 0 every tick so it never charges and discharges at
   once.

### Add it with the wizard (recommended)

Use **Settings → Devices & Services → SolarBalance → Add**, and pick the preset
from the **"Device model"** dropdown — the form is pre-filled and the matching
entities are auto-detected from the device prefix:

- **Add a battery → preset "EcoFlow STREAM"** → fills SoC, battery power, charge
  (`charging_power_limit`), discharge (`base_load_power`), mode
  (`energy_strategy`, `scheduled`/`self_powered`), backup reserve, temperature.
- **Add an inverter → preset "EcoFlow STREAM inverter"** → fills the output power
  (`grid_power`) and the curtailment limit (`maximum_output_power`), active
  control on.

**Verify after auto-fill**: `capacity_kwh`, `max_charge_power_w` /
`max_discharge_power_w` (the STREAM's **AC max is ~2300 W, solar included** — set
both to your real AC max so the discharge setpoint is bounded), and the inverter's
`peak_power_w`.

The equivalent YAML (for reference — the wizard writes this for you):

```yaml
- name: ecoflow_stream            # the ef_xxxxxx battery
  roles:
    battery:
      capacity_kwh: 1.92
      max_charge_power_w: 2300
      max_discharge_power_w: 2300
      soc_entity: sensor.ef_xxxxxx_battery_level
      power_entity: sensor.ef_xxxxxx_battery_power
      power_sign_convention: charge_positive
      controllable: true
      active_control_enabled: true
      charge_power_setpoint_entity: number.ef_xxxxxx_charging_power_limit
      discharge_power_setpoint_entity: number.ef_xxxxxx_base_load_power
      mode_setpoint_entity: select.ef_xxxxxx_energy_strategy
      charge_mode_option: scheduled
      discharge_mode_option: self_powered
      reserve_soc_setpoint_entity: number.ef_xxxxxx_backup_reserve
- name: ecoflow_stream_inverter   # the ef_bk… inverter (curtailable)
  roles:
    mppt:
      peak_power_w: 800
      power_entity: sensor.ef_bkxxxx_grid_power
      active_control_enabled: true
      power_limit_setpoint_entity: number.ef_bkxxxx_maximum_output_power
```

### Two STREAM batteries (one device per battery)

A STREAM stack with **two batteries** exposes **per-battery** SoC, PV (MPPT), charge
limit and base-load, but **one system-level power** sensor for the whole stack. Declare
**one device per battery** and:

- `power_entity`: the **same** system power sensor on both devices — SolarBalance detects
  the shared entity and **counts it once** (splits it evenly per device), so the fleet
  power isn't double-counted.
- MPPT: each device gets **its own** panel sensor (1 entity, real `peak_power_w`).
- `charge_power_setpoint_entity`: each battery's own `charging_power_limit` (per-battery).
- `discharge_power_setpoint_entity`: each battery's own `base_load_power`, **plus
  `discharge_mirror_group: stream` on both** — the discharge is a shared total mirrored
  to each base-load (800 W on both = 800 W total, not 1600). Charge stays per-battery.

```yaml
- name: ecoflow_stream_a
  roles:
    battery:
      soc_entity: sensor.ef_xxxxxx_a_battery_level
      power_entity: sensor.ef_xxxxxx_system_power          # shared (counted once)
      charge_power_setpoint_entity: number.ef_xxxxxx_a_charging_power_limit
      discharge_power_setpoint_entity: number.ef_xxxxxx_a_base_load_power
      discharge_mirror_group: stream
      active_control_enabled: true
      # ... capacity, max powers, mode_setpoint_entity, reserve, etc.
    mppt:
      peak_power_w: 520
      power_entity: sensor.ef_xxxxxx_a_solar_power
- name: ecoflow_stream_b
  roles:
    battery:
      soc_entity: sensor.ef_xxxxxx_b_battery_level
      power_entity: sensor.ef_xxxxxx_system_power          # same entity → counted once
      charge_power_setpoint_entity: number.ef_xxxxxx_b_charging_power_limit
      discharge_power_setpoint_entity: number.ef_xxxxxx_b_base_load_power
      discharge_mirror_group: stream
      active_control_enabled: true
    mppt:
      peak_power_w: 520
      power_entity: sensor.ef_xxxxxx_b_solar_power
```

The two batteries' SoC self-balances in the firmware, so SolarBalance does not steer
them against each other; its charge split only sets the total. The per-device **"Battery
power"** sensor reads ~half the system power (there is no true per-battery power) — that's
expected; the **fleet** power is correct.

### A non-controllable cloud battery alongside (e.g. Jackery)

Declare a cloud-only battery (Jackery HomePower) with `controllable: false` and
**no setpoint entities** — SolarBalance reads it but cannot command it, and steers
it indirectly via the SoC equaliser and the cloud guards. Recommended options
(*Configure → Regulation*): **"Don't discharge the fleet to feed a self-charging
cloud battery"** (on), **adaptive volatility damper** (on), and optionally **"Stop
a self-charging cloud battery"** (it only acts in surplus, never under a real load).

### Debugging

Add the **"Active clamp"** diagnostic sensor to a chart: it names which guard set
the fleet target each tick (`base` / `no_feed` / `stop_cloud` / `no_charge_floor`
/ `grid_*`), so a surprising target is self-explanatory.

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

## Recipe — EcoFlow River 2 (charge-only surplus sink)

A **River 2** portable station (via the *EcoFlow BLE (Unofficial)* integration, domain
`ef_ble`) can charge from the grid and from its own solar input, and powers isolated
appliances on its AC socket — but it **cannot inject back to the grid**. Model it as a
**charge-only** controllable battery: SolarBalance charges it from surplus (export) and
**never** commands it to discharge.

```yaml
- name: river2_garage
  roles:
    battery:
      capacity_kwh: 0.256            # River 2 base (Max 0.512, Pro 0.768)
      max_charge_power_w: 360        # AC input max: base 360, Max 660, Pro 940
      max_discharge_power_w: 0       # ← charge-only (never discharges to grid/house)
      soc_entity: sensor.ef_r60xxxx_battery_level
      power_entity: sensor.ef_r60xxxx_ac_input_power   # grid-facing charge draw (+ = charge)
      power_sign_convention: charge_positive
      controllable: true
      active_control_enabled: true
      charge_power_setpoint_entity: number.ef_r60xxxx_ac_charging_speed   # "AC Charging Speed" slider
      charge_limit_soc_setpoint_entity: number.ef_r60xxxx_max_charge_limit  # "Max Charge Limit" %
      charge_ceiling_soc_pct: 100    # charge up to this when there IS surplus (default soc_max)
```

Why these two setpoints: the `ef_ble` **AC charging power** slider floors at **100 W**, so
SolarBalance can't command 0. Instead it gates charging with the **max-charge-SoC limit**:
when there's surplus it raises the limit to `charge_ceiling_soc_pct` and drives the power
slider; when there's no surplus it drops the limit to the current SoC so the box stops (no
phantom ~100 W grid draw). The gate is hysteretic so a near-zero target doesn't flap it.

Notes:

- **Do not** declare the River 2's own solar as an `mppt` role — it charges the battery on
  the DC side and never reaches the grid; declaring it would inflate grid-facing PV. It just
  charges the River 2 "for free" in the background; SolarBalance only sees the grid-side draw.
- **Do not** add appliances on the River 2's AC socket to `local_ac_load_entities` — they're
  powered internally (isolated) and appear on neither the house meter nor `ac_input_power`.
  Exception: if the station runs in **EPS/passthrough** so grid flows *through* it to the load,
  a small phantom may appear in `ac_input_power` — only then compensate.
- Leave `discharge_power_setpoint_entity` and `mode_setpoint_entity` unset (a charge-only
  battery rejects a discharge setpoint).

## Verifying your mapping

After applying the YAML and reloading SolarBalance, check `sensor.solarbalance_baseline_consumption`:

- A reasonable value (between a few hundred W and a few kW for typical homes) means your power signs are consistent.
- A persistently negative or wildly large value means at least one entity has the wrong sign convention or is mismapped. The most common culprit is `power_sign_convention` on a battery role.

## Adding a new device family

If your hardware family isn't covered above, please [open a device support issue](https://github.com/solarbalance/ha-solarbalance/issues/new?template=device_support.yml) — community-contributed examples land in `examples/config/devices/` and seed the future config-flow assistant.
