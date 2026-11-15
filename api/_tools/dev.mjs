// Local preview of the deployed site: static files from site/ plus /api/ask.
//   node api/_tools/dev.mjs          -> http://localhost:8787
// Reads ANTHROPIC_API_KEY from the environment; without it Ask says it is off.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import handler from "../ask.js";

const SITE = fileURLToPath(new URL("../../site/", import.meta.url));
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain" };

createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/api/ask") return handler(req, res);
  let path = normalize(join(SITE, decodeURIComponent(url.pathname)));
  if (!path.startsWith(SITE)) return res.writeHead(403).end();
  if (existsSync(path) && statSync(path).isDirectory()) path = join(path, "index.html");
  if (!existsSync(path) && existsSync(`${path}.html`)) path = `${path}.html`;
  if (!existsSync(path)) return res.writeHead(404).end("not found");
  res.writeHead(200, { "Content-Type": TYPES[extname(path)] || "application/octet-stream" });
  createReadStream(path).pipe(res);
}).listen(8787, () => console.log("http://localhost:8787"));
