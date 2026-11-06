import assert from "node:assert/strict";
import { test } from "node:test";

import {
  esc,
  fmtDuration,
  fmtHours,
  fmtNum,
  fmtPower,
  powerParts,
  withUnit,
} from "../../custom_components/solarbalance/www/panel/format.js";

const NBSP = " ";
const NNBSP = " ";
const MINUS = "−";

const NUM_CASES = [
  [1234.5, 1, `1${NNBSP}234,5`],
  [0.5, 2, "0,50"],
  [-340, 0, `${MINUS}340`],
  [-0.001, 2, "0,00"],
  [null, 0, "—"],
  [Number.NaN, 1, "—"],
];

for (const [value, digits, expected] of NUM_CASES) {
  test(`fmtNum(${value}, ${digits}) uses French separators`, () => {
    assert.equal(fmtNum(value, digits, "fr"), expected);
  });
}

const POWER_CASES = [
  [340.4, `340${NBSP}W`],
  [1250, `1,25${NBSP}kW`],
  [-2000, `${MINUS}2,00${NBSP}kW`],
  [null, "—"],
];

for (const [watts, expected] of POWER_CASES) {
  test(`fmtPower(${watts})`, () => {
    assert.equal(fmtPower(watts, "fr"), expected);
  });
}

test("powerParts splits the figure and its unit", () => {
  assert.deepEqual(powerParts(1250, "fr"), { value: "1,25", unit: "kW" });
});

test("withUnit joins with a no-break space", () => {
  assert.equal(withUnit("68,4", "°C"), `68,4${NBSP}°C`);
});

const DURATION_CASES = [
  [40, `40${NBSP}s`],
  [300, `5${NBSP}min`],
  [13320, `3${NBSP}h${NBSP}42`],
  [null, "—"],
];

for (const [seconds, expected] of DURATION_CASES) {
  test(`fmtDuration(${seconds})`, () => {
    assert.equal(fmtDuration(seconds), expected);
  });
}

test("fmtHours converts decimal hours", () => {
  assert.equal(fmtHours(2.7), `2${NBSP}h${NBSP}42`);
});

test("esc neutralises markup and quotes", () => {
  assert.equal(esc(`<b a="1">'x'&</b>`), "&lt;b a=&quot;1&quot;&gt;&#39;x&#39;&amp;&lt;/b&gt;");
});
