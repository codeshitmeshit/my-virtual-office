(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) {
    root.CodexChatTiming = api;
    root.getCodexChatTimingDiagnostics = () => api.diagnostics();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const FRAGMENT_EVENTS = new Set([
    'message.delta', 'reasoning.available', 'tool.started', 'tool.completed',
    'tool.failed', 'provider.activity', 'approval.request'
  ]);
  const TERMINAL_EVENTS = new Set(['run.completed', 'run.failed', 'run.cancelled', 'run.canceled']);
  const trackers = new Set();

  function percentile(values, ratio) {
    if (!values.length) return 0;
    const ordered = values.slice().sort((a, b) => a - b);
    return ordered[Math.min(ordered.length - 1, Math.max(0, Math.ceil(ordered.length * ratio) - 1))];
  }

  function summarize(values) {
    const clean = values.filter(Number.isFinite);
    return {
      samples: clean.length,
      p50Ms: Number(percentile(clean, 0.50).toFixed(3)),
      p95Ms: Number(percentile(clean, 0.95).toFixed(3)),
      maxMs: Number((clean.length ? Math.max(...clean) : 0).toFixed(3))
    };
  }

  class CodexChatTimingTracker {
    constructor(options = {}) {
      this.clock = typeof options.clock === 'function'
        ? options.clock
        : () => (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now());
      this.maxRuns = Math.max(1, Math.min(Number(options.maxRuns || 200), 1000));
      this.maxOrphans = Math.max(1, Math.min(Number(options.maxOrphans || 100), 500));
      this.nextSubmission = 0;
      this.pending = new Map();
      this.runs = new Map();
      this.orphans = new Map();
    }

    beginSubmission() {
      const token = `submission-${++this.nextSubmission}`;
      this.pending.set(token, { token, submittedAt: this.clock(), workingAt: null, runId: '' });
      return token;
    }

    markWorkingVisible(token) {
      const record = this.pending.get(token) || this.runs.get(token);
      if (!record || record.workingAt !== null) return false;
      record.workingAt = this.clock();
      return true;
    }

    bindRun(token, runId) {
      const record = this.pending.get(token);
      runId = String(runId || '');
      if (!record || !runId) return false;
      this.pending.delete(token);
      record.runId = runId;
      const orphan = this.orphans.get(runId);
      if (orphan) {
        Object.assign(record, orphan);
        this.orphans.delete(runId);
      }
      this.runs.set(runId, record);
      this._trim(this.runs, this.maxRuns);
      return true;
    }

    abandon(token) {
      return this.pending.delete(token);
    }

    observeEvent(runId, eventName, data = {}) {
      runId = String(runId || '');
      if (!runId) return false;
      const now = this.clock();
      const record = this.runs.get(runId) || this.orphans.get(runId) || { runId };
      if (record.firstNativeAt == null) record.firstNativeAt = now;
      if (FRAGMENT_EVENTS.has(eventName) && record.firstFragmentAt == null) record.firstFragmentAt = now;
      const text = eventName === 'message.delta' ? String(data.delta || data.text || data.reply || '') : '';
      if (text && record.firstTextAt == null) record.firstTextAt = now;
      if (TERMINAL_EVENTS.has(eventName) && record.terminalAt == null) record.terminalAt = now;
      if (!this.runs.has(runId)) {
        this.orphans.set(runId, record);
        this._trim(this.orphans, this.maxOrphans);
      }
      return true;
    }

    diagnostics() {
      const rows = Array.from(this.runs.values()).map(record => ({
        runId: record.runId,
        workingFeedbackMs: this._delta(record.workingAt, record.submittedAt),
        firstNativeEventMs: this._delta(record.firstNativeAt, record.submittedAt),
        firstFragmentMs: this._delta(record.firstFragmentAt, record.submittedAt),
        firstTextMs: this._delta(record.firstTextAt, record.submittedAt),
        terminalMs: this._delta(record.terminalAt, record.submittedAt)
      }));
      const working = summarize(rows.map(row => row.workingFeedbackMs));
      const firstNative = summarize(rows.map(row => row.firstNativeEventMs));
      return {
        schema: 'vo.codex-chat-browser-timing.v1',
        clockDomain: 'browser-monotonic',
        backendCorrelation: 'runId-only-no-clock-subtraction',
        retainedRuns: rows.length,
        maxRuns: this.maxRuns,
        pendingSubmissions: this.pending.size,
        orphanRuns: this.orphans.size,
        stages: {
          workingFeedbackMs: working,
          firstNativeEventMs: firstNative,
          firstFragmentMs: summarize(rows.map(row => row.firstFragmentMs)),
          firstTextMs: summarize(rows.map(row => row.firstTextMs)),
          terminalMs: summarize(rows.map(row => row.terminalMs)
          )
        },
        slo: {
          workingFeedbackP95AtMost200Ms: working.samples > 0 && working.p95Ms <= 200,
          firstNativeEventP95AtMost1000Ms: firstNative.samples > 0 && firstNative.p95Ms <= 1000,
          firstTextObservationOnly: true
        }
      };
    }

    _delta(value, start) {
      return Number.isFinite(value) && Number.isFinite(start) ? Math.max(0, value - start) : NaN;
    }

    _trim(map, limit) {
      while (map.size > limit) map.delete(map.keys().next().value);
    }
  }

  function createTracker(options) {
    const tracker = new CodexChatTimingTracker(options);
    trackers.add(tracker);
    return tracker;
  }

  function diagnostics() {
    return Array.from(trackers, tracker => tracker.diagnostics());
  }

  return { CodexChatTimingTracker, createTracker, diagnostics };
});
