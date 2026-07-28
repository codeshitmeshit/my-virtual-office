import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const api = require('../app/project-orchestration-api.js');

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return payload;
    },
  };
}

async function recordsOneAtomicFullAssignmentWrite() {
  const calls = [];
  const assignments = [
    { taskId: 'research', executionStage: 1 },
    { taskId: 'draft', executionStage: 2 },
    { taskId: 'review', executionStage: 2 },
  ];
  const result = await api.saveCompletedDrag({
    projectId: 'project 1',
    revision: 7,
    assignments,
    fetcher: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(200, {
        ok: true,
        orchestration: { revision: 8 },
        assignments,
      });
    },
  });

  assert.equal(calls.length, 1, 'a completed drag must produce exactly one network write');
  assert.equal(calls[0].url, '/api/projects/project%201/orchestration');
  assert.equal(calls[0].init.method, 'PUT');
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    revision: 7,
    assignments,
  });
  assert.equal(result.ok, true);
  assert.equal(result.saved, true);
  assert.equal(result.status, 200);
  assert.deepEqual(result.assignments, assignments);
}

async function returnsAuthoritativeStateForStaleRevisions() {
  const authoritativeAssignments = [
    { taskId: 'research', executionStage: 1 },
    { taskId: 'draft', executionStage: 2 },
  ];
  const result = await api.autosaveAssignments({
    projectId: 'project-1',
    revision: 2,
    assignments: [
      { taskId: 'research', executionStage: 2 },
      { taskId: 'draft', executionStage: 1 },
    ],
    fetcher: async () => jsonResponse(409, {
      ok: false,
      code: 'orchestration_revision_conflict',
      currentRevision: 3,
      orchestration: { revision: 3, state: 'draft' },
      assignments: authoritativeAssignments,
    }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.saved, false);
  assert.equal(result.conflict, true);
  assert.equal(result.status, 409);
  assert.equal(result.currentRevision, 3);
  assert.deepEqual(result.assignments, authoritativeAssignments);
  assert.deepEqual(result.orchestration, { revision: 3, state: 'draft' });
}

async function rejectedWritesAreNeverPresentedAsSaved() {
  const validationResult = await api.autosaveAssignments({
    projectId: 'project-1',
    revision: 0,
    assignments: [{ taskId: 'only-one-task', executionStage: 1 }],
    fetcher: async () => jsonResponse(400, {
      ok: false,
      code: 'incomplete_orchestration_assignment',
      error: 'full assignment required',
    }),
  });

  assert.equal(validationResult.ok, false);
  assert.equal(validationResult.saved, false);
  assert.equal(validationResult.status, 400);
  assert.equal(validationResult.code, 'incomplete_orchestration_assignment');

  const transportResult = await api.autosaveAssignments({
    projectId: 'project-1',
    revision: 0,
    assignments: [{ taskId: 'a', executionStage: 1 }],
    fetcher: async () => {
      throw new Error('offline');
    },
  });

  assert.equal(transportResult.ok, false);
  assert.equal(transportResult.saved, false);
  assert.equal(transportResult.status, 0);
  assert.equal(transportResult.code, 'orchestration_autosave_failed');
}

async function nonJsonResponsesBecomeReadableFailures() {
  const result = await api.autosaveAssignments({
    projectId: 'project-1',
    revision: 0,
    assignments: [{ taskId: 'a', executionStage: 1 }],
    fetcher: async () => ({
      ok: false,
      status: 404,
      async json() {
        throw new SyntaxError("Unexpected token '<', \"<html>\" is not valid JSON");
      },
    }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.saved, false);
  assert.equal(result.status, 404);
  assert.equal(result.code, 'invalid_json_response');
  assert.equal(result.error, 'Server returned a non-JSON response (HTTP 404)');
}

async function postsOrchestrationActionsToStableRoutes() {
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push({ url, init });
    return jsonResponse(200, { ok: true, project: { id: 'p1' } });
  };

  await api.pauseProject({ projectId: 'p1', body: { reason: 'manual' }, fetcher });
  await api.resumeProject({ projectId: 'p1', fetcher });
  await api.requestTaskSkip({ projectId: 'p1', taskId: 'task 1', body: { reason: 'blocked' }, fetcher });
  await api.decideTaskSkip({ projectId: 'p1', taskId: 'task 1', body: { decision: 'approve' }, fetcher });

  assert.deepEqual(calls.map((call) => call.url), [
    '/api/projects/p1/orchestration/pause',
    '/api/projects/p1/orchestration/resume',
    '/api/projects/p1/tasks/task%201/orchestration/skip-request',
    '/api/projects/p1/tasks/task%201/orchestration/skip-decision',
  ]);
  assert.ok(calls.every((call) => call.init.method === 'POST'));
  assert.deepEqual(JSON.parse(calls[0].init.body), { reason: 'manual' });
  assert.deepEqual(JSON.parse(calls[3].init.body), { decision: 'approve' });
}

await recordsOneAtomicFullAssignmentWrite();
await returnsAuthoritativeStateForStaleRevisions();
await rejectedWritesAreNeverPresentedAsSaved();
await nonJsonResponsesBecomeReadableFailures();
await postsOrchestrationActionsToStableRoutes();

console.log('project orchestration API contract checks passed');
