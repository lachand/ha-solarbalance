/**
 * « Santé » tab: installation score, live alerts, anomaly timeline, unreliable links,
 * what the orchestration adds, standby baseline, and the expert diagnostic section.
 */

import { NBSP, clock, esc, fmtDuration, fmtNum, fmtPower, shortDate, withUnit } from "../format.js";
import { button, card, empty, icon, meter, measure, measureOf, row, stamp } from "../ui.js";

const SEV_STATE = { warn: "attention", err: "critique", info: "info" };

/** Live alerts derived from the regulation-debug attributes and the degraded flag. */
export function healthItems(m) {
  const rd = m.E.regDebug;
  const items = [];
  const stale = m.attr(rd, "stale_batteries");
  if (Array.isArray(stale)) {
    for (const b of stale) {
      const cause =
        b.reason === "soc"
          ? m.t("SoC figé")
          : b.reason === "power"
            ? m.t("puissance figée")
            : m.t("hors ligne");
      items.push({ sev: "warn", txt: `${b.device} : ${cause} (${fmtDuration(b.age_s)})` });
    }
  }
  const dup = m.attr(rd, "duplicate_entities");
  if (dup && typeof dup === "object") {
    for (const eid in dup) items.push({ sev: "err", txt: `${m.t("Appareil en double")} : ${dup[eid]} → ${eid}` });
  }
  const vf = m.attr(rd, "verify_failures");
  if (vf && typeof vf === "object") {
    for (const eid in vf)
      items.push({
        sev: "warn",
        txt: `${m.t("Écriture non appliquée")} : ${eid} (${fmtPower(vf[eid], m.lang)})`,
      });
  }
  if (m.state(m.E.degraded) === "on")
    items.push({ sev: "err", txt: m.t("Mode dégradé : entités indisponibles") });
  const cloudTimeout = m.attr(m.E.home, "cloud_timeout");
  const rawBase = m.num2(m.attr(m.E.home, "raw_w"));
  if (cloudTimeout) {
    items.push({
      sev: "info",
      txt: m.t("Batterie cloud en décharge (délai dépassé) : consommation de base plafonnée"),
    });
  } else if (rawBase != null && rawBase < -100) {
    items.push({
      sev: "err",
      txt: `${m.t("Consommation de base négative")} (${fmtPower(rawBase, m.lang)}) : ${m.t("vérifier la correspondance des capteurs")}`,
    });
  }
  return items;
}

function scoreState(score) {
  return score >= 90 ? "ok" : score >= 65 ? "attention" : "critique";
}

function unreliableLinks(m) {
  const links = m.attr(m.E.linkHealth, "links");
  if (!Array.isArray(links)) return null;
  return links.filter((l) => l.verdict === "flaky" || l.verdict === "unreliable");
}

/** How many things deserve attention, and how serious: drives the tab badge and the banner. */
export function healthSummary(m) {
  const items = healthItems(m).filter((i) => i.sev !== "info");
  let count = items.length;
  let level = items.some((i) => i.sev === "err") ? "critique" : count ? "attention" : "ok";
  const score = m.num2(m.state(m.E.installScore));
  if (score != null && score < 90) {
    count += 1;
    level = level === "critique" || score < 65 ? "critique" : "attention";
  }
  const bad = unreliableLinks(m);
  if (bad && bad.length) {
    count += 1;
    if (level === "ok") level = "attention";
  }
  return { count, level };
}

function scoreCard(m) {
  const score = m.num2(m.state(m.E.installScore));
  if (score == null) return "";
  const deductions = m.attr(m.E.installScore, "deductions");
  const state = scoreState(score);
  const label = { ok: "Bonne", attention: "Moyenne", critique: "Dégradée" }[state];
  const rows = Array.isArray(deductions)
    ? `<ul class="plain">${deductions.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>`
    : "";
  return card(
    m.t("Santé de l'installation"),
    `<div class="score">
       ${measure(fmtNum(Math.round(score), 0, m.lang), "/100", "l")}
       ${stamp(state, m.t(label))}
     </div>
     ${meter(score, m.t("Score de santé de l'installation"), { tone: state })}
     ${rows}`
  );
}

