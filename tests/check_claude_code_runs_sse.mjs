import assert from 'node:assert/strict';
import fs from 'node:fs';

const server = fs.readFileSync('app/server.py', 'utf8');
const chat = fs.readFileSync('app/chat.js', 'utf8');
const gatewayPresence = fs.readFileSync('app/gateway_presence.py', 'utf8');

for (const token of [
  'class ProviderRunBridge',
  'PROVIDER_RUN_BRIDGE = ProviderRunBridge()',
  'def stream_events(self, handler, run_id',
  'CLAUDE_CODE_STREAM_RUNS',
  'def _handle_claude_code_run_start',
  'def _handle_claude_code_run_events',
  'def _handle_claude_code_interrupt',
  'ephemeral": "claude-code-progress"',
  'gateway_presence.set_provider_event(status_key, "claude-code"',
  '"/api/claude-code/runs"',
  '"/api/claude-code/runs/") and request_path.endswith("/events")',
  '"/api/claude-code/runs/") and request_path.endswith("/stop")',
]) {
  assert.ok(server.includes(token), `server.py missing ${token}`);
}

assert.ok(
  server.includes('def _remember_claude_code_stream_run(meta):\n    PROVIDER_RUN_BRIDGE.remember(meta)'),
  'Claude Code run registry should delegate to ProviderRunBridge'
);
assert.ok(
  server.includes('PROVIDER_RUN_BRIDGE.stream_events(handler, run_id, "Claude Code")'),
  'Claude Code SSE should delegate to ProviderRunBridge'
);

for (const token of [
  "fetch('/api/claude-code/runs'",
  "conversationId: this.getProviderConversationId('claude-code')",
  "attachments: attachments || []",
  'streamClaudeCodeRunEvents(runId)',
  "new EventSource('/api/provider/events?'",
  'waitForProviderRun(runId)',
  'handleClaudeCodeNativeEvent(eventName, data)',
  'sendClaudeCodeBlockingMessage(body, startedAt)',
  "fetch('/api/claude-code/runs/' + encodeURIComponent(this.currentRunId) + '/stop'",
]) {
  assert.ok(chat.includes(token), `chat.js missing ${token}`);
}

assert.ok(
  chat.includes("if (this.isClaudeCodeSelected()) query.set('conversationId', this.getProviderConversationId('claude-code'))"),
  'Claude Code history loads should use the same conversation id as runs'
);
assert.ok(!chat.includes('attachments: uploadedFiles'), 'Claude Code send must not reference undefined uploadedFiles');

assert.ok(gatewayPresence.includes('def set_provider_event'), 'gateway_presence.py should expose set_provider_event');
assert.ok(gatewayPresence.includes('turn.stream'), 'provider event should support streaming turn updates');

console.log('claude code runs SSE checks passed');
