// Embed every passage once, offline, into api/_data/vectors.i8.
//   ALLOW_MODEL_DOWNLOAD=1 node api/_tools/embed.mjs
// Vectors are unit length, stored as int8 (x * 127): 384 bytes a passage
// instead of 1,536. The eval reports the ranking cost of that rounding.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { embed } from "../_lib/embed.js";
import { DIM, load } from "../_lib/retrieval.js";

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "_data", "vectors.i8");
const { passages } = load();
const vecs = new Int8Array(passages.length * DIM);
const t0 = Date.now();
for (let i = 0; i < passages.length; i += 32) {
  const batch = passages.slice(i, i + 32).map((p) => p.text);
  const v = await embed(batch);
  v.forEach((row, j) => row.forEach((x, d) => (vecs[(i + j) * DIM + d] = Math.round(x * 127))));
  if (i % 640 === 0) process.stdout.write(`${i}/${passages.length} ${((Date.now() - t0) / 1000).toFixed(0)}s\n`);
}
writeFileSync(out, vecs);
console.log(`wrote ${passages.length} x ${DIM} int8 to ${out}`);
