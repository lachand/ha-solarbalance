/**
 * Operating mode as a Signature state: `[state, French label]`. Storm and manual override
 * are « Attention »; paused is « Inactif »; degraded is « Critique ».
 */
export const MODES = {
  normal: ["ok", "Normal"],
  storm: ["attention", "Tempête"],
  degraded: ["critique", "Dégradé"],
  paused: ["inactif", "En pause"],
  manual_override: ["attention", "Manuel"],
};

/** `[state, label]` for a mode key, falling back to an inactive stamp with the raw key. */
export function modeState(mode) {
  return MODES[mode] || ["inactif", mode || "—"];
}
