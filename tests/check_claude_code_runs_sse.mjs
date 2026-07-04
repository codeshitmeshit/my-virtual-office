import assert from 'node:assert/strict';
import fs from 'node:fs';

const server = fs.readFileSync('app/server.py', 'utf8');
const bridgeService = fs.readFileSync('app/server_services/agent_bridges.py', 'utf8');
const bridgeRoute = fs.readFileSync('app/server_routes/agent_bridges.py', 'utf8');
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
]) {
  assert.ok(bridgeService.includes(token), `agent_bridges.py missing ${token}`);
}

for (const token of [
  '"/api/claude-code/runs"',
  'path.startswith("/api/claude-code/runs/") and path.endswith("/events")',
  'path.startswith("/api/claude-code/runs/") and path.endswith("/stop")',
]) {
  assert.ok(bridgeRoute.includes(token), `agent_bridges route missing ${token}`);
}

assert.ok(
  bridgeService.includes('def _remember_claude_code_stream_run(meta):\n    PROVIDER_RUN_BRIDGE.remember(meta)'),
  'Claude Code run registry should delegate to ProviderRunBridge'
);
assert.ok(
  bridgeService.includes('PROVIDER_RUN_BRIDGE.stream_events(handler, run_id, "Claude Code")'),
  'Claude Code SSE should delegate to ProviderRunBridge'
);

for (const token of [
  "fetch('/api/claude-code/runs'",
  "conversationId: this.getProviderConversationId('claude-code')",
  "attachments: attachments || []",
  'streamClaudeCodeRunEvents(runId)',
  'new EventSource(url)',
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
