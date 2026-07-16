function laneKey(value) {
  return String(value || '');
}

function compareOrder(left, right) {
  const a = Array.isArray(left.order) ? left.order : [];
  const b = Array.isArray(right.order) ? right.order : [];
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const av = a[index] ?? '';
    const bv = b[index] ?? '';
    if (av < bv) return -1;
    if (av > bv) return 1;
  }
  return left.sequence - right.sequence;
}

export class ChatExecutionLaneScheduler {
  constructor({
    maxConcurrent = 16,
    maxRecoveryConcurrent = 4,
    maxPerChatQueue = 20,
    onState = () => {},
  } = {}) {
    this.maxConcurrent = Math.max(1, Math.floor(Number(maxConcurrent) || 16));
    this.maxRecoveryConcurrent = Math.max(1, Math.min(
      this.maxConcurrent,
      Math.floor(Number(maxRecoveryConcurrent) || 4),
    ));
    this.maxPerChatQueue = Math.max(1, Math.floor(Number(maxPerChatQueue) || 20));
    this.onState = onState;
    this.lanes = new Map();
    this.jobsByMessageId = new Map();
    this.activeChats = new Set();
    this.active = 0;
    this.activeRecovery = 0;
    this.sequence = 0;
    this.pumpRequested = false;
    this.closed = false;
  }

  snapshot() {
    let pending = 0;
    for (const queue of this.lanes.values()) pending += queue.length;
    return {
      active: this.active,
      activeRecovery: this.activeRecovery,
      pending,
      chats: this.lanes.size,
      pressure: pending > 0 && this.active >= this.maxConcurrent,
    };
  }

  _publish() {
    try {
      Promise.resolve(this.onState(this.snapshot())).catch(() => {});
    } catch {
      // Queue observability must not interfere with delivery.
    }
  }

  submit({ chatId, messageId, mode = 'live', order = [], execute }) {
    if (this.closed) return Promise.reject(Object.assign(new Error('execution lanes are stopped'), { code: 'lanes_stopped' }));
    if (typeof execute !== 'function') return Promise.reject(new TypeError('lane execute function is required'));
    const normalizedChatId = laneKey(chatId);
    const normalizedMessageId = laneKey(messageId);
    if (!normalizedChatId || !normalizedMessageId) {
      return Promise.reject(new TypeError('chatId and messageId are required'));
    }
    const duplicate = this.jobsByMessageId.get(normalizedMessageId);
    if (duplicate) return duplicate.promise;

    const queue = this.lanes.get(normalizedChatId) || [];
    const depth = queue.length + (this.activeChats.has(normalizedChatId) ? 1 : 0);
    if (depth >= this.maxPerChatQueue) {
      return Promise.reject(Object.assign(new Error('per-chat queue is full'), { code: 'chat_queue_full' }));
    }

    let resolve;
    let reject;
    const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
    const job = {
      chatId: normalizedChatId,
      messageId: normalizedMessageId,
      mode: mode === 'recovery' ? 'recovery' : 'live',
      order,
      execute,
      sequence: this.sequence += 1,
      promise,
      resolve,
      reject,
    };
    queue.push(job);
    queue.sort(compareOrder);
    this.lanes.set(normalizedChatId, queue);
    this.jobsByMessageId.set(normalizedMessageId, job);
    this._requestPump();
    this._publish();
    return promise;
  }

  runOldest(entries, { mode = 'recovery', execute } = {}) {
    const heads = new Map();
    for (const item of entries || []) {
      const envelope = item?.envelope || item;
      const chatId = laneKey(envelope?.message?.chatId);
      if (!chatId || heads.has(chatId)) continue;
      heads.set(chatId, item);
    }
    return Promise.all([...heads.values()].map((item) => {
      const envelope = item?.envelope || item;
      return this.submit({
        chatId: envelope.message.chatId,
        messageId: envelope.message.messageId,
        mode,
        order: [Number(envelope.message.createTime || 0), Number(envelope.receivedAt || 0), envelope.message.messageId],
        execute: () => execute(item),
      });
    }));
  }

  _requestPump() {
    if (this.pumpRequested || this.closed) return;
    this.pumpRequested = true;
    queueMicrotask(() => {
      this.pumpRequested = false;
      this._pump();
    });
  }

  _nextRunnable() {
    for (const [chatId, queue] of this.lanes) {
      if (!queue.length || this.activeChats.has(chatId)) continue;
      const job = queue[0];
      if (job.mode === 'recovery' && this.activeRecovery >= this.maxRecoveryConcurrent) continue;
      queue.shift();
      if (!queue.length) this.lanes.delete(chatId);
      return job;
    }
    return null;
  }

  _pump() {
    while (!this.closed && this.active < this.maxConcurrent) {
      const job = this._nextRunnable();
      if (!job) break;
      this.active += 1;
      if (job.mode === 'recovery') this.activeRecovery += 1;
      this.activeChats.add(job.chatId);
      this._publish();
      Promise.resolve()
        .then(job.execute)
        .then(job.resolve, job.reject)
        .finally(() => {
          this.active = Math.max(0, this.active - 1);
          if (job.mode === 'recovery') this.activeRecovery = Math.max(0, this.activeRecovery - 1);
          this.activeChats.delete(job.chatId);
          this.jobsByMessageId.delete(job.messageId);
          this._publish();
          this._requestPump();
        });
    }
    this._publish();
  }

  stop() {
    this.closed = true;
    for (const queue of this.lanes.values()) {
      for (const job of queue) {
        this.jobsByMessageId.delete(job.messageId);
        job.reject(Object.assign(new Error('execution lanes are stopped'), { code: 'lanes_stopped' }));
      }
    }
    this.lanes.clear();
    this._publish();
  }
}
