// POST /api/ask {question} -> {answer, sources, abstained, usage}
//
// Cost and abuse controls, from cheapest to hardest:
//   0. the example questions on ask.html are answered from site/data/examples.json, no call
//   1. question length capped, answers to repeated questions served from memory
//   2. per-IP limit (IP_DAILY) and an instance-wide daily cap (DAILY_CAP)
//   3. at most 4 model turns and 800 output tokens a turn (agent.js LIMITS)
//   4. a monthly spend limit on the Anthropic workspace ($2): the hard stop
// At 60 answers a day and about $0.001 an answer, the worst case is under $2 a month.
// Limits 1 and 2 live in this instance's memory, so they reset when Vercel
// starts a new instance; the workspace spend limit is what cannot be bypassed.
import { ask, LIMITS } from "./_lib/agent.js";

const IP_DAILY = Number(process.env.IP_DAILY || 5);
const DAILY_CAP = Number(process.env.DAILY_CAP || 60);
const day = () => new Date().toISOString().slice(0, 10);
let state = { day: day(), total: 0, perIp: new Map() };
const answers = new Map(); // normalized question -> response

function json(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

async function readBody(req) {
  if (req.body && typeof req.body === "object") return req.body;
  let raw = "";
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 4000) break;
  }
  try {
    return JSON.parse(raw || "{}");
  } catch {
    return {};
  }
}

export default async function handler(req, res) {
  if (req.method !== "POST") return json(res, 405, { error: "POST only" });
  if (!process.env.ANTHROPIC_API_KEY) return json(res, 503, { error: "offline", message: "Ask is not switched on yet. Search still works." });

  const { question } = await readBody(req);
  const q = String(question || "").trim();
  if (q.length < 8) return json(res, 400, { error: "short", message: "Ask a full question." });
  if (q.length > LIMITS.maxQuestionChars) return json(res, 400, { error: "long", message: `Keep it under ${LIMITS.maxQuestionChars} characters.` });

  const key = q.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ");
  if (answers.has(key)) return json(res, 200, { ...answers.get(key), cached: true });

  if (state.day !== day()) state = { day: day(), total: 0, perIp: new Map() };
  const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "unknown";
  const used = state.perIp.get(ip) || 0;
  if (used >= IP_DAILY) return json(res, 429, { error: "ip_limit", message: `That is ${IP_DAILY} questions today from your connection. Search still works, and Ask resets tomorrow.` });
  if (state.total >= DAILY_CAP) return json(res, 429, { error: "daily_cap", message: "Ask has used today's budget. The examples and search still work, and Ask resets tomorrow." });
  state.perIp.set(ip, used + 1);
  state.total += 1;

  try {
    const out = await ask(q);
    const body = { answer: out.answer, sources: out.sources, abstained: out.abstained, model: out.model, usage: out.usage };
    if (answers.size > 500) answers.delete(answers.keys().next().value);
    answers.set(key, body);
    return json(res, 200, body);
  } catch (e) {
    const status = e?.status === 429 || e?.status === 529 ? 503 : 500;
    console.error("ask failed", e?.status, e?.message);
    return json(res, status, { error: "upstream", message: "Ask is unavailable right now. Search still works." });
  }
}
