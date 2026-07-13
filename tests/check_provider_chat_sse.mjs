#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';

const server = fs.readFileSync('app/server.py', 'utf8');
const sseTransport = fs.readFileSync('app/provider_sse_transport.py', 'utf8');
const chat = fs.readFileSync('app/chat.js', 'utf8');

for (const token of [
  'PROVIDER_SSE_TRANSPORT.stream_conversation(self, provider_kind, agent_id, conversation_id, after)',
  '"/api/provider/events"',
  'PROVIDER_EVENT_JOURNAL.publish(',
]) {
  assert.ok(server.includes(token), `server.py missing unified provider SSE marker: ${token}`);
}
for (const token of ['provider.snapshot', 'provider.heartbeat', 'Last-Event-ID', 'wait_for_conversation_events']) {
  assert.ok(sseTransport.includes(token), `provider_sse_transport.py missing unified provider SSE marker: ${token}`);
}

for (const token of [
  'this.providerEventSource = null',
  'this.providerRunWaiters = new Map()',
  'clearProviderRecoveryTimer()',
  'updateProviderEventSource()',
  "new EventSource('/api/provider/events?'",
  'handleProviderEvent(eventName, data)',
  'waitForProviderRun(runId',
  "'provider.snapshot'",
  "'provider.heartbeat'",
  "'approval.request'",
  "'approval.resolved'",
]) {
  assert.ok(chat.includes(token), `chat.js missing unified provider SSE marker: ${token}`);
}

{
  const start = chat.indexOf('    updateProviderEventSource()');
  const end = chat.indexOf('\n    async ensureProviderEventSourceReady()', start);
  const body = chat.slice(start, end);
  const cancellations = body.match(/this\.clearProviderRecoveryTimer\(\)/g) || [];
  assert.ok(cancellations.length >= 2, 'provider SSE should cancel fallback recovery on open and event delivery');
}

for (const method of ['streamCodexRunEvents', 'streamHermesRunEvents', 'streamClaudeCodeRunEvents']) {
  const start = chat.indexOf(`    ${method}(`);
  assert.ok(start >= 0, `${method} is missing`);
  const end = chat.indexOf('\n    }', start);
  const body = chat.slice(start, end + 6);
  assert.ok(body.includes('waitForProviderRun('), `${method} should settle from the conversation SSE`);
  assert.ok(!body.includes('new EventSource('), `${method} must not open a per-run EventSource`);
}

for (const method of [
  'startCodexActivityPolling',
  'startHermesHistoryPolling',
  'startCodexHistoryPolling',
  'startClaudeCodeHistoryPolling',
  'startHermesApprovalPolling',
  'startCodexApprovalPolling',
]) {
  const start = chat.indexOf(`    ${method}(`);
  assert.ok(start >= 0, `${method} compatibility method is missing`);
  const end = chat.indexOf('\n    }', start);
  const body = chat.slice(start, end + 6);
  assert.ok(!body.includes('setInterval('), `${method} must not create a resident polling interval`);
}

{
  const start = chat.indexOf('    ensureRecoveryWatchdog()');
  assert.ok(start >= 0, 'ensureRecoveryWatchdog is missing');
  const end = chat.indexOf('\n    stopRecoveryWatchdog()', start);
  const body = chat.slice(start, end);
  assert.ok(!body.includes('setInterval('), 'provider recovery watchdog must not create a resident polling interval');
  assert.ok(body.includes('document.hidden'), 'provider recovery watchdog should back off for hidden tabs');
  assert.ok(body.includes('recoverProviderStateOnce()'), 'provider recovery watchdog should use one-shot provider recovery');
}

console.log('provider chat SSE checks passed');
