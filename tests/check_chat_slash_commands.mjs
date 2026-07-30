import assert from 'node:assert/strict';
import fs from 'node:fs';

const chat = fs.readFileSync('app/chat.js', 'utf8');
const guard = fs.readFileSync('app/chat-slash-guard.js', 'utf8');
const html = fs.readFileSync('app/index.html', 'utf8');
const sendStart = chat.indexOf('async sendMessage()');
const optimisticInsert = chat.indexOf('this.historyStore.insertOptimistic(historyContext', sendStart);
const commandIntercept = chat.indexOf('ChatSlashGuard?.classify', sendStart);

assert.ok(sendStart >= 0, 'sendMessage must exist');
assert.ok(commandIntercept > sendStart && commandIntercept < optimisticInsert,
  'exact slash commands must be intercepted before optimistic history insertion');
assert.ok(guard.includes("SUPPORTED_COMMANDS = new Set(['/new', '/compact'])"),
  'only exact supported slash commands should execute command controls');
assert.ok(guard.includes("value.startsWith('/')"),
  'slash-prefixed attachment-free messages must be classified before provider dispatch');
assert.ok(guard.includes("kind: 'blocked'"),
  'unknown slash-prefixed messages must be blocked locally');
assert.ok(html.indexOf('chat-slash-guard.js') > html.indexOf('chat-history.js'),
  'slash guard must load after chat history dependencies');
assert.ok(html.indexOf('chat.js?', html.indexOf('chat-slash-guard.js')) > html.indexOf('chat-slash-guard.js'),
  'slash guard must load before chat.js');

const executeStart = chat.indexOf('async executeChatSlashCommand(command)');
const sendEnd = chat.indexOf('async sendMessage()', executeStart);
const executeBody = chat.slice(executeStart, sendEnd);
assert.ok(executeBody.includes("i18n.managementFetch('/api/chat/commands/execute'"),
  'commands must use the management-authenticated endpoint');
assert.ok(executeBody.indexOf('if (!res.ok || !data.ok)') < executeBody.indexOf('this.applyChatCommandConversation(data)'),
  'conversation identity must switch only after a successful response');
assert.ok(executeBody.includes('JSON.stringify(this.getHistoryContext()) !== JSON.stringify(commandContext)'),
  'a response for a stale selection must not mutate the active conversation');
assert.ok(executeBody.includes("if (data.status === 'disabled') return 'ordinary';"),
  'flag-off command responses must be distinguishable from executed commands');
assert.ok(!executeBody.includes('historyStore.invalidate(commandContext)'),
  'successful /new must preserve the old history cache for reopening');
assert.ok(executeBody.includes('this.closeProviderEventSource') || chat.includes('resetConversation()'),
  'conversation switching must close stale streams before reopening the provider subscription');
assert.ok(chat.includes('ChatSlashGuard?.disabledMessage'),
  'disabled command recognition must be reported locally');
assert.ok(!chat.includes("if (commandOutcome !== 'ordinary') return;"),
  'disabled command recognition must not fall through to the ordinary send path');

console.log('chat slash command regression checks passed');
