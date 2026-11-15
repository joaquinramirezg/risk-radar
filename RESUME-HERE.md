# RESUME HERE

## Nov 15 evening state (read this first)

Launch-ready: all 102 companies, in-page search over every risk factor
(site/app.js, data/search.json from tools/search_index.py), consistency
check tools/check_site.py run in CI, Vercel config (vercel.json,
docs/DEPLOY.md), link preview from tools/og/. Rebuild with `make radar`.
Left for Joaquin: README + DECISIONS from the drafts in
Employment/portfolio/risk-radar-drafts/, deploy on Vercel. Pushed to the
private repo joaquinramirezg/risk-radar on Nov 15.
181 edits have no change-type label (needs API credit, then
classify_changes.py and build_radar.py --relabel).

## Nov 15 state (earlier; the parked notes below are history)

The project is now Risk Radar: a static site (site/) showing what 98 of the
S&P 100 added, removed, split, merged and rewrote in their 10-K risk factors,
with a findings front page (tools/findings.py, each example linked to its
sentence), a measured-accuracy panel (first 20 companies, plus an
out-of-sample audit of the other 78 in tools/audit_scaled.py) and an LLM
change-type tag on each edited risk. Four companies are excluded and listed
on the site (EXCLUDED in tools/build_radar.py). After a new classifier run,
`python3 tools/build_radar.py --relabel` re-attaches tags without a rebuild.
Rebuild: `PYTHONPATH=src python3 tools/build_radar.py` (needs data/raw and
data/raw_prev, fetched by tools/fetch_filings.py). Scores:
tools/score_labels.py, tools/ablate_matcher.py, tools/score_changes.py.
Labels were made by AI labellers, by the owner's decision; say so wherever
numbers are quoted. Remaining: README and ADRs written by hand, Vercel deploy
(Nov 15 ruling: Vercel, or Render if a backend is needed; never Cloudflare).

Parked 2026-09-10. Written so this project can restart cold, with no memory of
the conversation that produced it.

## What this is, in one paragraph

A public eval harness that measures how well a retrieval-and-answer system
finds the right passage in SEC 10-K Item 1A risk-factor sections. The system
under test is ordinary agentic RAG. The DELIVERABLE IS THE MEASUREMENT, not the
RAG: a hand-labelled golden set, a baseline ladder, confidence intervals, a
validated LLM judge, and a published failure taxonomy. It becomes a fourth
pinned GitHub repo with one card linking to it from joaquinramirez.dev.

## Why this shape and not a chat demo

Decided 2026-09-10 after a research pass. Full reasoning is in
`../../portfolio/PORTFOLIO-PLAN.md` under v1.3. Short version:

1. Agentic RAG is a tutorial project now. Every framework ships one. A senior
   engineer shipping one more invites "so what". The scarce artifact is the
   measurement layer.
2. The free hosting a chat demo needs has degraded. Hugging Face gated the
   Gradio and Docker SDKs behind PRO around June 2026, Streamlit sleeps after
   12 hours with no custom domain, Render deletes its free Postgres at day 44,
   Fly.io has had no free tier since Oct 2024. A demo that breaks itself on a
   timer three months after he sends the link is worse than no demo. Hence
   static-first on Cloudflare Pages.
3. Joaquin shipped fraud detection to production, so he already thinks in
   precision and recall at a chosen threshold, cost of a false positive
   against a false negative, base rates. That is the vocabulary AI PM and
   product-DS interviews probe and almost no AI PM candidate has it. A chat box
   re-proves what his resume already says; this puts the rare skill on the table.

## Current state

Built, committed, 35 tests passing. NOT on GitHub, nothing public.

    src/harness/chunking.py    paragraph-aware chunking; carries the risk heading
                               onto every chunk; overlap never crosses a heading
    src/harness/bm25.py        Okapi BM25, no dependencies. The baseline floor.
    src/harness/ir_metrics.py  recall@k, precision@k, MRR, nDCG@k, percentile
                               bootstrap CIs
    src/harness/corpus.py      loaders plus the golden-set validator
    tools/extract_item1a.py    slices Item 1A out of a 10-K; refuses truncated output
    tools/label.py             the hand-labelling CLI
    tools/run_retrieval_eval.py  writes results/retrieval.json; --check gates CI
    tests/                     35 tests, no install, no network, no API key

Verified end to end on a synthetic corpus: extract, chunk, index, score,
bootstrap CIs, abstention block. `make test` and `make eval` both work.

## Three deliberate design choices. Do not "fix" these.

