/**
 * « Maintenant » tab: alerts, what the system is doing, live flow diagram, today's summary
 * and the power chart.
 */

import { NBSP, esc, fmtNum, fmtPower, withUnit } from "../format.js";
import { flowDiagram, flowFromModel } from "../svg/flow.js";
import { powerChart } from "../svg/chart.js";
import { button, card, empty, icon, meter, measureOf, tile } from "../ui.js";
import { healthSummary } from "./health.js";

/** Derived energy figures for the day. */
export function energyStats(m) {
  const pv = m.num(m.E.pvToday);
  const imp = m.num(m.E.gridImportToday);
  const exp = m.num(m.E.gridExportToday);
  const pvSelf = pv != null && exp != null ? Math.max(0, pv - exp) : null;
  // Prefer the integrated total-consumption sensor; fall back to the identity
  // consumption = self-consumed PV + grid import.
  let used = m.num(m.E.consoToday);
  if (used == null) {
    if (pvSelf != null && imp != null) used = pvSelf + imp;
    else if (imp != null) used = imp;
  }
  // Autonomy: share of consumption NOT drawn from the grid.
  let autonomy = null;
  if (used != null && used > 0 && imp != null)
    autonomy = Math.max(0, Math.min(100, ((used - imp) / used) * 100));
  // Self-consumption: share of production consumed locally (not exported).
  let selfCons = null;
  if (pv != null && pv > 0 && exp != null)
    selfCons = Math.max(0, Math.min(100, ((pv - exp) / pv) * 100));
  return { pv, imp, exp, used, autonomy, selfCons };
}

function banner(state, text, role = "status") {
  return `<div class="banner st-${state}" role="${role}">${icon(state, 20)}<div>${esc(text)}</div></div>`;
}

function banners(m) {
  const out = [];
  const on = (id) => m.state(id) === "on";
  if (on(m.E.degraded))
    out.push(banner("critique", m.t("Mode dégradé : une ou plusieurs entités sont indisponibles."), "alert"));
  if (on(m.E.storm))
    out.push(banner("attention", m.t("Mode tempête actif : préparation du stockage en cours.")));
  if (on(m.E.weather)) out.push(banner("attention", m.t("Vigilance météo en cours.")));
  if (on(m.E.eveningShed)) {
    const a = m.attr(m.E.eveningShed, "shed_loads");
    const loads = Array.isArray(a) ? a : [];
    const def = m.attr(m.E.eveningShed, "battery_deficit_kwh");
    out.push(
      banner(
        "attention",
        `${m.t("Délestage prioritaire de la batterie : gros consommateurs coupés")}${loads.length ? ` (${loads.join(", ")})` : ""}${def != null ? `, ${m.t("déficit")} ${fmtNum(Number(def), 1, m.lang)}${NBSP}kWh` : ""}.`
      )
    );
  }
  if (on(m.E.evFastCharge))
    out.push(banner("info", m.t("Charge rapide du véhicule assistée par les batteries (solaire récupérable).")));
  const dl = m.attr(m.E.evFastCharge, "deadline");
  if (dl && typeof dl === "object") {
    for (const name in dl) {
      if (dl[name] && dl[name].force) {
        out.push(
          banner(
            "attention",
            `${m.t("Échéance")} ${name} : ${m.t("charge réseau forcée")} (${dl[name].remaining_kwh}${NBSP}kWh ${m.t("restants")}, ${dl[name].hours_left}${NBSP}h).`
          )
        );
      }
    }
  }
  const h = healthSummary(m);
  if (h.count > 0) {
    const label = `${h.count} ${h.count > 1 ? m.t("points d'attention") : m.t("point d'attention")}`;
    out.push(
      `<div class="banner st-${h.level}" role="status">${icon(h.level, 20)}<div>${esc(label)}</div>${button(m.t("Ouvrir la santé"), { data: { tab: "health" } })}</div>`
    );
  }
  return out.length ? `<div class="banners">${out.join("")}</div>` : "";
}

