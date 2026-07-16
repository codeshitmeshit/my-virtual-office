const DEFAULT_BASE_DELAY_MS = 1_000;
const DEFAULT_MAX_DELAY_MS = 30_000;
const DEFAULT_JITTER_MS = 5_000;
const MAX_WAKE_DELAY_MS = 59_999;

function boundedInteger(value, fallback, minimum = 0) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minimum, Math.floor(parsed));
}

export class ProcessingRecoveryCoordinator {
  constructor({
    run,
    enabled = true,
    baseDelayMs = DEFAULT_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_MAX_DELAY_MS,
    jitterMs = DEFAULT_JITTER_MS,
    now = Date.now,
    random = Math.random,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    onState = () => {},
  } = {}) {
    if (typeof run !== 'function') throw new TypeError('processing recovery run function is required');
    this.run = run;
    this.enabled = Boolean(enabled);
    this.baseDelayMs = boundedInteger(baseDelayMs, DEFAULT_BASE_DELAY_MS, 1);
    this.maxDelayMs = boundedInteger(maxDelayMs, DEFAULT_MAX_DELAY_MS, this.baseDelayMs);
    this.jitterMs = boundedInteger(jitterMs, DEFAULT_JITTER_MS);
    if (this.maxDelayMs + this.jitterMs > MAX_WAKE_DELAY_MS) {
      throw new RangeError('processing recovery maximum delay plus jitter must stay below one minute');
    }
    this.now = now;
    this.random = random;
    this.setTimer = setTimer;
    this.clearTimer = clearTimer;
    this.onState = onState;
    this.timer = null;
    this.timerDueAt = 0;
    this.active = false;
    this.closed = false;
    this.wakeRequested = false;
    this.consecutiveFailures = 0;
    this.nextRetryAt = 0;
  }

  snapshot() {
    return {
      enabled: this.enabled && !this.closed,
      active: this.active,
      scheduled: Boolean(this.timer),
      nextRetryAt: this.nextRetryAt,
      consecutiveFailures: this.consecutiveFailures,
    };
  }

  _publish() {
    try {
      Promise.resolve(this.onState(this.snapshot())).catch(() => {});
    } catch {
      // Observability must never stop recovery scheduling.
    }
  }

  _schedule(delayMs) {
    if (!this.enabled || this.closed) return false;
    const delay = Math.min(MAX_WAKE_DELAY_MS, boundedInteger(delayMs, 0));
    const dueAt = this.now() + delay;
    if (this.timer && this.timerDueAt <= dueAt) return false;
    if (this.timer) this.clearTimer(this.timer);
    this.timerDueAt = dueAt;
    this.nextRetryAt = dueAt;
    this.timer = this.setTimer(() => {
      this.timer = null;
      this.timerDueAt = 0;
      this.nextRetryAt = 0;
      this._execute().catch(() => {});
    }, delay);
    this.timer?.unref?.();
    this._publish();
    return true;
  }

  wake({ delayMs = 0 } = {}) {
    if (!this.enabled || this.closed) return false;
    if (this.active) {
      this.wakeRequested = true;
      return true;
    }
    return this._schedule(delayMs);
  }

  _backoffDelay(retryAfterMs = 0) {
    const exponent = Math.max(0, this.consecutiveFailures - 1);
    const exponential = Math.min(this.maxDelayMs, this.baseDelayMs * (2 ** Math.min(exponent, 30)));
    const jitter = Math.floor(Math.max(0, Math.min(1, Number(this.random()) || 0)) * this.jitterMs);
    return Math.min(MAX_WAKE_DELAY_MS, Math.max(exponential + jitter, boundedInteger(retryAfterMs, 0)));
  }

  async _execute() {
    if (!this.enabled || this.closed || this.active) return;
    this.active = true;
    this._publish();
    let outcome;
    let failed = false;
    try {
      outcome = (await this.run()) || {};
      failed = Boolean(outcome.failed);
    } catch {
      outcome = { pending: true };
      failed = true;
    } finally {
      this.active = false;
    }

    if (!this.enabled || this.closed) {
      this.wakeRequested = false;
      this._publish();
      return;
    }

    if (outcome.progress) this.consecutiveFailures = 0;
    else if (failed || outcome.pending) this.consecutiveFailures += 1;
    else this.consecutiveFailures = 0;

    const explicitWake = this.wakeRequested;
    this.wakeRequested = false;
    if (explicitWake) this._schedule(0);
    else if (outcome.pending) {
      const delay = outcome.progress
        ? this.baseDelayMs
        : this._backoffDelay(outcome.retryAfterMs);
      this._schedule(delay);
    } else {
      this.nextRetryAt = 0;
      this._publish();
    }
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (!this.enabled && this.timer) {
      this.clearTimer(this.timer);
      this.timer = null;
      this.timerDueAt = 0;
      this.nextRetryAt = 0;
    }
    if (!this.enabled) this.wakeRequested = false;
    this._publish();
  }

  stop() {
    this.closed = true;
    this.setEnabled(false);
  }
}

export const PROCESSING_RECOVERY_DEFAULTS = Object.freeze({
  baseDelayMs: DEFAULT_BASE_DELAY_MS,
  maxDelayMs: DEFAULT_MAX_DELAY_MS,
  jitterMs: DEFAULT_JITTER_MS,
  maxWakeDelayMs: MAX_WAKE_DELAY_MS,
});
