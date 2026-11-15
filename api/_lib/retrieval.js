// Hybrid retrieval over this year's risk factors: BM25 plus dense (bge-small,
// int8 vectors), fused with reciprocal rank fusion. A port of
// src/harness/bm25.py and fusion.py, kept line-for-line equivalent so the
// Python tests describe this code too. The eval (api/_tools/eval.mjs) calls
// these exact functions, so the published numbers measure what ships.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "_data");
export const DIM = 384;
export const RRF_K = 60; // Cormack et al. (2009); not tuned on this set

const STOP = new Set(
  "a an and are as at be by for from has have in is it its of on or that the this to was were will with".split(" "),
);
export const tokenize = (t) => (t.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => !STOP.has(w));

let cache = null;

export function load() {
  if (cache) return cache;
  const corpus = JSON.parse(readFileSync(join(DATA, "corpus.json"), "utf8"));
  const risks = new Map(corpus.risks.map((r) => [r.id, r]));
  const passages = corpus.passages.map((p) => {
    const r = risks.get(p.risk);
    return { ...p, ticker: r.ticker, text: `${r.title}\n${r.sentences.slice(p.s0, p.s1).join(" ")}` };
  });
  let vecs = null;
  try {
    const buf = readFileSync(join(DATA, "vectors.i8"));
    vecs = new Int8Array(buf.buffer, buf.byteOffset, buf.byteLength);
    if (vecs.length !== passages.length * DIM) vecs = null;
  } catch {
    vecs = null;
  }
  cache = { ...corpus, risks, passages, vecs, bm25: buildBm25(passages.map((p) => p.text)) };
  return cache;
}

function buildBm25(texts, k1 = 1.5, b = 0.75) {
  const post = new Map(); // term -> [[docIndex, tf], ...]
  const lens = new Float64Array(texts.length);
  texts.forEach((t, i) => {
    const tf = new Map();
    for (const w of tokenize(t)) tf.set(w, (tf.get(w) || 0) + 1);
    let n = 0;
    for (const [w, f] of tf) {
      n += f;
      if (!post.has(w)) post.set(w, []);
      post.get(w).push([i, f]);
    }
    lens[i] = n;
  });
  const avgdl = lens.reduce((a, x) => a + x, 0) / lens.length;
  const N = texts.length;
  const idf = new Map();
  for (const [w, list] of post) idf.set(w, Math.max(0, Math.log((N - list.length + 0.5) / (list.length + 0.5) + 1)));
  return { post, lens, avgdl, idf, k1, b };
}

function rank(scores, ids, k) {
  const order = [...scores.keys()].sort((a, b) => scores.get(b) - scores.get(a) || (ids[a] < ids[b] ? -1 : 1));
  return order.slice(0, k);
}

export function bm25Search(query, allowed, k) {
  const { bm25, passages } = load();
  const scores = new Map();
  for (const w of tokenize(query)) {
    const list = bm25.post.get(w);
    if (!list) continue;
    const idf = bm25.idf.get(w);
    for (const [i, f] of list) {
      if (allowed && !allowed(i)) continue;
      const dl = bm25.lens[i] || 1;
      const s = (idf * (f * (bm25.k1 + 1))) / (f + bm25.k1 * (1 - bm25.b + (bm25.b * dl) / bm25.avgdl));
      scores.set(i, (scores.get(i) || 0) + s);
    }
  }
  for (const [i, s] of scores) if (s <= 0) scores.delete(i);
  return rank(scores, passages.map((p) => p.id), k);
}

export function denseSearch(qvec, allowed, k) {
  const { vecs, passages } = load();
  if (!vecs) return [];
  const q = Float32Array.from(qvec);
  const scores = new Map();
  for (let i = 0; i < passages.length; i++) {
    if (allowed && !allowed(i)) continue;
    let s = 0;
    const off = i * DIM;
    for (let d = 0; d < DIM; d++) s += vecs[off + d] * q[d];
    scores.set(i, s);
  }
  return rank(scores, passages.map((p) => p.id), k);
}

export function rrf(rankings, k, rrfK = RRF_K) {
  const { passages } = load();
  const scores = new Map();
  for (const r of rankings) r.forEach((i, n) => scores.set(i, (scores.get(i) || 0) + 1 / (rrfK + n + 1)));
  return rank(scores, passages.map((p) => p.id), k);
}

const BREADTH = 50; // each ranker's list length before fusion

// mode: "bm25" | "dense" | "hybrid". Returns passage indexes, best first.
export function search({ query, qvec, ticker, changedOnly, k = 8, mode = "hybrid" }) {
  const { passages, risks } = load();
  const tickers = ticker ? new Set([].concat(ticker).map((t) => t.toUpperCase())) : null;
  const allowed =
    tickers || changedOnly
      ? (i) => {
          const p = passages[i];
          if (tickers && !tickers.has(p.ticker)) return false;
          if (changedOnly && risks.get(p.risk).status === "unchanged") return false;
          return true;
        }
      : null;
  if (mode === "bm25") return bm25Search(query, allowed, k);
  if (mode === "dense") return denseSearch(qvec, allowed, k);
  return rrf([bm25Search(query, allowed, BREADTH), denseSearch(qvec, allowed, BREADTH)], k);
}
