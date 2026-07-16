import { randomUUID } from 'node:crypto';

export const INBOUND_SCHEMA = 'vo.feishu-chat.inbound/v1';
export const COMMAND_SCHEMA = 'vo.feishu-chat.command/v1';
export const ACK_SCHEMA = 'vo.feishu-chat.ack/v1';
export const MAX_INBOUND_BYTES = 1024 * 1024;
export const MAX_COMMAND_BYTES = 256 * 1024;
export const COMMAND_OPERATIONS = new Set([
  'send',
  'reply',
  'addReaction',
  'removeReaction',
  'recall',
  'downloadResource',
]);

const SENSITIVE_KEY = /(?:secret|token|authorization|cookie|password|api[_-]?key|proxy)/i;
const CREDENTIAL_URL = /([a-z][a-z0-9+.-]*:\/\/)([^/@\s:]+):([^/@\s]+)@/gi;
const BEARER = /\bBearer\s+[A-Za-z0-9._~+\/-]+=*/gi;

export class ProtocolError extends Error {
  constructor(code, message, statusCode = 400) {
    super(message);
    this.name = 'ProtocolError';
    this.code = code;
    this.statusCode = statusCode;
  }
}

export function redactString(value) {
  return String(value ?? '')
    .replace(CREDENTIAL_URL, '$1[REDACTED]@')
    .replace(BEARER, 'Bearer [REDACTED]');
}

export function redactSecretsString(value, secrets = []) {
  let result = redactString(value);
  for (const secret of secrets) {
    const text = String(secret || '');
    if (text) result = result.split(text).join('[REDACTED]');
  }
  return result;
}

export function redact(value, depth = 0) {
  if (depth > 8) return '[TRUNCATED]';
  if (typeof value === 'string') return redactString(value);
  if (Array.isArray(value)) return value.slice(0, 100).map((item) => redact(item, depth + 1));
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).slice(0, 200).map(([key, item]) => [
    key,
    SENSITIVE_KEY.test(key) ? '[REDACTED]' : redact(item, depth + 1),
  ]));
}

export function byteLength(value) {
  return Buffer.byteLength(typeof value === 'string' ? value : JSON.stringify(value), 'utf8');
}

function requireObject(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ProtocolError('invalid_shape', `${name} must be an object`);
  }
  return value;
}

function requireString(value, name, { max = 4096, optional = false } = {}) {
  if (optional && (value === undefined || value === null || value === '')) return '';
  if (typeof value !== 'string' || !value.trim()) {
    throw new ProtocolError('invalid_shape', `${name} must be a non-empty string`);
  }
  if (Buffer.byteLength(value, 'utf8') > max) {
    throw new ProtocolError('field_too_large', `${name} exceeds ${max} bytes`, 413);
  }
  return value;
}

function rejectUnknown(object, allowed, name) {
  const unknown = Object.keys(object).filter((key) => !allowed.has(key));
  if (unknown.length) {
    throw new ProtocolError('unknown_field', `${name} contains unknown field: ${unknown[0]}`);
  }
}

export function parseJsonBody(buffer, maxBytes) {
  if (!Buffer.isBuffer(buffer)) buffer = Buffer.from(buffer || '');
  if (buffer.length > maxBytes) {
    throw new ProtocolError('payload_too_large', `request exceeds ${maxBytes} bytes`, 413);
  }
  try {
    return requireObject(JSON.parse(buffer.toString('utf8')), 'request');
  } catch (error) {
    if (error instanceof ProtocolError) throw error;
    throw new ProtocolError('invalid_json', 'request body is not valid JSON');
  }
}

