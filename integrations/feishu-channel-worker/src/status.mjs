import { chmod, mkdir, open, readFile, rename, unlink } from 'node:fs/promises';
import { dirname } from 'node:path';

export function initialStatus(overrides = {}) {
  return {
    enabled: true,
    running: false,
    status: 'not_started',
    startedAt: 0,
    lastEventAt: 0,
    lastError: '',
    mode: 'subprocess',
    transport: 'channel-sdk-node',
    pid: process.pid,
    parentPid: process.ppid,
    workerInstanceId: '',
    heartbeatAt: 0,
    sdk: { connected: false, state: 'not_started' },
    reconnect: { active: false, count: 0, lastAt: 0 },
    callback: { active: 0, failures: 0, lastFailureAt: 0 },
    processing: {
      state: 'healthy', backlog: 0, blocked: 0, oldestPendingAt: 0,
      lastAckAt: 0, lastFailureAt: 0, nextRetryAt: 0, recoveryActive: false,
      consecutiveFailures: 0, warning: false, lastErrorCategory: '',
    },
    command: { ready: false, port: 0, failures: 0, lastFailureAt: 0 },
    queue: { active: 0, pending: 0, pressure: false },
    spool: { entries: 0, bytes: 0, pressure: false, full: false, replayed: 0 },
    counters: {},
    ...overrides,
  };
}
export class StatusStore {
  constructor(path, initial = {}) {
    this.path = path;
    this.value = initialStatus(initial);
    this._writeChain = Promise.resolve();
  }

  snapshot() {
    return structuredClone(this.value);
  }

  update(patch = {}) {
    this.value = merge(this.value, patch);
    const snapshot = this.snapshot();
    this._writeChain = this._writeChain.then(() => this._atomicWrite(snapshot));
    return this._writeChain.then(() => snapshot);
  }

  increment(path, amount = 1) {
    const keys = String(path).split('.');
    const patch = {};
    let cursor = patch;
    let current = this.value;
    keys.forEach((key, index) => {
      if (index === keys.length - 1) cursor[key] = Number(current?.[key] || 0) + amount;
      else {
        cursor[key] = {};
        cursor = cursor[key];
        current = current?.[key];
      }
    });
    return this.update(patch);
  }

  async flush() {
    await this._writeChain;
  }

  async _atomicWrite(snapshot) {
    await mkdir(dirname(this.path), { recursive: true, mode: 0o700 });
    const tmp = `${this.path}.${process.pid}.${Date.now()}.tmp`;
    let handle;
    try {
      handle = await open(tmp, 'wx', 0o600);
      await handle.writeFile(`${JSON.stringify(snapshot)}\n`, 'utf8');
      await handle.sync();
      await handle.close();
      handle = undefined;
      await chmod(tmp, 0o600);
      await rename(tmp, this.path);
      await chmod(this.path, 0o600);
    } finally {
      if (handle) await handle.close().catch(() => {});
      await unlink(tmp).catch(() => {});
    }
  }

  static async read(path) {
    return JSON.parse(await readFile(path, 'utf8'));
  }
}

function merge(base, patch) {
  const result = { ...base };
  for (const [key, value] of Object.entries(patch || {})) {
    if (value && typeof value === 'object' && !Array.isArray(value) && base?.[key] && typeof base[key] === 'object' && !Array.isArray(base[key])) {
      result[key] = merge(base[key], value);
    } else {
      result[key] = value;
    }
  }
  return result;
}
