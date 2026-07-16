import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { CallbackAttemptError, CallbackClient } from '../src/callback.mjs';
import { ACK_SCHEMA, makeInboundEnvelope } from '../src/protocol.mjs';
import { FeishuChannelWorker, normalizeMessage } from '../src/worker.mjs';

function message(id, chatId = 'oc_fault', createTime = Date.now()) {
  return {
    messageId: id, chatId, chatType: 'p2p', senderId: 'ou_fault', senderName: 'Fault Test', senderType: 'user',
    content: `fault-${id}`, rawContentType: 'text', resources: [], mentions: [], createTime,
    rootId: '', threadId: '', replyToMessageId: '', raw: {},
  };
}

function envelope(id, chatId = 'oc_fault', createTime = Date.now()) {
  return makeInboundEnvelope(normalizeMessage(message(id, chatId, createTime)), { workerInstanceId: 'fault-fixture' });
}

function terminal(input) {
  return { schema: ACK_SCHEMA, requestId: input.requestId, messageId: input.message.messageId, durable: true, state: 'completed' };
}

function channel(counter = { connects: 0 }) {
  return {
    on() {}, async connect() { counter.connects += 1; }, async disconnect() {},
    getConnectionStatus() { return { state: 'connected' }; },
  };
}

function workerOptions(statusDir, callbackClient, overrides = {}) {
  return {
    appId: 'cli_fault', appSecret: 'secret', callbackUrl: 'http://127.0.0.1/fault', callbackToken: 'token',
    statusDir, workerInstanceId: `worker-${Math.random()}`, parentPid: process.pid,
    createChannel: () => channel(overrides.connectionCounter), callbackClient,
    processingRecoveryOptions: { baseDelayMs: 5, maxDelayMs: 10, jitterMs: 0 },
    ...overrides,
  };
}

async function waitUntil(predicate, timeoutMs = 1_500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail('fault-injection condition timed out');
}

test('accepted-but-unresponsive callback times out and recovers without socket reconnect or a new event', async (t) => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-fault-timeout-'));
  let unavailable = true;
  let attempts = 0;
  const connectionCounter = { connects: 0 };
  const client = new CallbackClient({
    singleAttemptTimeoutMs: 10,
    fetchImpl: async (_url, options) => {
      attempts += 1;
      if (unavailable) {
        return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => {
          reject(Object.assign(new Error('accepted but response stalled'), { name: 'AbortError' }));
        }, { once: true }));
      }
      return {
        ok: true, status: 200,
        async json() {
          const sent = JSON.parse(options.body);
          return { ...terminal(sent), requestId: sent.requestId, messageId: sent.message.messageId };
        },
      };
    },
  });
  const worker = new FeishuChannelWorker(workerOptions(statusDir, client, { connectionCounter }));
  t.after(() => worker.stop());
  await worker.start();
  const failedAt = Date.now();
  await assert.rejects(worker.handleMessage(message('om_timeout_recovery')), (error) => error.category === 'callback_timeout');
  unavailable = false;
  await waitUntil(async () => (await worker.spool.stats()).entries === 0);
  assert.ok(Date.now() - failedAt < 60_000);
  assert.ok(attempts >= 2);
  assert.equal(connectionCounter.connects, 1);
});

test('long Agent processing probes never launch a duplicate outcome and terminal response loss is idempotent', async (t) => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-fault-processing-'));
  let agentDone = false;
  let committed = false;
  let agentRuns = 0;
  let responseLost = true;
  let visibleOutcomes = 0;
  const client = {
    async deliverOnce(input) {
      if (!committed) {
        committed = true;
        agentRuns += 1;
      }
      if (!agentDone) throw new CallbackAttemptError('callback_processing', 'Agent still running', { retryAfterMs: 5 });
      if (responseLost) {
        responseLost = false;
        visibleOutcomes += 1;
        throw new CallbackAttemptError('callback_network_error', 'terminal response was lost');
      }
      return terminal(input);
    },
  };
  const worker = new FeishuChannelWorker(workerOptions(statusDir, client));
  t.after(() => worker.stop());
  await worker.start();
  await assert.rejects(worker.handleMessage(message('om_long_agent')), (error) => error.category === 'callback_processing');
  await waitUntil(() => worker.status.snapshot().processing.consecutiveFailures >= 1);
  agentDone = true;
  await waitUntil(async () => (await worker.spool.stats()).entries === 0);
  await waitUntil(() => worker.status.snapshot().counters.callbackAcknowledged === 1);
  assert.equal(agentRuns, 1);
  assert.equal(visibleOutcomes, 1);
  assert.equal(worker.status.snapshot().counters.callbackAcknowledged, 1);
});

