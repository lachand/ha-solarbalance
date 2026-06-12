/**
 * SolarBalance — full-page custom panel (sidebar).
 *
 * Plain web component (no build step). Home Assistant sets `hass` on every state
 * change; we debounce-render. Reads the `sensor.solarbalance_*` entities and the
 * per-device battery sensors. Themed via HA CSS variables.
 */

const AGG_BLOCKLIST = new Set(["grid", "pv", "battery", "baseline"]);

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
    const s = this._hass && this._hass.states[id];
    if (!s || s.state === "unavailable" || s.state === "unknown" || s.state === "") return null;
    return s.state;
  }

  _fmt(id, digits = 0, unit = "") {
    const s = this._state(id);
    if (s === null) return "—";
    const n = Number(s);
    if (Number.isNaN(n)) return s;
    return n.toFixed(digits) + (unit ? " " + unit : "");
  }

  _devices() {
    const out = {};
    const h = this._hass;
    if (!h) return out;
    const re = /^sensor\.solarbalance_(.+)_(soc|power|temperature|setpoint_charge|setpoint_discharge)$/;
    for (const id in h.states) {
      const m = id.match(re);
      if (m && !AGG_BLOCKLIST.has(m[1])) {
        (out[m[1]] ||= {})[m[2]] = id;
      }
    }
    // Keep only real devices (those exposing a SoC or a setpoint).
    for (const dev of Object.keys(out)) {
      const k = out[dev];
      if (!("soc" in k) && !("setpoint_charge" in k) && !("setpoint_discharge" in k)) {
        delete out[dev];
      }
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
    const mode = this._state("sensor.solarbalance_mode") || "—";
    const strat = this._state("sensor.solarbalance_dominant_strategy") || "—";
    const modeColors = {
      storm: "var(--error-color, red)",
      degraded: "var(--warning-color, orange)",
      paused: "var(--disabled-text-color, grey)",
      manual_override: "var(--warning-color, gold)",
      normal: "var(--success-color, green)",
    };
    const chips = [];
    if (this._badge("binary_sensor.solarbalance_storm_mode")) chips.push("⛈️ Tempête");
    if (this._badge("binary_sensor.solarbalance_weather_warning")) chips.push("⚠️ Vigilance");
    if (this._badge("binary_sensor.solarbalance_degraded")) chips.push("🛑 Dégradé");

    const devs = this._devices();
    const devCards = Object.keys(devs)
      .sort()
      .map((dev) => {
        const k = devs[dev];
        const rows = [];
        if (k.soc) rows.push(this._row("SoC", this._fmt(k.soc, 0, "%")));
        if (k.power) rows.push(this._row("Puissance", this._fmt(k.power, 0, "W")));
        if (k.temperature) rows.push(this._row("Température", this._fmt(k.temperature, 1, "°C")));
        if (k.setpoint_charge) rows.push(this._row("Consigne charge", this._fmt(k.setpoint_charge, 0, "W")));
        if (k.setpoint_discharge)
          rows.push(this._row("Consigne décharge", this._fmt(k.setpoint_discharge, 0, "W")));
        const title = dev.replace(/_/g, " ");
        return `<div class="card"><h3>${title}</h3>${rows.join("")}</div>`;
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
              ${this._tile("Réseau", this._fmt("sensor.solarbalance_grid_power", 0, "W"), "var(--info-color,#39f)")}
              ${this._tile("Solaire", this._fmt("sensor.solarbalance_pv_power", 0, "W"), "var(--warning-color,#f90)")}
              ${this._tile("Batteries", this._fmt("sensor.solarbalance_battery_power", 0, "W"), "var(--success-color,#2a2)")}
              ${this._tile("Maison", this._fmt("sensor.solarbalance_baseline_consumption", 0, "W"))}
            </div>
            <div class="tiles">
              ${this._tile("SoC moyen", this._fmt("sensor.solarbalance_battery_soc_avg", 0, "%"))}
              ${this._tile("PV jour", this._fmt("sensor.solarbalance_pv_energy_today", 2, "kWh"))}
              ${this._tile("Soutirage jour", this._fmt("sensor.solarbalance_grid_import_today", 2, "kWh"))}
            </div>
          </div>

          <div class="card">
            <h3>Régulation</h3>
            ${this._row("Réseau (filtré)", this._fmt("sensor.solarbalance_grid_power_filtered", 0, "W"))}
            ${this._row("Cible parc", this._fmt("sensor.solarbalance_regulation_target", 0, "W"))}
            ${this._row("Correction zéro-injection", this._fmt("sensor.solarbalance_zero_injection_correction", 0, "W"))}
            ${this._row("Offre équaliseur SoC", this._fmt("sensor.solarbalance_soc_equaliser_offer", 0, "W"))}
            ${this._row("Limite de sortie PV", this._fmt("sensor.solarbalance_pv_output_limit", 0, "W"))}
          </div>

          <div class="card">
            <h3>Plan prédictif (advisory)</h3>
            ${this._row("Puissance recommandée", this._fmt("sensor.solarbalance_planner_recommended_power_advisory", 0, "W"))}
            ${this._row("Coût attendu (24 h)", this._fmt("sensor.solarbalance_planner_expected_cost_advisory", 2, "€"))}
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
