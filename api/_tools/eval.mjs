// Score "Ask the filings" against the hand-written golden set.
//
//   node api/_tools/eval.mjs retrieval              # free, no API key: the ladder
//   node api/_tools/eval.mjs answers MODEL [EFFORT] # runs the agent on every question
//   node api/_tools/eval.mjs report                 # merges results into site/data/eval.json
//
// Retrieval is scored at the risk-factor level (a passage counts as a hit if it
// belongs to a gold risk), with recall@k, MRR and nDCG@10 and percentile
// bootstrap 95% CIs over questions. It calls the same search() the function
// uses, so the numbers describe what ships.
//
// Answers: abstention on unanswerable questions is exact (did it cite
// nothing / say the filings do not say). Citation precision is exact against
// the gold risks. Answer correctness is judged by a second model against
// Joaquin's own reference answer, and every judged row is written out so the
// judge can be audited by hand (results/answers-*.jsonl).
import Anthropic from "@anthropic-ai/sdk";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ask, PRICES } from "../_lib/agent.js";
import { embedQuery } from "../_lib/embed.js";
import { load, search } from "../_lib/retrieval.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const GOLDEN = join(ROOT, "data", "golden", "golden.jsonl");
const OUT = join(ROOT, "results");
const JUDGE = "claude-sonnet-5-5";
mkdirSync(OUT, { recursive: true });

const golden = readFileSync(GOLDEN, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const answerable = golden.filter((g) => g.gold_risks.length);

// Seeded bootstrap so reruns print identical intervals.
function rng(seed) {
  return () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}
function ci(values, b = 2000) {
  const n = values.length;
  const mean = values.reduce((a, x) => a + x, 0) / n;
  const r = rng(12345);
  const ms = [];
  for (let i = 0; i < b; i++) {
    let s = 0;
    for (let j = 0; j < n; j++) s += values[Math.floor(r() * n)];
    ms.push(s / n);
  }
  ms.sort((a, x) => a - x);
  return { mean: +mean.toFixed(4), lo: +ms[Math.floor(0.025 * b)].toFixed(4), hi: +ms[Math.floor(0.975 * b)].toFixed(4), n };
}
const pct = (xs, p) => [...xs].sort((a, b) => a - b)[Math.min(xs.length - 1, Math.floor(p * xs.length))];

function riskRanking(hits) {
  const { passages } = load();
  const seen = [];
  for (const i of hits) if (!seen.includes(passages[i].risk)) seen.push(passages[i].risk);
  return seen;
}

async function retrieval() {
  const rows = { bm25: [], dense: [], hybrid: [] };
  const misses = [];
  for (const g of answerable) {
    const qvec = await embedQuery(g.question);
    for (const mode of Object.keys(rows)) {
      const ranked = riskRanking(search({ query: g.question, qvec, mode, k: 30 }));
      const gold = new Set(g.gold_risks);
      const rank = ranked.findIndex((r) => gold.has(r)) + 1; // 0 = not found
      const dcg = ranked.slice(0, 10).reduce((a, r, i) => a + (gold.has(r) ? 1 / Math.log2(i + 2) : 0), 0);
      const idcg = [...gold].slice(0, 10).reduce((a, _, i) => a + 1 / Math.log2(i + 2), 0);
      rows[mode].push({ qid: g.qid, rank, r1: +(rank === 1), r5: +(rank > 0 && rank <= 5), r10: +(rank > 0 && rank <= 10), mrr: rank ? 1 / rank : 0, ndcg: dcg / idcg });
      if (mode === "hybrid" && !(rank > 0 && rank <= 5)) misses.push({ qid: g.qid, question: g.question, gold: g.gold_risks, got: ranked.slice(0, 3) });
    }
  }
  const out = {};
  for (const [mode, rs] of Object.entries(rows)) {
    out[mode] = Object.fromEntries(["r1", "r5", "r10", "mrr", "ndcg"].map((m) => [m, ci(rs.map((r) => r[m]))]));
  }
  // Paired: does hybrid beat each single ranker on the same questions?
  out.paired = {};
  for (const base of ["bm25", "dense"]) {
    const d = rows.hybrid.map((r, i) => r.ndcg - rows[base][i].ndcg);
    out.paired[`hybrid_minus_${base}_ndcg`] = ci(d);
  }
  out.misses = misses;
  writeFileSync(join(OUT, "ask-retrieval.json"), JSON.stringify(out, null, 1));
  for (const m of ["bm25", "dense", "hybrid"]) {
    const s = out[m];
    console.log(`${m.padEnd(7)} recall@5 ${s.r5.mean} [${s.r5.lo}, ${s.r5.hi}]  MRR ${s.mrr.mean}  nDCG@10 ${s.ndcg.mean}`);
  }
  console.log(out.paired);
}

const JUDGE_PROMPT = `You grade an answer to a question about companies' 10-K risk factors against a reference answer written by a person who read the filing.
Return JSON only: {"verdict": "correct" | "partial" | "wrong", "reason": "<one sentence>"}.
correct: states what the reference states (wording may differ) and adds nothing that contradicts it.
partial: right direction but misses the main point of the reference, or adds an unsupported claim.
wrong: contradicts the reference, answers a different question, or declines to answer.`;

async function judge(client, g, answer) {
  const res = await client.messages.create({
    model: JUDGE,
    max_tokens: 400,
    output_config: { effort: "low" },
    system: JUDGE_PROMPT,
    messages: [{ role: "user", content: `Question: ${g.question}\nReference answer: ${g.answer}\nAnswer to grade: ${answer}` }],
  });
  const t = res.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  try {
    return { ...JSON.parse(t.slice(t.indexOf("{"), t.lastIndexOf("}") + 1)), usage: res.usage };
  } catch {
    return { verdict: "unparsed", reason: t.slice(0, 200), usage: res.usage };
  }
}

async function answers(model, effort = "low") {
  if (!PRICES[model]) throw new Error(`unknown model ${model}`);
  const client = new Anthropic();
  const file = join(OUT, `answers-${model}-${effort}.jsonl`);
  const done = new Set(existsSync(file) ? readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l).qid) : []);
  for (const g of golden) {
    if (done.has(g.qid)) continue;
    const out = await ask(g.question, { model, effort, client });
    const gold = new Set(g.gold_risks);
    const citedRisks = out.sources.map((s) => s.risk).filter(Boolean);
    const row = {
      qid: g.qid, question: g.question, answerable: gold.size > 0, answer: out.answer, abstained: out.abstained, rejected: out.rejected,
      cited: out.sources.map((s) => s.id),
      cites_gold: citedRisks.some((r) => gold.has(r)),
      citation_precision: citedRisks.length ? citedRisks.filter((r) => gold.has(r)).length / citedRisks.length : null,
      cites_gold_sentence: out.sources.some((s) => (g.gold_sentences || []).includes(s.id)),
      retrieved_gold: out.trace.retrieved.some((r) => gold.has(r)),
      tools: out.trace.tools, usage: out.usage,
    };
    if (row.answerable && !out.abstained) row.judge = await judge(client, g, out.answer);
    writeFileSync(file, `${JSON.stringify(row)}\n`, { flag: "a" });
    console.log(g.qid, row.answerable ? row.judge?.verdict || "abstained" : out.abstained ? "abstained (good)" : "ANSWERED", `$${out.usage.usd.toFixed(4)}`, `${out.usage.ms} ms`);
  }
}

