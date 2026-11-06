/**
 * Read-only view over the Home Assistant `hass` object for the SolarBalance panel.
 *
 * Entities are resolved by `translation_key` so localised entity_ids (French installs)
 * keep working; the English default ids are only a fallback.
 */

import { STR_EN } from "./i18n.js";
import { fmtNum, withUnit } from "./format.js";

const DEVICE_METRICS = {
  batt_soc: "soc",
  batt_power: "power",
  batt_temperature: "temperature",
  battery_setpoint_charge: "setpoint_charge",
  battery_setpoint_discharge: "setpoint_discharge",
  mppt_power: "mppt_power",
  mppt_limit: "mppt_limit",
  mppt_temperature: "mppt_temperature",
};

const LOAD_SWITCHES = {
  force_charge_now: "force",
  shed_exempt: "shed",
  off_peak_only: "offpeak",
  solar_only: "solar",
};

export class Model {
  constructor() {
    this.hass = null;
    this.byKey = {};
    this.E = {};
  }

  setHass(hass) {
    this.hass = hass;
    this._buildByKey();
    this._resolveEntities();
  }

  get lang() {
    const h = this.hass;
    return (h && ((h.locale && h.locale.language) || h.language)) || "fr";
  }

  get isEnglish() {
    return this.lang.startsWith("en");
  }

  /** Translate an in-source French label to English when HA runs in English. */
  t(s) {
    return this.isEnglish ? STR_EN[s] || s : s;
  }

  stateObj(id) {
    return (id && this.hass && this.hass.states[id]) || null;
  }

  /** True when the entity exists at all (even if currently unavailable). */
  exists(id) {
    return this.stateObj(id) !== null;
  }

  state(id) {
    const s = this.stateObj(id);
    if (!s || s.state === "unavailable" || s.state === "unknown" || s.state === "") return null;
    return s.state;
  }

  num(id) {
    const s = this.state(id);
    if (s === null) return null;
    const n = Number(s);
    return Number.isNaN(n) ? null : n;
  }

  attr(id, name) {
    const s = this.stateObj(id);
    return s && s.attributes ? s.attributes[name] : undefined;
  }

  /** Numeric coercion for a raw attribute value (already a number or a string). */
  num2(v) {
    if (v == null) return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  }

  /** Entity state as formatted text with its unit, or "—" when unavailable. */
  fmt(id, digits = 0, unit = "") {
    const s = this.state(id);
    if (s === null) return "—";
    const n = Number(s);
    if (Number.isNaN(n)) return s;
    return withUnit(fmtNum(n, digits, this.lang), unit);
  }

  _buildByKey() {
    const map = {};
    const ents = this.hass && this.hass.entities;
    if (ents) {
      for (const eid in ents) {
        const e = ents[eid];
        if (e && e.platform === "solarbalance" && e.translation_key) {
          map[e.translation_key] = eid;
        }
      }
    }
    this.byKey = map;
  }

  _id(translationKey, fallback) {
    return (this.byKey && this.byKey[translationKey]) || fallback;
  }

