#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';

const chat = fs.readFileSync('app/chat.js', 'utf8');

const newSessionStart = chat.indexOf('async newSession()');
const sendMessageStart = chat.indexOf('async sendMessage()');
const compactStart = chat.indexOf('async compactCodexContext()');
const stopStart = chat.indexOf('async sendStop()');

assert.ok(newSessionStart >= 0 && sendMessageStart > newSessionStart && compactStart > sendMessageStart && stopStart > compactStart);

const newSession = chat.slice(newSessionStart, sendMessageStart);
assert.ok(newSession.includes("fetch('/api/codex/reset'"), 'Codex new-session control must use the scoped reset endpoint');
assert.ok(newSession.includes('this.rotateCodexConversationId()'), 'Codex must rotate its VO conversation after reset succeeds');
assert.ok(newSession.includes("fetch('/api/' + providerPath + '/history/clear'"), 'Hermes and Claude Code must use scoped history clear');
assert.ok(newSession.includes('this.rotateProviderConversationId(providerKind)'), 'Hermes and Claude Code must rotate their VO conversation after clear succeeds');
assert.ok(newSession.includes("rpc('sessions.reset', { key: this.sessionKey })"), 'Gateway chat must retain its existing session reset path');
assert.ok(newSession.includes('showChatConfirmDialog'), 'Existing new-session button confirmation is characterized and must not change accidentally');

const sendMessage = chat.slice(sendMessageStart, compactStart);
assert.ok(!sendMessage.includes("text.startsWith('/')") && !sendMessage.includes('text.startsWith("/")'), 'Slash-prefixed ordinary messages must not be rejected wholesale');
assert.ok(sendMessage.includes('message: text'), 'Ordinary text, including unknown slash prefixes, must continue to provider dispatch');

const compact = chat.slice(compactStart, stopStart);
assert.ok(compact.includes("fetch('/api/codex/compact'"), 'Existing compaction must use the Codex native compact endpoint');
assert.ok(compact.includes('conversationId: this.getCodexConversationId()'), 'Compaction must retain the selected logical conversation');
assert.ok(compact.includes('if (!this.isCodexSelected() || this.codexBusy) return'), 'Existing compaction capability is Codex-only and busy-fenced');

console.log('chat control characterization checks passed');
