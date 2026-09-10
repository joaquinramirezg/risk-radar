# sec-10k-retrieval-evals

A hand-labelled retrieval eval harness over SEC 10-K Item 1A risk-factor
sections.

STATUS: in progress. The harness runs end to end; the golden set is being
labelled. No numbers here are citable until `make eval` stops printing the
incomplete-golden-set warning.

<!-- Joaquin: the prose below is deliberately unwritten. A reviewer can spot
generated README copy immediately, and for a candidate whose pitch is real
production judgement that is fatal. Write these sections yourself once the
numbers exist. The required order, from the research:
  1. one sentence on what and why
  2. the headline result WITH its n, and one table, above the fold
  3. reproduce in three commands
  4. architecture, one diagram
  5. eval methodology and results
  6. failure modes and known limitations
  7. decisions and tradeoffs (link DECISIONS.md)
  8. what I would do next and why I did not
-->

## Reproduce

    make test      # 35 tests, no install, no network, no API key
    make eval      # deterministic retrieval metrics with bootstrap CIs

## What is deliberate here

- The retrieval half has no dependencies and no LLM, so every number in it is
  checkable by hand. Generation quality rests on a judge; retrieval must not.
- Recall and nDCG raise `ValueError` on a question with no gold chunk rather
  than scoring it 0.0. Unanswerable questions are counted in a separate
  abstention block, because folding them into recall misreports both numbers.
- Confidence intervals are percentile bootstrap, not normal-approximation,
  because the set is well under n=100 where that approximation is unsafe.
- The golden set validator refuses to produce citable numbers below 50 items
  or below roughly 10% unanswerable.
- `tools/label.py` has no question-generation mode, on purpose. If a model
  writes the questions and the labels, the evaluation is circular.

## Known limitations

To be written honestly once the numbers exist: n, single annotator, single
sector, judge validated on which failure modes, and the width of the intervals.
