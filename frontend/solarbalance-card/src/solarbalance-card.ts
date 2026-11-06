/**
 * SolarBalance power-flow card, Signature design.
 *
 * Shares its diagram, stamps, measures and tokens with the full-page panel: the drawing
 * code is imported from `custom_components/solarbalance/www/panel/` (single source), the
 * Signature tokens and `panel.css` are loaded from the integration's static path.
 *
 * Configuration:
 *   type: custom:solarbalance-card
 *   title: "Tableau de bord solaire"        # optional
 *   contrast: false                          # optional, high-contrast theme
 *   # Entity overrides, all auto-detected by translation_key when omitted
 *   mode_entity:          sensor.solarbalance_mode
 *   strategy_entity:      sensor.solarbalance_dominant_strategy
 *   grid_power_entity:    sensor.solarbalance_grid_power
 *   pv_power_entity:      sensor.solarbalance_pv_power
 *   battery_power_entity: sensor.solarbalance_battery_power
 *   battery_soc_entity:   sensor.solarbalance_battery_soc_avg
 */

import { LitElement, css, html, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import { STR_EN } from "../../../custom_components/solarbalance/www/panel/i18n.js";
import { esc, fmtNum, fmtPower, withUnit } from "../../../custom_components/solarbalance/www/panel/format.js";
import { modeState } from "../../../custom_components/solarbalance/www/panel/mode.js";
import { flowDiagram } from "../../../custom_components/solarbalance/www/panel/svg/flow.js";
import { measureOf, meter, stamp, tile } from "../../../custom_components/solarbalance/www/panel/ui.js";
import type { HomeAssistant, HassEntity, LovelaceCardConfig } from "./types.js";

// ─── Config ────────────────────────────────────────────────────────────────

interface SolarBalanceCardConfig extends LovelaceCardConfig {
  title?: string;
  contrast?: boolean;
  mode_entity?: string;
  strategy_entity?: string;
  grid_power_entity?: string;
  pv_power_entity?: string;
  battery_power_entity?: string;
  battery_soc_entity?: string;
}

type EntityKey =
  | "mode_entity"
  | "strategy_entity"
  | "grid_power_entity"
  | "pv_power_entity"
  | "battery_power_entity"
  | "battery_soc_entity";

/** Config key → [translation_key, English default entity_id]. */
const ENTITIES: Record<EntityKey, [string, string]> = {
  mode_entity: ["mode", "sensor.solarbalance_mode"],
  strategy_entity: ["dominant_strategy", "sensor.solarbalance_dominant_strategy"],
  grid_power_entity: ["grid_power", "sensor.solarbalance_grid_power"],
  pv_power_entity: ["pv_power", "sensor.solarbalance_pv_power"],
  battery_power_entity: ["battery_power", "sensor.solarbalance_battery_power"],
  battery_soc_entity: ["battery_soc_avg", "sensor.solarbalance_battery_soc_avg"],
};

const STATIC_BASE = new URL(/* @vite-ignore */ "vendor/signature/", import.meta.url).href;
const PANEL_CSS = new URL(/* @vite-ignore */ "panel/panel.css", import.meta.url).href;

/** Strategy keys → French label. */
const STRATEGY_LABELS: Record<string, string> = {
  normal: "Normal",
  storm: "Tempête",
  vacation: "Vacances",
  self_consumption: "Autoconsommation",
  cost_min: "Coût minimal",
  revenue_max: "Revenu maximal",
  peak_shaving: "Écrêtage",
  backup: "Secours",
  longevity: "Longévité",
  manual_override: "Manuel",
  degraded: "Dégradé",
  paused: "En pause",
};

function numeric(entity: HassEntity | undefined): number | null {
  if (!entity || entity.state === "unavailable" || entity.state === "unknown") return null;
  const v = parseFloat(entity.state);
  return Number.isNaN(v) ? null : v;
}

/** @font-face is ignored inside a shadow root, so the fonts are declared once on the document. */
function ensureFonts(): void {
  if (document.getElementById("sb-signature-fonts")) return;
  const link = document.createElement("link");
  link.id = "sb-signature-fonts";
  link.rel = "stylesheet";
  link.href = `${STATIC_BASE}fonts.css`;
  document.head.appendChild(link);
}

// ─── Card element ────────────────────────────────────────────────────────────

export class SolarBalanceCard extends LitElement {
  @property({ attribute: false }) hass?: HomeAssistant;

  @state() private _config?: SolarBalanceCardConfig;
  @state() private _ready = false;

  static override styles = css`
    :host {
      display: block;
      background: none;
      min-height: 0;
    }
    .sbc-root {
      visibility: hidden;
      color: var(--ink);
      font-family: var(--font-ui);
    }
    .sbc-root.ready {
      visibility: visible;
    }
    .sbc-foot {
      margin-top: var(--space-3);
    }
  `;

  override connectedCallback(): void {
    super.connectedCallback();
    ensureFonts();
    // Fallback so a blocked stylesheet never leaves the card invisible.
    window.setTimeout(() => (this._ready = true), 1500);
  }

  setConfig(config: SolarBalanceCardConfig): void {
    this._config = config;
  }

  getCardSize(): number {
    return 5;
  }

  /** Resolve an entity: explicit config, then translation_key (localised ids), then default id. */
  private _entity(key: EntityKey): HassEntity | undefined {
    const hass = this.hass;
    if (!hass) return undefined;
    const configured = this._config?.[key];
    if (configured) return hass.states[configured];
    const [translationKey, fallback] = ENTITIES[key];
    for (const [eid, e] of Object.entries(hass.entities ?? {})) {
      if (e.platform === "solarbalance" && e.translation_key === translationKey) return hass.states[eid];
    }
    return hass.states[fallback];
  }

  override render(): TemplateResult {
    if (!this._config || !this.hass) return html``;
    const hass = this.hass;
    const lang = hass.locale?.language || hass.language || "fr";
    const english = lang.startsWith("en");
    const t = (s: string): string => (english ? (STR_EN[s as keyof typeof STR_EN] ?? s) : s);

    const modeEntity = this._entity("mode_entity");
    const strategy = this._entity("strategy_entity")?.state ?? "";
    const gridW = numeric(this._entity("grid_power_entity"));
    const pvW = numeric(this._entity("pv_power_entity"));
    const batW = numeric(this._entity("battery_power_entity"));
    const soc = numeric(this._entity("battery_soc_entity"));

    // Home load = PV + grid (+ import, − export) − battery (+ charge, − discharge).
    const home = Math.max(0, (pvW ?? 0) + (gridW ?? 0) - (batW ?? 0));
    const [modeSt, modeLabel] = modeState(modeEntity?.state);
    const theme = this._config.contrast ? "contrast" : hass.themes?.darkMode ? "dark" : "light";
    const title = this._config.title ?? "SolarBalance";

    const power = (label: string, w: number | null, note = ""): string =>
      w == null ? "" : tile(t(label), measureOf(fmtPower(w, lang)), note);
    const gridNote = gridW == null ? "" : gridW > 20 ? t("Soutirage") : gridW < -20 ? t("Injection") : "";
    const battNote = batW == null ? "" : batW > 20 ? t("Charge") : batW < -20 ? t("Décharge") : "";

    const socTile =
      soc == null
        ? ""
        : `<div class="tile"><div class="tl">${esc(t("Niveau moyen"))}</div>${measureOf(
            withUnit(fmtNum(Math.round(soc), 0, lang), "%"),
          )}</div>`;

    const body = `
      <div class="card-h"><h3 class="cote-rule">${esc(title)}</h3>${stamp(modeSt, t(modeLabel))}</div>
      ${flowDiagram({ pv: pvW ?? 0, grid: gridW ?? 0, batt: batW ?? 0, home, soc, lang, t })}
      <div class="tiles sbc-foot">
        ${power("Solaire", pvW)}${power("Réseau", gridW, gridNote)}${power("Batteries", batW, battNote)}${socTile}
      </div>
      ${soc == null ? "" : `<div class="sbc-foot">${meter(soc, t("Niveau de charge"))}</div>`}
      ${strategy ? `<p class="note">${esc(t("Stratégie"))} : ${esc(STRATEGY_LABELS[strategy] ?? strategy)}</p>` : ""}`;

    return html`
      <link rel="stylesheet" href="${STATIC_BASE}tokens.scoped.css" />
      <link rel="stylesheet" href="${STATIC_BASE}overlay.css" />
      <link
        rel="stylesheet"
        href="${PANEL_CSS}"
        @load=${() => (this._ready = true)}
      />
      <div class="sg-scope sbc-root ${this._ready ? "ready" : ""}" data-theme="${theme}">
        <section class="card">${unsafeHTML(body)}</section>
      </div>
    `;
  }
}

// A manual `extra_module_url` entry next to the integration's own registration loads this
// module twice; defining the element a second time would throw.
if (!customElements.get("solarbalance-card")) {
  customElements.define("solarbalance-card", SolarBalanceCard);
  // Register for Lovelace card picker
  window.customCards = window.customCards ?? [];
  window.customCards.push({
    type: "solarbalance-card",
    name: "SolarBalance",
    description:
      "Flux d'énergie en temps réel (solaire, batteries, réseau, maison) et état du pilotage.",
    preview: true,
  });
}
