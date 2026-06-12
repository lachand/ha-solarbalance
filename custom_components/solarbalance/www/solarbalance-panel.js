/**
 * SolarBalance — full-page custom panel (sidebar).
 *
 * Plain web component (no build step). Home Assistant sets `hass` on every state
 * change; we debounce-render. Reads the `sensor.solarbalance_*` entities and the
 * per-device battery sensors, all resolved by translation_key so localised
 * entity_ids (French installs) keep working. Themed via HA CSS variables.
 *
 * Adds a live SVG time-series chart (PV area + grid line) fed by the WebSocket
 * history API, plus energy stat tiles (production, consumption, self-production
 * share, import/export). No external dependencies.
 */

const HISTORY_HOURS = 6; // chart window
const HISTORY_REFRESH_MS = 60000; // re-fetch history at most this often

class SolarBalancePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._pending = false;
    this._byKey = {};
    this._E = {};
    this._series = null;
    this._histTs = 0;
    this._fetching = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._buildByKey();
    this._resolveEntities();
    this._maybeFetchHistory();
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

  _num(id) {
    const s = this._state(id);
    if (s === null) return null;
    const n = Number(s);
    return Number.isNaN(n) ? null : n;
  }

  /**
   * Resolve SolarBalance entities by their stable translation_key via the entity
   * registry. Entity_ids are localised (e.g. French installs get
   * `sensor.solarbalance_puissance_reseau`), translation_key is not.
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

  _resolveEntities() {
    const id = (k, fb) => this._id(k, fb);
    this._E = {
      mode: id("mode", "sensor.solarbalance_mode"),
      strat: id("dominant_strategy", "sensor.solarbalance_dominant_strategy"),
      grid: id("grid_power", "sensor.solarbalance_grid_power"),
      pv: id("pv_power", "sensor.solarbalance_pv_power"),
      battery: id("battery_power", "sensor.solarbalance_battery_power"),
      home: id("baseline_consumption", "sensor.solarbalance_baseline_consumption"),
      soc: id("battery_soc_avg", "sensor.solarbalance_battery_soc_avg"),
      pvToday: id("pv_energy_today", "sensor.solarbalance_pv_energy_today"),
      gridImportToday: id("grid_import_today", "sensor.solarbalance_grid_import_today"),
      gridExportToday: id("grid_export_today", "sensor.solarbalance_grid_export_today"),
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

  /** Group per-battery sensors by HA device, identifying metrics by key. */
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

  // ---- History (WebSocket) ------------------------------------------------

  _maybeFetchHistory() {
    const now = Date.now();
    if (this._fetching) return;
    if (this._series && now - this._histTs < HISTORY_REFRESH_MS) return;
    const ids = [this._E.pv, this._E.grid, this._E.battery].filter(Boolean);
    if (!this._hass || !ids.length) return;
    this._fetching = true;
    const startMs = now - HISTORY_HOURS * 3600 * 1000;
    this._hass
      .callWS({
        type: "history/history_during_period",
        start_time: new Date(startMs).toISOString(),
        end_time: new Date(now).toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      })
      .then((res) => {
        this._series = {
          pv: this._parseSeries(res[this._E.pv]),
          grid: this._parseSeries(res[this._E.grid]),
          battery: this._parseSeries(res[this._E.battery]),
        };
        this._histTs = Date.now();
        this._fetching = false;
        this._render();
      })
      .catch(() => {
        this._fetching = false;
      });
  }

  _parseSeries(arr) {
    if (!Array.isArray(arr)) return [];
    const out = [];
    for (const item of arr) {
      // Compressed history entries: { s: state, lu: last_updated (epoch s) }.
      const v = Number(item.s);
      const lu = item.lu != null ? item.lu : item.last_updated;
      if (Number.isNaN(v) || lu == null) continue;
      out.push({ t: lu * 1000, v });
    }
    return out;
  }

  // ---- SVG chart ----------------------------------------------------------

  _chart() {
    const s = this._series;
    if (!s || (!s.pv.length && !s.grid.length)) {
      return `<div class="chart-empty">Historique en cours de chargement…</div>`;
    }
    const W = 720;
    const H = 240;
    const padL = 44;
    const padR = 12;
    const padT = 12;
    const padB = 22;
    const all = [...s.pv, ...s.grid, ...s.battery];
    let tMin = Infinity;
    let tMax = -Infinity;
    let vMin = 0;
    let vMax = 0;
    for (const p of all) {
      if (p.t < tMin) tMin = p.t;
      if (p.t > tMax) tMax = p.t;
      if (p.v < vMin) vMin = p.v;
      if (p.v > vMax) vMax = p.v;
    }
    if (!isFinite(tMin) || tMax <= tMin) return `<div class="chart-empty">Pas de données.</div>`;
    if (vMax === vMin) vMax = vMin + 1;
    const pad = (vMax - vMin) * 0.08;
    vMax += pad;
    vMin -= pad;

    const x = (t) => padL + ((t - tMin) / (tMax - tMin)) * (W - padL - padR);
    const y = (v) => padT + (1 - (v - vMin) / (vMax - vMin)) * (H - padT - padB);

    const line = (pts) =>
      pts.length
        ? pts.map((p, i) => (i ? "L" : "M") + x(p.t).toFixed(1) + " " + y(p.v).toFixed(1)).join(" ")
        : "";

    // PV filled area down to the zero baseline.
    const y0 = y(0);
    let pvArea = "";
    if (s.pv.length) {
      pvArea =
        "M" + x(s.pv[0].t).toFixed(1) + " " + y0.toFixed(1) + " " +
        s.pv.map((p) => "L" + x(p.t).toFixed(1) + " " + y(p.v).toFixed(1)).join(" ") +
        " L" + x(s.pv[s.pv.length - 1].t).toFixed(1) + " " + y0.toFixed(1) + " Z";
    }

    // Horizontal gridlines + value labels.
    const ticks = 4;
    let grid = "";
    for (let i = 0; i <= ticks; i++) {
      const v = vMin + ((vMax - vMin) * i) / ticks;
      const yy = y(v).toFixed(1);
      grid +=
        `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" class="grid"/>` +
        `<text x="${padL - 6}" y="${(+yy + 3).toFixed(1)}" class="ylbl">${Math.round(v)}</text>`;
    }
    // Zero baseline emphasised when the domain straddles 0.
    let zero = "";
    if (vMin < 0 && vMax > 0) {
      zero = `<line x1="${padL}" y1="${y0.toFixed(1)}" x2="${W - padR}" y2="${y0.toFixed(1)}" class="zero"/>`;
    }
    // Time labels (start, mid, end).
    const fmtT = (t) => {
      const d = new Date(t);
      return d.getHours().toString().padStart(2, "0") + ":" + d.getMinutes().toString().padStart(2, "0");
    };
    const xlbls = [tMin, (tMin + tMax) / 2, tMax]
      .map(
        (t, i) =>
          `<text x="${x(t).toFixed(1)}" y="${H - 6}" class="xlbl" text-anchor="${
            i === 0 ? "start" : i === 2 ? "end" : "middle"
          }">${fmtT(t)}</text>`
      )
      .join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" class="chart" preserveAspectRatio="none" role="img">
        ${grid}${zero}
        ${pvArea ? `<path d="${pvArea}" class="pv-area"/>` : ""}
        ${s.pv.length ? `<path d="${line(s.pv)}" class="pv-line"/>` : ""}
        ${s.grid.length ? `<path d="${line(s.grid)}" class="grid-line"/>` : ""}
        ${s.battery.length ? `<path d="${line(s.battery)}" class="batt-line"/>` : ""}
        ${xlbls}
      </svg>
      <div class="legend">
        <span><i class="sw pv"></i>Solaire</span>
        <span><i class="sw grid"></i>Réseau</span>
        <span><i class="sw batt"></i>Batteries</span>
      </div>`;
  }

  // ---- Derived energy stats ----------------------------------------------

  _energyStats() {
    const pv = this._num(this._E.pvToday);
    const imp = this._num(this._E.gridImportToday);
    const exp = this._num(this._E.gridExportToday);
    // Home consumption = PV self-consumed + grid import.
    const pvSelf = pv != null && exp != null ? Math.max(0, pv - exp) : null;
    let used = null;
    if (pvSelf != null && imp != null) used = pvSelf + imp;
    else if (imp != null) used = imp;
    let selfShare = null;
    if (used != null && used > 0 && pvSelf != null) {
      selfShare = Math.min(100, (pvSelf / used) * 100);
    }
    return { pv, imp, exp, used, selfShare };
  }

  _tile(label, value, accent) {
    return `<div class="tile"><div class="tile-v" style="color:${
      accent || "var(--primary-text-color)"
    }">${value}</div><div class="tile-l">${label}</div></div>`;
  }

  _row(label, value) {
    return `<div class="row"><span>${label}</span><b>${value}</b></div>`;
  }

  _badge(id) {
    return this._state(id) === "on";
  }

  _gauge(pct) {
    if (pct == null) return "—";
    const r = 26;
    const c = 2 * Math.PI * r;
    const off = c * (1 - pct / 100);
    return `
      <svg viewBox="0 0 64 64" class="gauge">
        <circle cx="32" cy="32" r="${r}" class="g-bg"/>
        <circle cx="32" cy="32" r="${r}" class="g-fg"
                stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/>
        <text x="32" y="37" text-anchor="middle" class="g-txt">${Math.round(pct)}%</text>
      </svg>`;
  }

  _content() {
    if (!this._hass) return `<div class="wrap"><p>Chargement…</p></div>`;
    const E = this._E;
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

    const st = this._energyStats();
    const kwh = (v) => (v == null ? "—" : v.toFixed(2) + " kWh");

    const devCards = Object.values(this._devices())
      .sort((a, b) => (a.name > b.name ? 1 : -1))
      .map((k) => {
        const soc = this._num(k.soc);
        const rows = [];
        if (k.power) rows.push(this._row("Puissance", this._fmt(k.power, 0, "W")));
        if (k.temperature) rows.push(this._row("Température", this._fmt(k.temperature, 1, "°C")));
        if (k.setpoint_charge) rows.push(this._row("Consigne charge", this._fmt(k.setpoint_charge, 0, "W")));
        if (k.setpoint_discharge)
          rows.push(this._row("Consigne décharge", this._fmt(k.setpoint_discharge, 0, "W")));
        const gauge = soc != null ? `<div class="dev-gauge">${this._gauge(soc)}</div>` : "";
        return `<div class="card"><h3>${k.name}</h3><div class="dev-body">${gauge}<div class="dev-rows">${rows.join(
          ""
        )}</div></div></div>`;
      })
      .join("");

    return `
      <div class="wrap">
        <header>
          <div class="hrow">
            <h1>SolarBalance</h1>
            <div class="mode" style="background:${modeColors[mode] || "var(--primary-color)"}">${mode}</div>
          </div>
          <div class="strat">Stratégie : ${strat}</div>
          <div class="chips">${chips.map((c) => `<span class="chip">${c}</span>`).join("")}</div>
        </header>

        <section class="stats">
          ${this._tile("Production PV", kwh(st.pv), "var(--warning-color,#f5a623)")}
          ${this._tile("Consommation", kwh(st.used))}
          ${this._tile("Soutiré réseau", kwh(st.imp), "var(--info-color,#3d8bff)")}
          ${this._tile("Injecté réseau", kwh(st.exp), "var(--success-color,#27ae60)")}
          <div class="tile share">
            ${this._gauge(st.selfShare)}
            <div class="tile-l">Part autoproduite</div>
          </div>
        </section>

        <section class="card chart-card">
          <h3>Puissance — ${HISTORY_HOURS} dernières heures</h3>
          ${this._chart()}
        </section>

        <section class="grid">
          <div class="card">
            <h3>Flux instantané</h3>
            <div class="tiles">
              ${this._tile("Réseau", this._fmt(E.grid, 0, "W"), "var(--info-color,#3d8bff)")}
              ${this._tile("Solaire", this._fmt(E.pv, 0, "W"), "var(--warning-color,#f5a623)")}
              ${this._tile("Batteries", this._fmt(E.battery, 0, "W"), "var(--success-color,#27ae60)")}
              ${this._tile("Maison", this._fmt(E.home, 0, "W"))}
            </div>
            <div class="tiles">
              ${this._tile("SoC moyen", this._fmt(E.soc, 0, "%"))}
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
        .hrow { display:flex; align-items:center; gap:12px; }
        h1 { margin:0; font-size:1.6rem; }
        h2 { margin:24px 0 8px; font-size:1.1rem; color:var(--secondary-text-color); }
        h3 { margin:0 0 10px; font-size:1rem; }
        .mode { display:inline-block; padding:2px 10px; border-radius:12px; color:#fff;
                text-transform:capitalize; font-size:.85rem; }
        .strat { color:var(--secondary-text-color); font-size:.85rem; margin-top:4px; }
        .chips { margin-top:8px; }
        .chip { display:inline-block; padding:2px 8px; margin-right:6px; border-radius:12px;
                background:var(--secondary-background-color); font-size:.8rem; }
        .card { background:var(--card-background-color,#fff); border-radius:var(--ha-card-border-radius,12px);
                padding:14px; box-shadow:var(--ha-card-box-shadow,0 1px 3px rgba(0,0,0,.1)); }
        .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px;
                 margin-bottom:12px; }
        .stats .tile { background:var(--card-background-color,#fff);
                       box-shadow:var(--ha-card-box-shadow,0 1px 3px rgba(0,0,0,.1));
                       border-radius:var(--ha-card-border-radius,12px); padding:14px 8px; }
        .stats .tile-v { font-size:1.5rem; }
        .share { display:flex; flex-direction:column; align-items:center; gap:4px; }
        .chart-card { margin-bottom:12px; }
        .chart { width:100%; height:auto; display:block; }
        .chart-empty { color:var(--secondary-text-color); padding:40px 0; text-align:center; }
        .grid-line { fill:none; stroke:var(--info-color,#3d8bff); stroke-width:2; }
        .pv-line { fill:none; stroke:var(--warning-color,#f5a623); stroke-width:2; }
        .pv-area { fill:var(--warning-color,#f5a623); opacity:.18; stroke:none; }
        .batt-line { fill:none; stroke:var(--success-color,#27ae60); stroke-width:1.5;
                     stroke-dasharray:4 3; opacity:.8; }
        .grid { stroke:var(--divider-color,#e0e0e0); stroke-width:1; }
        line.grid { stroke:var(--divider-color,#e0e0e0); }
        .zero { stroke:var(--secondary-text-color,#888); stroke-width:1; stroke-dasharray:2 2; }
        .ylbl { fill:var(--secondary-text-color); font-size:10px; text-anchor:end; }
        .xlbl { fill:var(--secondary-text-color); font-size:10px; }
        .legend { display:flex; gap:16px; justify-content:center; margin-top:6px;
                  font-size:.8rem; color:var(--secondary-text-color); }
        .legend i.sw { display:inline-block; width:12px; height:3px; border-radius:2px;
                       margin-right:5px; vertical-align:middle; }
        .legend .sw.pv { background:var(--warning-color,#f5a623); }
        .legend .sw.grid { background:var(--info-color,#3d8bff); }
        .legend .sw.batt { background:var(--success-color,#27ae60); }
        .grid-section, .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }
        section.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }
        .tiles { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
        .tile { flex:1; min-width:70px; text-align:center; padding:8px; border-radius:8px;
                background:var(--secondary-background-color); }
        .tile-v { font-size:1.15rem; font-weight:600; }
        .tile-l { font-size:.72rem; color:var(--secondary-text-color); }
        .row { display:flex; justify-content:space-between; padding:4px 0;
               border-bottom:1px solid var(--divider-color,#eee); font-size:.9rem; }
        .row:last-child { border-bottom:none; }
        .dev-body { display:flex; align-items:center; gap:12px; }
        .dev-gauge { flex:0 0 auto; }
        .dev-rows { flex:1; }
        .gauge { width:64px; height:64px; }
        .g-bg { fill:none; stroke:var(--divider-color,#e0e0e0); stroke-width:6; }
        .g-fg { fill:none; stroke:var(--success-color,#27ae60); stroke-width:6;
                stroke-linecap:round; transform:rotate(-90deg); transform-origin:32px 32px; }
        .g-txt { fill:var(--primary-text-color); font-size:14px; font-weight:600; }
      </style>
      ${this._content()}`;
  }
}

if (!customElements.get("solarbalance-panel")) {
  customElements.define("solarbalance-panel", SolarBalancePanel);
}