test('worker restart replays retained processing work only after recovery is enabled', async (t) => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-fault-restart-'));
  let oldAttempts = 0;
  const first = new FeishuChannelWorker(workerOptions(statusDir, {
    async deliverOnce() { oldAttempts += 1; throw new CallbackAttemptError('callback_network_error', 'VO process stopped'); },
  }, { processingRecoveryEnabled: false }));
  await first.start();
  await assert.rejects(first.handleMessage(message('om_restart_reclaim')), /VO process stopped/);
  assert.equal((await first.spool.stats()).entries, 1);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(oldAttempts, 1, 'disabled recovery must retain without retrying');
  await first.stop();

  let reclaimed = 0;
  const second = new FeishuChannelWorker(workerOptions(statusDir, {
    async deliverOnce(input) { reclaimed += 1; return terminal(input); },
  }));
  t.after(() => second.stop());
  await second.start();
  await waitUntil(async () => (await second.spool.stats()).entries === 0);
  assert.equal(reclaimed, 1);
});

test('recovery-off live delivery drains older same-chat heads in order', async (t) => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-fault-live-drain-'));
  const delivered = [];
  const worker = new FeishuChannelWorker(workerOptions(statusDir, {
    async deliverOnce(input) { delivered.push(input.message.messageId); return terminal(input); },
  }, { processingRecoveryEnabled: false }));
  t.after(() => worker.stop());
  await worker.spool.put(envelope('om_live_old', 'oc_live_drain', 1));
  await worker.start();

  const ack = await worker.handleMessage(message('om_live_new', 'oc_live_drain', 2));
  assert.equal(ack.durable, true);
  assert.deepEqual(delivered, ['om_live_old', 'om_live_new']);
  assert.equal((await worker.spool.stats()).entries, 0);
});

test('recovery-off live delivery stops at a failed same-chat head and retains the tail', async (t) => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-fault-live-drain-fail-'));
  const delivered = [];
  const worker = new FeishuChannelWorker(workerOptions(statusDir, {
    async deliverOnce(input) {
      delivered.push(input.message.messageId);
      throw new CallbackAttemptError('callback_network_error', 'VO remains unavailable');
    },
  }, { processingRecoveryEnabled: false }));
  t.after(() => worker.stop());
  await worker.spool.put(envelope('om_live_failed_head', 'oc_live_drain_fail', 1));
  await worker.start();

  await assert.rejects(
    worker.handleMessage(message('om_live_retained_tail', 'oc_live_drain_fail', 2)),
    (error) => error.category === 'callback_network_error',
  );
  assert.deepEqual(delivered, ['om_live_failed_head']);
  assert.deepEqual(
    (await worker.spool.list()).filter((item) => item.envelope).map((item) => item.envelope.message.messageId),
    ['om_live_failed_head', 'om_live_retained_tail'],
  );
});

test('ordered replay isolates failed chats and retains corrupt or full spool evidence', async (t) => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-fault-order-'));
  const attempts = [];
  let chatAAvailable = false;
  const worker = new FeishuChannelWorker(workerOptions(statusDir, {
    async deliverOnce(input) {
      const id = input.message.messageId;
      attempts.push(id);
      if (input.message.chatId === 'oc_a' && !chatAAvailable) {
        throw new CallbackAttemptError('callback_network_error', 'chat A unavailable');
      }
      return terminal(input);
    },
  }, { processingRecoveryEnabled: false, recoveryConcurrency: 2 }));
  t.after(() => worker.stop());
  await worker.spool.put(envelope('om_a1', 'oc_a', 1));
  await worker.spool.put(envelope('om_a2', 'oc_a', 2));
  await worker.spool.put(envelope('om_b1', 'oc_b', 3));
  await worker.start();
  await worker.replay();
  assert.deepEqual(attempts.sort(), ['om_a1', 'om_b1']);
  assert.deepEqual((await worker.spool.list()).filter((item) => item.envelope).map((item) => item.envelope.message.messageId), ['om_a1', 'om_a2']);

  chatAAvailable = true;
  await worker.replay();
  await worker.replay();
  assert.deepEqual(attempts.filter((id) => id.startsWith('om_a')), ['om_a1', 'om_a1', 'om_a2']);
  await writeFile(join(worker.spool.root, 'corrupt.json'), '{corrupt', { mode: 0o600 });
  worker.spool.maxEntries = 1;
  const retained = await worker.spool.stats();
  assert.equal(retained.blocked, 1);
  assert.equal(retained.full, true);
  assert.equal((await worker.spool.list()).at(-1).error instanceof Error, true);
});
