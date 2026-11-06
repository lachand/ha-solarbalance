/**
 * Real-time energy-flow diagram: four labelled tags (solar, grid, batteries, home) joined
 * by links to the home. A flow is told by its hue (production / consumption / storage), a
 * stroke (solid, dashed, dotted), an arrowhead giving the direction, and a word under the
 * figure (« Soutirage », « Charge »...), never by colour alone.
 */

import { NBSP, esc, fmtNum, fmtPower, powerParts } from "../format.js";
import { icon } from "../ui.js";

const W = 480;
const H = 178;
const NODE_W = 124;
const NODE_H = 66;
const THRESHOLD_W = 20;

const FLOWS = {
  pv: { color: "var(--production)", dash: "", marker: "ah-pv" },
  grid: { color: "var(--consommation)", dash: "8 5", marker: "ah-grid" },
  batt: { color: "var(--stockage)", dash: "1.5 5", marker: "ah-batt", round: true },
};

function link(d, w, flow) {
  const a = Math.abs(w || 0);
  if (a < THRESHOLD_W) return `<path d="${d}" class="flow-off"/>`;
  const width = Math.max(2, Math.min(7, 2 + a / 400)).toFixed(1);
  const dur = Math.max(0.6, 2 - a / 1000).toFixed(2);
  const dash = flow.dash ? ` stroke-dasharray="${flow.dash}"` : "";
  const cap = flow.round ? ' stroke-linecap="round"' : "";
  // Paths are drawn outer node → home; w > 0 means "toward home", so the arrowhead sits at
  // the end, otherwise at the start.
  const toward = w > 0;
  const arrow = toward ? `marker-end="url(#${flow.marker})"` : `marker-start="url(#${flow.marker})"`;
  const anim = flow.dash ? ` class="flow-anim ${toward ? "in" : "out"}" style="animation-duration:${dur}s"` : "";
  return `<path d="${d}" fill="none" stroke="${flow.color}" stroke-width="${width}"${dash}${cap} ${arrow}${anim}/>`;
}

function node(cx, cy, ic, label, w, sub, color, lang) {
  const x = cx - NODE_W / 2;
  const y = cy - NODE_H / 2;
  const p = powerParts(w, lang);
  return `
    <g class="flow-node">
      <rect x="${x}" y="${y}" width="${NODE_W}" height="${NODE_H}" rx="2" class="fn-box"/>
      <rect x="${x}" y="${y}" width="3" height="${NODE_H}" fill="${color}"/>
      <g transform="translate(${x + 10} ${y + 10})" style="color:${color}">${icon(ic, 20)}</g>
      <text x="${x + 38}" y="${y + 20}" class="fn-lbl">${esc(label)}</text>
      <text x="${x + 38}" y="${y + 42}"><tspan class="fn-val">${esc(p.value)}</tspan><tspan class="fn-unit" dx="3">${p.unit}</tspan></text>
      <text x="${x + 38}" y="${y + 59}" class="fn-sub">${esc(sub)}</text>
    </g>`;
}

/** Flow figures from the panel's model (the card builds the same object from its own entities). */
export function flowFromModel(m) {
  return {
    pv: m.num(m.E.pv) || 0,
    grid: m.num(m.E.grid) || 0, // + import, − export
    batt: m.num(m.E.battery) || 0, // + charge, − discharge
    home: m.num(m.E.home) || 0,
    soc: m.num(m.E.soc),
    lang: m.lang,
    t: (s) => m.t(s),
  };
}

/**
 * Render the diagram. `d` = `{ pv, grid, batt, home, soc, lang, t }` in watts and percent;
 * `t` translates an in-source French label. Shared by the panel and the Lovelace card.
 */
export function flowDiagram(d) {
  const { pv, grid, batt, home, soc, lang, t } = d;

  const gridSub = grid > THRESHOLD_W ? "Soutirage" : grid < -THRESHOLD_W ? "Injection" : "Équilibre";
  const battState = batt > THRESHOLD_W ? "charge" : batt < -THRESHOLD_W ? "décharge" : "repos";
  const battSub = soc != null ? `${fmtNum(Math.round(soc), 0, lang)}${NBSP}% · ${t(battState)}` : t(battState);
  const pvSub = pv >= THRESHOLD_W ? "Production" : "Au repos";

  const cy = 141;
  const links =
    link("M240 68 L240 108", pv, FLOWS.pv) +
    link(`M126 ${cy} L178 ${cy}`, grid, FLOWS.grid) +
    link(`M354 ${cy} L302 ${cy}`, -batt, FLOWS.batt);

  const defs = Object.values(FLOWS)
    .map(
      (f) =>
        `<marker id="${f.marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${f.color}"/></marker>`
    )
    .join("");

  const aria =
    `${t("Flux d'énergie")} : ${t("solaire")} ${fmtPower(pv, lang)}, ` +
    `${t("réseau")} ${fmtPower(grid, lang)} (${t(gridSub).toLowerCase()}), ` +
    `${t("batteries")} ${fmtPower(batt, lang)} (${t(battState)}), ` +
    `${t("maison")} ${fmtPower(home, lang)}`;

  return `
    <svg viewBox="0 0 ${W} ${H}" class="flow" role="img" aria-label="${esc(aria)}">
      <defs>${defs}</defs>
      ${links}
      ${node(240, 35, "sun", t("Solaire"), pv, t(pvSub), "var(--production)", lang)}
      ${node(64, cy, "grid", t("Réseau"), grid, t(gridSub), "var(--consommation)", lang)}
      ${node(416, cy, "battery", t("Batteries"), batt, battSub, "var(--stockage)", lang)}
      ${node(240, cy, "home", t("Maison"), home, t("Consommation"), "var(--ink)", lang)}
    </svg>`;
}
