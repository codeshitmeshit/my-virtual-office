import { setTimeout as delay } from 'node:timers/promises';

import { ACK_SCHEMA, redact } from './protocol.mjs';

export class CallbackClient {
  constructor({ url, token, timeoutMs = 600000, maxAttempts = 5, baseDelayMs = 250, fetchImpl = globalThis.fetch, logger } = {}) {
    this.url = url;
    this.token = token;
    this.timeoutMs = Math.min(Math.max(Number(timeoutMs) || 1, 1), 900000);
    this.maxAttempts = Math.min(Math.max(Number(maxAttempts) || 1, 1), 10);
    this.baseDelayMs = Math.max(Number(baseDelayMs) || 0, 0);
    this.fetchImpl = fetchImpl;
    this.logger = logger;
  }

  async deliver(envelope) {
    let lastError;
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
      try {
        const response = await this.fetchImpl(this.url, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-vo-feishu-chat-worker-token': this.token },
          body: JSON.stringify({ ...envelope, attempt }),
          signal: controller.signal,
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw Object.assign(new Error(`callback HTTP ${response.status}`), { code: 'callback_http_error', status: response.status });
        if (body.schema !== ACK_SCHEMA || body.requestId !== envelope.requestId || body.messageId !== envelope.message.messageId || body.durable !== true) {
          throw Object.assign(new Error('callback response is not a durable acknowledgement'), { code: 'invalid_acknowledgement' });
        }
        return body;
      } catch (error) {
        lastError = error;
        this.logger?.warn?.('Feishu callback attempt failed', { attempt, requestId: envelope.requestId, error: redact({ message: error.message, code: error.code }) });
        if (attempt < this.maxAttempts) await delay(Math.min(this.baseDelayMs * (2 ** (attempt - 1)), 5000));
      } finally {
        clearTimeout(timeout);
      }
    }
    throw Object.assign(new Error(`callback failed after ${this.maxAttempts} attempts: ${lastError?.message || 'unknown'}`), { code: lastError?.code || 'callback_failed', cause: lastError });
  }
}
