// Quick manual check: node api/_tools/try.mjs "question" [TICKER]
import { embedQuery } from "../_lib/embed.js";
import { load, search } from "../_lib/retrieval.js";
const [q, t] = process.argv.slice(2);
let t0 = Date.now(); const { passages, risks } = load(); console.log("load", Date.now() - t0, "ms");
t0 = Date.now(); const v = await embedQuery(q); console.log("embed", Date.now() - t0, "ms");
for (const mode of ["bm25", "dense", "hybrid"]) {
  t0 = Date.now(); const r = search({ query: q, qvec: v, ticker: t, mode, k: 5 });
  console.log(`\n${mode} (${Date.now() - t0} ms)`);
  for (const i of r) console.log(" ", passages[i].ticker, risks.get(passages[i].risk).title.slice(0, 100));
}
