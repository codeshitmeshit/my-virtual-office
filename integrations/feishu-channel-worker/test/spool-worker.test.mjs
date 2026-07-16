import assert from 'node:assert/strict';
import { mkdtemp, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { ACK_SCHEMA, makeInboundEnvelope } from '../src/protocol.mjs';
import { InboundSpool, SpoolFullError } from '../src/spool.mjs';
import { CHANNEL_OPTIONS, FeishuChannelWorker, normalizeMessage } from '../src/worker.mjs';
import {
  CallbackAttemptError,
  CallbackClient,
  DEFAULT_SINGLE_ATTEMPT_TIMEOUT_MS,
  MAX_SINGLE_ATTEMPT_TIMEOUT_MS,
} from '../src/callback.mjs';

function message(id = 'om_1', chatId = 'oc_1') {
  return {
    messageId: id, chatId, chatType: 'p2p', senderId: 'ou_primary', senderName: 'Alice', senderType: 'user',
    content: 'hello', rawContentType: 'text', resources: [], mentions: [], createTime: Date.now(),
    rootId: 'om_root', threadId: 'omt_thread', replyToMessageId: 'om_reply',
    raw: { event: { sender: { sender_id: { open_id: 'ou_open', user_id: 'u_user', union_id: 'on_union' } } } },
  };
}

function envelope(id = 'om_1') {
  return makeInboundEnvelope(normalizeMessage(message(id)), { workerInstanceId: 'worker-test' });
}

test('worker SDK options preserve one-message semantics and VO-owned stale decisions', () => {
  assert.equal(CHANNEL_OPTIONS.transport, 'websocket');
  assert.equal(CHANNEL_OPTIONS.policy.dmMode, 'open');
  assert.deepEqual(CHANNEL_OPTIONS.policy.groupAllowlist, []);
  assert.equal(CHANNEL_OPTIONS.policy.requireMention, true);
  assert.equal(CHANNEL_OPTIONS.policy.respondToMentionAll, false);
  assert.deepEqual(CHANNEL_OPTIONS.policy.botLoopGuard, {
    enabled: true, windowMs: 60_000, maxBotMentions: 5, scope: 'chat', onTrip: 'reject',
  });
  assert.equal(CHANNEL_OPTIONS.safety.chatQueue.mergeWhileBusy, false);
  assert.equal(CHANNEL_OPTIONS.safety.batch.text.delayMs, 0);
  assert.equal(CHANNEL_OPTIONS.safety.batch.text.maxMessages, 1);
  assert.equal(CHANNEL_OPTIONS.safety.staleMessageWindowMs, Number.MAX_SAFE_INTEGER);
  assert.equal(CHANNEL_OPTIONS.keepalive.enabled, true);
});

test('worker accepts SDK-approved group mentions and counts policy rejects without message content', async () => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-worker-group-policy-'));
  const handlers = {};
  const deliveries = [];
  const logs = [];
  const logger = {
    info(label, context) { logs.push({ label, context }); },
    warn() {}, error() {}, debug() {},
  };
  const channel = {
    on(map) { Object.assign(handlers, map); },
    async connect() {}, async disconnect() {},
    getConnectionStatus() { return { state: 'connected' }; },
  };
  const worker = new FeishuChannelWorker({
    appId: 'cli_test', appSecret: 'secret', statusDir, callbackUrl: 'http://127.0.0.1', callbackToken: 'token',
    workerInstanceId: 'worker-group-policy', parentPid: process.pid, createChannel: () => channel, logger,
    callbackClient: {
      async deliver(input) {
        deliveries.push(input);
        return { schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId, durable: true, state: 'completed' };
      },
    },
  });
  await worker.start();

  await handlers.message({
    ...message('om_group_mention', 'oc_trusted'),
    chatType: 'group',
    content: 'approved group prompt',
    mentions: [{ openId: 'ou_bot', name: 'VO', isBot: true }],
  });
  await handlers.reject({ messageId: 'om_no_mention', reason: 'no_mention', content: 'must-not-log-no-mention' });
  await handlers.reject({ messageId: 'om_mention_all', reason: 'mention_all_blocked', content: 'must-not-log-mention-all' });
  await handlers.reject({ messageId: 'om_bot_loop', reason: 'bot_loop', content: 'must-not-log-bot-loop' });
  await handlers.reject({ messageId: 'om_unknown', reason: 'future_reason', content: 'must-not-log-unknown' });

  assert.equal(deliveries.length, 1);
  assert.equal(deliveries[0].message.chatType, 'group');
  assert.equal(deliveries[0].message.mentions[0].isBot, true);
  const counters = worker.status.snapshot().counters;
  assert.equal(counters.policyRejected, 4);
  assert.deepEqual(counters.policyRejectedByReason, {
    no_mention: 1, mention_all_blocked: 1, bot_loop: 1, unknown: 1,
  });
  assert.deepEqual(logs.map((entry) => entry.context.reason), [
    'no_mention', 'mention_all_blocked', 'bot_loop', 'unknown',
  ]);
  const renderedLogs = JSON.stringify(logs);
  assert.equal(renderedLogs.includes('must-not-log'), false);
  await worker.stop();
});

