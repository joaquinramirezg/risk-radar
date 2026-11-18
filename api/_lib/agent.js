// "Ask the filings": a small tool-using agent over the S&P 100 risk factors.
//
// The model sees only what its tools return. Every sentence a tool returns is
// numbered S1, S2, ... for this request, and the answer must cite those
// numbers. After the model finishes, every citation is checked against the
// set of sentences actually retrieved in this request; an answer that cites
// anything else is rejected, never shown. The real sentence ids stay on the
// server, so the model cannot cite a sentence it never saw.
import Anthropic from "@anthropic-ai/sdk";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { embedQuery } from "./embed.js";
import { load, search } from "./retrieval.js";

const SITE_DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "site", "data");
let findings = null;
const themes = () => (findings ??= JSON.parse(readFileSync(join(SITE_DATA, "findings.json"), "utf8")).themes);
// Terms that faded: ESG and COVID-19, counted by tools/faded.py (who had the term last year, who dropped it).
let fadedTerms = null;
const faded = () => (fadedTerms ??= JSON.parse(readFileSync(join(SITE_DATA, "faded.json"), "utf8")));

// USD per million tokens (input, output, cache read, cache write).
export const PRICES = {
  "claude-haiku-5-5": [0.1, 0.5, 0.01, 0.125],
  "claude-sonnet-5-5": [2, 10, 0.1, 2.5],
};
export const DEFAULT_MODEL = process.env.ASK_MODEL || "claude-haiku-5-5";
export const LIMITS = { maxTurns: 4, maxTokens: 800, perSearch: 8, maxQuestionChars: 300 };

const SYSTEM = `You answer questions about the risk factors (Item 1A) in the latest annual reports (10-K) of the 102 companies in the S&P 100, compared with the year before. You have tools that search those filings. You know nothing else: no news, no prices, no financial figures beyond what a returned sentence states, no opinions, no advice.

How to work:
- Search before answering. Use get_company when a question names one company, compare_years when it asks what changed in a specific risk, and theme_trend for "how many companies" questions about AI, tariffs and trade, cybersecurity, China, export controls, climate, ESG or COVID-19. A count from theme_trend must be cited like any other claim. Use at most 4 tool calls.
- Tool results number each sentence like [S7]. Cite the sentences that support each claim, right after the claim, like [S7] or [S7][S9]. Cite only numbers that appear in tool results. Quote short phrases from the filing when the exact wording matters.
- If the returned sentences do not answer the question, say plainly that the filings do not say, and stop. Never fill a gap from general knowledge. A partial answer is fine if you say what is missing.
- If the question is not about these companies' risk factors (investment advice, predictions, other companies, anything else), say what you can answer instead, in one sentence, with no citations.
- Answer in plain English for a general reader, in 2 to 6 sentences. No headings, no bullet lists, no preamble.`;

export const TOOLS = [
  {
    name: "search_filings",
    description:
      "Hybrid keyword and semantic search over this year's risk factor text. Returns the best passages with numbered sentences. Optionally restrict to tickers, or to risks that changed since last year.",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "What to look for, in plain words." },
        tickers: { type: "array", items: { type: "string" }, description: "Optional ticker symbols, e.g. [\"AAPL\"]." },
        changed_only: { type: "boolean", description: "Only risks that are new or changed since last year." },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "get_company",
    description:
      "One company's filings: dates, how many risks were new, removed, rewritten or edited, and the titles of the risks that changed, each with its risk_id.",
    input_schema: {
      type: "object",
      properties: { ticker: { type: "string" } },
      required: ["ticker"],
      additionalProperties: false,
    },
  },
  {
    name: "compare_years",
    description:
      "This year's and last year's text of one risk factor, with numbered sentences, and the change label. risk_id comes from get_company or search_filings.",
    input_schema: {
      type: "object",
      properties: { risk_id: { type: "string" } },
      required: ["risk_id"],
      additionalProperties: false,
    },
  },
  {
    name: "theme_trend",
    description:
      "Across all 102 companies: how many added or expanded risk language on a theme this year, how many cut it, and which. Themes: Artificial intelligence, Tariffs and trade, Cybersecurity, China, Export controls, Climate. Also ESG and COVID-19: how many companies used the term last year, how many dropped it entirely this year, and which.",
    input_schema: {
      type: "object",
      properties: { theme: { type: "string" } },
      required: ["theme"],
      additionalProperties: false,
    },
  },
];

// One request's citation book: S-numbers handed to the model, and what they point to.
class Book {
  constructor() {
    this.byKey = new Map();
    this.items = [];
  }
  add(item) {
    const key = item.id;
    if (!this.byKey.has(key)) {
      this.items.push(item);
      this.byKey.set(key, this.items.length);
    }
    return `S${this.byKey.get(key)}`;
  }
}