function alertsCard(m) {
  const items = healthItems(m);
  const body = items.length
    ? items
        .map(
          (i) =>
            `<div class="alert-row" role="${i.sev === "err" ? "alert" : "status"}">${stamp(SEV_STATE[i.sev], { warn: m.t("Attention"), err: m.t("Critique"), info: m.t("Information") }[i.sev])}<span>${esc(i.txt)}</span></div>`
        )
        .join("")
    : `<div class="alert-row">${stamp("ok", m.t("Normal"))}<span>${m.t("Aucune alerte en cours.")}</span></div>`;
  return card(m.t("Alertes en cours"), body);
}

function anomalyCard(m) {
  const events = m.attr(m.E.anomalyTimeline, "events");
  if (!Array.isArray(events) || !events.length) return "";
  const state = { info: "info", warning: "attention", error: "critique" };
  const rows = events
    .slice(0, 12)
    .map((e) => {
      const sev = state[e.severity] || "attention";
      const t = Date.parse(e.at);
      const when = Number.isNaN(t)
        ? esc(String(e.at || "").slice(0, 16).replace("T", " "))
        : `${shortDate(t)}${NBSP}${clock(t)}`;
      const n = e.count > 1 ? ` <span class="cote">×${e.count}</span>` : "";
      const lbl = { info: m.t("Information"), attention: m.t("Attention"), critique: m.t("Critique") }[sev];
      return `<div class="ev-row"><span class="ev-ic st-${sev}" title="${esc(lbl)}">${icon(sev, 16)}<span class="sr">${esc(lbl)}</span></span><span class="cote ev-when">${when}</span><span>${esc(e.message)}${n}</span></div>`;
    })
    .join("");
  return card(m.t("Frise d'anomalies"), rows);
}

