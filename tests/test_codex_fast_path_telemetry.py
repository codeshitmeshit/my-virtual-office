#!/usr/bin/env python3
"""Bounded, content-free Codex fast-path telemetry tests."""

import time

from app.services.codex_fast_path import CodexFastPathTelemetry


class ManualClock:
    def __init__(self):
        self.value = 1_000_000_000

    def __call__(self):
        return self.value

    def advance_ms(self, value):
        self.value += int(value * 1_000_000)


def test_timeline_histograms_are_bounded_correlated_and_content_free():
    clock = ManualClock()
    telemetry = CodexFastPathTelemetry(max_runs=2, max_samples=3, clock_ns=clock)
    secret_canary = "prompt-secret-Bearer-abcdefghijklmnop-/Users/private/file"
    telemetry.start(f"run-{secret_canary}", f"conversation-{secret_canary}")
    clock.advance_ms(4)
    assert telemetry.mark(f"run-{secret_canary}", "run_reserved") is True
    clock.advance_ms(6)
    assert telemetry.mark(f"run-{secret_canary}", "provider_request_sent") is True
    assert telemetry.mark(f"run-{secret_canary}", "provider_request_sent") is False
    clock.advance_ms(10)
    telemetry.mark(f"run-{secret_canary}", "provider_terminal")
    clock.advance_ms(3)
    telemetry.mark(f"run-{secret_canary}", "terminal_sse_written")
    telemetry.observe("terminal_fence_wait_ms", 1.25)
    telemetry.increment_busy("conversation")
    telemetry.increment_busy("capacity")
    telemetry.start("run-two", "conversation-two")
    telemetry.start("run-three", "conversation-three")

    diagnostics = telemetry.diagnostics(recent_limit=10)
    rendered = str(diagnostics)
    assert secret_canary not in rendered
    assert diagnostics["retainedRuns"] == diagnostics["maxRuns"] == 2
    assert diagnostics["evictedRuns"] == 1
    assert diagnostics["busyByConversation"] == diagnostics["busyByCapacity"] == 1
    assert diagnostics["histograms"]["accepted_to_run_reserved_ms"]["p95Ms"] == 4.0
    assert diagnostics["histograms"]["terminal_tail_ms"]["p95Ms"] == 3.0
    assert diagnostics["histograms"]["terminal_fence_wait_ms"]["p95Ms"] == 1.25
    assert all(len(item["runDigest"]) == 12 and len(item["conversationDigest"]) == 12 for item in diagnostics["recentRuns"])


def test_sample_capacity_discards_old_values_without_growing_cardinality():
    telemetry = CodexFastPathTelemetry(max_runs=4, max_samples=3)
    for value in range(10):
        telemetry.observe("terminal_fence_wait_ms", value)
    summary = telemetry.diagnostics()["histograms"]["terminal_fence_wait_ms"]
    assert summary == {"samples": 3, "p50Ms": 8.0, "p95Ms": 9.0, "maxMs": 9.0}
    assert telemetry.observe("prompt_text", 1) is False
    assert telemetry.mark("run", "unbounded-user-stage") is False


def test_marking_overhead_remains_microsecond_scale():
    telemetry = CodexFastPathTelemetry(max_runs=256, max_samples=512)
    samples = []
    for index in range(1000):
        started = time.perf_counter_ns()
        run_id = f"run-{index}"
        telemetry.start(run_id, f"conversation-{index % 8}")
        telemetry.mark(run_id, "run_reserved")
        samples.append((time.perf_counter_ns() - started) / 1_000)
    samples.sort()
    p95_us = samples[int(len(samples) * 0.95) - 1]
    assert p95_us < 200


def test_terminal_tail_uses_terminal_sse_not_first_sse():
    clock = ManualClock()
    telemetry = CodexFastPathTelemetry(clock_ns=clock)
    telemetry.start("run", "conversation")
    clock.advance_ms(1)
    telemetry.mark("run", "sse_written")
    clock.advance_ms(9)
    telemetry.mark("run", "provider_terminal")
    clock.advance_ms(5)
    telemetry.mark("run", "terminal_sse_written")
    summary = telemetry.diagnostics()["histograms"]["terminal_tail_ms"]
    assert summary["p95Ms"] == 5.0
