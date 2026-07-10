#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';

const chat = fs.readFileSync('app/chat.js', 'utf8');
const style = fs.readFileSync('app/style.css', 'utf8');

assert.match(
  chat,
  /const\s+HERMES_HISTORY_POLL_MS\s*=\s*\d+;/,
  'provider history polling interval must be defined before fallback pollers use it'
);

const sendMessageBody = chat.slice(chat.indexOf('async sendMessage()'), chat.indexOf('async compactCodexContext()'));
assert.ok(sendMessageBody.includes('let attachmentUploadFailures = 0'), 'sendMessage should count failed attachment uploads');
assert.ok(
  sendMessageBody.includes('attachmentUploadFailures += 1'),
  'sendMessage should increment failed attachment upload count'
);
assert.ok(
  sendMessageBody.includes('if (hasAttachments && !uploadedFiles.length && !attachments?.length && !text.trim())'),
  'sendMessage should abort when every attachment failed and there is no text to send'
);
assert.ok(
  sendMessageBody.includes('localUserMessage?.remove?.()'),
  'failed attachment-only sends should remove the optimistic user bubble'
);

const codexStopBranch = chat.slice(
  chat.indexOf('if (this.isCodexSelected()) {', chat.indexOf('async sendStop()')),
  chat.indexOf('if (this.streamingMsg)', chat.indexOf('async sendStop()'))
);
assert.ok(codexStopBranch.includes('this.codexRequestInFlight = false'), 'Codex stop should clear request-in-flight state');
assert.ok(codexStopBranch.includes('this.codexBusy = true'), 'Codex stop should keep the UI busy while cancellation is pending');
assert.ok(codexStopBranch.includes('this.startCodexActivityPolling()'), 'Codex stop should continue activity polling after closing the SSE stream');

const claudeStopBranch = chat.slice(
  chat.indexOf('if (this.isClaudeCodeSelected()) {', chat.indexOf('async sendStop()')),
  chat.indexOf('if (this.isCodexSelected())', chat.indexOf('async sendStop()'))
);
assert.ok(!claudeStopBranch.includes('.catch(() => {})'), 'Claude Code stop must not swallow fetch failures');
assert.ok(claudeStopBranch.includes('const data = await res.json()'), 'Claude Code stop should inspect the response body');
assert.ok(
  claudeStopBranch.includes("if (!res.ok || data.ok === false) throw new Error(data.error || _ct('cancel_failed_detail'))"),
  'Claude Code stop should surface backend cancel failures'
);

assert.match(
  style,
  /\.chat-panel\s*\{[^}]*z-index:\s*10003/s,
  'primary chat panel should sit above non-active secondary panels'
);
assert.match(
  style,
  /\.chat-panel-secondary\s*\{[^}]*z-index:\s*10000[^}]*border-color:\s*#7b8aa8/s,
  'non-active secondary chat panels should be visually de-emphasized below the primary panel'
);
assert.match(
  style,
  /\.chat-panel-secondary\.chat-panel-active\s*\{[^}]*z-index:\s*10004[^}]*border-color:\s*var\(--gold\)/s,
  /\.chat-confirm-dialog\s*\{[^}]*z-index:\s*10050/s,
  /\.chat-bubble h1\s*\{[^}]*font-size:\s*18px/s,
  /\.chat-bubble h2\s*\{[^}]*font-size:\s*16px/s,
  'only the active secondary chat panel should receive the foreground gold treatment'
);
assert.ok(
  chat.includes('if (this.isPrimary) setActiveSecondarySlot(null);') &&
    chat.includes("button.classList.toggle('state-active', isActive)") &&
    chat.includes("button.dataset.chatSlotState = isActive ? 'active' : (isOpen ? 'open' : 'hidden')"),
  'chat focus and slot controls should keep active secondary state in sync'
);

console.log('chat bug regression checks passed');
