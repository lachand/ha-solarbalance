/**
 * History helpers: WebSocket series parsing and display-only de-glitching.
 *
 * The grid meter occasionally reports a physically-impossible one-off spike (e.g. a
 * −2 kW "export" with only 1.6 kW of PV and the battery charging) that ruins the
 * auto-scale. We hide such spikes from the drawn line and the scale but MARK them so they
 * stay identifiable, never touching the control loop (which already filters them with a
 * median-of-3 and a settle). A spike is a glitch only when it recovers within
 * GLITCH_MAX_MS: a longer excursion is real data (a genuine load, or a cloud battery that
 * stops reporting for several ticks) and is left untouched.
 */

export const HISTORY_REFRESH_MS = 60000;
export const FUTURE_CAP_H = 12;

const GLITCH_DEV_W = 600; // deviation from the surrounding baseline to be an excursion
const GLITCH_RECOVERY_W = 300; // must return within this of the pre-excursion baseline
const GLITCH_MAX_MS = 20000; // and within ~2 ticks; longer = real, kept as-is

/** Local midnight (start of the current calendar day) in ms. */
export function midnightMs() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** Convert a recorder `history_during_period` array into `[{ t, v }]`. */
export function parseSeries(arr) {
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

/**
 * Split a power series into a de-glitched line and the spikes removed from it.
 * A spike is an excursion of >GLITCH_DEV_W from the pre-excursion baseline that returns
 * to within GLITCH_RECOVERY_W of it inside GLITCH_MAX_MS, i.e. a one-off sensor blip. Its
 * points are replaced by a straight interpolation across the gap (so the line and the
 * auto-scale ignore it) and listed in `glitches` so it stays identifiable.
 * Returns `{ clean: [{t,v,glitch?}], glitches: [{t, v, cy}] }` (cy = the on-line y-value).
 */
export function deglitch(series) {
  const n = series.length;
  if (n < 3) return { clean: series.map((p) => ({ ...p })), glitches: [] };
  const clean = series.map((p) => ({ ...p }));
  const glitches = [];
  let i = 1;
  while (i < n - 1) {
    const base = series[i - 1].v;
    if (Math.abs(series[i].v - base) <= GLITCH_DEV_W) {
      i++;
      continue;
    }
    let j = i;
    while (j < n && Math.abs(series[j].v - base) > GLITCH_DEV_W) j++;
    const recovered = j < n && Math.abs(series[j].v - base) <= GLITCH_RECOVERY_W;
    const endT = j < n ? series[j].t : series[n - 1].t;
    if (recovered && endT - series[i - 1].t <= GLITCH_MAX_MS) {
      const after = series[j].v;
      const span = series[j].t - series[i - 1].t || 1;
      for (let k = i; k < j; k++) {
        const f = (series[k].t - series[i - 1].t) / span;
        const cy = base + (after - base) * f;
        clean[k].v = cy;
        clean[k].glitch = true;
        glitches.push({ t: series[k].t, v: series[k].v, cy });
      }
    }
    i = j > i ? j : i + 1;
  }
  return { clean, glitches };
}
