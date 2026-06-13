/**
 * SolarBalance — full-page custom panel (sidebar).
 *
 * Plain web component (no build step). Home Assistant sets `hass` on every state
 * change; we debounce-render. Reads the `sensor.solarbalance_*` entities and the
 * per-device battery sensors, all resolved by translation_key so localised
 * entity_ids (French installs) keep working. Themed via HA CSS variables.
 *
 * Features:
 *  - animated energy-flow diagram (PV / battery / grid ↔ home);
 *  - live SVG time-series chart (PV area + grid/battery lines) via the WS history
 *    API, with a selectable window (1 h / 6 h / 24 h) and a PV-forecast overlay;
 *  - energy stat tiles + self-consumption / autonomy donuts;
 *  - subscribed-power load gauge; per-battery SoC gauges;
 *  - weather/storm banner + data-freshness indicator.
 *
 * No external dependencies.
 */

const HISTORY_REFRESH_MS = 60000; // re-fetch history at most this often
const TICK_MS = 30000; // periodic re-render (freshness + history refresh)
const FUTURE_CAP_H = 6; // how far ahead to draw the PV forecast

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
    this._window = 6; // hours
    this._timer = null;
    this._onClick = this._onClick.bind(this);
  }

  set hass(hass) {
    this._hass = hass;
    this._buildByKey();
    this._resolveEntities();
    this._maybeFetchHistory();
    this._scheduleRender();
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("click", this._onClick);
    this._render();
    this._timer = setInterval(() => {
      this._maybeFetchHistory();
      this._scheduleRender();
    }, TICK_MS);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onClick);
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
  }

  _onClick(ev) {
    const btn = ev.composedPath().find((n) => n.dataset && n.dataset.h);
    if (!btn) return;
    const h = Number(btn.dataset.h);
    if (h && h !== this._window) {
      this._window = h;
      this._histTs = 0; // force refetch for the new window
      this._maybeFetchHistory();
      this._render();
    }
  }

  _scheduleRender() {
    if (this._pending) return;
    this._pending = true;
    setTimeout(() => {
      this._pending = false;
      this._render();
    }, 300);
  }

  _stateObj(id) {
    return (id && this._hass && this._hass.states[id]) || null;
  }

  _state(id) {
    const s = this._stateObj(id);
    if (!s || s.state === "unavailable" || s.state === "unknown" || s.state === "") return null;
    return s.state;
  }

  _num(id) {
    const s = this._state(id);
    if (s === null) return null;
    const n = Number(s);
    return Number.isNaN(n) ? null : n;
  }

  _attr(id, name) {
    const s = this._stateObj(id);
    return s && s.attributes ? s.attributes[name] : undefined;
  }

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

  _w(n) {
    if (n == null) return "—";
    const a = Math.abs(n);
    return a >= 1000 ? (n / 1000).toFixed(2) + " kW" : Math.round(n) + " W";
  }

  _deviceName(deviceId) {
    const d = this._hass && this._hass.devices && this._hass.devices[deviceId];
    return (d && (d.name_by_user || d.name)) || deviceId;
  }

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
    if (this._series && this._series.window === this._window && now - this._histTs < HISTORY_REFRESH_MS) {
      return;
    }
    const ids = [this._E.pv, this._E.grid, this._E.battery].filter(Boolean);
    if (!this._hass || !ids.length) return;
    this._fetching = true;
    const startMs = now - this._window * 3600 * 1000;
    const win = this._window;
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
          window: win,
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
      const v = Number(item.s);
      const lu = item.lu != null ? item.lu : item.last_updated;
      if (Number.isNaN(v) || lu == null) continue;
      out.push({ t: lu * 1000, v });
    }
    return out;
  }

  _forecastSeries(now) {
    const fc = this._attr(this._E.pv, "pv_forecast_hourly");
    if (!Array.isArray(fc)) return [];
    const cap = now + Math.min(this._window, FUTURE_CAP_H) * 3600 * 1000;
    const out = [];
    for (const p of fc) {
      const t = Date.parse(p.start);
      const v = Number(p.w);
      if (Number.isNaN(t) || Number.isNaN(v) || t > cap) continue;
      out.push({ t, v });
    }
    return out.sort((a, b) => a.t - b.t);
  }

  // ---- SVG chart ----------------------------------------------------------

  _chart() {
    const s = this._series;
    if (!s || (!s.pv.length && !s.grid.length)) {
      return `<div class="chart-empty">Historique en cours de chargement…</div>`;
    }
    const now = Date.now();
    const fc = this._forecastSeries(now);
    const W = 720;
    const H = 240;
    const padL = 44;
    const padR = 12;
    const padT = 12;
    const padB = 22;
    const all = [...s.pv, ...s.grid, ...s.battery, ...fc];
    let tMin = now - this._window * 3600 * 1000;
    let tMax = now;
    let vMin = 0;
    let vMax = 0;
    for (const p of all) {
      if (p.t < tMin) tMin = p.t;
      if (p.t > tMax) tMax = p.t;
      if (p.v < vMin) vMin = p.v;
      if (p.v > vMax) vMax = p.v;
    }
    if (tMax <= tMin) return `<div class="chart-empty">Pas de données.</div>`;
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

    const y0 = y(0);
    let pvArea = "";
    if (s.pv.length) {
      pvArea =
        "M" + x(s.pv[0].t).toFixed(1) + " " + y0.toFixed(1) + " " +
        s.pv.map((p) => "L" + x(p.t).toFixed(1) + " " + y(p.v).toFixed(1)).join(" ") +
        " L" + x(s.pv[s.pv.length - 1].t).toFixed(1) + " " + y0.toFixed(1) + " Z";
    }

    const ticks = 4;
    let grid = "";
    for (let i = 0; i <= ticks; i++) {
      const v = vMin + ((vMax - vMin) * i) / ticks;
      const yy = y(v).toFixed(1);
      grid +=
        `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" class="grid"/>` +
        `<text x="${padL - 6}" y="${(+yy + 3).toFixed(1)}" class="ylbl">${Math.round(v)}</text>`;
    }
    let zero = "";
    if (vMin < 0 && vMax > 0) {
      zero = `<line x1="${padL}" y1="${y0.toFixed(1)}" x2="${W - padR}" y2="${y0.toFixed(1)}" class="zero"/>`;
    }
    // "Now" marker separates measured history from forecast.
    const nowX = x(now).toFixed(1);
    const nowLine = fc.length
      ? `<line x1="${nowX}" y1="${padT}" x2="${nowX}" y2="${H - padB}" class="nowline"/>`
      : "";

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
        ${grid}${zero}${nowLine}
        ${pvArea ? `<path d="${pvArea}" class="pv-area"/>` : ""}
        ${fc.length ? `<path d="${line(fc)}" class="fc-line"/>` : ""}
        ${s.pv.length ? `<path d="${line(s.pv)}" class="pv-line"/>` : ""}
        ${s.grid.length ? `<path d="${line(s.grid)}" class="grid-line"/>` : ""}
        ${s.battery.length ? `<path d="${line(s.battery)}" class="batt-line"/>` : ""}
        ${xlbls}
      </svg>
      <div class="legend">
        <span><i class="sw pv"></i>Solaire</span>
        <span><i class="sw grid"></i>Réseau</span>
        <span><i class="sw batt"></i>Batteries</span>
        ${fc.length ? '<span><i class="sw fc"></i>Prévision PV</span>' : ""}
      </div>`;
  }

  _windowSelector() {
    return `<div class="winsel">${[1, 6, 24]
      .map(
        (h) =>
          `<button data-h="${h}" class="${this._window === h ? "on" : ""}">${h} h</button>`
      )
      .join("")}</div>`;
  }

  // ---- Energy-flow diagram ------------------------------------------------

  _flowLink(d, w, color, threshold = 20) {
    const a = Math.abs(w || 0);
    if (a < threshold) return `<path d="${d}" class="flow-link off"/>`;
    const width = Math.max(1.5, Math.min(7, 1.5 + a / 400)).toFixed(1);
    const dur = Math.max(0.5, 2 - a / 1000).toFixed(2);
    // Path is drawn outer→home; w>0 means "toward home" (flow-in).
    const dir = w > 0 ? "flow-in" : "flow-out";
    return `<path d="${d}" class="flow-link ${dir}" style="stroke:${color};stroke-width:${width};animation-duration:${dur}s"/>`;
  }

  _flowNode(cx, cy, emoji, label, value, color) {
    return `
      <g class="flow-node">
        <circle cx="${cx}" cy="${cy}" r="26" style="stroke:${color}"/>
        <text x="${cx}" y="${cy - 2}" class="fn-ico">${emoji}</text>
        <text x="${cx}" y="${cy + 14}" class="fn-val">${value}</text>
        <text x="${cx}" y="${cy + 42}" class="fn-lbl">${label}</text>
      </g>`;
  }

  _flow() {
    const pv = this._num(this._E.pv) || 0;
    const grid = this._num(this._E.grid) || 0; // + import, − export
    const batt = this._num(this._E.battery) || 0; // + charge, − discharge
    const home = this._num(this._E.home) || 0;
    const soc = this._num(this._E.soc);
    const PV = "var(--warning-color,#f5a623)";
    const GR = "var(--info-color,#3d8bff)";
    const BT = "var(--success-color,#27ae60)";
    // outer→home; sign sets animation direction (>0 toward home).
    const links =
      this._flowLink("M160 40 L160 96", pv, PV) + // PV → home (always toward home)
      this._flowLink("M64 110 L134 110", grid, GR) + // grid: import>0 toward home
      this._flowLink("M256 110 L186 110", -batt, BT); // discharge(−batt>0) toward home
    const battLabel = soc != null ? `Batteries · ${Math.round(soc)}%` : "Batteries";
    return `
      <svg viewBox="0 0 320 220" class="flow" role="img">
        ${links}
        ${this._flowNode(160, 30, "☀️", "Solaire", this._w(pv), PV)}
        ${this._flowNode(38, 110, "🔌", "Réseau", this._w(grid), GR)}
        ${this._flowNode(282, 110, "🔋", battLabel, this._w(batt), BT)}
        ${this._flowNode(160, 150, "🏠", "Maison", this._w(home), "var(--primary-text-color)")}
      </svg>`;
  }

  // ---- Derived energy stats ----------------------------------------------

  _energyStats() {
    const pv = this._num(this._E.pvToday);
    const imp = this._num(this._E.gridImportToday);
    const exp = this._num(this._E.gridExportToday);
    const pvSelf = pv != null && exp != null ? Math.max(0, pv - exp) : null;
    let used = null;
    if (pvSelf != null && imp != null) used = pvSelf + imp;
    else if (imp != null) used = imp;
    // Autonomy: share of consumption NOT drawn from the grid.
    let autonomy = null;
    if (used != null && used > 0 && imp != null) autonomy = Math.max(0, Math.min(100, ((used - imp) / used) * 100));
    // Self-consumption: share of production consumed locally (not exported).
    let selfCons = null;
    if (pv != null && pv > 0 && exp != null) selfCons = Math.max(0, Math.min(100, ((pv - exp) / pv) * 100));
    return { pv, imp, exp, used, autonomy, selfCons };
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

  _gauge(pct, color) {
    if (pct == null) return `<svg viewBox="0 0 64 64" class="gauge"><text x="32" y="37" text-anchor="middle" class="g-txt">—</text></svg>`;
    const r = 26;
    const c = 2 * Math.PI * r;
    const off = c * (1 - Math.max(0, Math.min(100, pct)) / 100);
    return `
      <svg viewBox="0 0 64 64" class="gauge">
        <circle cx="32" cy="32" r="${r}" class="g-bg"/>
        <circle cx="32" cy="32" r="${r}" class="g-fg" style="stroke:${color || "var(--success-color,#27ae60)"}"
                stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/>
        <text x="32" y="37" text-anchor="middle" class="g-txt">${Math.round(pct)}%</text>
      </svg>`;
  }

  _loadGauge() {
    const sub = this._attr(this._E.grid, "subscribed_power_w");
    const grid = this._num(this._E.grid);
    if (!sub || grid == null) return "";
    const imp = Math.max(0, grid);
    const pct = (imp / sub) * 100;
    const color = pct >= 90 ? "var(--error-color,#e74c3c)" : pct >= 70 ? "var(--warning-color,#f5a623)" : "var(--success-color,#27ae60)";
    return `
      <div class="card load-card">
        <h3>Puissance souscrite</h3>
        <div class="load-body">
          ${this._gauge(pct, color)}
          <div class="load-info">
            <div class="load-v">${(imp / 1000).toFixed(2)} / ${(sub / 1000).toFixed(0)} kW</div>
            <div class="load-l">Soutirage instantané</div>
          </div>
        </div>
      </div>`;
  }

  _freshness() {
    const s = this._stateObj(this._E.grid);
    const lu = s && (s.last_updated || s.last_changed);
    if (!lu) return "";
    const ago = Math.max(0, Math.round((Date.now() - Date.parse(lu)) / 1000));
    const txt = ago < 90 ? `il y a ${ago} s` : `il y a ${Math.round(ago / 60)} min`;
    const stale = ago > 120;
    return `<span class="fresh ${stale ? "stale" : ""}">● mis à jour ${txt}</span>`;
  }

  _banner() {
    const msgs = [];
    if (this._badge(this._E.storm)) msgs.push("⛈️ Mode tempête actif — préparation du stockage en cours.");
    if (this._badge(this._E.degraded)) msgs.push("🛑 Mode dégradé — une ou plusieurs entités sont indisponibles.");
    if (this._badge(this._E.weather)) msgs.push("⚠️ Vigilance météo en cours.");
    if (!msgs.length) return "";
    const cls = this._badge(this._E.degraded) ? "err" : "warn";
    return `<div class="banner ${cls}">${msgs.map((m) => `<div>${m}</div>`).join("")}</div>`;
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
            ${this._freshness()}
          </div>
          <div class="strat">Stratégie : ${strat}</div>
        </header>

        ${this._banner()}

        <section class="grid two">
          <div class="card flow-card">
            <h3>Flux en temps réel</h3>
            ${this._flow()}
          </div>
          <div class="card">
            <h3>Bilan du jour</h3>
            <div class="donuts">
              <div class="donut">${this._gauge(st.selfCons, "var(--warning-color,#f5a623)")}<div class="tile-l">Autoconsommation</div></div>
              <div class="donut">${this._gauge(st.autonomy, "var(--success-color,#27ae60)")}<div class="tile-l">Autonomie</div></div>
            </div>
            <div class="tiles">
              ${this._tile("Production", kwh(st.pv), "var(--warning-color,#f5a623)")}
              ${this._tile("Consommation", kwh(st.used))}
            </div>
            <div class="tiles">
              ${this._tile("Soutiré", kwh(st.imp), "var(--info-color,#3d8bff)")}
              ${this._tile("Injecté", kwh(st.exp), "var(--success-color,#27ae60)")}
            </div>
          </div>
        </section>

        <section class="card chart-card">
          <div class="chart-head">
            <h3>Puissance</h3>
            ${this._windowSelector()}
          </div>
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

          ${this._loadGauge()}

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
        header { margin-bottom:12px; }
        .hrow { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
        h1 { margin:0; font-size:1.6rem; }
        h2 { margin:24px 0 8px; font-size:1.1rem; color:var(--secondary-text-color); }
        h3 { margin:0 0 10px; font-size:1rem; }
        .mode { display:inline-block; padding:2px 10px; border-radius:12px; color:#fff;
                text-transform:capitalize; font-size:.85rem; }
        .strat { color:var(--secondary-text-color); font-size:.85rem; margin-top:4px; }
        .fresh { font-size:.78rem; color:var(--success-color,#27ae60); margin-left:auto; }
        .fresh.stale { color:var(--warning-color,#f5a623); }
        .banner { border-radius:var(--ha-card-border-radius,12px); padding:10px 14px; margin-bottom:12px;
                  font-size:.9rem; }
        .banner.warn { background:rgba(245,166,35,.15); border:1px solid var(--warning-color,#f5a623); }
        .banner.err { background:rgba(231,76,60,.15); border:1px solid var(--error-color,#e74c3c); }
        .card { background:var(--card-background-color,#fff); border-radius:var(--ha-card-border-radius,12px);
                padding:14px; box-shadow:var(--ha-card-box-shadow,0 1px 3px rgba(0,0,0,.1)); }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }
        .grid.two { grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); margin-bottom:12px; }

        /* Flow diagram */
        .flow-card { display:flex; flex-direction:column; }
        .flow { width:100%; height:auto; max-height:280px; }
        .flow-node circle { fill:var(--card-background-color,#fff); stroke-width:2.5; }
        .fn-ico { font-size:18px; text-anchor:middle; }
        .fn-val { font-size:9px; text-anchor:middle; fill:var(--primary-text-color); font-weight:600; }
        .fn-lbl { font-size:9px; text-anchor:middle; fill:var(--secondary-text-color); }
        .flow-link { fill:none; stroke-linecap:round; stroke-dasharray:5 7; }
        .flow-link.off { stroke:var(--divider-color,#ddd); stroke-width:2; }
        .flow-link.flow-in { animation:dashIn linear infinite; }
        .flow-link.flow-out { animation:dashOut linear infinite; }
        @keyframes dashIn { to { stroke-dashoffset:-24; } }
        @keyframes dashOut { to { stroke-dashoffset:24; } }

        /* Donuts */
        .donuts { display:flex; justify-content:space-around; gap:12px; margin-bottom:10px; }
        .donut { display:flex; flex-direction:column; align-items:center; gap:4px; }

        /* Chart */
        .chart-card { margin-bottom:12px; }
        .chart-head { display:flex; align-items:center; justify-content:space-between; }
        .winsel button { background:var(--secondary-background-color); color:var(--secondary-text-color);
                border:none; border-radius:8px; padding:4px 10px; margin-left:6px; cursor:pointer;
                font-size:.8rem; }
        .winsel button.on { background:var(--primary-color); color:#fff; }
        .chart { width:100%; height:auto; display:block; }
        .chart-empty { color:var(--secondary-text-color); padding:40px 0; text-align:center; }
        .grid-line { fill:none; stroke:var(--info-color,#3d8bff); stroke-width:2; }
        .pv-line { fill:none; stroke:var(--warning-color,#f5a623); stroke-width:2; }
        .pv-area { fill:var(--warning-color,#f5a623); opacity:.18; stroke:none; }
        .fc-line { fill:none; stroke:var(--warning-color,#f5a623); stroke-width:1.5;
                   stroke-dasharray:5 4; opacity:.65; }
        .batt-line { fill:none; stroke:var(--success-color,#27ae60); stroke-width:1.5;
                     stroke-dasharray:4 3; opacity:.8; }
        line.grid { stroke:var(--divider-color,#e0e0e0); stroke-width:1; }
        .zero { stroke:var(--secondary-text-color,#888); stroke-width:1; stroke-dasharray:2 2; }
        .nowline { stroke:var(--secondary-text-color,#888); stroke-width:1; opacity:.5; }
        .ylbl { fill:var(--secondary-text-color); font-size:10px; text-anchor:end; }
        .xlbl { fill:var(--secondary-text-color); font-size:10px; }
        .legend { display:flex; gap:16px; justify-content:center; margin-top:6px; flex-wrap:wrap;
                  font-size:.8rem; color:var(--secondary-text-color); }
        .legend i.sw { display:inline-block; width:12px; height:3px; border-radius:2px;
                       margin-right:5px; vertical-align:middle; }
        .legend .sw.pv { background:var(--warning-color,#f5a623); }
        .legend .sw.grid { background:var(--info-color,#3d8bff); }
        .legend .sw.batt { background:var(--success-color,#27ae60); }
        .legend .sw.fc { background:var(--warning-color,#f5a623); opacity:.6; }

        /* Tiles & rows */
        .tiles { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
        .tile { flex:1; min-width:70px; text-align:center; padding:8px; border-radius:8px;
                background:var(--secondary-background-color); }
        .tile-v { font-size:1.15rem; font-weight:600; }
        .tile-l { font-size:.72rem; color:var(--secondary-text-color); }
        .row { display:flex; justify-content:space-between; padding:4px 0;
               border-bottom:1px solid var(--divider-color,#eee); font-size:.9rem; }
        .row:last-child { border-bottom:none; }

        /* Load gauge */
        .load-body { display:flex; align-items:center; gap:14px; }
        .load-v { font-size:1.1rem; font-weight:600; }
        .load-l { font-size:.72rem; color:var(--secondary-text-color); }

        /* Per-device */
        .dev-body { display:flex; align-items:center; gap:12px; }
        .dev-gauge { flex:0 0 auto; }
        .dev-rows { flex:1; }
        .gauge { width:64px; height:64px; }
        .g-bg { fill:none; stroke:var(--divider-color,#e0e0e0); stroke-width:6; }
        .g-fg { fill:none; stroke-width:6; stroke-linecap:round;
                transform:rotate(-90deg); transform-origin:32px 32px; }
        .g-txt { fill:var(--primary-text-color); font-size:14px; font-weight:600; }
      </style>
      ${this._content()}`;
  }
}

if (!customElements.get("solarbalance-panel")) {
  customElements.define("solarbalance-panel", SolarBalancePanel);
}
