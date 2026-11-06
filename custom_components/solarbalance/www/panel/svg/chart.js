/**
 * SVG charts. Series are told apart by colour AND stroke (solid, dashed, dotted) AND an
 * end marker, never by hue alone. Charts render at their real pixel width (no
 * `preserveAspectRatio="none"`), so text and strokes are never stretched.
 */

import { FUTURE_CAP_H, deglitch, midnightMs } from "../history.js";
import { NBSP, clock, esc, fmtNum, fmtPower, hourLabel } from "../format.js";

const f = (n) => n.toFixed(1);

/** Stroke vocabulary shared by chart lines and their legend swatches. */
export const STROKE = {
  pv: { color: "var(--production)", dash: "", marker: "circle", w: 2 },
  grid: { color: "var(--consommation)", dash: "7 4", marker: "square", w: 2 },
  batt: { color: "var(--stockage)", dash: "1.5 4.5", marker: "diamond", w: 2.6, round: true },
  fc: { color: "var(--production)", dash: "10 3 2 3", marker: "", w: 1.5 },
};

function markerPath(shape, x, y, r = 4.5) {
  if (shape === "circle") return `M${f(x - r)} ${f(y)}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
  if (shape === "square") return `M${f(x - r + 0.5)} ${f(y - r + 0.5)}h${2 * r - 1}v${2 * r - 1}h${-(2 * r - 1)}z`;
  if (shape === "diamond") return `M${f(x)} ${f(y - r - 1)}L${f(x + r + 1)} ${f(y)}L${f(x)} ${f(y + r + 1)}L${f(x - r - 1)} ${f(y)}Z`;
  if (shape === "triangle") return `M${f(x)} ${f(y - r)}L${f(x + r)} ${f(y + r - 1)}L${f(x - r)} ${f(y + r - 1)}Z`;
  if (shape === "cross") return `M${f(x - r)} ${f(y - r)}L${f(x + r)} ${f(y + r)}M${f(x + r)} ${f(y - r)}L${f(x - r)} ${f(y + r)}`;
  return "";
}

function marker(shape, x, y, color) {
  if (!shape) return "";
  const d = markerPath(shape, x, y);
  if (shape === "cross")
    return `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`;
  return `<path d="${d}" fill="var(--surface)" stroke="${color}" stroke-width="2"/>`;
}

function linePath(pts, x, y) {
  return pts.map((p, i) => (i ? "L" : "M") + f(x(p.t)) + " " + f(y(p.v))).join(" ");
}

/** Legend swatch drawing the exact stroke and marker of a series. */
export function swatch(style) {
  const dash = style.dash ? ` stroke-dasharray="${style.dash}"` : "";
  const cap = style.round ? ' stroke-linecap="round"' : "";
  return `<svg class="sw" width="34" height="14" viewBox="0 0 34 14" aria-hidden="true"><path d="M1 7H33" stroke="${style.color}" stroke-width="${style.w}" fill="none"${dash}${cap}/>${marker(style.marker, 17, 7, style.color)}</svg>`;
}

function legendItem(style, label) {
  return `<span class="lg">${swatch(style)}${esc(label)}</span>`;
}

/** Round the scale to a 1-2-5 step so the axis reads 0, 1 000, 2 000 rather than 776, 2 217. */
function niceScale(vMin, vMax, n = 4) {
  const span = vMax - vMin || 1;
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const lo = Math.floor(vMin / step) * step;
  const hi = Math.ceil(vMax / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 1000; v += step) ticks.push(v);
  return { lo, hi, ticks };
}

function yGrid(y, ticks, padL, W, padR, fmt) {
  return ticks
    .map((v) => {
      const yy = y(v);
      return (
        `<line x1="${padL}" y1="${f(yy)}" x2="${W - padR}" y2="${f(yy)}" class="gl"/>` +
        `<text x="${padL - 6}" y="${f(yy + 3.5)}" class="ylbl" text-anchor="end">${fmt(v)}</text>`
      );
    })
    .join("");
}

function windowBounds(st, now) {
  const dayMode = st.window === "day";
  return {
    tMin: dayMode ? midnightMs() : now - st.window * 3600 * 1000,
    tMax: dayMode ? midnightMs() + 24 * 3600 * 1000 : now,
  };
}

function windowLabel(m, st) {
  return st.window === "day" ? m.t("aujourd'hui") : `${st.window}${NBSP}h`;
}

function forecastSeries(m, st, now) {
  const fc = m.attr(m.E.pv, "pv_forecast_hourly");
  if (!Array.isArray(fc)) return [];
  const cap =
    st.window === "day"
      ? midnightMs() + 24 * 3600 * 1000
      : now + Math.min(st.window, FUTURE_CAP_H) * 3600 * 1000;
  const out = [];
  for (const p of fc) {
    const t = Date.parse(p.start);
    const v = Number(p.w);
    if (Number.isNaN(t) || Number.isNaN(v) || t > cap) continue;
    out.push({ t, v });
  }
  return out.sort((a, b) => a.t - b.t);
}

/** Power chart: PV area + grid and battery lines, PV forecast overlay, hidden-spike marks. */
export function powerChart(m, st) {
  const s = st.series;
  if (!s || (!s.pv.length && !s.grid.length)) {
    return `<p class="empty" role="status">${m.t("Chargement de l'historique")}</p>`;
  }
  const now = Date.now();
  const fc = forecastSeries(m, st, now);
  const W = Math.max(280, st.cw - 2);
  const H = W < 520 ? 200 : 250;
  const padL = 50;
  const padR = 14;
  const padT = 20;
  const padB = 26;
  const dg = (arr) => (st.showRaw ? { clean: arr, glitches: [] } : deglitch(arr));
  const pvS = dg(s.pv);
  const gridS = dg(s.grid);
  const battS = dg(s.battery);
  const glitches = [...gridS.glitches, ...battS.glitches, ...pvS.glitches];
  const all = [...pvS.clean, ...gridS.clean, ...battS.clean, ...fc];
  let { tMin, tMax } = windowBounds(st, now);
  let vMin = 0;
  let vMax = 0;
  for (const p of all) {
    if (p.t < tMin) tMin = p.t;
    if (p.t > tMax) tMax = p.t;
    if (p.v < vMin) vMin = p.v;
    if (p.v > vMax) vMax = p.v;
  }
  if (tMax <= tMin) return `<p class="empty">${m.t("Aucune donnée sur la période.")}</p>`;
  if (vMax === vMin) vMax = vMin + 1;
  const scale = niceScale(vMin, vMax);
  vMin = scale.lo;
  vMax = scale.hi;

  const x = (t) => padL + ((t - tMin) / (tMax - tMin)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - vMin) / (vMax - vMin)) * (H - padT - padB);
  const y0 = y(0);

  const area = pvS.clean.length
    ? `M${f(x(pvS.clean[0].t))} ${f(y0)} ` +
      pvS.clean.map((p) => `L${f(x(p.t))} ${f(y(p.v))}`).join(" ") +
      ` L${f(x(pvS.clean[pvS.clean.length - 1].t))} ${f(y0)}Z`
    : "";
  const zero =
    vMin < 0 && vMax > 0
      ? `<line x1="${padL}" y1="${f(y0)}" x2="${W - padR}" y2="${f(y0)}" class="zero"/>`
      : "";
  const nowLine = fc.length
    ? `<line x1="${f(x(now))}" y1="${padT}" x2="${f(x(now))}" y2="${H - padB}" class="nowline"/>` +
      `<text x="${f(x(now) + 4)}" y="${padT + 9}" class="xlbl">${m.t("maintenant")}</text>`
    : "";
  const xl = [tMin, (tMin + tMax) / 2, tMax]
    .map(
      (t, i) =>
        `<text x="${f(x(t))}" y="${H - 7}" class="xlbl" text-anchor="${i === 0 ? "start" : i === 2 ? "end" : "middle"}">${clock(t)}</text>`
    )
    .join("");

  const line = (pts, st_) => {
    if (!pts.length) return "";
    const dash = st_.dash ? ` stroke-dasharray="${st_.dash}"` : "";
    const cap = st_.round ? ' stroke-linecap="round"' : "";
    const last = pts[pts.length - 1];
    return (
      `<path d="${linePath(pts, x, y)}" fill="none" stroke="${st_.color}" stroke-width="${st_.w}" stroke-linejoin="round"${dash}${cap}/>` +
      marker(st_.marker, x(last.t), y(last.v), st_.color)
    );
  };

  const marks = glitches
    .filter((g) => g.t >= tMin && g.t <= tMax)
    .map(
      (g) =>
        `<path d="${markerPath("diamond", x(g.t), y(g.cy), 3.5)}" class="glitch-mark"><title>${m.t("Pic capteur masqué")} : ${fmtNum(Math.round(g.v), 0, m.lang)}${NBSP}W, ${clock(g.t)}</title></path>`
    )
    .join("");

  const lastOf = (a) => (a.length ? a[a.length - 1].v : null);
  const aria =
    `${m.t("Puissance")} ${windowLabel(m, st)} : ` +
    `${m.t("solaire")} ${fmtPower(lastOf(pvS.clean), m.lang)}, ` +
    `${m.t("réseau")} ${fmtPower(lastOf(gridS.clean), m.lang)}, ` +
    `${m.t("batteries")} ${fmtPower(lastOf(battS.clean), m.lang)}`;

  const legend = [
    legendItem(STROKE.pv, m.t("Solaire")),
    legendItem(STROKE.grid, m.t("Réseau")),
    legendItem(STROKE.batt, m.t("Batteries")),
    fc.length ? legendItem(STROKE.fc, m.t("Prévision solaire")) : "",
    glitches.length
      ? `<span class="lg" title="${esc(m.t("Pics isolés d'un capteur, masqués pour la lisibilité. La régulation les filtre déjà."))}"><svg class="sw" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="${markerPath("diamond", 7, 7, 3.5)}" class="glitch-mark"/></svg>${glitches.length} ${m.t("pic(s) masqué(s)")}</span>`
      : "",
    glitches.length || st.showRaw
      ? `<button type="button" class="btn small" data-toggle-raw="1" aria-pressed="${st.showRaw}">${m.t(st.showRaw ? "Masquer les pics" : "Afficher les pics bruts")}</button>`
      : "",
  ].join("");

  return `
    <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img" aria-label="${esc(aria)}">
      <text x="${padL}" y="${padT - 8}" class="ylbl">W</text>
      ${yGrid(y, scale.ticks, padL, W, padR, (v) => fmtNum(Math.round(v), 0, m.lang))}
      ${zero}${nowLine}
      ${area ? `<path d="${area}" class="pv-area"/>` : ""}
      ${line(fc, STROKE.fc)}${line(pvS.clean, STROKE.pv)}${line(gridS.clean, STROKE.grid)}${line(battS.clean, STROKE.batt)}
      ${marks}${xl}
    </svg>
    <div class="legend">${legend}</div>`;
}