function linksCard(m) {
  const all = m.attr(m.E.linkHealth, "links");
  if (!Array.isArray(all) || !all.length) return "";
  const bad = unreliableLinks(m);
  if (!bad.length)
    return card(m.t("Liaisons (24 h)"), `<div class="alert-row">${stamp("ok", m.t("Normal"))}<span>${m.t("Toutes les liaisons sont stables.")}</span></div>`);
  const rows = bad
    .map((l) => {
      const detail = [
        `${m.t("disponibilité")} ${fmtNum(Number(l.available_pct), 0, m.lang)}${NBSP}%`,
        l.longest_gap_s > 0 ? `${m.t("plus long trou")} ${fmtDuration(l.longest_gap_s)}` : null,
        l.dropouts ? `${l.dropouts} ${m.t("coupures")}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
      const state = l.verdict === "unreliable" ? "critique" : "attention";
      return `<div class="alert-row">${stamp(state, l.verdict === "unreliable" ? m.t("Peu fiable") : m.t("Instable"))}<span><b>${esc(l.key)}</b> <span class="cote">${fmtNum(Number(l.score), 0, m.lang)}/100 · ${esc(detail)}</span></span></div>`;
    })
    .join("");
  return card(m.t("Liaisons peu fiables (24 h)"), rows);
}

function orchestrationCard(m) {
  const gain = m.num2(m.state(m.E.orchGain));
  if (gain == null) return "";
  const hours = m.num2(m.attr(m.E.orchGain, "hours_compared"));
  const title = m.t("Apport de l'orchestration");
  if (hours != null && hours < 2)
    return card(title, empty(m.t("Comparaison en cours : trop tôt pour donner un chiffre.")));
  const actual = m.num2(m.attr(m.E.orchGain, "actual_cost_eur"));
  const naive = m.num2(m.attr(m.E.orchGain, "naive_cost_eur"));
  const held = m.num2(m.attr(m.E.orchGain, "stored_delta_kwh"));
  const eur = (v) => (v == null ? "—" : measureOf(withUnit(fmtNum(v, 2, m.lang), "€")));
  const sign = gain >= 0 ? "+" : "";
  return card(
    title,
    `${row(m.t("Gain par rapport à l'autoconsommation simple"), measure(sign + fmtNum(gain, 2, m.lang), "€"))}
     ${row(m.t("Facture réelle"), eur(actual))}
     ${row(m.t("Facture sans pilotage"), eur(naive))}
     ${row(m.t("Charge conservée"), held == null ? "—" : measureOf(withUnit(fmtNum(held, 2, m.lang), "kWh")))}
     <p class="note">${m.t("Même matériel, même maison, laissés en autoconsommation simple.")}</p>`
  );
}

function talonCard(m) {
  if (!m.exists(m.E.talon)) return "";
  return card(
    m.t("Consommation de veille"),
    `${row(m.t("Talon de nuit"), measureOf(m.fmt(m.E.talon, 0, "W")))}
     <p class="note">${m.t("Après une charge de véhicule de nuit qui l'aurait faussé, le talon peut être recalculé à la prochaine nuit calme.")}</p>
     ${button(m.t("Recalculer le talon"), { ic: "refresh", data: { service: "reset_baseline_talon" } })}`
  );
}

function diagnosticCard(m, st) {
  const a = (m.stateObj(m.E.regDebug) || {}).attributes || {};
  if (!Object.keys(a).length) return "";
  const open = !!st.debugOpen;
  const head = `<button type="button" class="disclosure" data-toggle-debug="1" aria-expanded="${open}">${icon("chevron", 16)}<span>${m.t("Diagnostic de la régulation")}</span></button>`;
  if (!open) return `<section class="card">${head}</section>`;
  const w = (k) => fmtPower(m.num2(a[k]), m.lang);
  const cells = [
    ["garde-fou", a.binding],
    ["cible", w("target_w")],
    ["base boucle", w("loop_base_w")],
    ["zéro-injection", w("zi_correction_w")],
    ["équaliseur", w("equaliser_offer_w")],
    ["parc", w("current_fleet_w")],
    ["mppt", w("controllable_mppt_w")],
    ["pv caché", w("hidden_pv_w")],
    ["non alloué", w("unallocated_w")],
    ["charge non pilotée", w("nc_charge_w")],
    ["réseau filtré", w("grid_filtered_w")],
    ["réseau naturel", w("natural_grid_w")],
    ["limite pv", w("pv_limit_w")],
    ["stabilisation", String(a.settle)],
    ["charge non pilotée active", String(a.noncontrollable_charging)],
  ];
  const tiles = cells
    .map(([l, v]) => `<div class="dbg"><span class="dbg-l">${esc(l)}</span><span class="dbg-v">${esc(v ?? "—")}</span></div>`)
    .join("");
  const per = a.per_battery_w || {};
  const wr = a.written_setpoints || {};
  const perTxt =
    Object.keys(per)
      .map((n) => `${n} : ${fmtNum(Math.round(per[n]), 0, m.lang)}`)
      .join(" · ") || "—";
  const wrTxt =
    Object.keys(wr)
      .map(
        (n) =>
          `${n} : ${fmtNum(Math.round(wr[n].charge_w), 0, m.lang)} en charge, ${fmtNum(Math.round(wr[n].discharge_w), 0, m.lang)} en décharge`
      )
      .join(" · ") || "—";
  return `<section class="card">${head}<div class="dbg-grid">${tiles}</div>
    <p class="dbg-line"><b>${m.t("Par batterie")}</b> ${esc(perTxt)}</p>
    <p class="dbg-line"><b>${m.t("Consignes écrites")}</b> ${esc(wrTxt)}</p></section>`;
}

export function renderHealth(m, st) {
  return `<div class="grid">
    ${scoreCard(m)}
    ${alertsCard(m)}
    ${anomalyCard(m)}
    ${linksCard(m)}
    ${orchestrationCard(m)}
    ${talonCard(m)}
    <div class="span-all">${diagnosticCard(m, st)}</div>
  </div>`;
}