function explainCard(m) {
  const key = m.attr(m.E.regDebug, "explanation_key");
  const text = m.attr(m.E.regDebug, "explanation");
  if (!text && !key) return "";
  const rd = m.E.regDebug;
  const p = {
    t: fmtPower(Math.abs(m.num2(m.attr(rd, "target_w")) || 0), m.lang),
    h: fmtPower(Math.abs(m.num2(m.attr(rd, "natural_grid_w")) || 0), m.lang),
    pv: fmtPower(Math.abs(m.num2(m.attr(rd, "controllable_mppt_w")) || 0), m.lang),
  };
  const base = String(key || "").split("_")[0];
  let fr;
  if (key === "degraded_solar_fallback")
    fr = "Compteur indisponible : stockage d'un surplus solaire estimé, sans jamais décharger à l'aveugle.";
  else if (key === "degraded_no_meter")
    fr = "Compteur réseau indisponible : le pilotage est suspendu jusqu'à son retour.";
  else if (key === "balance_settled")
    fr = "Au point d'équilibre : le réseau est assez proche de la consigne pour que corriger encore ne ferait que courir après l'ordre précédent, encore en route.";
  else if (key === "settle_hold")
    fr = "Pause volontaire après la chute d'une grosse charge, plutôt que de courir après le transitoire.";
  else if (base === "discharge") fr = `Décharge ${p.t} : la maison tire ${p.h}, le solaire en couvre ${p.pv}.`;
  else if (base === "charge") fr = `Charge ${p.t} : le solaire produit ${p.pv}, la maison tire ${p.h}.`;
  else if (base === "idle") fr = "Parc à l'arrêt : production et consommation s'équilibrent.";
  else fr = text;
  return card(m.t("Ce que fait le système"), `<p class="explain">${esc(m.isEnglish ? text : fr)}</p>`);
}

function optTile(m, label, id, digits, unit) {
  if (!m.exists(id)) return "";
  return tile(m.t(label), measureOf(m.fmt(id, digits, unit)));
}

function valueTile(m, label, v, digits, unit) {
  if (v == null) return "";
  return tile(m.t(label), measureOf(withUnit(fmtNum(v, digits, m.lang), unit)));
}

function summaryCard(m) {
  const E = m.E;
  const st = energyStats(m);
  const energy = [
    valueTile(m, "Production", st.pv, 2, "kWh"),
    valueTile(m, "Consommation", st.used, 2, "kWh"),
    optTile(m, "Solaire restant", E.pvRemaining, 1, "kWh"),
    valueTile(m, "Soutiré", st.imp, 2, "kWh"),
    valueTile(m, "Injecté", st.exp, 2, "kWh"),
  ].join("");
  const ratios = [
    st.selfCons != null
      ? `<div class="ratio"><div class="ratio-h"><span>${m.t("Autoconsommation")}</span>${measureOf(withUnit(fmtNum(Math.round(st.selfCons), 0, m.lang), "%"))}</div>${meter(st.selfCons, m.t("Autoconsommation"))}</div>`
      : "",
    st.autonomy != null
      ? `<div class="ratio"><div class="ratio-h"><span>${m.t("Autonomie")}</span>${measureOf(withUnit(fmtNum(Math.round(st.autonomy), 0, m.lang), "%"))}</div>${meter(st.autonomy, m.t("Autonomie"))}</div>`
      : "",
  ].join("");
  const money = [
    optTile(m, "Coût du réseau", E.dailyCost, 2, "€"),
    optTile(m, "Économies du jour", E.dailySavings, 2, "€"),
    optTile(m, "Économies du mois", E.savingsMonth, 2, "€"),
    optTile(m, "Économies de l'année", E.savingsYear, 2, "€"),
  ].join("");
  const group = (title, body) =>
    `<div class="group"><div class="group-t">${title}</div>${body || empty(m.t("Aucun capteur configuré."))}</div>`;
  return card(
    m.t("Bilan du jour"),
    `${group(m.t("Énergie"), `<div class="tiles">${energy}</div>${ratios}`)}${group(m.t("Argent"), `<div class="tiles">${money}</div>`)}`
  );
}

function windowSelector(m, st) {
  const opts = [
    { v: 1, label: `1${NBSP}h` },
    { v: 6, label: `6${NBSP}h` },
    { v: 24, label: `24${NBSP}h` },
    { v: "day", label: m.t("Jour") },
  ];
  return `<div class="winsel" role="group" aria-label="${esc(m.t("Période du graphique"))}">${opts
    .map(
      (o) =>
        `<button type="button" class="btn small" data-h="${o.v}" aria-pressed="${st.window === o.v}">${o.label}</button>`
    )
    .join("")}</div>`;
}

export function renderNow(m, st) {
  return `
    ${banners(m)}
    <div class="split">
      <div class="col">
        ${card(m.t("Flux en temps réel"), flowDiagram(flowFromModel(m)), { cls: "flow-card" })}
        ${card(m.t("Puissance"), powerChart(m, st), { cls: "chart-card", actions: windowSelector(m, st) })}
      </div>
      <div class="col">${explainCard(m)}${summaryCard(m)}</div>
    </div>`;
}
