/**
 * SolarBalance — full-page custom panel (sidebar).
 *
 * Plain web component (no build step). Home Assistant sets `hass` on every state
 * change; we debounce-render. Reads the `sensor.solarbalance_*` entities and the
 * per-device battery sensors. Themed via HA CSS variables.
 */

class SolarBalancePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._pending = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._scheduleRender();
  }

  connectedCallback() {
    this._render();
  }

  _scheduleRender() {
    if (this._pending) return;
    this._pending = true;
    setTimeout(() => {
      this._pending = false;
      this._render();
    }, 300);
  }

  _state(id) {
    const s = id && this._hass && this._hass.states[id];
    if (!s || s.state === "unavailable" || s.state === "unknown" || s.state === "") return null;
    return s.state;
  }

  /**
   * Resolve a SolarBalance entity by its stable translation_key via the entity
   * registry. Entity_ids are localised (French installs get e.g.
   * `sensor.solarbalance_puissance_reseau`), but translation_key is not. Falls
   * back to the given English entity_id if the registry is unavailable.
   */
  _buildByKey() {
    const map = {};
    const ents = this._hass && this._hass.entities;
    if (ents) {
      for (const eid in ents) {
        const e = ents[eid];
        if (e && e.platform === "solarbalance" && e.translation_key) {
          map[e.translation_key] = eid;
        }
      }
    }
    this._byKey = map;
  }

  _id(translationKey, fallback) {
    return (this._byKey && this._byKey[translationKey]) || fallback;
  }

  _fmt(id, digits = 0, unit = "") {
    const s = this._state(id);
    if (s === null) return "—";
    const n = Number(s);
    if (Number.isNaN(n)) return s;
    return n.toFixed(digits) + (unit ? " " + unit : "");
  }

  _deviceName(deviceId) {
    const d = this._hass && this._hass.devices && this._hass.devices[deviceId];
    return (d && (d.name_by_user || d.name)) || deviceId;
  }

  /**
   * Group per-battery sensors by their HA device (one sub-device per battery),
   * identifying each metric by translation_key — fully language-agnostic.
   */
  _devices() {
    const out = {};
    const h = this._hass;
    if (!h || !h.entities) return out;
    const METRIC = {
      batt_soc: "soc",
      batt_power: "power",
      batt_temperature: "temperature",
      battery_setpoint_charge: "setpoint_charge",
      battery_setpoint_discharge: "setpoint_discharge",
    };
    for (const eid in h.entities) {
      const e = h.entities[eid];
      if (!e || e.platform !== "solarbalance" || !e.device_id || !e.translation_key) continue;
      const metric = METRIC[e.translation_key];
      if (!metric) continue;
      const dev = (out[e.device_id] ||= { name: this._deviceName(e.device_id) });
      dev[metric] = eid;
    }
    return out;
  }

  _tile(label, value, accent) {
    return `<div class="tile"><div class="tile-v" style="color:${accent || "var(--primary-text-color)"}">${value}</div><div class="tile-l">${label}</div></div>`;
  }

  _row(label, value) {
    return `<div class="row"><span>${label}</span><b>${value}</b></div>`;
  }

  _badge(id) {
    const on = this._state(id) === "on";
    return on;
  }

  _content() {
    if (!this._hass) return `<div class="wrap"><p>Chargement…</p></div>`;
    this._buildByKey();
    const id = (k, fb) => this._id(k, fb);
    // Core + binary entities resolved by translation_key (language-agnostic).
    const E = {
      mode: id("mode", "sensor.solarbalance_mode"),
      strat: id("dominant_strategy", "sensor.solarbalance_dominant_strategy"),
      grid: id("grid_power", "sensor.solarbalance_grid_power"),
      pv: id("pv_power", "sensor.solarbalance_pv_power"),
      battery: id("battery_power", "sensor.solarbalance_battery_power"),
      home: id("baseline_consumption", "sensor.solarbalance_baseline_consumption"),
      soc: id("battery_soc_avg", "sensor.solarbalance_battery_soc_avg"),
      pvToday: id("pv_energy_today", "sensor.solarbalance_pv_energy_today"),
      gridToday: id("grid_import_today", "sensor.solarbalance_grid_import_today"),
      storm: id("storm_mode", "binary_sensor.solarbalance_storm_mode"),
      weather: id("weather_warning", "binary_sensor.solarbalance_weather_warning"),
      degraded: id("degraded", "binary_sensor.solarbalance_degraded"),
      gridFiltered: id("grid_filtered", "sensor.solarbalance_grid_power_filtered"),
      target: id("regulation_target", "sensor.solarbalance_regulation_target"),
      ziCorr: id("zi_correction", "sensor.solarbalance_zero_injection_correction"),
      eqOffer: id("equaliser_offer", "sensor.solarbalance_soc_equaliser_offer"),
      pvLimit: id("pv_output_limit", "sensor.solarbalance_pv_output_limit"),
      planPower: id("planner_recommended_power", "sensor.solarbalance_planner_recommended_power_advisory"),
      planCost: id("planner_expected_cost", "sensor.solarbalance_planner_expected_cost_advisory"),
    };
    const mode = this._state(E.mode) || "—";
    const strat = this._state(E.strat) || "—";
    const modeColors = {
      storm: "var(--error-color, red)",
      degraded: "var(--warning-color, orange)",
      paused: "var(--disabled-text-color, grey)",
      manual_override: "var(--warning-color, gold)",
      normal: "var(--success-color, green)",
    };
    const chips = [];
    if (this._badge(E.storm)) chips.push("⛈️ Tempête");
    if (this._badge(E.weather)) chips.push("⚠️ Vigilance");
    if (this._badge(E.degraded)) chips.push("🛑 Dégradé");

    const devCards = Object.values(this._devices())
      .sort((a, b) => (a.name > b.name ? 1 : -1))
      .map((k) => {
        const rows = [];
        if (k.soc) rows.push(this._row("SoC", this._fmt(k.soc, 0, "%")));
        if (k.power) rows.push(this._row("Puissance", this._fmt(k.power, 0, "W")));
        if (k.temperature) rows.push(this._row("Température", this._fmt(k.temperature, 1, "°C")));
        if (k.setpoint_charge) rows.push(this._row("Consigne charge", this._fmt(k.setpoint_charge, 0, "W")));
        if (k.setpoint_discharge)
          rows.push(this._row("Consigne décharge", this._fmt(k.setpoint_discharge, 0, "W")));
        return `<div class="card"><h3>${k.name}</h3>${rows.join("")}</div>`;
      })
      .join("");

    return `
      <div class="wrap">
        <header>
          <h1>SolarBalance</h1>
          <div class="mode" style="background:${modeColors[mode] || "var(--primary-color)"}">${mode}</div>
          <div class="strat">Stratégie : ${strat}</div>
          <div class="chips">${chips.map((c) => `<span class="chip">${c}</span>`).join("")}</div>
        </header>

        <section class="grid">
          <div class="card">
            <h3>Flux énergétique</h3>
            <div class="tiles">
              ${this._tile("Réseau", this._fmt(E.grid, 0, "W"), "var(--info-color,#39f)")}
              ${this._tile("Solaire", this._fmt(E.pv, 0, "W"), "var(--warning-color,#f90)")}
              ${this._tile("Batteries", this._fmt(E.battery, 0, "W"), "var(--success-color,#2a2)")}
              ${this._tile("Maison", this._fmt(E.home, 0, "W"))}
            </div>
            <div class="tiles">
              ${this._tile("SoC moyen", this._fmt(E.soc, 0, "%"))}
              ${this._tile("PV jour", this._fmt(E.pvToday, 2, "kWh"))}
              ${this._tile("Soutirage jour", this._fmt(E.gridToday, 2, "kWh"))}
            </div>
          </div>

          <div class="card">
            <h3>Régulation</h3>
            ${this._row("Réseau (filtré)", this._fmt(E.gridFiltered, 0, "W"))}
            ${this._row("Cible parc", this._fmt(E.target, 0, "W"))}
            ${this._row("Correction zéro-injection", this._fmt(E.ziCorr, 0, "W"))}
            ${this._row("Offre équaliseur SoC", this._fmt(E.eqOffer, 0, "W"))}
            ${this._row("Limite de sortie PV", this._fmt(E.pvLimit, 0, "W"))}
          </div>

          <div class="card">
            <h3>Plan prédictif (advisory)</h3>
            ${this._row("Puissance recommandée", this._fmt(E.planPower, 0, "W"))}
            ${this._row("Coût attendu (24 h)", this._fmt(E.planCost, 2, "€"))}
          </div>
        </section>

        <h2>Par appareil</h2>
        <section class="grid">${devCards || '<div class="card"><p>Aucun appareil batterie détecté.</p></div>'}</section>
      </div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .wrap { max-width:1100px; margin:0 auto; padding:16px; color:var(--primary-text-color); }
        header { margin-bottom:16px; }
        h1 { margin:0 0 4px; font-size:1.6rem; }
        h2 { margin:24px 0 8px; font-size:1.1rem; color:var(--secondary-text-color); }
        h3 { margin:0 0 8px; font-size:1rem; }
        .mode { display:inline-block; padding:2px 10px; border-radius:12px; color:#fff;
                text-transform:capitalize; font-size:.85rem; }
        .strat { color:var(--secondary-text-color); font-size:.85rem; margin-top:4px; }
        .chips { margin-top:8px; }
        .chip { display:inline-block; padding:2px 8px; margin-right:6px; border-radius:12px;
                background:var(--secondary-background-color); font-size:.8rem; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }
        .card { background:var(--card-background-color,#fff); border-radius:var(--ha-card-border-radius,12px);
                padding:14px; box-shadow:var(--ha-card-box-shadow,0 1px 3px rgba(0,0,0,.1)); }
        .tiles { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
        .tile { flex:1; min-width:70px; text-align:center; padding:8px; border-radius:8px;
                background:var(--secondary-background-color); }
        .tile-v { font-size:1.15rem; font-weight:600; }
        .tile-l { font-size:.72rem; color:var(--secondary-text-color); }
        .row { display:flex; justify-content:space-between; padding:4px 0;
               border-bottom:1px solid var(--divider-color,#eee); font-size:.9rem; }
        .row:last-child { border-bottom:none; }
      </style>
      ${this._content()}`;
  }
}

if (!customElements.get("solarbalance-panel")) {
  customElements.define("solarbalance-panel", SolarBalancePanel);
}
