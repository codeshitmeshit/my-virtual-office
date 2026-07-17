import assert from 'node:assert/strict';
import { mkdtemp, readFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import {
  COMMAND_SCHEMA,
  CARD_ACTION_SCHEMA,
  INBOUND_SCHEMA,
  ProtocolError,
  redact,
  validateCommandEnvelope,
  validateCardActionEnvelope,
  validateInboundEnvelope,
} from '../src/protocol.mjs';
import { StatusStore } from '../src/status.mjs';
import { createSafeLogger } from '../src/logger.mjs';

function inbound(overrides = {}) {
  return {
    schema: INBOUND_SCHEMA,
    requestId: 'req-1',
    workerInstanceId: 'worker-1',
    transport: 'channel-sdk-node',
    attempt: 1,
    receivedAt: 1,
    message: {
      messageId: 'om_1', chatId: 'oc_1', chatType: 'p2p', content: 'hello', rawContentType: 'text',
      createTime: 1, mentions: [], resources: [], sender: { primaryId: 'ou_1', openId: 'ou_1' },
    },
    source: {},
    ...overrides,
  };
}

test('validates strict inbound and command protocol envelopes', () => {
  const enriched = inbound();
  enriched.message.sender = { ...enriched.message.sender, name: 'Alice', type: 'user', isBot: false };
  enriched.message.mentions = [{ key: '@_user_1', openId: 'ou_bot', name: 'VO', isBot: true }];
  assert.equal(validateInboundEnvelope(enriched).message.messageId, 'om_1');
  assert.equal(enriched.message.sender.isBot, false);
  assert.equal(enriched.message.mentions[0].isBot, true);
  const command = validateCommandEnvelope({
    schema: COMMAND_SCHEMA,
    requestId: 'cmd-1',
    workerInstanceId: 'worker-1',
    operation: 'send',
    payload: { to: 'oc_1', content: 'hello', contentType: 'text', timeoutMs: 1000 },
  });
  assert.equal(command.operation, 'send');
  const action = validateCardActionEnvelope({
    schema: CARD_ACTION_SCHEMA,
    requestId: 'action-1',
    workerInstanceId: 'worker-1',
    transport: 'channel-sdk-node',
    attempt: 1,
    receivedAt: 1,
    action: {
      messageId: 'om_action', chatId: 'oc_action',
      operator: { openId: 'ou_1' },
      value: { action: 'codex_approval_once', route_id: 'route-1' }, tag: 'button',
    },
    source: { eventId: 'evt-1' },
  });
  assert.equal(action.action.value.route_id, 'route-1');
});

test('fails closed for malformed, oversized, unknown, and unsupported protocol input', () => {
  assert.throws(() => validateInboundEnvelope(inbound({ extra: true })), (error) => error instanceof ProtocolError && error.code === 'unknown_field');
  assert.throws(() => validateInboundEnvelope(inbound({ schema: 'v0' })), (error) => error.code === 'unsupported_schema');
  assert.throws(() => validateInboundEnvelope(inbound({ message: { ...inbound().message, content: 'x'.repeat(600000) } })), (error) => error.code === 'field_too_large');
  assert.throws(() => validateInboundEnvelope(inbound({ message: { ...inbound().message, sender: { ...inbound().message.sender, name: 'x'.repeat(513) } } })), (error) => error.code === 'field_too_large');
  assert.throws(() => validateInboundEnvelope(inbound({ message: { ...inbound().message, sender: { ...inbound().message.sender, isBot: 'false' } } })), (error) => error.code === 'invalid_shape');
  assert.throws(() => validateInboundEnvelope(inbound({ message: { ...inbound().message, mentions: Array.from({ length: 101 }, () => ({ openId: 'ou_1' })) } })), (error) => error.code === 'invalid_shape');
  assert.throws(() => validateInboundEnvelope(inbound({ message: { ...inbound().message, mentions: [{ openId: 'ou_1', isBot: 'yes' }] } })), (error) => error.code === 'invalid_shape');
  assert.throws(() => validateCommandEnvelope({ schema: COMMAND_SCHEMA, requestId: '1', workerInstanceId: '1', operation: 'shell', payload: {} }), (error) => error.code === 'unknown_operation');
});

test('redacts nested credentials, authorization, cookies, and credential URLs', () => {
  const safe = JSON.stringify(redact({
    appSecret: 'canary-secret',
    headers: { authorization: 'Bearer canary-token', cookie: 'sid=canary' },
    url: 'https://user:pass@example.test/path',
  }));
  assert.doesNotMatch(safe, /canary-secret|canary-token|sid=canary|user:pass/);
  assert.match(safe, /REDACTED/);
});

test('writes atomic mode-0600 status snapshots during concurrent updates', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'vo-feishu-status-'));
  const path = join(dir, 'status.json');
  const store = new StatusStore(path, { workerInstanceId: 'worker-1' });
  const writes = Array.from({ length: 40 }, (_, index) => store.update({ heartbeatAt: index, counters: { received: index } }));
  await Promise.all(writes);
  const data = JSON.parse(await readFile(path, 'utf8'));
  assert.equal(data.heartbeatAt, 39);
  assert.equal(data.counters.received, 39);
  assert.equal((await stat(path)).mode & 0o777, 0o600);
});

test('rate-limits repeated safe logs while retaining repeat counts', () => {
  const records = [];
  const sink = { warn: (line) => records.push(line), log: (line) => records.push(line) };
  const logger = createSafeLogger({ sink, repeatWindowMs: 60000 });
  logger.warn('connection failed', { authorization: 'Bearer canary', url: 'https://user:pass@example.test' });
  logger.warn('connection failed', { authorization: 'Bearer canary', url: 'https://user:pass@example.test' });
  assert.equal(records.length, 1);
  assert.doesNotMatch(records[0], /canary|user:pass/);
  assert.equal(logger.repeatCount('warn', 'connection failed', { authorization: 'Bearer canary', url: 'https://user:pass@example.test' }), 2);
});

test('safe logger redacts configured canary secrets even in arbitrary error text', () => {
  const records = [];
  const logger = createSafeLogger({ sink: { error: (line) => records.push(line) }, secrets: ['app-secret-canary'] });
  logger.error('startup app-secret-canary failed', { detail: 'app-secret-canary' });
  assert.doesNotMatch(records[0], /app-secret-canary/);
  assert.match(records[0], /REDACTED/);
});
