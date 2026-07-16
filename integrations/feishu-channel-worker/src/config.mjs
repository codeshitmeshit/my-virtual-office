function integer(value, fallback, { min = 0, max = Number.MAX_SAFE_INTEGER } = {}) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.floor(parsed)));
}

function boolean(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback;
  return !['0', 'false', 'no', 'off'].includes(String(value).trim().toLowerCase());
}

export function processingRecoveryConfig(env = process.env) {
  const maxConcurrentCallbacks = integer(env.VO_FEISHU_CHAT_MAX_CONCURRENT_CALLBACKS, 16, { min: 1, max: 64 });
  const jitterMs = integer(env.VO_FEISHU_CHAT_PROCESSING_RECOVERY_JITTER_MS, 5_000, { min: 0, max: 10_000 });
  const maxDelayMs = integer(env.VO_FEISHU_CHAT_PROCESSING_RECOVERY_MAX_DELAY_MS, 30_000, {
    min: 1_000,
    max: 59_999 - jitterMs,
  });
  const baseDelayMs = integer(env.VO_FEISHU_CHAT_PROCESSING_RECOVERY_BASE_DELAY_MS, 1_000, {
    min: 100,
    max: maxDelayMs,
  });
  return {
    enabled: boolean(env.VO_FEISHU_CHAT_PROCESSING_RECOVERY_ENABLED, true),
    callbackAttemptTimeoutMs: integer(env.VO_FEISHU_CHAT_CALLBACK_ATTEMPT_TIMEOUT_MS, 45_000, { min: 1_000, max: 55_000 }),
    baseDelayMs,
    maxDelayMs,
    jitterMs,
    maxConcurrentCallbacks,
    recoveryConcurrency: integer(env.VO_FEISHU_CHAT_PROCESSING_RECOVERY_CONCURRENCY, 4, { min: 1, max: maxConcurrentCallbacks }),
    warningThresholdMs: integer(env.VO_FEISHU_CHAT_PROCESSING_WARNING_THRESHOLD_MS, 60_000, { min: 1_000, max: 86_400_000 }),
  };
}
