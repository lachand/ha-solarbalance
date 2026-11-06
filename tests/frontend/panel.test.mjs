import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { Model } from "../../custom_components/solarbalance/www/panel/model.js";
import { renderBatteries } from "../../custom_components/solarbalance/www/panel/tabs/batteries.js";
import { renderControl } from "../../custom_components/solarbalance/www/panel/tabs/control.js";
import { healthSummary, renderHealth } from "../../custom_components/solarbalance/www/panel/tabs/health.js";
import { renderNow } from "../../custom_components/solarbalance/www/panel/tabs/now.js";
import { makeHass } from "./mock_hass.mjs";

const PANEL_DIR = new URL("../../custom_components/solarbalance/www/panel/", import.meta.url).pathname;

function modelFor(options = {}) {
  const m = new Model();
  m.setHass(makeHass(options));
  return m;
}

const state = () => ({
  tab: "now",
  window: 6,
  series: null,
  showRaw: false,
  regHist: [],
  debugOpen: true,
  cw: 720,
});

const TABS = [
  ["now", renderNow],
  ["control", renderControl],
  ["batteries", renderBatteries],
  ["health", renderHealth],
];

for (const [name, render] of TABS) {
  test(`${name} tab renders without placeholders or hard-coded colours`, () => {
    const html = render(modelFor(), state());
    assert.ok(html.length > 200);
    assert.doesNotMatch(html, /undefined|NaN|\[object/);
    assert.doesNotMatch(html, /#[0-9a-fA-F]{3,8}\b/);
  });
}

test("the English locale translates labels", () => {
  const html = renderNow(modelFor({ lang: "en" }), state());
  assert.match(html, /Real-time flow/);
});

test("entities resolve by translation_key", () => {
  const m = modelFor();
  assert.equal(m.E.pv, "sensor.sb_pv");
  assert.equal(m.num(m.E.grid), -340);
});

test("devices group the per-battery entities", () => {
  const names = Object.values(modelFor().devices()).map((d) => d.name);
  assert.ok(names.includes("Batterie salon"));
  assert.ok(names.includes("Batterie garage"));
});

test("load switches expose force, shed, off-peak and solar slots", () => {
  const load = Object.values(modelFor().loadSwitches())[0];
  assert.deepEqual(Object.keys(load).sort(), ["force", "name", "offpeak", "shed", "solar"]);
});

test("health summary reports attention when the score is low", () => {
  const { count, level } = healthSummary(modelFor({ lowScore: true }));
  assert.ok(count >= 1);
  assert.equal(level, "attention");
});

test("health summary is calm when everything is fine", () => {
  const m = modelFor({ lowScore: false });
  m.hass.states["sensor.sb_link"].attributes.links = [];
  assert.equal(healthSummary(m).count, 0);
});

function sources(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? sources(p) : [p];
  });
}

const FILES = sources(PANEL_DIR).filter((f) => /\.(js|css)$/.test(f));

for (const file of FILES) {
  test(`${file.replace(PANEL_DIR, "")} has no hard-coded colour`, () => {
    const text = readFileSync(file, "utf8");
    assert.doesNotMatch(text, /#[0-9a-fA-F]{3,8}\b(?![\w-])/);
    assert.doesNotMatch(text, /\brgba?\(|\bhsla?\(/);
  });
}
