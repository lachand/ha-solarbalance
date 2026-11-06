/**
 * SolarBalance full-page custom panel (sidebar), Signature design.
 *
 * Plain ES modules, no build step. Home Assistant sets `hass` on every state change; we
 * debounce-render only the pieces whose HTML actually changed, so focus and scroll survive.
 * Four tabs (Maintenant, Pilotage, Batteries, Santé) sit under a header and a strip of
 * live measures. Reads `sensor.solarbalance_*` entities resolved by translation_key.
 */

import { Model } from "./model.js";
import { HISTORY_REFRESH_MS, midnightMs, parseSeries } from "./history.js";
import { esc, fmtDuration, fmtPower } from "./format.js";
import { modeState } from "./mode.js";
import { icon, measureOf, stamp, tile } from "./ui.js";
import { renderNow } from "./tabs/now.js";
import { renderControl } from "./tabs/control.js";
import { renderBatteries } from "./tabs/batteries.js";
import { healthSummary, renderHealth } from "./tabs/health.js";

const TICK_MS = 30000;
const RENDER_DEBOUNCE_MS = 300;
const VENDOR = new URL("../vendor/signature/", import.meta.url).href;
const PANEL_CSS = new URL("./panel.css", import.meta.url).href;

const TABS = [
  { id: "now", label: "Maintenant", render: renderNow },
  { id: "control", label: "Pilotage", render: renderControl },
  { id: "batteries", label: "Batteries", render: renderBatteries },
  { id: "health", label: "Santé", render: renderHealth },
];

function store(key, value) {
  try {
    if (value === undefined) return window.localStorage.getItem(key);
    window.localStorage.setItem(key, value);
  } catch (e) {
    // Storage can be blocked (private window, site data cleared): the panel works without it.
  }
  return null;
}

/** @font-face is ignored inside a shadow root, so the fonts are declared once on the document. */
function ensureFonts() {
  if (document.getElementById("sb-signature-fonts")) return;
  const link = document.createElement("link");
  link.id = "sb-signature-fonts";
  link.rel = "stylesheet";
  link.href = `${VENDOR}fonts.css`;
  document.head.appendChild(link);
}

class SolarBalancePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.m = new Model();
    this._hass = null;
    this._narrow = false;
    this._pending = false;
    this._timer = null;
    this._fetching = false;
    this._histTs = 0;
    this._cache = {};
    this._ask = null;
    const savedTab = store("solarbalance.tab");
    this.st = {
      tab: TABS.some((t) => t.id === savedTab) ? savedTab : "now",
      window: 6,
      series: null,
      showRaw: false,
      regHist: [],
      debugOpen: false,
      cw: 720,
      contrast: store("solarbalance.contrast") === "1",
    };
    this._onClick = this._onClick.bind(this);
    this._onKey = this._onKey.bind(this);
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    this.m.setHass(hass);
    this._accumulateReg();
    this._maybeFetchHistory();
    this._scheduleRender();
  }

  get hass() {
    return this._hass;
  }

  set narrow(v) {
    this._narrow = !!v;
    this._syncMenu();
  }

  get narrow() {
    return this._narrow;
  }

  connectedCallback() {
    ensureFonts();
    this._build();
    this.shadowRoot.addEventListener("click", this._onClick);
    this.shadowRoot.addEventListener("keydown", this._onKey);
    this._ro = new ResizeObserver(() => this._measure());
    this._ro.observe(this._el("main"));
    this._render();
    this._timer = setInterval(() => {
      this._maybeFetchHistory();
      this._scheduleRender();
    }, TICK_MS);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onClick);
    this.shadowRoot.removeEventListener("keydown", this._onKey);
    if (this._ro) this._ro.disconnect();
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
  }

  // ---- shell -------------------------------------------------------------

  _build() {
    if (this._built) return;
    this._built = true;
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="${VENDOR}tokens.scoped.css">
      <link rel="stylesheet" href="${VENDOR}overlay.css">
      <link rel="stylesheet" id="panel-css" href="${PANEL_CSS}">
      <div class="sg-scope root" data-theme="light">
        <div class="wrap">
          <header id="hd"></header>
          <div id="measures"></div>
          <div class="tabs" id="tabs" role="tablist" aria-label="SolarBalance"></div>
          <main id="main" role="tabpanel" tabindex="-1"></main>
        </div>
        <dialog id="dlg" aria-labelledby="dlg-msg">
          <p id="dlg-msg"></p>
          <input id="dlg-input" type="text" hidden>
          <div class="btn-row">
            <button type="button" class="btn" data-dlg="cancel"></button>
            <button type="button" class="btn primary" data-dlg="ok"></button>
          </div>
        </dialog>
      </div>`;
    const css = this._el("panel-css");
    const ready = () => this._el("root", ".root").classList.add("ready");
    css.addEventListener("load", ready);
    setTimeout(ready, 1500);
  }

  _el(id, selector) {
    return this.shadowRoot.querySelector(selector || `#${id}`);
  }

  _measure() {
    // Charts are drawn at the real pixel width of the card that holds them.
    const probe = this.shadowRoot.querySelector("main .chart-card") || this._el("main");
    const w = probe.getBoundingClientRect().width;
    if (!w) return;
    // Card padding on each side; quantised so a scrollbar appearing does not re-render.
    const cw = Math.max(280, Math.floor((w - 32) / 8) * 8);
    if (cw !== this.st.cw) {
      this.st.cw = cw;
      this._scheduleRender();
    }
  }

  _syncMenu() {
    const slot = this.shadowRoot && this.shadowRoot.querySelector("#menu");
    if (!slot) return;
    const btn = slot.firstElementChild;
    if (btn) {
      btn.hass = this._hass;
      btn.narrow = this._narrow;
    }
  }

  _scheduleRender() {
    if (this._pending) return;
    this._pending = true;
    setTimeout(() => {
      this._pending = false;
      this._render();
    }, RENDER_DEBOUNCE_MS);
  }

  /** Replace a container's HTML only when it changed, keeping keyboard focus on the same control. */
  _set(id, html) {
    if (this._cache[id] === html) return;
    const el = this._el(id);
    if (!el) return;
    const active = this.shadowRoot.activeElement;
    let key = null;
    if (active && el.contains(active)) {
      key = [...active.attributes]
        .filter((a) => a.name.startsWith("data-"))
        .map((a) => `${a.name}=${a.value}`)
        .join("|");
    }
    el.innerHTML = html;
    this._cache[id] = html;
    if (key) {
      const next = [...el.querySelectorAll("button, input")].find(
        (n) =>
          [...n.attributes]
            .filter((a) => a.name.startsWith("data-"))
            .map((a) => `${a.name}=${a.value}`)
            .join("|") === key
      );
      if (next) next.focus();
    }
  }

  _applyTheme() {
    const root = this._el("root", ".root");
    const dark = !!(this._hass && this._hass.themes && this._hass.themes.darkMode);
    root.dataset.theme = this.st.contrast ? "contrast" : dark ? "dark" : "light";
  }

  // ---- render ------------------------------------------------------------

  _render() {
    if (!this._built) return;
    this._applyTheme();
    if (!this._hass) {
      this._set("main", `<p class="empty" role="status">Chargement…</p>`);
      return;
    }
    const m = this.m;
    this._set("hd", this._header(m));
    this._set("measures", this._measures(m));
    this._set("tabs", this._tabs(m));
    const tab = TABS.find((t) => t.id === this.st.tab) || TABS[0];
    const main = this._el("main");
    main.setAttribute("aria-labelledby", `tab-${tab.id}`);
    this._set("main", tab.render(m, this.st));
    this._measure();
    this._ensureMenu();
  }

  _ensureMenu() {
    const slot = this.shadowRoot.querySelector("#menu");
    if (!slot || slot.firstElementChild || !customElements.get("ha-menu-button")) return;
    slot.appendChild(document.createElement("ha-menu-button"));
    this._syncMenu();
  }

  _freshness(m) {
    const s = m.stateObj(m.E.grid);
    const lu = s && (s.last_reported || s.last_updated || s.last_changed);
    if (!lu) return "";
    const ago = Math.max(0, Math.round((Date.now() - Date.parse(lu)) / 1000));
    const stale = ago > 120;
    const state = stale ? "attention" : "ok";
    const when = m.isEnglish ? `${fmtDuration(ago)} ago` : `il y a ${fmtDuration(ago)}`;
    const text = stale ? `${m.t("Données anciennes")} : ${when}` : `${m.t("À jour")}, ${when}`;
    return `<span class="fresh st-${state}" role="status">${icon(state, 14)}<span class="t">${esc(text)}</span></span>`;
  }

  _header(m) {
    const mode = m.state(m.E.mode);
    const [state, label] = modeState(mode);
    const reason = m.attr(m.E.mode, "reason");
    const strat = m.state(m.E.strat);
    const contrast = this.st.contrast;
    return `
      <div class="hrow">
        <span id="menu"></span>
        <h1>SolarBalance</h1>
        ${stamp(state, m.t(label))}
        <span class="hspace"></span>
        ${this._freshness(m)}
        <button type="button" class="btn small" data-contrast="1" aria-pressed="${contrast}">${m.t("Contraste élevé")}</button>
      </div>
      ${strat ? `<p class="strat">${m.t("Stratégie")} : ${esc(strat)}</p>` : ""}
      ${reason ? `<p class="reason">${esc(reason)}</p>` : ""}`;
  }

  _measures(m) {
    const E = m.E;
    const lang = m.lang;
    const power = (label, id, note) =>
      m.exists(id) ? tile(m.t(label), measureOf(fmtPower(m.num(id), lang)), note) : "";
    const grid = m.num(E.grid);
    const batt = m.num(E.battery);
    const gridNote = grid == null ? "" : grid > 20 ? m.t("Soutirage") : grid < -20 ? m.t("Injection") : "";
    const battNote = batt == null ? "" : batt > 20 ? m.t("Charge") : batt < -20 ? m.t("Décharge") : "";
    const parts = [
      power("Solaire", E.pv, ""),
      power("Réseau", E.grid, gridNote),
      power("Batteries", E.battery, battNote),
      power("Maison", E.home, ""),
      m.exists(E.soc) ? tile(m.t("Niveau moyen"), measureOf(m.fmt(E.soc, 0, "%"))) : "",
    ].join("");
    return parts ? `<div class="measures" role="group" aria-label="${esc(m.t("Mesures en direct"))}">${parts}</div>` : "";
  }

  _tabs(m) {
    const h = healthSummary(m);
    return TABS.map((t) => {
      const sel = this.st.tab === t.id;
      const badge =
        t.id === "health" && h.count > 0
          ? `<span class="tab-badge st-${h.level}">${icon(h.level, 14)}${h.count}<span class="sr"> ${m.t("points d'attention")}</span></span>`
          : "";
      return `<button type="button" class="tab" role="tab" id="tab-${t.id}" data-tab="${t.id}" aria-selected="${sel}" aria-controls="main" tabindex="${sel ? 0 : -1}">${m.t(t.label)}${badge}</button>`;
    }).join("");
  }

  // ---- events ------------------------------------------------------------

  _selectTab(id, focus = false) {
    if (!TABS.some((t) => t.id === id)) return;
    this.st.tab = id;
    store("solarbalance.tab", id);
    this._render();
    if (focus) {
      const el = this._el("tabs").querySelector(`[data-tab="${id}"]`);
      if (el) el.focus();
    }
  }

  _onKey(ev) {
    const tab = ev.composedPath().find((n) => n.dataset && n.dataset.tab);
    if (!tab) return;
    const i = TABS.findIndex((t) => t.id === tab.dataset.tab);
    const move = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[ev.key];
    if (move === undefined) return;
    ev.preventDefault();
    this._selectTab(TABS[(move + TABS.length) % TABS.length].id, true);
  }

  async _onClick(ev) {
    const path = ev.composedPath();
    const find = (key) => path.find((n) => n.dataset && n.dataset[key] !== undefined);
    const hass = this._hass;

    const dlg = find("dlg");
    if (dlg && this._ask) {
      this._ask(dlg.dataset.dlg);
      return;
    }
    const tab = find("tab");
    if (tab) return this._selectTab(tab.dataset.tab);
    if (find("contrast")) {
      this.st.contrast = !this.st.contrast;
      store("solarbalance.contrast", this.st.contrast ? "1" : "0");
      this._render();
      return;
    }
    const toggle = find("toggle");
    if (toggle && hass) {
      hass.callService("switch", "toggle", { entity_id: toggle.dataset.toggle });
      return;
    }
    const svc = find("service");
    if (svc && hass) {
      let args = {};
      if (svc.dataset.args) {
        try {
          args = JSON.parse(svc.dataset.args);
        } catch (e) {
          args = {};
        }
      }
      if (svc.dataset.confirm && !(await this._dialog({ message: svc.dataset.confirm }))) return;
      hass.callService("solarbalance", svc.dataset.service, args);
      return;
    }
    if (find("toggleDebug")) {
      this.st.debugOpen = !this.st.debugOpen;
      this._render();
      return;
    }
    if (find("toggleRaw")) {
      this.st.showRaw = !this.st.showRaw;
      this._render();
      return;
    }
    const btn = find("h");
    if (!btn) return;
    const w = btn.dataset.h === "day" ? "day" : Number(btn.dataset.h);
    if (w && w !== this.st.window) {
      this.st.window = w;
      this._histTs = 0;
      this._maybeFetchHistory();
      this._render();
    }
  }

  /** In-page confirm / prompt. Resolves to true / false (confirm) or the typed text / null (prompt). */
  _dialog({ message, input = null }) {
    const dlg = this._el("dlg");
    const field = this._el("dlg-input");
    this._el("dlg-msg").textContent = message;
    dlg.querySelector('[data-dlg="cancel"]').textContent = this.m.t("Annuler");
    dlg.querySelector('[data-dlg="ok"]').textContent = this.m.t(input === null ? "Confirmer" : "Valider");
    field.hidden = input === null;
    field.value = input === null ? "" : input;
    return new Promise((resolve) => {
      const done = (answer) => {
        this._ask = null;
        dlg.removeEventListener("close", onClose);
        field.removeEventListener("keydown", onEnter);
        if (dlg.open) dlg.close();
        resolve(answer === "ok" ? (input === null ? true : field.value) : input === null ? false : null);
      };
      const onClose = () => done("cancel");
      const onEnter = (e) => {
        if (e.key === "Enter") done("ok");
      };
      this._ask = done;
      dlg.addEventListener("close", onClose);
      field.addEventListener("keydown", onEnter);
      dlg.showModal();
      if (input !== null) field.focus();
    });
  }

  // ---- data --------------------------------------------------------------

  _accumulateReg() {
    const m = this.m;
    const target = m.attr(m.E.regDebug, "target_w");
    const fleet = m.attr(m.E.regDebug, "current_fleet_w");
    if (target == null && fleet == null) return;
    const h = this.st.regHist;
    const last = h[h.length - 1];
    const now = Date.now();
    if (last && now - last.t < 2000) return;
    h.push({ t: now, target: Number(target) || 0, fleet: Number(fleet) || 0 });
    if (h.length > 180) h.shift();
  }

  _maybeFetchHistory() {
    const m = this.m;
    const now = Date.now();
    if (this._fetching) return;
    const st = this.st;
    if (st.series && st.series.window === st.window && now - this._histTs < HISTORY_REFRESH_MS) return;
    const socDevs = Object.values(m.devices()).filter((k) => k.soc);
    const ids = [m.E.pv, m.E.grid, m.E.battery, ...socDevs.map((k) => k.soc)].filter(Boolean);
    if (!this._hass || !ids.length) return;
    this._fetching = true;
    const startMs = st.window === "day" ? midnightMs() : now - st.window * 3600 * 1000;
    const win = st.window;
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
        const socByName = {};
        for (const k of socDevs) socByName[k.name] = parseSeries(res[k.soc]);
        st.series = {
          window: win,
          pv: parseSeries(res[m.E.pv]),
          grid: parseSeries(res[m.E.grid]),
          battery: parseSeries(res[m.E.battery]),
          socByName,
        };
        this._histTs = Date.now();
        this._fetching = false;
        this._render();
      })
      .catch(() => {
        this._fetching = false;
      });
  }
}

if (!customElements.get("solarbalance-panel")) {
  customElements.define("solarbalance-panel", SolarBalancePanel);
}
