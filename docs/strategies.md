# Strategies

SolarBalance arbitrates energy decisions using an ordered list of **strategies**. Each strategy produces a `Decision` — a set of battery targets, a grid constraint, and a confidence score. The arbiter then fuses them according to priority order.

> **Detailed algorithm specification**: [SPECIFICATIONS.md](SPECIFICATIONS.md) §5–§6.

---

## Ordering strategies

Strategy order is set in the Config Flow (drag to reorder). The **first strategy is dominant**: it sets the central battery SoC window and `preferred_power_w`. Lower-priority strategies can only _narrow_ that window, never widen it.

Example (YAML representation of what the Config Flow stores):

```yaml
priorities:
  - self_consumption # dominant
  - longevity # narrows SoC window per chemistry
  - backup # raises soc_min floor during storms
  - cost_min # shifts charge/discharge timing on tariff signal
  - peak_shaving # caps grid import at subscribed power
```

---

## `self_consumption`

**Goal**: maximize the fraction of PV production consumed locally; avoid grid import when the battery can cover it.

**Logic**:

- Grid **negative** (export) → battery should charge (absorb surplus). `preferred_power_w = max_charge_power_w`.
- Grid **positive** (import) → battery should discharge (cover load). `preferred_power_w = -max_discharge_power_w`.
- Grid near zero → no directional preference.
- Forbids export by default (`max_export_w = 0`).

**MPPT and micro-inverter production** is always included: every device with an `mppt` role contributes to `sensor.solarbalance_pv_power`, regardless of whether it is a string MPPT tracker, a micro-inverter, or a hybrid inverter's integrated MPPT. The strategy reacts to the aggregate reading.

**When batteries are full** and PV keeps producing, export becomes unavoidable unless production itself is curtailed. The ZI controller handles this in three steps, in preference order ([SPECIFICATIONS §6.3](SPECIFICATIONS.md)):

1. **MPPT/micro-inverter with `power_set_entity`** — if the role declares a controllable power-limit entity (e.g. a Hoymiles or Enphase micro-inverter exposed via an HA integration), the ZI controller calculates a curtailment setpoint. In **v1** this is published as a read-only sensor (`sensor.solarbalance_setpoint_mppt_<device>`); actual writing is **v2 (F14)**. You can already wire the sensor to your own automation.
2. **Inverter production regulation** — via a dedicated entity on the `inverter` role (v2+).
3. **No curtailment available** — the ZI controller enters `degraded_zi` mode and emits a persistent notification.

**When to use**: every setup. Place it first unless a cost or revenue strategy should be dominant.

**Parameters**: none (pure reactive on grid signal).

---

## `cost_min`

**Goal**: charge when electricity is cheap; discharge when it is expensive — improving the financial return of storage.

**Logic** (threshold-based heuristic):

- Reads `current_import_price` from the snapshot (resolved from `TariffConfig`).
- **Cheap window** (`price ≤ cheap_threshold`): sets `preferred_power_w = max_charge_power_w`; allows grid import (`max_import_w = None`).
- **Expensive window** (`price ≥ expensive_threshold`): sets `preferred_power_w = -max_discharge_power_w`; forbids grid import (`max_import_w = 0`).
- **Neutral window**: returns confidence = 0.5, no directional opinion.
- **No price available**: returns confidence = 0, no opinion (arbiter ignores it).

**Configuration** (set in Config Flow or YAML override):

| Parameter                 | Default    | Description                                        |
| ------------------------- | ---------- | -------------------------------------------------- |
| `cheap_threshold`         | 0.15 €/kWh | Price below which charging from grid is profitable |
| `expensive_threshold`     | 0.25 €/kWh | Price above which discharging is preferred         |
| `charge_soc_target_pct`   | 95         | Do not charge beyond this in cheap window          |
| `discharge_soc_floor_pct` | 20         | Do not discharge below this in expensive window    |

**When to use**: HC/HP tariffs, Tempo, time-of-use contracts with at least two price levels. Pair with `self_consumption` as dominant for mixed behaviour.