1. **Recall and nDCG raise ValueError on a question with no gold chunk** rather
   than scoring it 0.0. Unanswerable questions live in a separate abstention
   block. Folding them into recall misreports both numbers.
2. **CIs are percentile bootstrap, not normal-approximation.** The set is well
   under n=100, where the Central Limit Theorem is not a safe assumption.
3. **`tools/label.py` has no question-generation mode, on purpose.** If a model
   writes the questions and the labels, the evaluation grades itself and every
   number downstream is circular. This is the integrity core of the project.

## Bugs already found and regression-guarded. Do not reintroduce.

- A 139-character paragraph was misclassified as a heading and DELETED, so
  corpus text vanished while every metric still looked healthy. Fixed by
  `is_heading()`: single-line, under 120 chars, not ending in a period, no
  internal sentence break, with a leading item label stripped first.
  Guarded by `test_no_corpus_text_is_ever_lost`.
- Overlap bled across heading boundaries, so a chunk headed "Foreign Currency
  Exposure" opened with supplier prose. Any gold label on it would have been
  wrong in a way no metric could reveal. Guarded by
  `test_overlap_never_crosses_a_heading_boundary`.
- The table of contents also contains the string "Item 1A", so anchoring on the
  first match yields a 200-character extract. The extractor takes the longest
  candidate section and refuses anything under 4,000 characters. DO NOT lower
  `MIN_CHARS` to make a stubborn filing pass; inspect it by hand.

## Corpus: DONE 2026-11-15

The old blocker (sec.gov denied from Claude's shells) no longer applies: the
cloud shell reaches EDGAR. The latest 10-K of 20 large caps is extracted into
`data/corpus/` (1,853 chunks), with accession numbers and URLs in
`data/corpus/MANIFEST.tsv`. Every extract was checked by hand at both ends.
Extraction surfaced a real bug (later "see Item 1A" cross-references swallowing
MD&A in 10 of 20 filings); fixed and regression-guarded in `test_extract.py`.

## Exact next steps

    python3 tools/label.py --status                  # see where you are
    python3 tools/label.py                           # read a chunk, write its question
    python3 tools/label.py --unanswerable            # ~15% of the set
    make eval                                        # refuses until the set is valid

Target 60 to 100 items with about 15% unanswerable. Expect 3 to 5 hours. This is
Joaquin's work, not Claude's, and it cannot be compressed or delegated without
destroying the point of the project.

## Then, in order

1. Extend the baseline ladder: dense retrieval, then hybrid, then hybrid plus a
   reranker. Report every rung side by side. Without the ladder "agentic RAG" is
   an unfalsifiable claim.
2. Read about 30 traces by hand and derive binary pass/fail rubrics from what is
   actually there, not from a metrics catalogue.
3. Build ONE LLM judge for the most frequent failure mode and validate it
   against Joaquin's own labels, reporting true positive and true negative
   rates plus a corrected failure-rate estimate. Almost nobody publishes this
   and it is the strongest senior signal in the project.
4. Failure taxonomy table: category, frequency as n-out-of-N, one verbatim
   example, root-cause hypothesis, mitigation, status.
5. Product metrics: abstention against accuracy, citation-support rate, cost
   and tokens per query, p50 and p95 latency, intrinsic vs extrinsic
   hallucination split.
6. Write `DECISIONS.md` (three empty ADRs are waiting) and the README prose.
7. Static site on Cloudflare Pages. Optional live panel only behind Turnstile,
   a 5-per-IP-per-day and 300-per-day cap, read-only tools, and a spend cap
   that degrades to precomputed mode with an honest banner.

## Acceptance criteria

- Pass rate lands between 60 and 80 percent. A 95-plus pass rate reads as a
  weak eval set to every senior reviewer.
- Every number carries its n, and no improvement smaller than the confidence
  interval is claimed. At n=60 to 100 that interval is roughly 10 to 13 points.
- The baseline ladder is present.
- Runs from a fresh clone in three commands.
- A deliberate "Status: complete, known limitations below" note, so the repo
  reads as FINISHED rather than abandoned.

## Two traps specific to this repo

- **Keep it PRIVATE until it is finished.** A visibly half-built public repo
  reads as "does not finish things", the worst possible signal for someone
  whose constraint is that classes start.
- **Joaquin hand-writes the README and the ADRs.** Generated README copy is
  spotted immediately by reviewers, and for a candidate whose pitch is real
  production judgement that is fatal. The README body is deliberately left
  unwritten with the required section order in an HTML comment.
