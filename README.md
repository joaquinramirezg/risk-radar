# Risk Radar

What are America's 100 biggest companies suddenly worried about? Every S&P 100
annual report (10-K, Item 1A risk factors), compared with last year's sentence
by sentence, plus an agent that answers questions about them with the exact
sentences as proof, and a published measurement of how often it is right.

Live: https://risk-radar-ten.vercel.app

## Results

Ask the filings, on Claude Haiku 5.5 (low effort), over 63 test questions
(54 answerable, 9 deliberately unanswerable). 95% bootstrap intervals.

| Measure | Result |
|---|---|
| Answers correct, graded against the reference answer | 83% (72% to 93%) |
| Correct or partly correct | 94% (87% to 100%) |
| Claims fully backed by the sentence they cite | 80% (74% to 87%), 122 of 152 |
| Unanswerable questions declined | 9 of 9 |
| Answers citing text the search never returned | 0 |
| Cost per answer | $0.0006 |
| Typical / slowest-5% answer time | 2.3 s / 3.3 s |

Claude Sonnet 5.5 on the same questions: 93% correct, 89% of claims backed,
$0.0102 an answer. Paired against Haiku it answers 9 more in 100 correctly,
95% interval -2 to 20, at 18 times the cost, so Haiku stays. A stricter
grounding prompt on Haiku dropped correct answers to 72% and was reverted.

Search numbers are from Linux x64, the platform the live function runs on,
and CI fails if they stop reproducing. On a Mac the same code scores 87% on
the last row: ONNX arithmetic differs slightly across CPUs and flips a few
close rankings. The answer runs above were made on a Mac.

| Search method | Right risk factor in top 5 | MRR |
|---|---|---|
| Keywords only (BM25) | 46% (33% to 59%) | 0.33 |
| Meaning only (bge-small embeddings) | 57% (44% to 70%) | 0.45 |
| Both, fused (RRF) | 59% (46% to 72%) | 0.50 |
| Both, limited to the company named | 83% (72% to 93%) | 0.73 |

The test questions and reference answers were written by Claude (Opus 5.5)
from risk factors sampled one per company, and answers were graded by Claude
Sonnet 5.5; neither was checked against human labels. Every question and every
graded answer is in `data/golden/` and `results/`. Full write-up with each
failure quoted: https://risk-radar-ten.vercel.app/#eval

## How it works

1. `tools/fetch_filings.py` pulls the two latest 10-Ks per company from EDGAR;
   `tools/build_radar.py` splits Item 1A into risk factors, matches them
   year over year (bge-small, one-to-one, cosine >= 0.80), detects splits and
   merges, and labels each edit (new exposure, escalated, softened,
   boilerplate) with an LLM classifier.
2. `tools/build_ask_index.py` turns this year's risk factors into sentences
   with stable ids and ~1,000-character passages; `api/_tools/embed.mjs`
   embeds them offline with the same quantized model the server loads.
3. `api/ask.js` is the only server code: a Vercel function running a small
   tool-using agent (`search_filings`, `get_company`, `compare_years`,
   `theme_trend`). Every sentence a tool returns gets a per-request number;
   the answer must cite those numbers, and any citation the tools did not
   return blocks the answer. Per-IP and daily caps, 5 turns, 1,500 tokens a
   turn, and a workspace spend limit as the hard stop.
4. `api/_tools/eval.mjs` runs the golden set through the same search and agent
   code that ships.

## Reproduce

    make test                                  # Python tests, no install
    node api/_tools/eval.mjs retrieval         # search ladder, no API key
    node api/_tools/eval.mjs answers claude-haiku-5-5 low   # needs ANTHROPIC_API_KEY
    node api/_tools/eval.mjs report            # writes site/data/eval.json
    node api/_tools/dev.mjs                    # local site on :8787

Decisions and their reasons: `DECISIONS.md`.
