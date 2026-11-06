/**
 * Small HTML building blocks in the Signature vocabulary: stamps (state = colour + shape +
 * label), measures (monospace figure, unit on the right), cote-rule section headers,
 * meters and buttons. Every function returns an HTML string.
 */

import { esc } from "./format.js";

const ICONS = {
  ok: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  attention: '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  critique: '<path d="M8.5 3h7L21 8.5v7L15.5 21h-7L3 15.5v-7z"/><path d="M12 8v5M12 16v.1"/>',
  inactif: '<circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
  grid: '<path d="M12 2.5l-5 19M12 2.5l5 19M8.2 13h7.6M9.6 8h4.8M6.5 21.5h11"/>',
  battery: '<rect x="3" y="7" width="16" height="10" rx="1"/><path d="M21 10.5v3M7 10.5v3M11 10.5v3"/>',
  home: '<path d="M3.5 11.5L12 4l8.5 7.5M6 10v10h12V10"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  play: '<path d="M7 5l11 7-11 7z"/>',
  bolt: '<path d="M13 2.5L5 13.5h6l-1 8 8-11h-6z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  edit: '<path d="M4 20l1-4L16 5l3 3L8 19z"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>',
  storm:
    '<path d="M7 16a4.5 4.5 0 01-.5-9A6 6 0 0118 8.5 3.8 3.8 0 0117.5 16"/><path d="M12.5 12l-2.5 4h3l-1.5 4"/>',
  plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0zM12 17v4"/>',
};

/** Inline SVG icon (decorative: hidden from assistive technology). */
export function icon(name, size = 16) {
  return `<svg class="ic" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

const STATE_ICON = {
  ok: "ok",
  attention: "attention",
  critique: "critique",
  inactif: "inactif",
  info: "info",
};

/** Double-rule stamp: colour + icon of its own shape + a one- or two-word label. */
export function stamp(state, label, title = "") {
  const t = title ? ` title="${esc(title)}"` : "";
  return `<span class="sg-stamp st-${state}" role="status"${t}>${icon(STATE_ICON[state], 14)}<span>${esc(label)}</span></span>`;
}

/** Measure: the figure in monospace, the unit to its right in muted ink. */
export function measure(value, unit = "", cls = "") {
  const u = unit ? `<span class="mu">${esc(unit)}</span>` : "";
  return `<span class="mesure ${cls}"><span class="mv">${value}</span>${u}</span>`;
}

/** Split a "1,25 kW" style string produced by `withUnit` back into figure and unit. */
export function measureOf(text, cls = "") {
  const s = String(text);
  const i = s.indexOf(" ");
  if (i < 0) return measure(esc(s), "", cls);
  return measure(esc(s.slice(0, i)), s.slice(i + 1), cls);
}

/** Labelled measure tile. */
export function tile(label, measureHtml, note = "") {
  const n = note ? `<div class="tn">${esc(note)}</div>` : "";
  return `<div class="tile"><div class="tl">${esc(label)}</div>${measureHtml}${n}</div>`;
}

/** Label / value row inside a card. */
export function row(label, valueHtml) {
  return `<div class="row"><span class="rl">${esc(label)}</span><span class="rv">${valueHtml}</span></div>`;
}

/** Card with a cote-rule title (a rule with two end ticks) and optional header actions. */
export function card(title, body, { cls = "", actions = "", id = "" } = {}) {
  const i = id ? ` id="${id}"` : "";
  return `<section class="card ${cls}"${i}><div class="card-h"><h3 class="cote-rule">${esc(title)}</h3>${actions}</div>${body}</section>`;
}

/** Horizontal meter on a sunken track; `tick` (0-100) marks a threshold such as a SoC floor. */
export function meter(pct, label, { tick = null, tone = "" } = {}) {
  const p = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  const t = tick != null ? `<span class="bar-tick" style="left:${tick}%"></span>` : "";
  const now = pct == null ? "" : ` aria-valuenow="${Math.round(p)}"`;
  return `<div class="bar ${tone}" role="meter" aria-valuemin="0" aria-valuemax="100"${now} aria-label="${esc(label)}"><span class="bar-fill" style="width:${p}%"></span>${t}</div>`;
}

/**
 * Button. `data` entries become `data-*` attributes read by the panel's click handler.
 * `kind`: "" (neutral), "primary" (the one accent action), "toggle" (use with `pressed`).
 */
export function button(label, { ic = "", data = {}, kind = "", pressed = null, title = "" } = {}) {
  const attrs = Object.entries(data)
    .map(([k, v]) => ` data-${k}="${esc(v)}"`)
    .join("");
  const press = pressed == null ? "" : ` aria-pressed="${pressed ? "true" : "false"}"`;
  const tt = title ? ` title="${esc(title)}"` : "";
  return `<button type="button" class="btn ${kind}"${attrs}${press}${tt}>${ic ? icon(ic, 16) : ""}<span>${esc(label)}</span></button>`;
}

/** Empty state line in the instrument voice. */
export function empty(text) {
  return `<p class="empty">${esc(text)}</p>`;
}
