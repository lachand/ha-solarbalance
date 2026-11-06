// Simulated `hass` for panel tests and the render bench. Placeholder ids only (ef_xxxxxx), never real serials.
export function makeHass({ dark = false, lang = "fr", degraded = false, lowScore = true } = {}) {
  const now = Date.now();
  const states = {};
  const entities = {};
  const devices = {
    dev1: { name: "Batterie salon" },
    dev2: { name: "Batterie garage" },
    dev3: { name: "Lave-linge" },
  };
  const ago = (s) => new Date(now - s * 1000).toISOString();
  const add = (eid, key, state, attributes = {}, device_id) => {
    states[eid] = { entity_id: eid, state: String(state), attributes, last_updated: ago(8), last_reported: ago(8) };
    entities[eid] = { platform: "solarbalance", translation_key: key, ...(device_id ? { device_id } : {}) };
  };
  const forecast = [];
  for (let h = 0; h < 14; h++) {
    const t = new Date(now + h * 3600e3);
    t.setMinutes(0, 0, 0);
    forecast.push({ start: t.toISOString(), w: Math.max(0, Math.round(3200 * Math.sin(((t.getHours() - 6) / 14) * Math.PI))) });
  }
  add("sensor.sb_mode", "mode", degraded ? "degraded" : "normal", { reason: "Autoconsommation : le surplus solaire charge les batteries." });
  add("sensor.sb_strat", "dominant_strategy", "zero_injection");
  add("sensor.sb_grid", "grid_power", -340, { subscribed_power_w: 6000 });
  add("sensor.sb_pv", "pv_power", 2350, { pv_forecast_hourly: forecast });
  add("sensor.sb_batt", "battery_power", 1260);
  add("sensor.sb_home", "baseline_consumption", 750);
  add("sensor.sb_soc", "battery_soc_avg", 62);
  add("sensor.sb_rem", "battery_remaining", 3.1);
  add("sensor.sb_use", "battery_usable", 2.6);
  add("sensor.sb_ttf", "time_to_full", 2.7);
  add("sensor.sb_tte", "time_to_empty", 5.1);
  add("sensor.sb_pvt", "pv_energy_today", 6.2);
  add("sensor.sb_imp", "grid_import_today", 1.4);
  add("sensor.sb_exp", "grid_export_today", 0.8);
  add("sensor.sb_con", "consumption_today", 7.1);
  add("sensor.sb_talon", "baseline_night", 180);
  add("sensor.sb_cost", "daily_cost", 0.42);
  add("sensor.sb_sav", "daily_savings", 1.35);
  add("sensor.sb_savm", "savings_month", 31.2);
  add("sensor.sb_savy", "savings_year", 1214.5);
  add("sensor.sb_pvr", "pv_remaining_today", 3.4);
  add("sensor.sb_price", "current_import_price", 0.2, { time_varying: true });
  add("binary_sensor.sb_storm", "storm_mode", "off");
  add("binary_sensor.sb_weather", "weather_warning", "on");
  add("binary_sensor.sb_degraded", "degraded", degraded ? "on" : "off");
  add("binary_sensor.sb_shed", "evening_shed", "off");
  add("binary_sensor.sb_ev", "ev_fast_charge", "off");
  add("sensor.sb_gridf", "grid_filtered", -310);
  add("sensor.sb_target", "regulation_target", 1200);
  add("sensor.sb_zi", "zi_correction", 90);
  add("sensor.sb_eq", "equaliser_offer", 0);
  add("sensor.sb_pvlim", "pv_output_limit", 3000);
  add("sensor.sb_bind", "regulation_binding", "aucun");
  add("sensor.sb_dbg", "regulation_debug", "ok", {
    target_w: 1200, current_fleet_w: 1260, natural_grid_w: 80, controllable_mppt_w: 2350, hidden_pv_w: 0,
    explanation_key: "charge_surplus", explanation: "Charge 1,2 kW", binding: "aucun", loop_base_w: 90,
    zi_correction_w: 90, equaliser_offer_w: 0, unallocated_w: 0, nc_charge_w: 0, grid_filtered_w: -310,
    pv_limit_w: 3000, settle: false, noncontrollable_charging: false,
    stale_batteries: degraded ? [{ device: "Batterie garage", reason: "power", age_s: 420 }] : [],
    per_battery_w: { "Batterie salon": 640, "Batterie garage": 620 },
    written_setpoints: { "Batterie salon": { charge_w: 640, discharge_w: 0 } },
  });
  add("sensor.sb_app", "appliance_advice", "ok", {
    appliances: [
      { name: "Lave-linge", running: false, samples: 6, duration_min: 118, energy_kwh: 0.92, solar_now_pct: 74, best_hour: 13, best_pct: 91,
        program: "Coton 40", unlabelled: 2, last_unlabelled: { duration_min: 95, energy_kwh: 0.7 },
        programs: [
          { program: "Coton 40", samples: 4, duration_min: 118, energy_kwh: 0.92, solar_now_pct: 74, best_hour: 13, best_pct: 91, cost_now_eur: 0.12, saving_by_waiting_eur: 0.04, curve_w: [20, 900, 2000, 400, 300, 250, 1800, 200, 60] },
          { program: "Eco 30", samples: 2, duration_min: 62, energy_kwh: 0.4, solar_now_pct: 74, cost_now_eur: 0.05, curve_w: [10, 500, 700, 200, 100] },
        ] },
      { name: "Lave-vaisselle", running: true, elapsed_min: 22, samples: 0 },
    ],
  });
  add("sensor.sb_link", "link_health", "ok", { links: [{ key: "ef_xxxxxx", verdict: "flaky", available_pct: 91, longest_gap_s: 640, dropouts: 4, score: 62 }] });
  add("sensor.sb_orch", "orchestration_gain", "0.84", { hours_compared: 9, actual_cost_eur: 0.42, naive_cost_eur: 1.26, stored_delta_kwh: 1.8 });
  add("sensor.sb_score", "install_score", lowScore ? 78 : 96, { deductions: lowScore ? ["Liaison instable : ef_xxxxxx", "Talon recalculé deux fois"] : [] });
  add("sensor.sb_anom", "anomaly_timeline", "ok", {
    events: [
      { at: ago(3600).slice(0, 19), severity: "warning", message: "Liaison ef_xxxxxx coupée 4 min", count: 3 },
      { at: ago(9000).slice(0, 19), severity: "info", message: "Talon recalculé", count: 1 },
      { at: ago(20000).slice(0, 19), severity: "error", message: "Écriture non appliquée sur ef_bkxxxx", count: 1 },
    ],
  });
  const sched = [];
  for (let h = 0; h < 24; h++) {
    const t = new Date(now + h * 3600e3);
    t.setMinutes(0, 0, 0);
    const p = h < 5 ? 1500 : h < 12 ? 0 : h > 18 && h < 22 ? -900 : 0;
    sched.push({ start: t.toISOString(), battery_power_w: p, soc_end_pct: 30 + h * 2, expected_cost_eur: 0.03 * h });
  }
  add("sensor.sb_plan", "planner_recommended_power", "0", { schedule: sched });
  add("sensor.sb_plancost", "planner_expected_cost", "1.1");
  // Batteries
  for (const [d, soc, p] of [["dev1", 71, 640], ["dev2", 53, 620]]) {
    add(`sensor.${d}_soc`, "batt_soc", soc, { role: d === "dev2" ? "cloud" : "local", soc_min_pct: 10, stale: d === "dev2" && degraded, stale_reason: "power", stale_age_s: 420 }, d);
    add(`sensor.${d}_pow`, "batt_power", p, {}, d);
    add(`sensor.${d}_temp`, "batt_temperature", 24.5, {}, d);
    add(`sensor.${d}_sc`, "battery_setpoint_charge", p, {}, d);
    add(`sensor.${d}_sd`, "battery_setpoint_discharge", 0, {}, d);
    add(`sensor.${d}_mp`, "mppt_power", 1170, {}, d);
    add(`sensor.${d}_ml`, "mppt_limit", 1170, {}, d);
  }
  add("switch.dev3_force", "force_charge_now", "off", {}, "dev3");
  add("switch.dev3_shed", "shed_exempt", "on", {}, "dev3");
  add("switch.dev3_hc", "off_peak_only", "off", {}, "dev3");
  add("switch.dev3_sol", "solar_only", "on", {}, "dev3");

  const series = (eid, startMs, endMs) => {
    const out = [];
    for (let t = startMs; t <= endMs; t += 120e3) {
      const h = new Date(t).getHours() + new Date(t).getMinutes() / 60;
      const sun = Math.max(0, Math.sin(((h - 6) / 14) * Math.PI));
      let v = 0;
      if (eid === "sensor.sb_pv") v = 3200 * sun + (Math.sin(t / 4e5) * 120);
      else if (eid === "sensor.sb_grid") v = 250 - 1800 * sun + Math.sin(t / 3e5) * 200;
      else if (eid === "sensor.sb_batt") v = 1200 * sun - 150;
      else if (eid.endsWith("_soc")) v = 40 + 30 * sun + (eid.includes("dev2") ? -8 : 0);
      out.push({ s: String(Math.round(v)), lu: t / 1000 });
    }
    return out;
  };
  return {
    language: lang,
    locale: { language: lang },
    themes: { darkMode: dark },
    states,
    entities,
    devices,
    callService: (...a) => console.log("callService", JSON.stringify(a)),
    callWS: async (msg) => {
      const s = Date.parse(msg.start_time);
      const e = Date.parse(msg.end_time);
      const res = {};
      for (const id of msg.entity_ids) res[id] = series(id, s, e);
      return res;
    },
  };
}
