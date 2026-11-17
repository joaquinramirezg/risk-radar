// Precompute the answers to the example buttons on ask.html, once, into
// site/data/examples.json. The page serves those from the file with no API
// call, so a visitor who only clicks an example costs nothing.
//   node api/_tools/examples.mjs     # needs ANTHROPIC_API_KEY, about $0.003
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ask } from "../_lib/agent.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const html = readFileSync(join(ROOT, "site", "ask.html"), "utf8");
const block = html.match(/class="ask-try"[\s\S]*?<\/div>/)[0];
const questions = [...block.matchAll(/data-q="([^"]+)"/g)].map((m) => m[1]);
const out = { made: new Date().toISOString().slice(0, 10), answers: {} };
let usd = 0;
for (const q of questions) {
  const r = await ask(q);
  if (r.rejected) throw new Error(`${q}: ${r.rejected}`);
  out.answers[q] = { answer: r.answer, sources: r.sources, abstained: r.abstained, model: r.model, usage: { usd: r.usage.usd, ms: r.usage.ms } };
  usd += r.usage.usd;
  console.log(q, `$${r.usage.usd.toFixed(4)}`);
}
writeFileSync(join(ROOT, "site", "data", "examples.json"), JSON.stringify(out, null, 1));
console.log(`total $${usd.toFixed(4)}`);
