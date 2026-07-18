import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const doc = await readFile(new URL("../docs/VO_PROJECT_AUTHORING_OPERATIONS.md", import.meta.url), "utf8");

for (const contract of [
  "POST /api/agent/project-authoring/projects",
  "responsibleActor",
  "executorActor",
  "reviewerActor",
  "expectedRevision",
  "confirmationKey",
  "projectGrantSecret",
  "strict_confirmation",
  "routine_task_update",
  "templateId,version",
  "projectTemplateInstance",
  "occurrenceId",
  "VO_AGENT_PROJECT_AUTHORING_ENABLED",
  "VO_PROJECT_INSTANCE_RECURRENCE_ENABLED",
  "Failure and recovery runbook",
  "GET /api/project-authoring/health",
]) {
  assert.ok(doc.includes(contract), `authoring operations doc missing: ${contract}`);
}

assert.match(doc, /never starts Project Execution/);
assert.match(doc, /must never acquire `X-VO-Management-Token`/);
assert.match(doc, /Duplicate or restarted callbacks return the already materialized project/);
assert.match(doc, /cannot cryptographically verify provider-neutral chat authorship/);
assert.match(doc, /remain inert compatibility metadata/);

console.log("VO project authoring operations documentation passed");