**Tariff setup**: configure `tariff_config` in YAML (see [SPECIFICATIONS.md §7.3](SPECIFICATIONS.md)) or use the `make_hchp_tariff()` helper.

---

## `backup`

**Goal**: maintain a minimum SoC reserve for blackout/storm resilience, independent of PV or tariff conditions.

**Logic**:

- Raises `soc_min_pct` for all batteries to `reserve_soc_pct` (default 30%).
- Does not set a `preferred_power_w` — only constrains the floor.
- Typically placed after `self_consumption` so the dominant strategy still drives direction.

**Configuration**:

| Parameter         | Default | Description                    |
| ----------------- | ------- | ------------------------------ |
| `reserve_soc_pct` | 30      | Minimum SoC to always maintain |

**When to use**: homes with power reliability concerns, integration with storm mode (where the target rises to 90–100%).

---

## `longevity`

**Goal**: extend battery lifespan by keeping SoC within a chemistry-appropriate comfort window, avoiding deep cycles and persistent full-charge states.

**Default comfort windows per chemistry**:

| Chemistry  | `soc_min_pct` | `soc_max_pct` |
| ---------- | ------------- | ------------- |
| `lifepo4`  | 20 %          | 90 %          |
| `nmc`      | 20 %          | 85 %          |
| `leadacid` | 30 %          | 80 %          |
| `other`    | 20 %          | 85 %          |

**Logic**:

- Narrows the battery target window to the chemistry window.
- Never widens beyond the user's absolute `soc_min_pct`/`soc_max_pct` bounds.
- Override parameters `override_soc_min_pct` and `override_soc_max_pct` let you customize per-strategy.

**When to use**: always recommended as a background constraint. Place after `self_consumption` and `backup` so it only narrows, never overrides the reserve floor.

---

## `peak_shaving`

**Goal**: prevent grid import from exceeding the subscribed power (kVA limit), protecting against over-contract penalties.

**Logic**:

- Sets `max_import_w = subscribed_power_kva × 1000 × power_factor` as a `GridConstraint`.
- When the limit is active, the arbiter will clip grid import and the balancing controller must compensate from storage.

**Configuration**:

| Parameter      | Default                             | Description              |
| -------------- | ----------------------------------- | ------------------------ |
| `max_import_w` | derived from `subscribed_power_kva` | Hard import cap in watts |

**When to use**: contracts where exceeding subscribed power triggers penalties (common in France for 3-phase contracts). Set `subscribed_power_kva` in the Config Flow.

---

## `revenue_max`

**Status**: stub — planned for v1.5.

**Goal**: optimize for grid export revenue (sell PV surplus at peak export price).

Not yet implemented. When active it returns an empty `Decision` (no opinion), so it has no effect in v1.

---

## Strategy interaction — worked example

Setup: `[self_consumption, longevity, backup, cost_min]`, LiFePO4 battery, HC/HP tariff.

**14:00, HP, 800 W PV surplus, SoC = 55%**:

- `self_consumption`: wants to charge, `preferred_power_w = 1800`, window = [10, 95].
- `longevity`: narrows window to [20, 90].
- `backup`: raises soc_min to 30 → window = [30, 90].
- `cost_min`: HP is expensive → wants to discharge. Confidence = 1.0. Narrows to `preferred_power_w = -1800`.

Arbiter: dominant is `self_consumption`. `preferred_power_w` stays at 1800 W (charge, because dominant wins directional intent). Window = [30, 90]. Grid constraint: `max_import_w = 0` (from cost_min, most restrictive). Since battery can absorb the 800 W PV surplus without grid import, the constraint is satisfied.

**22:00, HC, SoC = 30%**:

- `self_consumption`: grid near 0, no preference.
- `cost_min`: HC → cheap window → `preferred_power_w = 1800`, allows import.

Balancing controller allocates 1800 W charge. Grid import is authorized. Battery charges from grid at off-peak rate.

---

## Adding custom strategies

Custom strategies are not yet pluggable via a public API (v1 registers all built-in kinds in `coordinator.py`). A plugin registration mechanism is on the v2 roadmap. In the meantime, fork the `core/strategies/` directory and add your class to `_STRATEGY_CLASSES` in `coordinator.py`.