function summarize(file) {
  const rows = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  const ans = rows.filter((r) => r.answerable);
  const un = rows.filter((r) => !r.answerable);
  const ok = ans.map((r) => +(r.judge?.verdict === "correct"));
  const prec = ans.filter((r) => r.citation_precision !== null).map((r) => r.citation_precision);
  return {
    n: rows.length, n_answerable: ans.length, n_unanswerable: un.length,
    correct: ci(ok),
    correct_or_partial: ci(ans.map((r) => +["correct", "partial"].includes(r.judge?.verdict))),
    abstained_when_answerable: ci(ans.map((r) => +r.abstained)),
    abstained_when_unanswerable: un.length ? ci(un.map((r) => +r.abstained)) : null,
    citation_precision: prec.length ? ci(prec) : null,
    rejected_by_citation_check: rows.filter((r) => r.rejected).length,
    usd_per_answer: +(rows.reduce((a, r) => a + r.usage.usd, 0) / rows.length).toFixed(5),
    p50_ms: pct(rows.map((r) => r.usage.ms), 0.5),
    p95_ms: pct(rows.map((r) => r.usage.ms), 0.95),
  };
}

function report() {
  const out = { golden: { n: golden.length, answerable: answerable.length }, retrieval: null, models: {} };
  const rf = join(OUT, "ask-retrieval.json");
  if (existsSync(rf)) {
    const r = JSON.parse(readFileSync(rf, "utf8"));
    delete r.misses;
    out.retrieval = r;
  }
  for (const f of readdir(OUT).filter((f) => f.startsWith("answers-") && f.endsWith(".jsonl"))) {
    out.models[f.slice(8, -6)] = summarize(join(OUT, f));
  }
  writeFileSync(join(ROOT, "site", "data", "eval.json"), JSON.stringify(out, null, 1));
  console.log(JSON.stringify(out.models, null, 1));
}

import { readdirSync as readdir } from "node:fs";

const [cmd, a, b] = process.argv.slice(2);
if (cmd === "retrieval") await retrieval();
else if (cmd === "answers") await answers(a || "claude-haiku-5-5", b);
else if (cmd === "report") report();
else console.log("usage: eval.mjs retrieval | answers MODEL [EFFORT] | report");
