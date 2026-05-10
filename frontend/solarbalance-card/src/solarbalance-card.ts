/**
 * SolarBalance Sankey power-flow card.
 *
 * Renders a real-time energy flow diagram:
 *   PV  ──►  Battery
 *        ├──►  Home load
 *        └──►  Grid (export)
 *   Grid ──►  Home load (import)
 *
 * Configuration:
 *   type: custom:solarbalance-card
 *   title: "Tableau de bord solaire"        # optional
 *   # Entity overrides — all have auto-detected defaults
 *   mode_entity:          sensor.solarbalance_mode
 *   strategy_entity:      sensor.solarbalance_dominant_strategy
 *   grid_power_entity:    sensor.solarbalance_grid_power
 *   pv_power_entity:      sensor.solarbalance_pv_power
 *   battery_power_entity: sensor.solarbalance_battery_power
 *   battery_soc_entity:   sensor.solarbalance_battery_soc_avg
 */

import { LitElement, html, css, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  LovelaceCardConfig,
  HassEntity,
} from "./types.js";

// ─── Config ────────────────────────────────────────────────────────────────

interface SolarBalanceCardConfig extends LovelaceCardConfig {
  title?: string;
  mode_entity?: string;
  strategy_entity?: string;
  grid_power_entity?: string;
  pv_power_entity?: string;
  battery_power_entity?: string;
  battery_soc_entity?: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function numericState(entity: HassEntity | undefined): number {
  if (!entity) return 0;
  const v = parseFloat(entity.state);
  return isNaN(v) ? 0 : v;
}

function fmtW(watts: number): string {
  const abs = Math.abs(watts);
  if (abs >= 1000) return `${(watts / 1000).toFixed(2)} kW`;
  return `${watts.toFixed(0)} W`;
}

/** Map HEMS mode key to a display label. */
function modeLabel(mode: string): string {
  const MAP: Record<string, string> = {
    self_consumption: "Auto-conso",
    cost_min: "Coût min",
    revenue_max: "Revenu max",
    peak_shaving: "Écrêtage",
    backup: "Secours",
    longevity: "Longévité",
    manual_override: "Manuel",
    degraded: "Dégradé",
    paused: "Pause",
  };
  return MAP[mode] ?? mode;
}

// ─── Sankey geometry ────────────────────────────────────────────────────────

interface FlowLink {
  from: string;
  to: string;
  value: number; // absolute watts
}

interface FlowNode {
  id: string;
  label: string;
  x: number;
  y: number;
}

const NODE_W = 90;
const NODE_H = 44;

/** Compute SVG Sankey nodes + links from raw power readings.
 *
 * Sign conventions (internal SolarBalance pdl convention):
 *   grid_power_w > 0 → import (soutirage)
 *   battery_power_w > 0 → charging
 *   pv_power_w ≥ 0 always
 */
function buildSankey(
  pvW: number,
  gridW: number,
  batW: number
): { nodes: FlowNode[]; links: FlowLink[] } {
  // Derived values
  const pvAvail = Math.max(0, pvW);
  const gridImport = Math.max(0, gridW);
  const gridExport = Math.max(0, -gridW);
  const batCharge = Math.max(0, batW);
  const batDischarge = Math.max(0, -batW);

  // Home load = PV + grid import + bat discharge − bat charge − grid export
  const homeLoad = Math.max(
    0,
    pvAvail + gridImport + batDischarge - batCharge - gridExport
  );

  const nodes: FlowNode[] = [
    { id: "pv", label: "Solaire", x: 20, y: 20 },
    { id: "battery", label: "Batterie", x: 200, y: 130 },
    { id: "home", label: "Maison", x: 380, y: 20 },
    { id: "grid", label: "Réseau", x: 200, y: 20 },
  ];

  const links: FlowLink[] = [];
  if (pvAvail > 0 && homeLoad > 0)
    links.push({ from: "pv", to: "home", value: Math.min(pvAvail, homeLoad) });
  if (pvAvail > 0 && batCharge > 0)
    links.push({ from: "pv", to: "battery", value: batCharge });
  if (pvAvail > 0 && gridExport > 0)
    links.push({ from: "pv", to: "grid", value: gridExport });
  if (gridImport > 0)
    links.push({ from: "grid", to: "home", value: gridImport });
  if (batDischarge > 0)
    links.push({ from: "battery", to: "home", value: batDischarge });

  return { nodes, links };
}

/** Render a simple cubic Bezier between node centres. */
function linkPath(
  from: FlowNode,
  to: FlowNode,
  thickness: number
): TemplateResult {
  const x1 = from.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_H / 2;
  const mx = (x1 + x2) / 2;
  const color =
    from.id === "grid"
      ? "var(--warning-color, #ff9800)"
      : from.id === "battery"
        ? "var(--info-color, #03a9f4)"
        : "var(--success-color, #4caf50)";
  return html`<path
    d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"
    fill="none"
    stroke="${color}"
    stroke-width="${Math.max(2, thickness)}"
    stroke-opacity="0.7"
  />`;
}

// ─── Card element ────────────────────────────────────────────────────────────

@customElement("solarbalance-card")
export class SolarBalanceCard extends LitElement {
  @property({ attribute: false }) hass?: HomeAssistant;

  @state() private _config?: SolarBalanceCardConfig;