test('normalization preserves identity, thread, reply, and resource fields', () => {
  const normalized = normalizeMessage({
    ...message(),
    resources: [{ type: 'image', fileKey: 'img_1' }],
    mentions: [{ key: '@_user_1', openId: 'ou_bot', name: 'VO', isBot: true }],
  });
  assert.deepEqual(normalized.sender, { primaryId: 'ou_primary', openId: 'ou_open', userId: 'u_user', unionId: 'on_union', name: 'Alice', type: 'user', isBot: false });
  assert.deepEqual(normalized.mentions, [{ key: '@_user_1', openId: 'ou_bot', name: 'VO', isBot: true }]);
  assert.equal(normalized.rootId, 'om_root');
  assert.equal(normalized.threadId, 'omt_thread');
  assert.equal(normalized.replyToMessageId, 'om_reply');
  assert.equal(normalized.resources[0].fileKey, 'img_1');
  const unknown = normalizeMessage({ ...message(), senderType: undefined, senderIsBot: undefined });
  assert.equal(Object.hasOwn(unknown.sender, 'isBot'), false);
});

test('normalization removes null optional mention identities from real group events', () => {
  const normalized = normalizeMessage({
    ...message('om_group_real', 'oc_group_real'),
    chatType: 'group',
    mentions: [{
      key: '@_user_1',
      openId: 'ou_bot',
      userId: null,
      unionId: null,
      name: 'VO',
      isBot: true,
    }],
  });

  assert.deepEqual(normalized.mentions, [{
    key: '@_user_1',
    openId: 'ou_bot',
    name: 'VO',
    isBot: true,
  }]);
  assert.doesNotThrow(() => makeInboundEnvelope(normalized, { workerInstanceId: 'worker-real-group' }));
});

test('spool is atomic, mode 0600, duplicate-safe, pressure-aware, and bounded', async () => {
  const root = await mkdtemp(join(tmpdir(), 'vo-feishu-spool-'));
  const spool = new InboundSpool(root, { maxEntries: 2, maxBytes: 2 * 1024 * 1024 });
  const first = await spool.put(envelope('om_1'));
  const duplicate = await spool.put(envelope('om_1'));
  assert.equal(first.duplicate, false);
  assert.equal(duplicate.duplicate, true);
  assert.equal((await stat(spool.pathFor('om_1'))).mode & 0o777, 0o600);
  await spool.put(envelope('om_2'));
  await assert.rejects(() => spool.put(envelope('om_3')), (error) => error instanceof SpoolFullError);
  assert.equal((await spool.stats()).full, true);
  await spool.remove('om_1');
  assert.equal((await spool.stats()).entries, 1);
});

test('spool snapshot orders source messages and retains blocked entries with bounded stats', async () => {
  const root = await mkdtemp(join(tmpdir(), 'vo-feishu-spool-snapshot-'));
  const spool = new InboundSpool(root, { maxEntries: 4, maxBytes: 2 * 1024 * 1024 });
  const newer = envelope('om_a_newer');
  newer.message.createTime = 1710000003;
  newer.receivedAt = 1710000004000;
  const sameTimeZ = envelope('om_z_tie');
  sameTimeZ.message.createTime = 1710000001;
  sameTimeZ.receivedAt = 1710000002000;
  const sameTimeA = envelope('om_a_tie');
  sameTimeA.message.createTime = 1710000001;
  sameTimeA.receivedAt = 1710000002000;

  await spool.put(newer);
  await spool.put(sameTimeZ);
  await spool.put(sameTimeA);
  await writeFile(join(root, 'corrupt.json'), '{not-json', { mode: 0o600 });

  const snapshot = await spool.snapshot();
  assert.deepEqual(
    snapshot.items.filter((item) => item.envelope).map((item) => item.envelope.message.messageId),
    ['om_a_tie', 'om_z_tie', 'om_a_newer'],
  );
  assert.equal(snapshot.entries, 4);
  assert.equal(snapshot.valid, 3);
  assert.equal(snapshot.blocked, 1);
  assert.equal(snapshot.oldestPendingAt, 1710000001000);
  assert.equal(snapshot.pressure, true);
  assert.equal(snapshot.full, true);
  assert.equal(snapshot.items.at(-1).path, join(root, 'corrupt.json'));
  assert.ok(snapshot.items.at(-1).error instanceof Error);
  const statsOnly = await spool.stats();
  assert.equal(Object.hasOwn(statsOnly, 'items'), false);
  assert.deepEqual(await spool.list(), snapshot.items, 'list should expose the same deterministic snapshot order');
});

