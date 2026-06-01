# API Reference

This page documents all **entities** exposed by SolarBalance and all **services** it registers.

> All entity IDs use the pattern `<platform>.solarbalance_<suffix>`. If you declared a device named `my_station`, per-device entities use that name verbatim (lower-cased, spaces replaced by underscores).

---

## Entities

### Sensors

| Entity ID                                         | Unit  | Description                                                                                          |
| ------------------------------------------------- | ----- | ---------------------------------------------------------------------------------------------------- |
| `sensor.solarbalance_mode`                        | —     | Current HEMS operating mode (`normal`, `storm`, `vacation`, `paused`, `degraded`, `manual_override`) |
| `sensor.solarbalance_dominant_strategy`           | —     | Strategy that dominated the last arbitration tick                                                    |
| `sensor.solarbalance_grid_power`                  | W     | Power at the PDL — positive = grid import, negative = export                                         |
| `sensor.solarbalance_pv_power`                    | W     | Total PV production (sum of all available MPPT roles)                                                |
| `sensor.solarbalance_battery_power`               | W     | Net battery power (positive = aggregate charging, negative = discharging)                            |
| `sensor.solarbalance_baseline_consumption`        | W     | Deduced background consumption (see [SPECIFICATIONS §3.4](SPECIFICATIONS.md))                        |
| `sensor.solarbalance_setpoint_charge_<device>`    | W     | Calculated charge setpoint for `<device>` — read-only in v1                                          |
| `sensor.solarbalance_setpoint_discharge_<device>` | W     | Calculated discharge setpoint for `<device>` — read-only in v1                                       |

All power sensors have `device_class: power` and `state_class: measurement` for Energy Dashboard compatibility.

### Binary sensors

| Entity ID                                    | Description                                                             |
| -------------------------------------------- | ----------------------------------------------------------------------- |
| `binary_sensor.solarbalance_storm_mode`      | `on` when the HEMS is in storm-preparation mode                         |
| `binary_sensor.solarbalance_weather_warning` | `on` when the mapped weather-warning entity is active                   |
| `binary_sensor.solarbalance_degraded`        | `on` when the HEMS is in degraded mode (stale critical entity detected) |

### Select

| Entity ID                  | Options                                 | Description                                                                          |
| -------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------ |
| `select.solarbalance_mode` | `normal`, `storm`, `vacation`, `paused` | Set the operating mode. Writing `degraded` is not allowed — it is set automatically. |

### Numbers

| Entity ID                           | Range      | Unit | Description                                                                                      |
| ----------------------------------- | ---------- | ---- | ------------------------------------------------------------------------------------------------ |
| `number.solarbalance_zi_setpoint`   | −500 … 500 | W    | Zero-injection target (0 = strict zero injection; negative = allow a small safety export buffer) |
| `number.solarbalance_zi_hysteresis` | 0 … 500    | W    | Zero-injection deadband — corrections below this threshold are ignored                           |

### Switches

| Entity ID                            | Description                                       |
| ------------------------------------ | ------------------------------------------------- |
| `switch.solarbalance_zero_injection` | Enable / disable the zero-injection PI regulation |

---

## Services

All services are registered at the domain level (`solarbalance.*`) and apply to whichever coordinator is active. They survive coordinator reloads.

---

### `solarbalance.pause`

Suspend the HEMS. The coordinator stops publishing setpoints until resumed.

```yaml
service: solarbalance.pause
```

No parameters.

---

### `solarbalance.resume`

Resume normal operation after a pause.

```yaml
service: solarbalance.resume
```

No parameters. No-op if the HEMS is not paused.

---

### `solarbalance.set_mode`

Directly set the global operating mode.

```yaml
service: solarbalance.set_mode
data:
  mode: vacation
```

| Field  | Type   | Required | Values                                  |
| ------ | ------ | -------- | --------------------------------------- |
| `mode` | string | yes      | `normal`, `storm`, `vacation`, `paused` |

---