const SOC_STYLES = [
  { color: "var(--stockage)", dash: "", marker: "circle", w: 2 },
  { color: "var(--ink)", dash: "7 4", marker: "square", w: 2 },
  { color: "var(--stockage)", dash: "1.5 4.5", marker: "diamond", w: 2.6, round: true },
  { color: "var(--ink-muted)", dash: "10 3 2 3", marker: "triangle", w: 2 },
  { color: "var(--ink)", dash: "", marker: "cross", w: 2 },
];

/** SoC of every battery over the selected window. */
export function socChart(m, st) {
  const s = st.series;
  if (!s || !s.socByName) return "";
  const names = Object.keys(s.socByName).filter((n) => s.socByName[n].length);
  if (!names.length) return "";
  const now = Date.now();
  const W = Math.max(280, st.cw - 2);
  const H = W < 520 ? 170 : 200;
  const padL = 50;
  const padR = 14;
  const padT = 20;
  const padB = 26;
  let { tMin, tMax } = windowBounds(st, now);
  for (const n of names)
    for (const p of s.socByName[n]) {
      if (p.t < tMin) tMin = p.t;
      if (p.t > tMax) tMax = p.t;
    }
  if (tMax <= tMin) return "";
  const x = (t) => padL + ((t - tMin) / (tMax - tMin)) * (W - padL - padR);
  const y = (v) => padT + (1 - v / 100) * (H - padT - padB);
  const xl = [tMin, (tMin + tMax) / 2, tMax]
    .map(
      (t, i) =>
        `<text x="${f(x(t))}" y="${H - 7}" class="xlbl" text-anchor="${i === 0 ? "start" : i === 2 ? "end" : "middle"}">${clock(t)}</text>`
    )
    .join("");
  const lines = names
    .map((n, idx) => {
      const style = SOC_STYLES[idx % SOC_STYLES.length];
      const pts = s.socByName[n];
      const last = pts[pts.length - 1];
      const dash = style.dash ? ` stroke-dasharray="${style.dash}"` : "";
      const cap = style.round ? ' stroke-linecap="round"' : "";
      return (
        `<path d="${linePath(pts, x, y)}" fill="none" stroke="${style.color}" stroke-width="${style.w}" stroke-linejoin="round"${dash}${cap}/>` +
        marker(style.marker, x(last.t), y(last.v), style.color)
      );
    })
    .join("");
  const legend = names
    .map((n, idx) => legendItem(SOC_STYLES[idx % SOC_STYLES.length], n))
    .join("");
  const aria = `${m.t("Niveau de charge par batterie")} ${windowLabel(m, st)} : ${names
    .map((n) => {
      const p = s.socByName[n];
      return `${n} ${fmtNum(Math.round(p[p.length - 1].v), 0, m.lang)}${NBSP}%`;
    })
    .join(", ")}`;
  return `
    <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img" aria-label="${esc(aria)}">
      <text x="${padL}" y="${padT - 8}" class="ylbl">%</text>
      ${yGrid(y, [0, 25, 50, 75, 100], padL, W, padR, (v) => String(v))}
      ${lines}${xl}
    </svg>
    <div class="legend">${legend}</div>`;
}

