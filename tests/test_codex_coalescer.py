#!/usr/bin/env python3
"""Deterministic bounds and ordering tests for Codex transient coalescing."""

import os
from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.codex_fast_path import (
    MAX_BUCKET_BYTES,
    MAX_BUCKET_FRAGMENTS,
    MAX_COALESCE_BUCKETS,
    MAX_COALESCE_BYTES,
    CodexTransientCoalescer,
)


class ManualClock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def advance_ms(self, value):
        self.value += int(value * 1_000_000)


def _collector():
    emitted = []
    return emitted, lambda name, payload: emitted.append((name, payload))


def test_first_fragment_bypasses_and_later_fragments_reconstruct_in_order():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(clock_ns=clock, start_dispatcher=False)

    assert coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "A", "text": "A", "activity": {"delta": "A", "text": "A"}}, emit) == "first"
    assert coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "B", "text": "B", "activity": {"delta": "B", "text": "B"}}, emit) == "buffered"
    assert coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "C", "text": "C", "activity": {"delta": "C", "text": "C"}}, emit) == "buffered"
    assert [payload["delta"] for _, payload in emitted] == ["A"]

    clock.advance_ms(32)
    assert coalescer.drain_due() == 0
    clock.advance_ms(2)
    assert coalescer.drain_due() == 1
    assert [payload["delta"] for _, payload in emitted] == ["A", "BC"]
    assert emitted[-1][1]["text"] == "BC"
    assert emitted[-1][1]["activity"]["delta"] == "BC"
    assert emitted[-1][1]["activity"]["text"] == "BC"
    assert emitted[-1][1]["coalescedCount"] == 2


def test_adaptive_window_grows_under_bucket_pressure_but_stays_bounded():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(
        min_ms=33,
        max_ms=100,
        max_buckets=2,
        clock_ns=clock,
        start_dispatcher=False,
    )
    coalescer.submit("agent", "conv-1", "run-1", "message.delta", {"delta": "1"}, emit)
    coalescer.submit("agent", "conv-1", "run-1", "message.delta", {"delta": "2"}, emit)
    coalescer.submit("agent", "conv-2", "run-2", "message.delta", {"delta": "3"}, emit)
    coalescer.submit("agent", "conv-2", "run-2", "message.delta", {"delta": "4"}, emit)

    clock.advance_ms(34)
    assert coalescer.drain_due() == 1  # low-pressure run-1 bucket
    assert [payload["delta"] for _, payload in emitted] == ["1", "3", "2"]
    clock.advance_ms(40)
    assert coalescer.drain_due() == 1  # run-2 used an adaptive ~66 ms window
    assert emitted[-1][1]["delta"] == "4"


def test_fragment_limit_forces_flush_without_dropping_new_fragment():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(max_fragments=2, clock_ns=clock, start_dispatcher=False)
    for text in "ABCD":
        coalescer.submit("agent", "conv", "run", "reasoning.delta", {"text": text}, emit)

    assert [payload["text"] for _, payload in emitted] == ["A", "BC"]
    assert coalescer.diagnostics()["forcedFlushes"] == 1
    assert coalescer.barrier("agent", "conv", "run") == 1
    assert [payload["text"] for _, payload in emitted] == ["A", "BC", "D"]


def test_bucket_and_global_capacity_use_direct_bypass_and_remain_bounded():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(
        max_buckets=1,
        max_bucket_bytes=256,
        max_bytes=256,
        clock_ns=clock,
        start_dispatcher=False,
    )
    coalescer.submit("agent", "conv-1", "run-1", "message.delta", {"delta": "first-1"}, emit)
    coalescer.submit("agent", "conv-1", "run-1", "message.delta", {"delta": "buffered-1"}, emit)
    coalescer.submit("agent", "conv-2", "run-2", "message.delta", {"delta": "first-2"}, emit)
    assert coalescer.submit("agent", "conv-2", "run-2", "message.delta", {"delta": "capacity-bypass"}, emit) == "direct"
    assert coalescer.submit("agent", "conv-3", "run-3", "message.delta", {"delta": "X" * 300}, emit) == "first"
    assert coalescer.submit("agent", "conv-3", "run-3", "message.delta", {"delta": "Y" * 300}, emit) == "direct"

    diagnostics = coalescer.diagnostics()
    assert diagnostics["activeBuckets"] == 1
    assert diagnostics["bufferedBytes"] <= diagnostics["maxBufferedBytes"]
    assert diagnostics["directBypass"] == 2


def test_global_byte_pressure_flushes_older_run_fragment_before_direct_bypass():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(
        max_bucket_bytes=256,
        max_bytes=30,
        clock_ns=clock,
        start_dispatcher=False,
    )

    assert coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "A"}, emit) == "first"
    assert coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "BBBBBBBBBB"}, emit) == "buffered"
    assert coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "CCCCCCCCCC"}, emit) == "direct"

    assert [payload["delta"] for _, payload in emitted] == ["A", "BBBBBBBBBB", "CCCCCCCCCC"]
    assert coalescer.diagnostics()["activeBuckets"] == 0


