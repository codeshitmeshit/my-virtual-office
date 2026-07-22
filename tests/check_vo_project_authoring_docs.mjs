import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const doc = await readFile(new URL("../docs/VO_PROJECT_AUTHORING_OPERATIONS.md", import.meta.url), "utf8");

for (const contract of [
  "POST /api/agent/project-authoring/projects",
  "POST /api/agent/projects/{projectId}/scheduled-cron",
  "responsibleActor",
  "executorActor",
  "reviewerActor",
  "expectedRevision",
  "confirmationKey",
  "fixed maintenance confirmation",
  "strict_confirmation",
  "routine_task_update",
  "templateId,version",
  "projectTemplateInstance",
  "occurrenceId",
  "VO_AGENT_PROJECT_AUTHORING_ENABLED",
  "VO_PROJECT_INSTANCE_RECURRENCE_ENABLED",
  "projectExecutionEnabled=true",
  "tracking-only",
  "task input",
  "task output",
  "structured `description`",
  "create_only",
  "create_and_execute",
  "failed_retryable",
  "intervention_required",
  "Failure and recovery runbook",
  "GET /api/project-authoring/health",
]) {
  assert.ok(doc.includes(contract), `authoring operations doc missing: ${contract}`);
}

assert.match(doc, /never starts Project Execution/);
assert.match(doc, /must never acquire `X-VO-Management-Token`/);
assert.match(doc, /Reusable is a project attribute and does not require a template/);
assert.match(doc, /Gateway registration is an implementation detail and should not be exposed as a user prerequisite/);
assert.match(doc, /Duplicate or restarted callbacks return the same Project/);
assert.match(doc, /never silently creates a legacy or tracking-only project/);
assert.match(doc, /additive recurrence `executionMode`\/`executionIntent` fields may remain inert/);
assert.match(doc, /cannot cryptographically verify provider-neutral chat authorship/);
assert.match(doc, /remain inert compatibility metadata/);

console.log("VO project authoring operations documentation passed");