  static override styles = css`
    :host {
      display: block;
    }
    ha-card {
      padding: 16px;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .title {
      font-size: 1.1em;
      font-weight: 600;
    }
    .mode-badge {
      font-size: 0.8em;
      padding: 2px 8px;
      border-radius: 12px;
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .mode-badge.degraded {
      background: var(--error-color, #f44336);
    }
    .mode-badge.paused {
      background: var(--disabled-color, #9e9e9e);
    }
    .sankey-svg {
      width: 100%;
      height: 220px;
    }
    .node-rect {
      rx: 6;
      ry: 6;
    }
    .node-label {
      font-size: 11px;
      fill: var(--primary-text-color);
      text-anchor: middle;
      dominant-baseline: middle;
    }
    .node-value {
      font-size: 10px;
      fill: var(--secondary-text-color);
      text-anchor: middle;
      dominant-baseline: middle;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px;
      margin-top: 12px;
    }
    .metric {
      text-align: center;
      padding: 8px;
      border-radius: 8px;
      background: var(--secondary-background-color);
    }
    .metric-label {
      font-size: 0.75em;
      color: var(--secondary-text-color);
    }
    .metric-value {
      font-size: 1em;
      font-weight: 600;
      margin-top: 2px;
    }
    .metric-value.positive {
      color: var(--success-color, #4caf50);
    }
    .metric-value.negative {
      color: var(--warning-color, #ff9800);
    }
    .soc-bar-bg {
      height: 6px;
      border-radius: 3px;
      background: var(--divider-color);
      margin-top: 4px;
      overflow: hidden;
    }
    .soc-bar-fill {
      height: 100%;
      border-radius: 3px;
      background: var(--info-color, #03a9f4);
      transition: width 0.4s ease;
    }
  `;

  setConfig(config: SolarBalanceCardConfig): void {
    this._config = config;
  }

  getCardSize(): number {
    return 4;
  }

  private _entity(key: keyof SolarBalanceCardConfig, fallback: string): HassEntity | undefined {
    const id = (this._config?.[key] as string | undefined) ?? fallback;
    return this.hass?.states[id];
  }

  override render(): TemplateResult {
    if (!this._config || !this.hass) return html``;

    const modeEntity = this._entity("mode_entity", "sensor.solarbalance_mode");
    const strategyEntity = this._entity("strategy_entity", "sensor.solarbalance_dominant_strategy");
    const gridEntity = this._entity("grid_power_entity", "sensor.solarbalance_grid_power");
    const pvEntity = this._entity("pv_power_entity", "sensor.solarbalance_pv_power");
    const batEntity = this._entity("battery_power_entity", "sensor.solarbalance_battery_power");
    const socEntity = this._entity("battery_soc_entity", "sensor.solarbalance_battery_soc_avg");

    const mode = modeEntity?.state ?? "unknown";
    const strategy = strategyEntity?.state ?? "";
    const gridW = numericState(gridEntity);
    const pvW = numericState(pvEntity);
    const batW = numericState(batEntity);
    const soc = numericState(socEntity);

    const { nodes, links } = buildSankey(pvW, gridW, batW);

    const maxFlow = Math.max(1, ...links.map((l) => l.value));
    const scale = (v: number) => (v / maxFlow) * 14 + 2;

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    const title = this._config.title ?? "SolarBalance";

    return html`
      <ha-card>
        <div class="header">
          <span class="title">${title}</span>
          <span class="mode-badge ${mode}">${modeLabel(mode)}</span>
        </div>

        <svg
          class="sankey-svg"
          viewBox="0 0 520 200"
          preserveAspectRatio="xMidYMid meet"
        >
          ${links.map((link) => {
            const fromN = nodeMap.get(link.from);
            const toN = nodeMap.get(link.to);
            if (!fromN || !toN) return nothing;
            return linkPath(fromN, toN, scale(link.value));
          })}
          ${nodes.map(
            (n) => html`
              <rect
                class="node-rect"
                x="${n.x}"
                y="${n.y}"
                width="${NODE_W}"
                height="${NODE_H}"
                fill="var(--card-background-color)"
                stroke="var(--divider-color)"
                stroke-width="1.5"
                rx="6"
                ry="6"
              />
              <text class="node-label" x="${n.x + NODE_W / 2}" y="${n.y + 14}">
                ${n.label}
              </text>
              <text
                class="node-value"
                x="${n.x + NODE_W / 2}"
                y="${n.y + 30}"
              >
                ${n.id === "pv"
                  ? fmtW(pvW)
                  : n.id === "grid"
                    ? fmtW(Math.abs(gridW))
                    : n.id === "battery"
                      ? fmtW(Math.abs(batW))
                      : fmtW(
                          Math.max(0, pvW + Math.max(0, -gridW) + Math.max(0, -batW))
                        )}
              </text>
            `
          )}
        </svg>

        <div class="metrics">
          <div class="metric">
            <div class="metric-label">Solaire</div>
            <div class="metric-value positive">${fmtW(pvW)}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Réseau</div>
            <div class="metric-value ${gridW > 0 ? "negative" : "positive"}">
              ${gridW > 0 ? "+" : ""}${fmtW(gridW)}
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">Batterie</div>
            <div class="metric-value ${batW < 0 ? "positive" : "negative"}">
              ${batW >= 0 ? "Charge" : "Décharge"} ${fmtW(Math.abs(batW))}
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">SoC batterie</div>
            <div class="metric-value">${soc.toFixed(0)} %</div>
            <div class="soc-bar-bg">
              <div
                class="soc-bar-fill"
                style="width: ${Math.min(100, soc).toFixed(0)}%"
              ></div>
            </div>
          </div>
          ${strategy
            ? html`<div class="metric">
                <div class="metric-label">Stratégie</div>
                <div class="metric-value">${modeLabel(strategy)}</div>
              </div>`
            : nothing}
        </div>
      </ha-card>
    `;
  }
}

// Register for Lovelace card picker
window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "solarbalance-card",
  name: "SolarBalance Card",
  description: "Flux d'énergie temps réel (solaire / batterie / réseau / maison) avec indicateurs HEMS.",
  preview: true,
});
