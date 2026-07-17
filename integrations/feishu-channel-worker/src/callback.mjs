import { setTimeout as delay } from 'node:timers/promises';

import { ACK_SCHEMA, CARD_ACTION_ACK_SCHEMA, redact } from './protocol.mjs';

export const DEFAULT_SINGLE_ATTEMPT_TIMEOUT_MS = 45_000;
export const MAX_SINGLE_ATTEMPT_TIMEOUT_MS = 55_000;

export class CallbackAttemptError extends Error {
  constructor(category, message, { status = 0, retryAfterMs = 0, cause } = {}) {
    super(message, cause ? { cause } : undefined);
    this.name = 'CallbackAttemptError';
    this.code = category;
    this.category = category;
    this.status = Number(status || 0);
    this.retryAfterMs = Number(retryAfterMs || 0);
  }
}

function boundedRetryAfter(value) {
  const parsed = Number(value || 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.min(Math.max(Math.round(parsed), 1_000), 60_000);
}

export class CallbackClient {
  constructor({
    url,
    token,
    timeoutMs = 600000,
    singleAttemptTimeoutMs = DEFAULT_SINGLE_ATTEMPT_TIMEOUT_MS,
    maxAttempts = 5,
    baseDelayMs = 250,
    fetchImpl = globalThis.fetch,
    logger,
  } = {}) {
    this.url = url;
    this.token = token;
    this.timeoutMs = Math.min(Math.max(Number(timeoutMs) || 1, 1), 900000);
    this.singleAttemptTimeoutMs = Math.min(
      Math.max(Number(singleAttemptTimeoutMs) || 1, 1),
      MAX_SINGLE_ATTEMPT_TIMEOUT_MS,
    );
    this.maxAttempts = Math.min(Math.max(Number(maxAttempts) || 1, 1), 10);
    this.baseDelayMs = Math.max(Number(baseDelayMs) || 0, 0);
    this.fetchImpl = fetchImpl;
    this.logger = logger;
  }

  async _attempt(envelope, attempt, timeoutMs) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      let response;
      try {
        response = await this.fetchImpl(this.url, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-vo-feishu-chat-worker-token': this.token },
          body: JSON.stringify({ ...envelope, attempt }),
          signal: controller.signal,
        });
      } catch (error) {
        if (controller.signal.aborted || error?.name === 'AbortError') {
          throw new CallbackAttemptError('callback_timeout', `callback attempt timed out after ${timeoutMs}ms`, { cause: error });
        }
        throw new CallbackAttemptError('callback_network_error', 'callback network request failed', { cause: error });
      }
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new CallbackAttemptError('callback_http_error', `callback HTTP ${response.status}`, { status: response.status });
      }
      const identityMatches = body.schema === ACK_SCHEMA
        && body.requestId === envelope.requestId
        && body.messageId === envelope.message.messageId;
      if (!identityMatches) {
        throw new CallbackAttemptError('callback_invalid_ack', 'callback response identity is invalid');
      }
      if (body.durable === true) return body;
      if (body.durable === false && body.state === 'processing') {
        throw new CallbackAttemptError('callback_processing', 'callback is still processing', {
          retryAfterMs: boundedRetryAfter(body.retryAfterMs),
        });
      }
      throw new CallbackAttemptError('callback_invalid_ack', 'callback response is not a terminal durable acknowledgement');
    } finally {
      clearTimeout(timeout);
    }
  }

  deliverOnce(envelope, { attempt = 1 } = {}) {
    return this._attempt(envelope, Math.max(1, Number(attempt) || 1), this.singleAttemptTimeoutMs);
  }

  async deliver(envelope) {
    let lastError;
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        return await this._attempt(envelope, attempt, this.timeoutMs);
      } catch (error) {
        lastError = error;
        this.logger?.warn?.('Feishu callback attempt failed', { attempt, requestId: envelope.requestId, error: redact({ message: error.message, code: error.code }) });
        if (attempt < this.maxAttempts) await delay(Math.min(this.baseDelayMs * (2 ** (attempt - 1)), 5000));
      }
    }
    throw Object.assign(new Error(`callback failed after ${this.maxAttempts} attempts: ${lastError?.message || 'unknown'}`), { code: lastError?.code || 'callback_failed', cause: lastError });
  }
}

export function cardActionCallbackUrl(inboundUrl) {
  const parsed = new URL(String(inboundUrl || ''));
  parsed.pathname = parsed.pathname.endsWith('/inbound-worker')
    ? parsed.pathname.slice(0, -'/inbound-worker'.length) + '/card-action-worker'
    : parsed.pathname.replace(/\/$/, '') + '/card-action-worker';
  return parsed.toString();
}

export class CardActionCallbackClient {
  constructor({ url, token, singleAttemptTimeoutMs = 5000, fetchImpl = globalThis.fetch } = {}) {
    this.url = url;
    this.token = token;
    this.singleAttemptTimeoutMs = Math.min(Math.max(Number(singleAttemptTimeoutMs) || 1, 1), 10_000);
    this.fetchImpl = fetchImpl;
  }

  async deliverOnce(envelope) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.singleAttemptTimeoutMs);
    try {
      let response;
      try {
        response = await this.fetchImpl(this.url, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-vo-feishu-chat-worker-token': this.token },
          body: JSON.stringify(envelope),
          signal: controller.signal,
        });
      } catch (error) {
        const category = controller.signal.aborted || error?.name === 'AbortError' ? 'callback_timeout' : 'callback_network_error';
        throw new CallbackAttemptError(category, 'card-action callback request failed', { cause: error });
      }
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new CallbackAttemptError('callback_http_error', `callback HTTP ${response.status}`, { status: response.status });
      if (
        body.schema !== CARD_ACTION_ACK_SCHEMA
        || body.requestId !== envelope.requestId
        || body.messageId !== envelope.action.messageId
        || body.durable !== true
      ) {
        throw new CallbackAttemptError('callback_invalid_ack', 'card-action callback acknowledgement is invalid');
      }
      return body;
    } finally {
      clearTimeout(timeout);
    }
  }
}
