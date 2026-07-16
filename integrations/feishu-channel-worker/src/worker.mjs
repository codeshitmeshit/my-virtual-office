import { randomUUID } from 'node:crypto';
import { join } from 'node:path';

import { CallbackClient } from './callback.mjs';
import { CommandServer } from './command-server.mjs';
import { createSafeLogger } from './logger.mjs';
import { makeInboundEnvelope, redactSecretsString } from './protocol.mjs';
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
    mentions: Array.isArray(message.mentions) ? message.mentions.slice(0, 100) : [],
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
    this.status = new StatusStore(join(statusDir, 'feishu-chat-worker-status.json'), { workerInstanceId, parentPid: this.parentPid });
    this.spool = new InboundSpool(join(statusDir, 'feishu-channel-inbox'));
    this.callback = callbackClient || new CallbackClient({ url: callbackUrl, token: callbackToken, logger: this.logger });
    this.channel = null;
    this.commandServer = null;
    this.running = false;
    this.activeCallbacks = 0;
    this.waiters = [];
    this.chatDepth = new Map();
    this.parentTimer = null;
    this.heartbeatTimer = null;
    this.recoveryTimer = null;
  }

  async _factory(options) {
    if (this.createChannel) return this.createChannel(options);
    const { createLarkChannel } = await import('@larksuite/channel');
    return createLarkChannel(options);
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
    await this.replay();
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
      this._scheduleRecovery();
    }
    return this.status.snapshot();
  }

  async stop(reason = 'stopped') {
    this.running = false;
    clearInterval(this.parentTimer);
    clearInterval(this.heartbeatTimer);
    clearTimeout(this.recoveryTimer);
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

  async _acquire(chatId) {
    const depth = Number(this.chatDepth.get(chatId) || 0) + 1;
    this.chatDepth.set(chatId, depth);
    if (depth > this.maxPerChatQueue) {
      this.chatDepth.set(chatId, depth - 1);
      throw Object.assign(new Error('per-chat queue is full'), { code: 'chat_queue_full' });
    }
    if (this.activeCallbacks >= this.maxConcurrentCallbacks) {
      this.status.increment('counters.queuePressure').catch(() => {});
      await new Promise((resolve) => this.waiters.push(resolve));
    }
    this.activeCallbacks += 1;
    await this.status.update({ callback: { active: this.activeCallbacks }, queue: { active: this.activeCallbacks, pending: this.waiters.length, pressure: this.waiters.length > 0 } });
  }

  async _release(chatId) {
    this.activeCallbacks = Math.max(0, this.activeCallbacks - 1);
    this.chatDepth.set(chatId, Math.max(0, Number(this.chatDepth.get(chatId) || 1) - 1));
    this.waiters.shift()?.();
    await this.status.update({ callback: { active: this.activeCallbacks }, queue: { active: this.activeCallbacks, pending: this.waiters.length, pressure: this.waiters.length > 0 } });
  }

  async handleMessage(message) {
    const normalized = normalizeMessage(message);
    const envelope = makeInboundEnvelope(normalized, {
      workerInstanceId: this.workerInstanceId,
      source: { eventId: nested(rawEvent(message), ['header', 'event_id']), tenantKey: nested(rawEvent(message), ['header', 'tenant_key']) },
    });
    let acquired = false;
    try {
      const spoolState = await this.spool.put(envelope);
      await this.status.increment('counters.received');
      await this.status.increment('counters.spooled', spoolState.duplicate ? 0 : 1);
      await this.status.update({ lastEventAt: Date.now(), spool: spoolState });
      await this._acquire(normalized.chatId);
      acquired = true;
      const ack = await this.callback.deliver(envelope);
      const remaining = await this.spool.remove(normalized.messageId);
      await this.status.increment('counters.callbackAcknowledged');
      await this.status.update({ status: 'connected', spool: remaining, lastError: '' });
      return ack;
    } catch (error) {
      if (error instanceof SpoolFullError) {
        await this.status.increment('counters.spoolFull');
        await this.status.update({ status: 'inbox_full', spool: { full: true }, lastError: redactSecretsString(error.message, this.secrets) });
        await this.channel?.disconnect?.().catch(() => {});
        this._scheduleRecovery();
      } else if (error?.code === 'chat_queue_full') {
        await this.status.increment('counters.queueRejected');
        await this.status.update({ status: 'queue_pressure', queue: { pressure: true }, lastError: error.message });
      } else {
        await this.status.increment('callback.failures');
        await this.status.update({ status: 'callback_failure', callback: { lastFailureAt: Date.now() }, lastError: redactSecretsString(error.message, this.secrets) });
      }
      throw error;
    } finally {
      if (acquired) await this._release(normalized.chatId);
    }
  }

  _scheduleRecovery(delayMs = 1000) {
    if (this.recoveryTimer) return;
    this.recoveryTimer = setTimeout(async () => {
      this.recoveryTimer = null;
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
      if (this.running) this._scheduleRecovery(Math.min(delayMs * 2, 30000));
    }, delayMs);
    this.recoveryTimer.unref?.();
  }

  async _recoverConnection() {
    await this.replay();
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
    const entries = await this.spool.list();
    for (const item of entries) {
      if (item.error) continue;
      try {
        await this.callback.deliver(item.envelope);
        await this.spool.remove(item.envelope.message.messageId);
        await this.status.increment('spool.replayed');
        await this.status.increment('counters.replayed');
      } catch (error) {
        this.logger.warn('spool replay deferred', { messageId: item.envelope.message.messageId, error: error.message });
      }
    }
    await this.status.update({ spool: await this.spool.stats() });
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