export function validateInboundEnvelope(input) {
  const envelope = requireObject(input, 'inbound envelope');
  if (byteLength(envelope) > MAX_INBOUND_BYTES) {
    throw new ProtocolError('payload_too_large', `inbound envelope exceeds ${MAX_INBOUND_BYTES} bytes`, 413);
  }
  rejectUnknown(envelope, new Set([
    'schema', 'requestId', 'workerInstanceId', 'transport', 'attempt', 'receivedAt', 'message', 'source',
  ]), 'inbound envelope');
  if (envelope.schema !== INBOUND_SCHEMA) {
    throw new ProtocolError('unsupported_schema', `expected ${INBOUND_SCHEMA}`);
  }
  requireString(envelope.requestId, 'requestId', { max: 128 });
  requireString(envelope.workerInstanceId, 'workerInstanceId', { max: 128 });
  if (envelope.transport !== 'channel-sdk-node') {
    throw new ProtocolError('unsupported_transport', 'transport must be channel-sdk-node');
  }
  if (!Number.isInteger(envelope.attempt) || envelope.attempt < 1 || envelope.attempt > 1000) {
    throw new ProtocolError('invalid_shape', 'attempt must be an integer between 1 and 1000');
  }
  const message = requireObject(envelope.message, 'message');
  rejectUnknown(message, new Set([
    'messageId', 'chatId', 'chatType', 'content', 'rawContentType', 'createTime', 'rootId', 'threadId',
    'replyToMessageId', 'mentions', 'resources', 'sender',
  ]), 'message');
  requireString(message.messageId, 'message.messageId', { max: 256 });
  requireString(message.chatId, 'message.chatId', { max: 256 });
  if (!['p2p', 'group'].includes(message.chatType)) {
    throw new ProtocolError('invalid_shape', 'message.chatType must be p2p or group');
  }
  requireString(message.rawContentType, 'message.rawContentType', { max: 64 });
  if (typeof message.content !== 'string') {
    throw new ProtocolError('invalid_shape', 'message.content must be a string');
  }
  if (Buffer.byteLength(message.content, 'utf8') > 512 * 1024) {
    throw new ProtocolError('field_too_large', 'message.content exceeds 524288 bytes', 413);
  }
  const sender = requireObject(message.sender, 'message.sender');
  rejectUnknown(sender, new Set(['primaryId', 'openId', 'userId', 'unionId', 'name', 'type', 'isBot']), 'message.sender');
  if (![sender.openId, sender.userId, sender.unionId, sender.primaryId].some((value) => typeof value === 'string' && value)) {
    throw new ProtocolError('invalid_shape', 'message.sender requires at least one identifier');
  }
  for (const field of ['primaryId', 'openId', 'userId', 'unionId']) {
    if (sender[field] !== undefined && sender[field] !== '') requireString(sender[field], `message.sender.${field}`, { max: 256 });
  }
  if (sender.name !== undefined && sender.name !== '') requireString(sender.name, 'message.sender.name', { max: 512 });
  if (sender.type !== undefined && sender.type !== '') requireString(sender.type, 'message.sender.type', { max: 64 });
  if (sender.isBot !== undefined && typeof sender.isBot !== 'boolean') {
    throw new ProtocolError('invalid_shape', 'message.sender.isBot must be a boolean');
  }
  if (!Array.isArray(message.mentions) || message.mentions.length > 100) {
    throw new ProtocolError('invalid_shape', 'message.mentions must be an array with at most 100 entries');
  }
  for (const [index, rawMention] of message.mentions.entries()) {
    const mention = requireObject(rawMention, `message.mentions[${index}]`);
    rejectUnknown(mention, new Set(['id', 'key', 'openId', 'userId', 'unionId', 'name', 'isBot']), `message.mentions[${index}]`);
    for (const field of ['id', 'key', 'openId', 'userId', 'unionId', 'name']) {
      if (mention[field] !== undefined && mention[field] !== '') {
        requireString(mention[field], `message.mentions[${index}].${field}`, { max: field === 'name' ? 512 : 256 });
      }
    }
    if (mention.isBot !== undefined && typeof mention.isBot !== 'boolean') {
      throw new ProtocolError('invalid_shape', `message.mentions[${index}].isBot must be a boolean`);
    }
  }
  return envelope;
}

function validateOperationPayload(operation, payload) {
  payload = requireObject(payload, 'payload');
  const schemas = {
    send: [['to', 'content'], ['to', 'content', 'contentType', 'timeoutMs']],
    reply: [['to', 'messageId', 'content'], ['to', 'messageId', 'content', 'contentType', 'replyInThread', 'timeoutMs']],
    addReaction: [['messageId', 'emojiType'], ['messageId', 'emojiType', 'timeoutMs']],
    removeReaction: [['messageId', 'reactionId'], ['messageId', 'reactionId', 'timeoutMs']],
    recall: [['messageId'], ['messageId', 'timeoutMs']],
    downloadResource: [['messageId', 'fileKey', 'resourceType'], ['messageId', 'fileKey', 'resourceType', 'displayName', 'timeoutMs']],
  };
  const allowed = new Set(schemas[operation][1]);
  rejectUnknown(payload, allowed, 'payload');
  for (const field of schemas[operation][0]) requireString(payload[field], `payload.${field}`, { max: field === 'content' ? 192 * 1024 : 1024 });
  if (payload.timeoutMs !== undefined && (!Number.isInteger(payload.timeoutMs) || payload.timeoutMs < 1 || payload.timeoutMs > 900000)) {
    throw new ProtocolError('invalid_timeout', 'payload.timeoutMs must be between 1 and 900000');
  }
  if (payload.contentType !== undefined && !['text', 'markdown'].includes(payload.contentType)) {
    throw new ProtocolError('invalid_shape', 'payload.contentType must be text or markdown');
  }
  if (operation === 'downloadResource' && !['image', 'file'].includes(payload.resourceType)) {
    throw new ProtocolError('unsupported_resource_type', 'payload.resourceType must be image or file');
  }
  return payload;
}

export function validateCommandEnvelope(input) {
  const envelope = requireObject(input, 'command envelope');
  if (byteLength(envelope) > MAX_COMMAND_BYTES) {
    throw new ProtocolError('payload_too_large', `command envelope exceeds ${MAX_COMMAND_BYTES} bytes`, 413);
  }
  rejectUnknown(envelope, new Set(['schema', 'requestId', 'workerInstanceId', 'operation', 'payload']), 'command envelope');
  if (envelope.schema !== COMMAND_SCHEMA) throw new ProtocolError('unsupported_schema', `expected ${COMMAND_SCHEMA}`);
  requireString(envelope.requestId, 'requestId', { max: 128 });
  requireString(envelope.workerInstanceId, 'workerInstanceId', { max: 128 });
  requireString(envelope.operation, 'operation', { max: 64 });
  if (!COMMAND_OPERATIONS.has(envelope.operation)) {
    throw new ProtocolError('unknown_operation', `unsupported operation: ${envelope.operation}`);
  }
  validateOperationPayload(envelope.operation, envelope.payload);
  return envelope;
}

export function makeInboundEnvelope(message, { workerInstanceId, attempt = 1, source = {} } = {}) {
  const envelope = {
    schema: INBOUND_SCHEMA,
    requestId: randomUUID(),
    workerInstanceId,
    transport: 'channel-sdk-node',
    attempt,
    receivedAt: Date.now(),
    message,
    source: redact(source),
  };
  return validateInboundEnvelope(envelope);
}

export function makeAck(requestId, messageId, { durable, state, idempotent = false } = {}) {
  return {
    schema: ACK_SCHEMA,
    requestId,
    messageId,
    durable: Boolean(durable),
    state: String(state || ''),
    idempotent: Boolean(idempotent),
  };
}
