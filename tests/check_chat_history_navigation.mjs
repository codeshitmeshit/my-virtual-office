#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync('app/index.html', 'utf8');
const chat = fs.readFileSync('app/chat.js', 'utf8');
const style = fs.readFileSync('app/style.css', 'utf8');

const historyScript = html.indexOf('chat-history.js');
const chatScript = html.indexOf('chat.js?', historyScript);
assert.ok(historyScript > html.indexOf('marked.min.js'), 'history runtime must load after Markdown dependencies');
assert.ok(chatScript > historyScript, 'history runtime must load immediately before chat.js');

assert.match(chat, /const CHAT_HISTORY_V2_ENABLED = true;/, 'V2 must have one explicit rollback switch');
assert.match(chat, /const sharedChatHistoryStore = new ChatHistoryRuntime\.ChatHistoryStore/, 'all chat windows must share one page-level store');
assert.match(chat, /new ChatHistoryRuntime\.ChatHistoryView/, 'each ChatWindow must own a bounded history view');
assert.ok(chat.includes("className = 'chat-history-layer'"), 'ChatWindow must create a history layer');
assert.ok(chat.includes("className = 'chat-live-layer'"), 'ChatWindow must create a live layer');

const loadLegacyStart = chat.indexOf('async loadLegacyHistory(opts = {})');
const loadV2Start = chat.indexOf('async loadHistory(opts = {})');
assert.ok(loadLegacyStart > 0 && loadV2Start > 0, 'the unchanged provider-specific loader must remain behind the V2 wrapper');
const loadV2Body = chat.slice(loadV2Start, chat.indexOf('\n    setFeishuLiveStatus', loadV2Start));
const activateStart = chat.indexOf('activateHistory(options = {})');
const activateBody = chat.slice(activateStart, chat.indexOf('\n    renderNormalizedHistoryMessage', activateStart));
assert.ok(loadV2Body.includes('if (!CHAT_HISTORY_V2_ENABLED) return this.loadLegacyHistory(opts)'), 'the kill switch must invoke legacy history');
assert.ok(activateBody.includes('this.historyStore.activate(context, this.historyView)'), 'activation must bind the selected key to the current view');
assert.ok(loadV2Body.indexOf('this.activateHistory()') < loadV2Body.indexOf('this.historyStore.fetchLatest(context)'), 'cached content must paint before background refresh starts');
assert.ok(loadV2Body.includes('entry.order.length === 0'), 'loading UI must be limited to a cold cache miss');
assert.ok(!loadV2Body.includes("this.messages.innerHTML = ''"), 'the V2 wrapper must not clear a cached conversation');

const selectionBody = chat.slice(chat.indexOf('applySelection(opt,'), chat.indexOf('async loadAgentList()'));
assert.ok(!selectionBody.includes("this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_loading_history')"), 'selection changes must not insert a blocking loading bubble');
assert.ok(selectionBody.includes('this.activateHistory'), 'selection changes must activate cached history synchronously');
assert.ok(chat.includes('windowInstance?.activateHistory') && chat.includes('primaryWindow.activateHistory'), 'primary and secondary reopen paths must reuse cached state');
assert.ok(chat.includes('handleHistoryScroll()'), 'the scroll owner must drive bounded history navigation');
assert.ok(chat.includes("this.historyView.navigate('older')"), 'scrolling toward the top must shift the mounted window toward older records');
assert.ok(chat.includes('this.historyStore.fetchOlder(entry.context)'), 'reaching the loaded top must request one older cursor page');
assert.ok(chat.includes("this.historyView.navigate('newer')"), 'scrolling back down must release older roots and restore newer records');

const newSessionStart = chat.indexOf('async newSession()');
const newSessionBody = chat.slice(newSessionStart, chat.indexOf('\n    handleFiles()', newSessionStart));
assert.ok(newSessionBody.includes('this.historyStore.invalidate(oldHistoryContext)'), 'successful provider resets must invalidate the old conversation key');
assert.ok(newSessionBody.includes('this.activateHistory({ coldEmpty: true })'), 'successful resets must activate the empty new key');

const sendBody = chat.slice(chat.indexOf('async sendMessage()'), chat.indexOf('async compactCodexContext()'));
assert.ok(sendBody.includes('this.historyStore.insertOptimistic'), 'outgoing user messages must enter the shared model before network completion');
assert.ok(sendBody.includes('this.historyStore.removeMessage(historyContext, optimisticHistoryMessage.id)'), 'attachment-only upload failure must remove the optimistic model record');
assert.ok(sendBody.includes('localUserMessage?.remove?.()'), 'attachment-only upload failure must also remove its DOM node');

const normalizedRenderStart = chat.indexOf('renderNormalizedHistoryMessage(message, options = {})');
const normalizedRenderBody = chat.slice(normalizedRenderStart, chat.indexOf('\n    async loadHistory', normalizedRenderStart));
assert.ok(normalizedRenderBody.includes('this.historyStore.getRenderedHtml(message.id, message.version)'), 'stable history text should reuse cached formatted HTML');
assert.ok(normalizedRenderBody.includes('this.historyStore.setRenderedHtml(message.id, message.version, html)'), 'new stable renders should populate the shared HTML cache');
assert.ok(normalizedRenderBody.includes('cachedHtml'), 'cached HTML must flow through the normalized rendering hook');
assert.ok(normalizedRenderBody.includes('normalizeHermesTools(message.tools || [])'), 'tool cards must be reconstructed for the active ChatWindow');
assert.ok(normalizedRenderBody.includes('approval: message.approval || null'), 'approval cards must be reconstructed for the active ChatWindow');

assert.ok(chat.includes('mergeLiveHistoryRecord(eventName, payload)'), 'provider and Gateway final events need one normalized Store merge hook');
assert.ok(chat.includes("if (eventName === 'message.delta') return"), 'streaming deltas must remain transient in the live layer');
assert.ok(chat.includes('this.mergeLiveHistoryRecord('), 'live provider handlers must feed terminal records into the shared Store');

assert.match(style, /\.chat-history-layer,[\s\S]*\.chat-live-layer/, 'history and live layers must retain shared layout rules');
assert.match(style, /\.chat-history-spacer\s*\{[^}]*pointer-events:\s*none/s, 'virtual spacers must be non-interactive');

console.log('chat history navigation checks passed');
