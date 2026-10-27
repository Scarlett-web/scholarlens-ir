import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
const root = process.cwd();
const required = [
  "index.html", "package.json", "tsconfig.json", "vite.config.ts",
  "src/main.tsx", "src/App.tsx", "src/styles.css", "src/types.ts",
  "src/components/Layout.tsx", "src/components/SearchBox.tsx", "src/components/PaperCard.tsx",
  "src/components/LocalPdfViewer.tsx", "src/components/ToolNavigation.tsx",
  "src/services/papers.ts", "src/services/ai.ts", "src/data/demoPapers.ts",
  "src/lib/evaluation.ts", "src/lib/pdfStore.ts", "src/lib/storage.ts",
  "src/pages/HomePage.tsx", "src/pages/SearchPage.tsx", "src/pages/PaperPage.tsx",
  "src/pages/ExplorePage.tsx", "src/pages/LibraryPage.tsx", "src/pages/AssistantPage.tsx",
  "src/pages/EvaluationPage.tsx", "src/pages/UploadPage.tsx", "src/pages/AdminPage.tsx",
  "src/pages/NotFoundPage.tsx",
  "docs/FEATURE_SPEC.md", "docs/DESIGN_SYSTEM.md", "docs/BACKEND_INTEGRATION.md", "docs/QA_CHECKLIST.md",
  "docs/AI_API_INTEGRATION.md", "src/refined.css", "src/workflows.css",
  "src/design-core.css", "src/design-pages.css", "src/design-workspaces.css", "public/favicon.svg",
  "AGENTS.md", ".agents/skills/landing-page-design/SKILL.md",
  ".agents/skills/redesign-existing-projects/SKILL.md", "docs/DESIGN_SKILL_AUDIT.md"
];
for(const filename of required) assert.ok(fs.existsSync(filename), "Missing "+filename);
const sources = required.filter(f=>f.startsWith("src/")&&/\.(ts|tsx)$/.test(f));
for(const file of sources){
 const contents=fs.readFileSync(file,"utf8");
 const rex=/from\s+["'](\.{1,2}\/[^"']+)["']/g;
 for(const match of contents.matchAll(rex)){
  const p=path.resolve(path.dirname(file),match[1]);
  assert.ok([".ts",".tsx",".js",".jsx"].some(ext=>fs.existsSync(p+ext))||fs.existsSync(path.join(p,"index.ts")), "Broken local import "+file+" -> "+match[1]);
 }
}
const app=fs.readFileSync("src/App.tsx","utf8");
for(const route of ["/search","/paper/:paperId","/explore","/library","/assistant","/evaluation","/upload","/admin"])assert.ok(app.includes('path="'+route+'"'),"Missing route "+route);
assert.ok(app.includes('path="*"')&&app.includes("NotFoundPage"),"Missing branded 404 route");
for(const name of ["landing-page-design","redesign-existing-projects"]){
  const content=fs.readFileSync(".agents/skills/"+name+"/SKILL.md","utf8");
  assert.ok(content.startsWith("---")&&content.includes("name: "+name),"Missing or malformed project skill "+name);
}
const data=fs.readFileSync("src/data/demoPapers.ts","utf8");
assert.equal((data.match(/title: "/g)||[]).length,18,"Expected 18 synthetic paper seeds");
const search=fs.readFileSync("src/lib/search.ts","utf8");
assert.ok(search.includes("searchDemo")&&search.includes("highlightParts"));
assert.ok(!required.filter(f=>f.startsWith("src/")).some(f=>fs.readFileSync(f,"utf8").includes("dangerouslySetInnerHTML")),"Unsafe HTML rendering");
const packageJson=JSON.parse(fs.readFileSync("package.json","utf8"));
assert.ok(packageJson.scripts.build && packageJson.scripts.test && packageJson.dependencies.react && packageJson.devDependencies.typescript);
const ai=fs.readFileSync("src/services/ai.ts","utf8");
assert.ok(ai.includes('VITE_AI_ENDPOINT ?? ""'),"AI endpoint must remain empty by default");
assert.ok(ai.includes('rawEndpoint.startsWith("/api/")'),"AI endpoint must be same-origin");
assert.ok(!ai.includes("dangerouslySetInnerHTML"),"AI output must never be executed as HTML");
const pdf=fs.readFileSync("src/lib/pdfStore.ts","utf8");
assert.ok(pdf.includes("indexedDB.open")&&pdf.includes("SHA-256"),"Local PDF persistence and verification must exist");
console.log("Structural verification passed: "+required.length+" files, "+sources.length+" source modules, 8 core routes plus 404, 18 explicitly synthetic sample papers.");
console.log("Note: This is NOT TypeScript compilation, Vite build, or browser testing.");