test('worker delivers durable callbacks, deletes acknowledged spool, and replays after restart', async () => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-worker-'));
  const handlers = {};
  const channel = {
    on(map) { Object.assign(handlers, map); },
    async connect() {}, async disconnect() {},
    getConnectionStatus() { return { state: 'connected' }; },
  };
  const deliveries = [];
  const callbackClient = {
    async deliver(input) {
      deliveries.push(input.message.messageId);
      return { schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId, durable: true, state: 'completed' };
    },
  };
  const worker = new FeishuChannelWorker({
    appId: 'cli_test', appSecret: 'secret', statusDir, callbackUrl: 'http://127.0.0.1', callbackToken: 'token',
    workerInstanceId: 'worker-test', parentPid: process.pid, createChannel: () => channel, callbackClient,
  });
  await worker.start();
  await handlers.message(message('om_live'));
  assert.deepEqual(deliveries, ['om_live']);
  assert.equal((await worker.spool.stats()).entries, 0);
  await worker.spool.put(envelope('om_replay'));
  await worker.replay();
  assert.deepEqual(deliveries, ['om_live', 'om_replay']);
  assert.equal((await worker.spool.stats()).entries, 0);
  await worker.stop();
});

test('worker keeps running and reconnects after a transient startup network failure', async () => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-worker-startup-recovery-'));
  const handlers = {};
  let connectAttempts = 0;
  let factoryOptions;
  const channel = {
    on(map) { Object.assign(handlers, map); },
    async connect() {
      connectAttempts += 1;
      if (connectAttempts === 1) throw new Error('getaddrinfo ENOTFOUND open.feishu.cn');
    },
    async disconnect() {},
    getConnectionStatus() { return { state: connectAttempts > 1 ? 'connected' : 'failed' }; },
  };
  const worker = new FeishuChannelWorker({
    appId: 'cli_test', appSecret: 'secret', statusDir, callbackUrl: 'http://127.0.0.1', callbackToken: 'token',
    workerInstanceId: 'worker-recovery-test', parentPid: process.pid, createChannel: (options) => { factoryOptions = options; return channel; },
  });

  const starting = await worker.start();
  assert.equal(factoryOptions.logger, worker.logger);
  assert.equal(starting.running, true);
  assert.equal(starting.status, 'reconnecting');
  assert.equal(connectAttempts, 1);

  clearTimeout(worker.recoveryTimer);
  worker.recoveryTimer = null;
  assert.equal(await worker._recoverConnection(), true);
  const recovered = worker.status.snapshot();
  assert.equal(recovered.status, 'connected');
  assert.equal(recovered.sdk.connected, true);
  assert.equal(connectAttempts, 2);
  await worker.stop();
});

test('callback failure retains the spooled envelope for restart recovery', async () => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-worker-fail-'));
  const channel = { on() {}, async connect() {}, async disconnect() {}, getConnectionStatus() { return { state: 'connected' }; } };
  const worker = new FeishuChannelWorker({
    appId: 'cli_test', appSecret: 'secret', statusDir, callbackUrl: 'http://127.0.0.1', callbackToken: 'token',
    workerInstanceId: 'worker-test', parentPid: process.pid, createChannel: () => channel,
    callbackClient: { async deliver() { throw Object.assign(new Error('offline'), { code: 'callback_failed' }); } },
  });
  await worker.start();
  await assert.rejects(() => worker.handleMessage(message('om_pending')), /offline/);
  assert.equal((await worker.spool.stats()).entries, 1);
  assert.equal(worker.status.snapshot().status, 'callback_failure');
  await worker.stop();
});

test('callback timeout is capped at 15 minutes', () => {
  assert.equal(new CallbackClient({ timeoutMs: 99999999 }).timeoutMs, 900000);
  assert.equal(new CallbackClient().singleAttemptTimeoutMs, DEFAULT_SINGLE_ATTEMPT_TIMEOUT_MS);
  assert.equal(new CallbackClient({ singleAttemptTimeoutMs: 99999999 }).singleAttemptTimeoutMs, MAX_SINGLE_ATTEMPT_TIMEOUT_MS);
});

