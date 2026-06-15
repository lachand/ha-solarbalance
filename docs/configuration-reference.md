# Configuration reference

Complete reference of every SolarBalance option. Two places hold configuration:

- **UI options** — *Settings → Devices & Services → SolarBalance → Configure*
  (no restart needed; the entry reloads automatically).
- **YAML** — the `solarbalance:` block in `configuration.yaml` for devices,
  meters, loads, tariff and forecast (**requires a Home Assistant restart** to
  apply; the YAML is read only at startup).

> Entity IDs for control/write entities are validated strictly: they must
> include a domain (e.g. `number.x`), otherwise setup fails with an error.

---

## UI options

| Option | Default | Description |
|---|---|---|
| `tick_interval_s` | 10 | Engine update interval (s). |
| `zero_injection_enabled` | true | Enable the zero-injection PI regulation. |
| `zero_injection_setpoint_w` | 0 | Target grid power (W). Negative allows a small export buffer. |
| `zero_injection_hysteresis_w` | 50 | Deadband (W) around the setpoint. |
| `zero_injection_kp` | 0.6 | Proportional gain (lower for slow/cloud batteries). |
| `max_ramp_w` | 800 | Max change of the fleet target per tick (W); 0 disables. |
| `grid_filter_samples` | 3 | Rolling-median window on the grid reading; 1 disables. |
| `zi_settle_ticks` | 2 | Anti-yoyo: freeze the ZI loop for N ticks after a big load drops. |
| `zi_settle_min_drop_w` | 300 | Min load-power drop (W) that arms the settle window. |
| `phases` | 1 | Electrical phases (1 or 3). |
| `subscribed_power_kva` | 6 | Subscribed power; drives the overload gauge/alert. |
| `backup_reserve_soc_pct` | 20 | Backup-strategy discharge floor (%). |
| `baseline_window_start_h` / `_end_h` | 2 / 5 | Quiet night window used to average the standby baseline (talon). |
| `load_control_enabled` | false | Allow writing to load switches/levels. **Required for any load action.** |
| `evening_shed_enabled` | false | End-of-day shedding of big loads to prioritise battery charge. |
| `evening_shed_min_power_w` | 500 | Min power of an interruptible load to be considered "big". |
| `predictive_control_enabled` | false | Let the planner steer batteries (cheap charge / peak discharge). Inert on a flat tariff. |
| `notifications_enabled` | true | Persistent notifications (degraded, overload, shedding). |
| `tempo_red_prep_enabled` | false | Pre-charge the fleet before a Tempo red day (off-peak). |
| `tempo_red_prep_soc_pct` | 100 | Target SoC for the red-day pre-charge. |
| `vacation_soc_max_pct` | 60 | Charge ceiling in vacation mode (longevity; never grid-charges). |
| `import_price` / `export_price` | 0.25 / 0.10 | Flat fallback prices (€/kWh) when no `tariff:` block is declared. |
| `pv_forecast_entity` | — | Solcast/Forecast.Solar sensor (today) for the hourly PV profile. |
| `pv_forecast_tomorrow_entity` | — | Optional second sensor (tomorrow) concatenated to the profile. |
| `forecast_safety_factor` | 0.85 | Conservative P50 discount for shed/fast-charge when P10 is unavailable. |
| `weather_warning_entity` | — | Binary/sensor for a Météo-France warning (storm auto-trigger). |
| `soc_equaliser_*` | — | Indirect steering of a non-controllable battery (see user guide). |

### Operating modes

- **normal** — full operation, zero-injection regulates.
- **vacation** — self-consume from solar but cap charging at `vacation_soc_max_pct`; never grid-charge.
- **storm** — charge to the storm target; raise the discharge floor (and the device reserve, if `reserve_soc_setpoint_entity` is set) so discharge-only batteries fill from PV.
- **paused** — engine stops, no control.
- **degraded** — critical entities stale; control suspended, setpoints reset.
- **manual_override** — `force_charge` / `force_discharge` services.

---

## YAML: `solarbalance:`

### `devices[].roles.battery`

| Field | Req | Description |
|---|---|---|
| `capacity_kwh` | ✓ | Nominal capacity. |
| `max_charge_power_w` / `max_discharge_power_w` | ✓ | Power limits (W). |
| `soc_entity` | ✓ | SoC sensor (%). |
| `power_entity` | ✓* | Signed power sensor; or both `charge_power_entity` + `discharge_power_entity`. |
| `controllable` | | `true` (default) = part of the balancing fleet; `false` = steered indirectly. |
| `active_control_enabled` | | Write setpoints to this battery (requires controllable). |
| `discharge_power_setpoint_entity` | | `number` receiving the discharge setpoint (W). |
| `charge_power_setpoint_entity` | | `number` receiving the charge setpoint (W). |
| `mode_setpoint_entity` | | `select` receiving charge/discharge/idle. |
| `reserve_soc_setpoint_entity` | | `number` receiving the backup-reserve/min-SoC (%); raised to the storm target during storm. |
| `soc_min_pct` / `soc_max_pct` | | SoC bounds (default 10 / 95). |
| `usable_capacity_kwh` | | Override usable capacity for deficit maths. |
| `ac_charge_limit_w` | | Max AC absorption (W) for the SoC equaliser. |
| `chemistry`, `power_sign_convention` | | `lifepo4`…, `charge_positive`/`discharge_positive`. |

### `devices[].roles.mppt` (micro-inverter / curtailment)

