import fs from 'node:fs';

const source = fs.readFileSync('app/projects.js', 'utf8');

if (!source.includes('function projectExecutionHasRunningTask(project)')) {
  throw new Error('Missing task-level project execution activity check');
}

const pollingStart = source.indexOf('function startProjectExecutionPolling()');
const pollingEnd = source.indexOf('async function workflowStartAction()', pollingStart);
const pollingSource = source.slice(pollingStart, pollingEnd);
if (!pollingSource.includes('workflowChatShouldBeLive(state.currentProject)')) {
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

if (!source.includes("new EventSource(`/api/projects/${encodeURIComponent(p.id)}/workflow/chat/events?${qs.toString()}`)")) {
  throw new Error('Project Execution chat does not open the project-scoped workflow chat stream');
}
if (!source.includes('if (!state.workflow.chatStreamHealthy) pollWorkflowChat();')) {
  throw new Error('Project Execution polling should avoid repeated chat snapshots while the stream is healthy');
}
if (!source.includes("source.addEventListener('workflow.scope.changed'")) {
  throw new Error('Project Execution chat stream does not handle scope invalidation');
}
if (!source.includes("const item = data.timelineItem && typeof data.timelineItem === 'object' ? data.timelineItem : null;")) {
  throw new Error('Project Execution chat stream must reconcile canonical timelineItem payloads');
}
if (source.includes('data.reply || data.text || data.message')) {
  throw new Error('Project Execution chat stream must not derive messages from provider-native payload fallbacks');
}

console.log('project execution chat polling follows task-level activity and stream fallback');
