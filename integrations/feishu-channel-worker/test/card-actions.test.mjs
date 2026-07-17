import assert from 'node:assert/strict';
import { mkdtemp, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { ActionSpoolFullError, ApprovalActionSpool } from '../src/action-spool.mjs';
import { CardActionCallbackClient } from '../src/callback.mjs';
import {
  CARD_ACTION_ACK_SCHEMA,
  CARD_ACTION_SCHEMA,
  ProtocolError,
  makeCardActionEnvelope,
  validateCardActionEnvelope,
} from '../src/protocol.mjs';
import { FeishuChannelWorker } from '../src/worker.mjs';

function action(overrides = {}) {
  return {
    messageId: 'om_action',
    chatId: 'oc_action',
    operator: { openId: 'ou_origin', userId: 'u_origin', unionId: 'on_origin', name: 'Origin' },
    value: { action: 'codex_approval_once', route_id: 'route-1', version: 1 },
    tag: 'button',
    name: '',
    option: '',
    ...overrides,
  };
}

function envelope(overrides = {}) {
  const value = makeCardActionEnvelope(action(), { workerInstanceId: 'worker-action', source: { eventId: 'evt-1' } });
  return { ...value, ...overrides };
}

async function waitUntil(predicate, timeoutMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail('condition not reached');
}

test('card-action protocol is strict, bounded, and keeps only normalized fields', () => {
  const value = envelope();
  assert.equal(validateCardActionEnvelope(value).schema, CARD_ACTION_SCHEMA);
  assert.throws(() => validateCardActionEnvelope({ ...value, extra: true }), (error) => error instanceof ProtocolError && error.code === 'unknown_field');
  assert.throws(
    () => validateCardActionEnvelope({ ...value, action: { ...value.action, value: { text: 'x'.repeat(17 * 1024) } } }),
    (error) => error.code === 'field_too_large',
  );
  assert.throws(
    () => validateCardActionEnvelope({ ...value, action: { ...value.action, operator: { openId: '' } } }),
    (error) => error.code === 'invalid_shape',
  );
});

test('approval-action spool is atomic, duplicate-safe, and bounded', async () => {
  const root = await mkdtemp(join(tmpdir(), 'vo-feishu-action-spool-'));
  const spool = new ApprovalActionSpool(root, { maxEntries: 1, maxBytes: 1024 * 1024 });
  const first = envelope();
  assert.equal((await spool.put(first)).duplicate, false);
  assert.equal((await spool.put(first)).duplicate, true);
  assert.equal((await stat(spool.pathFor(first.requestId))).mode & 0o777, 0o600);
  await assert.rejects(() => spool.put(envelope({ requestId: 'request-2' })), (error) => error instanceof ActionSpoolFullError);
  assert.equal((await spool.stats()).full, true);
  await spool.remove(first.requestId);
  assert.equal((await spool.stats()).entries, 0);
});

test('card-action callback uses worker token and validates durable acknowledgement', async () => {
  let request;
  const input = envelope();
  const client = new CardActionCallbackClient({
    url: 'http://127.0.0.1/card-action-worker',
    token: 'worker-secret-token',
    fetchImpl: async (_url, options) => {
      request = options;
      return {
        ok: true,
        async json() {
          return {
            schema: CARD_ACTION_ACK_SCHEMA,
            requestId: input.requestId,
            messageId: input.action.messageId,
            durable: true,
            state: 'completed',
          };
        },
      };
    },
  });
  const ack = await client.deliverOnce(input);
  assert.equal(ack.durable, true);
  assert.equal(request.headers['x-vo-feishu-chat-worker-token'], 'worker-secret-token');
  assert.equal(JSON.parse(request.body).schema, CARD_ACTION_SCHEMA);
});

test('worker spools card actions separately and replays callback failures', async () => {
  const statusDir = await mkdtemp(join(tmpdir(), 'vo-feishu-card-action-worker-'));
  const handlers = {};
  const normalMessages = [];
  const actionDeliveries = [];
  let failAction = true;
  const channel = {
    on(map) { Object.assign(handlers, map); },
    async connect() {}, async disconnect() {},
    getConnectionStatus() { return { state: 'connected' }; },
  };
  const worker = new FeishuChannelWorker({
    appId: 'cli_test', appSecret: 'secret', statusDir,
    callbackUrl: 'http://127.0.0.1/inbound-worker', callbackToken: 'worker-token',
    workerInstanceId: 'worker-action', parentPid: process.pid, createChannel: () => channel,
    callbackClient: { async deliverOnce(value) { normalMessages.push(value); } },
    cardActionCallbackClient: {
      async deliverOnce(value) {
        actionDeliveries.push(value);
        if (failAction) throw Object.assign(new Error('backend unavailable'), { code: 'callback_network_error' });
        return { schema: CARD_ACTION_ACK_SCHEMA, requestId: value.requestId, messageId: value.action.messageId, durable: true };
      },
    },
  });
  await worker.start();
  clearInterval(worker.actionRecoveryTimer);
  worker.actionRecoveryTimer = null;

  const response = await handlers.cardAction({
    messageId: 'om_action', chatId: 'oc_action',
    operator: { openId: 'ou_origin', userId: 'u_origin', name: 'Origin' },
    action: { value: { action: 'codex_approval_once', route_id: 'route-1', version: 1 }, tag: 'button' },
    raw: { header: { event_id: 'evt-action', tenant_key: 'tenant-1' }, operator: { union_id: 'on_origin' } },
  });
  assert.deepEqual(response, { toast: { type: 'loading', content: '审批处理中' } });
  await waitUntil(async () => actionDeliveries.length === 1 && worker.actionInFlight.size === 0 && (await worker.actionSpool.stats()).entries === 1);
  assert.equal(normalMessages.length, 0, 'card actions must not use the normal inbound-message callback');
  assert.equal(actionDeliveries[0].action.operator.unionId, 'on_origin');

  failAction = false;
  const replay = await worker._runActionRecovery();
  assert.equal(replay.entries, 0);
  assert.equal(actionDeliveries.length, 2);
  assert.equal(worker.status.snapshot().counters.cardActionAcknowledged, 1);
  await worker.stop();
});