def test_nested_activity_replace_snapshot_is_never_concatenated():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(clock_ns=clock, start_dispatcher=False)

    for text in ("A", "AB", "ABC"):
        coalescer.submit(
            "agent",
            "conv",
            "run",
            "reasoning.available",
            {"text": text, "activity": {"text": text, "replace": True}},
            emit,
        )

    assert [payload["text"] for _, payload in emitted] == ["A", "AB", "ABC"]
    assert [payload["activity"]["text"] for _, payload in emitted] == ["A", "AB", "ABC"]
    assert coalescer.diagnostics()["activeBuckets"] == 0


def test_event_class_change_replace_and_barrier_preserve_order():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(clock_ns=clock, start_dispatcher=False)
    coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "A"}, emit)
    coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "B"}, emit)
    coalescer.submit("agent", "conv", "run", "reasoning.delta", {"text": "C"}, emit)
    coalescer.submit("agent", "conv", "run", "reasoning.delta", {"text": "D"}, emit)
    coalescer.submit("agent", "conv", "run", "reasoning.delta", {"text": "E", "replace": True}, emit)
    coalescer.submit("agent", "conv", "run", "tool.started", {"text": "F"}, emit)

    assert [(name, payload.get("delta") or payload.get("text")) for name, payload in emitted] == [
        ("message.delta", "A"),
        ("message.delta", "B"),
        ("reasoning.delta", "CD"),
        ("reasoning.delta", "E"),
        ("tool.started", "F"),
    ]
    assert coalescer.diagnostics()["activeBuckets"] == 0


def test_end_and_close_flush_and_cleanup_all_memory():
    clock = ManualClock()
    emitted, emit = _collector()
    coalescer = CodexTransientCoalescer(clock_ns=clock, start_dispatcher=False)
    for run_id in ("run-1", "run-2"):
        coalescer.submit("agent", "conv", run_id, "message.delta", {"delta": "A"}, emit)
        coalescer.submit("agent", "conv", run_id, "message.delta", {"delta": "B"}, emit)
    assert coalescer.end("agent", "conv", "run-1") == 1
    coalescer.close()
    assert coalescer.diagnostics()["activeBuckets"] == 0
    assert coalescer.diagnostics()["bufferedBytes"] == 0


def test_default_hard_bounds_match_confirmed_design():
    coalescer = CodexTransientCoalescer(start_dispatcher=False)
    diagnostics = coalescer.diagnostics()
    assert diagnostics["maxBuckets"] == MAX_COALESCE_BUCKETS == 256
    assert diagnostics["maxFragmentsPerBucket"] == MAX_BUCKET_FRAGMENTS == 200
    assert diagnostics["maxBytesPerBucket"] == MAX_BUCKET_BYTES == 64 * 1024
    assert diagnostics["maxBufferedBytes"] == MAX_COALESCE_BYTES == 16 * 1024 * 1024


def test_single_dispatcher_flushes_due_bucket():
    emitted, emit = _collector()
    flushed = threading.Event()

    def notifying_emit(name, payload):
        emit(name, payload)
        if payload.get("coalescedCount"):
            flushed.set()

    coalescer = CodexTransientCoalescer(min_ms=33, max_ms=33, start_dispatcher=True)
    try:
        coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "A"}, notifying_emit)
        coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "B"}, notifying_emit)
        assert flushed.wait(0.5)
        assert [payload["delta"] for _, payload in emitted] == ["A", "B"]
        assert coalescer.diagnostics()["dispatcherFlushes"] == 1
    finally:
        coalescer.close()


def test_barrier_waits_for_dispatcher_flush_already_in_flight():
    emitted = []
    flush_entered = threading.Event()
    release_flush = threading.Event()

    def blocking_emit(name, payload):
        if payload.get("coalescedCount"):
            flush_entered.set()
            release_flush.wait(1)
        emitted.append((name, payload.get("delta") or payload.get("text")))

    coalescer = CodexTransientCoalescer(min_ms=10, max_ms=10, start_dispatcher=True)
    try:
        coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "A"}, blocking_emit)
        coalescer.submit("agent", "conv", "run", "message.delta", {"delta": "B"}, blocking_emit)
        assert flush_entered.wait(0.5)
        barrier_done = threading.Event()

        def publish_barrier():
            coalescer.submit("agent", "conv", "run", "tool.started", {"text": "tool"}, blocking_emit)
            barrier_done.set()

        worker = threading.Thread(target=publish_barrier)
        worker.start()
        assert not barrier_done.wait(0.05)
        assert emitted == [("message.delta", "A")]
        release_flush.set()
        worker.join(1)
        assert barrier_done.is_set()
        assert emitted == [("message.delta", "A"), ("message.delta", "B"), ("tool.started", "tool")]
    finally:
        release_flush.set()
        coalescer.close()