### `solarbalance.force_charge`

Force all batteries to charge towards a target SoC. Bypasses the arbiter and enters `manual_override` mode. Automatically clears when the target is reached or the deadline expires.

```yaml
service: solarbalance.force_charge
data:
  target_soc_pct: 90
  power_w: 1800 # optional — defaults to max_charge_power_w per device
  deadline: "2026-05-05T22:00:00" # optional ISO-8601 datetime
```

| Field            | Type              | Required | Description                                                                            |
| ---------------- | ----------------- | -------- | -------------------------------------------------------------------------------------- |
| `target_soc_pct` | number 0–100      | yes      | Target SoC in percent                                                                  |
| `power_w`        | number > 0        | no       | Per-device charge power limit (W). Defaults to `max_charge_power_w`.                   |
| `deadline`       | ISO-8601 datetime | no       | If provided, the override auto-clears at this time even if the target was not reached. |

---

### `solarbalance.force_discharge`

Force all batteries to discharge towards a floor SoC. Bypasses the arbiter.

```yaml
service: solarbalance.force_discharge
data:
  target_soc_pct: 20
  power_w: 1500
```

| Field            | Type         | Required | Description                                                                |
| ---------------- | ------------ | -------- | -------------------------------------------------------------------------- |
| `target_soc_pct` | number 0–100 | yes      | Discharge-to SoC floor in percent                                          |
| `power_w`        | number > 0   | no       | Per-device discharge power limit (W). Defaults to `max_discharge_power_w`. |

---

### `solarbalance.activate_storm_mode`

Manually trigger storm-preparation mode. Charges batteries to `DEFAULT_STORM_TARGET_SOC_PCT` (95 %). Optionally auto-exits after `duration_h` hours, then returns to normal mode.

```yaml
service: solarbalance.activate_storm_mode
data:
  duration_h: 24 # optional — auto-exit after this many hours
```

| Field        | Type        | Required | Description                                          |
| ------------ | ----------- | -------- | ---------------------------------------------------- |
| `duration_h` | number 1–72 | no       | Auto-exit after this many hours (stays if omitted)   |

---

## Using services in automations

Example — automatically force-charge before a predicted night storm:

```yaml
automation:
  alias: Pre-charge for evening storm
  trigger:
    - platform: state
      entity_id: binary_sensor.meteofrance_44_thunderstorm_warning
      to: "on"
  action:
    - service: solarbalance.force_charge
      data:
        target_soc_pct: 95
        deadline: "{{ (now() + timedelta(hours=12)).isoformat() }}"
```

Example — pause during a long maintenance window:

```yaml
automation:
  alias: Pause HEMS during firmware update
  trigger:
    - platform: time
      at: "02:00:00"
  action:
    - service: solarbalance.pause
  mode: single
```

---

## Sign conventions

| Quantity               | Positive                              | Negative                            |
| ---------------------- | ------------------------------------- | ----------------------------------- |
| `grid_power`           | Import from grid (soutirage)          | Export to grid (injection)          |
| `battery_power`        | Charging                              | Discharging                         |
| `pv_power`             | Production (always ≥ 0)               | —                                   |
| `baseline_consumption` | Background load (always expected ≥ 0) | Indicates mapping error if negative |
| `zi_setpoint`          | Allow slight import                   | Allow slight export buffer          |

---

## Glossary

| Term          | Definition                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------- |
| **PDL**       | Point De Livraison — grid connection point, measured by the meter                           |
| **ZI**        | Zero Injection — the regulatory objective of not exporting surplus to the grid              |
| **Tick**      | One coordinator update cycle (default 10 s)                                                 |
| **Snapshot**  | Full system state captured at the start of a tick                                           |
| **Decision**  | Output of one strategy for one tick — battery targets + grid constraint                     |
| **Arbiter**   | Component that fuses N strategy decisions into one fused decision                           |
| **Balancing** | Per-device allocation of the total target power (hybrid capacity-weight + SoC equalisation) |
