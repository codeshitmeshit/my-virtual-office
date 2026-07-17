import { chmod, mkdir, open, readdir, readFile, rename, stat, unlink } from 'node:fs/promises';
import { basename, join } from 'node:path';

import { MAX_CARD_ACTION_BYTES, validateCardActionEnvelope } from './protocol.mjs';

export const DEFAULT_ACTION_MAX_ENTRIES = 1000;
export const DEFAULT_ACTION_MAX_BYTES = 8 * 1024 * 1024;

function safeId(value) {
  const normalized = String(value || '').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 180);
  if (!normalized || normalized === '.' || normalized === '..') throw new Error('invalid action request id');
  return normalized;
}

export class ActionSpoolFullError extends Error {
  constructor() {
    super('Feishu card-action spool is full');
    this.name = 'ActionSpoolFullError';
    this.code = 'action_spool_full';
  }
}

export class ApprovalActionSpool {
  constructor(root, { maxEntries = DEFAULT_ACTION_MAX_ENTRIES, maxBytes = DEFAULT_ACTION_MAX_BYTES } = {}) {
    this.root = root;
    this.maxEntries = maxEntries;
    this.maxBytes = maxBytes;
    this._chain = Promise.resolve();
  }

  async initialize() {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    await chmod(this.root, 0o700);
    return this.stats();
  }

  pathFor(requestId) { return join(this.root, `${safeId(requestId)}.json`); }

  async put(envelope) {
    validateCardActionEnvelope(envelope);
    const serialized = `${JSON.stringify(envelope)}\n`;
    const bytes = Buffer.byteLength(serialized);
    if (bytes > MAX_CARD_ACTION_BYTES) throw Object.assign(new Error('card action exceeds spool entry limit'), { code: 'payload_too_large' });
    const work = async () => {
      await this.initialize();
      const target = this.pathFor(envelope.requestId);
      try {
        await stat(target);
        return { duplicate: true, ...(await this.stats()) };
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
      const current = await this.stats();
      if (current.entries >= this.maxEntries || current.bytes + bytes > this.maxBytes) throw new ActionSpoolFullError();
      const temporary = `${target}.${process.pid}.${Date.now()}.tmp`;
      let handle;
      try {
        handle = await open(temporary, 'wx', 0o600);
        await handle.writeFile(serialized, 'utf8');
        await handle.sync();
        await handle.close();
        handle = undefined;
        await rename(temporary, target);
        await chmod(target, 0o600);
      } finally {
        if (handle) await handle.close().catch(() => {});
        await unlink(temporary).catch(() => {});
      }
      return { duplicate: false, ...(await this.stats()) };
    };
    const result = this._chain.then(work);
    this._chain = result.catch(() => {});
    return result;
  }

  async remove(requestId) {
    await unlink(this.pathFor(requestId)).catch((error) => {
      if (error.code !== 'ENOENT') throw error;
    });
    return this.stats();
  }

  async list() {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    const names = (await readdir(this.root)).filter((name) => name.endsWith('.json')).sort();
    const items = [];
    for (const name of names) {
      const path = join(this.root, basename(name));
      try {
        const info = await stat(path);
        const envelope = validateCardActionEnvelope(JSON.parse(await readFile(path, 'utf8')));
        items.push({ path, envelope, mtimeMs: info.mtimeMs, bytes: info.size });
      } catch (error) {
        if (error.code !== 'ENOENT') items.push({ path, error, bytes: 0 });
      }
    }
    return items.sort((left, right) => Number(left.envelope?.receivedAt || left.mtimeMs || 0) - Number(right.envelope?.receivedAt || right.mtimeMs || 0));
  }

  async stats() {
    const items = await this.list();
    const bytes = items.reduce((total, item) => total + Number(item.bytes || 0), 0);
    return {
      entries: items.length,
      valid: items.filter((item) => item.envelope).length,
      blocked: items.filter((item) => !item.envelope).length,
      bytes,
      full: items.length >= this.maxEntries || bytes >= this.maxBytes,
    };
  }
}
