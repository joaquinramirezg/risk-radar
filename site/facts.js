// Every number printed on the pages, computed from site/data. A page writes the number in its HTML
// (so it reads without script) and tags it data-f="<key>"; this module rewrites it from the data on
// load, and tests/js/site_facts.test.mjs fails CI when a page's printed number disagrees.
const pct = x => `${Math.round(100 * x)}%`;
const int = x => Math.round(x).toLocaleString("en-US");
const usd4 = x => `$${x.toFixed(4)}`;

export const SOURCES = ["index", "findings", "faded", "eval"];

export function facts({ index, findings, faded, eval: ev }) {
  const th = name => findings.themes.find(t => t.theme === name);
  const esg = faded.find(t => t.theme === "ESG");
  const haiku = ev.models["claude-haiku-5-5-low"], sonnet = ev.models["claude-sonnet-5-5-low"];
  const r = ev.retrieval;
  return {
    companies: int(findings.companies),
    filings: int(2 * index.companies.length),
    risks: int(findings.risks_current),
    new: int(findings.statuses.new),
    removed: int(findings.statuses.removed),
    ai: int(th("Artificial intelligence").companies_up),
    tariffs: int(th("Tariffs and trade").companies_up),
    cyber: int(th("Cybersecurity").companies_up),
    esg_had: int(esg.had),
    esg_gone: int(esg.gone),
    golden: int(ev.golden.n),
    unanswerable: int(ev.golden.n - ev.golden.answerable),
    correct: pct(haiku.correct.mean),
    correct_lo: pct(haiku.correct.lo),
    correct_hi: pct(haiku.correct.hi),
    refused: int(haiku.declined_when_unanswerable.mean * haiku.n_unanswerable),
    backed: pct(haiku.claims_supported.rate.mean),
    cost: usd4(haiku.usd_per_answer),
    p50: `${(haiku.p50_ms / 1000).toFixed(1)} s`,
    sonnet_correct: pct(sonnet.correct.mean),
    sonnet_cost: usd4(sonnet.usd_per_answer),
    sonnet_backed: pct(sonnet.claims_supported.rate.mean),
    sonnet_refused: int(sonnet.declined_when_unanswerable.mean * sonnet.n_unanswerable),
    sonnet_p50: `${(sonnet.p50_ms / 1000).toFixed(1)} s`,
    bm25_r5: pct(r.bm25.r5.mean),
    dense_r5: pct(r.dense.r5.mean),
    hybrid_r5: pct(r.hybrid.r5.mean),
    company_r5: pct(r.hybrid_company.r5.mean),
    judge_agree: int(ev.judge_check.exact_agreement),
    judge_n: int(ev.judge_check.n),
    eval_cost: `$${ev.eval_cost_usd.toFixed(2)}`,
  };
}

// The forecast page's numbers, from data/forecast.json (absent until the first forecast run).
export function forecastFacts(fc) {
  return {
    fc_themes: int(fc.themes.length),
    fc_n: int(fc.forecasts.length),
    fc_companies: int(new Set(fc.forecasts.map(f => f.ticker)).size),
    bt_model: fc.backtest.model.brier.toFixed(3),
    bt_b0: fc.backtest.B0.brier.toFixed(3),
    bt_b1: fc.backtest.B1.brier.toFixed(3),
  };
}

// In the browser: rewrite every [data-f] from the data, so a rebuilt dataset never leaves a stale number.
if (typeof document !== "undefined") {
  Promise.all(SOURCES.map(s => fetch(`data/${s}.json`).then(r => r.json())))
    .then(async ([index, findings, faded, ev]) => {
      const fc = await fetch("data/forecast.json").then(r => (r.ok ? r.json() : null)).catch(() => null);
      const f = { ...facts({ index, findings, faded, eval: ev }), ...(fc ? forecastFacts(fc) : {}) };
      document.querySelectorAll("[data-f]").forEach(el => { if (el.dataset.f in f) el.textContent = f[el.dataset.f]; });
    })
    .catch(() => {});
}
