// GET /api/health -> 200 {ok: true} when Ask can reach the model, 503 otherwise.
//
// It lists the models on the configured key, which costs no tokens, so the
// uptime workflow (.github/workflows/uptime.yml) can call it as often as it
// likes for free. A rejected key, a spent workspace limit or an Anthropic
// outage all show up here before a visitor sees "Ask is unavailable".
import Anthropic from "@anthropic-ai/sdk";

export default async function handler(req, res) {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  const send = (status, body) => {
    res.statusCode = status;
    res.end(JSON.stringify(body));
  };
  if (!process.env.ANTHROPIC_API_KEY) return send(503, { ok: false, reason: "no key set" });
  try {
    await new Anthropic().models.list({ limit: 1 });
    return send(200, { ok: true });
  } catch (e) {
    return send(503, { ok: false, reason: e?.status === 401 ? "key rejected" : `upstream ${e?.status || "error"}` });
  }
}