  _resolveEntities() {
    const id = (k, fb) => this._id(k, fb);
    this.E = {
      mode: id("mode", "sensor.solarbalance_mode"),
      strat: id("dominant_strategy", "sensor.solarbalance_dominant_strategy"),
      grid: id("grid_power", "sensor.solarbalance_grid_power"),
      pv: id("pv_power", "sensor.solarbalance_pv_power"),
      battery: id("battery_power", "sensor.solarbalance_battery_power"),
      home: id("baseline_consumption", "sensor.solarbalance_baseline_consumption"),
      soc: id("battery_soc_avg", "sensor.solarbalance_battery_soc_avg"),
      batteryRemaining: id("battery_remaining", "sensor.solarbalance_battery_remaining"),
      batteryUsable: id("battery_usable", "sensor.solarbalance_battery_usable"),
      timeToFull: id("time_to_full", "sensor.solarbalance_time_to_full"),
      timeToEmpty: id("time_to_empty", "sensor.solarbalance_time_to_empty"),
      pvToday: id("pv_energy_today", "sensor.solarbalance_pv_energy_today"),
      gridImportToday: id("grid_import_today", "sensor.solarbalance_grid_import_today"),
      gridExportToday: id("grid_export_today", "sensor.solarbalance_grid_export_today"),
      consoToday: id("consumption_today", "sensor.solarbalance_consumption_today"),
      talon: id("baseline_night", "sensor.solarbalance_standby_baseline_night"),
      dailyCost: id("daily_cost", "sensor.solarbalance_grid_cost_today"),
      dailySavings: id("daily_savings", "sensor.solarbalance_savings_today"),
      savingsMonth: id("savings_month", "sensor.solarbalance_savings_this_month"),
      savingsYear: id("savings_year", "sensor.solarbalance_savings_this_year"),
      pvRemaining: id("pv_remaining_today", "sensor.solarbalance_remaining_pv_production_today"),
      importPrice: id("current_import_price", "sensor.solarbalance_current_import_price"),
      storm: id("storm_mode", "binary_sensor.solarbalance_storm_mode"),
      weather: id("weather_warning", "binary_sensor.solarbalance_weather_warning"),
      degraded: id("degraded", "binary_sensor.solarbalance_degraded"),
      eveningShed: id("evening_shed", "binary_sensor.solarbalance_battery_priority_shedding"),
      evFastCharge: id("ev_fast_charge", "binary_sensor.solarbalance_ev_fast_charge_assisted"),
      gridFiltered: id("grid_filtered", "sensor.solarbalance_grid_power_filtered"),
      target: id("regulation_target", "sensor.solarbalance_regulation_target"),
      ziCorr: id("zi_correction", "sensor.solarbalance_zero_injection_correction"),
      eqOffer: id("equaliser_offer", "sensor.solarbalance_soc_equaliser_offer"),
      pvLimit: id("pv_output_limit", "sensor.solarbalance_pv_output_limit"),
      binding: id("regulation_binding", "sensor.solarbalance_active_clamp"),
      regDebug: id("regulation_debug", "sensor.solarbalance_regulation_debug"),
      appliances: id("appliance_advice", "sensor.solarbalance_appliance_advice"),
      linkHealth: id("link_health", "sensor.solarbalance_link_health_weakest"),
      orchGain: id("orchestration_gain", "sensor.solarbalance_orchestration_gain_today"),
      installScore: id("install_score", "sensor.solarbalance_installation_health_score"),
      anomalyTimeline: id("anomaly_timeline", "sensor.solarbalance_anomaly_timeline"),
      planPower: id(
        "planner_recommended_power",
        "sensor.solarbalance_planner_recommended_power_advisory"
      ),
      planCost: id("planner_expected_cost", "sensor.solarbalance_planner_expected_cost_advisory"),
    };
  }

  deviceName(deviceId) {
    const d = this.hass && this.hass.devices && this.hass.devices[deviceId];
    return (d && (d.name_by_user || d.name)) || deviceId;
  }

  /** Per-battery entities grouped by device, keyed by the metric names above. */
  devices() {
    const out = {};
    const h = this.hass;
    if (!h || !h.entities) return out;
    for (const eid in h.entities) {
      const e = h.entities[eid];
      if (!e || e.platform !== "solarbalance" || !e.device_id || !e.translation_key) continue;
      const metric = DEVICE_METRICS[e.translation_key];
      if (!metric) continue;
      const dev = (out[e.device_id] ||= { name: this.deviceName(e.device_id) });
      dev[metric] = eid;
    }
    return out;
  }

  /** Per-load control switches, grouped by load (force-charge, shed-exempt, ...). */
  loadSwitches() {
    const out = {};
    const h = this.hass;
    if (!h || !h.entities) return out;
    for (const eid in h.entities) {
      const e = h.entities[eid];
      if (!e || e.platform !== "solarbalance") continue;
      const slot = LOAD_SWITCHES[e.translation_key];
      if (!slot || !e.device_id) continue;
      const s = this.stateObj(eid);
      const load = (out[e.device_id] ||= { name: this.deviceName(e.device_id) });
      load[slot] = { eid, on: !!(s && s.state === "on") };
    }
    return out;
  }
}
