/** Production builds always use this site's real backend; never include AI credentials. */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const env = { ...process.env, VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "/api" };
for (const [entry, ...args] of [
  ["node_modules/typescript/bin/tsc", "--noEmit"],
  ["node_modules/vite/bin/vite.js", "build"],
]) {
  const result = spawnSync(process.execPath, [join(root, entry), ...args], { cwd: root, env, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const hash = path => createHash("sha256").update(readFileSync(path)).digest("hex");
const assets = Object.fromEntries(readdirSync(join(root, "dist/assets"))
  .filter(name => /\.(js|css)$/.test(name))
  .map(name => ["assets/" + name, hash(join(root, "dist/assets", name))]));
writeFileSync(join(root, "dist/build-info.json"), JSON.stringify({
  data_source: "api", api_base: "/api", html_sha256: hash(join(root, "dist/index.html")), assets,
}, null, 2) + "\n");
console.log("Production build verified: real API at /api; asset hashes recorded in dist/build-info.json.");
