import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ProcessingRecoveryCoordinator } from '../src/recovery.mjs';

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function fakeClock() {
  let now = 1_000;
  let nextId = 1;
  const timers = new Map();
  return {
    now: () => now,
    setTimer(callback, delay) {
      const timer = { id: nextId += 1, callback, dueAt: now + delay, unref() {} };
      timers.set(timer.id, timer);
      return timer;
    },
    clearTimer(timer) { timers.delete(timer.id); },
    delays() { return [...timers.values()].map((timer) => timer.dueAt - now).sort((a, b) => a - b); },
    elapse(ms) { now += ms; },
    async advance(ms = 0) {
      const target = now + ms;
      while (true) {
        const due = [...timers.values()].filter((timer) => timer.dueAt <= target).sort((a, b) => a.dueAt - b.dueAt)[0];
        if (!due) break;
        now = due.dueAt;
        timers.delete(due.id);
        due.callback();
        await Promise.resolve();
        await Promise.resolve();
      }
      now = Math.max(now, target);
      await Promise.resolve();
      await Promise.resolve();
    },
  };
}

test('processing recovery is single-flight and coalesces wake-ups during a run', async () => {
  const clock = fakeClock();
  const first = deferred();
  let calls = 0;
  let active = 0;
  let maximumActive = 0;
  const coordinator = new ProcessingRecoveryCoordinator({
    run: async () => {
      calls += 1;
      active += 1;
      maximumActive = Math.max(maximumActive, active);
      if (calls === 1) await first.promise;
      active -= 1;
      return { pending: false };
    },
    now: clock.now, setTimer: clock.setTimer, clearTimer: clock.clearTimer,
  });

  coordinator.wake();
  coordinator.wake();
  await clock.advance();
  assert.equal(calls, 1);
  coordinator.wake();
  coordinator.wake();
  first.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(clock.delays(), [0]);
  await clock.advance();
  assert.equal(calls, 2);
  assert.equal(maximumActive, 1);
});

test('processing recovery uses capped exponential backoff and bounded jitter indefinitely', async () => {
  const clock = fakeClock();
  let calls = 0;
  const coordinator = new ProcessingRecoveryCoordinator({
    run: async () => { calls += 1; throw new Error('VO unavailable'); },
    baseDelayMs: 1_000,
    maxDelayMs: 30_000,
    jitterMs: 5_000,
    random: () => 1,
    now: clock.now, setTimer: clock.setTimer, clearTimer: clock.clearTimer,
  });

  coordinator.wake();
  const expected = [6_000, 7_000, 9_000, 13_000, 21_000, 35_000, 35_000, 35_000];
  for (const delay of expected) {
    await clock.advance(clock.delays()[0] || 0);
    assert.deepEqual(clock.delays(), [delay]);
  }
  assert.equal(calls, expected.length);
  assert.equal(coordinator.snapshot().consecutiveFailures, expected.length);
  assert.ok(coordinator.snapshot().nextRetryAt - clock.now() < 60_000);
});

test('processing recovery resets failures after progress and honors retry guidance', async () => {
  const clock = fakeClock();
  const outcomes = [
    { pending: true, failed: true, retryAfterMs: 8_000 },
    { pending: true, progress: true },
    { pending: false },
  ];
  const coordinator = new ProcessingRecoveryCoordinator({
    run: async () => outcomes.shift(),
    baseDelayMs: 1_000, maxDelayMs: 30_000, jitterMs: 0,
    now: clock.now, setTimer: clock.setTimer, clearTimer: clock.clearTimer,
  });

  coordinator.wake();
  await clock.advance();
  assert.deepEqual(clock.delays(), [8_000]);
  assert.equal(coordinator.snapshot().consecutiveFailures, 1);
  await clock.advance(8_000);
  assert.deepEqual(clock.delays(), [1_000]);
  assert.equal(coordinator.snapshot().consecutiveFailures, 0);
  await clock.advance(1_000);
  assert.deepEqual(clock.delays(), []);
  assert.equal(coordinator.snapshot().consecutiveFailures, 0);
});

test('processing recovery measures retry deadlines from attempt start', async () => {
  const clock = fakeClock();
  let calls = 0;
  const attemptStarts = [];
  const coordinator = new ProcessingRecoveryCoordinator({
    run: async () => {
      calls += 1;
      attemptStarts.push(clock.now());
      clock.elapse(calls === 1 ? 45_000 : 10_000);
      return { pending: true, failed: true, retryAfterMs: 35_000 };
    },
    baseDelayMs: 1_000,
    maxDelayMs: 30_000,
    jitterMs: 5_000,
    random: () => 1,
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });

  coordinator.wake();
  await clock.advance();
  assert.equal(calls, 1);
  assert.deepEqual(clock.delays(), [0]);

  await clock.advance();
  assert.equal(calls, 2);
  assert.deepEqual(attemptStarts, [1_000, 46_000]);
  assert.deepEqual(clock.delays(), [25_000]);
  assert.equal(coordinator.snapshot().nextRetryAt - attemptStarts[1], 35_000);
});

test('processing recovery reschedules earlier wake-ups and stops cleanly behind the feature switch', async () => {
  const clock = fakeClock();
  let calls = 0;
  const coordinator = new ProcessingRecoveryCoordinator({
    run: async () => { calls += 1; return { pending: false }; },
    now: clock.now, setTimer: clock.setTimer, clearTimer: clock.clearTimer,
  });

  coordinator.wake({ delayMs: 20_000 });
  coordinator.wake({ delayMs: 5_000 });
  coordinator.wake({ delayMs: 10_000 });
  assert.deepEqual(clock.delays(), [5_000]);
  coordinator.setEnabled(false);
  assert.deepEqual(clock.delays(), []);
  assert.equal(coordinator.wake(), false);
  await clock.advance(60_000);
  assert.equal(calls, 0);
  coordinator.setEnabled(true);
  assert.equal(coordinator.wake(), true);
  await clock.advance();
  assert.equal(calls, 1);
  coordinator.stop();
  coordinator.setEnabled(true);
  assert.equal(coordinator.wake(), false);
});

test('processing recovery rejects configurations whose maximum wake exceeds one minute', () => {
  assert.throws(() => new ProcessingRecoveryCoordinator({
    run: async () => {}, maxDelayMs: 55_000, jitterMs: 5_000,
  }), /below one minute/);
});
