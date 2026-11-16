// Tests for the shipped Ask code. No network, no API key: the model is a stub.
//   node --test tests/js/*.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { ask, checkCitations, cost } from "../../api/_lib/agent.js";
import { bm25Search, load, rrf, search, tokenize } from "../../api/_lib/retrieval.js";

test("tokenize matches the Python harness: lowercase, alphanumeric, short stopword list", () => {
  assert.deepEqual(tokenize("The Company's AI-related risks, in 2025."), ["company", "s", "ai", "related", "risks", "2025"]);
});

test("BM25 honours a ticker filter and ranks a distinctive phrase first", () => {
  const { passages, risks } = load();
  const hits = bm25Search("Trulicity patent data protections", (i) => passages[i].ticker === "LLY", 5);
  assert.ok(hits.length > 0);
  assert.ok(hits.every((i) => passages[i].ticker === "LLY"));
  assert.match(risks.get(passages[hits[0]].risk).title, /intellectual property/i);
});

test("search with changedOnly never returns an unchanged risk", () => {
  const { passages, risks } = load();
  const hits = search({ query: "cybersecurity breach", changedOnly: true, mode: "bm25", k: 20 });
  assert.ok(hits.every((i) => risks.get(passages[i].risk).status !== "unchanged"));
});

test("RRF rewards agreement between rankers and is deterministic", () => {
  const fused = rrf([[1, 2, 3], [2, 9, 1]], 3);
  assert.equal(fused[0], 2); // 1/62 + 1/61 beats 1/61 + 1/63
  assert.equal(fused[1], 1);
  assert.deepEqual(rrf([[1, 2, 3], [2, 9, 1]], 3), fused);
});

test("checkCitations flags numbers the tools never returned", () => {
  const book = { items: [{}, {}] };
  assert.deepEqual(checkCitations("A [S1]. B [S2][S1].", book), { cited: [1, 2], bad: [] });
  assert.deepEqual(checkCitations("C [S3].", book).bad, [3]);
});

test("cost uses the per-model price table", () => {
  const u = { input_tokens: 1e6, output_tokens: 1e6 };
  assert.equal(cost("claude-haiku-5-5", u), 0.6);
  assert.equal(cost("claude-sonnet-5-5", u), 12);
});

// A stub model: first turn calls get_company, second turn writes the given text.
function stub(finalText) {
  let turn = 0;
  return {
    messages: {
      create: async () => {
        turn += 1;
        if (turn === 1) {
          return { stop_reason: "tool_use", usage: {}, content: [{ type: "tool_use", id: "t1", name: "get_company", input: { ticker: "GM" } }] };
        }
        return { stop_reason: "end_turn", usage: {}, content: [{ type: "text", text: finalText }] };
      },
    },
  };
}

test("an answer citing returned sentences comes back renumbered with its sources", async () => {
  const out = await ask("What changed at GM?", { client: stub("GM added a tariff risk [S1].") });
  assert.equal(out.rejected, null);
  assert.equal(out.answer, "GM added a tariff risk [1].");
  assert.equal(out.sources.length, 1);
  assert.equal(out.sources[0].ticker, "GM");
});

test("an answer citing a sentence the tools never returned is blocked", async () => {
  const out = await ask("What changed at GM?", { client: stub("Something invented [S999].") });
  assert.ok(out.rejected);
  assert.equal(out.sources.length, 0);
  assert.equal(out.abstained, true);
  assert.doesNotMatch(out.answer, /invented/);
});

test("an answer with no citations counts as declining", async () => {
  const out = await ask("Should I buy GM?", { client: stub("I can only answer questions about the filings.") });
  assert.equal(out.abstained, true);
});
