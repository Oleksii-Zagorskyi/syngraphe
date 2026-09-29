// Builds the editor's bundle into src/editing/static/editing/: editor.js and editor.css from
// src/editing/js/, and a copy of the whitelist specification. Rewrites those files and nothing
// else, so running it twice is running it once.
import { copyFileSync, mkdirSync } from "node:fs";
import * as esbuild from "esbuild";

const out = "src/editing/static/editing";
mkdirSync(out, { recursive: true });

await esbuild.build({
  entryPoints: { editor: "src/editing/js/editor.js" },
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "SyngrapheEditor",
  target: "es2022",
  outdir: out,
  logLevel: "warning",
});
copyFileSync("src/editing/whitelist/spec.json", `${out}/spec.json`);
