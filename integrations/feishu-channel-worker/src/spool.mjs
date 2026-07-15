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
    await this.initialize();
    const names = (await readdir(this.root)).filter((name) => name.endsWith('.json')).sort();
    const results = [];
    for (const name of names) {
      const path = join(this.root, basename(name));
      try {
        const envelope = validateInboundEnvelope(JSON.parse(await readFile(path, 'utf8')));
        results.push({ path, envelope });
      } catch (error) {
        results.push({ path, error });
      }
    }
    return results;
  }

  async stats() {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    const names = (await readdir(this.root)).filter((name) => name.endsWith('.json'));
    let bytes = 0;
    for (const name of names) {
      try {
        bytes += (await stat(join(this.root, name))).size;
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
    }
    const entries = names.length;
    const ratio = Math.max(entries / this.maxEntries, bytes / this.maxBytes);
    return { entries, bytes, pressure: ratio >= DEFAULT_PRESSURE_RATIO, full: entries >= this.maxEntries || bytes >= this.maxBytes };
  }
}
