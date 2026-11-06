/**
 * Number, unit and duration formatting for the SolarBalance panel.
 *
 * Signature rules: decimal comma, a no-break space before the unit, a narrow no-break
 * space between thousands (what `Intl` emits for "fr"), true minus sign, durations as
 * `3 h 42`. Pure functions, no DOM and no Home Assistant access, so they are unit-testable.
 */

export const NBSP = " ";
const MINUS = "−";

const _nf = new Map();

function numberFormat(lang, digits) {
  const key = `${lang}|${digits}`;
  let nf = _nf.get(key);
  if (!nf) {
    nf = new Intl.NumberFormat(lang, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    _nf.set(key, nf);
  }
  return nf;
}

/** Format a finite number with `digits` decimals; non-finite values give "—". */
export function fmtNum(n, digits = 0, lang = "fr") {
  if (n == null || !Number.isFinite(n)) return "—";
  const out = numberFormat(lang, digits).format(n);
  // `-0` after rounding must not show a minus sign.
  const zero = Number(n.toFixed(digits)) === 0;
  return (zero ? out.replace("-", "") : out).replace("-", MINUS);
}

/** `value` and `unit` joined by a no-break space, e.g. `68,4 °C`. */
export function withUnit(value, unit) {
  return unit ? `${value}${NBSP}${unit}` : value;
}

/** Power as `{ value, unit }`: watts below 1 kW, kilowatts above. */
export function powerParts(w, lang = "fr") {
  if (w == null || !Number.isFinite(w)) return { value: "—", unit: "W" };
  if (Math.abs(w) >= 1000) return { value: fmtNum(w / 1000, 2, lang), unit: "kW" };
  return { value: fmtNum(Math.round(w), 0, lang), unit: "W" };
}

/** Power as plain text, e.g. `1,25 kW`. */
export function fmtPower(w, lang = "fr") {
  const p = powerParts(w, lang);
  return p.value === "—" ? "—" : withUnit(p.value, p.unit);
}

/** Seconds as the shortest readable duration: `40 s`, `5 min`, `3 h 42`. */
export function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const n = Number(seconds);
  if (!Number.isFinite(n)) return "—";
  if (n < 90) return `${Math.round(n)}${NBSP}s`;
  if (n < 5400) return `${Math.round(n / 60)}${NBSP}min`;
  const totalMin = Math.round(n / 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `${h}${NBSP}h${NBSP}${String(m).padStart(2, "0")}`;
}

/** Decimal hours as `3 h 42`. */
export function fmtHours(hours) {
  if (hours == null || !Number.isFinite(hours)) return "—";
  return fmtDuration(hours * 3600);
}

/** Local clock time `08:05`. */
export function clock(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Local hour label `08 h`. */
export function hourLabel(ms) {
  return `${String(new Date(ms).getHours()).padStart(2, "0")}${NBSP}h`;
}

/** Local date `29/10/2026`. */
export function shortDate(ms) {
  const d = new Date(ms);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

/** Escape a value for use inside HTML text or a double-quoted attribute. */
export function esc(v) {
  return String(v ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}
