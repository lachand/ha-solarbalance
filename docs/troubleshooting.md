# Troubleshooting

This page covers the most common issues encountered when setting up and operating SolarBalance.

---

## Integration does not load

**Symptom**: The component never finishes loading; no entities are created.

**Check the logs first** — in Home Assistant, go to _Settings → System → Logs_, search for `solarbalance`.

**Common causes**:

| Log message fragment                           | Cause                                          | Fix                                                                                                                      |
| ---------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `voluptuous.error.Invalid` or `Invalid config` | YAML schema error in `configuration.yaml`      | Validate your YAML against the schema in [SPECIFICATIONS §3](SPECIFICATIONS.md). Check indentation and mandatory fields. |
| `No PDL meter declared`                        | No device with a `meter` role of `kind: pdl`   | Add a PDL meter entry under `devices:`. See [device-mapping.md](device-mapping.md).                                      |
| `No battery role declared`                     | No device has a `battery` role                 | At least one battery role is required.                                                                                   |
| `EntityNotFound`                               | An entity ID in your YAML does not exist in HA | Copy-paste entity IDs from _Developer Tools → States_. Watch for typos and letter case.                                  |

---

## `sensor.solarbalance_baseline_consumption` shows a negative or absurd value

**Symptom**: The baseline sensor shows −500 W, 4 000 W, or fluctuates wildly.

**Cause**: The power balance equation

```
P_baseline = P_pdl + P_pv_total + P_battery_discharge − P_battery_charge − Σ P_loads
```

is driven by your entity mappings. A wrong sign convention on any measured entity throws it off.

**Diagnosis steps**:

1. Open _Developer Tools → States_, inspect `sensor.solarbalance_grid_power`. Confirm it is positive when your home draws from the grid and negative when exporting.
2. Inspect each battery `power_entity`. With `power_sign_convention: charge_positive` (default) the value must be positive when the battery is charging. If your device reports the opposite, declare `power_sign_convention: discharge_positive`.
3. If you use separate `charge_power_entity` + `discharge_power_entity`, both must be positive (the sign is handled internally by the role).
4. Check that PV sensors are not negative.

---

## `binary_sensor.solarbalance_degraded` is ON and won't clear

**Symptom**: The degraded binary sensor stays `on`; the HEMS operates in degraded mode (no zero-injection, no load dispatch).

**Cause**: The watchdog detected a **critical entity** (PDL meter) or **monitored entity** (battery SoC, battery power, MPPT power) that has not been updated for more than 5 minutes.

**Diagnosis**:

