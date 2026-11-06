import assert from "node:assert/strict";
import { test } from "node:test";

import { deglitch, parseSeries } from "../../custom_components/solarbalance/www/panel/history.js";

const series = (values, stepMs = 10000) => values.map((v, i) => ({ t: i * stepMs, v }));

test("a one-off spike that recovers is interpolated and listed", () => {
  const { clean, glitches } = deglitch(series([100, 100, -2500, 100, 100]));
  assert.equal(glitches.length, 1);
  assert.equal(glitches[0].v, -2500);
  assert.equal(clean[2].v, 100);
  assert.equal(clean[2].glitch, true);
});

test("a sustained excursion is real data and is left untouched", () => {
  const values = [100, 100, 2500, 2500, 2500, 2500, 2500, 100];
  const { clean, glitches } = deglitch(series(values));
  assert.equal(glitches.length, 0);
  assert.deepEqual(
    clean.map((p) => p.v),
    values
  );
});

test("fewer than three points are returned as-is", () => {
  const { clean, glitches } = deglitch(series([5, 9]));
  assert.equal(glitches.length, 0);
  assert.equal(clean.length, 2);
});

test("parseSeries reads the recorder minimal response and skips bad rows", () => {
  const out = parseSeries([
    { s: "12.5", lu: 100 },
    { s: "unavailable", lu: 101 },
    { s: "3", last_updated: 102 },
  ]);
  assert.deepEqual(out, [
    { t: 100000, v: 12.5 },
    { t: 102000, v: 3 },
  ]);
});
