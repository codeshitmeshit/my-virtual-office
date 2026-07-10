#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';

const dashboard = fs.readFileSync('app/dashboard-realtime.js', 'utf8');
const game = fs.readFileSync('app/game.js', 'utf8');
const chat = fs.readFileSync('app/chat.js', 'utf8');
const chatHistory = fs.readFileSync('app/chat-history.js', 'utf8');
const projects = fs.readFileSync('app/projects.js', 'utf8');
const pcMonitor = fs.readFileSync('app/pc-monitor.js', 'utf8');
const browserPanel = fs.readFileSync('app/browser-panel.js', 'utf8');
const server = fs.readFileSync('app/server.py', 'utf8');
const pcMetricsServerBranch = server.slice(
  server.indexOf('elif self.path == "/pc-metrics":'),
  server.indexOf('elif self.path == "/api-usage":')
);

assert.ok(
  dashboard.includes('lastSseAt') && dashboard.includes('isSseFresh'),
  'dashboard realtime should expose a fresh-SSE signal so legacy pollers can yield'
);
assert.ok(
  chatHistory.includes('PAGE_SIZE: 50') && chatHistory.includes('DOM_WINDOW_MAX: 160'),
  'history runtime must keep the cold-page and mounted-root limits explicit'
);
assert.ok(
  chatHistory.includes("performance.mark('vo-chat-history:render-batch:start')") &&
    chatHistory.includes("performance.measure('vo-chat-history:render-batch'") &&
    chat.includes("performance.mark('vo-chat-history:switch:start')"),
  'history rendering and switching must emit content-free performance measures'
);
assert.ok(
  chatHistory.includes('__voChatHistoryDebug') &&
    chatHistory.includes('Object.freeze({') &&
    chatHistory.includes('maxRenderBatchMs'),
  'history runtime must expose a frozen aggregate-only debug snapshot'
);
assert.ok(
  chat.includes('CHAT_HISTORY_V2_ENABLED') && chat.includes('return this.loadLegacyHistory(opts)'),
  'history V2 must retain one verified legacy rollback switch'
);
const debugSection = chatHistory.slice(chatHistory.indexOf('__voChatHistoryDebug'));
for (const forbidden of ['message.text', 'attachments', 'tool.payload', 'conversationKey']) {
  assert.equal(debugSection.includes(forbidden), false, `debug output must not expose ${forbidden}`);
}
assert.ok(
  dashboard.includes("source.addEventListener('dashboard.heartbeat'") && dashboard.includes('if (!isSseFresh'),
  'dashboard realtime should treat heartbeat events as healthy and tolerate transient EventSource errors'
);
assert.ok(
  game.includes('dashboardRealtime.isSseFresh') && game.includes('return; // realtime SSE owns this refresh while it is healthy'),
  'game status/meeting pollers should skip duplicate network refreshes while dashboard SSE is healthy'
);
assert.ok(
  game.includes('_sidebarRenderSignature') && game.includes('if (signature === _sidebarRenderSignature) return;'),
  'sidebar rendering should skip DOM rebuilds when visible agent state has not changed'
);
assert.ok(
  chat.includes('formatStreamingContent') && chat.includes('bubble.innerHTML = formatStreamingContent(content)'),
  'streaming chat updates should use lightweight formatting instead of reparsing Markdown on every frame'
);
assert.ok(
  chat.includes('HISTORY_RENDER_BATCH_SIZE') &&
    chat.includes('renderHistoryQueue') &&
    chat.includes('DocumentFragment') &&
    chat.includes('await this.renderHistoryQueue(renderQueue, isCurrentHistoryRequest)'),
  'large chat histories should be rendered in cancellable batches instead of synchronously appending every message'
);
assert.ok(
  projects.includes('projectSummarySignature') && projects.includes('if (nextSignature === state._projectSummarySignature) return;'),
  'project summary SSE updates should avoid full list rerenders when summaries are unchanged'
);
assert.ok(
  pcMonitor.includes('PC_FAILURE_BACKOFF_MS') && pcMonitor.includes('scheduleNextPoll'),
  'PC metrics polling should back off when the optional metrics server is offline'
);
assert.ok(
  pcMetricsServerBranch.includes('"ok": False') &&
    pcMetricsServerBranch.includes('"status": "offline"') &&
    !pcMetricsServerBranch.includes('self.send_response(502)'),
  'PC metrics proxy should report offline state as JSON instead of generating repeated browser 502 errors'
);
assert.ok(
  browserPanel.includes('_browserCdpAvailable') && browserPanel.includes('if (!_browserCdpAvailable) return;'),
  'browser URL polling should stop while the optional CDP browser is unavailable'
);
assert.ok(
  game.includes('BACKGROUND_FRAME_DELAY_MS') && game.includes('document.hidden') && game.includes('setTimeout(loop, BACKGROUND_FRAME_DELAY_MS)'),
  'canvas animation loop should slow down while the VO tab is hidden'
);

console.log('frontend performance static checks passed');