1. Check logs for `Watchdog: stale critical entity` or `stale monitored entity` messages — the entity ID is logged.
2. Go to _Developer Tools → States_, find the stale entity. Check its `last_updated` timestamp.
3. Verify the device providing that entity is online (ping it, or check the integration's status in _Settings → Integrations_).

**The degraded sensor clears automatically** once all critical entities are fresh again. You do not need to restart HA.

**If the entity keeps going stale intermittently**, the watchdog timeout is fixed at 300 s (5 minutes) in v1 and is not configurable via YAML. If you need a longer grace period, it can only be changed by modifying the constant in `adapters/watchdog.py` until a config option is added in a future version.

---

## Zero injection never settles — battery keeps cycling

**Symptom**: The battery oscillates between charging and discharging with a period of a few seconds; `sensor.solarbalance_grid_power` fluctuates around zero but never stabilises.

**Cause**: PI tuning mismatch. The default (`Kp = 0.6`, `Ki = 0.05`) may be too aggressive for slow-responding equipment or noisy PDL sensors.

**If the battery is full and PV keeps exporting**: this is the _saturation_ case, not a tuning problem. Hysteresis and Kp/Ki adjustments will not help. You need a curtailment path:

- Declare `power_set_entity` on your MPPT or micro-inverter's device role. In v1, SolarBalance will publish a `sensor.solarbalance_setpoint_mppt_<device>` you can use in an automation. Direct writing is v2 (F14).
- If curtailment is impossible (e.g. no controllable entity), the ZI controller enters `degraded_zi` mode and logs a persistent notification.

**Fixes for genuine oscillation**:

1. **Increase hysteresis** via `number.solarbalance_zi_hysteresis`. Start at 100–150 W. This introduces a deadband around the setpoint — no correction is issued when the PDL reading is within ±hysteresis of the target.
2. **Lower Kp** in your YAML (`zi_kp: 0.3`) to reduce the proportional reaction speed.
3. **Lower Ki** (`zi_ki: 0.02`) if the integrator winds up.
4. If the PDL meter samples at a low rate (e.g. Shelly 3EM every 5 s), reduce `tick_s` from the default 10 s to match the meter's reporting rate.

---

## Force charge / force discharge does not clear

**Symptom**: The HEMS stays in `manual_override` after the battery has reached the target SoC.

**Cause**: If the SoC entity is slow to update (low reporting frequency), the override may linger for one extra tick before the target-reached check fires.

**Clear it manually**:

```yaml
service: solarbalance.resume
```

Or use the **Resume** button in the dashboard if you deployed the [example dashboard](../examples/lovelace/dashboard.yaml).

**If the override never cleared** even after the battery definitely reached the target: check whether the battery's `soc_entity` was already at the target value _at the moment the service was called_. The check fires each tick; if the very first tick already satisfies `current_soc ≥ target_soc`, the override is cleared immediately. If it keeps running, confirm the `soc_entity` is reporting the correct value.

---

## Storm mode is not triggering from the weather warning entity

**Symptom**: Your weather warning entity is `on` but `binary_sensor.solarbalance_storm_mode` stays `off`.

**Checks**:

1. Confirm the mapped entity is a `binary_sensor` (not `sensor`) with state `"on"`.
2. Verify `weather_warning_entity` in your YAML matches the exact entity ID (copy-paste from _Developer Tools → States_).
3. Check that the phenomenon and level in `storm_triggers` match what the Météo-France integration actually exposes. For instance, `phenomenon: wind, min_level: orange` only fires if the entity state is `"orange"` or `"red"` — not `"yellow"`.

---

## Strategies appear inactive — no charging or discharging decisions

**Symptom**: `sensor.solarbalance_dominant_strategy` shows `none` or an unexpected value; the battery stays idle even during PV surplus.

**Checks**:

1. Confirm the `priorities` list in the integration options (Config Flow → _Options_) contains at least `self_consumption`.
2. Check that the PDL meter entity is reading a non-zero value during daytime — if it reads 0 at all times, the strategies receive no signal.
3. Ensure the battery is not at `soc_max_pct` (already full). In that case, `self_consumption` will not output a charge decision.

---

## Cost-min strategy charges at the wrong time

**Symptom**: The battery charges during HP (expensive hours) instead of HC (cheap hours).

**Cause**: The `TariffConfig` schedule is likely misconfigured. The matcher uses **first-match wins** on the declared `schedules` list — if a broad HP schedule is listed before the HC entry, HC windows are shadowed.

**Fix**: Reorder your tariff schedules so the most specific windows (HC) appear first. Refer to [SPECIFICATIONS §7.3](SPECIFICATIONS.md) for the overlap resolution rule.

---

## Dashboard entities show "Unavailable"

**Symptom**: The example Lovelace dashboard shows "Unavailable" for some or all cards.

**Cause**: Default entity IDs assume the device names used in your YAML are mapped to the standard suffixes.

**Fix**: Per-device sensors (setpoint charge/discharge) use the device `name` as a slug. If you named your battery `EcoFlow Delta`, the entity will be `sensor.solarbalance_setpoint_charge_ecoflow_delta`. Update the dashboard YAML accordingly, or use the entity picker in the card editor to find the real IDs.

---

## Getting further help

1. Enable debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.solarbalance: debug
```

2. Restart HA and reproduce the issue.
3. Copy the relevant log lines and [open an issue on GitHub](https://github.com/your-org/ha-solarbalance/issues) with:
   - The log excerpt
   - Your anonymised YAML config (remove personal entity IDs or replace them with descriptive placeholders)
   - HA version, SolarBalance version, affected device model