function sentenceLines(book, risk, from, to, prev = false) {
  const { companies } = load();
  const sents = prev ? splitPrev(risk.previous) : risk.sentences;
  const out = [];
  for (let n = from; n < Math.min(to, sents.length); n++) {
    const tag = book.add({
      id: `${risk.id}.${prev ? "p" : ""}${n}`, kind: prev ? "previous" : "current",
      ticker: risk.ticker, company: companies[risk.ticker].name, risk: risk.id,
      title: prev ? risk.old_title || risk.title : risk.title, status: risk.status, text: sents[n],
    });
    out.push(`[${tag}] ${sents[n]}`);
  }
  return out.join(" ");
}

const splitPrev = (t) =>
  (t || "").split(/\n\s*\n/).flatMap((p) => p.replace(/\s+/g, " ").trim().split(/(?<=[.?!])\s+(?=[A-Z0-9“"(])/)).filter(Boolean);

const shortRisk = (risk) => risk.id.split(".")[1];

function findRisk(rid) {
  const { risks } = load();
  if (risks.has(rid)) return risks.get(rid);
  for (const r of risks.values()) if (r.id.endsWith(`.${rid}`)) return r;
  return null;
}

async function runTool(name, input, book, trace) {
  const { passages, risks, companies } = load();
  if (name === "search_filings") {
    const q = String(input.query || "").slice(0, 300);
    const tickers = (input.tickers || []).map((t) => String(t).toUpperCase()).filter((t) => companies[t]);
    const qvec = await embedQuery(q);
    const hits = search({ query: q, qvec, ticker: tickers.length ? tickers : null, changedOnly: !!input.changed_only, k: LIMITS.perSearch });
    trace.retrieved.push(...hits.map((i) => passages[i].risk));
    if (!hits.length) return "No passages matched.";
    return hits
      .map((i) => {
        const p = passages[i];
        const r = risks.get(p.risk);
        return `${r.ticker} (${companies[r.ticker].name}) | risk_id ${r.id} | ${r.status} since last year\nTitle: ${r.title}\n${sentenceLines(book, r, p.s0, p.s1)}`;
      })
      .join("\n\n");
  }
  if (name === "get_company") {
    const t = String(input.ticker || "").toUpperCase();
    const c = companies[t];
    if (!c) return `No company with ticker ${t} in the S&P 100 set. Companies: ${Object.keys(companies).join(", ")}.`;
    const changed = [...risks.values()].filter((r) => r.ticker === t && r.status !== "unchanged");
    const lines = changed.map((r) => {
      const tag = book.add({ id: `${r.id}.title`, kind: "title", ticker: t, company: c.name, risk: r.id, title: r.title, status: r.status, text: r.title });
      return `[${tag}] ${r.status}${r.change ? ` (${r.change.replace("_", " ")})` : ""} | risk_id ${r.id} | ${r.title}`;
    });
    return `${c.name} (${t}). This year's 10-K for the period ending ${c.current.period_end}, filed ${c.current.filed}; compared with the one for ${c.previous.period_end}.\nCounts: ${JSON.stringify(c.counts)}\nRisks that changed (the [S] tag cites the risk's title):\n${lines.join("\n")}`;
  }
  if (name === "compare_years") {
    const r = findRisk(String(input.risk_id || ""));
    if (!r) return "Unknown risk_id. Get one from get_company or search_filings.";
    trace.retrieved.push(r.id);
    const cur = r.sentences.length ? sentenceLines(book, r, 0, 40) : "(not in this year's filing)";
    const prev = r.previous ? sentenceLines(book, r, 0, 40, true) : "(not in last year's filing)";
    return `${r.ticker} | ${r.status}${r.change ? ` | change type: ${r.change.replace("_", " ")}` : ""}\nThis year, "${r.title}":\n${cur}\n\nLast year, "${r.old_title || r.title}":\n${prev}`;
  }
  if (name === "theme_trend") {
    const want = String(input.theme || "").toLowerCase();
    const fd = faded().find((x) => want.includes(x.theme.toLowerCase().split("-")[0]) || (x.theme === "ESG" && /environmental, social|sustainab/.test(want)));
    if (fd) {
      const tag = book.add({
        id: `faded.${fd.theme}`, kind: "theme", ticker: null, company: null, risk: null, title: fd.theme, status: null,
        text: `${fd.had} of 102 companies used ${fd.theme} language in last year's risk factors; ${fd.gone} dropped it entirely this year, and ${fd.down} used it less. ${fd.up} used it more.`,
      });
      const ex = fd.examples.slice(0, 3).map((e) => {
        const t = book.add({
          id: `faded.${fd.theme}.${e.ticker}`, kind: "previous", ticker: null, company: e.company, risk: null,
          title: `${e.company} (${e.ticker}), last year's wording, gone this year`, status: "removed", text: e.sentence,
        });
        return `[${t}] ${e.ticker} (${e.company}), last year: ${e.sentence}`;
      });
      return `[${tag}] ${fd.had} of 102 companies used ${fd.theme} language in last year's risk factors; ${fd.gone} dropped it entirely this year; ${fd.down} used it less; ${fd.up} used it more.\nDropped it entirely: ${fd.tickers_gone.join(", ")}\nExamples of last year's wording that is gone:\n${ex.join("\n")}`;
    }
    const th = themes().find((x) => x.theme.toLowerCase().includes(want) || want.includes(x.theme.toLowerCase().split(" ")[0]));
    if (!th) return `Unknown theme. Themes: ${themes().map((x) => x.theme).join(", ")}.`;
    const tag = book.add({
      id: `theme.${th.theme}`, kind: "theme", ticker: null, company: null, risk: null, title: th.theme, status: null,
      text: `${th.companies_up} of 102 companies added or expanded risk language on ${th.theme.toLowerCase()} this year; ${th.companies_down} cut or softened it.`,
    });
    const ex = th.examples.slice(0, 4).map((e) => {
      const r = findRisk(`${e.ticker}.${e.id}`);
      const n = r ? r.sentences.indexOf(e.sentence) : -1;
      if (n < 0) return `${e.ticker}: ${e.title}`;
      return `${e.ticker} (${e.company}), risk_id ${r.id}: ${sentenceLines(book, r, n, n + 1)}`;
    });
    return `[${tag}] ${th.companies_up} of 102 companies added or expanded risk language on ${th.theme} this year (${th.risks_up} risk factors); ${th.companies_down} cut or softened it.\nCompanies up: ${th.tickers_up.join(", ")}\nExamples:\n${ex.join("\n")}`;
  }
  return `Unknown tool ${name}.`;
}

const CITE = /\[S(\d+)\]/g;

export function checkCitations(text, book) {
  const cited = [...text.matchAll(CITE)].map((m) => Number(m[1]));
  const bad = cited.filter((n) => n < 1 || n > book.items.length);
  return { cited: [...new Set(cited)], bad };
}

export function cost(model, u) {
  const [i, o, cr, cw] = PRICES[model] || PRICES[DEFAULT_MODEL];
  return (
    ((u.input_tokens || 0) * i + (u.output_tokens || 0) * o + (u.cache_read_input_tokens || 0) * cr + (u.cache_creation_input_tokens || 0) * cw) / 1e6
  );
}

const REFUSAL = "The filings do not answer that, so I would rather not guess.";

/** Answer one question. Returns { answer, sources, abstained, usage, trace }. */
export async function ask(question, { model = DEFAULT_MODEL, effort = "low", client = new Anthropic() } = {}) {
  const t0 = Date.now();
  const q = String(question || "").trim().slice(0, LIMITS.maxQuestionChars);
  const book = new Book();
  const trace = { retrieved: [], tools: [] };
  const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
  const messages = [{ role: "user", content: q }];
  let text = "";
  let stop = null;

  for (let turn = 0; turn < LIMITS.maxTurns; turn++) {
    const res = await client.messages.create({
      model,
      max_tokens: LIMITS.maxTokens,
      system: [{ type: "text", text: SYSTEM, cache_control: { type: "ephemeral" } }],
      tools: TOOLS,
      output_config: { effort },
      messages,
    });
    for (const k of Object.keys(usage)) usage[k] += res.usage?.[k] || 0;
    stop = res.stop_reason;
    messages.push({ role: "assistant", content: res.content });
    if (stop !== "tool_use") {
      text = res.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
      break;
    }
    const calls = res.content.filter((b) => b.type === "tool_use");
    const results = [];
    for (const c of calls) {
      trace.tools.push({ name: c.name, input: c.input });
      let out;
      try {
        out = await runTool(c.name, c.input, book, trace);
      } catch (e) {
        out = `Tool error: ${e.message}`;
      }
      results.push({ type: "tool_result", tool_use_id: c.id, content: out });
    }
    // The last allowed turn tells the model to answer from what it has.
    if (turn === LIMITS.maxTurns - 2) results.push({ type: "text", text: "Tool budget reached. Answer now from the sentences above, or say the filings do not say." });
    messages.push({ role: "user", content: results });
  }

  const { cited, bad } = checkCitations(text, book);
  let abstained = cited.length === 0;
  let rejected = null;
  if (stop === "refusal" || !text) {
    text = REFUSAL;
    abstained = true;
  } else if (bad.length) {
    rejected = `cited S${bad.join(", S")} which no tool returned`;
    text = "I could not back that answer with sentences from the filings, so I am not showing it.";
    abstained = true;
  }
  // Renumber citations 1..n in order of first use, and return only those sources.
  const order = [];
  const answer = rejected
    ? text
    : text.replace(CITE, (_, n) => {
        let k = order.indexOf(Number(n));
        if (k < 0) k = order.push(Number(n)) - 1;
        return `[${k + 1}]`;
      });
  const sources = order.map((n, k) => ({ n: k + 1, ...book.items[n - 1] }));
  return {
    answer,
    sources,
    abstained,
    rejected,
    model,
    usage: { ...usage, usd: cost(model, usage), ms: Date.now() - t0 },
    trace,
  };
}
