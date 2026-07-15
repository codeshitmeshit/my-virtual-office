import { timingSafeEqual } from 'node:crypto';
import http from 'node:http';

import { COMMAND_SCHEMA, MAX_COMMAND_BYTES, ProtocolError, parseJsonBody, redact, validateCommandEnvelope } from './protocol.mjs';

function tokenMatches(expected, actual) {
  const left = Buffer.from(String(expected || ''));
  const right = Buffer.from(String(actual || ''));
  return left.length > 0 && left.length === right.length && timingSafeEqual(left, right);
}

function json(response, status, body) {
  const payload = Buffer.from(JSON.stringify(redact(body)));
  response.writeHead(status, { 'content-type': 'application/json', 'content-length': payload.length });
  response.end(payload);
}

export function classifyChannelError(error) {
  const allowed = new Set(['format_error', 'target_revoked', 'rate_limited', 'permission_denied', 'upload_failed', 'ssrf_blocked', 'send_timeout', 'not_connected', 'unknown']);
  const code = allowed.has(error?.code) ? error.code : error?.code === 'resource_too_large' || error?.code === 'unsafe_resource_path' || error?.code === 'unsupported_resource_type' ? error.code : 'unknown';
  return { ok: false, status: 'failed', category: code, error: String(error?.message || 'operation failed').slice(0, 500) };
}

function inputFor(payload) {
  return payload.contentType === 'text' ? { text: payload.content } : { markdown: payload.content };
}

export class CommandServer {
  constructor({ channel, token, workerInstanceId, resourceStore, logger, onEvent, maxBodyBytes = MAX_COMMAND_BYTES } = {}) {
    this.channel = channel;
    this.token = token;
    this.workerInstanceId = workerInstanceId;
    this.resourceStore = resourceStore;
    this.logger = logger;
    this.onEvent = onEvent;
    this.maxBodyBytes = maxBodyBytes;
    this.server = null;
    this.port = 0;
  }

  async start() {
    if (this.server) return this.status();
    this.server = http.createServer((request, response) => this._handle(request, response));
    await new Promise((resolve, reject) => {
      this.server.once('error', reject);
      this.server.listen(0, '127.0.0.1', resolve);
    });
    this.port = this.server.address().port;
    return this.status();
  }

  status() {
    return { ready: Boolean(this.server?.listening), host: '127.0.0.1', port: this.port };
  }

  async stop() {
    if (!this.server) return;
    const server = this.server;
    this.server = null;
    await new Promise((resolve) => server.close(resolve));
    this.port = 0;
  }

  async _read(request) {
    const chunks = [];
    let bytes = 0;
    for await (const chunk of request) {
      bytes += chunk.length;
      if (bytes > this.maxBodyBytes) throw new ProtocolError('payload_too_large', `request exceeds ${this.maxBodyBytes} bytes`, 413);
      chunks.push(chunk);
    }
    return parseJsonBody(Buffer.concat(chunks), this.maxBodyBytes);
  }

  async _handle(request, response) {
    if (request.method === 'GET' && request.url === '/health') return json(response, 200, { ok: true, ...this.status(), transport: 'channel-sdk-node' });
    if (request.method !== 'POST' || request.url !== '/command') return json(response, 404, { ok: false, category: 'not_found' });
    if (!tokenMatches(this.token, request.headers['x-vo-feishu-chat-worker-token'])) {
      await this.onEvent?.({ type: 'authentication_failure' });
      return json(response, 403, { ok: false, category: 'authentication_failed' });
    }
    try {
      const command = validateCommandEnvelope(await this._read(request));
      if (command.workerInstanceId !== this.workerInstanceId) throw new ProtocolError('worker_instance_mismatch', 'worker instance does not match', 409);
      const result = await this.execute(command);
      await this.onEvent?.({ type: 'command_success', operation: command.operation });
      return json(response, 200, { schema: `${COMMAND_SCHEMA}.result`, requestId: command.requestId, operation: command.operation, ...result });
    } catch (error) {
      const status = error instanceof ProtocolError ? error.statusCode : 502;
      await this.onEvent?.({ type: 'command_failure', category: error.code || 'unknown' });
      this.logger?.warn?.('Feishu command failed', { code: error.code, error: error.message });
      return json(response, status, { ...(error instanceof ProtocolError ? { ok: false, category: error.code, error: error.message } : classifyChannelError(error)) });
    }
  }

  async execute(command) {
    const { operation, payload } = command;
    const timeoutMs = payload.timeoutMs || 30000;
    const operationPromise = (async () => {
      if (operation === 'send') {
        const result = await this.channel.send(payload.to, inputFor(payload));
        return { ok: true, status: 'sent', messageId: result.messageId, chunkIds: result.chunkIds || [] };
      }
      if (operation === 'reply') {
        const result = await this.channel.send(payload.to, inputFor(payload), { replyTo: payload.messageId, replyInThread: Boolean(payload.replyInThread) });
        return { ok: true, status: 'sent', messageId: result.messageId, chunkIds: result.chunkIds || [] };
      }
      if (operation === 'addReaction') return { ok: true, status: 'added', reactionId: await this.channel.addReaction(payload.messageId, payload.emojiType) };
      if (operation === 'removeReaction') {
        await this.channel.removeReaction(payload.messageId, payload.reactionId);
        return { ok: true, status: 'deleted', reactionId: payload.reactionId };
      }
      if (operation === 'recall') {
        await this.channel.recallMessage(payload.messageId);
        return { ok: true, status: 'recalled', messageId: payload.messageId };
      }
      if (operation === 'downloadResource') return this.resourceStore.download(this.channel, payload);
      throw new ProtocolError('unknown_operation', `unsupported operation: ${operation}`);
    })();
    let timer;
    try {
      return await Promise.race([
        operationPromise,
        new Promise((_, reject) => { timer = setTimeout(() => reject(Object.assign(new Error('command timed out'), { code: 'send_timeout' })), timeoutMs); }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }
}
