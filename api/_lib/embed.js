// Query and passage embeddings: BAAI/bge-small-en-v1.5, quantized ONNX, run
// locally through transformers.js. The same model file embeds the corpus
// offline (api/_tools/embed.mjs) and the question at request time, so the two
// sides of every cosine come from identical weights. No embedding vendor.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { env, pipeline } from "@huggingface/transformers";

export const MODEL = "Xenova/bge-small-en-v1.5";
// bge is trained to see this prefix on queries, not on passages.
export const QUERY_PREFIX = "Represent this sentence for searching relevant passages: ";

env.localModelPath = join(dirname(fileURLToPath(import.meta.url)), "..", "_model");
env.allowRemoteModels = process.env.ALLOW_MODEL_DOWNLOAD === "1";
env.cacheDir = env.localModelPath;

let extractor = null;
async function get() {
  extractor ??= await pipeline("feature-extraction", MODEL, { dtype: "q8" });
  return extractor;
}

export async function embed(texts) {
  const ex = await get();
  const out = await ex(texts, { pooling: "cls", normalize: true });
  return out.tolist();
}

export async function embedQuery(q) {
  return (await embed([QUERY_PREFIX + q]))[0];
}
