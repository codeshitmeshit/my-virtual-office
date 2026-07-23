#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync('app/index.html', 'utf8');
const chat = fs.readFileSync('app/chat.js', 'utf8');
const historyRuntime = fs.readFileSync('app/chat-history.js', 'utf8');
const style = fs.readFileSync('app/style.css', 'utf8');

const historyScript = html.indexOf('chat-history.js');
const chatScript = html.indexOf('chat.js?', historyScript);
assert.ok(historyScript > html.indexOf('marked.min.js'), 'history runtime must load after Markdown dependencies');
assert.ok(chatScript > historyScript, 'history runtime must load immediately before chat.js');
assert.match(html, /style\.css\?v=[^"']*chat-bottom-follow/, 'bottom-follow CSS changes must invalidate the production browser cache');
assert.match(html, /chat-history\.js\?v=[^"']*live-history-reconcile/, 'history runtime changes must invalidate the production browser cache');
assert.match(html, /chat\.js\?v=[^"']*live-history-reconcile/, 'chat controller changes must invalidate the production browser cache');

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
assert.ok(activateBody.includes('if (this.historyView.entry !== activeEntry) this.historyView.activate(activeEntry)'), 'background refreshes for the active conversation must preserve the current virtual window');
assert.ok(loadV2Body.indexOf('this.activateHistory()') < loadV2Body.indexOf('this.historyStore.fetchLatest(context)'), 'cached content must paint before background refresh starts');
assert.ok(loadV2Body.includes('entry.order.length === 0'), 'loading UI must be limited to a cold cache miss');
assert.ok(!loadV2Body.includes("this.messages.innerHTML = ''"), 'the V2 wrapper must not clear a cached conversation');
assert.ok(loadV2Body.includes('const shouldStickToBottom = !!(opts.forceBottom || this.historyStickToBottom)'), 'history refresh must capture bottom-follow intent before asynchronous rendering');
assert.ok(loadV2Body.includes('this.scheduleHistoryBottomFollow()'), 'authoritative history refresh must settle at the bottom while following is enabled');

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
assert.ok(sendBody.includes('idempotencyKey'), 'optimistic history and provider requests must share an exact request identity');
assert.ok(sendBody.includes('this.historyStore.removeMessage(historyContext, optimisticHistoryMessage.id)'), 'attachment-only upload failure must remove the optimistic model record');
assert.ok(sendBody.includes('localUserMessage?.remove?.()'), 'attachment-only upload failure must also remove its DOM node');
assert.ok(chat.includes('onReconciled: reconciled => this.reconcileOptimisticMessages(reconciled)'), 'authoritative history reconciliation must clean the matching live-layer bubble');
assert.ok(sendBody.includes('await this.loadHistory({ recoverFinal: true, startedAt: codexSendStartedAt })'), 'successful Codex SSE completion must refresh authoritative history');
assert.ok(sendBody.includes('this.reconcileCodexLiveReply(data.runId, completed?.reply'), 'successful Codex SSE completion must remove the matching live reply');

const normalizedRenderStart = chat.indexOf('renderNormalizedHistoryMessage(message, options = {})');
const normalizedRenderBody = chat.slice(normalizedRenderStart, chat.indexOf('\n    async loadHistory', normalizedRenderStart));
assert.ok(normalizedRenderBody.includes('this.historyStore.getRenderedHtml(message.id, message.version)'), 'stable history text should reuse cached formatted HTML');
assert.ok(normalizedRenderBody.includes('this.historyStore.setRenderedHtml(message.id, message.version, html)'), 'new stable renders should populate the shared HTML cache');
assert.ok(normalizedRenderBody.includes('cachedHtml'), 'cached HTML must flow through the normalized rendering hook');
assert.ok(normalizedRenderBody.includes('normalizeHermesTools(message.tools || [])'), 'tool cards must be reconstructed for the active ChatWindow');
assert.ok(normalizedRenderBody.includes('approval: message.approval || null'), 'approval cards must be reconstructed for the active ChatWindow');

assert.ok(chat.includes('applyCanonicalLiveHistoryItem(eventName, payload)'), 'provider final events need one canonical Store merge hook');
assert.ok(chat.includes("if (eventName === 'message.delta') return"), 'streaming deltas must remain transient in the live layer');
assert.ok(chat.includes('this.applyCanonicalLiveHistoryItem('), 'live provider handlers must feed canonical terminal records into the shared Store');
assert.ok(chat.includes('this.historyStickToBottom = true'), 'each ChatWindow must own bottom-follow state');
assert.ok(chat.includes('updateHistoryBottomFollow()'), 'user scrolling must update bottom-follow state');
assert.ok(chat.includes('prepareHistoryBottomFollow(options = {})'), 'opening or switching a conversation must initialize bottom-follow state');
assert.ok(chat.includes('scheduleHistoryBottomFollow()'), 'post-layout bottom settling must be shared by history and live events');
assert.match(chat, /historyBottomSettleTimers = \[80, 300\]/, 'bottom settling must cover immediate post-render layout changes');
assert.ok(historyRuntime.includes('navigateToNewest()'), 'initial bottom placement must move the virtual history window to its newest range');
assert.ok(chat.includes('prepareHistoryBottomFollow({ newest: true })'), 'opening and switching must request the newest virtual range');
const providerMergeStart = chat.indexOf('applyCanonicalLiveHistoryItem(eventName, payload)');
const providerMergeBody = chat.slice(providerMergeStart, chat.indexOf('\n    handleProviderHistoryRecovered', providerMergeStart));
assert.ok(providerMergeBody.includes('payload.timelineItem'), 'provider model reconciliation must prefer the canonical server projection');
assert.ok(providerMergeBody.includes('this.historyStore.applyLiveEvent(this.getHistoryContext(), eventName, payload'), 'canonical timeline payloads must enter the shared Store without re-derivation');
assert.ok(providerMergeBody.includes('const shouldStickToBottom = this.historyStickToBottom'), 'provider events must capture follow intent before live mutation');
assert.ok(providerMergeBody.includes('this.scheduleHistoryBottomFollow()'), 'provider events must follow the bottom when enabled');

assert.match(historyRuntime, /mutation\.mode === 'live' \|\| mutation\.mode === 'latest'/, 'authoritative latest refreshes must advance a view that was already at the newest message');
assert.ok(historyRuntime.includes("mutation.mode === 'latest' && !wasAtNewest"), 'latest refreshes must preserve the visual anchor while the user is reading older history');

const feishuLiveStart = chat.indexOf('scheduleFeishuHistoryRefresh()');
const feishuLiveBody = chat.slice(feishuLiveStart, chat.indexOf('\n    async sendHermesBlockingMessage', feishuLiveStart));
assert.ok(feishuLiveBody.includes('this.feishuHistoryRefreshPending = true'), 'Feishu invalidations must retain a trailing refresh while one is running');
assert.ok(feishuLiveBody.includes('while (this.feishuHistoryRefreshPending'), 'Feishu refreshes must drain invalidations that arrive during a request');
assert.ok(feishuLiveBody.includes("source.addEventListener('ready'"), 'Feishu reconnect readiness must be observed');
assert.match(feishuLiveBody, /source\.addEventListener\('ready',[\s\S]*this\.scheduleFeishuHistoryRefresh\(\)/, 'Feishu ready must recover authoritative history missed while disconnected');
assert.ok(feishuLiveBody.includes("source.addEventListener('message'"), 'Feishu messages must invalidate normalized history');
assert.ok(feishuLiveBody.includes("source.addEventListener('delivery'"), 'Feishu delivery outcomes must invalidate normalized history');
assert.ok(feishuLiveBody.includes("source.addEventListener('keepalive'"), 'Feishu keepalive events must prove the browser connection is alive');
assert.ok(chat.includes('startFeishuEventWatchdog(source, agentId)'), 'Feishu subscriptions must start a stale-connection watchdog');
assert.ok(chat.includes('Date.now() - this.feishuEventActivityAt <= FEISHU_SSE_STALE_MS'), 'Feishu watchdog must reconnect a silently stale EventSource');

assert.match(style, /\.chat-history-layer,[\s\S]*\.chat-live-layer/, 'history and live layers must retain shared layout rules');
assert.match(style, /\.chat-history-spacer\s*\{[^}]*pointer-events:\s*none/s, 'virtual spacers must be non-interactive');
assert.match(style, /\.chat-history-layer\s*\{[^}]*overflow-anchor:\s*none/s, 'the virtual history layer must not compete with explicit visual-anchor restoration');

console.log('chat history navigation checks passed');
