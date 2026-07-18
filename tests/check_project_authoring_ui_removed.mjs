import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const index = readFileSync("app/index.html", "utf8");

assert.ok(!existsSync("app/project-authoring-review.js"));
assert.ok(!existsSync("app/project-authoring-review.css"));
assert.ok(!index.includes("project-authoring-review.js"));
assert.ok(!index.includes("project-authoring-review.css"));
assert.ok(!index.includes("Agent project drafts"));
assert.ok(!index.includes("Agent 项目草稿"));

console.log("project authoring draft UI removal checks passed");
