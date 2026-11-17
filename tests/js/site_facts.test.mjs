// Every number a page prints with data-f="<key>" must equal what site/facts.js computes from
// site/data. The pages read without script, so a rebuilt dataset must not leave a stale figure.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { facts, forecastFacts, SOURCES } from "../../site/facts.js";

const SITE = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "site");
const data = Object.fromEntries(SOURCES.map(s => [s, JSON.parse(readFileSync(join(SITE, "data", `${s}.json`), "utf8"))]));
const FC = join(SITE, "data", "forecast.json");
const F = { ...facts(data), ...(existsSync(FC) ? forecastFacts(JSON.parse(readFileSync(FC, "utf8"))) : {}) };
// Before the first forecast run there is no forecast.json, so its numbers cannot be checked yet.
const pendingForecast = k => !existsSync(FC) && /^(fc|bt)_/.test(k);
const pages = readdirSync(SITE).filter(f => f.endsWith(".html"));

test("facts are computed for every key", () => {
  for (const [k, v] of Object.entries(F)) assert.ok(v && !/NaN|undefined/.test(v), `${k} = ${v}`);
});

for (const page of pages) {
  test(`${page}: every data-f number matches site/data`, () => {
    const html = readFileSync(join(SITE, page), "utf8");
    const re = /<(\w+)[^>]*\bdata-f="([^"]+)"[^>]*>([^<]*)</g;
    let m, n = 0;
    while ((m = re.exec(html))) {
      n++;
      if (pendingForecast(m[2])) continue;
      assert.ok(m[2] in F, `${page}: unknown fact ${m[2]}`);
      assert.equal(m[3], F[m[2]], `${page}: ${m[2]} prints ${m[3]}, data says ${F[m[2]]}`);
    }
    if (["index.html", "ask.html", "how.html"].includes(page)) assert.ok(n > 0, `${page} prints no checked numbers`);
  });
}
