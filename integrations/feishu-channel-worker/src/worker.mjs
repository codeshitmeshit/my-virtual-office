import { randomUUID } from 'node:crypto';
import { join } from 'node:path';

import { CallbackClient } from './callback.mjs';
import { CommandServer } from './command-server.mjs';
import { ChatExecutionLaneScheduler } from './execution-lanes.mjs';
import { createSafeLogger } from './logger.mjs';
import { makeInboundEnvelope, redactSecretsString } from './protocol.mjs';
import { ProcessingRecoveryCoordinator } from './recovery.mjs';
import { ResourceStore } from './resources.mjs';
import { InboundSpool, SpoolFullError } from './spool.mjs';
import { StatusStore } from './status.mjs';

export const CHANNEL_OPTIONS = {
  transport: 'websocket',
  includeRawEvent: true,
  policy: {
    dmMode: 'open',
    groupAllowlist: [],
    requireMention: true,
    respondToMentionAll: false,
    botLoopGuard: {
      enabled: true,
      windowMs: 60_000,
      maxBotMentions: 5,
      scope: 'chat',
      onTrip: 'reject',
    },
  },
  safety: {
    chatQueue: { enabled: true, mergeWhileBusy: false },
    batch: { text: { delayMs: 0, longDelayMs: 0, maxMessages: 1, maxChars: 512 * 1024 }, media: { delayMs: 0, maxItems: 1 } },
    staleMessageWindowMs: Number.MAX_SAFE_INTEGER,
    dedup: { ttl: 60000, maxEntries: 1000, sweepIntervalMs: 30000 },
  },
  keepalive: { enabled: true, intervalMs: 15000 },
  handshakeTimeoutMs: 30000,
  httpTimeoutMs: 30000,
  source: 'virtual-office',
};

function rawEvent(message) {
  return message?.raw && typeof message.raw === 'object' ? message.raw : {};
}