| Field | Req | Description |
|---|---|---|
| `peak_power_w` | ✓ | Inverter peak power (W) = curtailment upper bound. |
| `power_entity` | ✓ | Current production (W). |
| `active_control_enabled` | | Enable PV curtailment for this inverter. |
| `power_limit_setpoint_entity` | | `number` receiving the max output power (**W**). |

### `loads[]`

| Field | Description |
|---|---|
| `name`, `control_type` | `on_off` \| `stepped` \| `modulating`. |
| `priority` | 1 = highest. |
| `interruptible` | Eligible for evening shedding (default true). |
| `min_on_duration_s` / `min_off_duration_s` | Anti-short-cycle. |
| `time_window`, `max_daily_runtime_s`, `max_daily_energy_kwh` | Eligibility limits. |
| `switch_entity` | on/off switch (also cuts a stepped/modulating load whose 0 doesn't stop it). |
| `steps[]` (`level`, `power_w`), `level_entity` | stepped loads (level = e.g. EV amperage). |
| `min_power_w`, `max_power_w`, `power_set_entity` | modulating loads. |
| `actual_power_entity` | Measured load power (for deadline energy tracking). |
| `fast_charge` | EV fast-charge assist (efficient floor + battery assist). |
| `min_charge_w` | Efficient charge floor; below it: assist or pause. |
| `assist_floor_soc_pct` | Battery SoC floor for the assist (default = backup reserve). |
| `pause_when_inefficient` | Pause rather than slow-charge when neither surplus nor assist suffices (default true). |
| `deadline_constraint` (`kwh_required`, `before_time`) | Grid-backed guarantee by a departure time. |

### `tariff:`

```yaml
tariff:
  type: hc_hp           # flat | hc_hp | tempo
  export_price: 0.13
  # flat:
  import_price: 0.25
  # hc_hp:
  slots:
    - { start: "22:00", end: "06:00", price: 0.2068 }
    - { start: "06:00", end: "22:00", price: 0.27 }
  # tempo:
  color_entity: sensor.rte_tempo_today
  color_tomorrow_entity: sensor.rte_tempo_tomorrow   # for red-day pre-charge
  prices:
    blue:  { hc: 0.1296, hp: 0.1609 }
    white: { hc: 0.1467, hp: 0.1894 }
    red:   { hc: 0.1569, hp: 0.7562 }
```

### `forecast:` (manual hourly mapping — alternative to `pv_forecast_entity`)

```yaml
forecast:
  unit: w               # w | wh | kwh
  hours:
    - { hour: 0, entity: sensor.pv_this_hour }
    - { hour: 1, entity: sensor.pv_next_hour }
```

Solcast/Forecast.Solar users should instead point `pv_forecast_entity` at the
sensor exposing `detailedHourly` (Solcast) or `watts` (Forecast.Solar).

---

## Per-load controls (switches)

Each configured load gets control switches (also reachable from the panel's
*Consommateurs* card). All are runtime overrides — no YAML.

| Switch | Effect |
|---|---|
| `switch.solarbalance_<load>_force_charge` | **Charge now**: full power immediately, even without surplus. Overrides shedding, fast-charge pause and dispatch. Grid-backed — the ZI target is raised by the load's power so the **battery is not discharged** to feed it. Not restored across restarts. |
| `switch.solarbalance_<load>_shed_exempt` | **Keep running**: exempt from evening battery-priority shedding and the fast-charge inefficiency pause (interruptible loads only). Restored across restarts. |
| `switch.solarbalance_<load>_off_peak_only` | **Off-peak only**: forced off whenever the tariff window is not cheap (HP / expensive spot / Tempo red). Overridden by the departure deadline and force-charge. Restored across restarts. |

## Services

| Service | Fields | Description |
|---|---|---|
| `solarbalance.force_charge_load` | `load` (name, required), `kwh`, `hours` | Start a grid-backed "charge now" for a load. Auto-clears once `kwh` is delivered or `hours` elapse; without either, runs until cancelled (equivalent to the switch). |
| `solarbalance.cancel_force_charge_load` | `load` | Cancel a manual charge-now request. |
| `solarbalance.export_config` | — | Returns all UI sub-entries (response data) to back up / migrate. |
| `solarbalance.import_config` | `subentries` | Re-create devices/loads from a previously exported list (reloads the entry). |

(Plus `pause`, `resume`, `set_mode`, `force_charge`, `force_discharge`, `activate_storm_mode`.)

## Exposed sensors (selection)

| Sensor | Notes |
|---|---|
| `sensor.solarbalance_savings_this_month` / `..._this_year` | Cumulative € savings, `device_class: monetary`, `state_class: total` with `last_reset` → usable in the **Energy dashboard**. Reset on month/year rollover, persisted. |
| `sensor.solarbalance_<load>_energy_today` | Energy delivered to a load since local midnight (kWh, `total_increasing`). |
| `sensor.solarbalance_<load>_status` | Load state: `actif` / `inactif` / `délesté` / `attente heures creuses` / `charge forcée`. |
| `sensor.solarbalance_mode` (attribute `reason`) | Human-readable explanation of the current battery action, shown atop the panel. |

## Diagnostics

- `binary_sensor.solarbalance_config_health` + a **persistent notification** flag
  config mistakes: zero/missing battery capacity, invalid SoC range, a
  `fast_charge` load without `min_charge_w` or nominal power.
- *Settings → Devices & Services → SolarBalance → ⋮ → Download diagnostics*
  exports engine state, config, last snapshot and regulation values for support.
