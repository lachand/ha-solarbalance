/**
 * « Batteries » tab: fleet figures, one card per battery (SoC with its floor, power,
 * setpoints, solar input, temperatures, link state) and the SoC history.
 */

import { NBSP, esc, fmtDuration, fmtHours, fmtNum, fmtPower } from "../format.js";
import { socChart } from "../svg/chart.js";
import { card, empty, meter, measure, measureOf, row, stamp, tile } from "../ui.js";

function fleetCard(m) {
  const E = m.E;
  const tiles = [];
  const add = (label, id, build) => {
    if (m.exists(id)) tiles.push(tile(m.t(label), build()));
  };
  add("Niveau moyen", E.soc, () => measureOf(m.fmt(E.soc, 0, "%"), "l"));
  add("Énergie restante", E.batteryRemaining, () => measureOf(m.fmt(E.batteryRemaining, 1, "kWh")));
  add("Énergie exploitable", E.batteryUsable, () => measureOf(m.fmt(E.batteryUsable, 1, "kWh")));
  add("Avant d'être pleines", E.timeToFull, () => {
    const h = m.num(E.timeToFull);
    return h == null ? measure("—") : measureOf(fmtHours(h));
  });
  add("Avant d'être vides", E.timeToEmpty, () => {
    const h = m.num(E.timeToEmpty);
    return h == null ? measure("—") : measureOf(fmtHours(h));
  });
  return card(
    m.t("Parc de batteries"),
    tiles.length ? `<div class="tiles">${tiles.join("")}</div>` : empty(m.t("Aucun capteur configuré.")),
    { cls: "span-all" }
  );
}

function batteryCard(m, k) {
  const soc = m.num(k.soc);
  const stale = !!m.attr(k.soc, "stale");
  const reason = m.attr(k.soc, "stale_reason");
  const ageS = m.attr(k.soc, "stale_age_s");
  const cause =
    reason === "soc" ? m.t("SoC figé") : reason === "power" ? m.t("puissance figée") : m.t("hors ligne");
  const age = ageS != null ? ` (${fmtDuration(ageS)})` : "";
  const badge = stale ? stamp("attention", m.t("Hors ligne"), `${cause}${age}`) : "";
  const role = m.attr(k.soc, "role");
  const roleBadge = role === "cloud" ? `<span class="tag">${m.t("cloud")}</span>` : "";
  const floor = m.num2(m.attr(k.soc, "soc_min_pct"));

  const rows = [];
  if (k.power) rows.push(row(m.t("Puissance de la batterie"), measureOf(m.fmt(k.power, 0, "W"))));
  // On a STREAM (solar-first + mirror) the base_load setpoint is the AC output of the WHOLE
  // group, while the measured power is the per-battery cell, so the two are not meant to be
  // equal: no comparison here. The real "device does not honour it" signal comes from the
  // health tab (read-back of the written entity).
  const sc = m.num(k.setpoint_charge) || 0;
  const sd = m.num(k.setpoint_discharge) || 0;
  if (sc > 0) rows.push(row(m.t("Consigne de charge"), measureOf(fmtPower(sc, m.lang))));
  if (sd > 0) rows.push(row(m.t("Consigne de décharge"), measureOf(fmtPower(-sd, m.lang))));
  if (k.mppt_power) rows.push(row(m.t("Production solaire"), measureOf(m.fmt(k.mppt_power, 0, "W"))));
  if (k.mppt_limit) rows.push(row(m.t("Limite de production"), measureOf(m.fmt(k.mppt_limit, 0, "W"))));
  if (k.temperature) rows.push(row(m.t("Température de la batterie"), measureOf(m.fmt(k.temperature, 1, "°C"))));
  if (k.mppt_temperature)
    rows.push(row(m.t("Température du régulateur solaire"), measureOf(m.fmt(k.mppt_temperature, 1, "°C"))));

  const level =
    soc != null
      ? `<div class="soc"><div class="ratio-h"><span>${m.t("Niveau de charge")}</span>${measure(fmtNum(Math.round(soc), 0, m.lang), "%", "l")}</div>
         ${meter(soc, `${m.t("Niveau de charge")} ${k.name}`, { tick: floor })}
         ${floor != null ? `<div class="note">${m.t("Plancher")} ${fmtNum(Math.round(floor), 0, m.lang)}${NBSP}%</div>` : ""}</div>`
      : "";

  return `<section class="card${stale ? " stale" : ""}"><div class="card-h"><h3 class="cote-rule">${esc(k.name)}</h3>${roleBadge}${badge}</div>${level}${rows.join("")}</section>`;
}

export function renderBatteries(m, st) {
  const cards = Object.values(m.devices())
    .sort((a, b) => (a.name > b.name ? 1 : -1))
    .map((k) => batteryCard(m, k))
    .join("");
  const chart = socChart(m, st);
  return `
    <div class="grid">
      ${fleetCard(m)}
      ${cards || card(m.t("Batteries"), empty(m.t("Aucun appareil batterie détecté.")))}
    </div>
    ${chart ? card(m.t("Niveau de charge par batterie"), chart, { cls: "chart-card" }) : ""}`;
}
