# Risk Radar v2: build plan

Written Nov 15 2026 for a fresh session. Read this, then `RESUME-HERE.md`.
Live v1: https://risk-radar-ten.vercel.app (Vercel, deploys on push to master).

## The story in one line

What are America's biggest companies worried about this year? Every S&P 100
annual report, compared with last year's, plus an AI analyst that answers
questions about them with the exact sentences as proof, and a published
measurement of how often it is right.

Recruiter view: "he built an AI analyst over every S&P 100 annual report."
Hiring manager view: filing pipeline, hybrid retrieval, a tool-using agent
with refusals, cost and abuse controls, and an evaluation with real numbers.

## (a) Story front page

Lead with three findings from `site/data/findings.json` (counts are companies
that added or expanded risks on the theme, of 102):

| Theme | Up | Down |
|---|---|---|
| Artificial intelligence | 80 | 11 |
| Tariffs and trade | 61 | 5 |
| Cybersecurity | 56 | 8 |

Each finding: one plain sentence, the count, two or three company examples
(the `examples` already hold the sentence and risk id), and one click to the
sentence highlighted in its filing. China, export controls and climate stay
reachable but below the fold; COVID and ESG are cut. The browse/search view
from v1 moves to a second page.

## (b) "Ask the filings" agent

- **Runtime:** a Vercel serverless function (Node) at `/api/ask`. The site
  stays static; only this route runs code.
- **Retrieval:** hybrid over risk-factor chunks: BM25 (`src/harness/bm25.py`
  logic) plus dense, fused with RRF (`fusion.py`). Chunk embeddings are
  precomputed offline into a static index file. Decision needed at build
  time: `neural.py` uses sentence-transformers, too big for a function, so the
  query is embedded with the same bge-small model through transformers.js
  (quantized ONNX, about 35 MB). Recommended over a paid embedding API: one
  model, no extra vendor, matches the offline vectors.
- **Tools the model can call:** `search(query, ticker?, year?)`,
  `get_company(ticker)` (its risks and their change status),
  `compare_years(ticker, risk_id)` (last year's vs this year's text).
- **Answer contract:** every claim carries a citation to a sentence id the
  tools returned; the function checks each cited id exists in the retrieved
  set and drops any answer that cites something it did not retrieve. If the
  filings do not support an answer, it says so. No outside knowledge.
- **Abuse and cost:** per-IP rate limit (for example 10 questions a day),
  a global daily cap, max tokens per answer, an Anthropic workspace spend
  limit as the hard stop, and a banner that falls back to search when the cap
  is hit.
- **Model:** chosen by the eval in (c), between Haiku 5.5 and Sonnet 5.5, on
  accuracy per dollar. Not chosen up front.

## (c) Evaluation: "How we know it's right"

- **Golden set:** about 60 questions written and answered by Joaquin, with the
  sentence ids that answer each one, about 15% unanswerable. No
  model-written questions or labels: if a model writes the test, the test
  grades itself. `tools/label.py` already enforces this.
- **Metrics:** retrieval recall@k and nDCG@k per rung (BM25, dense, hybrid,
  hybrid plus reranker if it fits), answer accuracy, citation accuracy (does
  the cited sentence support the claim), abstention rate on unanswerable
  questions, cost and p50/p95 latency per answer, for each candidate model.
  Bootstrap CIs (`ir_metrics.py`).
- **Published** as a page on the site: the numbers, the CIs, five failure
  cases quoted verbatim, and what was changed because of them.
- The v1 matcher and tagger numbers move to this page too, with their
  existing caveat that they were checked by two AI labellers.

## (d) Redesign

Joaquin's ideas, to be collected before any visual work. The v1 page is not
the base to polish.

## (e) Cleanup

- The September retrieval harness stops being a separate half-project: it
  becomes the agent's retrieval layer and its eval.
- Rename the remaining `sec-10k-retrieval-evals` references to Risk Radar.
- README rewritten around the new story, in Joaquin's own words (drafts in
  `Employment/portfolio/risk-radar-drafts/` are a starting point only).

## (f) Order of work

1. Joaquin: write and label the ~60 golden questions (`python3 tools/label.py`;
   about 45 to 60 minutes). Can run in parallel with step 2.
2. Build retrieval over the 102-company corpus and score the ladder.
3. Build `/api/ask` with tools, citation check and caps; run it locally.
4. Run the eval across models; pick the model; write the eval page.
5. Story front page.
6. Redesign with Joaquin's ideas.
7. README and cleanup; deploy (push to master).

Joaquin must supply: the ~60 labels; an Anthropic API key with a spend limit,
added by him in Vercel → Project → Settings → Environment Variables as
`ANTHROPIC_API_KEY` (Claude never handles the key); his design ideas.

Rules that still hold: commits as Joaquin Ramirez, no AI attribution; deploy
on Vercel only; verified numbers only, quoted byte-identical everywhere.
