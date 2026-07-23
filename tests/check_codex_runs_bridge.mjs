#!/usr/bin/env node
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const server = fs.readFileSync(path.join(root, 'app', 'server.py'), 'utf8');
const chat = fs.readFileSync(path.join(root, 'app', 'chat.js'), 'utf8');
const style = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');

const required = [
  'PROVIDER_RUN_REPOSITORY = ProviderRunRepository(',
  'PROVIDER_EVENT_JOURNAL = ProviderEventJournal(',
  'PROVIDER_RUN_COORDINATOR = ProviderRunCoordinator(',
  'def _handle_codex_run_start',
  'def _handle_codex_run_events',
  'def _handle_codex_run_stop',
  'def _append_codex_user_comm_event',
  'def _codex_activity_bridge_event_name',
  'body.get("_onActivity")',
  '"/api/codex/runs"',
  '"/api/codex/runs/") and request_path.endswith("/events")',
  '"/api/codex/runs/") and request_path.endswith("/stop")',
];

for (const needle of required) {
  if (!server.includes(needle)) {
    throw new Error(`missing Codex bridge source marker: ${needle}`);
  }
}
for (const obsolete of ['class ProviderRunBridge', '_CODEX_RUN_IDEMPOTENCY', '_PROVIDER_RUN_IDEMPOTENCY']) {
  if (server.includes(obsolete)) throw new Error(`obsolete Provider authority remains: ${obsolete}`);
}

const runStart = server.slice(server.indexOf('def _handle_codex_run_start'), server.indexOf('def _handle_codex_run_events'));
if (!runStart.includes('PROVIDER_RUN_COORDINATOR.start(command, adapter=adapter, compatibility_meta=meta)') || !runStart.includes('CallableProviderAdapter(')) {
  throw new Error('Codex runs should use the shared ProviderRunCoordinator and a provider adapter');
}
if (!runStart.includes('_handle_codex_chat(run_body)')) {
  throw new Error('Codex runs should reuse existing _handle_codex_chat');
}

const chatHandler = server.slice(server.indexOf('def _handle_codex_chat'), server.indexOf('def _handle_codex_activity'));
if (!chatHandler.includes('_append_codex_activity(agent_id, conversation_id, event)') &&
    !chatHandler.includes('legacy_callback=lambda item: _append_codex_activity(agent_id, conversation_id, item)')) {
  throw new Error('Codex chat should still append legacy activity');
}
if (!chatHandler.includes('activity_callback(record)')) {
  throw new Error('Codex chat should forward activity to optional bridge callback');
}
if (!chatHandler.includes('_append_codex_user_comm_event(agent, agent_id, conversation_id, message, body)')) {
  throw new Error('Codex chat should persist human messages for history reload');
}
if (!chatHandler.includes('"direction": "reply"') || !chatHandler.includes('"inReplyTo": inbound_event.get("id")')) {
  throw new Error('Codex chat should persist replies linked to the human message');
}

const codexChatRoute = server.slice(server.indexOf('elif self.path == "/api/codex/chat"'), server.indexOf('elif self.path == "/api/codex/reset"'));
if (!codexChatRoute.includes('result = _handle_codex_chat(body)')) {
  throw new Error('Codex chat fallback should call _handle_codex_chat directly');
}
if (codexChatRoute.includes('_handle_agent_platform_comm_send(body)')) {
  throw new Error('Codex chat fallback should not wrap chat-window messages as agent-platform A2A envelopes');
}

const chatRequired = [
  "fetch('/api/codex/runs'",
  "streamCodexRunEvents(data.runId",
  "closeCodexEventSource()",
  "handleCodexNativeEvent(eventName, data, label)",
  "pollCodexActivity(true, { replayHistoricalTurns: false })",
  "if (includeHistory && !replayHistoricalTurns && event.type === 'turn') continue;",
  "isA2AEnvelope",
  "renderedHistoryKeys",
  "renderCodexActivity(event, options = {})",
  "this.codexUnavailableInteractionKeys = new Set()",
  "renderCodexRunStatus({ runId, label, status, text, ts })",
  "settleCodexRunningStatusCards(",
  "settleCodexReasoningCards(",
  "renderCodexReasoningItem(item)",
  "this.renderCodexReasoningItem(data.timelineItem)",
  "this.renderCodexActivity(activity, { runId })",
  "this.renderCodexActivity(activity, { runId, replayCompletedTurns: false })",
  "const preferredRunId = options.runId || this.currentRunId || ''",
  "activityOutput.reply",
  "sendCodexBlockingMessage(codexBody",
  "'/api/codex/runs/' + encodeURIComponent(this.currentRunId) + '/stop'",
  "new EventSource('/api/provider/events?'",
  "waitForProviderRun(runId)",
];

for (const needle of chatRequired) {
  if (!chat.includes(needle)) {
    throw new Error(`missing Codex chat SSE source marker: ${needle}`);
  }
}

