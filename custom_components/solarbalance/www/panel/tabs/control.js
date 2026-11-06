/**
 * « Pilotage » tab: regulation, quick controls, per-load switches, subscribed power,
 * the advisory 24 h plan and PV curtailment.
 */

import { NBSP, esc, fmtNum, fmtPower, hourLabel, withUnit } from "../format.js";
import { planChart, regSparkline } from "../svg/chart.js";
import { button, card, icon, meter, measure, measureOf, row, stamp } from "../ui.js";

function tag(state, text) {
  return `<span class="tag st-${state}">${icon(state, 12)}<span>${text}</span></span>`;
}

function regulationCard(m, st) {
  const E = m.E;
  const rows = [];
  if (m.exists(E.binding)) rows.push(row(m.t("Garde-fou actif"), `<b>${esc(m.state(E.binding) || "—")}</b>`));
  const num = (label, id) => {
    if (m.exists(id)) rows.push(row(m.t(label), measureOf(m.fmt(id, 0, "W"))));
  };
  num("Réseau filtré", E.gridFiltered);
  num("Cible du parc", E.target);
  num("Correction zéro-injection", E.ziCorr);
  num("Offre de l'équaliseur", E.eqOffer);
  num("Limite de sortie solaire", E.pvLimit);
  if (!rows.length) return "";
  return card(m.t("Régulation"), rows.join("") + regSparkline(m, st.regHist));
}

function controlsCard(m) {
  const b = (svc, label, ic, args, confirm) =>
    button(m.t(label), {
      ic,
      data: {
        service: svc,
        ...(args ? { args: JSON.stringify(args) } : {}),
        ...(confirm ? { confirm: m.t(confirm) } : {}),
      },
    });
  return card(
    m.t("Contrôles rapides"),
    `<div class="btn-row">
      ${b("pause", "Mettre en pause", "pause")}
      ${b("resume", "Reprendre", "play")}
      ${b("force_charge", "Charger à 100 %", "bolt", { target_soc_pct: 100 }, "Forcer la charge à 100 % ?")}
      ${b("force_discharge", "Décharger à 20 %", "battery", { target_soc_pct: 20 }, "Forcer la décharge à 20 % ?")}
      ${b("activate_storm_mode", "Mode tempête", "storm", null, "Activer le mode tempête ?")}
    </div>`
  );
}

function loadsCard(m) {
  const loads = Object.values(m.loadSwitches()).sort((a, b) => (a.name > b.name ? 1 : -1));
  if (!loads.length) return "";
  const t = (c, label, ic) =>
    c ? button(m.t(label), { ic, data: { toggle: c.eid }, kind: "toggle", pressed: c.on }) : "";
  const rows = loads
    .map(
      (l) => `<div class="load-row"><span class="load-name">${esc(l.name)}</span><span class="btn-row">
        ${t(l.force, "Charger maintenant", "bolt")}
        ${t(l.offpeak, "Heures creuses seulement", "clock")}
        ${t(l.solar, "Solaire seulement", "sun")}
        ${t(l.shed, "Ne pas délester", "plug")}
      </span></div>`
    )
    .join("");
  return card(m.t("Consommateurs"), rows);
}

function subscribedCard(m) {
  const sub = m.attr(m.E.grid, "subscribed_power_w");
  const grid = m.num(m.E.grid);
  if (!sub || grid == null) return "";
  const imp = Math.max(0, grid);
  const pct = (imp / sub) * 100;
  const state = pct >= 90 ? "critique" : pct >= 70 ? "attention" : "ok";
  const label = { ok: m.t("Normal"), attention: m.t("Élevé"), critique: m.t("Limite proche") }[state];
  return card(
    m.t("Puissance souscrite"),
    `<div class="score">
       ${measure(fmtNum(imp / 1000, 2, m.lang), `/${NBSP}${fmtNum(sub / 1000, 0, m.lang)}${NBSP}kW`, "l")}
       ${stamp(state, label)}
     </div>
     ${meter(pct, m.t("Soutirage instantané par rapport à la puissance souscrite"), { tone: state })}
     <p class="note">${m.t("Soutirage instantané")}</p>`
  );
}