/** Advisory 24 h plan: filled bars = planned charge, outlined bars = planned discharge. */
export function planChart(m, sched, cw) {
  const W = Math.max(280, cw - 2);
  const H = W < 520 ? 180 : 210;
  const padL = 40;
  const padR = 14;
  const padT = 14;
  const padB = 26;
  const n = sched.length;
  const bw = (W - padL - padR) / n;
  let pMax = 1;
  for (const s of sched) pMax = Math.max(pMax, Math.abs(s.battery_power_w || 0));
  const by0 = padT + (H - padT - padB) * 0.55;
  const barScale = ((H - padT - padB) * 0.4) / pMax;
  const socY = (pct) => padT + (1 - pct / 100) * (H - padT - padB);
  let bars = "";
  sched.forEach((s, i) => {
    const p = s.battery_power_w || 0;
    const h = Math.abs(p) * barScale;
    const bx = padL + i * bw + 1;
    const by = p >= 0 ? by0 - h : by0;
    bars += `<rect x="${f(bx)}" y="${f(by)}" width="${f(Math.max(1, bw - 2))}" height="${f(h)}" class="${p >= 0 ? "bar-chg" : "bar-dis"}"/>`;
  });
  const pts = sched
    .map((s, i) => `${f(padL + i * bw + bw / 2)},${f(socY(s.soc_end_pct))}`)
    .join(" ");
  const labels = sched
    .map((s, i) =>
      i % 3 === 0
        ? `<text x="${f(padL + i * bw + bw / 2)}" y="${H - 7}" class="xlbl" text-anchor="middle">${hourLabel(Date.parse(s.start))}</text>`
        : ""
    )
    .join("");
  const aria = `${m.t("Plan indicatif de la batterie sur 24 h")} : ${m.t("barres pleines, charge prévue ; barres creuses, décharge prévue ; ligne, niveau de charge prévu.")}`;
  return `
    <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="chart" role="img" aria-label="${esc(aria)}">
      <line x1="${padL}" y1="${f(by0)}" x2="${W - padR}" y2="${f(by0)}" class="zero"/>
      ${bars}
      <polyline points="${pts}" class="soc-line"/>
      ${labels}
    </svg>
    <div class="legend">
      <span class="lg"><svg class="sw" width="16" height="14" viewBox="0 0 16 14" aria-hidden="true"><rect x="2" y="2" width="12" height="10" class="bar-chg"/></svg>${m.t("Charge prévue")}</span>
      <span class="lg"><svg class="sw" width="16" height="14" viewBox="0 0 16 14" aria-hidden="true"><rect x="2" y="2" width="12" height="10" class="bar-dis"/></svg>${m.t("Décharge prévue")}</span>
      <span class="lg"><svg class="sw" width="34" height="14" viewBox="0 0 34 14" aria-hidden="true"><path d="M1 7H33" class="soc-line"/></svg>${m.t("Niveau prévu")}</span>
    </div>`;
}