const sendMessageBody = chat.slice(chat.indexOf('async sendMessage()'), chat.indexOf('async compactCodexContext()'));
const codexSendBranch = sendMessageBody.slice(sendMessageBody.indexOf('if (this.isCodexSelected())'), sendMessageBody.indexOf('if (this.isClaudeCodeSelected())'));
if (codexSendBranch.indexOf("fetch('/api/codex/runs'") < 0) {
  throw new Error('Codex chat send branch should start background runs from the UI');
}
if (codexSendBranch.indexOf("fetch('/api/codex/chat'") >= 0) {
  throw new Error('Codex chat send branch should not call the blocking chat endpoint directly');
}
const codexSuccessPath = codexSendBranch.slice(codexSendBranch.indexOf('await this.streamCodexRunEvents(data.runId, label);'), codexSendBranch.indexOf('} catch (e) {'));
if (codexSuccessPath.includes('loadHistory({ recoverFinal: true, startedAt: codexSendStartedAt })')) {
  throw new Error('Codex SSE completion should not fully redraw history and drop locally appended user bubbles');
}
const codexCatchPath = codexSendBranch.slice(codexSendBranch.indexOf('} catch (e) {'), codexSendBranch.indexOf('} finally {'));
const acceptedGuard = codexCatchPath.indexOf('else if (codexAccepted)');
const preAcceptanceFallback = codexCatchPath.indexOf('} else try {');
if (acceptedGuard < 0 || preAcceptanceFallback < 0 || acceptedGuard > preAcceptanceFallback) {
  throw new Error('Accepted Codex runs must be handled before the pre-acceptance blocking fallback');
}
const acceptedFailurePath = codexCatchPath.slice(acceptedGuard, preAcceptanceFallback);
if (acceptedFailurePath.includes('sendCodexBlockingMessage(')) {
  throw new Error('Accepted Codex run failures must not re-execute the prompt through blocking chat');
}
if (!acceptedFailurePath.includes('recoverProviderStateOnce()') || !acceptedFailurePath.includes('loadHistory({ recoverFinal: true, startedAt: codexSendStartedAt })')) {
  throw new Error('Accepted Codex run failures should recover existing run and history state');
}
const compatibilityFallbackPath = codexCatchPath.slice(preAcceptanceFallback, codexCatchPath.indexOf('} catch (fallbackError)'));
if (!compatibilityFallbackPath.includes('sendCodexBlockingMessage(codexBody')) {
  throw new Error('Pre-acceptance Codex run creation failures should retain the compatibility fallback');
}
const codexFinallyPath = codexSendBranch.slice(codexSendBranch.indexOf('} finally {'), codexSendBranch.indexOf('return;', codexSendBranch.indexOf('} finally {')));
if (codexFinallyPath.includes('pollCodexActivity()')) {
  throw new Error('Codex SSE finally should not poll legacy activity after the run has already settled');
}
if (!style.includes('.chat-codex-run-status') || !style.includes('.codex-run-status-card')) {
  throw new Error('Codex run status stream cards should have visible styling');
}
if (!chat.includes('summarizeAgentToolResult(') || !chat.includes('renderAgentToolResultSummary(summary)')) {
  throw new Error('OpenClaw/Codex tool results should render as summarized agent result cards');
}
if (!chat.includes('const agentResultSummary = displayContent.trim() ? summarizeAgentToolResult(displayContent) : null') || !chat.includes("role === 'toolResult'")) {
  throw new Error('Tool result chat messages should render summarized agent result cards instead of raw JSON');
}
if (!chat.includes('const senderHeader = agentResultSummary ? null : renderSenderHeader(meta, role)')) {
  throw new Error('Summarized agent tool results should not show the outer human sender label');
}
if (!style.includes('.chat-agent-result-summary') || !style.includes('.chat-agent-result-reply')) {
  throw new Error('Agent tool result summaries should have visible VO-styled card CSS');
}

const unavailableInteractionBranch = chat.slice(
  chat.indexOf("event.type === 'interaction' && event.status === 'unavailable'"),
  chat.indexOf("event.type === 'turn' && event.status === 'cancelling'")
);
if (
  !unavailableInteractionBranch.includes('const key = this.codexInteractionKey(event)') ||
  !unavailableInteractionBranch.includes('if (this.codexUnavailableInteractionKeys.has(key)) return') ||
  !unavailableInteractionBranch.includes('this.codexUnavailableInteractionKeys.add(key)') ||
  unavailableInteractionBranch.indexOf('this.codexUnavailableInteractionKeys.add(key)') > unavailableInteractionBranch.indexOf('this.appendSystem(')
) {
  throw new Error('Unavailable Codex interactions should be deduped before appending system messages');
}

const nativeEventHandler = chat.slice(chat.indexOf('    handleCodexNativeEvent(eventName, data, label) {'), chat.indexOf('    closeClaudeCodeEventSource()'));
if (!nativeEventHandler.includes('const settledCards = this.settleCodexRunningStatusCards(finalStatus, finalStatusText)')) {
  throw new Error('Codex completion should settle existing running status cards before creating a final card');
}
if (!nativeEventHandler.includes('if (!settledCards)')) {
  throw new Error('Codex completion should avoid creating duplicate completed cards when a running card was already settled');
}
if (
  !nativeEventHandler.includes('const replyAlreadyInHistory = this.hasCurrentCodexReplyInHistory(canonicalReply)') ||
  !nativeEventHandler.includes('this.streamingMsg && replyAlreadyInHistory') ||
  !nativeEventHandler.includes('finalText && !replyAlreadyInHistory')
) {
  throw new Error('Codex completion should not append a live reply when the same run reply is already rendered from history');
}
const codexHistoryReplyDedupe = chat.slice(
  chat.indexOf('hasCurrentCodexReplyInHistory(reply)'),
  chat.indexOf('streamClaudeCodeRunEvents(runId)')
);
if (
  !codexHistoryReplyDedupe.includes("querySelectorAll('[data-history-message-id]')") ||
  !codexHistoryReplyDedupe.includes('node.dataset.historyMessageId === String(message.id')
) {
  throw new Error('Codex reply dedupe must require the matching history message to be mounted in the visible history layer');
}
const settleRunStatus = chat.slice(chat.indexOf('settleCodexRunningStatusCards(status, text)'), chat.indexOf('settleCodexReasoningCards(status ='));
if (!settleRunStatus.includes('let settled = 0') || !settleRunStatus.includes('settled += 1') || !settleRunStatus.includes('return settled')) {
  throw new Error('Codex run status settling should report how many cards it updated');
}

console.log('codex runs bridge checks passed');