function nested(raw, ...paths) {
  for (const path of paths) {
    let value = raw;
    for (const part of path) value = value?.[part];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return '';
}

function normalizeMention(mention) {
  if (!mention || typeof mention !== 'object' || Array.isArray(mention)) return mention;
  const normalized = { ...mention };
  for (const field of ['id', 'key', 'openId', 'userId', 'unionId', 'name', 'isBot']) {
    if (normalized[field] === null || normalized[field] === undefined || normalized[field] === '') {
      delete normalized[field];
    }
  }
  return normalized;
}

const PROCESSING_ERROR_CATEGORIES = new Set([
  'callback_processing', 'callback_http_error', 'callback_invalid_ack',
  'callback_network_error', 'callback_timeout', 'callback_failure',
  'chat_queue_full', 'inbox_full',
]);

function processingErrorCategory(error) {
  const category = String(error?.category || error?.code || 'callback_failure');
  return PROCESSING_ERROR_CATEGORIES.has(category) ? category : 'callback_failure';
}

export function normalizeMessage(message) {
  const raw = rawEvent(message);
  const senderType = typeof message.senderType === 'string' ? message.senderType : '';
  const senderIsBot = typeof message.senderIsBot === 'boolean'
    ? message.senderIsBot
    : (senderType ? senderType === 'bot' : undefined);
  const sender = {
    primaryId: String(message.senderId || ''),
    openId: String(nested(raw, ['event', 'sender', 'sender_id', 'open_id'], ['sender', 'sender_id', 'open_id']) || (String(message.senderId || '').startsWith('ou_') ? message.senderId : '')),
    userId: String(nested(raw, ['event', 'sender', 'sender_id', 'user_id'], ['sender', 'sender_id', 'user_id']) || ''),
    unionId: String(nested(raw, ['event', 'sender', 'sender_id', 'union_id'], ['sender', 'sender_id', 'union_id']) || ''),
    name: String(message.senderName || ''),
    type: senderType,
    ...(senderIsBot === undefined ? {} : { isBot: senderIsBot }),
  };
  return {
    messageId: String(message.messageId || ''),
    chatId: String(message.chatId || ''),
    chatType: message.chatType,
    content: String(message.content || ''),
    rawContentType: String(message.rawContentType || ''),
    createTime: Number(message.createTime || 0),
    rootId: String(message.rootId || ''),
    threadId: String(message.threadId || ''),
    replyToMessageId: String(message.replyToMessageId || ''),
    mentions: Array.isArray(message.mentions)
      ? message.mentions.slice(0, 100).map(normalizeMention)
      : [],
    resources: Array.isArray(message.resources) ? message.resources.slice(0, 100) : [],
    sender,
  };
}

export class FeishuChannelWorker {
  constructor({
    appId,
    appSecret,
    statusDir,
    callbackUrl,
    callbackToken,
    parentPid = process.ppid,
    workerInstanceId = randomUUID(),
    createChannel,
    callbackClient,
    channelOptions = {},
    logger,
    maxConcurrentCallbacks = 16,
    maxPerChatQueue = 20,
    recoveryConcurrency = 4,
    processingRecoveryEnabled = true,
    processingWarningThresholdMs = 60_000,
    processingRecoveryOptions = {},
    callbackOptions = {},
  }) {
    this.appId = appId;
    this.appSecret = appSecret;
    this.statusDir = statusDir;
    this.parentPid = Number(parentPid || 0);
    this.commandToken = callbackToken;
    this.workerInstanceId = workerInstanceId;
    this.createChannel = createChannel;
    this.channelOptions = channelOptions;
    this.secrets = [appSecret, callbackToken].filter(Boolean);
    this.logger = logger || createSafeLogger({ secrets: this.secrets });
    this.maxConcurrentCallbacks = maxConcurrentCallbacks;
    this.maxPerChatQueue = maxPerChatQueue;
    this.processingWarningThresholdMs = processingWarningThresholdMs;
    this.processingSpool = { entries: 0, valid: 0, blocked: 0, bytes: 0, oldestPendingAt: 0, pressure: false, full: false };
    this.processingLastAckAt = 0;
    this.processingLastFailureAt = 0;
    this.processingLastProgressAt = 0;
    this.processingLastErrorCategory = '';
    this.processingRecoveryState = {
      active: false, nextRetryAt: 0, consecutiveFailures: 0,
    };
    this.lanePressure = false;
    this.status = new StatusStore(join(statusDir, 'feishu-chat-worker-status.json'), { workerInstanceId, parentPid: this.parentPid });
    this.spool = new InboundSpool(join(statusDir, 'feishu-channel-inbox'));
    this.callback = callbackClient || new CallbackClient({ url: callbackUrl, token: callbackToken, logger: this.logger, ...callbackOptions });
    this.channel = null;
    this.commandServer = null;
    this.running = false;
    this.lanes = new ChatExecutionLaneScheduler({
      maxConcurrent: maxConcurrentCallbacks,
      maxRecoveryConcurrent: recoveryConcurrency,
      maxPerChatQueue,
      onState: (state) => {
        if (state.pressure && !this.lanePressure) this.status.increment('counters.queuePressure').catch(() => {});
        this.lanePressure = state.pressure;
        return this.status.update({
          callback: { active: state.active },
          queue: { active: state.active, pending: state.pending, pressure: state.pressure },
        });
      },
    });
    this.processingRecovery = new ProcessingRecoveryCoordinator({
      ...processingRecoveryOptions,
      run: () => this._runRecoveryPass(),
      enabled: processingRecoveryEnabled,
      onState: (state) => {
        this.processingRecoveryState = state;
        return this._publishProcessing();
      },
    });
    this.parentTimer = null;
    this.heartbeatTimer = null;
    this.connectionRecoveryTimer = null;
  }

  async _factory(options) {
    if (this.createChannel) return this.createChannel(options);
    const { createLarkChannel } = await import('@larksuite/channel');
    return createLarkChannel(options);
  }

  _processingValue(spool = this.processingSpool) {
    const backlog = Number(spool?.valid || 0);
    const blocked = Number(spool?.blocked || 0);
    const oldestPendingAt = Number(spool?.oldestPendingAt || 0);
    const recoveryActive = Boolean(this.processingRecoveryState?.active);
    let state = 'healthy';
    if (backlog || blocked || recoveryActive) {
      const makingProgress = recoveryActive
        || (backlog > 0 && this.processingLastFailureAt === 0 && this.processingRecoveryState?.enabled)
        || (backlog > 0 && this.processingLastFailureAt === 0 && Number(this.lanes?.snapshot().active || 0) > 0)
        || this.processingLastProgressAt > this.processingLastFailureAt;
      state = makingProgress && blocked === 0 ? 'recovering' : 'degraded';
    }
    return {
      state,
      backlog,
      blocked,
      oldestPendingAt,
      lastAckAt: this.processingLastAckAt,
      lastFailureAt: this.processingLastFailureAt,
      nextRetryAt: Number(this.processingRecoveryState?.nextRetryAt || 0),
      recoveryActive,
      consecutiveFailures: Number(this.processingRecoveryState?.consecutiveFailures || 0),
      warning: Boolean((backlog || blocked) && oldestPendingAt && Date.now() - oldestPendingAt >= this.processingWarningThresholdMs),
      lastErrorCategory: this.processingLastErrorCategory,
    };
  }

  _publishProcessing(spool = this.processingSpool, extra = {}) {
    this.processingSpool = spool || this.processingSpool;
    return this.status.update({ spool: this.processingSpool, processing: this._processingValue(), ...extra });
  }

  async start() {
    if (!this.appId || !this.appSecret) {
      await this.status.update({ enabled: false, running: false, status: 'missing_app_credentials' });
      return this.status.snapshot();
    }
    await this.spool.initialize();
    await this.status.update({ running: true, status: 'starting', startedAt: Date.now(), heartbeatAt: Date.now() });
    this.channel = await this._factory({ appId: this.appId, appSecret: this.appSecret, logger: this.logger, ...CHANNEL_OPTIONS, ...this.channelOptions });
    this.channel.on({
      message: (message) => this.handleMessage(message),
      reject: (event) => this.handleReject(event),
      error: (error) => this.handleError(error),
      reconnecting: () => this.handleReconnecting(),
      reconnected: () => this.handleReconnected(),
    });
    this.commandServer = new CommandServer({
      channel: this.channel,
      token: this.commandToken || '',
      workerInstanceId: this.workerInstanceId,
      resourceStore: new ResourceStore(join(this.statusDir, 'feishu-chat-attachments')),
      logger: this.logger,
      onEvent: (event) => this.handleCommandEvent(event),
    });
    const command = await this.commandServer.start();
    await this.status.update({ command });
    this.running = true;
    this._startWatchdogs();
    const retained = await this.spool.stats();
    await this._publishProcessing(retained);
    if (retained.entries > 0) this.processingRecovery.wake();
    if (retained.full) {
      await this.status.update({ status: 'inbox_full', spool: retained });
      this._scheduleConnectionRecovery();
      return this.status.snapshot();
    }
    try {
      await this.channel.connect();
      const connection = this.channel.getConnectionStatus?.();
      await this.status.update({ status: 'connected', sdk: { connected: true, state: connection?.state || 'connected', connection }, command: { ready: true }, lastError: '' });
    } catch (error) {
      await this.status.update({
        running: true,
        status: 'reconnecting',
        reconnect: { active: true, lastAt: Date.now() },
        sdk: { connected: false, state: 'reconnecting' },
        lastError: redactSecretsString(error.message, this.secrets),
      });
      this.logger.warn('initial Feishu connection deferred', { error: error.message });
      this._scheduleConnectionRecovery();
    }
    return this.status.snapshot();
  }

  async stop(reason = 'stopped') {
    this.running = false;
    clearInterval(this.parentTimer);
    clearInterval(this.heartbeatTimer);
    clearTimeout(this.connectionRecoveryTimer);
    this.processingRecovery.stop();
    this.lanes.stop();
    await this.channel?.disconnect?.().catch((error) => this.logger.warn('channel disconnect failed', { error: error.message }));
    await this.commandServer?.stop().catch((error) => this.logger.warn('command server stop failed', { error: error.message }));
    await this.status.update({ enabled: false, running: false, status: reason, sdk: { connected: false, state: reason } });
    return this.status.snapshot();
  }

  _startWatchdogs() {
    this.heartbeatTimer = setInterval(() => this.status.update({ heartbeatAt: Date.now() }).catch(() => {}), 5000);
    this.heartbeatTimer.unref?.();
    this.parentTimer = setInterval(() => {
      if (!this.parentPid || this.parentPid === process.pid) return;
      try {
        process.kill(this.parentPid, 0);
      } catch {
        this.stop('orphaned_parent_exited').finally(() => process.exitCode = 0);
      }
    }, 3000);
    this.parentTimer.unref?.();
  }

  async handleMessage(message) {
    const normalized = normalizeMessage(message);
    const envelope = makeInboundEnvelope(normalized, {
      workerInstanceId: this.workerInstanceId,
      source: { eventId: nested(rawEvent(message), ['header', 'event_id']), tenantKey: nested(rawEvent(message), ['header', 'tenant_key']) },
    });
    try {
      const spoolState = await this.spool.put(envelope);
      await this.status.increment('counters.received');
      await this.status.increment('counters.spooled', spoolState.duplicate ? 0 : 1);
      await this._publishProcessing(spoolState, { lastEventAt: Date.now() });
      const snapshot = await this.spool.snapshot();
      const head = snapshot.items.find((item) => item.envelope?.message?.chatId === normalized.chatId);
      if (!head || head.envelope.message.messageId !== normalized.messageId) {
        if (!this.processingRecovery.snapshot().enabled && head) {
          return await this._drainLiveThrough(normalized.chatId, normalized.messageId);
        }
        this.processingRecovery.wake();
        return { durable: false, state: 'queued', messageId: normalized.messageId };
      }
      const ack = await this._attemptItem(head, 'live');
      if ((await this.spool.stats()).entries > 0) this.processingRecovery.wake();
      return ack;
    } catch (error) {
      if (error instanceof SpoolFullError) {
        await this.status.increment('counters.spoolFull');
        await this.status.update({ status: 'inbox_full', spool: { full: true }, lastError: redactSecretsString(error.message, this.secrets) });
        await this.channel?.disconnect?.().catch(() => {});
        this.processingRecovery.wake();
        this._scheduleConnectionRecovery();
      } else if (error?.code === 'chat_queue_full') {
        await this.status.increment('counters.queueRejected');
        await this.status.update({ status: 'queue_pressure', queue: { pressure: true }, lastError: error.message });
      } else {
        this.processingRecovery.wake({ delayMs: Number(error?.retryAfterMs || 0) });
      }
      throw error;
    }
  }

  _scheduleConnectionRecovery(delayMs = 1000) {
    if (this.connectionRecoveryTimer) return;
    this.connectionRecoveryTimer = setTimeout(async () => {
      this.connectionRecoveryTimer = null;
      try {
        if (await this._recoverConnection()) return;
      } catch (error) {
        this.logger.warn('Feishu connection recovery deferred', { error: error.message });
        await this.status.update({
          status: 'reconnecting',
          reconnect: { active: true, lastAt: Date.now() },
          sdk: { connected: false, state: 'reconnecting' },
          lastError: redactSecretsString(error.message, this.secrets),
        }).catch(() => {});
      }
      if (this.running) this._scheduleConnectionRecovery(Math.min(delayMs * 2, 30000));
    }, delayMs);
    this.connectionRecoveryTimer.unref?.();
  }

  async _recoverConnection() {
    const spool = await this.spool.stats();
    if (spool.full || !this.running) return false;
    await this.channel?.connect?.();
    const connection = this.channel?.getConnectionStatus?.();
    await this.status.update({
      running: true,
      status: 'connected',
      reconnect: { active: false },
      spool,
      sdk: { connected: true, state: connection?.state || 'connected', connection },
      lastError: '',
    });
    return true;
  }

  async replay() {
    return this._runRecoveryPass();
  }

  async _drainLiveThrough(chatId, targetMessageId) {
    while (this.running) {
      const snapshot = await this.spool.snapshot();
      const head = snapshot.items.find((item) => item.envelope?.message?.chatId === chatId);
      if (!head) return { durable: false, state: 'queued', messageId: targetMessageId };
      const ack = await this._attemptItem(head, 'live');
      if (head.envelope.message.messageId === targetMessageId) return ack;
    }
    return { durable: false, state: 'queued', messageId: targetMessageId };
  }

  _attemptItem(item, mode) {
    const { envelope } = item;
    return this.lanes.submit({
      chatId: envelope.message.chatId,
      messageId: envelope.message.messageId,
      mode,
      order: [Number(envelope.message.createTime || 0), Number(envelope.receivedAt || 0), envelope.message.messageId],
      execute: async () => {
        try {
          const ack = await this.callback.deliverOnce(envelope);
          const remaining = await this.spool.remove(envelope.message.messageId);
          const acknowledgedAt = Date.now();
          this.processingLastAckAt = acknowledgedAt;
          this.processingLastProgressAt = acknowledgedAt;
          if (remaining.entries === 0) this.processingLastErrorCategory = '';
          await this.status.increment('counters.callbackAcknowledged');
          if (mode === 'recovery') {
            await this.status.increment('spool.replayed');
            await this.status.increment('counters.replayed');
          }
          await this._publishProcessing(remaining);
          return ack;
        } catch (error) {
          this.processingLastFailureAt = Date.now();
          this.processingLastErrorCategory = processingErrorCategory(error);
          await this.status.increment('callback.failures');
          await this._publishProcessing(this.processingSpool, {
            callback: { lastFailureAt: Date.now() },
          });
          throw error;
        }
      },
    });
  }

  async _runRecoveryPass() {
    if (!this.running) return { pending: false, progress: false, failed: false, retryAfterMs: 0 };
    const snapshot = await this.spool.snapshot();
    const heads = new Map();
    for (const item of snapshot.items) {
      const chatId = item.envelope?.message?.chatId;
      if (chatId && !heads.has(chatId)) heads.set(chatId, item);
    }
    const attempts = await Promise.allSettled(
      [...heads.values()].map((item) => this._attemptItem(item, 'recovery')),
    );
    let progress = false;
    let failed = snapshot.blocked > 0;
    let retryAfterMs = 0;
    attempts.forEach((result, index) => {
      if (result.status === 'fulfilled') progress = true;
      else {
        failed = true;
        retryAfterMs = Math.max(retryAfterMs, Number(result.reason?.retryAfterMs || 0));
        if (this.running) {
          this.logger.warn('spool replay deferred', {
            messageId: [...heads.values()][index]?.envelope?.message?.messageId,
            category: result.reason?.category || result.reason?.code || 'callback_failure',
          });
        }
      }
    });
    const remaining = await this.spool.stats();
    await this._publishProcessing(remaining);
    return { pending: remaining.entries > 0, progress, failed, retryAfterMs };
  }

  async handleReject(event) {
    const allowedReasons = new Set([
      'group_not_allowed', 'sender_not_allowed', 'no_mention', 'dm_disabled',
      'mention_all_blocked', 'bot_loop',
    ]);
    const reason = allowedReasons.has(String(event?.reason || '')) ? String(event.reason) : 'unknown';
    await this.status.increment('counters.policyRejected');
    await this.status.increment(`counters.policyRejectedByReason.${reason}`);
    this.logger.info('Feishu message rejected by SDK policy', { messageId: String(event?.messageId || ''), reason });
  }

  async handleError(error) {
    await this.status.update({ lastError: redactSecretsString(error?.message || String(error), this.secrets) });
    this.logger.error('Feishu channel error', { error: error?.message || String(error) });
  }

  async handleReconnecting() {
    await this.status.increment('reconnect.count');
    await this.status.update({ status: 'reconnecting', reconnect: { active: true, lastAt: Date.now() }, sdk: { connected: false, state: 'reconnecting' } });
  }

  async handleReconnected() {
    await this.status.update({ status: 'connected', reconnect: { active: false }, sdk: { connected: true, state: 'connected' }, lastError: '' });
    this.processingRecovery.wake();
  }

  async handleCommandEvent(event) {
    if (event.type === 'authentication_failure') {
      await this.status.increment('counters.authenticationFailure');
      return;
    }
    if (event.type === 'command_success') {
      await this.status.increment(`counters.outboundSuccess.${event.operation}`);
      return;
    }
    if (event.type === 'command_failure') {
      await this.status.increment(`counters.outboundFailure.${event.category || 'unknown'}`);
      await this.status.increment('command.failures');
      if (String(event.category || '').includes('resource')) await this.status.increment('counters.resourceRejected');
      await this.status.update({ command: { lastFailureAt: Date.now() } });
    }
  }
}