/** Live regulation sparkline: target (dashed) against the real fleet (solid). */
export function regSparkline(m, h) {
  if (h.length < 3) return "";
  const W = 320;
  const H = 64;
  const pad = 4;
  let vMin = 0;
  let vMax = 0;
  for (const p of h) {
    vMin = Math.min(vMin, p.target, p.fleet);
    vMax = Math.max(vMax, p.target, p.fleet);
  }
  if (vMax === vMin) vMax = vMin + 1;
  const n = h.length;
  const x = (i) => pad + (i / (n - 1)) * (W - 2 * pad);
  const y = (v) => pad + (1 - (v - vMin) / (vMax - vMin)) * (H - 2 * pad);
  const path = (key) =>
    h.map((p, i) => (i ? "L" : "M") + f(x(i)) + " " + f(y(p[key]))).join(" ");
  const zero =
    vMin < 0 && vMax > 0
      ? `<line x1="${pad}" y1="${f(y(0))}" x2="${W - pad}" y2="${f(y(0))}" class="zero"/>`
      : "";
  const target = { color: "var(--ink)", dash: "6 3", marker: "", w: 1.8 };
  const fleet = { color: "var(--stockage)", dash: "", marker: "", w: 2 };
  return `<svg viewBox="0 0 ${W} ${H}" class="spark" preserveAspectRatio="none" role="img" aria-label="${esc(m.t("Cible et parc réel, dernières minutes"))}">${zero}
    <path d="${path("target")}" fill="none" stroke="${target.color}" stroke-width="${target.w}" stroke-dasharray="${target.dash}" vector-effect="non-scaling-stroke"/>
    <path d="${path("fleet")}" fill="none" stroke="${fleet.color}" stroke-width="${fleet.w}" vector-effect="non-scaling-stroke"/></svg>
    <div class="legend small">${legendItem(target, m.t("Cible"))}${legendItem(fleet, m.t("Parc réel"))}</div>`;
}

/** Tiny profile of one appliance cycle, scaled to its own peak (a shape, not a magnitude). */
export function cycleSpark(curve) {
  if (!Array.isArray(curve) || curve.length < 2) return "";
  const W = 120;
  const H = 22;
  const peak = Math.max(...curve, 1);
  const pts = curve
    .map((v, i) => `${f((i / (curve.length - 1)) * W)},${f(H - (v / peak) * H)}`)
    .join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" class="cyc" preserveAspectRatio="none" aria-hidden="true">
    <polygon points="0,${H} ${pts} ${W},${H}" class="cyc-fill"/>
    <polyline points="${pts}" class="cyc-line" vector-effect="non-scaling-stroke"/></svg>`;
}
