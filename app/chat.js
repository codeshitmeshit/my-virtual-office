// Virtual Office Chat — Gateway WebSocket Client (Multi-Window)
(() => {
  let GATEWAY_TOKEN = '';
  let ws = null;
  let reqId = 0;
  let connected = false;
  let pendingCallbacks = {};
  let _chatWsPort = 8091;
  let _chatWsPath = '/ws';
  let GATEWAY_CLIENT_VERSION = 'unknown';
  let _modelBarInterval = null;
  let _sessionsListCache = { at: 0, promise: null, payload: null };
  const runOwners = new Map();
  const _ct = (key, params) => typeof i18n !== 'undefined' ? i18n.t(key, params) : key;

  const MAX_INPUT_LINES = 15;
  const CHAT_STACK_GAP = 12;
  const STREAM_RENDER_INTERVAL_MS = 80;
  const TOOL_RENDER_INTERVAL_MS = 90;
  const MAX_LIVE_TOOL_CARDS = 40;
  const MAX_TOOL_PAYLOAD_CHARS = 6000;
  const ACTIVE_RUN_RECOVERY_MS = 15000;
  const PROVIDER_PROGRESS_MAX_AGE_MS = 120000;
  const HERMES_APPROVAL_POLL_MS = 1500;
  const chatConfirmLabel = () => {
    const label = _ct('confirm');
    return label === 'confirm' ? '确认' : label;
  };
  function visibleProviderThinking(providerKind, value, status = '') {
    const text = String(value || '').trim();
    const normalized = text.toLowerCase();
    const normalizedStatus = String(status || '').trim().toLowerCase();
    if (!text || normalized === normalizedStatus) return '';
    if (['queued', 'starting', 'running', 'completed', 'complete', 'done', 'success', 'failed', 'error', 'execution_failed', 'cancelled', 'canceled'].includes(normalized)) return '';
    if (providerKind === 'claude-code' && ['claude code completed.', 'claude code completed'].includes(normalized)) return '';
    if (providerKind === 'codex' && ['codex run 已完成', 'codex run 未完成', 'codex run 正在执行', 'codex run 正在取消', 'waiting for codex run events.'].includes(normalized)) return '';
    return text;
  }
  function providerProgressStatus(progress) {
    return String(progress?.status || progress?.error && 'failed' || '').toLowerCase();
  }
  function isTerminalProviderProgress(progress) {
    return ['completed', 'complete', 'done', 'success', 'failed', 'error', 'execution_failed', 'cancelled', 'canceled'].includes(providerProgressStatus(progress));
  }
  function isRecoverableProviderProgress(progress) {
    if (!progress || typeof progress !== 'object' || isTerminalProviderProgress(progress)) return false;
    if (progress.active || progress.activeRunId || progress.runActive || progress.activeConversationId) return true;
    const ts = Number(progress.ts || progress.epochMs || progress.updatedAt || progress.startedAt || 0);
    if (ts > 0 && Date.now() - ts > PROVIDER_PROGRESS_MAX_AGE_MS) return false;
    return true;
  }
  function showChatConfirmDialog(options = {}) {
    return new Promise((resolve) => {
      const existing = document.getElementById('chat-confirm-dialog');
      if (existing) existing.remove();

      const previouslyFocused = document.activeElement;
      const modal = document.createElement('div');
      modal.id = 'chat-confirm-dialog';
      modal.className = 'modal chat-confirm-dialog';
      modal.innerHTML =
        '<div class="modal-content chat-confirm-modal">' +
          '<div class="modal-header">' +
            '<span class="modal-emoji">' + escHtml(options.emoji || '🗜') + '</span>' +
            '<h2>' + escHtml(options.title || '') + '</h2>' +
            '<span class="close-btn" data-chat-confirm-cancel>&times;</span>' +
          '</div>' +
          '<div class="chat-confirm-body">' + escHtml(options.message || '') + '</div>' +
          '<div class="modal-controls chat-confirm-actions">' +
            '<button type="button" class="mtg-btn" data-chat-confirm-cancel>' + escHtml(options.cancelLabel || _ct('cancel')) + '</button>' +
            '<button type="button" class="mtg-btn mtg-btn-end" data-chat-confirm-ok>' + escHtml(options.confirmLabel || chatConfirmLabel()) + '</button>' +
          '</div>' +
        '</div>';

      let resolved = false;
      const close = (value) => {
        if (resolved) return;
        resolved = true;
        modal.remove();
        document.removeEventListener('keydown', onKeydown, true);
        if (previouslyFocused && typeof previouslyFocused.focus === 'function') previouslyFocused.focus();
        resolve(!!value);
      };
      const onKeydown = (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          close(false);
        } else if (e.key === 'Enter') {
          e.preventDefault();
          close(true);
        }
      };
      modal.addEventListener('click', (e) => {
        if (e.target === modal || e.target.closest('[data-chat-confirm-cancel]')) close(false);
        if (e.target.closest('[data-chat-confirm-ok]')) close(true);
      });
      document.addEventListener('keydown', onKeydown, true);
      document.body.appendChild(modal);
      modal.querySelector('[data-chat-confirm-ok]')?.focus();
    });
  }
  const getHermesProgressSteps = () => [
    _ct('hermes_step_receive'),
    _ct('hermes_step_load_profile'),
    _ct('hermes_step_run_loop'),
    _ct('hermes_step_wait_updates'),
    _ct('hermes_step_export_activity'),
    _ct('hermes_step_render_reply')
  ];
  const secondarySlotButtons = Array.from(document.querySelectorAll('[data-chat-slot-toggle]'));
  const CHAT_SELECTION_STORAGE_KEY = 'vo-chat-selections';
  let activeSecondarySlot = null;
  const secondaryPanelPlaceholders = {
    1: document.getElementById('chat-secondary-1'),
    2: document.getElementById('chat-secondary-2'),
    3: document.getElementById('chat-secondary-3')
  };
  let secondaryChatPanels = {};

  function readSavedChatSelections() {
    try {
      const saved = JSON.parse(localStorage.getItem(CHAT_SELECTION_STORAGE_KEY) || '{}');
      return saved && typeof saved === 'object' ? saved : {};
    } catch (e) {
      return {};
    }
  }

  function getSavedChatSelection(slotId) {
    const saved = readSavedChatSelections()[slotId];
    if (!saved || typeof saved !== 'object') return null;
    if (!saved.selectedAgentKey || !saved.sessionKey) return null;
    return saved;
  }

  function saveChatSelection(slotId, selection) {
    if (!slotId || !selection?.selectedAgentKey || !selection?.sessionKey) return;
    try {
      const saved = readSavedChatSelections();
      saved[slotId] = {
        selectedAgentKey: selection.selectedAgentKey,
        sessionKey: selection.sessionKey
      };
      localStorage.setItem(CHAT_SELECTION_STORAGE_KEY, JSON.stringify(saved));
    } catch (e) {
      console.warn('[chat] Failed to save chat selection:', e);
    }
  }

  class ChatWindow {
    constructor(root, options = {}) {
      this.root = root;
      this.isPrimary = !!options.isPrimary;
      this.slot = options.slot || null;
      this.slotId = this.isPrimary ? 'primary' : `secondary-${this.slot}`;
      this.root.dataset.chatSlot = this.slotId;
      const savedSelection = getSavedChatSelection(this.slotId);
      this.agentList = [];
      this.selectedAgentKey = options.selectedAgentKey || savedSelection?.selectedAgentKey || 'main';
      this.sessionKey = options.sessionKey || savedSelection?.sessionKey || 'agent:main:main';
      this.hasExplicitAgentSelection = !!savedSelection;
      this.currentRunId = null;
      this.streamingMsg = null;
      this.liveToolCards = new Map();
      this.pendingToolEvents = new Map();
      this.toolFlushTimer = null;
      this.pendingStreamContent = '';
      this.streamRenderTimer = null;
      this.scrollFrame = null;
      this.lastLiveEventAt = 0;
      this.recoveryTimer = null;
      this.hermesProgressTimers = [];
      this.hermesHistoryPollTimer = null;
      this.hermesEventSource = null;
      this.hermesStreamCancel = null;
      this.hermesSendStartedAt = 0;
      this.feishuEventSource = null;
      this.feishuHistoryRefreshTimer = null;
      this.hermesCompletedToolKeys = new Set();
      this.codexHistoryPollTimer = null;
      this.codexEventSource = null;
      this.codexStreamCancel = null;
      this.codexCompletedToolKeys = new Set();
      this.claudeCodeHistoryPollTimer = null;
      this.claudeCodeEventSource = null;
      this.claudeCodeStreamCancel = null;
      this.claudeCodeSendStartedAt = 0;
      this.claudeCodeCompletedToolKeys = new Set();
      this.hermesApprovalPollTimer = null;
      this.hermesApprovalLastId = '';
      this.sendInFlight = false;
      this.codexBusy = false;
      this.codexRequestInFlight = false;
      this.codexActivityTimer = null;
      this.codexLastSequence = 0;
      this.codexInteractionCards = new Map();
      this.codexReasoningCards = new Map();
      this.codexRunStatusCards = new Map();
      this.codexEventSource = null;
      this.claudeCodeEventSource = null;
      this.claudeCodeCompletedToolKeys = new Set();
      this.sessionModel = '—';
      this.contextWindow = 0;
      this.contextUsed = 0;
      this.pendingAttachments = [];
      this.isRecording = false;
      this.mediaRecorder = null;
      this.audioChunks = [];

      this.messages = root.querySelector('.chat-messages');
      this.status = root.querySelector('.chat-status');
      this.feishuLiveStatus = root.querySelector('.chat-feishu-live-status');
      this.agentSelect = root.querySelector('.chat-agent-select');
      this.modelName = root.querySelector('.chat-model-name, #chat-model-name');
      this.contextInfo = root.querySelector('.chat-context-info, #chat-context-info');
      this.input = root.querySelector('.chat-input');
      this.sendBtn = root.querySelector('.chat-send-btn');
      this.stopBtn = root.querySelector('.chat-stop-btn');
      this.attachBtn = root.querySelector('.chat-attach-btn');
      this.fileInput = root.querySelector('.chat-file-input');
      this.attachmentsPreview = root.querySelector('.chat-attachments-preview');
      this.micBtn = root.querySelector('.chat-mic-btn');
      this.newSessionBtn = root.querySelector('.chat-new-session');
      this.compactContextBtn = root.querySelector('.chat-compact-context');
      this.closeBtn = root.querySelector('.chat-close, .chat-secondary-close');

      this.messages.addEventListener('click', (e) => {
        if (e.target.classList.contains('chat-image-clickable') || e.target.classList.contains('chat-image-thumb')) {
          openImageLightbox(e.target.src);
        }
      });

      this.agentSelect?.addEventListener('change', (event) => {
        event.__voChatHandledByInstance = true;
        const opt = this.agentSelect.selectedOptions[0];
        if (!opt) return;
        this.applySelection(opt, { markExplicit: true, systemPrefix: typeof i18n !== 'undefined' ? i18n.t('chat_switched_to') : 'Switched to' });
      });

      this.sendBtn?.addEventListener('click', () => this.sendMessage());
      this.stopBtn?.addEventListener('click', () => this.sendStop());
      this.input?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.sendMessage();
        }
      });
      this.input?.addEventListener('input', () => this.autoResizeInput());
      this.input?.addEventListener('paste', (e) => this.handlePaste(e));

      this.attachBtn?.addEventListener('click', () => this.fileInput?.click());
      this.fileInput?.addEventListener('change', () => this.handleFiles());
      this.micBtn?.addEventListener('click', () => this.toggleRecording());
      this.newSessionBtn?.addEventListener('click', () => this.newSession());
      this.compactContextBtn?.addEventListener('click', () => this.compactCodexContext());
      this.closeBtn?.addEventListener('click', () => {
        if (this.isPrimary) {
          const chatPanel = document.getElementById('chat-panel');
          const chatBtn = document.getElementById('chat-toggle');
          // Clear snap/floating state and inline styles before closing
          chatPanel.classList.remove('open', 'floating', 'snap-left', 'snap-right', 'dragging', 'move-active');
          chatPanel.style.left = '';
          chatPanel.style.top = '';
          chatPanel.style.right = '';
          chatPanel.style.bottom = '';
          chatPanel.style.width = '';
          chatPanel.style.height = '';
          chatPanel.style.transform = '';
          chatBtn.style.display = 'flex';
          chatBtn.classList.remove('active');
          if (exteriorTabs) exteriorTabs.classList.remove('visible');
          closeAllSecondaryPanels();
          _chatExitMoveMode();
        } else if (this.slot) {
          _secExitMoveMode(this.slot);
          setSecondaryPanelOpen(this.slot, false);
        }
      });

      this.root.addEventListener('mousedown', () => {
        if (!this.isPrimary && this.slot) setActiveSecondarySlot(this.slot);
      });
      this.root.addEventListener('focusin', () => {
        if (!this.isPrimary && this.slot) setActiveSecondarySlot(this.slot);
      });
    }

    resetConversation(systemText) {
      this.closeCodexEventSource();
      this.closeHermesEventSource();
      this.closeClaudeCodeEventSource();
      this.closeFeishuEventSource();
      this.stopCodexActivityPolling();
      this.stopHermesHistoryPolling();
      this.stopCodexHistoryPolling();
      this.stopClaudeCodeHistoryPolling();
      this.messages.innerHTML = '';
      this.streamingMsg = null;
      this.pendingStreamContent = '';
      if (this.streamRenderTimer) { clearTimeout(this.streamRenderTimer); this.streamRenderTimer = null; }
      if (this.toolFlushTimer) { clearTimeout(this.toolFlushTimer); this.toolFlushTimer = null; }
      if (this.recoveryTimer) { clearInterval(this.recoveryTimer); this.recoveryTimer = null; }
      this.stopHermesProgressTimers();
      this.stopHermesApprovalPolling();
      this.stopCodexApprovalPolling();
      this.pendingToolEvents.clear();
      this.liveToolCards.clear();
      this.codexInteractionCards.clear();
      this.codexReasoningCards.clear();
      this.codexRunStatusCards.clear();
      this.codexLastSequence = 0;
      this.currentRunId = null;
      this.sessionModel = '—';
      this.contextWindow = 0;
      this.contextUsed = 0;
      this.updateModelBar();
      if (systemText) this.appendSystem(systemText);
    }

    setStatus(text, cls) {
      if (!this.status) return;
      this.status.textContent = text;
      this.status.className = 'chat-status ' + (cls || '');
    }

    formatTokens(n, options = {}) {
      const value = Number(n) || 0;
      if (options.exact && value < 1000000) return Math.round(value).toLocaleString();
      if (value >= 1000000) return (value / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
      if (value >= 1000) return (value / 1000).toFixed(value < 100000 ? 1 : 0).replace(/\.0$/, '') + 'k';
      return String(Math.round(value));
    }

    updateModelBar() {
      if (!this.modelName || !this.contextInfo) return;
      const shortModel = this.sessionModel.includes('/') ? this.sessionModel.split('/').pop() : this.sessionModel;
      this.modelName.textContent = shortModel;
      if (this.contextWindow > 0 && this.contextUsed > 0) {
        this.contextInfo.textContent = this.formatTokens(this.contextUsed) + ' / ' + this.formatTokens(this.contextWindow);
      } else if (this.contextWindow > 0) {
        this.contextInfo.textContent = '— / ' + this.formatTokens(this.contextWindow);
      } else {
        this.contextInfo.textContent = '';
      }
    }

    applySessionMetrics(data) {
      data = data && typeof data === 'object' ? data : {};
      if (data.model) this.sessionModel = String(data.model);
      const usage = data.usage && typeof data.usage === 'object' ? data.usage : {};
      const contextWindow = Number(data.contextWindow || data.context_window || usage.contextWindow || usage.context_window || 0);
      const contextUsed = Number(data.contextUsed || data.context_used || data.totalTokens || data.total_tokens || usage.totalTokens || usage.total_tokens || usage.inputTokens || usage.input_tokens || 0);
      if (contextWindow > 0) this.contextWindow = Math.max(this.contextWindow || 0, contextWindow);
      if (contextUsed > 0) this.contextUsed = contextUsed;
      this.updateModelBar();
    }

    autoResizeInput() {
      if (!this.input) return;
      const lineHeight = parseInt(getComputedStyle(this.input).fontSize) * 1.4;
      const inputMaxHeight = lineHeight * MAX_INPUT_LINES;
      this.input.style.height = 'auto';
      const newHeight = Math.min(this.input.scrollHeight, inputMaxHeight);
      this.input.style.height = newHeight + 'px';
      this.input.style.overflowY = this.input.scrollHeight > inputMaxHeight ? 'auto' : 'hidden';
    }

    syncAgentSelect() {
      if (!this.agentSelect) return;
      const options = Array.from(this.agentSelect.querySelectorAll('option'));
      let matched = false;
      for (const opt of options) {
        const isMatch = opt.value === this.selectedAgentKey && opt.dataset.sessionKey === this.sessionKey;
        opt.selected = isMatch;
        if (isMatch) matched = true;
      }
      if (!matched) {
        const fallback = options.find(opt => opt.value === this.selectedAgentKey) || options.find(opt => opt.dataset.sessionKey === this.sessionKey) || options[0];
        if (fallback) {
          fallback.selected = true;
          this.selectedAgentKey = fallback.value;
          this.sessionKey = fallback.dataset.sessionKey || this.sessionKey;
          this.saveSelection();
        }
      }
    }

    saveSelection() {
      saveChatSelection(this.slotId, {
        selectedAgentKey: this.selectedAgentKey,
        sessionKey: this.sessionKey
      });
    }

    applySelection(opt, { markExplicit = false, systemPrefix = typeof i18n !== 'undefined' ? i18n.t('chat_switched_to') : 'Switched to' } = {}) {
      if (!opt) return;
      const newSessionKey = opt.dataset.sessionKey;
      const newAgentKey = opt.value;
      if (newSessionKey === this.sessionKey && newAgentKey === this.selectedAgentKey) {
        if (markExplicit) {
          this.hasExplicitAgentSelection = true;
          this.saveSelection();
        }
        if (connected || this.isHermesSelected() || this.isCodexSelected() || this.isClaudeCodeSelected()) {
          this.fetchSessionInfo();
          this.updateFeishuEventSource();
          this.loadHistory();
        }
        return;
      }
      this.selectedAgentKey = newAgentKey;
      this.sessionKey = newSessionKey;
      if (markExplicit) this.hasExplicitAgentSelection = true;
      this.saveSelection();
      this.currentRunId = null;
      this.streamingMsg = null;
      this.sendInFlight = false;
      this.codexBusy = false;
      this.codexRequestInFlight = false;
      this.closeCodexEventSource();
      this.closeHermesEventSource();
      this.closeClaudeCodeEventSource();
      this.closeFeishuEventSource();
      this.stopCodexActivityPolling();
      this.stopHermesHistoryPolling();
      this.stopCodexHistoryPolling();
      this.stopClaudeCodeHistoryPolling();
      this.stopHermesProgressTimers();
      this.removeTypingIndicator();
      this.syncAgentSelect();
      this.resetConversation(`${systemPrefix} ${opt.textContent.trim()}`);
      this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_loading_history') : 'Loading chat history...');
      this.updateProviderControls();
      if (this.isHermesSelected()) this.startHermesApprovalPolling();
      else this.stopHermesApprovalPolling();
      if (this.isCodexSelected()) this.startCodexApprovalPolling();
      else this.stopCodexApprovalPolling();
      this.updateFeishuEventSource();
      this.loadHistory();
      if (connected || this.isHermesSelected() || this.isCodexSelected() || this.isClaudeCodeSelected()) {
        this.fetchSessionInfo();
      }
    }

    async loadAgentList() {
      try {
        const res = await fetch('/agents-list');
        const data = await res.json();
        if (!data.agents || !this.agentSelect) return;
        this.agentList = data.agents;
        this.agentSelect.innerHTML = '';
        const branches = {};
        for (const a of this.agentList) {
          if (!branches[a.branch]) branches[a.branch] = [];
          branches[a.branch].push(a);
        }
        for (const [branch, agents] of Object.entries(branches)) {
          const group = document.createElement('optgroup');
          group.label = branch;
          for (const a of agents) {
            const opt = document.createElement('option');
            opt.value = a.key;
            opt.textContent = `${a.emoji} ${a.name}`;
            opt.dataset.sessionKey = a.sessionKey;
            opt.dataset.agentId = a.agentId;
            opt.dataset.providerKind = a.providerKind || 'openclaw';
            opt.dataset.providerType = a.providerType || 'runtime';
            opt.dataset.providerAgentId = a.providerAgentId || a.agentId;
            group.appendChild(opt);
          }
          this.agentSelect.appendChild(group);
        }
        this.syncAgentSelect();
        this.updateProviderControls();
        this.updateFeishuEventSource();
      } catch (e) {
        console.warn('[chat] Failed to load agent list:', e);
      }
    }

    isVisibleForPolling() {
      return this.isPrimary ? this.root.classList.contains('open') : this.root.classList.contains('open');
    }

    async fetchContextUsage() {
      if (!this.isVisibleForPolling()) return;
      if (this.isHermesSelected() || this.isCodexSelected() || this.isClaudeCodeSelected()) return;
      try {
        // Avoid broad sessions.list polling. Describe only the selected session.
        const res = await rpc('sessions.describe', { key: this.sessionKey });
        const s = res?.payload?.session;
        if (!res.ok || !s) return;
        if (s.totalTokens > 0) this.contextUsed = s.totalTokens;
        if (s.contextTokens > 0 && s.contextTokens > this.contextWindow) this.contextWindow = s.contextTokens;
        // Don't update model from gateway transcript — it can be stale.
        // Model display is driven by fetchSessionInfo() from server config.
        this.updateModelBar();
      } catch (e) {
        console.warn('[chat] Failed to fetch context usage:', e);
      }
    }

    getSelectedAgentId() {
      if (!this.agentSelect) return null;
      const opt = this.agentSelect.selectedOptions[0];
      return opt?.dataset?.agentId || null;
    }

    getSelectedProviderKind() {
      const opt = this.agentSelect?.selectedOptions?.[0];
      return opt?.dataset?.providerKind || 'openclaw';
    }

    getSelectedProviderKindStrict() {
      const opt = this.agentSelect?.selectedOptions?.[0];
      return opt?.dataset?.providerKind || '';
    }

    isHermesSelected() {
      return this.getSelectedProviderKind() === 'hermes' || String(this.sessionKey || '').startsWith('hermes:');
    }

    isCodexSelected() {
      return this.getSelectedProviderKind() === 'codex' || String(this.sessionKey || '').startsWith('codex:');
    }

    isClaudeCodeSelected() {
      return this.getSelectedProviderKind() === 'claude-code' || String(this.sessionKey || '').startsWith('claude-code:');
    }

    getSelectedAgentRecord() {
      const agentId = this.getSelectedAgentId();
      return (this.agentList || []).find(a =>
        a.key === this.selectedAgentKey ||
        a.sessionKey === this.sessionKey ||
        a.agentId === agentId ||
        a.key === agentId
      ) || null;
    }

    isArchiveManagerSelected() {
      const a = this.getSelectedAgentRecord();
      return !!(a && (a.systemRole === 'archive_manager' || a.archiveManager));
    }

    isArchiveRelatedMessage(text) {
      const lower = String(text || '').toLowerCase();
      return [
        '档案', '归档', '档案室', '项目产物', '产物', '上下文', '入场包', '目录', '来源', '证据',
        'archive', 'archives', 'archival', 'artifact', 'artifacts', 'onboarding', 'context',
        'catalog', 'source', 'sources', 'evidence', 'summary', 'summaries'
      ].some(k => lower.includes(k));
    }

    archiveManagerBoundaryReply() {
      return '我是档案管理员，只处理档案室、项目上下文、产物来源、入场包和归档维护相关问题。普通执行、编码、审查、闲聊或项目任务分配请转给对应执行 AI。';
    }

    updateProviderControls() {
      if (this.compactContextBtn) this.compactContextBtn.style.display = this.isCodexSelected() ? '' : 'none';
      if (this.stopBtn) this.stopBtn.style.display = '';
      if (!this.currentRunId && !this.streamingMsg) {
        const providerKind = this.getSelectedProviderKindStrict();
        if (providerKind === 'hermes') this.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_ready') : 'Hermes ready', 'connected');
        else if (providerKind === 'claude-code') this.setStatus(_ct('claude_code_ready'), 'connected');
        else if (providerKind === 'codex') this.setStatus(_ct('codex_ready'), 'connected');
        else this.setStatus(connected ? ((typeof i18n !== 'undefined' ? i18n.t('connected') : 'Connected') + ' ⚡') : (typeof i18n !== 'undefined' ? i18n.t('chat_disconnected_label') : 'Disconnected'), connected ? 'connected' : 'disconnected');
      }
    }

    codexConversationStorageKey() {
      return `vo-codex-conversation:${this.slotId}:${this.selectedAgentKey}`;
    }

    getCodexConversationId() {
      const key = this.codexConversationStorageKey();
      let value = localStorage.getItem(key);
      if (!value) {
        value = `codex-${this.slotId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(key, value);
      }
      return value;
    }

    rotateCodexConversationId() {
      const value = `codex-${this.slotId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(this.codexConversationStorageKey(), value);
      return value;
    }

    providerConversationStorageKey(providerKind) {
      return `vo-${providerKind}-conversation:${this.slotId}:${this.selectedAgentKey}`;
    }

    getProviderConversationId(providerKind) {
      const key = this.providerConversationStorageKey(providerKind);
      let value = localStorage.getItem(key);
      if (!value) {
        value = `${providerKind}-${this.slotId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(key, value);
      }
      return value;
    }

    rotateProviderConversationId(providerKind) {
      const value = `${providerKind}-${this.slotId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(this.providerConversationStorageKey(providerKind), value);
      return value;
    }

    startHermesApprovalPolling() {
      if (!this.isHermesSelected() || this.hermesApprovalPollTimer) return;
      this.pollHermesApproval().catch(() => {});
      this.hermesApprovalPollTimer = setInterval(() => {
        this.pollHermesApproval().catch(() => {});
      }, HERMES_APPROVAL_POLL_MS);
    }

    stopHermesApprovalPolling() {
      if (this.hermesApprovalPollTimer) {
        clearInterval(this.hermesApprovalPollTimer);
        this.hermesApprovalPollTimer = null;
      }
      this.hermesApprovalLastId = '';
    }

    async pollHermesApproval() {
      if (!this.isHermesSelected() || !this.isVisibleForPolling()) return;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const res = await fetch('/api/hermes/approval/pending?agentId=' + encodeURIComponent(agentId));
      const data = await res.json();
      if (!data.ok || !data.pending) return;
      this.appendHermesPendingApproval(data.pending, data.pending_count || 1);
    }

    appendHermesPendingApproval(approval, pendingCount = 1) {
      if (!approval) return;
      const approvalId = approval.approval_id || approval.id || '';
      if (approvalId) {
        const existing = [...this.messages.querySelectorAll('[data-approval-id]')].find(el => el.dataset.approvalId === approvalId);
        if (existing) return;
      }
      const enriched = {
        ...approval,
        id: approvalId || approval.id,
        approval_id: approvalId || approval.approval_id,
        pending_count: pendingCount
      };
      this.hermesApprovalLastId = enriched.id || '';
      this.appendMessage(
        'assistant',
        '',
        Date.now(),
        [],
        {
          label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Hermes',
          kind: 'agent',
          approval: enriched
        },
        []
      );
      this.scrollBottom();
    }

    startCodexApprovalPolling() {
      this.stopCodexApprovalPolling();
      this.pollCodexApproval().catch(() => {});
      this.codexApprovalPollTimer = setInterval(() => {
        this.pollCodexApproval().catch(() => {});
      }, HERMES_APPROVAL_POLL_MS);
    }

    stopCodexApprovalPolling() {
      if (this.codexApprovalPollTimer) {
        clearInterval(this.codexApprovalPollTimer);
        this.codexApprovalPollTimer = null;
      }
      this.codexApprovalLastId = '';
    }

    async pollCodexApproval() {
      if (!this.isCodexSelected() || !this.isVisibleForPolling()) return;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const res = await fetch('/api/codex/approval/pending?agentId=' + encodeURIComponent(agentId));
      const data = await res.json();
      if (!data.ok || !data.pending) return;
      this.appendCodexPendingApproval(data.pending, data.pending_count || 1);
    }

    appendCodexPendingApproval(approval, pendingCount = 1) {
      if (!approval) return;
      const approvalId = approval.approval_id || approval.id || '';
      if (approvalId) {
        const existing = [...this.messages.querySelectorAll('[data-approval-id]')].find(el => el.dataset.approvalId === approvalId);
        if (existing) return;
      }
      const enriched = {
        ...approval,
        id: approvalId || approval.id,
        approval_id: approvalId || approval.approval_id,
        pending_count: pendingCount,
        provider: approval.provider || 'codex-app-server'
      };
      this.codexApprovalLastId = enriched.id || '';
      this.appendMessage(
        'assistant',
        '',
        Date.now(),
        [],
        {
          label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex',
          kind: 'agent',
          approval: enriched
        },
        []
      );
      this.scrollBottom();
    }

    async fetchSessionInfo() {
      let gatewayContext = 0;
      try {
        // Targeted lookup avoids rebuilding the full sessions.list index.
        if (!this.isHermesSelected() && !this.isCodexSelected()) {
          const res = await rpc('sessions.describe', { key: this.sessionKey });
          const s = res?.payload?.session;
          if (res.ok && s) {
            if (s.totalTokens > 0) this.contextUsed = s.totalTokens;
            if (s.contextTokens > 0) gatewayContext = s.contextTokens;
          }
        }
      } catch (e) {
        console.warn('[chat] sessions.describe failed:', e);
      }
      let serverContext = 0;
      try {
        // Pass current agent ID so server returns the correct configured model
        const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
        const qs = agentId ? `?agent=${encodeURIComponent(agentId)}` : '';
        const res = await fetch('/session-info' + qs);
        const data = await res.json();
        // Always use the configured model from the server — this reflects
        // what the agent is SET to use, not what was last used historically.
        // The gateway transcript model can be stale (from before a model change).
        this.applySessionMetrics(data);
        if (data.contextWindow) serverContext = data.contextWindow;
      } catch (e) {
        console.warn('[chat] /session-info failed:', e);
      }
      this.contextWindow = Math.max(gatewayContext, serverContext, this.contextWindow || 0);
      this.updateModelBar();
    }

    async loadHistory(opts = {}) {
      const loadToken = (this.historyLoadToken || 0) + 1;
      this.historyLoadToken = loadToken;
      const expectedAgentKey = this.selectedAgentKey;
      const expectedSessionKey = this.sessionKey;
      const isCurrentHistoryRequest = () => (
        this.historyLoadToken === loadToken &&
        this.selectedAgentKey === expectedAgentKey &&
        this.sessionKey === expectedSessionKey
      );
      try {
        if (this.isCodexSelected()) {
          this.startCodexApprovalPolling();
          const conversationId = this.getCodexConversationId();
          const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
          const res = await fetch('/api/codex/history?agentId=' + encodeURIComponent(agentId) + '&conversationId=' + encodeURIComponent(conversationId));
          const data = await res.json();
          if (!isCurrentHistoryRequest()) return;
          if (data.ok && Array.isArray(data.events)) {
            this.messages.innerHTML = '';
            this.liveToolCards.clear();
            this.codexInteractionCards.clear();
            this.codexReasoningCards.clear();
            this.codexRunStatusCards.clear();
            const progressById = new Map();
            const renderedHistoryKeys = new Set();
            for (const event of data.events) {
              const codexMeta = event.metadata?.codex || event.metadata || {};
              if (codexMeta.ephemeral === 'codex-progress') {
                const progress = codexMeta.progress && typeof codexMeta.progress === 'object'
                  ? codexMeta.progress
                  : {
                      ...(codexMeta || {}),
                      text: event.text || '',
                      ts: event.ts || Date.now(),
                      agentId: event.from?.id || agentId,
                      conversationId: event.conversationId || conversationId
                    };
                progressById.set(progress.progressId || codexMeta.progressId || event.id, progress);
                continue;
              }
              if (!event.text) continue;
              const rawText = String(event.text || '');
              const isA2AEnvelope = rawText.startsWith('[A2A ') && rawText.includes('Message from ') && rawText.includes('Reply directly to the sender');
              if (isA2AEnvelope) continue;
              const fromId = event.from?.id || '';
              const role = fromId === agentId ? 'assistant' : (fromId === 'user' ? 'user' : (event.direction === 'reply' ? 'assistant' : 'user'));
              let text = rawText;
              if (role === 'assistant' && Array.isArray(codexMeta.modifiedFiles) && codexMeta.modifiedFiles.length) {
                text += '\n\n' + _ct('modified_files') + ':\n' + codexMeta.modifiedFiles.map(path => '- ' + path).join('\n');
              }
              const historyKey = [
                event.id || event.commEventId || '',
                role,
                text,
                event.inReplyTo || '',
                (event.from && event.from.id) || '',
                (event.to && event.to.id) || ''
              ].join('\u0001');
              if (renderedHistoryKeys.has(historyKey)) continue;
              renderedHistoryKeys.add(historyKey);
              this.appendMessage(role, text, event.ts || Date.now(), [], role === 'assistant'
                ? { label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex', kind: 'agent' }
                : { label: event.from?.name || _ct('chat_you_label'), kind: 'human' });
            }
            for (const progress of progressById.values()) {
              this.restoreProviderProgress(progress, 'codex');
            }
            await this.appendFeishuChannelHistory(agentId, renderedHistoryKeys);
            this.scrollBottom();
            this.setStatus(_ct('codex_ready'), 'connected');
          }
          await this.pollCodexApproval().catch(() => {});
          this.codexLastSequence = 0;
          await this.pollCodexActivity(true, { replayHistoricalTurns: false });
          return;
        }
        if (this.isHermesSelected() || this.isClaudeCodeSelected()) {
          if (this.isHermesSelected()) this.startHermesApprovalPolling();
          const providerPath = this.isClaudeCodeSelected() ? 'claude-code' : 'hermes';
          const query = new URLSearchParams({ agentId: this.getSelectedAgentId() || this.selectedAgentKey });
          if (this.isClaudeCodeSelected()) query.set('conversationId', this.getProviderConversationId('claude-code'));
          else query.set('conversationId', this.getProviderConversationId('hermes'));
          const res = await fetch('/api/' + providerPath + '/history?' + query.toString());
          const data = await res.json();
          if (!isCurrentHistoryRequest()) return;
          if (data.ok && Array.isArray(data.messages)) {
            const providerKind = this.isClaudeCodeSelected() ? 'claude-code' : 'hermes';
            const recoveryStartedAt = Number(opts.startedAt || (providerKind === 'claude-code' ? this.claudeCodeSendStartedAt : this.hermesSendStartedAt) || 0);
            const hasFreshFinal = !opts.recoverFinal || !recoveryStartedAt || data.messages.some(msg => (
              msg &&
              msg.role === 'assistant' &&
              msg.ephemeral !== 'hermes-progress' &&
              msg.ephemeral !== 'claude-code-progress' &&
              Number(msg.ts || 0) >= recoveryStartedAt &&
              (msg.text || msg.thinking || msg.approval || (Array.isArray(msg.tools) && msg.tools.length))
            ));
            if (!hasFreshFinal) {
              this.scrollBottomAfterLayout();
              return;
            }
            this.applySessionMetrics(data);
            this.messages.innerHTML = '';
            for (const msg of data.messages) {
              if (msg.ephemeral === 'hermes-progress' || msg.ephemeral === 'claude-code-progress') {
                this.restoreProviderProgress(msg, this.isClaudeCodeSelected() ? 'claude-code' : 'hermes');
                continue;
              }
              if (msg.text || msg.thinking || msg.approval || (Array.isArray(msg.tools) && msg.tools.length)) {
                const meta = msg.role === 'assistant'
                  ? { ...resolveMessageSender(msg, this), thinking: visibleProviderThinking(providerKind, msg.thinking, msg.status), reasoningTokens: msg.reasoningTokens || 0, approval: msg.approval || null }
                  : { label: _ct('chat_you_label'), kind: 'human' };
                this.appendMessage(msg.role, msg.text || '', msg.ts || Date.now(), [], meta, normalizeHermesTools(msg.tools || []));
              }
            }
            await this.appendFeishuChannelHistory(this.getSelectedAgentId() || this.selectedAgentKey);
            this.scrollBottomAfterLayout();
          }
          if (this.isHermesSelected()) await this.pollHermesApproval().catch(() => {});
          return;
        }
        const res = await rpc('chat.history', { sessionKey: this.sessionKey, limit: 500 });
        if (!isCurrentHistoryRequest()) return;
        if (res.ok && res.payload?.messages) {
          const messages = res.payload.messages;
          const seenToolKeys = new Set();
          this.messages.innerHTML = '';
          for (const msg of messages) {
            const t = extractText(msg) || (typeof msg.content === 'string' ? msg.content : '');
            const ts = msg.timestamp || msg.ts || msg.message?.timestamp || null;
            const media = extractMedia(msg, t);
            const tools = extractToolItems(msg);
            for (const tool of tools) seenToolKeys.add(toolHistoryKey(tool));
            if (t || media.length || tools.length) this.appendMessage(msg.role, t, ts, media, resolveMessageSender(msg, this), tools);
          }
          await this.loadRecoveredActivity(seenToolKeys);
          const lastMeaningful = [...messages].reverse().find(m => {
            const t = extractText(m) || (typeof m.content === 'string' ? m.content : '');
            return t || extractToolItems(m).length;
          });
          const role = lastMeaningful?.role || lastMeaningful?.message?.role || '';
          if (opts.recoverFinal && role === 'assistant') {
            this.streamingMsg = null;
            this.pendingStreamContent = '';
            this.liveToolCards.clear();
            this.pendingToolEvents.clear();
            this.currentRunId = null;
            this.removeTypingIndicator();
            this.clearActivityFeed();
            this.stopRecoveryWatchdog();
          }
          this.scrollBottomAfterLayout();
        }
      } catch (e) {
        console.warn('Failed to load history:', e);
        if (isCurrentHistoryRequest() && opts.showError !== false) {
          this.messages.innerHTML = '';
          this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_history_unavailable') : 'Chat history is unavailable right now.');
        }
      }
    }

    setFeishuLiveStatus(state, detail = '') {
      if (!this.feishuLiveStatus) return;
      const t = (key, fallback) => (typeof i18n !== 'undefined' && i18n && typeof i18n.t === 'function') ? i18n.t(key) : fallback;
      const labels = {
        connecting: t('chat_feishu_live_connecting', 'Feishu live: connecting'),
        connected: t('chat_feishu_live_connected', 'Feishu live: connected'),
        disconnected: t('chat_feishu_live_disconnected', 'Feishu live: disconnected')
      };
      if (!state || state === 'hidden') {
        this.feishuLiveStatus.hidden = true;
        this.feishuLiveStatus.textContent = labels.disconnected;
        this.feishuLiveStatus.className = 'chat-feishu-live-status';
        this.feishuLiveStatus.title = '';
        return;
      }
      this.feishuLiveStatus.hidden = false;
      this.feishuLiveStatus.textContent = labels[state] || labels.disconnected;
      this.feishuLiveStatus.className = 'chat-feishu-live-status ' + state;
      this.feishuLiveStatus.title = detail || '';
    }

    async appendFeishuChannelHistory(agentId, renderedHistoryKeys = new Set()) {
      agentId = String(agentId || '').trim();
      if (!agentId) return;
      try {
        const query = new URLSearchParams({ agentId, limit: '500' });
        const res = await fetch('/api/agent-platform-communications/history?' + query.toString());
        const data = await res.json();
        if (!data.ok || !Array.isArray(data.events)) return;
        const rows = data.events.filter(event => {
          const meta = event && typeof event.metadata === 'object' ? event.metadata : {};
          const fromRef = event && typeof event.from === 'object' ? event.from : {};
          const toRef = event && typeof event.to === 'object' ? event.to : {};
          return event && event.visibleInOffice !== false && (
            meta.sourceApp === 'feishu' ||
            meta.channel === 'feishu' ||
            fromRef.sourceApp === 'feishu' ||
            toRef.sourceApp === 'feishu' ||
            String(event.conversationId || '').startsWith('feishu-dm:')
          );
        }).sort((a, b) => Number(a.ts || 0) - Number(b.ts || 0));
        for (const event of rows) {
          const eventMeta = event && typeof event.metadata === 'object' ? event.metadata : {};
          const attachments = Array.isArray(event.attachments)
            ? event.attachments
            : (Array.isArray(eventMeta.attachments) ? eventMeta.attachments : []);
          if (!event.text && !attachments.length) continue;
          const fromId = event.from?.id || '';
          const role = fromId === agentId ? 'assistant' : 'user';
          const text = String(event.text || '');
          const historyKey = [
            event.id || '',
            role,
            text,
            event.inReplyTo || '',
            (event.from && event.from.id) || '',
            (event.to && event.to.id) || '',
            attachments.map(item => item && (item.path || item.url || item.fileKey || item.name || '')).join('|')
          ].join('\u0001');
          if (renderedHistoryKeys.has(historyKey)) continue;
          renderedHistoryKeys.add(historyKey);
          const meta = role === 'assistant'
            ? { label: this.agentSelect.selectedOptions[0]?.textContent.trim() || agentId, kind: 'agent' }
            : { label: event.from?.name || 'Feishu', kind: 'human' };
          this.appendMessage(role, text, event.ts || Date.now(), attachments, meta);
        }
      } catch (e) {
        console.warn('[chat] Failed to load Feishu channel history:', e);
      }
    }

    async loadRecoveredActivity(seenToolKeys = new Set()) {
      try {
        const url = '/api/session-activity?sessionKey=' + encodeURIComponent(this.sessionKey) + '&limit=80';
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.ok || !Array.isArray(data.messages)) return;
        for (const msg of data.messages) {
          const tools = normalizeHistoricalTools(msg.tools || []).filter((tool) => {
            const key = toolHistoryKey(tool);
            if (seenToolKeys.has(key)) return false;
            seenToolKeys.add(key);
            return true;
          });
          if (!tools.length && !msg.text) continue;
          const ts = msg.epochMs || msg.ts || Date.now();
          this.appendMessage(msg.role || 'assistant', msg.text || '', ts, [], resolveMessageSender(msg, this), tools);
        }
      } catch (e) {
        console.warn('[chat] recovered activity load failed:', e);
      }
    }

    async newSession() {
      const agentName = this.agentSelect.selectedOptions[0]?.textContent.trim() || 'this agent';
      if (!confirm(_ct('new_session_confirm', { agent: agentName }))) return;
      if (this.isCodexSelected()) {
        const oldConversationId = this.getCodexConversationId();
        try {
          const res = await fetch('/api/codex/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId: this.getSelectedAgentId() || this.selectedAgentKey, conversationId: oldConversationId })
          });
          const data = await res.json();
          if (!res.ok || !data.ok) throw new Error(data.error || 'reset failed');
          this.rotateCodexConversationId();
          this.resetConversation(_ct('new_codex_session'));
        } catch (e) {
          this.appendSystem(_ct('chat_reset_error') + ': ' + e.message);
        }
        return;
      }
      if (this.isHermesSelected() || this.isClaudeCodeSelected()) {
        try {
          const providerKind = this.isClaudeCodeSelected() ? 'claude-code' : 'hermes';
          const providerPath = providerKind;
          const clearBody = { agentId: this.getSelectedAgentId() || this.selectedAgentKey };
          clearBody.conversationId = this.getProviderConversationId(providerKind);
          const res = await fetch('/api/' + providerPath + '/history/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(clearBody)
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || 'clear failed');
          this.rotateProviderConversationId(providerKind);
          this.resetConversation(this.isClaudeCodeSelected() ? _ct('new_claude_code_session') : _ct('new_hermes_session'));
        } catch (e) {
          this.appendSystem(_ct('chat_reset_error') + ': ' + e.message);
        }
        return;
      }
      if (!connected) { this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_not_connected') : 'Not connected'); return; }
      try {
        const res = await rpc('sessions.reset', { key: this.sessionKey });
        if (res.ok) {
          this.messages.innerHTML = '';
          this.streamingMsg = null;
          this.currentRunId = null;
          this.liveToolCards.clear();
          this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_new_session_started') : 'New session started');
        } else {
          this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_reset_failed') : 'Reset failed') + ': ' + JSON.stringify(res.error || res));
        }
      } catch (e) {
        this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_reset_error') : 'Reset error') + ': ' + e.message);
      }
    }

    handleFiles() {
      if (!this.fileInput) return;
      for (const file of this.fileInput.files) {
        const reader = new FileReader();
        reader.addEventListener('load', () => {
          const att = { id: Date.now() + '-' + Math.random().toString(36).slice(2), dataUrl: reader.result, mimeType: file.type || 'application/octet-stream', name: file.name };
          this.pendingAttachments.push(att);
          this.renderAttachmentPreviews();
        });
        reader.readAsDataURL(file);
      }
      this.fileInput.value = '';
    }

    handlePaste(e) {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          e.preventDefault();
          const file = item.getAsFile();
          const reader = new FileReader();
          reader.addEventListener('load', () => {
            const att = { id: Date.now() + '-' + Math.random().toString(36).slice(2), dataUrl: reader.result, mimeType: file.type, name: file.name || 'pasted-image.png' };
            this.pendingAttachments.push(att);
            this.renderAttachmentPreviews();
          });
          reader.readAsDataURL(file);
        }
      }
    }

    renderAttachmentPreviews() {
      this.attachmentsPreview.innerHTML = '';
      for (const att of this.pendingAttachments) {
        const div = document.createElement('div');
        div.className = 'chat-attach-item';
        if (att.mimeType.startsWith('image/')) {
          const img = document.createElement('img');
          img.src = att.dataUrl;
          div.appendChild(img);
        } else {
          const span = document.createElement('div');
          span.className = 'file-name';
          span.textContent = att.name;
          div.appendChild(span);
        }
        const rm = document.createElement('button');
        rm.className = 'chat-attach-remove';
        rm.textContent = '×';
        rm.addEventListener('click', () => {
          this.pendingAttachments = this.pendingAttachments.filter(a => a.id !== att.id);
          this.renderAttachmentPreviews();
        });
        div.appendChild(rm);
        this.attachmentsPreview.appendChild(div);
      }
    }

    restoreProviderProgress(progress, providerKind) {
      if (!isRecoverableProviderProgress(progress)) return;
      const runId = progress.runId || progress.turnId || progress.sessionId || progress.progressId || (providerKind + '-progress');
      const label = resolveMessageSender(progress, this).label || (
        providerKind === 'codex' ? 'Codex' : providerKind === 'claude-code' ? 'Claude Code' : 'Hermes'
      );
      this.currentRunId = runId;
      if (providerKind === 'codex') {
        const thinking = visibleProviderThinking('codex', progress.thinking, progress.status);
        this.renderCodexRunStatus({
          runId,
          label,
          status: 'running',
          text: thinking || progress.text || _ct('chat_processing'),
          ts: progress.ts || Date.now()
        });
        if (thinking) {
          this.renderCodexReasoning({
            type: 'reasoning',
            status: progress.status || 'running',
            text: thinking,
            turnId: progress.turnId || runId,
            itemId: progress.progressId || 'progress'
          });
        }
        if (progress.approval) this.appendCodexPendingApproval(progress.approval, progress.approval.pending_count || 1);
        for (const tool of (progress.tools || [])) {
          this.appendToolCall({
            runId,
            data: {
              toolCallId: tool.id || tool.toolCallId || tool.itemId || (runId + ':tool'),
              phase: 'update',
              name: tool.name || tool.tool || 'Codex activity',
              args: tool.arguments || tool.input || {},
              result: tool.result || tool.output || tool.error || '',
              isError: String(tool.status || '').toLowerCase() === 'error' || !!tool.error
            }
          });
        }
        this.setStatus(_ct('codex_ready'), 'connecting');
        return;
      }
      const meta = {
        ...resolveMessageSender(progress, this),
        thinking: visibleProviderThinking(providerKind, progress.thinking, progress.status),
        reasoningTokens: progress.reasoningTokens || 0,
        approval: progress.approval || null
      };
      this.appendMessage('assistant', progress.text || '', progress.ts || Date.now(), [], meta, normalizeHermesTools(progress.tools || []));
      this.updateTypingIndicator(label + ' ' + _ct('working'));
      this.setStatus(providerKind === 'claude-code' ? _ct('claude_code_stream_active') : _ct('chat_hermes_stream_active'), 'connecting');
      this.ensureRecoveryWatchdog();
    }

    async sendMessage() {
      let text = this.input.value.trim();
      const hasAttachments = this.pendingAttachments.length > 0;
      if (this.sendInFlight || (!text && !hasAttachments) || (!connected && !this.isHermesSelected() && !this.isCodexSelected() && !this.isClaudeCodeSelected()) || this.codexBusy) return;
      this.sendInFlight = true;

      this.input.value = '';
      this.input.style.height = 'auto';
      this.input.style.overflowY = 'hidden';

      let displayText = text || '';
      const imageDataUrls = this.pendingAttachments.filter(a => a.mimeType.startsWith('image/')).map(a => a.dataUrl);
      const nonImageNames = this.pendingAttachments.filter(a => !a.mimeType.startsWith('image/')).map(a => a.name);
      if (nonImageNames.length) displayText += (displayText ? '\n' : '') + '📎 ' + nonImageNames.join(', ');
      const localUserMessage = this.appendMessage('user', displayText, Date.now(), imageDataUrls, { label: _ct('chat_you_label'), kind: 'human' });
      this.scrollBottom();

      if (this.isArchiveManagerSelected() && !this.isArchiveRelatedMessage(text || displayText)) {
        this.sendInFlight = false;
        this.pendingAttachments = [];
        this.renderAttachmentPreviews();
        this.appendMessage('assistant', this.archiveManagerBoundaryReply(), Date.now(), [], {
          label: this.agentSelect.selectedOptions[0]?.textContent.trim() || '档案管理员',
          kind: 'agent'
        });
        this.scrollBottom();
        return;
      }

      let attachments;
      let uploadedFiles = [];
      if (hasAttachments) {
        const UPLOAD_URL = window.location.origin + '/upload';
        const imageAtts = [];
        const uploadAttachment = async (a) => {
          const b64 = a.dataUrl.split(',')[1];
          const resp = await fetch(UPLOAD_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: a.name, content: b64, mimeType: a.mimeType || '' })
          });
          if (!resp.ok) throw new Error(resp.statusText || ('HTTP ' + resp.status));
          const result = await resp.json();
          return {
            name: a.name,
            mimeType: a.mimeType || '',
            path: result.path || '',
            url: result.url || (result.path ? '/chat-media?path=' + encodeURIComponent(result.path) : ''),
            size: result.size || 0
          };
        };

        for (const a of this.pendingAttachments) {
          let uploaded = null;
          try {
            uploaded = await uploadAttachment(a);
            if (uploaded?.path || uploaded?.url) uploadedFiles.push(uploaded);
          } catch (e) {
            this.appendSystem('Upload failed for ' + a.name + ': ' + e.message);
            continue;
          }
          if (a.mimeType.startsWith('image/')) {
            const url = await compressImage(a.dataUrl);
            const parsed = parseDataUrl(url);
            if (parsed) imageAtts.push({ type: 'image', mimeType: parsed.mimeType, content: parsed.content });
          } else if (a.mimeType.startsWith('audio/') || /\.(mp3|wav|m4a|ogg|flac|webm|opus|aac)$/i.test(a.name)) {
            this.appendSystem('🎤 ' + (typeof i18n !== 'undefined' ? i18n.t('chat_transcribing') : 'Transcribing') + ' ' + a.name + '...');
            try {
              const b64 = a.dataUrl.split(',')[1];
              const audioBytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
              const resp = await fetch('/transcribe', {
                method: 'POST', headers: { 'Content-Type': a.mimeType || 'audio/webm' }, body: audioBytes
              });
              const data = await resp.json();
              if (data.text && data.text.trim()) {
                text = text ? text + '\n[Audio transcription: ' + data.text.trim() + ']' : '[Audio transcription: ' + data.text.trim() + ']';
                this.appendSystem('✅ ' + (typeof i18n !== 'undefined' ? i18n.t('chat_transcription_complete') : 'Transcription complete'));
              } else if (data.error) {
                this.appendSystem('❌ ' + (typeof i18n !== 'undefined' ? i18n.t('chat_transcription_error_label') : 'Transcription error') + ': ' + data.error);
              } else {
                this.appendSystem('⚠️ ' + (typeof i18n !== 'undefined' ? i18n.t('chat_no_speech_detected') : 'No speech detected in audio'));
              }
            } catch (e) {
              this.appendSystem('❌ ' + (typeof i18n !== 'undefined' ? i18n.t('chat_transcription_error_label') : 'Transcription error') + ': ' + e.message);
            }
          } else {
            // Non-image files were already uploaded above and are passed by path note.
          }
        }

        if (uploadedFiles.length) {
          const pathNote = uploadedFiles.map(f => '(attached file: ' + (f.path || f.url) + ')').join('\n');
          text = text ? text + '\n' + pathNote : pathNote;
        }
        attachments = imageAtts.length ? imageAtts : undefined;
      }

      this.pendingAttachments = [];
      this.renderAttachmentPreviews();

      const idempotencyKey = `office-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const params = { sessionKey: this.sessionKey, message: text || '(attached files)', idempotencyKey };
      if (attachments?.length) params.attachments = attachments;

      if (this.isCodexSelected()) {
        const label = this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex';
        const codexSendStartedAt = Date.now();
        let finalStatusText = _ct('codex_ready');
        let finalStatusClass = 'connected';
        const codexBody = {
          agentId: this.getSelectedAgentId() || this.selectedAgentKey,
          message: text || '(attached files)',
          conversationId: this.getCodexConversationId(),
          fromType: 'human',
          fromDisplayName: 'User',
          sourceApp: 'virtual-office',
          sourceSurface: 'chat-window',
          sourceLabel: 'Virtual Office Chat',
          idempotencyKey
        };
        this.codexBusy = true;
        this.codexRequestInFlight = true;
        this.sendBtn.disabled = true;
        this.setStatus(_ct('codex_working'), 'connecting');
        this.updateTypingIndicator(label + ' ' + _ct('working'));
        this.startCodexActivityPolling();
        try {
          const resp = await fetch('/api/codex/runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(codexBody)
          });
          const data = await resp.json();
          if (data.status === 'busy') {
            localUserMessage?.remove?.();
            this.appendCodexActiveConversationNotice(data.activeConversationId || '', data.activeStatus || 'running');
            finalStatusText = _ct('codex_working');
            finalStatusClass = 'connecting';
            this.setStatus(finalStatusText, finalStatusClass);
            return;
          }
          if (!resp.ok || data.ok === false || !data.runId) {
            await this.sendCodexBlockingMessage(codexBody, codexSendStartedAt, label);
            return;
          }
          this.currentRunId = data.runId || null;
          await this.streamCodexRunEvents(data.runId, label);
          this.removeTypingIndicator();
          finalStatusText = _ct('codex_ready');
          finalStatusClass = 'connected';
          this.setStatus(finalStatusText, finalStatusClass);
        } catch (e) {
          this.closeCodexEventSource();
          this.removeTypingIndicator();
          if (e?.cancelledByUi) {
            finalStatusText = '';
            finalStatusClass = '';
          } else if (e?.providerBusy) {
            localUserMessage?.remove?.();
            finalStatusText = _ct('codex_working');
            finalStatusClass = 'connecting';
            this.setStatus(finalStatusText, finalStatusClass);
          } else try {
            await this.sendCodexBlockingMessage(codexBody, codexSendStartedAt, label);
          } catch (fallbackError) {
            await this.loadHistory({ recoverFinal: true, startedAt: codexSendStartedAt }).catch(() => {});
            this.appendSystem(_ct('chat_failed_to_send') + ': ' + fallbackError.message);
            finalStatusText = _ct('codex_error');
            finalStatusClass = 'disconnected';
            this.setStatus(finalStatusText, finalStatusClass);
          }
        } finally {
          this.codexBusy = false;
          this.codexRequestInFlight = false;
          this.sendInFlight = false;
          this.sendBtn.disabled = false;
          this.removeTypingIndicator();
          if (finalStatusText) this.setStatus(finalStatusText, finalStatusClass);
          this.stopCodexActivityPolling();
          this.scrollBottom();
        }
        return;
      }

      if (this.isClaudeCodeSelected()) {
        const providerLabel = this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Claude Code';
        const claudeSendStartedAt = Date.now();
        this.claudeCodeSendStartedAt = claudeSendStartedAt;
        const claudeBody = {
          agentId: this.getSelectedAgentId() || this.selectedAgentKey,
          message: text || '(attached files)',
          conversationId: this.getProviderConversationId('claude-code'),
          fromType: 'human',
          fromDisplayName: 'User',
          sourceApp: 'virtual-office',
          sourceSurface: 'chat-window',
          sourceLabel: 'Virtual Office Chat',
          idempotencyKey,
          attachments: attachments || []
        };
        this.updateTypingIndicator(providerLabel + ' ' + _ct('working'));
        this.setStatus(_ct('claude_code_working'), 'connecting');
        try {
          const resp = await fetch('/api/claude-code/runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(claudeBody)
          });
          const data = await resp.json();
          if (!resp.ok || data.ok === false) {
            if (data.fallback) {
              await this.sendClaudeCodeBlockingMessage(claudeBody, claudeSendStartedAt);
              return;
            }
            throw new Error(data.error || data.reply || resp.statusText);
          }
          this.currentRunId = data.runId || null;
          await this.fetchSessionInfo();
          await this.streamClaudeCodeRunEvents(data.runId);
          this.removeTypingIndicator();
          await this.loadHistory({ recoverFinal: true, startedAt: claudeSendStartedAt });
          await this.fetchSessionInfo();
          this.setStatus(_ct('claude_code_ready'), 'connected');
        } catch (e) {
          this.closeClaudeCodeEventSource();
          this.removeTypingIndicator();
          if (!e?.cancelledByUi) {
            await this.loadHistory({ recoverFinal: true, startedAt: claudeSendStartedAt }).catch(() => {});
            this.appendSystem(_ct('claude_code_send_failed') + ': ' + e.message);
            this.setStatus(_ct('claude_code_error'), 'disconnected');
          }
        } finally {
          this.sendInFlight = false;
        }
        return;
      }

      if (this.isHermesSelected()) {
        const providerLabel = this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Hermes';
        const hermesSendStartedAt = Date.now();
        this.hermesSendStartedAt = hermesSendStartedAt;
        const hermesBody = {
          agentId: this.getSelectedAgentId() || this.selectedAgentKey,
          message: text || '(attached files)',
          conversationId: this.getProviderConversationId('hermes'),
          fromType: 'human',
          fromDisplayName: 'User',
          sourceApp: 'virtual-office',
          sourceSurface: 'chat-window',
          sourceLabel: 'Virtual Office Chat',
          idempotencyKey,
          attachments: attachments || []
        };
        const hermesProgress = this.startHermesProgress(providerLabel);
        try {
          const resp = await fetch('/api/hermes/runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(hermesBody)
          });
          const data = await resp.json();
          if (!resp.ok || data.ok === false) {
            if (data.fallback) {
              await this.sendHermesBlockingMessage(hermesBody, hermesProgress, hermesSendStartedAt);
              return;
            }
            throw new Error(data.error || data.reply || resp.statusText);
          }
          this.currentRunId = data.runId || null;
          await this.streamHermesRunEvents(data.runId, hermesProgress, hermesSendStartedAt);
          this.removeTypingIndicator();
          await this.loadHistory({ recoverFinal: true, startedAt: hermesSendStartedAt });
          await this.pollHermesApproval().catch(() => {});
          this.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_ready') : 'Hermes ready', 'connected');
        } catch (e) {
          this.closeHermesEventSource();
          this.removeTypingIndicator();
          if (!e?.cancelledByUi) {
            this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_hermes_send_failed') : 'Hermes send failed') + ': ' + e.message);
            this.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_error') : 'Hermes error', 'disconnected');
          }
        } finally {
          this.sendInFlight = false;
        }
        return;
      }

      const sendSessionKey = this.sessionKey;
      rpc('chat.send', params).then(res => {
        if (res.ok && res.payload?.runId) {
          this.currentRunId = res.payload.runId;
          this.markLiveEvent();
          this.ensureRecoveryWatchdog();
          runOwners.set(res.payload.runId, { slotId: this.slotId, sessionKey: sendSessionKey });
        }
      }).catch(e => {
        localUserMessage?.remove?.();
        this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_failed_to_send') : 'Failed to send') + ': ' + e.message);
      }).finally(() => {
        this.sendInFlight = false;
      });
    }

    async compactCodexContext() {
      if (!this.isCodexSelected() || this.codexBusy) return;
      const shouldCompact = await showChatConfirmDialog({
        title: _ct('compress_codex_context'),
        message: _ct('compress_context_confirm'),
        confirmLabel: chatConfirmLabel(),
        cancelLabel: _ct('cancel'),
        emoji: '🗜'
      });
      if (!shouldCompact) return;
      this.codexBusy = true;
      this.sendBtn.disabled = true;
      this.compactContextBtn.disabled = true;
      this.setStatus(_ct('compressing_codex_context'), 'connecting');
      try {
        const res = await fetch('/api/codex/compact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agentId: this.getSelectedAgentId() || this.selectedAgentKey,
            conversationId: this.getCodexConversationId()
          })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _ct('compression_failed_detail'));
        this.appendSystem(data.reply || _ct('codex_context_compressed'));
        this.setStatus(_ct('codex_ready'), 'connected');
      } catch (e) {
        this.appendSystem(_ct('codex_compression_failed') + ': ' + e.message);
        this.setStatus(_ct('codex_error'), 'disconnected');
      } finally {
        this.codexBusy = false;
        this.sendBtn.disabled = false;
        this.compactContextBtn.disabled = false;
      }
    }

    async sendStop() {
      try {
        if (this.isClaudeCodeSelected()) {
          const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
          const conversationId = this.getProviderConversationId('claude-code');
          if (this.currentRunId) {
            await fetch('/api/claude-code/runs/' + encodeURIComponent(this.currentRunId) + '/stop', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ agentId, conversationId })
            }).catch(() => {});
          } else {
            await fetch('/api/claude-code/cancel', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ agentId, conversationId })
            }).catch(() => {});
          }
          this.closeClaudeCodeEventSource();
          this.setStatus(_ct('claude_code_working'), 'connecting');
          this.appendSystem(_ct('stop_preserves_changes'));
          return;
        }
        if (this.isCodexSelected()) {
          const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
          const conversationId = this.getCodexConversationId();
          let res;
          if (this.currentRunId) {
            res = await fetch('/api/codex/runs/' + encodeURIComponent(this.currentRunId) + '/stop', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ agentId, conversationId })
            });
          } else {
            res = await fetch('/api/codex/cancel', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ agentId, conversationId })
            });
          }
          const data = await res.json();
          if (!res.ok || !data.ok) throw new Error(data.error || _ct('cancel_failed_detail'));
          this.closeCodexEventSource();
          this.setStatus(_ct('codex_cancelling'), 'connecting');
          this.appendSystem(_ct('stop_preserves_changes'));
          return;
        }
        if (this.streamingMsg) {
          this.finalizeStreamingMessage(this.streamingMsg.content || '');
          this.streamingMsg = null;
        }
        const params = { sessionKey: this.sessionKey };
        if (this.currentRunId) params.runId = this.currentRunId;
        const res = await rpc('chat.abort', params);
        if (res?.ok === false) throw new Error(res.error?.message || 'abort failed');
        this.clearActivityFeed();
        this.currentRunId = null;
        this.appendSystem('🛑 ' + (typeof i18n !== 'undefined' ? i18n.t('chat_stop_sent') : 'Stop sent'));
      } catch (e) {
        this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_failed_to_stop') : 'Failed to stop') + ': ' + e.message);
      }
    }

    async sendClaudeCodeBlockingMessage(body, startedAt) {
      const providerLabel = this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Claude Code';
      const resp = await fetch('/api/claude-code/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      this.removeTypingIndicator();
      if (!resp.ok || data.ok === false) throw new Error(data.error || data.reply || resp.statusText);
      this.appendMessage('assistant', data.reply || '', Date.now(), [], {
        label: providerLabel,
        kind: 'agent',
        thinking: data.thinking || '',
        reasoningTokens: data.reasoningTokens || 0
      }, normalizeHermesTools(data.tools || []));
      await this.loadHistory({ recoverFinal: true, startedAt }).catch(() => {});
      this.setStatus(_ct('claude_code_ready'), 'connected');
    }

    async sendCodexBlockingMessage(body, startedAt, label) {
      const resp = await fetch('/api/codex/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      this.removeTypingIndicator();
      let reply = data.reply || data.error || '';
      if (data.status === 'busy') {
        if (data.activeConversationId) {
          this.appendCodexActiveConversationNotice(data.activeConversationId, data.activeStatus);
        }
        const err = new Error(data.error || data.status || resp.statusText);
        err.providerBusy = true;
        throw err;
      }
      if (Array.isArray(data.modifiedFiles) && data.modifiedFiles.length) {
        reply += '\n\n' + _ct('modified_files') + ':\n' + data.modifiedFiles.map(path => '- ' + path).join('\n');
      }
      if (data.needsHumanIntervention) reply += '\n\n' + _ct('human_intervention_required');
      if (reply) this.appendMessage('assistant', reply, Date.now(), [], { label: label || 'Codex', kind: 'agent' });
      if (data.status !== 'cancelled' && (!resp.ok || data.ok === false)) throw new Error(data.error || data.status || resp.statusText);
      await this.loadHistory({ recoverFinal: true, startedAt }).catch(() => {});
      this.setStatus(_ct('codex_ready'), 'connected');
    }

    streamCodexRunEvents(runId, label) {
      if (!runId) return Promise.reject(new Error('Codex run did not return a run id'));
      this.closeCodexEventSource();
      this.currentRunId = runId;
      this.setStatus('Codex stream active...', 'connecting');
      this.markLiveEvent();
      this.ensureRecoveryWatchdog();
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey || '';
      const url = '/api/codex/runs/' + encodeURIComponent(runId) + '/events?agentId=' + encodeURIComponent(agentId);
      return new Promise((resolve, reject) => {
        let settled = false;
        const source = new EventSource(url);
        this.codexEventSource = source;
        this.codexStreamCancel = (err) => finish(false, err);
        const cleanup = () => {
          if (this.codexEventSource === source) this.codexEventSource = null;
          if (this.codexStreamCancel) this.codexStreamCancel = null;
          source.close();
        };
        const finish = (ok, value) => {
          if (settled) return;
          settled = true;
          cleanup();
          if (ok) resolve(value);
          else reject(value instanceof Error ? value : new Error(String(value || 'Codex stream failed')));
        };
        const handle = (eventName, evt) => {
          let data = {};
          try { data = JSON.parse(evt.data || '{}'); } catch (_) {}
          this.handleCodexNativeEvent(eventName, data, label);
          if (eventName === 'run.completed') finish(true, data);
          if (eventName === 'run.failed' || eventName === 'run.cancelled' || eventName === 'run.canceled') finish(false, data.error || data.status || 'Codex run failed');
        };
        ['run.started','message.delta','reasoning.available','session.metrics','tool.started','tool.completed','tool.failed','approval.request','provider.activity','run.completed','run.failed','run.cancelled','run.canceled'].forEach(name => {
          source.addEventListener(name, evt => handle(name, evt));
        });
        source.onerror = () => {
          if (!settled) finish(false, new Error('Codex event stream disconnected'));
        };
      });
    }

    handleCodexNativeEvent(eventName, data, label) {
      if (!this.isCodexSelected()) return;
      data = data && typeof data === 'object' ? data : {};
      this.markLiveEvent();
      this.applySessionMetrics(data);
      const runId = data.runId || this.currentRunId || 'codex-run';
      const activity = data.activity && typeof data.activity === 'object' ? data.activity : null;
      if (activity) this.codexLastSequence = Math.max(this.codexLastSequence, Number(activity.sequence || 0));

      if (eventName === 'run.started') {
        this.renderCodexRunStatus({
          runId,
          label: label || 'Codex',
          status: 'running',
          text: '已收到消息，正在启动 Codex run',
          ts: Date.now()
        });
        return;
      }
      if (eventName === 'session.metrics') return;
      if (eventName === 'message.delta') {
        const delta = data.delta || data.text || data.reply || '';
        if (!delta) return;
        if (!this.streamingMsg || this.streamingMsg.id !== runId) {
          this.streamingMsg = { id: runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
          this.ensureRecoveryWatchdog();
        }
        this.pendingStreamContent = (this.pendingStreamContent || '') + delta;
        this.scheduleStreamingRender();
        return;
      }
      if (eventName === 'reasoning.available') {
        if (activity) this.renderCodexActivity(activity);
        else {
          const thinking = visibleProviderThinking('codex', data.thinking || data.text, data.status);
          if (thinking) this.renderCodexReasoning({
            type: 'reasoning',
            status: data.status || 'running',
            text: thinking,
            turnId: data.turnId || runId,
            itemId: data.itemId || 'reasoning'
          });
        }
        return;
      }
      if (eventName === 'approval.request') {
        if (activity) this.renderCodexActivity(activity);
        return;
      }
      if (eventName === 'tool.started' || eventName === 'tool.completed' || eventName === 'tool.failed' || eventName === 'provider.activity') {
        if (activity) {
          this.renderCodexActivity(activity, { runId });
          return;
        }
        const tool = data.toolCard || {};
        const payload = {
          runId,
          data: {
            toolCallId: data.toolCallId || tool.id || data.itemId || ('codex-tool-' + this.liveToolCards.size),
            phase: eventName === 'tool.started' ? 'start' : eventName === 'provider.activity' ? 'update' : 'result',
            name: tool.name || data.name || 'Codex activity',
            args: tool.arguments || data.input || {},
            result: tool.result || data.output || data.error || '',
            isError: eventName === 'tool.failed'
          },
          error: eventName === 'tool.failed' ? (tool.error || data.error || 'tool failed') : ''
        };
        if (eventName === 'tool.started') this.appendToolCall(payload);
        else if (eventName === 'provider.activity') this.updateToolCall(payload);
        else this.finishToolCall(payload);
        return;
      }
      if (eventName === 'run.completed' || eventName === 'run.failed' || eventName === 'run.cancelled' || eventName === 'run.canceled') {
        if (activity && activity.type === 'turn') this.renderCodexActivity(activity, { runId, replayCompletedTurns: false });
        const activityOutput = activity?.output && typeof activity.output === 'object' ? activity.output : {};
        const files = Array.isArray(data.modifiedFiles) && data.modifiedFiles.length
          ? data.modifiedFiles
          : (Array.isArray(activityOutput.modifiedFiles) ? activityOutput.modifiedFiles : []);
        let finalText = data.reply || activityOutput.reply || data.error || activity?.error || this.pendingStreamContent || (this.streamingMsg ? this.streamingMsg.content : '');
        if (files.length) finalText += '\n\n' + _ct('modified_files') + ':\n' + files.map(path => '- ' + path).join('\n');
        if (data.needsHumanIntervention) finalText += '\n\n' + _ct('human_intervention_required');
        this.flushStreamingRender(true);
        this.flushToolEvents(true);
        this.clearActivityFeed();
        this.removeTypingIndicator();
        if (this.streamingMsg) {
          this.finalizeStreamingMessage(finalText);
          this.streamingMsg = null;
        } else if (finalText) {
          this.appendMessage('assistant', finalText, Date.now(), [], { label: label || 'Codex', kind: 'agent' });
        }
        if (runId) this.finalizeRunToolCards(runId);
        const finalStatus = eventName === 'run.completed' ? 'completed' : 'failed';
        const finalStatusText = eventName === 'run.completed' ? 'Codex run 已完成' : (data.error || 'Codex run 未完成');
        const settledCards = this.settleCodexRunningStatusCards(finalStatus, finalStatusText);
        if (!settledCards) {
          this.renderCodexRunStatus({
            runId,
            label: label || 'Codex',
            status: finalStatus,
            text: finalStatusText,
            ts: Date.now()
          });
        }
        this.settleCodexReasoningCards(eventName === 'run.completed' ? 'done' : 'error');
        this.currentRunId = null;
        this.codexBusy = false;
        this.codexRequestInFlight = false;
        this.sendBtn.disabled = false;
        this.setStatus(eventName === 'run.completed' ? _ct('codex_ready') : _ct('codex_error'), eventName === 'run.completed' ? 'connected' : 'disconnected');
        this.stopRecoveryWatchdog();
        this.fetchSessionInfo().catch(() => {});
      }
    }

    streamClaudeCodeRunEvents(runId) {
      if (!runId) return Promise.reject(new Error('Claude Code run did not return a run id'));
      this.closeClaudeCodeEventSource();
      this.claudeCodeCompletedToolKeys = new Set();
      this.currentRunId = runId;
      this.setStatus(_ct('claude_code_stream_active'), 'connecting');
      this.markLiveEvent();
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey || '';
      const url = '/api/claude-code/runs/' + encodeURIComponent(runId) + '/events?agentId=' + encodeURIComponent(agentId);
      return new Promise((resolve, reject) => {
        let settled = false;
        const source = new EventSource(url);
        this.claudeCodeEventSource = source;
        this.claudeCodeStreamCancel = (err) => finish(false, err);
        const cleanup = () => {
          if (this.claudeCodeEventSource === source) this.claudeCodeEventSource = null;
          if (this.claudeCodeStreamCancel) this.claudeCodeStreamCancel = null;
          source.close();
        };
        const finish = (ok, value) => {
          if (settled) return;
          settled = true;
          cleanup();
          if (ok) resolve(value);
          else reject(value instanceof Error ? value : new Error(String(value || _ct('claude_code_stream_failed'))));
        };
        const handle = (eventName, evt) => {
          let data = {};
          try { data = JSON.parse(evt.data || '{}'); } catch (_) {}
          this.handleClaudeCodeNativeEvent(eventName, data);
          if (eventName === 'run.completed') finish(true, data);
          if (eventName === 'run.failed' || eventName === 'run.cancelled' || eventName === 'run.canceled') finish(false, data.error || _ct('claude_code_run_failed'));
        };
        ['run.started','message.delta','reasoning.available','session.metrics','tool.started','tool.completed','tool.failed','run.completed','run.failed','run.cancelled','run.canceled'].forEach(name => {
          source.addEventListener(name, evt => handle(name, evt));
        });
        source.onerror = () => {
          if (!settled) finish(false, new Error(_ct('claude_code_stream_disconnected')));
        };
      });
    }

    handleClaudeCodeNativeEvent(eventName, data) {
      data = data && typeof data === 'object' ? data : {};
      this.markLiveEvent();
      this.applySessionMetrics(data);
      const runId = data.runId || this.currentRunId || 'claude-code-run';
      if (eventName === 'run.started') {
        this.appendActivity('Claude Code: ' + _ct('chat_hermes_queued'));
        return;
      }
      if (eventName === 'session.metrics') return;
      if (eventName === 'message.delta') {
        if (!this.streamingMsg || this.streamingMsg.id !== runId) {
          this.streamingMsg = { id: runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
          this.ensureRecoveryWatchdog();
        }
        const next = data.reply || ((this.pendingStreamContent || '') + (data.delta || ''));
        if (next) {
          this.pendingStreamContent = next;
          this.scheduleStreamingRender();
        }
        return;
      }
      if (eventName === 'reasoning.available') {
        const thinking = visibleProviderThinking('claude-code', data.thinking, data.status);
        if (thinking) this.appendActivity('Claude Code: ' + thinking);
        return;
      }
      if (eventName === 'tool.started' || eventName === 'tool.completed' || eventName === 'tool.failed') {
        const tool = data.toolCard || {};
        const payload = {
          runId,
          data: {
            toolCallId: data.toolCallId || tool.id || ('claude-tool-' + this.liveToolCards.size),
            phase: eventName === 'tool.started' ? 'start' : 'result',
            name: tool.name || 'Claude tool',
            args: tool.arguments || {},
            result: tool.result || tool.error || '',
            isError: eventName === 'tool.failed'
          },
          error: eventName === 'tool.failed' ? (tool.error || data.error || 'tool failed') : ''
        };
        if (eventName === 'tool.started') this.appendToolCall(payload);
        else this.finishToolCall(payload);
        return;
      }
      if (eventName === 'run.completed' || eventName === 'run.failed' || eventName === 'run.cancelled' || eventName === 'run.canceled') {
        const finalText = data.reply || this.pendingStreamContent || (this.streamingMsg ? this.streamingMsg.content : '');
        this.flushStreamingRender(true);
        this.flushToolEvents(true);
        this.clearActivityFeed();
        this.removeTypingIndicator();
        if (this.streamingMsg) {
          this.finalizeStreamingMessage(finalText);
          this.streamingMsg = null;
        } else if (finalText) {
          this.appendMessage('assistant', finalText);
        }
        if (runId) this.finalizeRunToolCards(runId);
        this.currentRunId = null;
        this.stopRecoveryWatchdog();
        this.fetchSessionInfo().catch(() => {});
      }
    }

    startCodexActivityPolling() {
      if (!this.isCodexSelected() || this.codexActivityTimer) return;
      this.pollCodexActivity().catch(() => {});
      this.codexActivityTimer = setInterval(() => this.pollCodexActivity().catch(() => {}), 500);
    }

    stopCodexActivityPolling() {
      if (this.codexActivityTimer) clearInterval(this.codexActivityTimer);
      this.codexActivityTimer = null;
    }

    async pollCodexActivity(includeHistory = false, options = {}) {
      if (!this.isCodexSelected()) return;
      const replayCompletedTurns = options.replayCompletedTurns !== false;
      const replayHistoricalTurns = options.replayHistoricalTurns !== false;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const conversationId = this.getCodexConversationId();
      const after = includeHistory ? 0 : this.codexLastSequence;
      const res = await fetch('/api/codex/activity?agentId=' + encodeURIComponent(agentId) + '&conversationId=' + encodeURIComponent(conversationId) + '&after=' + after);
      const data = await res.json();
      if (!res.ok || !data.ok) return;
      for (const event of data.events || []) {
        this.codexLastSequence = Math.max(this.codexLastSequence, Number(event.sequence || 0));
        if (includeHistory && !replayHistoricalTurns && event.type === 'turn') continue;
        this.renderCodexActivity(event, { replayCompletedTurns });
      }
      if (data.active) {
        this.codexBusy = true;
        this.sendBtn.disabled = true;
        const waiting = data.active.pending ? _ct('codex_waiting') : _ct('codex_working');
        this.setStatus(waiting, 'connecting');
        this.startCodexActivityPolling();
      } else if (this.codexRequestInFlight) {
        this.codexBusy = true;
        this.sendBtn.disabled = true;
        this.setStatus(_ct('codex_working'), 'connecting');
        this.startCodexActivityPolling();
      } else {
        const wasBusy = this.codexBusy;
        this.codexBusy = false;
        this.sendBtn.disabled = false;
        if (wasBusy) {
          this.removeTypingIndicator();
          this.setStatus(_ct('codex_ready'), 'connected');
        }
        this.stopCodexActivityPolling();
      }
    }

    renderCodexActivity(event, options = {}) {
      const replayCompletedTurns = options.replayCompletedTurns !== false;
      const preferredRunId = options.runId || this.currentRunId || '';
      if (event.type === 'reasoning') {
        this.renderCodexReasoning(event);
      } else if (event.type === 'activity') {
        const payload = {
          itemId: event.itemId || event.id,
          runId: event.turnId || event.threadId,
          status: event.status === 'done' ? 'done' : event.status === 'error' ? 'error' : 'running',
          name: event.name || 'Codex tool',
          input: event.input || {},
          output: event.output || '',
          error: event.error || ''
        };
        if (payload.status === 'running') this.updateToolCall(payload);
        else {
          this.updateToolCall(payload);
          this.finishToolCall(payload);
        }
      } else if (event.type === 'interaction' && event.status === 'pending') {
        this.renderCodexInteraction(event);
      } else if (event.type === 'interaction' && event.status === 'resolved') {
        const card = this.codexInteractionCards.get(this.codexInteractionKey(event));
        if (card) {
          card.classList.add('resolved');
          card.querySelectorAll('button').forEach(btn => { btn.disabled = true; });
          const status = card.querySelector('.chat-codex-interaction-status');
        if (status) status.textContent = event.output?.action || _ct('resolved');
        }
      } else if (event.type === 'interaction' && event.status === 'unavailable') {
        this.appendSystem(event.error || _ct('codex_interaction_unavailable'));
      } else if (event.type === 'turn' && event.status === 'cancelling') {
        this.setStatus(_ct('codex_cancelling'), 'connecting');
        this.renderCodexRunStatus({
          runId: preferredRunId || event.operationId || event.turnId || event.threadId,
          label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex',
          status: 'running',
          text: 'Codex run 正在取消',
          ts: event.ts || Date.now()
        });
      } else if (event.type === 'turn' && event.status === 'running') {
        this.renderCodexRunStatus({
          runId: preferredRunId || event.operationId || event.turnId || event.threadId,
          label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex',
          status: 'running',
          text: 'Codex run 正在执行',
          ts: event.ts || Date.now()
        });
      } else if (event.type === 'turn' && ['completed', 'failed', 'cancelled', 'execution_failed'].includes(event.status)) {
        if (replayCompletedTurns) {
          this.renderCodexRunStatus({
            runId: preferredRunId || event.operationId || event.turnId || event.threadId,
            label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex',
            status: event.status === 'completed' ? 'completed' : 'failed',
            text: event.status === 'completed' ? 'Codex run 已完成' : (event.error || 'Codex run 未完成'),
            ts: event.ts || Date.now()
          });
        }
        const reply = event.output?.reply || event.error || '';
        if (!this.codexRequestInFlight && reply && !this.messages.innerText.includes(reply)) {
          let text = reply;
          const files = event.output?.modifiedFiles || [];
          if (files.length) text += '\n\n' + _ct('modified_files') + ':\n' + files.map(path => '- ' + path).join('\n');
          this.appendMessage('assistant', text, event.ts || Date.now(), [], {
            label: this.agentSelect.selectedOptions[0]?.textContent.trim() || 'Codex',
            kind: 'agent'
          });
        }
      }
    }

    renderCodexRunStatus({ runId, label, status, text, ts }) {
      const key = runId || 'codex-run-status';
      let card = this.codexRunStatusCards.get(key);
      if (!card) {
        const wrap = document.createElement('div');
        wrap.className = 'chat-msg assistant chat-codex-run-status';
        wrap.dataset.codexRunStatusKey = key;
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble codex-run-status-card';
        const title = document.createElement('strong');
        title.className = 'codex-run-status-title';
        const body = document.createElement('div');
        body.className = 'codex-run-status-body';
        const time = document.createElement('span');
        time.className = 'chat-time';
        bubble.append(title, body, time);
        wrap.appendChild(bubble);
        const indicator = this.messages.querySelector('.typing-indicator');
        if (indicator) this.messages.insertBefore(wrap, indicator);
        else this.messages.appendChild(wrap);
        card = { wrap, title, body, time };
        this.codexRunStatusCards.set(key, card);
      }
      card.wrap.dataset.status = status || 'running';
      card.title.textContent = (label || 'Codex') + ' · ' + (status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : 'running');
      card.body.textContent = text || '';
      card.time.textContent = new Date(ts || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      this.scrollBottom();
    }

    settleCodexRunningStatusCards(status, text) {
      let settled = 0;
      for (const card of this.codexRunStatusCards.values()) {
        if (!card?.wrap || card.wrap.dataset.status !== 'running') continue;
        card.wrap.dataset.status = status || 'completed';
        card.title.textContent = card.title.textContent.replace(/ · .+$/, ' · ' + (status || 'completed'));
        card.body.textContent = text || card.body.textContent || '';
        card.time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        settled += 1;
      }
      return settled;
    }

    settleCodexReasoningCards(status = 'done') {
      for (const state of this.codexReasoningCards.values()) {
        if (!state?.wrap) continue;
        const card = state.wrap.querySelector('.chat-thinking-card');
        updateThinkingCard(card, state.text || '', status);
      }
    }

    renderCodexReasoning(event) {
      const visibleText = visibleProviderThinking('codex', event?.text || event?.output || '', event?.status);
      if (!visibleText) return;
      event = { ...event, text: visibleText, output: '' };
      const key = `${event.operationId || event.turnId || event.threadId || 'turn'}:${event.itemId || 'reasoning'}`;
      let state = this.codexReasoningCards.get(key);
      if (!state) {
        state = { ...CodexReasoning.createState(), wrap: null };
        this.codexReasoningCards.set(key, state);
      }
      CodexReasoning.applyEvent(state, event);

      if (!state.text.trim()) return;
      if (!state.wrap) {
        const wrap = document.createElement('div');
        wrap.className = 'chat-msg assistant chat-reasoning-msg';
        wrap.dataset.reasoningKey = key;
        wrap.appendChild(renderThinkingCard(state.text, { codex: true, status: event.status }));
        const indicator = this.messages.querySelector('.typing-indicator');
        if (indicator) this.messages.insertBefore(wrap, indicator);
        else this.messages.appendChild(wrap);
        state.wrap = wrap;
      } else {
        updateThinkingCard(state.wrap.querySelector('.chat-thinking-card'), state.text, event.status);
      }
      this.scrollBottom();
    }

    renderCodexInteraction(event) {
      const interactionKey = this.codexInteractionKey(event);
      if (this.codexInteractionCards.has(interactionKey)) return;
      const wrap = document.createElement('div');
      wrap.className = 'chat-msg assistant chat-codex-interaction';
      wrap.dataset.interactionId = event.interactionId;
      const card = document.createElement('div');
      card.className = 'chat-bubble codex-interaction-card';
      const title = document.createElement('strong');
      title.textContent = event.interactionType === 'input' ? _ct('codex_needs_information') : _ct('codex_requests_approval');
      const detail = document.createElement('pre');
      detail.textContent = formatToolPayload(event.input || {});
      const actions = document.createElement('div');
      actions.className = 'chat-codex-interaction-actions';
      if (event.interactionType === 'input') {
        actions.appendChild(this.makeCodexInteractionButton(_ct('answer'), 'answer', event));
      } else {
        actions.appendChild(this.makeCodexInteractionButton(_ct('chat_allow_once'), 'accept', event));
        actions.appendChild(this.makeCodexInteractionButton(_ct('allow_codex_session'), 'acceptForSession', event));
        actions.appendChild(this.makeCodexInteractionButton(_ct('reject'), 'decline', event));
      }
      const note = document.createElement('div');
      note.className = 'chat-codex-interaction-note';
      note.textContent = event.interactionType === 'approval' ? _ct('codex_session_scope_hint') : '';
      const status = document.createElement('span');
      status.className = 'chat-codex-interaction-status';
      status.textContent = _ct('pending');
      card.append(title, detail, actions, note, status);
      wrap.appendChild(card);
      this.messages.appendChild(wrap);
      this.codexInteractionCards.set(interactionKey, card);
      this.scrollBottom();
    }

    codexInteractionKey(event) {
      return `${event.operationId || event.turnId || event.threadId || 'turn'}:${event.interactionId || event.id}`;
    }

    makeCodexInteractionButton(label, action, event) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.dataset.action = action;
      button.addEventListener('click', async () => {
        let answers = {};
        if (action === 'answer') {
          const value = prompt(_ct('answer_codex'));
          if (value === null) return;
          const questions = event.input?.questions || [];
          if (questions.length) {
            for (const question of questions) answers[question.id || question.name || 'answer'] = value;
          } else answers.answer = value;
        }
        const card = button.closest('.codex-interaction-card');
        card?.querySelectorAll('button').forEach(btn => { btn.disabled = true; });
        try {
          const res = await fetch('/api/codex/interaction', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              agentId: this.getSelectedAgentId() || this.selectedAgentKey,
              conversationId: this.getCodexConversationId(),
              interactionId: event.interactionId,
              action,
              answers
            })
          });
          const data = await res.json();
          if (!res.ok || !data.ok) throw new Error(data.error || data.status || _ct('interaction_failed_detail'));
          const status = card?.querySelector('.chat-codex-interaction-status');
          if (status) status.textContent = _ct('submitted');
        } catch (error) {
          card?.querySelectorAll('button').forEach(btn => { btn.disabled = false; });
          this.appendSystem(_ct('codex_interaction_failed') + ': ' + error.message);
        }
      });
      return button;
    }

    appendCodexActiveConversationNotice(conversationId, status) {
      const wrap = document.createElement('div');
      wrap.className = 'chat-msg system';
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble system-bubble';
      const activeLabel = conversationId ? ` · ${conversationId}` : '';
      bubble.append(document.createTextNode(_ct('codex_busy_other_conversation', { status: status || _ct('busy') }) + activeLabel + ' '));
      if (conversationId) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chat-inline-action';
        button.textContent = _ct('open_active_conversation');
        button.addEventListener('click', () => {
          localStorage.setItem(this.codexConversationStorageKey(), conversationId);
          this.resetConversation(_ct('opened_active_codex_conversation'));
          this.loadHistory();
        });
        bubble.appendChild(button);
      }
      const stopButton = document.createElement('button');
      stopButton.type = 'button';
      stopButton.className = 'chat-inline-action';
      stopButton.textContent = _ct('stop');
      stopButton.addEventListener('click', async () => {
        stopButton.disabled = true;
        try {
          const res = await fetch('/api/codex/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              agentId: this.getSelectedAgentId() || this.selectedAgentKey,
              conversationId: conversationId || this.getCodexConversationId()
            })
          });
          const data = await res.json();
          if (!res.ok || data.ok === false) throw new Error(data.error || data.status || 'cancel failed');
          this.appendSystem(_ct('stop_preserves_changes'));
          this.setStatus(_ct('codex_cancelling'), 'connecting');
        } catch (error) {
          stopButton.disabled = false;
          this.appendSystem(_ct('cancel_failed_detail') + ': ' + error.message);
        }
      });
      bubble.appendChild(stopButton);
      wrap.appendChild(bubble);
      this.messages.appendChild(wrap);
      this.scrollBottom();
    }

    async toggleRecording() {
      if (this.isRecording) return this.stopRecording();
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        this.audioChunks = [];
        this.mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) this.audioChunks.push(e.data); };
        this.mediaRecorder.onstop = async () => {
          stream.getTracks().forEach(t => t.stop());
          const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
          await this.transcribeAudio(blob);
        };
        this.mediaRecorder.start();
        this.isRecording = true;
        this.micBtn.classList.add('recording');
        this.micBtn.innerHTML = '■';
      } catch (e) {
        this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_microphone_access_denied') : 'Microphone access denied');
      }
    }

    stopRecording() {
      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') this.mediaRecorder.stop();
      this.isRecording = false;
      this.micBtn.classList.remove('recording');
      this.micBtn.innerHTML = '🎙️';
    }

    async transcribeAudio(blob) {
      this.micBtn.innerHTML = '···';
      this.micBtn.disabled = true;
      try {
        const resp = await fetch('/transcribe', { method: 'POST', headers: { 'Content-Type': 'audio/webm' }, body: blob });
        const data = await resp.json();
        if (data.text) {
          this.input.value = (this.input.value ? this.input.value + ' ' : '') + data.text;
          this.autoResizeInput();
          this.input.focus();
        } else if (data.error) {
          this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_transcription_error_label') : 'Transcription error') + ': ' + data.error);
        }
      } catch (e) {
        this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_transcription_error_label') : 'Transcription error') + ': ' + e.message);
      }
      this.micBtn.innerHTML = '🎙️';
      this.micBtn.disabled = false;
    }

    ownsPayload(payload) {
      if (!payload) return false;
      if (payload.sessionKey) return payload.sessionKey === this.sessionKey;
      if (payload.runId && this.currentRunId && payload.runId === this.currentRunId) return true;
      const owner = payload.runId ? runOwners.get(payload.runId) : null;
      if (owner) return owner.slotId === this.slotId && owner.sessionKey === this.sessionKey;
      return false;
    }

    handleChatEvent(payload) {
      if (!this.ownsPayload(payload)) return;
      this.markLiveEvent();
      const text = extractText(payload);
      if (payload?.state === 'delta' || payload?.state === 'streaming') {
        if (!this.streamingMsg || this.streamingMsg.id !== payload.runId) {
          this.streamingMsg = { id: payload.runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
          this.ensureRecoveryWatchdog();
        }
        if (text) {
          this.pendingStreamContent = text;
          this.scheduleStreamingRender();
        }
      } else if (payload?.state === 'final' || payload?.state === 'done') {
        const finalText = text || this.pendingStreamContent || (this.streamingMsg ? this.streamingMsg.content : '');
        this.flushStreamingRender(true);
        this.flushToolEvents(true);
        this.clearActivityFeed();
        if (this.streamingMsg) {
          this.finalizeStreamingMessage(finalText);
          this.streamingMsg = null;
        } else if (finalText) {
          this.appendMessage('assistant', finalText);
        }
        this.fetchContextUsage();
        if (payload?.runId) this.finalizeRunToolCards(payload.runId);
        if (payload?.runId) runOwners.delete(payload.runId);
        this.currentRunId = null;
        this.stopRecoveryWatchdog();
        this.scrollBottom();
      }
    }

    handleAgentEvent(payload) {
      if (!this.ownsPayload(payload)) return;

      const data = payload?.data && typeof payload.data === 'object' ? payload.data : {};
      const stream = payload?.stream || data.stream || '';
      const phase = data.phase || payload?.phase || '';
      const isToolLikeItem = stream === 'item' && data.kind === 'command';

      // Current OpenClaw emits tool activity as agent events:
      // { stream:"tool", data:{ phase:"start|update|result", name, toolCallId, args, result } }
      if (stream === 'tool' || isToolLikeItem || payload?.type === 'tool_start' || payload?.type === 'tool_end' || payload?.type === 'tool_result') {
        this.markLiveEvent();
        const tool = normalizeToolEvent(payload, phase === 'result' ? 'done' : 'running');
        const label = formatToolLabel(tool.name, coerceToolArgs(tool.arguments));
        this.updateTypingIndicator((phase === 'result' || phase === 'end' || payload?.type === 'tool_end' || payload?.type === 'tool_result') ? (typeof i18n !== 'undefined' ? i18n.t('chat_processing') : 'Processing...') : label);
        this.queueToolEvent(payload);
        this.ensureRecoveryWatchdog();
        return;
      }

      if (payload?.type === 'thinking' || stream === 'lifecycle' && phase === 'start') {
        this.updateTypingIndicator(typeof i18n !== 'undefined' ? i18n.t('chat_thinking') + '...' : 'Thinking...');
      }
    }

    markLiveEvent() {
      this.lastLiveEventAt = Date.now();
    }

    scheduleStreamingRender() {
      if (this.streamRenderTimer) return;
      this.streamRenderTimer = setTimeout(() => this.flushStreamingRender(), STREAM_RENDER_INTERVAL_MS);
    }

    flushStreamingRender(force = false) {
      if (this.streamRenderTimer) { clearTimeout(this.streamRenderTimer); this.streamRenderTimer = null; }
      if (!this.streamingMsg) return;
      if (!force && this.pendingStreamContent === this.streamingMsg.content) return;
      this.streamingMsg.content = this.pendingStreamContent || this.streamingMsg.content || '';
      this.updateStreamingMessage(this.streamingMsg.content);
      this.scrollBottom(true);
    }

    queueToolEvent(payload) {
      const key = this.toolKey(payload);
      const data = payload?.data && typeof payload.data === 'object' ? payload.data : {};
      const phase = data.phase || payload?.phase || '';
      const isTerminal = phase === 'result' || phase === 'end' || payload?.type === 'tool_end' || payload?.type === 'tool_result';

      // Fast tools can emit start + result inside the render debounce window.
      // If the result replaces the unrendered start, no live card is created and
      // the user only sees the tool after a history refresh.
      if (isTerminal && this.pendingToolEvents.has(key) && !this.liveToolCards.has(key)) {
        const startPayload = this.pendingToolEvents.get(key);
        this.pendingToolEvents.delete(key);
        this.appendToolCall(startPayload);
        this.finishToolCall(payload);
        if (!this.toolFlushTimer && this.pendingToolEvents.size) this.toolFlushTimer = setTimeout(() => this.flushToolEvents(), TOOL_RENDER_INTERVAL_MS);
        return;
      }

      this.pendingToolEvents.set(key, payload);
      if (!this.toolFlushTimer) this.toolFlushTimer = setTimeout(() => this.flushToolEvents(), TOOL_RENDER_INTERVAL_MS);
    }

    flushToolEvents(force = false) {
      if (this.toolFlushTimer) { clearTimeout(this.toolFlushTimer); this.toolFlushTimer = null; }
      if (!this.pendingToolEvents.size) return;
      const events = [...this.pendingToolEvents.values()];
      this.pendingToolEvents.clear();
      for (const payload of events) {
        const data = payload?.data && typeof payload.data === 'object' ? payload.data : {};
        const phase = data.phase || payload?.phase || '';
        if (phase === 'result' || phase === 'end' || payload?.type === 'tool_end' || payload?.type === 'tool_result') this.finishToolCall(payload);
        else if (phase === 'update') this.updateToolCall(payload);
        else this.appendToolCall(payload);
      }
      this.pruneToolCards();
      this.scrollBottom();
    }

    pruneToolCards() {
      const cards = [...this.messages.querySelectorAll('.chat-tool-msg')];
      const extra = cards.length - MAX_LIVE_TOOL_CARDS;
      if (extra <= 0) return;
      for (const el of cards.slice(0, extra)) {
        const key = el.dataset.toolKey;
        if (key) this.liveToolCards.delete(key);
        el.remove();
      }
      let notice = this.messages.querySelector('.chat-tool-pruned-notice');
      if (!notice) {
        notice = document.createElement('div');
        notice.className = 'chat-msg system chat-tool-pruned-notice';
        notice.innerHTML = '<div class="chat-bubble system-bubble">' + (typeof i18n !== 'undefined' ? i18n.t('chat_earlier_tools_collapsed') : 'Earlier live tool activity was collapsed to keep the chat responsive.') + '</div>';
        this.messages.prepend(notice);
      }
    }

    ensureRecoveryWatchdog() {
      if (this.recoveryTimer) return;
      this.lastLiveEventAt = this.lastLiveEventAt || Date.now();
      this.recoveryTimer = setInterval(() => {
        if (!this.currentRunId && !this.streamingMsg && !this.liveToolCards.size && !this.messages.querySelector('.typing-indicator')) return this.stopRecoveryWatchdog();
        if (!connected) return;
        if (Date.now() - this.lastLiveEventAt > ACTIVE_RUN_RECOVERY_MS) {
          this.lastLiveEventAt = Date.now();
          const providerKind = this.isClaudeCodeSelected() ? 'claude-code' : (this.isHermesSelected() ? 'hermes' : '');
          const startedAt = providerKind === 'claude-code' ? this.claudeCodeSendStartedAt : (providerKind === 'hermes' ? this.hermesSendStartedAt : 0);
          this.loadHistory({ recoverFinal: true, startedAt }).catch(() => {});
        }
      }, ACTIVE_RUN_RECOVERY_MS);
    }

    stopRecoveryWatchdog() {
      if (this.recoveryTimer) { clearInterval(this.recoveryTimer); this.recoveryTimer = null; }
    }

    handleSessionMessageEvent(payload) {
      if (!this.ownsPayload(payload)) return;
      const msg = payload?.message && typeof payload.message === 'object' ? payload.message : payload;
      const role = msg?.role || payload?.role || '';
      if (role === 'assistant') {
        this.markLiveEvent();
        const providerKind = this.isClaudeCodeSelected() ? 'claude-code' : (this.isHermesSelected() ? 'hermes' : '');
        const startedAt = providerKind === 'claude-code' ? this.claudeCodeSendStartedAt : (providerKind === 'hermes' ? this.hermesSendStartedAt : 0);
        this.loadHistory({ recoverFinal: true, startedAt });
      } else if (role === 'user') {
        this.markLiveEvent();
      }
    }

    appendMessage(role, content, ts, mediaItems, meta = {}, toolItems = []) {
      const div = document.createElement('div');
      div.className = `chat-msg ${role}`;
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble';
      let displayContent = content || '';
      const envelope = parseA2AEnvelope(displayContent);
      if (envelope) {
        displayContent = envelope.text;
        meta = { ...meta, label: envelope.label, toLabel: envelope.toLabel || meta.toLabel, kind: 'agent' };
      }
      if (role === 'assistant' && meta.thinking && String(meta.thinking).trim() === String(displayContent || '').trim()) {
        meta = { ...meta, thinking: '', reasoningTokens: 0 };
      }
      meta = normalizeSenderMeta(meta, role, this);
      if (meta.kind) div.dataset.senderKind = meta.kind;
      if (role === 'tool' && displayContent.length > 3000) {
        displayContent = displayContent.substring(0, 2000) + '\n\n... [truncated - ' + displayContent.length + ' chars total] ...';
      }
      const extractedMedia = extractMedia({ content: displayContent }, displayContent);
      const media = normalizeChatMedia([...(mediaItems || []), ...extractedMedia]);
      displayContent = displayContent.split(/\r?\n/).filter(line => {
        const t = line.trim();
        return !(t.match(/^\(attached file:\s*(.+?)\)$/i) || t.match(/^attached file:\s*(.+)$/i) || t.match(/^MEDIA:/i));
      }).join('\n').trim();
      if (media.length) {
        bubble.appendChild(renderChatMedia(media));
      }
      const agentResultSummary = displayContent.trim() ? summarizeAgentToolResult(displayContent) : null;
      const senderHeader = agentResultSummary ? null : renderSenderHeader(meta, role);
      if (senderHeader) bubble.appendChild(senderHeader);
      if (role === 'assistant' && (meta.thinking || meta.reasoningTokens)) {
        bubble.appendChild(renderThinkingCard(meta.thinking || `Reasoning trace stored by Hermes provider. Reasoning tokens: ${meta.reasoningTokens}`));
      }
      if (role === 'assistant' && meta.approval) {
        bubble.appendChild(renderHermesApprovalCard(meta.approval, this));
      }
      if (displayContent.trim()) {
        if (agentResultSummary && (role === 'toolResult' || role === 'tool' || meta.kind === 'human')) {
          bubble.appendChild(renderAgentToolResultSummary(agentResultSummary));
        } else {
          const textDiv = document.createElement('div');
          textDiv.innerHTML = formatContent(displayContent);
          bubble.appendChild(textDiv);
        }
      }
      for (const tool of toolItems) bubble.appendChild(renderToolCallCard(tool, { historical: true }));
      if (ts) {
        const time = document.createElement('span');
        time.className = 'chat-time';
        time.textContent = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        bubble.appendChild(time);
      }
      div.appendChild(bubble);
      this.removeTypingIndicator();
      this.messages.appendChild(div);
      return div;
    }

    appendStreamingMessage() {
      const shouldStick = this.isNearBottom();
      this.removeTypingIndicator();
      const existing = this.messages.querySelector('.streaming-msg');
      if (existing) existing.classList.remove('streaming-msg');
      const div = document.createElement('div');
      div.className = 'chat-msg assistant streaming-msg';
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble streaming';
      bubble.innerHTML = '<span class="cursor">▊</span>';
      div.appendChild(bubble);
      this.messages.appendChild(div);
      this.scrollBottom(shouldStick);
    }

    updateStreamingMessage(content) {
      const div = this.messages.querySelector('.streaming-msg');
      if (!div) return;
      const bubble = div.querySelector('.chat-bubble');
      bubble.innerHTML = formatContent(content) + '<span class="cursor">▊</span>';
    }

    finalizeStreamingMessage(content, mediaItems) {
      const div = this.messages.querySelector('.streaming-msg');
      if (!div) return this.appendMessage('assistant', content, Date.now(), mediaItems);
      const bubble = div.querySelector('.chat-bubble');
      bubble.classList.remove('streaming');
      bubble.innerHTML = '';
      const senderHeader = renderSenderHeader(normalizeSenderMeta({}, 'assistant', this), 'assistant');
      if (senderHeader) bubble.appendChild(senderHeader);
      const media = normalizeChatMedia(mediaItems || extractMedia({ content }, content));
      if (media.length) bubble.appendChild(renderChatMedia(media));
      if ((content || '').trim()) {
        const textDiv = document.createElement('div');
        textDiv.innerHTML = formatContent(content || '');
        bubble.appendChild(textDiv);
      }
      const time = document.createElement('span');
      time.className = 'chat-time';
      time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      bubble.appendChild(time);
      div.classList.remove('streaming-msg');
    }

    appendSystem(text) {
      const div = document.createElement('div');
      div.className = 'chat-msg system';
      div.innerHTML = `<div class="chat-bubble system-bubble">${escHtml(text)}</div>`;
      this.messages.appendChild(div);
      this.scrollBottom();
    }

    updateTypingIndicator(text) {
      let ind = this.messages.querySelector('.typing-indicator');
      if (!ind) {
        ind = document.createElement('div');
        ind.className = 'chat-msg assistant typing-indicator';
        ind.innerHTML = `<div class="chat-bubble typing"><span class="typing-text">${escHtml(text)}</span><span class="typing-dots"><span>.</span><span>.</span><span>.</span></span></div>`;
        this.messages.appendChild(ind);
      } else {
        ind.querySelector('.typing-text').textContent = text;
      }
      this.scrollBottom();
    }

    removeTypingIndicator() {
      const ind = this.messages.querySelector('.typing-indicator');
      if (ind) ind.remove();
    }

    clearActivityFeed() { this.messages.querySelectorAll('.chat-activity').forEach(el => el.remove()); }

    makeStreamCancelledError(providerKind) {
      const err = new Error(providerKind + ' stream cancelled');
      err.cancelledByUi = true;
      return err;
    }

    closeHermesEventSource() {
      const cancel = this.hermesStreamCancel;
      this.hermesStreamCancel = null;
      if (this.hermesEventSource) {
        try { this.hermesEventSource.close(); } catch (_) {}
        this.hermesEventSource = null;
      }
      if (cancel) cancel(this.makeStreamCancelledError('Hermes'));
    }

    closeCodexEventSource() {
      const cancel = this.codexStreamCancel;
      this.codexStreamCancel = null;
      if (this.codexEventSource) {
        try { this.codexEventSource.close(); } catch (_) {}
        this.codexEventSource = null;
      }
      if (cancel) cancel(this.makeStreamCancelledError('Codex'));
    }

    closeClaudeCodeEventSource() {
      const cancel = this.claudeCodeStreamCancel;
      this.claudeCodeStreamCancel = null;
      if (this.claudeCodeEventSource) {
        try { this.claudeCodeEventSource.close(); } catch (_) {}
        this.claudeCodeEventSource = null;
      }
      if (cancel) cancel(this.makeStreamCancelledError('Claude Code'));
    }

    closeFeishuEventSource() {
      if (this.feishuHistoryRefreshTimer) {
        clearTimeout(this.feishuHistoryRefreshTimer);
        this.feishuHistoryRefreshTimer = null;
      }
      if (this.feishuEventSource) {
        try { this.feishuEventSource.close(); } catch (_) {}
        this.feishuEventSource = null;
      }
      this.setFeishuLiveStatus('hidden');
    }

    scheduleFeishuHistoryRefresh() {
      if (this.feishuHistoryRefreshTimer) return;
      this.feishuHistoryRefreshTimer = setTimeout(() => {
        this.feishuHistoryRefreshTimer = null;
        if (!this.root.classList.contains('open')) return;
        this.loadHistory({ showError: false }).catch(() => {});
      }, 120);
    }

    async updateFeishuEventSource() {
      if (!this.root.classList.contains('open')) {
        this.closeFeishuEventSource();
        return;
      }
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey || '';
      if (!agentId) {
        this.closeFeishuEventSource();
        return;
      }
      try {
        const res = await fetch('/api/feishu-chat/config');
        const cfg = await res.json();
        const representativeAgentId = String(cfg.representativeAgentId || '').trim();
        const shouldSubscribe = !!(cfg.enabled && representativeAgentId && representativeAgentId === agentId);
        if (!shouldSubscribe) {
          this.closeFeishuEventSource();
          return;
        }
        if (this.feishuEventSource && this.feishuEventSource.__agentId === agentId) return;
        this.closeFeishuEventSource();
        const source = new EventSource('/api/feishu-chat/events?agentId=' + encodeURIComponent(agentId));
        source.__agentId = agentId;
        this.feishuEventSource = source;
        this.setFeishuLiveStatus('connecting', agentId);
        source.addEventListener('open', () => {
          if (this.feishuEventSource === source) this.setFeishuLiveStatus('connected', agentId);
        });
        source.addEventListener('ready', () => {
          if (this.feishuEventSource === source) this.setFeishuLiveStatus('connected', agentId);
        });
        source.addEventListener('message', () => this.scheduleFeishuHistoryRefresh());
        source.addEventListener('delivery', () => this.scheduleFeishuHistoryRefresh());
        source.onerror = () => {
          if (this.feishuEventSource === source && this.root.classList.contains('open')) {
            this.setFeishuLiveStatus('disconnected', agentId);
          }
          if (!this.root.classList.contains('open') && this.feishuEventSource === source) {
            this.closeFeishuEventSource();
          }
        };
      } catch (e) {
        this.closeFeishuEventSource();
      }
    }

    async sendHermesBlockingMessage(hermesBody, hermesProgress, hermesSendStartedAt) {
      this.startHermesHistoryPolling();
      try {
        const resp = await fetch('/api/hermes/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(hermesBody)
        });
        const data = await resp.json();
        this.stopHermesHistoryPolling();
        this.removeTypingIndicator();
        if (!resp.ok || (data.ok === false && !data.approval)) throw new Error(data.error || data.reply || resp.statusText);
        this.finishHermesProgress(hermesProgress, true);
        if (this.streamingMsg) {
          this.pendingStreamContent = data.reply || this.pendingStreamContent || this.streamingMsg.content || '';
          this.flushStreamingRender(true);
          const existing = this.messages.querySelector('.streaming-msg');
          if (existing) existing.remove();
          this.streamingMsg = null;
        }
        await this.loadHistory({ recoverFinal: true, startedAt: hermesSendStartedAt });
        await this.pollHermesApproval().catch(() => {});
        this.setStatus('Hermes ready', 'connected');
      } catch (e) {
        this.stopHermesHistoryPolling();
        throw e;
      }
    }

    streamHermesRunEvents(runId, hermesProgress, startedAt = 0) {
      if (!runId) return Promise.reject(new Error('Hermes run did not return a run id'));
      this.closeHermesEventSource();
      this.hermesCompletedToolKeys = new Set();
      this.currentRunId = runId;
      this.setStatus('Hermes stream active...', 'connecting');
      this.markLiveEvent();
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey || '';
      const url = '/api/hermes/runs/' + encodeURIComponent(runId) + '/events?agentId=' + encodeURIComponent(agentId);
      let completed = false;
      return new Promise((resolve, reject) => {
        let settled = false;
        const source = new EventSource(url);
        this.hermesEventSource = source;
        this.hermesStreamCancel = (err) => finish(false, err);
        const cleanup = () => {
          if (this.hermesEventSource === source) this.hermesEventSource = null;
          if (this.hermesStreamCancel) this.hermesStreamCancel = null;
          source.close();
        };
        const finish = (ok, value) => {
          if (settled) return;
          settled = true;
          completed = !!ok;
          cleanup();
          if (ok) resolve(value);
          else reject(value instanceof Error ? value : new Error(String(value || 'Hermes stream failed')));
        };
        const handle = (eventName, evt) => {
          let data = {};
          try { data = JSON.parse(evt.data || '{}'); } catch (_) {}
          this.handleHermesNativeEvent(eventName, data);
          if (['run.completed', 'run.failed', 'run.cancelled', 'run.canceled'].includes(eventName)) {
            finish(eventName === 'run.completed', eventName === 'run.completed' ? data : new Error(data.error || eventName));
          }
        };
        [
          'run.started',
          'message.delta',
          'reasoning.available',
          'tool.started',
          'tool.completed',
          'tool.failed',
          'approval.request',
          'run.completed',
          'run.failed',
          'run.cancelled',
          'run.canceled'
        ].forEach(name => source.addEventListener(name, evt => handle(name, evt)));
        source.onmessage = evt => handle('message', evt);
        source.onerror = () => {
          if (!settled) finish(false, new Error('Hermes native stream disconnected'));
        };
      }).catch(async err => {
        const recovered = await this.recoverHermesFinalFromHistory(startedAt || this.hermesSendStartedAt, 8000).catch(() => false);
        if (recovered) {
          completed = true;
          return { ok: true, recovered: true };
        }
        throw err;
      }).finally(() => {
        this.finishHermesProgress(hermesProgress, completed);
      });
    }

    handleHermesNativeEvent(eventName, data) {
      this.markLiveEvent();
      const runId = data?.runId || this.currentRunId || '';
      if (runId) this.currentRunId = runId;

      if (eventName === 'run.started') {
        this.updateTypingIndicator('Hermes is running...');
        return;
      }

      if (eventName === 'message.delta') {
        if (!this.streamingMsg || this.streamingMsg.id !== runId) {
          this.streamingMsg = { id: runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
        }
        if (data.reply) this.pendingStreamContent = data.reply;
        else if (data.delta) this.pendingStreamContent += String(data.delta || '');
        this.scheduleStreamingRender();
        return;
      }

      if (eventName === 'reasoning.available') {
        this.updateTypingIndicator('Hermes is reasoning...');
        return;
      }

      if (eventName === 'approval.request') {
        if (data.approval) this.appendHermesPendingApproval(data.approval, data.pending_count || 1);
        this.updateTypingIndicator('Hermes is waiting for approval...');
        return;
      }

      if (eventName === 'tool.started' || eventName === 'tool.completed' || eventName === 'tool.failed') {
        const card = data.toolCard || {};
        const isTerminal = eventName !== 'tool.started';
        const payload = {
          runId,
          data: {
            toolCallId: card.id || data.toolCallId || data.id || '',
            phase: isTerminal ? 'result' : 'start',
            name: card.name || data.tool || data.name || 'Hermes tool',
            args: card.arguments || (card.args_preview ? { command: card.args_preview } : (data.preview ? { command: data.preview } : {})),
            result: card.result || data.result || data.output || '',
            isError: eventName === 'tool.failed' || card.status === 'error' || !!data.error,
            error: data.error || card.error || ''
          }
        };
        const label = formatToolLabel(payload.data.name, coerceToolArgs(payload.data.args));
        this.updateTypingIndicator(isTerminal ? 'Processing...' : label);
        if (isTerminal) {
          if (!this.liveToolCards.has(this.toolKey(payload))) {
            this.appendToolCall({ ...payload, data: { ...payload.data, phase: 'start' } });
          }
          this.finishToolCall(payload);
        } else {
          this.updateToolCall(payload);
        }
        return;
      }

      if (['run.completed', 'run.failed', 'run.cancelled', 'run.canceled'].includes(eventName)) {
        const finalText = data.reply || data.output || this.pendingStreamContent || (this.streamingMsg ? this.streamingMsg.content : '');
        this.flushStreamingRender(true);
        this.flushToolEvents(true);
        this.clearActivityFeed();
        this.removeTypingIndicator();
        if (this.streamingMsg) {
          this.finalizeStreamingMessage(finalText);
          this.streamingMsg = null;
        } else if (finalText) {
          this.appendMessage('assistant', finalText);
        }
        if (runId) this.finalizeRunToolCards(runId);
        this.currentRunId = null;
        this.stopRecoveryWatchdog();
      }
    }

    stopHermesProgressTimers() {
      if (!this.hermesProgressTimers?.length) return;
      for (const timer of this.hermesProgressTimers) clearTimeout(timer);
      this.hermesProgressTimers = [];
    }

    startHermesHistoryPolling() {
      this.stopHermesHistoryPolling();
      this.hermesCompletedToolKeys = new Set();
      this.pollHermesLiveActivity().catch(() => {});
      this.hermesHistoryPollTimer = setInterval(() => {
        if (this.isHermesSelected()) this.pollHermesLiveActivity().catch(() => {});
      }, HERMES_HISTORY_POLL_MS);
    }

    stopHermesHistoryPolling() {
      if (this.hermesHistoryPollTimer) clearInterval(this.hermesHistoryPollTimer);
      this.hermesHistoryPollTimer = null;
    }

    startCodexHistoryPolling() {
      this.stopCodexHistoryPolling();
      this.codexCompletedToolKeys = new Set();
      this.pollCodexLiveActivity().catch(() => {});
      this.codexHistoryPollTimer = setInterval(() => {
        if (this.isCodexSelected()) this.pollCodexLiveActivity().catch(() => {});
      }, HERMES_HISTORY_POLL_MS);
    }

    stopCodexHistoryPolling() {
      if (this.codexHistoryPollTimer) clearInterval(this.codexHistoryPollTimer);
      this.codexHistoryPollTimer = null;
    }

    startClaudeCodeHistoryPolling() {
      this.stopClaudeCodeHistoryPolling();
      this.claudeCodeCompletedToolKeys = new Set();
      this.pollClaudeCodeLiveActivity().catch(() => {});
      this.claudeCodeHistoryPollTimer = setInterval(() => {
        if (this.isClaudeCodeSelected()) this.pollClaudeCodeLiveActivity().catch(() => {});
      }, HERMES_HISTORY_POLL_MS);
    }

    stopClaudeCodeHistoryPolling() {
      if (this.claudeCodeHistoryPollTimer) clearInterval(this.claudeCodeHistoryPollTimer);
      this.claudeCodeHistoryPollTimer = null;
    }

    async pollClaudeCodeLiveActivity() {
      if (!this.isClaudeCodeSelected()) return;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const conversationId = this.getProviderConversationId('claude-code');
      const query = new URLSearchParams({ agentId, conversationId });
      const res = await fetch('/api/claude-code/history?' + query.toString());
      const data = await res.json();
      if (!data.ok || !Array.isArray(data.messages)) return;
      const progress = [...data.messages].reverse().find(msg =>
        msg && msg.role === 'assistant' && msg.ephemeral === 'claude-code-progress'
      );
      if (!isRecoverableProviderProgress(progress)) return;

      this.applySessionMetrics(progress);

      const runId = progress.runId || progress.progressId || this.currentRunId || '';
      if (runId) this.currentRunId = runId;

      if (progress.text) {
        if (!this.streamingMsg || this.streamingMsg.id !== runId) {
          this.streamingMsg = { id: runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
        }
        this.pendingStreamContent = progress.text;
        this.scheduleStreamingRender();
      }

      const tools = normalizeHermesTools(progress.tools || []);
      tools.forEach((tool, idx) => {
        const toolId = tool.id || `${idx}:${tool.name}:${JSON.stringify(tool.arguments || {}).slice(0, 80)}`;
        const key = `${runId}:${toolId}`;
        const isDone = ['done', 'error', 'failed'].includes(String(tool.status || '').toLowerCase());
        if (isDone && this.claudeCodeCompletedToolKeys.has(key)) return;
        const payload = {
          runId,
          data: {
            toolCallId: toolId,
            phase: isDone ? 'result' : 'update',
            name: tool.name,
            args: tool.arguments || {},
            result: tool.result || '',
            isError: tool.status === 'error' || !!tool.error,
            error: tool.error || ''
          }
        };
        if (isDone) {
          if (!this.liveToolCards.has(this.toolKey(payload))) {
            this.appendToolCall({ ...payload, data: { ...payload.data, phase: 'start' } });
          }
          this.finishToolCall(payload);
          this.claudeCodeCompletedToolKeys.add(key);
        } else {
          this.updateToolCall(payload);
        }
      });
      if (progress.thinking) this.updateTypingIndicator('Claude Code is reasoning...');
    }

    async pollCodexLiveActivity() {
      if (!this.isCodexSelected()) return;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const conversationId = this.getCodexConversationId();
      const query = new URLSearchParams({ agentId, conversationId });
      const res = await fetch('/api/codex/history?' + query.toString());
      const data = await res.json();
      if (!data.ok || !Array.isArray(data.messages)) return;
      const progress = [...data.messages].reverse().find(msg =>
        msg && msg.role === 'assistant' && msg.ephemeral === 'codex-progress'
      );
      if (!isRecoverableProviderProgress(progress)) return;

      this.applySessionMetrics(progress);

      const runId = progress.runId || progress.progressId || this.currentRunId || '';
      if (runId) this.currentRunId = runId;
      if (progress.approval && String(progress.approval.status || 'pending').toLowerCase() === 'pending') {
        this.appendCodexPendingApproval(progress.approval, progress.approval.pending_count || 1);
      }

      if (progress.text) {
        if (!this.streamingMsg || this.streamingMsg.id !== runId) {
          this.streamingMsg = { id: runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
        }
        this.pendingStreamContent = progress.text;
        this.scheduleStreamingRender();
      }

      const tools = normalizeHermesTools(progress.tools || []);
      tools.forEach((tool, idx) => {
        const toolId = tool.id || `${idx}:${tool.name}:${JSON.stringify(tool.arguments || {}).slice(0, 80)}`;
        const key = `${runId}:${toolId}`;
        const isDone = ['done', 'error', 'failed'].includes(String(tool.status || '').toLowerCase());
        if (isDone && this.codexCompletedToolKeys.has(key)) return;
        const payload = {
          runId,
          data: {
            toolCallId: toolId,
            phase: isDone ? 'result' : 'update',
            name: tool.name,
            args: tool.arguments || {},
            result: tool.result || '',
            isError: tool.status === 'error' || !!tool.error,
            error: tool.error || ''
          }
        };
        if (isDone) {
          if (!this.liveToolCards.has(this.toolKey(payload))) {
            this.appendToolCall({ ...payload, data: { ...payload.data, phase: 'start' } });
          }
          this.finishToolCall(payload);
          this.codexCompletedToolKeys.add(key);
        } else {
          this.updateToolCall(payload);
        }
      });
    }

    async pollHermesLiveActivity() {
      if (!this.isHermesSelected()) return;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const conversationId = this.getProviderConversationId('hermes');
      const query = new URLSearchParams({ agentId, conversationId });
      const res = await fetch('/api/hermes/history?' + query.toString());
      const data = await res.json();
      if (!data.ok || !Array.isArray(data.messages)) return;
      const progress = [...data.messages].reverse().find(msg =>
        msg && msg.role === 'assistant' && msg.ephemeral === 'hermes-progress'
      );
      if (!isRecoverableProviderProgress(progress)) return;
      const runId = progress.runId || progress.progressId || this.currentRunId || '';
      if (progress.text) {
        if (!this.streamingMsg || this.streamingMsg.id !== runId) {
          this.streamingMsg = { id: runId, role: 'assistant', content: '' };
          this.pendingStreamContent = '';
          this.appendStreamingMessage();
        }
        this.pendingStreamContent = progress.text;
        this.scheduleStreamingRender();
      }
      const tools = normalizeHermesTools(progress.tools || []);
      tools.forEach((tool, idx) => {
        const toolId = tool.id || `${idx}:${tool.name}:${JSON.stringify(tool.arguments || {}).slice(0, 80)}`;
        const key = `${runId}:${toolId}`;
        const isDone = ['done', 'error', 'failed'].includes(String(tool.status || '').toLowerCase());
        if (isDone && this.hermesCompletedToolKeys.has(key)) return;
        const payload = {
          runId,
          data: {
            toolCallId: toolId,
            phase: isDone ? 'result' : 'update',
            name: tool.name,
            args: tool.arguments || {},
            result: tool.result || '',
            isError: tool.status === 'error' || !!tool.error,
            error: tool.error || ''
          }
        };
        if (isDone) {
          if (!this.liveToolCards.has(this.toolKey(payload))) {
            this.appendToolCall({ ...payload, data: { ...payload.data, phase: 'start' } });
          }
          this.finishToolCall(payload);
          this.hermesCompletedToolKeys.add(key);
        } else {
          this.updateToolCall(payload);
        }
      });
      if (progress.thinking) this.updateTypingIndicator('Hermes is reasoning...');
    }

    async recoverHermesFinalFromHistory(startedAt, timeoutMs = 45000) {
      if (!this.isHermesSelected()) return false;
      const deadline = Date.now() + timeoutMs;
      const agentId = this.getSelectedAgentId() || this.selectedAgentKey;
      const conversationId = this.getProviderConversationId('hermes');
      while (Date.now() < deadline) {
        const query = new URLSearchParams({ agentId, conversationId });
        const res = await fetch('/api/hermes/history?' + query.toString());
        const data = await res.json();
        if (data.ok && Array.isArray(data.messages)) {
          const finalMsg = [...data.messages].reverse().find(msg =>
            msg &&
            msg.role === 'assistant' &&
            msg.ephemeral !== 'hermes-progress' &&
            (msg.text || msg.approval) &&
            Number(msg.ts || 0) >= Number(startedAt || 0)
          );
          if (finalMsg) {
            if (this.streamingMsg) {
              const existing = this.messages.querySelector('.streaming-msg');
              if (existing) existing.remove();
              this.streamingMsg = null;
            }
            await this.loadHistory({ recoverFinal: true, startedAt });
            return true;
          }
        }
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
      return false;
    }

    startHermesProgress(label) {
      this.stopHermesProgressTimers();
      const runId = 'hermes-' + Date.now() + '-' + Math.random().toString(36).slice(2);
      const planId = runId + ':task-breakdown';
      this.currentRunId = runId;
      this.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_stream_active') : 'Hermes stream active...', 'connecting');
      this.updateTypingIndicator(label + ' ' + (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_is_running') : 'is running Hermes'));
      this.appendActivity(label + ': ' + (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_queued') : 'queued message'));
      const progressSteps = getHermesProgressSteps();
      this.appendToolCall({
        runId,
        data: {
          toolCallId: planId,
          phase: 'start',
          name: 'Hermes task breakdown',
          args: { willDo: progressSteps },
          result: _ct('hermes_queued_waiting')
        }
      });
      progressSteps.forEach((step, idx) => {
        const timer = setTimeout(() => {
          this.appendActivity(label + ': ' + step.toLowerCase());
          this.updateToolCall({
            runId,
            data: {
              toolCallId: planId,
              phase: 'update',
              name: 'Hermes task breakdown',
              args: {
                done: progressSteps.slice(0, idx),
                now: step,
                next: progressSteps.slice(idx + 1)
              },
              partialResult: _ct('hermes_running_step', { current: idx + 1, total: progressSteps.length, step })
            }
          });
          this.updateTypingIndicator(label + ' ' + (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_is_working') : 'is working') + ': ' + step.toLowerCase());
        }, 250 + idx * 1400);
        this.hermesProgressTimers.push(timer);
      });
      return { runId, planId, label };
    }

    finishHermesProgress(progress, ok, errorText = '') {
      if (!progress) return;
      this.stopHermesProgressTimers();
      const progressSteps = getHermesProgressSteps();
      this.finishToolCall({
        runId: progress.runId,
        data: {
          toolCallId: progress.planId,
          phase: 'result',
          name: 'Hermes task breakdown',
          args: {
            done: ok ? progressSteps : progressSteps.slice(0, 3),
            next: ok ? [] : [_ct('hermes_review_error')]
          },
          result: ok ? _ct('hermes_reply_collected') : (errorText || _ct('hermes_request_failed')),
          isError: !ok
        },
        error: ok ? '' : errorText
      });
      this.appendActivity((progress.label || 'Hermes') + (ok ? ': ' + (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_stream_complete') : 'stream complete') : ': ' + (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_stream_failed') : 'stream failed')));
      if (this.currentRunId === progress.runId) this.currentRunId = null;
    }

    async respondHermesApproval(approval, choice, card) {
      if (!approval || !this.isHermesSelected()) return;
      const buttons = card ? [...card.querySelectorAll('button')] : [];
      buttons.forEach(btn => btn.disabled = true);
      if (card) {
        card.classList.add('responding');
        const status = card.querySelector('.chat-approval-status');
        if (status) status.textContent = choice === 'approve_once' ? (typeof i18n !== 'undefined' ? i18n.t('chat_approving_once') : 'Approving once...') : (typeof i18n !== 'undefined' ? i18n.t('chat_denying') : 'Denying...');
      }
      try {
        const resp = await fetch('/api/hermes/approval/respond', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agentId: this.getSelectedAgentId() || this.selectedAgentKey,
            approval,
            approval_id: approval.approval_id || approval.id || '',
            session_id: approval.session_id || approval.sessionId || '',
            choice,
            fromDisplayName: 'User'
          })
        });
        const data = await resp.json();
        if (!resp.ok || data.ok === false) throw new Error(data.error || data.reply || resp.statusText);
        if (card) {
          card.classList.remove('responding');
          card.classList.add(choice === 'approve_once' ? 'approved' : 'denied');
          const status = card.querySelector('.chat-approval-status');
          if (status) status.textContent = choice === 'approve_once' ? (typeof i18n !== 'undefined' ? i18n.t('chat_approved_once') : 'approved once') : (typeof i18n !== 'undefined' ? i18n.t('chat_denied_status') : 'denied');
        }
        if (choice === 'approve_once') {
          await this.pollHermesApproval().catch(() => {});
        } else if (choice === 'deny') {
          this.appendSystem(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_approval_denied') : 'Hermes approval denied.');
          await this.pollHermesApproval().catch(() => {});
        }
        this.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_ready') : 'Hermes ready', 'connected');
      } catch (e) {
        buttons.forEach(btn => btn.disabled = false);
        if (card) {
          card.classList.remove('responding');
          const status = card.querySelector('.chat-approval-status');
        if (status) status.textContent = _ct('error');
        }
        this.appendSystem((typeof i18n !== 'undefined' ? i18n.t('chat_hermes_error') : 'Hermes error') + ': ' + e.message);
        this.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_hermes_error') : 'Hermes error', 'disconnected');
      }
    }

    async respondCodexApproval(approval, choice, card) {
      if (!approval || !this.isCodexSelected()) return;
      const normalized = String(choice || '').toLowerCase().includes('approve') ? 'approve' : 'cancel';
      const buttons = card ? [...card.querySelectorAll('button')] : [];
      buttons.forEach(btn => btn.disabled = true);
      if (card) {
        card.classList.add('responding');
        const status = card.querySelector('.chat-approval-status');
        if (status) status.textContent = normalized === 'approve' ? _ct('chat_approving_once') : _ct('chat_cancelling_approval');
      }
      try {
        const resp = await fetch('/api/codex/approval/respond', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agentId: this.getSelectedAgentId() || this.selectedAgentKey,
            conversationId: this.getCodexConversationId(),
            approval,
            approval_id: approval.approval_id || approval.id || '',
            approvalId: approval.approval_id || approval.id || '',
            session_id: approval.session_id || approval.sessionId || approval.threadId || '',
            sessionId: approval.session_id || approval.sessionId || approval.threadId || '',
            choice: normalized,
            action: normalized
          })
        });
        const data = await resp.json();
        if (!resp.ok || data.ok === false) throw new Error(data.error || data.status || resp.statusText);
        if (card) {
          card.classList.remove('responding');
          card.classList.add(normalized === 'approve' ? 'approved' : 'denied');
          const status = card.querySelector('.chat-approval-status');
          if (status) status.textContent = normalized === 'approve' ? _ct('chat_approved_once') : _ct('chat_cancelled_status');
        }
        if (normalized !== 'approve') this.appendSystem(_ct('chat_codex_approval_cancelled'));
        this.setStatus(_ct('codex_ready'), 'connected');
        await this.pollCodexApproval().catch(() => {});
      } catch (e) {
        buttons.forEach(btn => btn.disabled = false);
        if (card) {
          card.classList.remove('responding');
          const status = card.querySelector('.chat-approval-status');
          if (status) status.textContent = _ct('error');
        }
        this.appendSystem(_ct('chat_codex_approval_failed') + ': ' + e.message);
        this.setStatus(_ct('chat_codex_error'), 'disconnected');
      }
    }
    isNearBottom(threshold = 80) {
      if (!this.messages) return true;
      return this.messages.scrollHeight - this.messages.scrollTop - this.messages.clientHeight <= threshold;
    }

    scrollBottom(force = true) {
      if (!force) return;
      if (this.scrollFrame) return;
      this.scrollFrame = requestAnimationFrame(() => {
        this.scrollFrame = null;
        this.messages.scrollTop = this.messages.scrollHeight;
      });
    }

    scrollBottomAfterLayout() {
      this.scrollBottom(true);
      setTimeout(() => this.scrollBottom(true), 80);
      setTimeout(() => this.scrollBottom(true), 300);
    }

    toolKey(payload) {
      const data = payload?.data && typeof payload.data === 'object' ? payload.data : {};
      const id = data.toolCallId || data.itemId || payload?.toolCallId || payload?.callId || payload?.itemId || payload?.id;
      const runId = payload?.runId || data.runId || this.currentRunId || 'run';
      const name = data.name || payload?.name || payload?.tool || payload?.toolName || 'tool';
      let args = data.args || data.arguments || payload?.arguments || payload?.args || payload?.input || {};
      if (!args || typeof args !== 'object' || Array.isArray(args)) args = { value: args };
      const preview = args.command || args.path || args.file_path || args.url || args.query || args.message || args.value || JSON.stringify(args).slice(0, 120);
      return id || `${runId}:${name}:${String(preview).slice(0, 160)}`;
    }

    appendToolCall(payload) {
      const shouldStick = this.isNearBottom();
      const tool = normalizeToolEvent(payload, 'running');
      const key = this.toolKey(payload);
      tool.key = key;
      const existing = this.liveToolCards.get(key);
      if (existing) {
        updateToolCallCard(existing.querySelector('.chat-tool-call'), tool);
        return;
      }
      const wrap = document.createElement('div');
      wrap.className = 'chat-msg assistant chat-tool-msg';
      wrap.dataset.runId = payload?.runId || tool.runId || this.currentRunId || '';
      wrap.dataset.toolKey = key;
      wrap.appendChild(renderToolCallCard(tool, { live: true }));
      const ind = this.messages.querySelector('.typing-indicator');
      if (ind) this.messages.insertBefore(wrap, ind);
      else this.messages.appendChild(wrap);
      this.liveToolCards.set(key, wrap);
      this.pruneToolCards();
      this.scrollBottom(shouldStick);
    }

    updateToolCall(payload) {
      const shouldStick = this.isNearBottom();
      const key = this.toolKey(payload);
      const wrap = this.liveToolCards.get(key);
      if (!wrap) return this.appendToolCall(payload);
      updateToolCallCard(wrap.querySelector('.chat-tool-call'), normalizeToolEvent(payload, 'running'));
      this.scrollBottom(shouldStick);
    }

    finishToolCall(payload) {
      const shouldStick = this.isNearBottom();
      let key = this.toolKey(payload);
      let wrap = this.liveToolCards.get(key);
      if (!wrap && this.liveToolCards.size) {
        const sameRun = [...this.liveToolCards.entries()].reverse().find(([, el]) => !payload?.runId || el.dataset.runId === payload.runId);
        if (sameRun) { key = sameRun[0]; wrap = sameRun[1]; }
      }
      if (!wrap) return;
      const tool = normalizeToolEvent(payload, payload?.error ? 'error' : 'done');
      const card = wrap.querySelector('.chat-tool-call');
      updateToolCallCard(card, tool);
      this.liveToolCards.delete(key);
      this.scrollBottom(shouldStick);
    }

    finalizeRunToolCards(runId) {
      for (const [key, wrap] of [...this.liveToolCards.entries()]) {
        if (!runId || wrap.dataset.runId === runId) {
          updateToolCallCard(wrap.querySelector('.chat-tool-call'), { status: 'done', result: 'Completed' });
          this.liveToolCards.delete(key);
        }
      }
    }

    appendActivity(text) {
      const shouldStick = this.isNearBottom();
      const existing = this.messages.querySelectorAll('.chat-activity');
      if (existing.length >= 8) existing[0].remove();
      const div = document.createElement('div');
      div.className = 'chat-activity';
      div.innerHTML = '<span class="activity-text">' + escHtml(text) + '</span><span class="activity-time">' + new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) + '</span>';
      const ind = this.messages.querySelector('.typing-indicator');
      if (ind) this.messages.insertBefore(div, ind);
      else this.messages.appendChild(div);
      this.scrollBottom(shouldStick);
    }
  }

  function buildSecondaryChatPanel(slotNum) {
    const placeholder = secondaryPanelPlaceholders[slotNum];
    const primaryPanel = document.getElementById('chat-panel');
    if (!placeholder || !primaryPanel) return null;
    const panel = primaryPanel.cloneNode(true);
    panel.id = `chat-secondary-${slotNum}`;
    panel.dataset.chatSlot = `secondary-${slotNum}`;
    panel.classList.remove('open', 'floating', 'dragging', 'move-active', 'snap-left', 'snap-right');
    panel.classList.add('chat-panel-secondary');
    panel.setAttribute('aria-hidden', 'true');
    panel.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
    panel.querySelector('.chat-secondary-controls')?.remove();
    panel.querySelector('.chat-exterior-tabs')?.remove();

    const header = panel.querySelector('.chat-header');
    header.classList.add('chat-secondary-header');
    const headerBtns = panel.querySelector('.chat-header-btns');
    if (headerBtns) {
      const badge = document.createElement('span');
      badge.className = 'chat-secondary-badge';
      badge.textContent = `W${slotNum}`;
      header.insertBefore(badge, headerBtns);
      // Remove the move button — secondary panels are always tiled, not movable
      const existingMoveBtn = headerBtns.querySelector('.chat-move-btn');
      if (existingMoveBtn) existingMoveBtn.remove();
    }
    const closeBtn = panel.querySelector('.chat-close');
    if (closeBtn) {
      closeBtn.classList.add('chat-secondary-close');
      closeBtn.dataset.chatSlotClose = String(slotNum);
      closeBtn.title = _ct('hide_secondary_chat', { slot: slotNum });
    }
    placeholder.replaceWith(panel);
    return panel;
  }

  function updateChatStackLayout() {
    const root = document.documentElement;
    const sidebarWidth = typeof _getSidebarWidth === 'function' ? _getSidebarWidth() : 0;
    root.style.setProperty('--chat-stack-gap', CHAT_STACK_GAP + 'px');
    root.style.setProperty('--chat-stack-main-right', sidebarWidth + 'px');
    _tileSecondaryPanels();
  }

  /**
   * Tile all open secondary panels to the left of the main panel.
   * Order: Main | 1 | 2 | 3 (right to left).
   * Only sets horizontal position + width. Height is independent per panel.
   * New panels get the main panel's height; existing panels keep theirs.
   */
  let _tileRafPending = false;
  function _tileSecondaryPanels() {
    if (_tileRafPending) return;
    _tileRafPending = true;
    requestAnimationFrame(_tileSecondaryPanelsNow);
  }
  function _tileSecondaryPanelsNow() {
    _tileRafPending = false;
    const mainPanel = document.getElementById('chat-panel');
    if (!mainPanel || !mainPanel.classList.contains('open')) return;

    const GAP = CHAT_STACK_GAP;
    const MIN_W = 160;

    const mainRect = mainPanel.getBoundingClientRect();
    const mainLeft = mainRect.left;

    // Collect open secondary panels in order (1, 2, 3)
    const openSecondaries = [];
    [1, 2, 3].forEach((slotNum) => {
      const p = secondaryChatPanels[String(slotNum)];
      if (p && p.classList.contains('open')) openSecondaries.push(p);
    });

    if (openSecondaries.length === 0) return;

    // Available space to the left of the main panel
    const availableLeft = mainLeft - GAP;
    const totalGaps = (openSecondaries.length - 1) * GAP;
    const secWidth = Math.max(MIN_W, Math.floor((availableLeft - totalGaps) / openSecondaries.length));

    // Position each open secondary from right to left, starting just left of main
    let cursor = mainLeft - GAP;
    openSecondaries.forEach((panel) => {
      const left = cursor - secWidth;
      panel.style.position = 'fixed';
      panel.style.left = Math.max(0, left) + 'px';
      panel.style.right = 'auto';
      panel.style.width = secWidth + 'px';
      panel.style.transform = 'none';
      // Only set height/bottom if panel doesn't have an explicit height yet
      if (!panel.dataset.hasCustomHeight) {
        panel.style.bottom = '0px';
        panel.style.height = mainRect.height + 'px';
        panel.style.top = mainRect.top + 'px';
      }
      cursor = left - GAP;
    });
  }

  /**
   * Reset all chat panels to equal size, tiled side by side, bottom-anchored.
   */
  function _resetChatLayout() {
    const mainPanel = document.getElementById('chat-panel');
    if (!mainPanel || !mainPanel.classList.contains('open')) return;

    const sidebarWidth = typeof _getSidebarWidth === 'function' ? _getSidebarWidth() : 0;
    const GAP = CHAT_STACK_GAP;

    // Reset main panel to default docked position
    mainPanel.classList.remove('floating', 'snap-left', 'snap-right', 'dragging', 'move-active');
    mainPanel.style.left = '';
    mainPanel.style.top = '';
    mainPanel.style.right = sidebarWidth + 'px';
    mainPanel.style.bottom = '';
    mainPanel.style.height = '500px';
    mainPanel.style.transform = '';
    if (chatMoveBtn) chatMoveBtn.classList.remove('active');

    // Count open panels (main + open secondaries)
    const openSecondaries = [];
    [1, 2, 3].forEach((slotNum) => {
      const p = secondaryChatPanels[String(slotNum)];
      if (p && p.classList.contains('open')) openSecondaries.push(p);
    });

    const totalPanels = 1 + openSecondaries.length;
    const available = window.innerWidth - sidebarWidth;
    const totalGaps = (totalPanels - 1) * GAP;
    const equalWidth = Math.max(160, Math.floor((available - totalGaps) / totalPanels));

    // Set main panel width
    mainPanel.style.width = equalWidth + 'px';
    mainPanel.style.right = sidebarWidth + 'px';

    // Reset secondaries — clear custom heights, equal size
    openSecondaries.forEach((panel) => {
      delete panel.dataset.hasCustomHeight;
      panel.style.height = '500px';
      panel.style.bottom = '0px';
      panel.style.top = '';
    });

    // Re-tile with new sizes
    _tileSecondaryPanelsNow();
    _positionExteriorTabs();

    // Scroll all to bottom
    chatWindows.forEach(w => w.scrollBottom());
  }

  function syncSecondaryChatControls() {
    secondarySlotButtons.forEach((button) => {
      const slotNum = button.dataset.chatSlotToggle;
      const panel = secondaryChatPanels[slotNum];
      const isOpen = !!panel && panel.classList.contains('open');
      button.classList.toggle('active', isOpen);
      button.classList.toggle('state-open', isOpen);
      button.classList.toggle('state-hidden', !isOpen);
      button.classList.remove('state-active');
      button.dataset.chatSlotState = isOpen ? 'open' : 'hidden';
      button.setAttribute('aria-pressed', isOpen ? 'true' : 'false');
      button.setAttribute('aria-label', `${isOpen ? 'Hide' : 'Open'} chat window ${slotNum}`);
      button.title = isOpen ? `Hide chat window ${slotNum}` : `Open chat window ${slotNum}`;
    });
    _tileSecondaryPanels();
  }

  function setActiveSecondarySlot(slotNum) {
    const slotKey = slotNum == null ? null : String(slotNum);
    if (slotKey && !secondaryChatPanels[slotKey]?.classList.contains('open')) return;
    activeSecondarySlot = slotKey;
    Object.entries(secondaryChatPanels).forEach(([otherSlot, panel]) => {
      panel?.classList.toggle('chat-panel-active', !!slotKey && otherSlot === slotKey && panel.classList.contains('open'));
    });
    syncSecondaryChatControls();
  }

  function inheritPrimarySelection(windowInstance) {
    if (!windowInstance || windowInstance.hasExplicitAgentSelection) return;
    const primaryOpt = primaryWindow.agentSelect?.selectedOptions?.[0];
    if (!primaryOpt) return;
    windowInstance.applySelection(primaryOpt, { markExplicit: false, systemPrefix: typeof i18n !== 'undefined' ? i18n.t('chat_ready_to_chat_with') : 'Ready to chat with' });
  }

  function shouldUseSingleWindowMobileLayout() {
    return window.innerWidth <= 900;
  }

  function setSecondaryPanelOpen(slotNum, shouldOpen) {
    const slotKey = String(slotNum);
    const panel = secondaryChatPanels[slotKey];
    if (!panel) return;

    const isOpen = panel.classList.contains('open');
    if (isOpen === shouldOpen) {
      syncSecondaryChatControls();
      return;
    }

    if (shouldOpen && shouldUseSingleWindowMobileLayout()) {
      Object.entries(secondaryChatPanels).forEach(([otherSlot, otherPanel]) => {
        if (otherSlot === slotKey || !otherPanel.classList.contains('open')) return;
        setSecondaryPanelOpen(otherSlot, false);
      });
    }

    const windowInstance = chatWindowsByRoot.get(panel);
    if (shouldOpen) inheritPrimarySelection(windowInstance);

    panel.classList.toggle('open', shouldOpen);
    panel.setAttribute('aria-hidden', shouldOpen ? 'false' : 'true');

    if (shouldOpen) {
      panel.dataset.hiddenByUser = 'false';
      windowInstance?.scrollBottom();
      if (connected || windowInstance?.isHermesSelected() || windowInstance?.isCodexSelected()) {
        windowInstance?.loadHistory();
        windowInstance?.fetchSessionInfo();
      }
      windowInstance?.updateFeishuEventSource();
      windowInstance?.input?.focus();
    } else {
      panel.dataset.hiddenByUser = 'true';
      if (windowInstance?.streamingMsg) {
        windowInstance.finalizeStreamingMessage(windowInstance.streamingMsg.content || '');
        windowInstance.streamingMsg = null;
      }
      windowInstance?.removeTypingIndicator();
      windowInstance?.closeFeishuEventSource();
    }
    syncSecondaryChatControls();
  }

  function closeAllSecondaryPanels() {
    Object.keys(secondaryChatPanels).forEach((slotNum) => {
      _secExitMoveMode(slotNum);
      setSecondaryPanelOpen(slotNum, false);
    });
  }

  function toggleSecondaryPanel(slotNum) {
    if (!primaryWindow.root.classList.contains('open')) return;
    const slotKey = String(slotNum);
    const panel = secondaryChatPanels[slotKey];
    if (!panel) return;
    const isOpen = panel.classList.contains('open');
    setSecondaryPanelOpen(slotKey, !isOpen);
  }

  secondarySlotButtons.forEach((button) => button.addEventListener('click', () => toggleSecondaryPanel(button.dataset.chatSlotToggle)));

  // Reset layout button
  const chatResetBtn = document.getElementById('chat-reset-layout');
  if (chatResetBtn) chatResetBtn.addEventListener('click', () => _resetChatLayout());

  function nextId() { return `office-${++reqId}-${Date.now()}`; }

  function getGatewayUrl() {
    const host = window.location.hostname || '127.0.0.1';
    if (window.location.protocol === 'https:') return `wss://${window.location.host}${_chatWsPath}`;
    return `ws://${host}:${_chatWsPort}`;
  }

  function startModelBarRefresh() {
    if (_modelBarInterval) clearInterval(_modelBarInterval);
    _modelBarInterval = setInterval(() => {
      if (!connected) return;
      chatWindows.forEach(w => {
        if (w.isHermesSelected?.() || w.isCodexSelected?.()) w.fetchSessionInfo();
        else w.fetchContextUsage();
      });
    }, 60000);
  }

  function connectGateway() {
    if (ws) return;
    ws = new WebSocket(getGatewayUrl());
    chatWindows.forEach(w => {
      if (!w.isHermesSelected() && !w.isCodexSelected()) w.setStatus(typeof i18n !== 'undefined' ? i18n.t('connecting') : 'Connecting...', 'connecting');
    });
    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      if (msg.type === 'event' && msg.event === 'connect.challenge') return sendConnect();
      if (msg.type === 'res') {
        const cb = pendingCallbacks[msg.id];
        if (cb) { delete pendingCallbacks[msg.id]; cb(msg); }
        return;
      }
      if (msg.type === 'event') handleEvent(msg);
    };
    ws.onclose = (evt) => {
      connected = false;
      ws = null;
      chatWindows.forEach(w => {
        if (!w.isHermesSelected() && !w.isCodexSelected()) w.setStatus((typeof i18n !== 'undefined' ? i18n.t('chat_disconnected_label') : 'Disconnected') + ` (${evt.code})`, 'disconnected');
      });
      if (chatWindows.some(w => w.root.classList.contains('open') || w.currentRunId || w.streamingMsg)) setTimeout(connectGateway, 3000);
    };
    ws.onerror = () => chatWindows.forEach(w => {
      if (!w.isHermesSelected() && !w.isCodexSelected()) w.setStatus(typeof i18n !== 'undefined' ? i18n.t('chat_connection_error') : 'Connection error', 'disconnected');
    });
  }

  function sendConnect() {
    const id = nextId();
    const msg = {
      type: 'req', id, method: 'connect',
      params: {
        minProtocol: 4, maxProtocol: 4,
        client: { id: 'openclaw-control-ui', version: GATEWAY_CLIENT_VERSION || 'unknown', platform: 'web', mode: 'webchat' },
        role: 'operator', scopes: ['operator.read', 'operator.write', 'operator.admin'], caps: ['tool-events'], commands: [], permissions: {},
        auth: { token: GATEWAY_TOKEN }, locale: 'en-US', userAgent: 'virtual-office-chat/1.0'
      }
    };
    pendingCallbacks[id] = (res) => {
      if (res.ok) {
        connected = true;
        chatWindows.forEach(w => {
          if (!w.isHermesSelected() && !w.isCodexSelected()) w.setStatus((typeof i18n !== 'undefined' ? i18n.t('connected') : 'Connected') + ' ⚡', 'connected');
          if (w.isPrimary || w.root.classList.contains('open')) {
            w.fetchSessionInfo();
            w.loadHistory();
          }
        });
        startModelBarRefresh();
      } else {
        chatWindows.forEach(w => {
          if (!w.isHermesSelected() && !w.isCodexSelected()) w.setStatus((typeof i18n !== 'undefined' ? i18n.t('chat_auth_failed_label') : 'Auth failed') + `: ${res.error?.message || 'unknown'}`, 'disconnected');
        });
      }
    };
    ws.send(JSON.stringify(msg));
  }

  function rpc(method, params) {
    return new Promise((resolve, reject) => {
      if (!ws || !connected) return reject(new Error('Not connected'));
      const id = nextId();
      pendingCallbacks[id] = resolve;
      ws.send(JSON.stringify({ type: 'req', id, method, params }));
      setTimeout(() => {
        if (pendingCallbacks[id]) { delete pendingCallbacks[id]; reject(new Error('Timeout')); }
      }, 30000);
    });
  }

  function getSessionsListCached(maxAgeMs = 2500) {
    // Deprecated: broad sessions.list polling was replaced by targeted
    // sessions.describe calls and the backend presence cache.
    const now = Date.now();
    if (_sessionsListCache.promise && now - _sessionsListCache.at < maxAgeMs) return _sessionsListCache.promise;
    _sessionsListCache.at = now;
    _sessionsListCache.promise = rpc('sessions.list', { limit: 100 }).then((res) => {
      _sessionsListCache.payload = res;
      return res;
    }).catch((err) => {
      _sessionsListCache.promise = null;
      throw err;
    });
    return _sessionsListCache.promise;
  }

  function handleEvent(msg) {
    const { event, payload } = msg;
    if (event === 'chat') chatWindows.forEach(w => w.handleChatEvent(payload));
    if (event === 'agent') chatWindows.forEach(w => w.handleAgentEvent(payload));
    if (event === 'session.message') chatWindows.forEach(w => w.handleSessionMessageEvent(payload));
  }

  function agentLabelFromId(agentId) {
    if (!agentId) return '';
    const opt = document.querySelector(`.chat-agent-select option[value="${CSS.escape(String(agentId))}"]`);
    return opt ? opt.textContent.trim() : String(agentId);
  }

  function getWindowAgentLabel(win) {
    return win?.agentSelect?.selectedOptions?.[0]?.textContent?.trim() || agentLabelFromId(win?.agentSelect?.value) || 'Assistant';
  }

  function parseAgentIdFromSessionKey(sessionKey) {
    const m = String(sessionKey || '').match(/^agent:([^:]+):/);
    return m ? m[1] : '';
  }

  function parseA2AEnvelope(text) {
    const m = String(text || '').match(/^\s*\[A2A\s+([^\]]+)\]\s*\n?/);
    if (!m) return null;
    const attrs = {};
    const raw = m[1];
    raw.replace(/([A-Za-z][\w-]*)=("[^"]*"|'[^']*'|\S+)/g, (_, k, v) => {
      v = String(v || '').trim();
      if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
      attrs[k] = v;
      return '';
    });
    const fromId = attrs.from || '';
    const toId = attrs.to || '';
    return {
      fromId,
      toId,
      label: attrs.name || agentLabelFromId(fromId) || fromId || 'Agent',
      toLabel: agentLabelFromId(toId) || toId || '',
      text: String(text || '').slice(m[0].length).trimStart()
    };
  }

  function normalizeSenderMeta(meta, role, win) {
    const out = { ...(meta || {}) };
    if (!out.label) {
      if (role === 'assistant') {
        out.label = getWindowAgentLabel(win);
        out.kind = out.kind || 'agent';
      } else if (role === 'user') {
        out.label = typeof i18n !== 'undefined' ? i18n.t('chat_you_label') : 'You';
        out.kind = out.kind || 'human';
      }
    }
    return out;
  }

  function resolveMessageSender(msg, win) {
    const message = msg?.message || msg || {};
    const role = message.role || msg?.role || '';
    const text = extractText(msg) || (typeof message.content === 'string' ? message.content : '') || '';
    const prov = message.provenance || msg?.provenance || {};
    const targetLabel = getWindowAgentLabel(win);

    if (role === 'assistant') return { label: targetLabel, kind: 'agent' };

    if (role === 'user' && prov?.kind === 'inter_session') {
      const sourceAgentId = parseAgentIdFromSessionKey(prov.sourceSessionKey || '');
      return {
        label: agentLabelFromId(sourceAgentId) || (typeof i18n !== 'undefined' ? i18n.t('chat_assistant_label') : 'Agent'),
        toLabel: targetLabel,
        kind: 'agent',
        isInterSession: true,
        sourceAgentId
      };
    }

    const envelope = parseA2AEnvelope(text);
    if (role === 'user' && envelope) {
      return { label: envelope.label, toLabel: envelope.toLabel || targetLabel, kind: 'agent', isInterSession: true, sourceAgentId: envelope.fromId };
    }

    return { label: typeof i18n !== 'undefined' ? i18n.t('chat_you_label') : 'You', kind: 'human' };
  }

  function renderSenderHeader(meta, role) {
    if (!meta?.label || role === 'system') return null;
    const div = document.createElement('div');
    div.className = 'chat-sender-label ' + (meta.kind === 'agent' ? 'agent' : 'human');
    div.textContent = meta.toLabel ? `${meta.label} → ${meta.toLabel}` : meta.label;
    return div;
  }

  function extractToolItems(msg) {
    const c = msg?.message?.content ?? msg?.content;
    if (!Array.isArray(c)) return [];
    const tools = [];
    for (const b of c) {
      if (!b || typeof b !== 'object') continue;
      const type = b.type || '';
      if (type === 'toolCall' || type === 'tool_call') {
        tools.push({
          status: 'done',
          name: b.name || b.toolName || b.function?.name || 'tool',
          arguments: b.arguments || b.args || b.input || b.function?.arguments || {},
          id: b.id || b.toolCallId || b.callId || ''
        });
      } else if (type === 'toolResult' || type === 'tool_result') {
        const last = tools[tools.length - 1];
        const result = b.result ?? b.output ?? b.content ?? b.text ?? b.error ?? '';
        if (last && (!b.toolCallId || b.toolCallId === last.id)) {
          last.result = result;
          last.status = b.error ? 'error' : 'done';
        } else {
          tools.push({ status: b.error ? 'error' : 'done', name: b.name || 'tool result', result, id: b.toolCallId || b.id || '' });
        }
      }
    }
    return tools;
  }

  function normalizeHistoricalTools(items) {
    if (!Array.isArray(items)) return [];
    return items.filter(Boolean).map((item) => ({
      id: item.id || item.toolCallId || item.callId || '',
      runId: item.runId || '',
      status: item.status || (item.error ? 'error' : item.result ? 'done' : 'running'),
      name: item.name || item.toolName || item.tool_name || 'tool',
      arguments: coerceToolArgs(item.arguments || item.args || item.input || {}),
      result: item.result ?? item.output ?? item.content ?? '',
      error: item.error || ''
    }));
  }

  function toolHistoryKey(tool) {
    if (!tool) return '';
    if (tool.id) return 'id:' + tool.id;
    const args = coerceToolArgs(tool.arguments || {});
    const preview = args.command || args.path || args.file_path || args.url || args.query || args.message || args.value || '';
    return [tool.runId || '', tool.name || 'tool', tool.status || '', String(preview).slice(0, 160)].join('|');
  }

  function normalizeHermesTools(items, coerceCompleted = false) {
    if (!Array.isArray(items)) return [];
    return items.filter(Boolean).map((item) => {
      let status = item.status || (item.error ? 'error' : 'done');
      let result = item.result ?? item.output ?? item.content ?? '';
      if (coerceCompleted && String(status).toLowerCase() === 'running') {
        status = 'done';
        if (!result || result === 'Running') result = 'Completed';
      }
      return {
        id: item.id || item.toolCallId || item.callId || '',
        status,
        name: item.name || item.toolName || item.tool_name || 'tool',
        arguments: coerceToolArgs(item.arguments || item.args || item.input || (item.args_preview ? { command: item.args_preview } : {})),
        result,
        error: item.error || ''
      };
    });
  }

  function normalizeToolEvent(payload, fallbackStatus = 'running') {
    const data = payload?.data && typeof payload.data === 'object' ? payload.data : {};
    const phase = data.phase || payload?.phase || '';
    const isError = data.isError || payload?.isError || payload?.error;
    let status = payload?.status || fallbackStatus;
    if (phase === 'start' || phase === 'update') status = 'running';
    if (phase === 'result' || phase === 'end') status = isError ? 'error' : 'done';
    const result = data.result ?? data.partialResult ?? payload?.result ?? payload?.output ?? payload?.content ?? payload?.text ?? '';
    const error = data.error || payload?.error || (isError && typeof result === 'string' ? result : '');
    let args = data.args || data.arguments || payload?.arguments || payload?.args || payload?.input || {};
    if (!args || typeof args !== 'object' || Array.isArray(args)) args = { value: args };
    if (data.meta && !args.command && !args.description) args.description = data.meta;
    return {
      id: data.toolCallId || data.itemId || payload?.toolCallId || payload?.callId || payload?.itemId || payload?.id || '',
      runId: payload?.runId || data.runId || '',
      status,
      name: data.name || data.title || payload?.name || payload?.tool || payload?.toolName || 'tool',
      arguments: args,
      result,
      error
    };
  }

  function renderToolCallCard(tool, opts = {}) {
    const details = document.createElement('details');
    details.className = `chat-tool-call ${tool.status || 'running'}`;
    if (opts.live || tool.status === 'running') details.open = true;
    details.dataset.toolName = tool.name || 'tool';

    const summary = document.createElement('summary');
    summary.className = 'chat-tool-summary';
    const dot = document.createElement('span');
    dot.className = 'chat-tool-running-dot';
    const icon = document.createElement('span');
    icon.className = 'chat-tool-icon';
    icon.textContent = toolIcon(tool);
    const name = document.createElement('span');
    name.className = 'chat-tool-name';
    name.textContent = formatToolName(tool.name);
    const preview = document.createElement('span');
    preview.className = 'chat-tool-preview';
    preview.textContent = formatToolPreview(tool);
    const toggle = document.createElement('span');
    toggle.className = 'chat-tool-toggle';
    toggle.textContent = '▶';
    const state = document.createElement('span');
    state.className = 'chat-tool-state';
    state.textContent = tool.status === 'error' ? (typeof i18n !== 'undefined' ? i18n.t('chat_error_label') : 'error') : tool.status === 'done' ? (typeof i18n !== 'undefined' ? i18n.t('chat_completed_label') : 'done') : (typeof i18n !== 'undefined' ? i18n.t('chat_running_label') : 'running');
    summary.append(dot, icon, name, preview, toggle, state);
    details.appendChild(summary);

    const body = document.createElement('div');
    body.className = 'chat-tool-body';
    body.appendChild(renderToolSection(typeof i18n !== 'undefined' ? i18n.t('chat_input_label') : 'Input', formatToolPayload(tool.arguments || {})));
    if (tool.result || tool.error) {
      const summary = summarizeAgentToolResult(tool.error || tool.result);
      if (summary) body.appendChild(renderAgentToolResultSummary(summary));
      else body.appendChild(renderToolSection(tool.error ? (typeof i18n !== 'undefined' ? i18n.t('chat_error_label') : 'Error') : 'Result', formatToolPayload(tool.error || tool.result)));
    }
    details.appendChild(body);
    return details;
  }

  function updateToolCallCard(card, tool) {
    if (!card) return;
    const previousStatus = card.classList.contains('running') ? 'running' : card.classList.contains('error') ? 'error' : card.classList.contains('done') ? 'done' : '';
    card.classList.remove('running', 'done', 'error');
    card.classList.add(tool.status || 'done');
    if (previousStatus && previousStatus !== (tool.status || 'done')) {
      card.classList.add('status-changed');
      setTimeout(() => card.classList.remove('status-changed'), 850);
      if ((tool.status === 'done' || tool.status === 'error') && card.open) {
        setTimeout(() => { if (card.classList.contains('done') || card.classList.contains('error')) card.open = false; }, 900);
      }
    }
    const icon = card.querySelector('.chat-tool-icon');
    if (icon) icon.textContent = toolIcon(tool);
    const state = card.querySelector('.chat-tool-state');
    if (state) state.textContent = tool.status === 'error' ? (typeof i18n !== 'undefined' ? i18n.t('chat_error_label') : 'error') : tool.status === 'done' ? (typeof i18n !== 'undefined' ? i18n.t('chat_completed_label') : 'done') : (typeof i18n !== 'undefined' ? i18n.t('chat_running_label') : 'running');
    const name = card.querySelector('.chat-tool-name');
    if (name) name.textContent = formatToolName(tool.name);
    const preview = card.querySelector('.chat-tool-preview');
    if (preview) preview.textContent = formatToolPreview(tool);
    const body = card.querySelector('.chat-tool-body');
    if (body) {
      body.innerHTML = '';
      body.appendChild(renderToolSection(typeof i18n !== 'undefined' ? i18n.t('chat_input_label') : 'Input', formatToolPayload(tool.arguments || {})));
      if (tool.result || tool.error) {
        const summary = summarizeAgentToolResult(tool.error || tool.result);
        if (summary) body.appendChild(renderAgentToolResultSummary(summary));
        else body.appendChild(renderToolSection(tool.error ? (typeof i18n !== 'undefined' ? i18n.t('chat_error_label') : 'Error') : tool.status === 'running' ? (typeof i18n !== 'undefined' ? i18n.t('chat_progress_label') : 'Progress') : 'Result', formatToolPayload(tool.error || tool.result)));
      }
    }
  }

  function parseToolJsonResult(value) {
    if (!value) return null;
    if (typeof value === 'object') return value;
    const raw = String(value || '').trim();
    const start = raw.indexOf('{');
    if (start < 0) return null;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < raw.length; i += 1) {
      const ch = raw[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (ch === '\\') escaped = true;
        else if (ch === '"') inString = false;
      } else if (ch === '"') {
        inString = true;
      } else if (ch === '{') {
        depth += 1;
      } else if (ch === '}') {
        depth -= 1;
        if (depth === 0) {
          try { return JSON.parse(raw.slice(start, i + 1)); } catch { return null; }
        }
      }
    }
    return null;
  }

  function summarizeAgentToolResult(value) {
    const data = parseToolJsonResult(value);
    if (!data || typeof data !== 'object') return null;
    const from = data.from && typeof data.from === 'object' ? data.from : {};
    const to = data.to && typeof data.to === 'object' ? data.to : {};
    const hasAgentShape = data.conversationId || data.messageId || data.replyMessageId || from.id || to.id || data.reply;
    if (!hasAgentShape) return null;
    return {
      ok: data.ok !== false,
      conversationId: data.conversationId || '',
      from: from.name || from.id || '',
      to: to.name || to.id || '',
      status: data.status || 'completed',
      reply: data.reply || data.text || '',
      modifiedFiles: Array.isArray(data.modifiedFiles) ? data.modifiedFiles : [],
      needsHumanIntervention: !!data.needsHumanIntervention,
      activeConversationId: data.activeConversationId || '',
      raw: value
    };
  }

  function renderAgentToolResultSummary(summary) {
    const section = document.createElement('div');
    section.className = 'chat-agent-result-summary';
    const head = document.createElement('div');
    head.className = 'chat-agent-result-head';
    const title = document.createElement('strong');
    title.textContent = summary.to ? `${summary.to} 回复` : 'Agent 回复';
    const state = document.createElement('span');
    state.className = 'chat-tool-state';
    state.textContent = summary.ok ? (typeof i18n !== 'undefined' ? i18n.t('chat_completed_label') : 'completed') : (typeof i18n !== 'undefined' ? i18n.t('chat_error_label') : 'error');
    head.append(title, state);
    section.appendChild(head);

    const meta = document.createElement('div');
    meta.className = 'chat-agent-result-meta';
    meta.textContent = [summary.from && `from ${summary.from}`, summary.to && `to ${summary.to}`, summary.conversationId && `conversation ${summary.conversationId}`].filter(Boolean).join(' · ');
    if (meta.textContent) section.appendChild(meta);

    if (summary.reply) {
      const reply = document.createElement('div');
      reply.className = 'chat-agent-result-reply';
      reply.textContent = summary.reply;
      section.appendChild(reply);
    }
    if (summary.modifiedFiles.length || summary.needsHumanIntervention || summary.activeConversationId) {
      const facts = document.createElement('div');
      facts.className = 'chat-agent-result-facts';
      if (summary.modifiedFiles.length) facts.appendChild(document.createTextNode(`修改文件 ${summary.modifiedFiles.length} 个`));
      if (summary.needsHumanIntervention) facts.appendChild(document.createTextNode((facts.textContent ? ' · ' : '') + '需要人工介入'));
      if (summary.activeConversationId) facts.appendChild(document.createTextNode((facts.textContent ? ' · ' : '') + `活跃会话 ${summary.activeConversationId}`));
      section.appendChild(facts);
    }

    const raw = document.createElement('details');
    raw.className = 'chat-agent-result-raw';
    const rawSummary = document.createElement('summary');
    rawSummary.textContent = '原始返回';
    const pre = document.createElement('pre');
    pre.textContent = formatToolPayload(summary.raw);
    raw.append(rawSummary, pre);
    section.appendChild(raw);
    return section;
  }

  function renderToolSection(label, text) {
    const section = document.createElement('div');
    section.className = 'chat-tool-section';
    const h = document.createElement('div');
    h.className = 'chat-tool-section-label';
    h.textContent = label;
    const pre = document.createElement('pre');
    pre.textContent = text || '—';
    section.append(h, pre);
    return section;
  }

  function renderThinkingCard(text, options = {}) {
    const details = document.createElement('details');
    details.className = 'chat-thinking-card';
    if (options.codex) {
      details.classList.add('codex-reasoning-card');
      details.title = _ct('reasoning_summary_hint');
    }
    const summary = document.createElement('summary');
    summary.className = 'chat-thinking-summary';
    const label = document.createElement('span');
    label.className = 'chat-thinking-title';
    label.textContent = options.codex ? _ct('reasoning_summary') : _ct('chat_thinking');
    const state = document.createElement('span');
    state.className = 'chat-tool-state';
    state.textContent = options.codex ? (options.status === 'done' ? _ct('complete') : _ct('live')) : _ct('chat_trace_label');
    const toggle = document.createElement('span');
    toggle.className = 'chat-tool-toggle';
    toggle.textContent = '▶';
    summary.append('💡', label, toggle, state);
    const body = document.createElement('div');
    body.className = 'chat-thinking-body';
    const pre = document.createElement('pre');
    pre.textContent = String(text || '').trim();
    body.appendChild(pre);
    details.append(summary, body);
    return details;
  }

  function updateThinkingCard(card, text, status = 'running') {
    if (!card) return;
    const pre = card.querySelector('.chat-thinking-body pre');
    if (pre) pre.textContent = String(text || '').trim();
    const state = card.querySelector('.chat-tool-state');
    if (state && card.classList.contains('codex-reasoning-card')) state.textContent = status === 'done' ? _ct('complete') : _ct('live');
    card.classList.toggle('done', status === 'done');
  }

  function renderHermesApprovalCard(approval, windowInstance) {
    const card = document.createElement('div');
    const status = String(approval.status || 'pending').toLowerCase();
    const isCodex = String(approval.provider || '').startsWith('codex') || String(approval.agentId || '').startsWith('codex-') || String(approval.title || '').toLowerCase().includes('codex');
    card.className = 'chat-approval-card ' + (status.includes('denied') || status.includes('cancel') ? 'denied' : status.includes('approved') ? 'approved' : 'pending');
    card.dataset.approvalId = approval.approval_id || approval.id || '';

    const header = document.createElement('div');
    header.className = 'chat-approval-header';
    const icon = document.createElement('span');
    icon.className = 'chat-approval-icon';
    icon.textContent = (status.includes('denied') || status.includes('cancel')) ? '✕' : status.includes('approved') ? '✓' : '!';
    const title = document.createElement('span');
    title.className = 'chat-approval-title';
    title.textContent = approval.title || (isCodex ? _ct('chat_codex_approval_required') : (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_approval_required') : 'Hermes approval required'));
    const state = document.createElement('span');
    state.className = 'chat-approval-status';
    const pendingCount = Number(approval.pending_count || approval.pendingCount || 0);
    state.textContent = status === 'pending' && pendingCount > 1 ? `${pendingCount} ` + (typeof i18n !== 'undefined' ? i18n.t('chat_pending_count') : 'pending') : (status === 'pending' ? (typeof i18n !== 'undefined' ? i18n.t('chat_pending_label') : 'pending') : status);
    header.append(icon, title, state);

    const desc = document.createElement('div');
    desc.className = 'chat-approval-desc';
    desc.textContent = approval.description || (isCodex ? _ct('chat_codex_needs_approval') : (typeof i18n !== 'undefined' ? i18n.t('chat_hermes_needs_approval') : 'Hermes needs user approval before it can continue.'));

    const cmd = document.createElement('pre');
    cmd.className = 'chat-approval-command';
    cmd.textContent = approval.command || (isCodex ? _ct('chat_codex_approval_gated_action') : (typeof i18n !== 'undefined' ? i18n.t('chat_approval_gated_command') : 'Approval-gated Hermes command'));

    card.append(header, desc, cmd);
    if (status === 'pending') {
      const actions = document.createElement('div');
      actions.className = 'chat-approval-actions';
      const allow = document.createElement('button');
      allow.type = 'button';
      allow.className = 'chat-approval-btn primary';
      allow.textContent = typeof i18n !== 'undefined' ? i18n.t('chat_allow_once') : 'Allow once';
      allow.title = isCodex ? _ct('chat_codex_approval_allow_hint') : _ct('retry_hermes_allow_hint');
      allow.addEventListener('click', () => {
        if (isCodex) windowInstance?.respondCodexApproval(approval, 'approve', card);
        else windowInstance?.respondHermesApproval(approval, 'approve_once', card);
      });
      const deny = document.createElement('button');
      deny.type = 'button';
      deny.className = 'chat-approval-btn';
      deny.textContent = typeof i18n !== 'undefined' ? i18n.t('chat_deny') : 'Deny';
      deny.title = isCodex ? _ct('chat_codex_approval_cancel_hint') : _ct('retry_hermes_deny_hint');
      deny.addEventListener('click', () => {
        if (isCodex) windowInstance?.respondCodexApproval(approval, 'cancel', card);
        else windowInstance?.respondHermesApproval(approval, 'deny', card);
      });
      actions.append(allow, deny);
      card.appendChild(actions);
    }
    return card;
  }

  function coerceToolArgs(value) {
    if (!value) return {};
    if (typeof value === 'string') {
      try { return JSON.parse(value); } catch { return { input: value }; }
    }
    return typeof value === 'object' ? value : { value };
  }

  function formatToolPayload(value) {
    if (value == null || value === '') return '';
    if (typeof value === 'string') return value.length > MAX_TOOL_PAYLOAD_CHARS ? value.slice(0, MAX_TOOL_PAYLOAD_CHARS) + '\n… [truncated]' : value;
    try {
      const s = JSON.stringify(value, null, 2);
      return s.length > MAX_TOOL_PAYLOAD_CHARS ? s.slice(0, MAX_TOOL_PAYLOAD_CHARS) + '\n… [truncated]' : s;
    } catch {
      return String(value);
    }
  }

  function extractText(msg) {
    const c = msg?.message?.content ?? msg?.content;
    if (typeof c === 'string') return c;
    if (Array.isArray(c)) return c.filter(b => b.type === 'text').map(b => b.text).join('');
    return '';
  }

  function extractMedia(msg, text) {
    const media = [];
    const c = msg?.message?.content ?? msg?.content;
    const add = (item) => {
      const normalized = normalizeOneChatMedia(item);
      if (normalized) media.push(normalized);
    };
    if (Array.isArray(c)) {
      for (const b of c) {
        if (!b || b.type === 'text') continue;
        if (b.type === 'image' || b.type === 'image_url' || b.type === 'input_image') {
          add({ url: b.url || b.image_url?.url || b.source?.url || b.path || b.filePath, mimeType: b.mimeType || b.media_type || b.source?.media_type || 'image/*', name: b.name || b.filename || 'image' });
        } else if (b.type === 'file' || b.type === 'media' || b.type === 'attachment' || b.type === 'video' || b.type === 'audio') {
          add({ url: b.url || b.path || b.filePath || b.source?.url, mimeType: b.mimeType || b.media_type || b.contentType || b.source?.media_type || '', name: b.name || b.filename });
        }
      }
    }
    const sourceText = text || '';
    for (const rawLine of sourceText.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (/^MEDIA:/i.test(line)) add({ url: line.replace(/^MEDIA:/i, '').trim() });
      const attachMatch = line.match(/^\(attached file:\s*(.+?)\)$/i) || line.match(/^attached file:\s*(.+)$/i);
      if (attachMatch) add({ url: attachMatch[1].trim() });
    }
    const seen = new Set();
    return media.filter(item => {
      const key = item.url || item.path;
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function normalizeOneChatMedia(item) {
    if (!item) return null;
    if (typeof item === 'string') item = { url: item };
    let url = item.url || item.path || item.filePath || item.href || item.mediaUrl || item.proxyUrl || '';
    if (!url) return null;
    url = String(url).trim();
    const dataUrlMatch = url.match(/^data:([^;,]+)[;,]/i);
    const dataMime = dataUrlMatch ? dataUrlMatch[1].toLowerCase() : '';
    const name = item.name || item.filename || (dataMime ? (dataMime.split('/')[0] || 'media') : decodeURIComponent((url.split('/').pop() || 'media').split('?')[0]));
    const mimeType = item.mimeType || item.contentType || (dataMime && dataMime !== 'text/plain' ? dataMime : '') || item.type || guessMimeFromName(name, url);
    const isLocalPath = url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/__openclaw__') && !url.startsWith('/sms-media') && !url.startsWith('/chat-media');
    const src = isLocalPath ? '/chat-media?path=' + encodeURIComponent(url) : url;
    return { url: src, originalUrl: url, name, mimeType };
  }

  function normalizeChatMedia(items) {
    if (!items) return [];
    if (!Array.isArray(items)) items = [items];
    return items.map(normalizeOneChatMedia).filter(Boolean);
  }

  function guessMimeFromName(name, url) {
    const v = (name || url || '').toLowerCase().split('?')[0];
    if (/\.(png|jpg|jpeg|gif|webp|bmp|svg)$/.test(v)) return 'image/*';
    if (/\.(mp4|webm|mov|m4v|ogg)$/.test(v)) return 'video/*';
    if (/\.(mp3|wav|m4a|aac|flac|opus)$/.test(v)) return 'audio/*';
    if (/\.pdf$/.test(v)) return 'application/pdf';
    return '';
  }

  function renderChatMedia(media) {
    const wrap = document.createElement('div');
    wrap.className = 'chat-media-list';
    for (const item of media) {
      const type = (item.mimeType || '').toLowerCase();
      const card = document.createElement('figure');
      card.className = 'chat-media-item';
      if (type.startsWith('image/') || type === 'image/*') {
        const img = document.createElement('img');
        img.src = item.url;
        img.alt = item.name || (typeof i18n !== 'undefined' ? i18n.t('chat_image_alt') : 'image');
        img.className = 'chat-image-thumb chat-image-clickable';
        img.addEventListener('click', () => openImageLightbox(item.url));
        card.appendChild(img);
      } else if (type.startsWith('video/') || type === 'video/*') {
        const video = document.createElement('video');
        video.src = item.url;
        video.controls = true;
        video.preload = 'metadata';
        video.className = 'chat-media-video';
        card.appendChild(video);
      } else if (type.startsWith('audio/') || type === 'audio/*') {
        const audio = document.createElement('audio');
        audio.src = item.url;
        audio.controls = true;
        audio.preload = 'metadata';
        audio.className = 'chat-media-audio';
        card.appendChild(audio);
      } else {
        const link = document.createElement('a');
        link.href = item.url;
        link.target = '_blank';
        link.rel = 'noopener';
        link.className = 'chat-media-file';
        link.textContent = '📎 ' + (item.name || (typeof i18n !== 'undefined' ? i18n.t('chat_open_attachment') : 'Open attachment'));
        card.appendChild(link);
      }
      if (item.name && (type.startsWith('image/') || type.startsWith('video/') || type.startsWith('audio/') || type.endsWith('/*'))) {
        const cap = document.createElement('figcaption');
        cap.textContent = item.name;
        card.appendChild(cap);
      }
      wrap.appendChild(card);
    }
    return wrap;
  }

  function parseDataUrl(dataUrl) {
    const m = dataUrl.match(/^data:([^;]+);base64,(.+)$/);
    if (!m) return null;
    return { mimeType: m[1], content: m[2] };
  }

  function compressImage(dataUrl, maxBase64Len = 350000) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        let w = img.width, h = img.height;
        const maxDim = 800;
        if (w > maxDim || h > maxDim) {
          const ratio = Math.min(maxDim / w, maxDim / h);
          w = Math.round(w * ratio); h = Math.round(h * ratio);
        }
        canvas.width = w; canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        let quality = 0.7;
        let result = canvas.toDataURL('image/jpeg', quality);
        while (result.length - 23 > maxBase64Len && quality > 0.05) {
          quality -= 0.1;
          if (quality < 0.3 && w > 400) {
            w = Math.round(w * 0.7); h = Math.round(h * 0.7);
            canvas.width = w; canvas.height = h;
            canvas.getContext('2d').drawImage(img, 0, 0, w, h);
          }
          result = canvas.toDataURL('image/jpeg', quality);
        }
        resolve(result);
      };
      img.onerror = () => resolve(dataUrl);
      img.src = dataUrl;
    });
  }

  function openImageLightbox(src) {
    let overlay = document.getElementById('image-lightbox');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'image-lightbox';
      overlay.className = 'image-lightbox';
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay || e.target.classList.contains('lightbox-close')) overlay.classList.remove('active');
      });
      const closeBtn = document.createElement('button');
      closeBtn.className = 'lightbox-close';
      closeBtn.textContent = '✕';
      overlay.appendChild(closeBtn);
      const img = document.createElement('img');
      img.className = 'lightbox-img';
      overlay.appendChild(img);
      document.body.appendChild(overlay);
    }
    overlay.querySelector('.lightbox-img').src = src;
    overlay.classList.add('active');
  }

  const _SAFE_TAGS = new Set(['p','br','strong','b','em','i','u','s','del','mark','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','hr','pre','code','span','a','img','table','thead','tbody','tr','th','td','sup','sub','small','details','summary']);
  const _SAFE_ATTRS = { 'a': ['href','title','target','rel'], 'img': ['src','alt','title','class','width','height'], 'code': ['class'], 'span': ['class'], 'pre': ['class'], 'td': ['align'], 'th': ['align'] };
  function _sanitizeHtml(html) {
    return html.replace(/<\/?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\/?>/g, function(match, tag) {
      var lower = tag.toLowerCase();
      if (!_SAFE_TAGS.has(lower)) return '';
      var allowed = _SAFE_ATTRS[lower];
      if (!allowed) {
        if (match.charAt(1) === '/') return '</' + lower + '>';
        if (match.slice(-2) === '/>') return '<' + lower + ' />';
        return '<' + lower + '>';
      }
      var attrsStr = '';
      var attrRe = /\s([a-zA-Z\-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))/g;
      var m;
      while ((m = attrRe.exec(match)) !== null) {
        var attrName = m[1].toLowerCase();
        var attrVal = m[2] !== undefined ? m[2] : (m[3] !== undefined ? m[3] : m[4]);
        if (allowed.indexOf(attrName) !== -1) {
          if ((attrName === 'href' || attrName === 'src') && /^\s*javascript\s*:/i.test(attrVal)) continue;
          attrsStr += ' ' + attrName + '="' + attrVal.replace(/"/g, '&quot;') + '"';
        }
      }
      if (match.charAt(1) === '/') return '</' + lower + '>';
      if (match.slice(-2) === '/>') return '<' + lower + attrsStr + ' />';
      return '<' + lower + attrsStr + '>';
    });
  }
  function formatContent(text) {
    if (!text) return '';
    const safeText = escHtml(text);
    let html;
    if (typeof marked !== 'undefined') {
      marked.setOptions({ breaks: true, gfm: true, sanitize: false });
      html = marked.parse(safeText);
    } else {
      html = safeText.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
    }
    html = _sanitizeHtml(html);
    html = html.replace(/<img ([^>]*)>/g, '<img $1 class="chat-image-thumb chat-image-clickable">');
    return html;
  }
  function escHtml(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  function formatToolLabel(name, args) {
    const truncate = (s, n) => s && s.length > n ? s.slice(0, n) + '...' : (s || '');
    switch (name) {
      case 'exec': return '⚙️ exec: ' + truncate(args.command || '', 60);
      case 'bash': return '⚙️ bash: ' + truncate(args.command || args.description || '', 60);
      case 'Command': return '⚙️ command: ' + truncate(args.command || args.description || '', 60);
      case 'read': return '📄 read: ' + truncate(args.path || args.file_path || '', 50);
      case 'write': return '💾 write: ' + truncate(args.path || args.file_path || '', 50);
      case 'edit': return '✏️ edit: ' + truncate(args.path || args.file_path || '', 50);
      case 'sessions_send': return '📡 sessions_send → ' + truncate(args.sessionKey || args.label || '', 40);
      case 'sessions_spawn': return '🤖 spawn: ' + truncate(args.agentId || '', 30) + (args.task ? ' — ' + truncate(args.task, 40) : '');
      case 'sessions_history': return '📜 history: ' + truncate(args.sessionKey || '', 40);
      case 'sessions_list': return '📋 sessions_list';
      case 'todo': return '✅ tasks: ' + truncate(args.todos ? `${args.todos.length} updates` : args.content || args.id || '', 50);
      case 'memory_search': return '🧠 memory: ' + truncate(args.query || '', 50);
      case 'memory_get': return '🧠 memory_get: ' + truncate(args.path || '', 40);
      case 'web_search': return '🔍 search: ' + truncate(args.query || '', 50);
      case 'web_fetch': return '🌐 fetch: ' + truncate(args.url || '', 50);
      case 'browser': return '🖥️ browser: ' + truncate(args.action || '', 20);
      case 'process': return '🔄 process: ' + truncate(args.action || '', 20);
      case 'tts': return '🔊 tts';
      case 'image': return '🖼️ image analysis';
      default: return '🔧 ' + (name || 'tool');
    }
  }

  function formatToolName(name) {
    const raw = String(name || 'tool');
    if (raw === 'Command') return 'command';
    if (raw === 'Hermes task breakdown') return _ct('hermes_task_plan');
    return raw.replace(/^functions\./, '');
  }

  function toolIcon(tool) {
    const name = String(tool?.name || '').toLowerCase();
    if (tool?.status === 'error' || tool?.error) return '⚠️';
    if (name.includes('task') || name === 'todo') return tool?.status === 'done' ? '✓' : '◌';
    if (name.includes('read') || name.includes('fetch')) return '📄';
    if (name.includes('write') || name.includes('edit')) return '✎';
    if (name.includes('search')) return '⌕';
    if (name.includes('browser')) return '◈';
    if (tool?.status === 'done') return '✓';
    return '⚡';
  }

  function formatToolPreview(tool) {
    const args = coerceToolArgs(tool?.arguments || {});
    const result = String(tool?.error || tool?.result || '').replace(/\s+/g, ' ').trim();
    const pick = (...keys) => {
      for (const key of keys) if (args[key]) return String(args[key]);
      return '';
    };
    let preview = '';
    switch (tool?.name) {
      case 'exec':
      case 'bash':
      case 'Command':
        preview = pick('command', 'description', 'value');
        break;
      case 'read':
      case 'write':
      case 'edit':
        preview = pick('path', 'file_path', 'filePath');
        break;
      case 'sessions_send':
        preview = pick('sessionKey', 'label', 'message');
        break;
      case 'sessions_spawn':
        preview = [pick('agentId'), pick('task')].filter(Boolean).join(' · ');
        break;
      case 'todo':
        preview = args.todos ? `${args.todos.length} task updates` : pick('content', 'id');
        break;
      case 'Hermes task breakdown':
        preview = args.now || (Array.isArray(args.done) ? _ct('hermes_steps_complete', { count: args.done.length }) : _ct('hermes_plan_preview'));
        break;
      default:
        preview = pick('query', 'url', 'action', 'input', 'value');
    }
    if (!preview && result) preview = result;
    if (!preview) preview = tool?.status === 'running' ? (typeof i18n !== 'undefined' ? i18n.t('chat_running_dots') : 'running...') : (typeof i18n !== 'undefined' ? i18n.t('chat_completed_label') : 'completed');
    return preview.length > 90 ? preview.slice(0, 87) + '...' : preview;
  }

  updateChatStackLayout();
  const primaryWindow = new ChatWindow(document.getElementById('chat-panel'), { isPrimary: true });
  const chatWindows = [primaryWindow];
  const chatWindowsByRoot = new Map([[primaryWindow.root, primaryWindow]]);
  secondaryChatPanels = Object.fromEntries(Object.keys(secondaryPanelPlaceholders).map((slot) => [slot, buildSecondaryChatPanel(Number(slot))]));
  Object.entries(secondaryChatPanels).forEach(([slot, panel]) => {
    const w = new ChatWindow(panel, { slot: Number(slot) });
    chatWindows.push(w);
    chatWindowsByRoot.set(panel, w);
  });
  window.__voChatWindows = chatWindows;

  chatWindows.forEach(w => w.loadAgentList());
  window.__voChatWindows = chatWindows;
  window.__voChatWindowsByRoot = chatWindowsByRoot;
  document.addEventListener('change', (event) => {
    const select = event.target?.closest?.('.chat-agent-select');
    if (!select) return;
    const panel = select.closest('.chat-panel');
    const windowInstance = panel ? chatWindowsByRoot.get(panel) : null;
    if (!windowInstance || windowInstance.agentSelect !== select) return;
    if (event.__voChatHandledByInstance) return;
    const opt = select.selectedOptions?.[0];
    if (!opt) return;
    windowInstance.applySelection(opt, {
      markExplicit: true,
      systemPrefix: typeof i18n !== 'undefined' ? i18n.t('chat_switched_to') : 'Switched to'
    });
  });
  syncSecondaryChatControls();

  function applyQueryAgentAssignments() {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('chatAgents');
    if (!mode) return;
    const windows = [primaryWindow, ...Object.values(secondaryChatPanels).map(panel => chatWindowsByRoot.get(panel)).filter(Boolean)];
    const allOptions = primaryWindow.agentSelect ? Array.from(primaryWindow.agentSelect.querySelectorAll('option')) : [];
    if (!allOptions.length) return;

    let assignments = [];
    if (mode === 'auto') {
      assignments = allOptions.slice(0, windows.length);
    } else {
      const requestedKeys = mode.split(',').map(s => s.trim()).filter(Boolean);
      assignments = requestedKeys.map((key) => allOptions.find(opt => opt.value === key || opt.dataset.agentId === key || opt.dataset.sessionKey === key)).filter(Boolean);
    }

    assignments.forEach((opt, index) => {
      const windowInstance = windows[index];
      if (!windowInstance || !opt) return;
      windowInstance.applySelection(opt, { markExplicit: false, systemPrefix: typeof i18n !== 'undefined' ? i18n.t('chat_loaded') : 'Loaded' });
    });
  }

  const chatBtn = document.getElementById('chat-toggle');
  const exteriorTabs = document.getElementById('chat-exterior-tabs');

  /* Position the exterior tabs bar right above the chat panel */
  let _tabsRafPending = false;
  function _positionExteriorTabs() {
    if (_tabsRafPending) return;
    _tabsRafPending = true;
    requestAnimationFrame(() => {
      _tabsRafPending = false;
      if (!exteriorTabs) return;
      const panel = primaryWindow.root;
      const rect = panel.getBoundingClientRect();
      exteriorTabs.style.bottom = (window.innerHeight - rect.top) + 'px';
      exteriorTabs.style.right = (window.innerWidth - rect.right) + 'px';
      exteriorTabs.style.width = rect.width + 'px';
    });
  }

  function setPrimaryPanelOpen(shouldOpen) {
    primaryWindow.root.classList.toggle('open', shouldOpen);
    chatBtn.classList.toggle('active', shouldOpen);
    chatBtn.style.display = shouldOpen ? 'none' : 'flex';
    if (exteriorTabs) exteriorTabs.classList.toggle('visible', shouldOpen);
    if (shouldOpen) {
      requestAnimationFrame(_positionExteriorTabs);
    }
    if (shouldOpen && !ws) connectGateway();
    if (shouldOpen) {
      primaryWindow.input.focus();
      primaryWindow.scrollBottom();
      if (connected || primaryWindow.isHermesSelected() || primaryWindow.isCodexSelected()) {
        primaryWindow.loadHistory();
        primaryWindow.fetchSessionInfo();
      }
      primaryWindow.updateFeishuEventSource();
    } else {
      primaryWindow.closeFeishuEventSource();
      closeAllSecondaryPanels();
    }
  }

  chatBtn.addEventListener('click', () => {
    setPrimaryPanelOpen(!primaryWindow.root.classList.contains('open'));
  });

  const chatUrlParams = new URLSearchParams(window.location.search);
  const chatViewParam = chatUrlParams.get('chatView');
  if (chatViewParam === 'all') {
    setTimeout(() => {
      setPrimaryPanelOpen(true);
      setSecondaryPanelOpen('1', true);
      setSecondaryPanelOpen('2', true);
      setSecondaryPanelOpen('3', true);
      setTimeout(applyQueryAgentAssignments, 400);
    }, 50);
  } else if (chatUrlParams.get('chatAgents')) {
    setTimeout(applyQueryAgentAssignments, 400);
  }

  fetch('/gateway-info').then(r => r.json()).then(d => {
    if (d.wsPort) _chatWsPort = d.wsPort;
    if (d.wsPath && d.wsPath.startsWith('/')) _chatWsPath = d.wsPath;
    if (d.token) GATEWAY_TOKEN = d.token;
    if (d.openclawVersion) GATEWAY_CLIENT_VERSION = d.openclawVersion;
  }).catch(() => {});

  // --- MOVE / SNAP SYSTEM (primary window only) ---
  const chatPanel = primaryWindow.root;
  const chatMoveBtn = document.getElementById('chat-move');
  let _chatMoveMode = false;
  let _chatDragging = false;
  let _chatDragStartX = 0, _chatDragStartY = 0;
  let _chatOrigLeft = 0, _chatOrigTop = 0;
  let _chatSnapZoneL = null, _chatSnapZoneR = null;

  function _chatCreateSnapZones() {
    if (_chatSnapZoneL) return;
    _chatSnapZoneL = document.createElement('div'); _chatSnapZoneL.className = 'chat-snap-zone left';
    _chatSnapZoneR = document.createElement('div'); _chatSnapZoneR.className = 'chat-snap-zone right';
    document.body.appendChild(_chatSnapZoneL); document.body.appendChild(_chatSnapZoneR);
  }
  function _chatRemoveSnapZones() {
    if (_chatSnapZoneL) { _chatSnapZoneL.remove(); _chatSnapZoneL = null; }
    if (_chatSnapZoneR) { _chatSnapZoneR.remove(); _chatSnapZoneR = null; }
  }
  function _getSidebarWidth() {
    var sb = document.querySelector('.sidebar'); var edge = document.querySelector('.sidebar-edge');
    if (!sb || sb.classList.contains('collapsed')) return (edge ? edge.offsetWidth : 20);
    return sb.offsetWidth + (edge ? edge.offsetWidth : 20);
  }
  function _chatEnterMoveMode() {
    _chatMoveMode = true; chatMoveBtn.classList.add('active'); chatPanel.classList.add('move-active');
    // Exit move mode for all secondary windows
    [1, 2, 3].forEach((sn) => _secExitMoveMode(sn));
    var rect = chatPanel.getBoundingClientRect();
    chatPanel.classList.remove('snap-left', 'snap-right'); chatPanel.classList.add('floating');
    chatPanel.style.left = rect.left + 'px'; chatPanel.style.top = rect.top + 'px';
    chatPanel.style.right = 'auto'; chatPanel.style.bottom = 'auto'; chatPanel.style.width = rect.width + 'px'; chatPanel.style.height = rect.height + 'px';
  }
  function _chatExitMoveMode() {
    _chatMoveMode = false; _chatDragging = false;
    if (chatMoveBtn) chatMoveBtn.classList.remove('active');
    chatPanel.classList.remove('floating', 'dragging', 'move-active');
    chatPanel.style.removeProperty('transform');
    _chatRemoveSnapZones();
    if (!chatPanel.classList.contains('snap-left') && !chatPanel.classList.contains('snap-right')) {
      chatPanel.style.left = ''; chatPanel.style.top = ''; chatPanel.style.right = ''; chatPanel.style.bottom = ''; chatPanel.style.width = ''; chatPanel.style.height = '';
    }
  }
  function _chatSnapTo(side) {
    chatPanel.classList.remove('floating', 'dragging', 'move-active');
    chatPanel.style.left = ''; chatPanel.style.right = ''; chatPanel.style.bottom = ''; chatPanel.style.width = '380px';
    var wrapper = document.querySelector('.game-wrapper');
    var wRect = wrapper ? wrapper.getBoundingClientRect() : { top: 0, height: window.innerHeight };
    chatPanel.style.top = wRect.top + 'px'; chatPanel.style.height = wRect.height + 'px';
    if (side === 'left') { chatPanel.classList.remove('snap-right'); chatPanel.classList.add('snap-left'); }
    else { chatPanel.classList.remove('snap-left'); chatPanel.classList.add('snap-right'); chatPanel.style.right = _getSidebarWidth() + 'px'; }
    _chatMoveMode = false; _chatDragging = false;
    if (chatMoveBtn) chatMoveBtn.classList.remove('active');
    _chatRemoveSnapZones();
    setTimeout(() => { _tileSecondaryPanels(); _positionExteriorTabs(); _resolveOverlaps(chatPanel); }, 50);
  }
  function _chatUpdateSnapPosition() {
    if (chatPanel.classList.contains('snap-right')) chatPanel.style.right = _getSidebarWidth() + 'px';
    if (chatPanel.classList.contains('snap-left') || chatPanel.classList.contains('snap-right')) {
      var wrapper = document.querySelector('.game-wrapper');
      var wRect = wrapper ? wrapper.getBoundingClientRect() : { top: 0, height: window.innerHeight };
      chatPanel.style.top = wRect.top + 'px'; chatPanel.style.height = wRect.height + 'px';
    }
    requestAnimationFrame(_positionExteriorTabs);
  }
  var _sidebarEdge = document.getElementById('sidebar-edge');
  if (_sidebarEdge) _sidebarEdge.addEventListener('click', () => setTimeout(() => { updateChatStackLayout(); _chatUpdateSnapPosition(); }, 350));
  window.addEventListener('resize', () => { updateChatStackLayout(); _chatUpdateSnapPosition(); _positionExteriorTabs(); });
  if (chatMoveBtn) chatMoveBtn.addEventListener('click', (e) => { e.stopPropagation(); _chatMoveMode ? _chatExitMoveMode() : _chatEnterMoveMode(); });
  const chatHeader = chatPanel.querySelector('.chat-header');
  chatHeader.addEventListener('mousedown', (e) => {
    if (!_chatMoveMode) return;
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT') return;
    e.preventDefault(); _chatDragging = true; chatPanel.classList.add('dragging');
    _chatDragStartX = e.clientX; _chatDragStartY = e.clientY;
    var rect = chatPanel.getBoundingClientRect(); _chatOrigLeft = rect.left; _chatOrigTop = rect.top; _chatCreateSnapZones();
  });
  window.addEventListener('mousemove', (e) => {
    if (!_chatDragging) return;
    var dx = e.clientX - _chatDragStartX; var dy = e.clientY - _chatDragStartY;
    chatPanel.style.left = (_chatOrigLeft + dx) + 'px'; chatPanel.style.top = (_chatOrigTop + dy) + 'px';
    _tileSecondaryPanels();
    _positionExteriorTabs();
    var sbW = _getSidebarWidth(); var rightEdge = window.innerWidth - sbW;
    if (_chatSnapZoneL) _chatSnapZoneL.classList.toggle('active', e.clientX < 80);
    if (_chatSnapZoneR) { _chatSnapZoneR.style.right = sbW + 'px'; _chatSnapZoneR.classList.toggle('active', e.clientX > rightEdge - 80); }
  });
  window.addEventListener('mouseup', (e) => {
    if (!_chatDragging) return;
    _chatDragging = false; chatPanel.classList.remove('dragging');
    var sbW = _getSidebarWidth(); var rightEdge = window.innerWidth - sbW;
    if (e.clientX < 80) _chatSnapTo('left'); else if (e.clientX > rightEdge - 80) _chatSnapTo('right');
    _chatRemoveSnapZones();
    _tileSecondaryPanels();
    _positionExteriorTabs();
    _resolveOverlaps(chatPanel);
  });

  // ─── SHARED CHAT RESIZE SYSTEM (primary + secondary, all directions) ───
  const CHAT_MIN_W = 220;
  const CHAT_MAX_W_RATIO = 0.92;
  const CHAT_MIN_H = 250;
  const CHAT_MAX_H_RATIO = 0.95;

  // Collect primary panel handles
  const _primaryHandleEls = chatPanel.querySelectorAll('.chat-resize-handle');

  /** Generic resize state — one per panel, keyed by slotId */
  const _resizeStates = {};

  /** Detect which direction class a handle element has */
  function _getHandleDir(handleEl) {
    if (handleEl.classList.contains('top-left'))     return 'topLeft';
    if (handleEl.classList.contains('top-right'))    return 'topRight';
    if (handleEl.classList.contains('bottom-left'))  return 'bottomLeft';
    if (handleEl.classList.contains('bottom-right')) return 'bottomRight';
    if (handleEl.classList.contains('top'))    return 'top';
    if (handleEl.classList.contains('bottom')) return 'bottom';
    if (handleEl.classList.contains('left'))   return 'left';
    if (handleEl.classList.contains('right'))  return 'right';
    return null;
  }

  /** Is this panel anchored via CSS `right` (default docked mode)? */
  function _isRightAnchored(panel) {
    // Floating or snapped-left panels are NOT right-anchored
    if (panel.classList.contains('floating') || panel.classList.contains('snap-left')) return false;
    // Default docked-right or snap-right panels ARE right-anchored
    return true;
  }

  /**
   * Apply a width+height resize delta to a panel, respecting min/max and
   * handling the difference between right-anchored and left/floating panels.
   *
   * @param {HTMLElement} panel — the chat-panel element
   * @param {Object} rs — resize state (startX, startY, startW, startH, startRect, dir)
   * @param {number} dx — mouse delta X (positive = moved right)
   * @param {number} dy — mouse delta Y (positive = moved down)
   */
  function _applyResizeDelta(panel, rs, dx, dy) {
    const maxW = Math.floor(window.innerWidth * CHAT_MAX_W_RATIO);
    const maxH = Math.floor(window.innerHeight * CHAT_MAX_H_RATIO);
    const dir = rs.dir;
    const rightAnchored = rs.rightAnchored;
    const { startW, startH, startRect } = rs;

    // Determine which axes this direction affects
    const movesLeft   = dir === 'left'   || dir === 'topLeft'    || dir === 'bottomLeft';
    const movesRight  = dir === 'right'  || dir === 'topRight'   || dir === 'bottomRight';
    const movesTop    = dir === 'top'    || dir === 'topLeft'    || dir === 'topRight';
    const movesBottom = dir === 'bottom' || dir === 'bottomLeft' || dir === 'bottomRight';

    // --- Horizontal resize ---
    if (movesRight) {
      if (rightAnchored) {
        // Right edge is CSS-anchored — dragging right handle means we want the LEFT side to stay,
        // but CSS right is fixed. So we just widen by moving the right anchor inward (shrink) or expand.
        // Actually in right-anchored mode, dragging right edge outward goes INTO the sidebar.
        // More intuitive: dx>0 = wider. We grow leftward by increasing width.
        const newW = Math.min(Math.max(startW + dx, CHAT_MIN_W), maxW);
        panel.style.width = newW + 'px';
      } else {
        // Floating or left-snapped: right edge expands rightward
        const newW = Math.min(Math.max(startW + dx, CHAT_MIN_W), maxW);
        panel.style.width = newW + 'px';
      }
    }

    if (movesLeft) {
      if (rightAnchored) {
        // Right-anchored: left edge resize simply changes width (right stays put)
        // dx < 0 = moved left = wider; dx > 0 = moved right = narrower
        const newW = Math.min(Math.max(startW - dx, CHAT_MIN_W), maxW);
        panel.style.width = newW + 'px';
      } else {
        // Floating/left-snap: left edge moves, right edge stays fixed
        const newW = Math.min(Math.max(startW - dx, CHAT_MIN_W), maxW);
        const widthDelta = newW - startW;
        panel.style.width = newW + 'px';
        panel.style.left = (startRect.left - widthDelta) + 'px';
      }
    }

    // --- Vertical resize ---
    if (movesTop) {
      // Top edge: dragging up = dy < 0 = taller
      const newH = Math.min(Math.max(startH - dy, CHAT_MIN_H), maxH);
      const heightDelta = newH - startH;
      panel.style.height = newH + 'px';
      // Adjust top position: for secondary panels (position:fixed with explicit top)
      // and for floating/snapped primary panels
      if (panel.classList.contains('chat-panel-secondary') ||
          panel.classList.contains('floating') || panel.classList.contains('snap-left') || panel.classList.contains('snap-right')) {
        panel.style.top = (startRect.top - heightDelta) + 'px';
      }
      // Mark secondary panels as having custom height so tiling doesn't override
      if (panel.classList.contains('chat-panel-secondary')) {
        panel.dataset.hasCustomHeight = '1';
      }
    }

    if (movesBottom) {
      // Bottom edge: dragging down = dy > 0.
      if (panel.classList.contains('chat-panel-secondary')) {
        // Secondary panels: bottom edge can grow downward (they have explicit positioning)
        const newH = Math.min(Math.max(startH + dy, CHAT_MIN_H), maxH);
        panel.style.height = newH + 'px';
        panel.dataset.hasCustomHeight = '1';
      } else if (panel.classList.contains('floating')) {
        const newH = Math.min(Math.max(startH + dy, CHAT_MIN_H), maxH);
        panel.style.height = newH + 'px';
      }
    }
  }

  function _chatResizeStart(panel, handleEl, e) {
    const dir = _getHandleDir(handleEl);
    if (!dir) return;
    e.preventDefault();
    e.stopPropagation();
    // Activate this panel so it gets highest z-index (prevents overlapping panels from blocking)
    const chatSlot = panel.dataset.chatSlot || '';
    if (chatSlot.startsWith('secondary-')) {
      const slotNum = chatSlot.replace('secondary-', '');
      if (typeof setActiveSecondarySlot === 'function') setActiveSecondarySlot(slotNum);
    }
    const rect = panel.getBoundingClientRect();
    const slotId = chatSlot || 'primary';
    _resizeStates[slotId] = {
      active: true,
      panel,
      handleEl,
      dir,
      rightAnchored: _isRightAnchored(panel),
      startX: e.type.startsWith('touch') ? e.touches[0].clientX : e.clientX,
      startY: e.type.startsWith('touch') ? e.touches[0].clientY : e.clientY,
      startW: rect.width,
      startH: rect.height,
      startRect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
    };
    panel.style.transition = 'none';
    handleEl.classList.add('dragging');
    document.body.style.userSelect = 'none';
    document.body.style.webkitUserSelect = 'none';
    // Lock cursor to resize direction for the entire drag (prevents cursor flicker
    // when mouse moves off the narrow handle zone)
    const cursorMap = {
      left: 'ew-resize', right: 'ew-resize',
      top: 'ns-resize', bottom: 'ns-resize',
      topLeft: 'nw-resize', topRight: 'ne-resize',
      bottomLeft: 'sw-resize', bottomRight: 'se-resize',
    };
    document.body.style.cursor = cursorMap[dir] || 'default';
  }

  function _chatResizeMove(e) {
    for (const slotId in _resizeStates) {
      const rs = _resizeStates[slotId];
      if (!rs || !rs.active) continue;
      const clientX = e.type.startsWith('touch') ? e.touches[0].clientX : e.clientX;
      const clientY = e.type.startsWith('touch') ? e.touches[0].clientY : e.clientY;
      const dx = clientX - rs.startX;
      const dy = clientY - rs.startY;
      _applyResizeDelta(rs.panel, rs, dx, dy);
    }
    _tileSecondaryPanels();
    _positionExteriorTabs();
  }

  function _chatResizeEnd() {
    let resizedPanels = [];
    for (const slotId in _resizeStates) {
      const rs = _resizeStates[slotId];
      if (!rs || !rs.active) continue;
      rs.active = false;
      rs.handleEl.classList.remove('dragging');
      rs.panel.style.transition = '';
      resizedPanels.push(rs.panel);
      // Scroll chat to bottom after resize
      const w = chatWindowsByRoot.get(rs.panel);
      if (w) w.scrollBottom();
    }
    document.body.style.userSelect = '';
    document.body.style.webkitUserSelect = '';
    document.body.style.cursor = '';
    // Re-tile secondary panels after any resize, then resolve overlaps
    _tileSecondaryPanels();
    _positionExteriorTabs();
    resizedPanels.forEach(p => _resolveOverlaps(p));
  }

  // Bind resize events for PRIMARY panel
  _primaryHandleEls.forEach(handle => {
    handle.addEventListener('mousedown', (e) => _chatResizeStart(chatPanel, handle, e));
    handle.addEventListener('touchstart', (e) => _chatResizeStart(chatPanel, handle, e), { passive: false });
  });

  // Bind resize events for SECONDARY panels
  [1, 2, 3].forEach((slotNum) => {
    const slotKey = String(slotNum);
    const panel = secondaryChatPanels[slotKey];
    if (!panel) return;
    const handles = panel.querySelectorAll('.chat-resize-handle');
    handles.forEach(handle => {
      handle.addEventListener('mousedown', (e) => _chatResizeStart(panel, handle, e));
      handle.addEventListener('touchstart', (e) => _chatResizeStart(panel, handle, e), { passive: false });
    });
  });

  // Global move/end listeners (shared for all panels)
  document.addEventListener('mousemove', _chatResizeMove);
  document.addEventListener('touchmove', _chatResizeMove, { passive: false });
  document.addEventListener('mouseup', _chatResizeEnd);
  document.addEventListener('touchend', _chatResizeEnd);

  // ─── OVERLAP PREVENTION SYSTEM ───
  // After any move/resize/snap, push overlapping chat windows apart.
  // Uses getBoundingClientRect() for detection (always accurate for visual position)
  // and converts pushed panels to floating with explicit left/top positioning.

  const OVERLAP_PAD = 8; // minimum gap (px) between windows

  /** Get all open, visible chat panels (primary + secondaries) */
  function _getAllOpenChatPanels() {
    const panels = [];
    if (chatPanel.classList.contains('open')) panels.push(chatPanel);
    [1, 2, 3].forEach((slotNum) => {
      const p = secondaryChatPanels[String(slotNum)];
      if (p && p.classList.contains('open')) panels.push(p);
    });
    return panels;
  }

  /**
   * Read a panel's position. For floating panels with explicit inline styles,
   * reads from style.left/top (avoids stale CSS-transform issues). Otherwise
   * falls back to getBoundingClientRect (reliable for stacked/docked panels).
   */
  function _getPanelRect(panel) {
    // Floating panels: trust inline styles as source of truth
    if (panel.classList.contains('floating')) {
      const l = parseFloat(panel.style.left);
      const t = parseFloat(panel.style.top);
      if (!isNaN(l) && !isNaN(t)) {
        const w = parseFloat(panel.style.width) || panel.offsetWidth || 300;
        const h = parseFloat(panel.style.height) || panel.offsetHeight || 500;
        return { left: l, top: t, right: l + w, bottom: t + h, width: w, height: h };
      }
    }
    // Docked/stacked panels: getBoundingClientRect reflects transforms correctly
    const r = panel.getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
  }

  /** Check if two rects overlap (accounting for minimum gap) */
  function _rectsOverlap(a, b, pad) {
    return !(a.right + pad <= b.left || b.right + pad <= a.left ||
             a.bottom + pad <= b.top || b.bottom + pad <= a.top);
  }

  /**
   * Convert a panel from stacked/docked layout to floating so we can
   * reposition it freely. Captures getBoundingClientRect BEFORE adding
   * the floating class, then applies all styles in one cssText batch
   * to avoid layout thrash.
   */
  function _convertToFloating(panel) {
    // Already floating — just make sure transform is killed
    if (panel.classList.contains('floating') || panel.classList.contains('snap-left') || panel.classList.contains('snap-right')) {
      panel.style.setProperty('transform', 'none', 'important');
      return;
    }
    // Capture current visual position (getBoundingClientRect includes CSS transforms)
    const rect = panel.getBoundingClientRect();
    // Apply floating class + all position props in one batch
    panel.classList.add('floating');
    panel.style.cssText = 'transform: none !important; left: ' + rect.left + 'px; top: ' + rect.top + 'px; right: auto; bottom: auto; width: ' + rect.width + 'px; height: ' + rect.height + 'px;';
  }

  /**
   * After a panel is moved/resized/snapped, detect and resolve overlaps
   * with all other open chat windows. The moved panel stays put;
   * overlapping neighbors get pushed out of the way.
   *
   * Algorithm: multi-pass pairwise resolution with viewport clamping.
   * On each pass, every overlapping pair is resolved by pushing the
   * non-mover in the shortest-escape direction. If a horizontal push
   * would send the panel off-screen, a vertical push is tried instead.
   * Up to 8 passes handle cascading shifts.
   */
  function _resolveOverlaps(movedPanel) {
    const allPanels = _getAllOpenChatPanels();
    if (allPanels.length < 2) return;

    // First, convert any non-floating panels to floating so we can
    // position them via style.left/top. Do this BEFORE reading rects
    // to avoid mid-loop transform issues.
    allPanels.forEach(p => {
      if (p !== movedPanel) _convertToFloating(p);
    });

    const viewW = window.innerWidth;
    const viewH = window.innerHeight;
    const sbW = _getSidebarWidth();
    const usableRight = viewW - sbW;
    const minVisible = 100;
    const maxPasses = 8;

    // Build mutable position map: panel → {left, top, width, height}
    // For the moved panel, use getBoundingClientRect (it may not be floating)
    const posMap = new Map();
    allPanels.forEach(p => {
      const r = _getPanelRect(p);
      posMap.set(p, { left: r.left, top: r.top, width: r.width, height: r.height });
    });

    function getRect(p) {
      const pos = posMap.get(p);
      return { left: pos.left, top: pos.top, right: pos.left + pos.width, bottom: pos.top + pos.height, width: pos.width, height: pos.height };
    }

    for (let pass = 0; pass < maxPasses; pass++) {
      let anyMoved = false;

      for (let i = 0; i < allPanels.length; i++) {
        for (let j = i + 1; j < allPanels.length; j++) {
          const pA = allPanels[i], pB = allPanels[j];
          const rA = getRect(pA), rB = getRect(pB);

          if (!_rectsOverlap(rA, rB, OVERLAP_PAD)) continue;

          // Decide who moves: never move the movedPanel
          let fixed, push, fR, pR;
          if (pA === movedPanel) { fixed = pA; push = pB; fR = rA; pR = rB; }
          else if (pB === movedPanel) { fixed = pB; push = pA; fR = rB; pR = rA; }
          else {
            // Neither is the moved panel — push whichever is further from mover
            const mR = getRect(movedPanel);
            const dA = Math.abs((rA.left + rA.width / 2) - (mR.left + mR.width / 2));
            const dB = Math.abs((rB.left + rB.width / 2) - (mR.left + mR.width / 2));
            if (dA >= dB) { fixed = pB; push = pA; fR = rB; pR = rA; }
            else { fixed = pA; push = pB; fR = rA; pR = rB; }
          }

          // Calculate shortest escape direction
          const overlapX = Math.min(fR.right, pR.right) - Math.max(fR.left, pR.left);
          const overlapY = Math.min(fR.bottom, pR.bottom) - Math.max(fR.top, pR.top);
          const fCX = (fR.left + fR.right) / 2, fCY = (fR.top + fR.bottom) / 2;
          const pCX = (pR.left + pR.right) / 2, pCY = (pR.top + pR.bottom) / 2;

          // Try up to 4 candidate positions (preferred direction, opposite, then other axis)
          // and pick the first that resolves the overlap while staying in viewport.
          const candidates = [];

          // Preferred axis first (shorter escape)
          if (overlapX <= overlapY) {
            // Horizontal preferred
            if (pCX >= fCX) {
              candidates.push({ l: fR.right + OVERLAP_PAD, t: pR.top });             // right
              candidates.push({ l: fR.left - pR.width - OVERLAP_PAD, t: pR.top });   // left
            } else {
              candidates.push({ l: fR.left - pR.width - OVERLAP_PAD, t: pR.top });   // left
              candidates.push({ l: fR.right + OVERLAP_PAD, t: pR.top });             // right
            }
            // Fallback: vertical
            candidates.push({ l: pR.left, t: fR.bottom + OVERLAP_PAD });             // down
            candidates.push({ l: pR.left, t: fR.top - pR.height - OVERLAP_PAD });    // up
          } else {
            // Vertical preferred
            if (pCY >= fCY) {
              candidates.push({ l: pR.left, t: fR.bottom + OVERLAP_PAD });           // down
              candidates.push({ l: pR.left, t: fR.top - pR.height - OVERLAP_PAD });  // up
            } else {
              candidates.push({ l: pR.left, t: fR.top - pR.height - OVERLAP_PAD });  // up
              candidates.push({ l: pR.left, t: fR.bottom + OVERLAP_PAD });           // down
            }
            // Fallback: horizontal
            candidates.push({ l: fR.right + OVERLAP_PAD, t: pR.top });               // right
            candidates.push({ l: fR.left - pR.width - OVERLAP_PAD, t: pR.top });     // left
          }

          // Evaluate each candidate: prefer one that doesn't overlap with ANY other panel
          let newLeft = pR.left, newTop = pR.top;
          let bestScore = -1;
          for (const c of candidates) {
            const cl = Math.max(0, Math.min(c.l, usableRight - minVisible));
            const ct = Math.max(0, Math.min(c.t, viewH - minVisible));
            const tr = { left: cl, top: ct, right: cl + pR.width, bottom: ct + pR.height };
            // Must not overlap the fixed panel
            if (_rectsOverlap(fR, tr, OVERLAP_PAD)) continue;
            // Count how many OTHER panels it would overlap (fewer = better)
            let collisions = 0;
            for (let k = 0; k < allPanels.length; k++) {
              if (allPanels[k] === push || allPanels[k] === fixed) continue;
              if (_rectsOverlap(getRect(allPanels[k]), tr, OVERLAP_PAD)) collisions++;
            }
            const score = 100 - collisions; // higher is better
            if (score > bestScore) {
              bestScore = score; newLeft = cl; newTop = ct;
              if (collisions === 0) break; // perfect placement found
            }
          }
          if (bestScore < 0) {
            // No candidate avoids the fixed panel — use first clamped as fallback
            newLeft = Math.max(0, Math.min(candidates[0].l, usableRight - minVisible));
            newTop = Math.max(0, Math.min(candidates[0].t, viewH - minVisible));
          }

          // Update the position map
          const pos = posMap.get(push);
          pos.left = newLeft;
          pos.top = newTop;
          anyMoved = true;
        }
      }
      if (!anyMoved) break;
    }

    // Apply final positions to DOM (skip the moved panel)
    allPanels.forEach(p => {
      if (p === movedPanel) return;
      const pos = posMap.get(p);
      p.style.left = pos.left + 'px';
      p.style.top = pos.top + 'px';
    });
  }

  // No-op stubs for backward compat (secondary panels no longer have independent move)
  function _secExitMoveMode() {}

  window._secExitMoveMode = _secExitMoveMode;
  window._resolveOverlaps = _resolveOverlaps;
  window._convertToFloating = _convertToFloating;
  window._getPanelRect = _getPanelRect;
})();
