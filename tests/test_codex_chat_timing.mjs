#!/usr/bin/env node

import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { CodexChatTimingTracker } = require('../app/codex-chat-timing.js');

let now = 0;
const advance = value => { now += value; };

// Ten warm-up turns are intentionally excluded from the measured tracker.
const warmup = new CodexChatTimingTracker({ clock: () => now });
for (let index = 0; index < 10; index += 1) {
  const token = warmup.beginSubmission();
  advance(10);
  warmup.markWorkingVisible(token);
  warmup.bindRun(token, `warmup-${index}`);
  advance(40);
  warmup.observeEvent(`warmup-${index}`, 'run.started', { ts: 999999999 });
  advance(10);
  warmup.observeEvent(`warmup-${index}`, 'reasoning.available', { text: 'warmup' });
}

const tracker = new CodexChatTimingTracker({ clock: () => now, maxRuns: 200 });
for (let index = 0; index < 100; index += 1) {
  const submittedAt = now;
  const token = tracker.beginSubmission();
  advance(8 + (index % 9));
  tracker.markWorkingVisible(token);
  const runId = `measured-${index}`;

  // Exercise the race where shared SSE beats the POST response. Synthetic
  // run.started must not count as a native Agent event.
  now = submittedAt + 80 + (index % 7);
  tracker.observeEvent(runId, 'run.started', { ts: 9999999999999 });
  now = submittedAt + 95 + (index % 11);
  tracker.observeEvent(runId, 'reasoning.available', { text: `fragment-${index}`, ts: -999999 });
  now = submittedAt + 110;
  assert.equal(tracker.bindRun(token, runId), true);
  now = submittedAt + 260 + (index % 31);
  tracker.observeEvent(runId, 'message.delta', { delta: `text-${index}`, ts: 1 });
  now = submittedAt + 400 + (index % 17);
  tracker.observeEvent(runId, 'run.completed', { reply: `done-${index}`, ts: 2 });
  now = submittedAt + 500;
}

const diagnostics = tracker.diagnostics();
assert.equal(diagnostics.retainedRuns, 100);
assert.equal(diagnostics.stages.workingFeedbackMs.samples, 100);
assert.equal(diagnostics.stages.firstNativeEventMs.samples, 100);
assert.equal(diagnostics.stages.firstFragmentMs.samples, 100);
assert.equal(diagnostics.stages.firstTextMs.samples, 100);
assert.ok(diagnostics.stages.workingFeedbackMs.p95Ms <= 200, diagnostics);
assert.ok(diagnostics.stages.firstNativeEventMs.p95Ms <= 1000, diagnostics);
assert.ok(diagnostics.stages.firstFragmentMs.p95Ms - diagnostics.stages.firstNativeEventMs.p95Ms < 33, diagnostics);
assert.equal(diagnostics.slo.workingFeedbackP95AtMost200Ms, true);
assert.equal(diagnostics.slo.firstNativeEventP95AtMost1000Ms, true);
assert.equal(diagnostics.slo.firstTextObservationOnly, true);
assert.equal(diagnostics.clockDomain, 'browser-monotonic');
assert.equal(diagnostics.backendCorrelation, 'runId-only-no-clock-subtraction');
assert.ok(diagnostics.stages.firstTextMs.p95Ms > diagnostics.stages.firstFragmentMs.p95Ms);
assert.ok(!JSON.stringify(diagnostics).includes('fragment-99'));
assert.ok(!JSON.stringify(diagnostics).includes('text-99'));

const nativeGate = new CodexChatTimingTracker({ clock: () => now });
const nativeToken = nativeGate.beginSubmission();
nativeGate.bindRun(nativeToken, 'native-gate');
advance(5);
nativeGate.observeEvent('native-gate', 'run.started');
assert.equal(nativeGate.diagnostics().stages.firstNativeEventMs.samples, 0);
advance(40);
nativeGate.observeEvent('native-gate', 'provider.activity');
assert.equal(nativeGate.diagnostics().stages.firstNativeEventMs.samples, 1);
assert.equal(nativeGate.diagnostics().stages.firstNativeEventMs.p95Ms, 45);

const workingRace = new CodexChatTimingTracker({ clock: () => now });
const workingToken = workingRace.beginSubmission();
advance(2);
assert.equal(workingRace.bindRun(workingToken, 'working-race'), true);
advance(8);
assert.equal(workingRace.markWorkingVisible(workingToken), true);
assert.equal(workingRace.diagnostics().stages.workingFeedbackMs.samples, 1);
assert.equal(workingRace.diagnostics().stages.workingFeedbackMs.p95Ms, 10);

const abandoned = tracker.beginSubmission();
tracker.markWorkingVisible(abandoned);
tracker.abandon(abandoned);
assert.equal(tracker.diagnostics().pendingSubmissions, 0);
assert.equal(tracker.diagnostics().stages.workingFeedbackMs.samples, 100);

const chat = fs.readFileSync(new URL('../app/chat.js', import.meta.url), 'utf8');
const index = fs.readFileSync(new URL('../app/index.html', import.meta.url), 'utf8');
for (const marker of [
  'CodexChatTiming.createTracker()',
  'beginSubmission()',
  'markWorkingVisible(codexTimingToken)',
  'bindRun(codexTimingToken, data.runId)',
  'observeEvent(runId, eventName, data)'
]) {
  assert.ok(chat.includes(marker), `chat.js missing browser timing marker: ${marker}`);
}
assert.ok(index.includes('codex-chat-timing.js'), 'index.html must load browser timing before chat.js');

console.log('codex browser timing checks passed');
