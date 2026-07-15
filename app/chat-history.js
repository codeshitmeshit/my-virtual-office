(function (global) {
  'use strict';

  const KEY_SEPARATOR = '\u001f';
  const constants = Object.freeze({
    PAGE_SIZE: 50,
    DOM_WINDOW_MAX: 160,
    MESSAGE_LIMIT: 1000,
    INACTIVE_ENTRY_LIMIT: 8,
  });
  const aggregateDebug = {
    cacheHits: 0,
    cacheMisses: 0,
    evictions: 0,
    renderBatches: 0,
    maxRenderBatchMs: 0,
  };

  function stableHistoryHash(value) {
    const bytes = new TextEncoder().encode(String(value || ''));
    let hash = 0x811c9dc5;
    for (const byte of bytes) {
      hash ^= byte;
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, '0');
  }

  function createConversationKey(context = {}) {
    return [
      String(context.providerKind || 'gateway'),
      String(context.agentId || ''),
      String(context.conversationId || context.sessionKey || ''),
    ].join(KEY_SEPARATOR);
  }

  function computeWindowRange(total, options = {}) {
    const count = Math.max(0, Math.floor(Number(total) || 0));
    if (!count) return { start: 0, end: 0 };
    const maximum = Math.min(constants.DOM_WINDOW_MAX, count);
    const initial = Math.min(constants.PAGE_SIZE, count);
    const shift = 40;
    const overscan = 20;

    if (Number.isFinite(options.targetIndex)) {
      const target = Math.max(0, Math.min(count - 1, Math.floor(options.targetIndex)));
      let start = Math.max(0, target - Math.floor(maximum / 2));
      let end = Math.min(count, start + maximum);
      start = Math.max(0, end - maximum);
      if (target - start < overscan) start = Math.max(0, target - overscan);
      end = Math.min(count, Math.max(end, target + overscan + 1));
      start = Math.max(0, end - maximum);
      return { start, end };
    }

    const current = options.current;
    if (!current) return { start: count - initial, end: count };
    let start = Math.max(0, Math.min(count, Math.floor(Number(current.start) || 0)));
    let end = Math.max(start, Math.min(count, Math.floor(Number(current.end) || 0)));
    const size = end - start;

    if (options.direction === 'older') {
      if (size < maximum) start = Math.max(0, start - Math.min(shift, maximum - size));
      else {
        start = Math.max(0, start - shift);
        end = Math.min(count, start + maximum);
      }
    } else if (options.direction === 'newer') {
      if (size < maximum) end = Math.min(count, end + Math.min(shift, maximum - size));
      else {
        end = Math.min(count, end + shift);
        start = Math.max(0, end - maximum);
      }
    }
    return { start, end };
  }

  function computeSpacerHeights(order, range, heights, fallbackHeight = 0) {
    const sum = (start, end) => {
      let total = 0;
      for (let index = start; index < end; index += 1) {
        const measured = Number(heights?.get?.(order[index]));
        total += Number.isFinite(measured) && measured >= 0 ? measured : fallbackHeight;
      }
      return total;
    };
    return {
      top: sum(0, range.start),
      bottom: sum(range.end, order.length),
    };
  }

  function computeAnchorDelta(beforeTop, afterTop) {
    return (Number(afterTop) || 0) - (Number(beforeTop) || 0);
  }

  function presentationStateKey(messageId, part) {
    return `${messageId}${KEY_SEPARATOR}${part}`;
  }

  function removeReconciledOptimisticNodes(root, reconciled = []) {
    if (!root?.querySelectorAll) return 0;
    const keys = new Set(reconciled.map(item => String(item?.idempotencyKey || '')).filter(Boolean));
    if (!keys.size) return 0;
    let removed = 0;
    for (const node of root.querySelectorAll('[data-idempotency-key]')) {
      if (!keys.has(String(node.dataset?.idempotencyKey || ''))) continue;
      node.remove?.();
      removed += 1;
    }
    return removed;
  }

  function removeProviderRunNodes(root, runId) {
    const key = String(runId || '');
    if (!root?.querySelectorAll || !key) return 0;
    let removed = 0;
    for (const node of root.querySelectorAll('[data-provider-run-id]')) {
      if (String(node.dataset?.providerRunId || '') !== key) continue;
      node.remove?.();
      removed += 1;
    }
    return removed;
  }

  function claimChatSubmission(root, fingerprint, now = Date.now(), debounceMs = 1500) {
    if (!root || !fingerprint) return true;
    const previous = root.__voLastChatSubmission;
    const submittedAt = Number(now) || 0;
    if (
      previous
      && previous.fingerprint === fingerprint
      && submittedAt >= previous.submittedAt
      && submittedAt - previous.submittedAt < debounceMs
    ) {
      return false;
    }
    root.__voLastChatSubmission = { fingerprint, submittedAt };
    return true;
  }

  function normalizedMessage(message = {}, context = {}) {
    const rawEpochMs = message.epochMs ?? message.ts ?? Date.now();
    const epochMs = Number(rawEpochMs) || 0;
    const role = String(message.role || 'assistant');
    const text = String(message.text || '');
    const identity = [
      context.providerKind || message.providerKind || 'gateway',
      context.conversationId || context.sessionKey || message.conversationId || '',
      role,
      epochMs,
      message.fromAgentId || '',
      message.toAgentId || '',
      message.source || '',
      stableHistoryHash(text),
    ].join(KEY_SEPARATOR);
    const id = String(message.id || message.commEventId || message.messageId || `fallback-${stableHistoryHash(identity)}-0`);
    const version = String(message.version || stableHistoryHash(JSON.stringify({
      role,
      text,
      media: message.media || message.attachments || [],
      tools: message.tools || [],
      thinking: message.thinking || '',
      approval: message.approval || null,
      status: message.status || 'done',
    })));
    return { ...message, id, version, role, text, epochMs, status: String(message.status || 'done') };
  }

  function estimateMessageBytes(message) {
    try { return JSON.stringify(message).length * 2; } catch (_) { return 0; }
  }

  function isTerminalStatus(status) {
    return ['done', 'completed', 'failed', 'error', 'cancelled', 'canceled', 'approved', 'denied'].includes(String(status || '').toLowerCase());
  }

  class ChatHistoryStore {
    constructor(options = {}) {
      this.fetchImpl = options.fetchImpl || global.fetch?.bind(global);
      this.entries = new Map();
      this.viewKeys = new WeakMap();
      this.renderedHtml = new Map();
      this.renderedHtmlBytes = 0;
      this.inactiveByteLimit = options.inactiveByteLimit || 12 * 1024 * 1024;
      this.renderedHtmlByteLimit = options.renderedHtmlByteLimit || 8 * 1024 * 1024;
      this.renderedHtmlEntryLimit = options.renderedHtmlEntryLimit || 1000;
      this.sequence = 0;
      this.debug = { cacheHits: 0, cacheMisses: 0, staleResponses: 0, evictions: 0 };
    }

    _newEntry(key, context) {
      return {
        key,
        context: { ...context },
        messages: new Map(),
        order: [],
        nextCursor: '',
        hasMore: false,
        session: {},
        activeViews: new Set(),
        latestPromise: null,
        olderPromises: new Map(),
        abortControllers: new Set(),
        anchor: null,
        presentationState: new Map(),
        revision: 0,
        lastAccessAt: ++this.sequence,
        estimatedBytes: 0,
      };
    }

    getOrCreate(context) {
      const key = typeof context === 'string' ? context : createConversationKey(context);
      let entry = this.entries.get(key);
      if (entry) {
        entry.lastAccessAt = ++this.sequence;
        this.debug.cacheHits += 1;
        aggregateDebug.cacheHits += 1;
        return entry;
      }
      this.debug.cacheMisses += 1;
      aggregateDebug.cacheMisses += 1;
      entry = this._newEntry(key, typeof context === 'string' ? {} : context);
      this.entries.set(key, entry);
      this._evictInactive();
      return entry;
    }

    activate(context, view) {
      const entry = this.getOrCreate(context);
      const previousKey = this.viewKeys.get(view);
      if (previousKey && previousKey !== entry.key) {
        this.entries.get(previousKey)?.activeViews.delete(view);
      }
      view.activation = Number(view.activation || 0) + 1;
      this.viewKeys.set(view, entry.key);
      entry.activeViews.add(view);
      entry.lastAccessAt = ++this.sequence;
      return { key: entry.key, entry, activation: view.activation };
    }

    deactivate(view) {
      const key = this.viewKeys.get(view);
      if (key) this.entries.get(key)?.activeViews.delete(view);
      this.viewKeys.delete(view);
      this._evictInactive();
    }

    _notify(entry, mutation = null) {
      for (const view of entry.activeViews) {
        if (this.viewKeys.get(view) !== entry.key) continue;
        view.onHistoryEntryChanged?.(entry, mutation);
      }
    }

    mergePage(entryOrContext, page = {}, mode = 'latest', options = {}) {
      const entry = entryOrContext?.messages instanceof Map ? entryOrContext : this.getOrCreate(entryOrContext);
      const previousOrder = entry.order.slice();
      const previousIds = new Set(previousOrder);
      const changedIds = [];
      const reconciled = [];
      for (const raw of page.messages || []) {
        const message = normalizedMessage(raw, entry.context);
        const idempotencyKey = String(message.idempotencyKey || '');
        if (message.role === 'user' && idempotencyKey && !message.id.startsWith('optimistic-')) {
          let skipIncoming = false;
          for (const [candidateId, candidate] of entry.messages) {
            if (candidateId === message.id || candidate.role !== 'user') continue;
            if (String(candidate.idempotencyKey || '') !== idempotencyKey) continue;
            if (!candidateId.startsWith('optimistic-')) {
              const candidateOrder = [Number(candidate.epochMs) || 0, candidateId];
              const messageOrder = [Number(message.epochMs) || 0, message.id];
              if (candidateOrder[0] < messageOrder[0] || (candidateOrder[0] === messageOrder[0] && candidateOrder[1] < messageOrder[1])) {
                skipIncoming = true;
                continue;
              }
              entry.messages.delete(candidateId);
              continue;
            }
            entry.messages.delete(candidateId);
            reconciled.push({
              optimisticId: candidateId,
              authoritativeId: message.id,
              idempotencyKey,
            });
          }
          if (skipIncoming) continue;
        }
        if (message.role === 'assistant' && message.source === 'agent-platform-communications' && String(message.text || '').trim()) {
          let matchedRun = null;
          for (const [candidateId, candidate] of entry.messages) {
            if (!candidateId.startsWith('run-') || !candidateId.endsWith('-final')) continue;
            if (candidate.role !== 'assistant' || String(candidate.text || '').trim() !== String(message.text || '').trim()) continue;
            const delta = Math.abs((Number(candidate.epochMs) || 0) - (Number(message.epochMs) || 0));
            if (delta > 10000 || (matchedRun && matchedRun.delta <= delta)) continue;
            matchedRun = { candidateId, delta };
          }
          if (matchedRun) {
            entry.messages.delete(matchedRun.candidateId);
            reconciled.push({
              providerRunId: matchedRun.candidateId.slice(4, -6),
              authoritativeId: message.id,
            });
          }
        }
        const existing = entry.messages.get(message.id);
        if (existing && isTerminalStatus(existing.status) && !isTerminalStatus(message.status)) continue;
        if (!existing || existing.version !== message.version || existing.status !== message.status) {
          entry.messages.set(message.id, message);
          changedIds.push(message.id);
        }
      }
      entry.order = Array.from(entry.messages.values())
        .sort((left, right) => left.epochMs - right.epochMs || left.id.localeCompare(right.id))
        .map(message => message.id);
      const firstPreviousIndex = previousOrder.length
        ? entry.order.findIndex(id => previousIds.has(id))
        : 0;
      const addedBefore = firstPreviousIndex < 0 ? 0 : firstPreviousIndex;
      if (entry.order.length > constants.MESSAGE_LIMIT) {
        const removed = entry.order.splice(0, entry.order.length - constants.MESSAGE_LIMIT);
        for (const id of removed) entry.messages.delete(id);
      }
      if (mode === 'latest' || page.nextCursor !== undefined) entry.nextCursor = String(page.nextCursor || '');
      if (page.hasMore !== undefined) entry.hasMore = !!page.hasMore;
      if (page.session && typeof page.session === 'object') entry.session = { ...entry.session, ...page.session };
      entry.estimatedBytes = Array.from(entry.messages.values()).reduce((sum, message) => sum + estimateMessageBytes(message), 0);
      entry.revision += 1;
      entry.lastAccessAt = ++this.sequence;
      if (options.notify !== false) this._notify(entry, { type: 'page', mode, messageIds: changedIds, addedBefore, reconciled });
      this._evictInactive();
      return entry;
    }

    _evictEntry(key) {
      const entry = this.entries.get(key);
      if (!entry || entry.activeViews.size) return false;
      for (const controller of entry.abortControllers) controller.abort();
      this.entries.delete(key);
      this.debug.evictions += 1;
      aggregateDebug.evictions += 1;
      return true;
    }

    _evictInactive() {
      const inactive = () => Array.from(this.entries.values()).filter(entry => !entry.activeViews.size).sort((a, b) => a.lastAccessAt - b.lastAccessAt);
      let candidates = inactive();
      while (candidates.length > constants.INACTIVE_ENTRY_LIMIT) {
        this._evictEntry(candidates[0].key);
        candidates = inactive();
      }
      const inactiveBytes = () => inactive().reduce((sum, entry) => sum + entry.estimatedBytes, 0);
      while (inactiveBytes() > this.inactiveByteLimit) {
        candidates = inactive();
        if (!candidates.length || !this._evictEntry(candidates[0].key)) break;
      }
    }

    getRenderedHtml(messageId, version) {
      const key = `${messageId}${KEY_SEPARATOR}${version}`;
      const cached = this.renderedHtml.get(key);
      if (!cached) return null;
      this.renderedHtml.delete(key);
      this.renderedHtml.set(key, cached);
      return cached.html;
    }

    setRenderedHtml(messageId, version, html) {
      const key = `${messageId}${KEY_SEPARATOR}${version}`;
      const value = String(html || '');
      const previous = this.renderedHtml.get(key);
      if (previous) this.renderedHtmlBytes -= previous.bytes;
      const item = { html: value, bytes: value.length * 2 };
      this.renderedHtml.delete(key);
      this.renderedHtml.set(key, item);
      this.renderedHtmlBytes += item.bytes;
      while (this.renderedHtml.size > this.renderedHtmlEntryLimit || this.renderedHtmlBytes > this.renderedHtmlByteLimit) {
        const oldestKey = this.renderedHtml.keys().next().value;
        const evicted = this.renderedHtml.get(oldestKey);
        this.renderedHtml.delete(oldestKey);
        this.renderedHtmlBytes -= evicted.bytes;
      }
    }

    _historyUrl(context, before = '') {
      const query = new URLSearchParams({
        providerKind: String(context.providerKind || 'gateway'),
        agentId: String(context.agentId || ''),
        limit: String(constants.PAGE_SIZE),
      });
      if (context.conversationId) query.set('conversationId', String(context.conversationId));
      if (context.sessionKey) query.set('sessionKey', String(context.sessionKey));
      if (before) query.set('before', String(before));
      return `/api/chat/history?${query}`;
    }

    fetchLatest(context) {
      const entry = this.getOrCreate(context);
      if (entry.latestPromise) return entry.latestPromise;
      const controller = new AbortController();
      entry.abortControllers.add(controller);
      const request = Promise.resolve(this.fetchImpl(this._historyUrl(context), { signal: controller.signal }))
        .then(async response => {
          const page = await response.json();
          if (!response.ok || page.ok === false) throw Object.assign(new Error(page.error || 'History request failed'), { code: page.code });
          return this.mergePage(entry, page, 'latest');
        });
      entry.latestPromise = request.finally(() => {
        entry.latestPromise = null;
        entry.abortControllers.delete(controller);
      });
      return entry.latestPromise;
    }

    fetchOlder(context) {
      const entry = this.getOrCreate(context);
      if (!entry.hasMore || !entry.nextCursor) return Promise.resolve(entry);
      const cursor = entry.nextCursor;
      if (entry.olderPromises.has(cursor)) return entry.olderPromises.get(cursor);
      const controller = new AbortController();
      entry.abortControllers.add(controller);
      const request = Promise.resolve(this.fetchImpl(this._historyUrl(context, cursor), { signal: controller.signal }))
        .then(async response => {
          const page = await response.json();
          if (!response.ok || page.ok === false) throw Object.assign(new Error(page.error || 'History request failed'), { code: page.code });
          return this.mergePage(entry, page, 'older');
        }).catch(error => {
          if (error?.code === 'invalid_chat_history_cursor') {
            entry.nextCursor = '';
            entry.hasMore = false;
            return this.fetchLatest(context);
          }
          throw error;
        }).finally(() => {
          entry.olderPromises.delete(cursor);
          entry.abortControllers.delete(controller);
        });
      entry.olderPromises.set(cursor, request);
      return request;
    }

    insertOptimistic(context, message, options = {}) {
      const entry = this.getOrCreate(context);
      const normalized = normalizedMessage(message, context);
      if (options.notify === false) {
        entry.messages.set(normalized.id, normalized);
        entry.order = Array.from(entry.messages.values())
          .sort((left, right) => left.epochMs - right.epochMs || left.id.localeCompare(right.id))
          .map(item => item.id);
        entry.estimatedBytes = Array.from(entry.messages.values()).reduce((sum, item) => sum + estimateMessageBytes(item), 0);
        entry.revision += 1;
      } else {
        this.mergePage(entry, { messages: [normalized] }, 'live');
      }
      return normalized;
    }

    applyLiveEvent(context, eventName, data = {}, options = {}) {
      if (eventName === 'message.delta') return this.getOrCreate(context);
      const message = normalizedMessage(data.message || data, context);
      return this.mergePage(this.getOrCreate(context), { messages: [message] }, 'live', options);
    }

    removeMessage(context, messageId) {
      const entry = this.getOrCreate(context);
      entry.messages.delete(String(messageId));
      entry.order = entry.order.filter(id => id !== String(messageId));
      entry.estimatedBytes = Array.from(entry.messages.values()).reduce((sum, message) => sum + estimateMessageBytes(message), 0);
      entry.revision += 1;
      this._notify(entry, { type: 'remove', messageId: String(messageId) });
    }

    invalidate(context) {
      const key = typeof context === 'string' ? context : createConversationKey(context);
      const entry = this.entries.get(key);
      if (!entry) return;
      for (const view of entry.activeViews) this.viewKeys.delete(view);
      entry.activeViews.clear();
      this._evictEntry(key);
    }
  }

  class ChatHistoryView {
    constructor(options = {}) {
      this.scrollElement = options.scrollElement || options.container;
      this.historyLayer = options.historyLayer || this._createLayer('chat-history-layer');
      this.liveLayer = options.liveLayer || this._createLayer('chat-live-layer');
      this.renderMessage = options.renderMessage;
      this.onReconciled = options.onReconciled;
      this.heights = new Map();
      this.fallbackHeight = Number(options.fallbackHeight) || 72;
      this.entry = null;
      this.range = { start: 0, end: 0 };
      this.activation = 0;
      this.topSpacer = this._createSpacer('top');
      this.bottomSpacer = this._createSpacer('bottom');
      this.historyLayer.append(this.topSpacer, this.bottomSpacer);
      this.resizeObserver = typeof global.ResizeObserver === 'function'
        ? new global.ResizeObserver(entries => this._handleResize(entries))
        : null;
      this.historyLayer.addEventListener('toggle', event => this._captureDetailsState(event), true);
      this.historyLayer.addEventListener('load', event => this._handleMediaLoad(event), true);
    }

    _createLayer(className) {
      const layer = global.document.createElement('div');
      layer.className = className;
      this.scrollElement.appendChild(layer);
      return layer;
    }

    _createSpacer(position) {
      const spacer = global.document.createElement('div');
      spacer.className = `chat-history-spacer ${position}`;
      spacer.setAttribute('aria-hidden', 'true');
      return spacer;
    }

    activate(entry) {
      this.entry = entry;
      const savedRange = entry.anchor?.range;
      this.range = savedRange
        ? computeWindowRange(entry.order.length, { targetIndex: Math.min(savedRange.start, Math.max(0, entry.order.length - 1)) })
        : computeWindowRange(entry.order.length);
      this.renderAll({ restoreAnchor: !!entry.anchor });
    }

    deactivate() {
      this.saveAnchor();
      this.resizeObserver?.disconnect();
      this.entry = null;
    }

    saveAnchor() {
      if (!this.entry) return null;
      const root = this._firstVisibleRoot();
      const anchor = root ? {
        messageId: root.dataset.historyMessageId,
        offset: root.getBoundingClientRect().top - this.scrollElement.getBoundingClientRect().top,
        range: { ...this.range },
      } : { messageId: '', offset: 0, range: { ...this.range } };
      this.entry.anchor = anchor;
      return anchor;
    }

    navigate(direction) {
      if (!this.entry || !['older', 'newer'].includes(direction)) return;
      const next = computeWindowRange(this.entry.order.length, { current: this.range, direction });
      if (next.start === this.range.start && next.end === this.range.end) return;
      this.range = next;
      this.renderAll({ preserveViewport: true });
    }

    navigateToNewest() {
      if (!this.entry) return;
      const next = computeWindowRange(this.entry.order.length);
      if (next.start === this.range.start && next.end === this.range.end) return;
      this.range = next;
      this.renderAll();
    }

    onHistoryEntryChanged(entry, mutation = {}) {
      if (entry !== this.entry) return;
      if (mutation.reconciled?.length) this.onReconciled?.(mutation.reconciled);
      const changedIds = mutation.messageIds || [];
      const canPatch = mutation.mode === 'live' && changedIds.length === 1;
      if (canPatch && this._patchMessage(changedIds[0])) return;
      if (mutation.mode === 'latest' && this.range.start === 0 && this.range.end === 0 && entry.order.length) {
        this.range = computeWindowRange(entry.order.length);
      }
      if (mutation.mode === 'older' && mutation.addedBefore) {
        this.range = {
          start: this.range.start + mutation.addedBefore,
          end: this.range.end + mutation.addedBefore,
        };
      }
      const wasAtNewest = this.range.end >= Math.max(0, entry.order.length - changedIds.length);
      if ((mutation.mode === 'live' || mutation.mode === 'latest' || mutation.reconciled?.length) && wasAtNewest) {
        this.range = computeWindowRange(entry.order.length, { current: this.range, direction: 'newer' });
      } else if (this.range.end > entry.order.length) {
        this.range = computeWindowRange(entry.order.length);
      }
      const preserveViewport = mutation.mode === 'older' || (mutation.mode === 'latest' && !wasAtNewest);
      this.renderAll({ preserveViewport });
    }

    renderAll(options = {}) {
      if (!this.entry || typeof this.renderMessage !== 'function') return;
      const renderStartedAt = typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
      if (typeof performance !== 'undefined' && performance.mark) performance.mark('vo-chat-history:render-batch:start');
      const anchor = options.preserveViewport ? this._captureVisualAnchor() : null;
      this.resizeObserver?.disconnect();
      for (const root of this.historyLayer.querySelectorAll('[data-history-message-id]')) root.remove();
      const fragment = global.document.createDocumentFragment();
      for (const id of this.entry.order.slice(this.range.start, this.range.end)) {
        const message = this.entry.messages.get(id);
        if (!message) continue;
        const root = this._renderRoot(message);
        if (root) fragment.appendChild(root);
      }
      this.historyLayer.insertBefore(fragment, this.bottomSpacer);
      this._updateSpacers();
      this._observeRoots();
      this._restoreDetailsState();
      if (anchor) this._restoreVisualAnchor(anchor);
      else if (options.restoreAnchor && this.entry.anchor) this._restoreSavedAnchor(this.entry.anchor);
      const renderDuration = (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now()) - renderStartedAt;
      aggregateDebug.renderBatches += 1;
      aggregateDebug.maxRenderBatchMs = Math.max(aggregateDebug.maxRenderBatchMs, renderDuration);
      if (typeof performance !== 'undefined' && performance.mark && performance.measure) {
        performance.mark('vo-chat-history:render-batch:end');
        performance.measure('vo-chat-history:render-batch', 'vo-chat-history:render-batch:start', 'vo-chat-history:render-batch:end');
      }
    }

    _renderRoot(message) {
      if (String(message?.id || '').startsWith('optimistic-')) return null;
      const fragment = global.document.createDocumentFragment();
      const rendered = this.renderMessage(message, { parent: fragment, skipTypingCleanup: true });
      const root = rendered || fragment.firstElementChild;
      if (!root) return null;
      root.dataset.historyMessageId = message.id;
      root.dataset.historyMessageVersion = message.version;
      return root;
    }

    _patchMessage(messageId) {
      const index = this.entry.order.indexOf(messageId);
      if (index < this.range.start || index >= this.range.end) return false;
      const existing = this.historyLayer.querySelector(`[data-history-message-id="${global.CSS?.escape ? global.CSS.escape(messageId) : String(messageId).replace(/["\\]/g, '\\$&')}"]`);
      const message = this.entry.messages.get(messageId);
      if (!existing || !message) return false;
      const replacement = this._renderRoot(message);
      if (!replacement) return false;
      this.resizeObserver?.unobserve(existing);
      existing.replaceWith(replacement);
      this.resizeObserver?.observe(replacement);
      this._restoreDetailsState(replacement);
      return true;
    }

    _observeRoots() {
      if (!this.resizeObserver) return;
      for (const root of this.historyLayer.querySelectorAll('[data-history-message-id]')) this.resizeObserver.observe(root);
    }

    _handleResize(entries) {
      let changed = false;
      for (const observed of entries) {
        const id = observed.target.dataset.historyMessageId;
        const height = observed.borderBoxSize?.[0]?.blockSize || observed.contentRect?.height || observed.target.getBoundingClientRect().height;
        if (id && Number.isFinite(height) && height >= 0 && this.heights.get(id) !== height) {
          this.heights.set(id, height);
          changed = true;
        }
      }
      if (changed) this._updateSpacers();
    }

    _handleMediaLoad(event) {
      if (!event.target?.matches?.('img, video, audio')) return;
      const root = event.target.closest('[data-history-message-id]');
      if (root && this.resizeObserver) {
        this.resizeObserver.unobserve(root);
        this.resizeObserver.observe(root);
      }
    }

    _updateSpacers() {
      if (!this.entry) return;
      const spacers = computeSpacerHeights(this.entry.order, this.range, this.heights, this.fallbackHeight);
      this.topSpacer.style.height = `${spacers.top}px`;
      this.bottomSpacer.style.height = `${spacers.bottom}px`;
    }

    _captureVisualAnchor() {
      const root = this._firstVisibleRoot();
      return root ? { id: root.dataset.historyMessageId, top: root.getBoundingClientRect().top } : null;
    }

    _restoreVisualAnchor(anchor) {
      const root = this.historyLayer.querySelector(`[data-history-message-id="${global.CSS?.escape ? global.CSS.escape(anchor.id) : anchor.id}"]`);
      if (root) this.scrollElement.scrollTop += computeAnchorDelta(anchor.top, root.getBoundingClientRect().top);
    }

    _restoreSavedAnchor(anchor) {
      if (!anchor.messageId) return;
      const root = this.historyLayer.querySelector(`[data-history-message-id="${global.CSS?.escape ? global.CSS.escape(anchor.messageId) : anchor.messageId}"]`);
      if (!root) return;
      const currentOffset = root.getBoundingClientRect().top - this.scrollElement.getBoundingClientRect().top;
      this.scrollElement.scrollTop += currentOffset - anchor.offset;
    }

    _firstVisibleRoot() {
      const scrollTop = this.scrollElement.getBoundingClientRect().top;
      return Array.from(this.historyLayer.querySelectorAll('[data-history-message-id]'))
        .find(root => root.getBoundingClientRect().bottom >= scrollTop) || null;
    }

    _detailsKey(details) {
      const root = details.closest('[data-history-message-id]');
      if (!root) return '';
      const all = Array.from(root.querySelectorAll('details'));
      return presentationStateKey(root.dataset.historyMessageId, `details:${all.indexOf(details)}`);
    }

    _captureDetailsState(event) {
      if (!this.entry || event.target?.tagName !== 'DETAILS') return;
      const key = this._detailsKey(event.target);
      if (key) this.entry.presentationState.set(key, !!event.target.open);
    }

    _restoreDetailsState(parent = this.historyLayer) {
      if (!this.entry) return;
      for (const details of parent.querySelectorAll('details')) {
        const key = this._detailsKey(details);
        if (key && this.entry.presentationState.has(key)) details.open = this.entry.presentationState.get(key);
      }
    }
  }

  global.ChatHistoryRuntime = Object.freeze({
    ChatHistoryStore,
    ChatHistoryView,
    computeAnchorDelta,
    computeSpacerHeights,
    computeWindowRange,
    createConversationKey,
    claimChatSubmission,
    normalizedMessage,
    presentationStateKey,
    removeReconciledOptimisticNodes,
    removeProviderRunNodes,
    stableHistoryHash,
    constants,
  });
  Object.defineProperty(global, '__voChatHistoryDebug', {
    configurable: true,
    get() {
      return Object.freeze({
        cacheHits: aggregateDebug.cacheHits,
        cacheMisses: aggregateDebug.cacheMisses,
        evictions: aggregateDebug.evictions,
        renderBatches: aggregateDebug.renderBatches,
        maxRenderBatchMs: aggregateDebug.maxRenderBatchMs,
      });
    },
  });
})(globalThis);
