# Versions

One entry per version, same headings each time: the question it answers, what
shipped, the measured result, what it showed, its limits, where it lives. Every
number here is computed from the committed data; the README and the site carry
the same numbers. Git tags mark the last commit of each version.

## v1: the radar (Nov 15 2026, tag `v1`, de42dfb)

**Question.** What did each S&P 100 company change in its 10-K risk factors this year?

**Shipped.** The two latest 10-Ks of 102 companies from SEC EDGAR (204 filings).
Item 1A split into risk factors and matched year over year (bge-small,
one-to-one, cosine 0.80), splits and merges detected, each edit labelled new
exposure, escalated, softened or boilerplate by an LLM classifier. Theme counts
per company, full-text search, a consistency check in CI, deployed on Vercel.
Started Sep 10 2026 as a retrieval eval harness (BM25, IR metrics, tests).

**Result.** 80 of 102 companies added or expanded AI risk; 26 of 53 that named
ESG dropped the term. Matcher and classifier accuracy measured against AI
labellers and published with the method.

**Limits.** Describes the past only. Labels made by AI labellers, said wherever
numbers are quoted.

## v2: Ask the filings (Nov 15 to 16 2026, tag `v2`, a811baa)

**Question.** Can anyone ask the filings a question and trust the answer?

**Shipped.** A tool-using agent on Claude Haiku 5.5 (`api/ask.js`): hybrid
search (BM25 plus embeddings, fused by RRF), four tools, every claim cites a
sentence, and a citation no tool returned blocks the answer on the server.
A 63-question test set, a model grader checked against 30 hand grades, a
Haiku vs Sonnet comparison. Site split into the board, Ask and Method.

**Result.** 83% correct (72% to 93%), 9 of 9 unanswerable questions declined,
$0.0006 an answer; the grader matched 26 of 30 hand grades. Sonnet 5.5 was
right 9 more in 100 (interval -2 to 20) at 18 times the cost, so Haiku ships.

**Limits.** Still about the past. The test questions were written by a model
and say so.

## v3: the forecast (Nov 17 to 18 2026, tag `v3`, af7209e)

**Question.** What will each company add to its next 10-K, and can that be
checked once the filing exists?

**Shipped.**
- Budget: the live Ask held under $2 a month (5 questions a visitor, 60 a day,
  4 turns, 800 tokens; example answers stored in `site/data/examples.json`).
  Rerun at these limits: 83% correct (72% to 93%), unchanged.
- Signals from the companies' own filings since their last 10-K
  (`tools/fetch_10q.py`, `tools/extract_10q.py`): 10-Q risk factor updates,
  8-K items, the company's and its sector's trend.
- 808 forecasts for 101 companies over 8 themes (v2's six plus interest rates
  and credit, government shutdown and spending), each with its top reason.
- Baselines B0 (each theme's share) and B1 (plus the company's trend), a
  logistic model, scored one year back out of sample (`tools/forecast.py`).
- A scorer that refuses any forecast frozen on or after a company's filing
  date, and a CI check that fails if a frozen forecast changes.
- `forecast.html`, gated (tasteskill PASS) and linked from every page.

**Result.** 30 of 102 companies wrote new 10-Q risk text since their latest
10-K. Backtest Brier: model 0.166 (0.151 to 0.181), B0 0.182, B1 0.178; model
minus B0 -0.017 (-0.028 to -0.005). API spend $0.14.

**Limits.** The edge over the base rate is modest. Base rates assume next year
adds each theme about as often as this year. The 10-Q section could not be
read for 12 companies. The real score exists only after the Feb to Mar 2027
filings. Frozen 2026-11-17 in commit 950eaa9 (`Forecast frozen 2026-11-17`),
before any of the forecast 10-Ks was filed; CI fails if the file changes.

## v4: in progress

Plan: `../../portfolio/RISK-RADAR-V4-PLAN.md` in the author's workspace;
summary here when it ships.
