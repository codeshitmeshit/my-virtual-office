import fs from 'node:fs';

const source = fs.readFileSync('app/projects.js', 'utf8');

const refreshStart = source.indexOf('async function refreshProjectExecutionProject');
const pollingStart = source.indexOf('function startProjectExecutionPolling()');
const workflowStart = source.indexOf('async function workflowStartAction()', pollingStart);
if (refreshStart < 0 || pollingStart < 0 || workflowStart < 0) {
  throw new Error('Project execution refresh/polling functions were not found');
}

const refreshSource = source.slice(refreshStart, pollingStart);
if (!refreshSource.includes('updateProjectExecutionBoardInPlace(previousProject, state.currentProject)')) {
  throw new Error('Lightweight project execution refresh does not preserve the board/chat DOM');
}
if (!source.includes('function snapshotWorkflowChatDom()') || !source.includes('restoreWorkflowChatDom(chatSnapshot)')) {
  throw new Error('Board rerenders do not preserve workflow chat DOM while execution is active');
}
if (!source.includes("state.workflow.chatSignature || (container && container.querySelector('.proj-chat-msg'))")) {
  throw new Error('Board rerenders do not preserve historical workflow chat after execution is blocked or stopped');
}
if (!source.includes('function updateProjectColumnTasks(')) {
  throw new Error('Project execution updates cannot refresh changed columns in place');
}
if (!refreshSource.includes('state.workflow.active || projectExecutionHasRunningTask(state.currentProject)')) {
  throw new Error('Auxiliary refreshes can still rebuild the board while a project execution is active');
}

const pollingSource = source.slice(pollingStart, workflowStart);
if (pollingSource.includes('mc.innerHTML = renderBoardView()')) {
  throw new Error('Project execution polling directly rebuilds the board and clears workflow chat');
}

const chatStart = source.indexOf('function renderWorkflowChat(data)');
const chatEnd = source.indexOf('function updateActiveColumnIndicator()', chatStart);
const chatSource = source.slice(chatStart, chatEnd);
if (!chatSource.includes('state.workflow.chatSignature === signature')) {
  throw new Error('Workflow chat rendering does not skip identical message payloads');
}
if (!chatSource.includes('container.querySelector(\'.proj-chat-msg\')')) {
  throw new Error('Empty active chat responses can still replace visible workflow messages');
}
if (!chatSource.includes('执行会话已启动，等待 Agent 输出')) {
  throw new Error('Workflow chat does not show an active placeholder while waiting for provider output');
}

console.log('project workflow chat DOM remains stable during execution polling');
