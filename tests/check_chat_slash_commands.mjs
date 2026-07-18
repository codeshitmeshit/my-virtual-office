import assert from 'node:assert/strict';
import fs from 'node:fs';

const chat = fs.readFileSync('app/chat.js', 'utf8');
const sendStart = chat.indexOf('async sendMessage()');
const optimisticInsert = chat.indexOf('this.historyStore.insertOptimistic(historyContext', sendStart);
const commandIntercept = chat.indexOf("text === '/new' || text === '/compact'", sendStart);

assert.ok(sendStart >= 0, 'sendMessage must exist');
assert.ok(commandIntercept > sendStart && commandIntercept < optimisticInsert,
  'exact slash commands must be intercepted before optimistic history insertion');
assert.ok(chat.includes("const slashCommand = !hasAttachments && (text === '/new' || text === '/compact') ? text : '';"),
  'only exact attachment-free /new and /compact commands are intercepted');

const executeStart = chat.indexOf('async executeChatSlashCommand(command)');
const sendEnd = chat.indexOf('async sendMessage()', executeStart);
const executeBody = chat.slice(executeStart, sendEnd);
assert.ok(executeBody.includes("i18n.managementFetch('/api/chat/commands/execute'"),
  'commands must use the management-authenticated endpoint');
assert.ok(executeBody.indexOf('if (!res.ok || !data.ok)') < executeBody.indexOf('this.applyChatCommandConversation(data)'),
  'conversation identity must switch only after a successful response');
assert.ok(executeBody.includes('JSON.stringify(this.getHistoryContext()) !== JSON.stringify(commandContext)'),
  'a response for a stale selection must not mutate the active conversation');
assert.ok(!executeBody.includes('historyStore.invalidate(commandContext)'),
  'successful /new must preserve the old history cache for reopening');
assert.ok(executeBody.includes('this.closeProviderEventSource') || chat.includes('resetConversation()'),
  'conversation switching must close stale streams before reopening the provider subscription');

console.log('chat slash command regression checks passed');
