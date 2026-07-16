import fs from 'node:fs';

const source = fs.readFileSync('app/projects.js', 'utf8');

if (!source.includes('function projectExecutionHasRunningTask(project)')) {
  throw new Error('Missing task-level project execution activity check');
}

const pollingStart = source.indexOf('function startProjectExecutionPolling()');
const pollingEnd = source.indexOf('async function workflowStartAction()', pollingStart);
const pollingSource = source.slice(pollingStart, pollingEnd);
if (!pollingSource.includes('projectExecutionHasRunningTask(state.currentProject)')) {
  throw new Error('Project execution polling stops without checking running task attempts');
}

const openStart = source.indexOf('async function checkWorkflowOnOpen(projectId)');
const legacyBranch = source.indexOf('const d = await api.workflowStatus(p.id)', openStart);
const projectExecutionOpenSource = source.slice(openStart, legacyBranch);
if (!projectExecutionOpenSource.includes('pollWorkflowChat()')) {
  throw new Error('Opening a project execution board does not fetch existing chat');
}
if (!projectExecutionOpenSource.includes('projectExecutionHasRunningTask(p)')) {
  throw new Error('Opening a board does not resume polling for a running task after workflow timeout');
}

console.log('project execution chat polling follows task-level activity');