test('single callback attempt classifies terminal, processing, HTTP, invalid, network, and timeout outcomes', async () => {
  const input = envelope('om_callback_once');
  const response = (status, body) => ({ ok: status >= 200 && status < 300, status, async json() { return body; } });
  const terminal = new CallbackClient({
    fetchImpl: async () => response(200, {
      schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId,
      durable: true, state: 'completed',
    }),
  });
  assert.equal((await terminal.deliverOnce(input)).state, 'completed');

  const cases = [
    {
      category: 'callback_processing',
      client: new CallbackClient({ fetchImpl: async () => response(202, {
        schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId,
        durable: false, state: 'processing', retryAfterMs: 2500,
      }) }),
      check: (error) => error.retryAfterMs === 2500,
    },
    {
      category: 'callback_http_error',
      client: new CallbackClient({ fetchImpl: async () => response(503, { error: 'unavailable' }) }),
      check: (error) => error.status === 503,
    },
    {
      category: 'callback_invalid_ack',
      client: new CallbackClient({ fetchImpl: async () => response(200, { schema: ACK_SCHEMA, requestId: 'wrong', durable: true }) }),
    },
    {
      category: 'callback_network_error',
      client: new CallbackClient({ fetchImpl: async () => { throw new Error('connection refused'); } }),
    },
    {
      category: 'callback_timeout',
      client: new CallbackClient({
        singleAttemptTimeoutMs: 5,
        fetchImpl: async (_url, options) => new Promise((resolve, reject) => {
          options.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })), { once: true });
        }),
      }),
    },
  ];
  for (const item of cases) {
    await assert.rejects(
      () => item.client.deliverOnce(input),
      (error) => error instanceof CallbackAttemptError
        && error.category === item.category
        && (!item.check || item.check(error)),
    );
  }
});

test('legacy callback delivery keeps bounded multi-attempt behavior', async () => {
  const input = envelope('om_callback_legacy');
  let attempts = 0;
  const client = new CallbackClient({
    maxAttempts: 2,
    baseDelayMs: 0,
    fetchImpl: async () => {
      attempts += 1;
      if (attempts === 1) throw new Error('temporary offline');
      return {
        ok: true, status: 200,
        async json() {
          return { schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId, durable: true, state: 'completed' };
        },
      };
    },
  });
  assert.equal((await client.deliver(input)).state, 'completed');
  assert.equal(attempts, 2);
});

test('worker bounds global callback concurrency and per-chat queue depth', async () => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-worker-capacity-'));
  const releases = [];
  let active = 0;
  let maximum = 0;
  const callbackClient = {
    async deliver(input) {
      active += 1;
      maximum = Math.max(maximum, active);
      await new Promise((resolve) => releases.push(resolve));
      active -= 1;
      return { schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId, durable: true, state: 'completed' };
    },
  };
  const worker = new FeishuChannelWorker({
    appId: 'cli_test', appSecret: 'secret', statusDir, callbackUrl: 'http://127.0.0.1', callbackToken: 'token',
    workerInstanceId: 'worker-capacity', parentPid: process.pid, callbackClient,
    createChannel: () => ({ on() {}, async connect() {}, async disconnect() {}, getConnectionStatus() { return { state: 'connected' }; } }),
  });
  const tasks = Array.from({ length: 18 }, (_, index) => worker.handleMessage(message(`om_capacity_${index}`, `oc_${index}`)));
  while (releases.length < 16) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(worker.activeCallbacks, 16);
  assert.equal(worker.waiters.length, 2);
  while (tasks.some(Boolean) && releases.length) releases.shift()();
  while (worker.waiters.length || worker.activeCallbacks) {
    while (releases.length) releases.shift()();
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  await Promise.all(tasks);
  assert.equal(maximum, 16);

  const held = [];
  worker.callback = {
    async deliver(input) {
      await new Promise((resolve) => held.push(resolve));
      return { schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId, durable: true, state: 'completed' };
    },
  };
  const sameChat = Array.from({ length: 20 }, (_, index) => worker.handleMessage(message(`om_same_${index}`, 'oc_same')));
  await assert.rejects(worker.handleMessage(message('om_same_20', 'oc_same')), (error) => error.code === 'chat_queue_full');
  while (held.length < 16) await new Promise((resolve) => setTimeout(resolve, 5));
  while (worker.waiters.length || worker.activeCallbacks) {
    while (held.length) held.shift()();
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  await Promise.all(sameChat);
  worker.spool.maxEntries = 0;
  await assert.rejects(worker.handleMessage(message('om_spool_full', 'oc_spool_full')), (error) => error instanceof SpoolFullError);
  clearTimeout(worker.recoveryTimer);
  worker.recoveryTimer = null;
  const counters = worker.status.snapshot().counters;
  assert.ok(counters.queuePressure >= 2);
  assert.equal(counters.queueRejected, 1);
  assert.equal(counters.spoolFull, 1);
});
