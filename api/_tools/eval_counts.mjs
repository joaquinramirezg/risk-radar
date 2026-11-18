// "How many companies" questions, scored exactly against the site's own counts.
//
//   node api/_tools/eval_counts.mjs run TAG     # runs Ask on every question, writes results/counts-TAG.jsonl
//   node api/_tools/eval_counts.mjs report      # merges every run into reports/counts_eval.json
//
// The golden set (data/golden) asks about one company at a time, so it never
// caught the v3 miss: asked whether companies dropped ESG language, Ask said
// none had, while the board shows 26 of 53. These questions cover every count
// the board prints. The expected number comes from site/data/findings.json and
// faded.json at run time, so the check needs no judge: an answer passes when it
// states the expected number and cites at least one sentence.
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ask } from "../_lib/agent.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DATA = join(ROOT, "site", "data");
const findings = JSON.parse(readFileSync(join(DATA, "findings.json"), "utf8"));
const faded = JSON.parse(readFileSync(join(DATA, "faded.json"), "utf8"));
const theme = (t) => findings.themes.find((x) => x.theme === t);
const fade = (t) => faded.find((x) => x.theme === t);

export const QUESTIONS = [
  ["c01", "How many companies dropped ESG language from their risk factors this year?", fade("ESG").gone],
  ["c02", "Did any companies stop mentioning ESG in their risk factors?", fade("ESG").gone],
  ["c03", "How many companies removed every mention of COVID-19 from their risk factors?", fade("COVID-19").gone],
  ["c04", "How many companies added or expanded risk language about artificial intelligence this year?", theme("Artificial intelligence").companies_up],
  ["c05", "How many companies added or expanded risk language about tariffs?", theme("Tariffs and trade").companies_up],
  ["c06", "How many companies added or expanded cybersecurity risk language?", theme("Cybersecurity").companies_up],
  ["c07", "How many companies added or expanded risk language about China?", theme("China").companies_up],
  ["c08", "How many companies added or expanded risk language about export controls?", theme("Export controls").companies_up],
  ["c09", "How many companies cut or softened their climate risk language this year?", theme("Climate").companies_down],
  ["c10", "How many companies cut or softened risk language about tariffs?", theme("Tariffs and trade").companies_down],
].map(([qid, question, expect]) => ({ qid, question, expect }));

const ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];
const spell = (n) => (n < 20 ? ONES[n] : TENS[Math.floor(n / 10)] + (n % 10 ? `[- ]${ONES[n % 10]}` : ""));
// True when the answer states n, as digits ("26") or in words ("Twenty-six").
export function states(answer, n) {
  const a = answer.toLowerCase();
  if (new RegExp(`(^|[^0-9.])${n}([^0-9]|$)`).test(a)) return true;
  return n < 100 && new RegExp(`\\b${spell(n)}\\b`).test(a);
}
const passes = (x) => !x.abstained && x.cited > 0 && states(x.answer, x.expect);

async function run(tag) {
  const out = [];
  for (const q of QUESTIONS) {
    const r = await ask(q.question);
    const row = { ...q, answer: r.answer, abstained: r.abstained, cited: r.sources.length };
    const pass = passes(row);
    out.push({ ...row, pass, tools: r.trace.tools.map((t) => t.name), usd: r.usage.usd });
    console.log(`${q.qid} ${pass ? "PASS" : "FAIL"} expect ${q.expect}: ${r.answer.slice(0, 140)}`);
  }
  writeFileSync(join(ROOT, "results", `counts-${tag}.jsonl`), out.map((x) => JSON.stringify(x)).join("\n") + "\n");
  const usd = out.reduce((s, x) => s + x.usd, 0);
  console.log(`${tag}: ${out.filter((x) => x.pass).length}/${out.length} pass, $${usd.toFixed(4)}`);
}

function report() {
  const runs = {};
  for (const f of readdirSync(join(ROOT, "results")).filter((f) => /^counts-.+\.jsonl$/.test(f)).sort()) {
    const rows = readFileSync(join(ROOT, "results", f), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
    for (const x of rows) x.pass = passes(x); // rescored with the current check
    runs[f.slice(7, -6)] = {
      pass: rows.filter((x) => x.pass).length,
      n: rows.length,
      usd: +rows.reduce((s, x) => s + x.usd, 0).toFixed(4),
      failed: rows.filter((x) => !x.pass).map((x) => x.qid),
    };
  }
  const path = join(ROOT, "reports", "counts_eval.json");
  writeFileSync(path, JSON.stringify({ questions: QUESTIONS, runs }, null, 2) + "\n");
  console.log(JSON.stringify(runs, null, 2));
}

const [cmd, tag] = process.argv.slice(2);
if (cmd === "run" && tag) await run(tag);
else if (cmd === "report") report();
else console.log("usage: eval_counts.mjs run TAG | report");
