import assert from 'node:assert/strict';
import { test } from 'node:test';

import { processingRecoveryConfig } from '../src/config.mjs';

test('processing recovery environment controls use safe defaults and bounded values', () => {
  assert.deepEqual(processingRecoveryConfig({}), {
    enabled: true,
    callbackAttemptTimeoutMs: 45_000,
    baseDelayMs: 1_000,
    maxDelayMs: 30_000,
    jitterMs: 5_000,
    maxConcurrentCallbacks: 16,
    recoveryConcurrency: 4,
    warningThresholdMs: 60_000,
  });
  const bounded = processingRecoveryConfig({
    VO_FEISHU_CHAT_PROCESSING_RECOVERY_ENABLED: 'off',
    VO_FEISHU_CHAT_CALLBACK_ATTEMPT_TIMEOUT_MS: '999999',
    VO_FEISHU_CHAT_PROCESSING_RECOVERY_BASE_DELAY_MS: '999999',
    VO_FEISHU_CHAT_PROCESSING_RECOVERY_MAX_DELAY_MS: '999999',
    VO_FEISHU_CHAT_PROCESSING_RECOVERY_JITTER_MS: '999999',
    VO_FEISHU_CHAT_MAX_CONCURRENT_CALLBACKS: '3',
    VO_FEISHU_CHAT_PROCESSING_RECOVERY_CONCURRENCY: '99',
    VO_FEISHU_CHAT_PROCESSING_WARNING_THRESHOLD_MS: '-1',
  });
  assert.equal(bounded.enabled, false);
  assert.equal(bounded.callbackAttemptTimeoutMs, 55_000);
  assert.equal(bounded.jitterMs, 10_000);
  assert.equal(bounded.maxDelayMs, 49_999);
  assert.equal(bounded.baseDelayMs, 49_999);
  assert.equal(bounded.maxConcurrentCallbacks, 3);
  assert.equal(bounded.recoveryConcurrency, 3);
  assert.equal(bounded.warningThresholdMs, 1_000);
  assert.ok(bounded.maxDelayMs + bounded.jitterMs < 60_000);
});
