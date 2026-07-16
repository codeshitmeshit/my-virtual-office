import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ChatExecutionLaneScheduler } from '../src/execution-lanes.mjs';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

test('execution lanes preserve source order in one chat and deduplicate live/replay activation', async () => {
  const scheduler = new ChatExecutionLaneScheduler({ maxConcurrent: 4, maxRecoveryConcurrent: 2 });
  const gates = [deferred(), deferred(), deferred()];
  const started = [];
  const submit = (id, order, gate, mode = 'live') => scheduler.submit({
    chatId: 'oc_same', messageId: id, order: [order], mode,
    execute: async () => { started.push(id); await gate.promise; return id; },
  });

  const newest = submit('om_3', 3, gates[2]);
  const oldest = submit('om_1', 1, gates[0], 'recovery');
  const middle = submit('om_2', 2, gates[1]);
  const duplicate = submit('om_1', 1, gates[0]);
  assert.equal(duplicate, oldest);
  await flush();
  assert.deepEqual(started, ['om_1']);
  gates[0].resolve();
  await oldest;
  await flush();
  assert.deepEqual(started, ['om_1', 'om_2']);
  gates[1].resolve();
  await middle;
  await flush();
  assert.deepEqual(started, ['om_1', 'om_2', 'om_3']);
  gates[2].resolve();
  assert.deepEqual(await Promise.all([oldest, middle, newest, duplicate]), ['om_1', 'om_2', 'om_3', 'om_1']);
});

test('execution lanes isolate a failed chat while bounding cross-chat recovery and global capacity', async () => {
  const scheduler = new ChatExecutionLaneScheduler({ maxConcurrent: 3, maxRecoveryConcurrent: 2 });
  const gates = new Map(Array.from({ length: 5 }, (_, index) => [`om_${index}`, deferred()]));
  const started = [];
  const tasks = Array.from({ length: 5 }, (_, index) => scheduler.submit({
    chatId: `oc_${index}`, messageId: `om_${index}`, mode: index < 4 ? 'recovery' : 'live',
    execute: async () => { started.push(`om_${index}`); await gates.get(`om_${index}`).promise; return index; },
  }));
  await flush();
  assert.equal(scheduler.snapshot().active, 3);
  assert.equal(scheduler.snapshot().activeRecovery, 2);
  assert.ok(started.includes('om_4'), 'live work should reuse capacity reserved from recovery');

  gates.get('om_0').reject(new Error('VO unavailable for chat 0'));
  await assert.rejects(tasks[0], /VO unavailable/);
  await flush();
  assert.ok(started.includes('om_2'), 'another chat should start after one chat fails');
  for (const [id, gate] of gates) if (id !== 'om_0') gate.resolve();
  assert.deepEqual(await Promise.all(tasks.slice(1)), [1, 2, 3, 4]);
});

test('runOldest attempts only the first retained message in each chat', async () => {
  const scheduler = new ChatExecutionLaneScheduler();
  const entries = [
    { envelope: { receivedAt: 1, message: { chatId: 'oc_a', messageId: 'om_a1', createTime: 1 } } },
    { envelope: { receivedAt: 2, message: { chatId: 'oc_a', messageId: 'om_a2', createTime: 2 } } },
    { envelope: { receivedAt: 3, message: { chatId: 'oc_b', messageId: 'om_b1', createTime: 3 } } },
  ];
  const attempted = [];
  await scheduler.runOldest(entries, {
    execute: async (item) => attempted.push(item.envelope.message.messageId),
  });
  assert.deepEqual(attempted.sort(), ['om_a1', 'om_b1']);
});

test('execution lanes reject per-chat pressure without affecting other chats', async () => {
  const scheduler = new ChatExecutionLaneScheduler({ maxConcurrent: 1, maxPerChatQueue: 2 });
  const first = deferred();
  const one = scheduler.submit({ chatId: 'oc_full', messageId: 'om_1', execute: () => first.promise });
  const two = scheduler.submit({ chatId: 'oc_full', messageId: 'om_2', execute: async () => 2 });
  await assert.rejects(
    scheduler.submit({ chatId: 'oc_full', messageId: 'om_3', execute: async () => 3 }),
    (error) => error.code === 'chat_queue_full',
  );
  const other = scheduler.submit({ chatId: 'oc_other', messageId: 'om_other', execute: async () => 'other' });
  await flush();
  assert.equal(scheduler.snapshot().active, 1);
  first.resolve(1);
  assert.equal(await one, 1);
  assert.equal(await two, 2);
  assert.equal(await other, 'other');
});