function planSummary(m, sched) {
  const SLOT_MS = 3600000;
  const cls = (p) => (p > 50 ? "charge" : p < -50 ? "discharge" : "hold");
  const segs = [];
  for (const s of sched) {
    const c = cls(s.battery_power_w || 0);
    const startMs = Date.parse(s.start);
    const last = segs[segs.length - 1];
    if (last && last.c === c) last.endMs = startMs + SLOT_MS;
    else segs.push({ c, startMs, endMs: startMs + SLOT_MS });
  }
  const labels = { charge: m.t("Charge"), discharge: m.t("Décharge") };
  const parts = segs
    .filter((s) => s.c !== "hold")
    .map((s) => `${labels[s.c]} ${m.t("de")} ${hourLabel(s.startMs)} ${m.t("à")} ${hourLabel(s.endMs)}`);
  return parts.length ? parts.join(" · ") : m.t("Aucune action batterie planifiée");
}

function planCard(m, st) {
  // Under a flat tariff there is no time-of-use signal: the advisory charge plan is
  // meaningless (and not applied).
  if (m.attr(m.E.importPrice, "time_varying") === false) return "";
  const a = m.stateObj(m.E.planPower);
  const sched = a && a.attributes && Array.isArray(a.attributes.schedule) ? a.attributes.schedule : [];
  if (!sched.length) return "";
  const rows = sched
    .slice(0, 8)
    .map((s) => {
      const p = Math.round(s.battery_power_w || 0);
      const act =
        p > 20
          ? `${m.t("charge")} ${fmtPower(p, m.lang)}`
          : p < -20
            ? `${m.t("décharge")} ${fmtPower(-p, m.lang)}`
            : m.t("repos");
      return `<tr><td>${hourLabel(Date.parse(s.start))}</td><td>${esc(act)}</td><td>${fmtNum(Math.round(s.soc_end_pct), 0, m.lang)}${NBSP}%</td><td>${withUnit(fmtNum(s.expected_cost_eur || 0, 2, m.lang), "€")}</td></tr>`;
    })
    .join("");
  return card(
    m.t("Plan indicatif sur 24 h"),
    `<p class="plan-summary">${esc(planSummary(m, sched))}</p>
     ${planChart(m, sched, st.cw)}
     <div class="table-wrap"><table class="pred-table">
       <thead><tr><th scope="col">${m.t("Heure")}</th><th scope="col">${m.t("Batterie")}</th><th scope="col">${m.t("Niveau")}</th><th scope="col">${m.t("Coût")}</th></tr></thead>
       <tbody>${rows}</tbody></table></div>
     <p class="note">${m.t("Indicatif : ce plan n'est pas appliqué aux équipements.")}</p>`,
    { cls: "span-all" }
  );
}

function curtailCard(m) {
  const devs = Object.values(m.devices()).filter((k) => k.mppt_power || k.mppt_limit);
  if (!devs.length) return "";
  const rows = devs
    .map((k) => {
      const prod = m.num(k.mppt_power);
      const lim = m.num(k.mppt_limit);
      const capped = prod != null && lim != null && lim > 0 && prod >= lim - 20;
      return row(
        k.name,
        `${measureOf(fmtPower(prod || 0, m.lang))} <span class="cote">/ ${lim != null ? fmtPower(lim, m.lang) : "∞"}</span>${capped ? ` ${tag("attention", m.t("bridé"))}` : ""}`
      );
    })
    .join("");
  const hidden = m.num2(m.attr(m.E.regDebug, "hidden_pv_w"));
  const hiddenRow =
    hidden != null && hidden > 10 ? row(m.t("Solaire caché estimé"), measureOf(fmtPower(hidden, m.lang))) : "";
  return card(m.t("Bridage solaire"), rows + hiddenRow);
}

export function renderControl(m, st) {
  const blocks = [
    regulationCard(m, st),
    controlsCard(m),
    loadsCard(m),
    subscribedCard(m),
    curtailCard(m),
    planCard(m, st),
  ].filter(Boolean);
  return `<div class="grid">${blocks.join("")}</div>`;
}
