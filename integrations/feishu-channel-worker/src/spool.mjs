import { chmod, mkdir, open, readdir, readFile, rename, stat, unlink } from 'node:fs/promises';
import { basename, join } from 'node:path';

import { MAX_INBOUND_BYTES, validateInboundEnvelope } from './protocol.mjs';

export const DEFAULT_MAX_ENTRIES = 1000;
export const DEFAULT_MAX_BYTES = 50 * 1024 * 1024;
export const DEFAULT_PRESSURE_RATIO = 0.8;

function safeId(value) {
  const normalized = String(value || '').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 180);
  if (!normalized || normalized === '.' || normalized === '..') throw new Error('invalid spool message id');
  return normalized;
}

function epochMs(value) {
  const parsed = Number(value || 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return parsed < 1_000_000_000_000 ? parsed * 1000 : parsed;
}

function envelopeOrder(item) {
  const envelope = item?.envelope || {};
  const message = envelope.message || {};
  return [
    epochMs(message.createTime) || epochMs(envelope.receivedAt) || Number(item?.mtimeMs || 0),
    epochMs(envelope.receivedAt) || Number(item?.mtimeMs || 0),
    String(message.messageId || ''),
  ];
}

function compareEntries(left, right) {
  const a = envelopeOrder(left);
  const b = envelopeOrder(right);
  for (let index = 0; index < a.length; index += 1) {
    if (a[index] < b[index]) return -1;
    if (a[index] > b[index]) return 1;
  }
  return String(left?.path || '').localeCompare(String(right?.path || ''));
}

export class SpoolFullError extends Error {
  constructor(message = 'Feishu inbound spool is full') {
    super(message);
    this.name = 'SpoolFullError';
    this.code = 'inbox_full';
  }
}

export class InboundSpool {
  constructor(root, { maxEntries = DEFAULT_MAX_ENTRIES, maxBytes = DEFAULT_MAX_BYTES, maxEntryBytes = MAX_INBOUND_BYTES } = {}) {
    this.root = root;
    this.maxEntries = maxEntries;
    this.maxBytes = maxBytes;
    this.maxEntryBytes = maxEntryBytes;
    this._chain = Promise.resolve();
  }

  async initialize() {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    await chmod(this.root, 0o700);
    return this.stats();
  }

  pathFor(messageId) {
    return join(this.root, `${safeId(messageId)}.json`);
  }

  async put(envelope) {
    validateInboundEnvelope(envelope);
    const serialized = `${JSON.stringify(envelope)}\n`;
    const bytes = Buffer.byteLength(serialized);
    if (bytes > this.maxEntryBytes) throw Object.assign(new Error('inbound envelope exceeds spool entry limit'), { code: 'payload_too_large' });
    const work = async () => {
      await this.initialize();
      const target = this.pathFor(envelope.message.messageId);
      try {
        await stat(target);
        return { path: target, duplicate: true, ...(await this.stats()) };
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
      const current = await this.stats();
      if (current.entries >= this.maxEntries || current.bytes + bytes > this.maxBytes) throw new SpoolFullError();
      const tmp = `${target}.${process.pid}.${Date.now()}.tmp`;
      let handle;
      try {
        handle = await open(tmp, 'wx', 0o600);
        await handle.writeFile(serialized, 'utf8');
        await handle.sync();
        await handle.close();
        handle = undefined;
        await chmod(tmp, 0o600);
        await rename(tmp, target);
        await chmod(target, 0o600);
      } finally {
        if (handle) await handle.close().catch(() => {});
        await unlink(tmp).catch(() => {});
      }
      return { path: target, duplicate: false, ...(await this.stats()) };
    };
    const result = this._chain.then(work);
    this._chain = result.catch(() => {});
    return result;
  }

  async remove(messageId) {
    await unlink(this.pathFor(messageId)).catch((error) => {
      if (error.code !== 'ENOENT') throw error;
    });
    return this.stats();
  }

  async list() {
    return (await this.snapshot()).items;
  }

  async snapshot() {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    const names = (await readdir(this.root)).filter((name) => name.endsWith('.json')).sort();
    const validItems = [];
    const blockedItems = [];
    let bytes = 0;
    let oldestPendingAt = 0;
    for (const name of names) {
      const path = join(this.root, basename(name));
      try {
        const fileStat = await stat(path);
        bytes += fileStat.size;
        try {
          const envelope = validateInboundEnvelope(JSON.parse(await readFile(path, 'utf8')));
          const item = { path, envelope, mtimeMs: fileStat.mtimeMs };
          validItems.push(item);
          const pendingAt = envelopeOrder(item)[0];
          if (pendingAt > 0 && (!oldestPendingAt || pendingAt < oldestPendingAt)) oldestPendingAt = pendingAt;
        } catch (error) {
          blockedItems.push({ path, error, mtimeMs: fileStat.mtimeMs });
          if (!oldestPendingAt || fileStat.mtimeMs < oldestPendingAt) oldestPendingAt = fileStat.mtimeMs;
        }
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
    }
    validItems.sort(compareEntries);
    const items = [...validItems, ...blockedItems];
    const entries = items.length;
    const ratio = Math.max(entries / this.maxEntries, bytes / this.maxBytes);
    return {
      items,
      entries,
      valid: validItems.length,
      blocked: blockedItems.length,
      bytes,
      oldestPendingAt: Math.round(oldestPendingAt || 0),
      pressure: ratio >= DEFAULT_PRESSURE_RATIO,
      full: entries >= this.maxEntries || bytes >= this.maxBytes,
    };
  }

  async stats() {
    const { items: _items, ...stats } = await this.snapshot();
    return stats;
  }
}
