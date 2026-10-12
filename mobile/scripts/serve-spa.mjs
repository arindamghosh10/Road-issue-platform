// Serve the app's web build (npx expo export --platform web) for the end-to-end tests:
// static files, and index.html for any route the app handles itself (e.g. /login).
//   node scripts/serve-spa.mjs <dist-dir> [port]
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "dist");
const port = Number(process.argv[3] ?? 8081);
const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
  ".ico": "image/x-icon", ".ttf": "font/ttf", ".woff2": "font/woff2", ".map": "application/json",
};

createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url ?? "/", "http://x").pathname));
  let file = join(root, path);
  if (!file.startsWith(root)) { res.writeHead(403).end(); return; } // no ../ escapes
  try {
    if (!(await stat(file)).isFile()) throw new Error("dir");
  } catch {
    file = join(root, "index.html"); // client-side route
  }
  try {
    const body = await readFile(file);
    res.writeHead(200, { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream" }).end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(port, () => console.log(`Serving ${root} on http://localhost:${port}`));
