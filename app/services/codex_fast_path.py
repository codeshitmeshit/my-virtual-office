"""Guarded configuration and runtime primitives for the Codex chat fast path."""

from __future__ import annotations

from collections import OrderedDict
from collections import deque
import copy
from dataclasses import dataclass
import json
import hashlib
import math
import threading
import time
from typing import Any, Callable, Mapping

from .provider_events import sanitize_payload


TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
TERMINAL_STATUSES = {"completed", "done", "success", "failed", "error", "cancelled", "canceled"}
TERMINAL_JOURNAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.canceled"}
MAX_LIVE_SCOPES = 4_096
MAX_COALESCE_BUCKETS = 256
MAX_BUCKET_FRAGMENTS = 200
MAX_BUCKET_BYTES = 64 * 1024
MAX_COALESCE_BYTES = 16 * 1024 * 1024
COALESCE_EVENT_NAMES = {"message.delta", "message.delta.text", "reasoning.available", "reasoning.delta"}
TIMING_STAGES = {
    "request_accepted",
    "run_reserved",
    "provider_request_sent",
    "first_native_event",
    "first_displayable_fragment",
    "journal_published",
    "sse_written",
    "terminal_sse_written",
    "provider_terminal",
    "durable_terminal_committed",
}
TIMING_METRICS = {f"accepted_to_{stage}_ms" for stage in TIMING_STAGES if stage != "request_accepted"} | {
    "terminal_tail_ms",
    "terminal_fence_wait_ms",
}


class CodexFastPathTelemetry:
    """Bounded content-free run timing and fixed-cardinality counters."""

    def __init__(self, *, max_runs: int = 1024, max_samples: int = 2048, clock_ns: Callable[[], int] | None = None) -> None:
        self.max_runs = max(1, int(max_runs))
        self.max_samples = max(1, int(max_samples))
        self._clock_ns = clock_ns or time.monotonic_ns
        self._lock = threading.Lock()
        self._runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._samples = {metric: deque(maxlen=self.max_samples) for metric in TIMING_METRICS}
        self._counters = {
            "busyByConversation": 0,
            "busyByCapacity": 0,
            "startedRuns": 0,
            "evictedRuns": 0,
        }

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]

    def start(self, run_id: str, conversation_id: str = "", *, at_ns: int | None = None) -> None:
        run_id = str(run_id or "")[:240]
        if not run_id:
            return
        now_ns = int(at_ns if at_ns is not None else self._clock_ns())
        with self._lock:
            if run_id not in self._runs:
                self._counters["startedRuns"] += 1
            self._runs[run_id] = {
                "runDigest": self._digest(run_id),
                "conversationDigest": self._digest(str(conversation_id or "")),
                "stages": {"request_accepted": now_ns},
            }
            self._runs.move_to_end(run_id)
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)
                self._counters["evictedRuns"] += 1

    def mark(self, run_id: str, stage: str, *, at_ns: int | None = None) -> bool:
        run_id = str(run_id or "")[:240]
        stage = str(stage or "")
        if not run_id or stage not in TIMING_STAGES:
            return False
        now_ns = int(at_ns if at_ns is not None else self._clock_ns())
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                record = {"runDigest": self._digest(run_id), "conversationDigest": self._digest(""), "stages": {}}
                self._runs[run_id] = record
            stages = record["stages"]
            if stage in stages:
                return False
            stages[stage] = now_ns
            self._runs.move_to_end(run_id)
            accepted_ns = stages.get("request_accepted")
            if accepted_ns is not None and stage != "request_accepted":
                self._samples[f"accepted_to_{stage}_ms"].append(max(0.0, (now_ns - accepted_ns) / 1_000_000))
            if "provider_terminal" in stages and "terminal_sse_written" in stages and not record.get("terminalTailObserved"):
                self._samples["terminal_tail_ms"].append(max(0.0, (stages["terminal_sse_written"] - stages["provider_terminal"]) / 1_000_000))
                record["terminalTailObserved"] = True
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)
                self._counters["evictedRuns"] += 1
            return True

    def observe(self, metric: str, value_ms: float) -> bool:
        metric = str(metric or "")
        if metric not in TIMING_METRICS:
            return False
        try:
            value = max(0.0, float(value_ms))
        except (TypeError, ValueError):
            return False
        with self._lock:
            self._samples[metric].append(value)
        return True

    def increment_busy(self, reason: str) -> None:
        key = "busyByCapacity" if str(reason or "").lower() == "capacity" else "busyByConversation"
        with self._lock:
            self._counters[key] += 1

    @staticmethod
    def _summary(values) -> dict[str, float | int]:
        ordered = sorted(float(value) for value in values)
        if not ordered:
            return {"samples": 0, "p50Ms": 0.0, "p95Ms": 0.0, "maxMs": 0.0}
        percentile = lambda ratio: ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio) - 1))]
        return {
            "samples": len(ordered),
            "p50Ms": round(percentile(0.50), 3),
            "p95Ms": round(percentile(0.95), 3),
            "maxMs": round(ordered[-1], 3),
        }

    def diagnostics(self, *, recent_limit: int = 20) -> dict[str, Any]:
        with self._lock:
            samples = {key: list(values) for key, values in self._samples.items()}
            recent = []
            for record in list(self._runs.values())[-max(0, min(int(recent_limit), 100)):]:
                stages = record.get("stages") or {}
                accepted_ns = stages.get("request_accepted")
                relative = {
                    stage: round((value - accepted_ns) / 1_000_000, 3)
                    for stage, value in stages.items()
                    if accepted_ns is not None and value >= accepted_ns
                }
                recent.append({
                    "runDigest": record.get("runDigest") or "",
                    "conversationDigest": record.get("conversationDigest") or "",
                    "stageMs": relative,
                })
            counters = dict(self._counters)
            retained = len(self._runs)
        return {
            **counters,
            "retainedRuns": retained,
            "maxRuns": self.max_runs,
            "maxSamplesPerMetric": self.max_samples,
            "histograms": {key: self._summary(values) for key, values in samples.items()},
            "recentRuns": recent,
        }


@dataclass(frozen=True)
class CodexFastPathSettings:
    requested_enabled: bool = False
    enabled: bool = False
    valid: bool = True
    max_concurrent_turns: int = 1
    coalesce_min_ms: int = 33
    coalesce_max_ms: int = 100
    issues: tuple[str, ...] = ()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "requestedEnabled": self.requested_enabled,
            "enabled": self.enabled,
            "valid": self.valid,
            "startupOnly": True,
            "maxConcurrentTurns": self.max_concurrent_turns,
            "streamCoalesceMinMs": self.coalesce_min_ms,
            "streamCoalesceMaxMs": self.coalesce_max_ms,
            "issues": list(self.issues),
        }


@dataclass
class _LiveScope:
    sequence: int = 0
    active: int = 0
    last_used_ns: int = 0
    last_event: dict[str, Any] | None = None


@dataclass
class _CoalesceBucket:
    event_name: str
    emit: Callable[[str, dict[str, Any]], Any]
    payloads: list[dict[str, Any]]
    text_key: str
    byte_count: int
    created_ns: int
    due_ns: int
    ordinal: int


class CodexTransientCoalescer:
    """Bounded transient fragment coalescing with one optional dispatcher."""

    def __init__(
        self,
        *,
        min_ms: int = 33,
        max_ms: int = 100,
        max_buckets: int = MAX_COALESCE_BUCKETS,
        max_fragments: int = MAX_BUCKET_FRAGMENTS,
        max_bucket_bytes: int = MAX_BUCKET_BYTES,
        max_bytes: int = MAX_COALESCE_BYTES,
        clock_ns: Callable[[], int] | None = None,
        start_dispatcher: bool = True,
    ) -> None:
        self.min_ns = max(1, int(min_ms)) * 1_000_000
        self.max_ns = max(self.min_ns, int(max_ms) * 1_000_000)
        self.max_buckets = max(1, int(max_buckets))
        self.max_fragments = max(1, int(max_fragments))
        self.max_bucket_bytes = max(1, int(max_bucket_bytes))
        self.max_bytes = max(1, int(max_bytes))
        self._clock_ns = clock_ns or time.monotonic_ns
        self._condition = threading.Condition(threading.Lock())
        self._buckets: OrderedDict[tuple[str, str, str, str], _CoalesceBucket] = OrderedDict()
        self._seen_runs: OrderedDict[tuple[str, str, str], None] = OrderedDict()
        self._total_bytes = 0
        self._ordinal = 0
        self._closed = False
        self._dispatcher = None
        self._counters = {
            "firstFragmentBypass": 0,
            "bufferedFragments": 0,
            "coalescedFragments": 0,
            "forcedFlushes": 0,
            "barrierFlushes": 0,
            "directBypass": 0,
            "dispatcherFlushes": 0,
        }
        if start_dispatcher:
            self._dispatcher = threading.Thread(target=self._dispatch_loop, name="codex-coalescer", daemon=True)
            self._dispatcher.start()

    @staticmethod
    def _run_key(agent_id: str, conversation_id: str, run_id: str) -> tuple[str, str, str]:
        return (str(agent_id or "")[:160], str(conversation_id or "")[:240], str(run_id or "")[:200])

    @staticmethod
    def _text_key(payload: Mapping[str, Any]) -> str:
        for key in ("delta", "text", "thinking", "content"):
            if isinstance(payload.get(key), str):
                return key
        return ""

    @staticmethod
    def _payload_bytes(payload: Mapping[str, Any]) -> int:
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))

    @staticmethod
    def _is_replace_snapshot(payload: Mapping[str, Any]) -> bool:
        activity = payload.get("activity") if isinstance(payload.get("activity"), Mapping) else {}
        return bool(payload.get("replace") or activity.get("replace"))

    def submit(
        self,
        agent_id: str,
        conversation_id: str,
        run_id: str,
        event_name: str,
        payload: dict[str, Any],
        emit: Callable[[str, dict[str, Any]], Any],
    ) -> str:
        run_key = self._run_key(agent_id, conversation_id, run_id)
        name = str(event_name or "provider.activity")
        clean_payload = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        text_key = self._text_key(clean_payload)
        size = self._payload_bytes(clean_payload)
        emissions: list[tuple[Callable, str, dict[str, Any]]] = []
        disposition = "buffered"
        with self._condition:
            emissions.extend(self._take_due_locked(self._clock_ns(), dispatcher=False))
            if self._closed or name not in COALESCE_EVENT_NAMES or not text_key or self._is_replace_snapshot(clean_payload):
                emissions.extend(self._take_run_locked(run_key, barrier=True))
                emissions.append((emit, name, clean_payload))
                self._counters["directBypass"] += 1
                disposition = "direct"
            elif run_key not in self._seen_runs:
                self._remember_run_locked(run_key)
                emissions.append((emit, name, clean_payload))
                self._counters["firstFragmentBypass"] += 1
                disposition = "first"
            else:
                # Different transient classes are ordering barriers; only
                # compatible adjacent fragments may share a bucket.
                for key in list(self._buckets):
                    if key[:3] == run_key and key[3] != name:
                        emissions.extend(self._take_bucket_locked(key, barrier=True))
                bucket_key = (*run_key, name)
                bucket = self._buckets.get(bucket_key)
                if bucket and bucket.text_key != text_key:
                    emissions.extend(self._take_bucket_locked(bucket_key, barrier=True))
                    bucket = None
                if bucket and (
                    len(bucket.payloads) >= self.max_fragments
                    or bucket.byte_count + size > self.max_bucket_bytes
                ):
                    emissions.extend(self._take_bucket_locked(bucket_key, forced=True))
                    bucket = None
                if size > self.max_bucket_bytes or self._total_bytes + size > self.max_bytes or (bucket is None and len(self._buckets) >= self.max_buckets):
                    # A direct fragment cannot overtake older buffered content
                    # from the same run when any capacity bound is reached.
                    emissions.extend(self._take_run_locked(run_key, barrier=True))
                    emissions.append((emit, name, clean_payload))
                    self._counters["directBypass"] += 1
                    disposition = "direct"
                else:
                    now_ns = self._clock_ns()
                    created = bucket is None
                    if bucket is None:
                        self._ordinal += 1
                        due_ns = now_ns + self._adaptive_window_locked()
                        bucket = _CoalesceBucket(name, emit, [], text_key, 0, now_ns, due_ns, self._ordinal)
                        self._buckets[bucket_key] = bucket
                    bucket.payloads.append(clean_payload)
                    bucket.byte_count += size
                    self._total_bytes += size
                    if not created:
                        bucket.due_ns = min(bucket.created_ns + self.max_ns, now_ns + self._adaptive_window_locked())
                    self._counters["bufferedFragments"] += 1
                    if len(bucket.payloads) >= self.max_fragments or bucket.byte_count >= self.max_bucket_bytes:
                        emissions.extend(self._take_bucket_locked(bucket_key, forced=True))
                        disposition = "forced"
                    else:
                        self._buckets.move_to_end(bucket_key)
                        self._condition.notify()
            self._emit_all(emissions)
        return disposition

    def publish_event(
        self,
        provider_kind: str,
        agent_id: str,
        conversation_id: str,
        event_name: str,
        payload: dict[str, Any],
        run_id: str,
        publish: Callable[[str, dict[str, Any]], Any],
    ) -> bool:
        """Publish immediately or accept for later publication through one callback."""
        published = {"result": True}

        def emit(name, data):
            published["result"] = publish(name, data)
            return published["result"]

        disposition = self.submit(agent_id, conversation_id, run_id, event_name, payload, emit)
        if str(event_name or "").lower() in TERMINAL_JOURNAL_EVENTS:
            self.end(agent_id, conversation_id, run_id)
        return True if disposition == "buffered" else bool(published["result"])

    def barrier(self, agent_id: str, conversation_id: str, run_id: str) -> int:
        run_key = self._run_key(agent_id, conversation_id, run_id)
        with self._condition:
            emissions = self._take_run_locked(run_key, barrier=True)
            self._emit_all(emissions)
        return len(emissions)

    def drain_due(self) -> int:
        with self._condition:
            emissions = self._take_due_locked(self._clock_ns(), dispatcher=False)
            self._emit_all(emissions)
        return len(emissions)

    def end(self, agent_id: str, conversation_id: str, run_id: str) -> int:
        run_key = self._run_key(agent_id, conversation_id, run_id)
        count = self.barrier(*run_key)
        with self._condition:
            self._seen_runs.pop(run_key, None)
        return count

    def close(self) -> None:
        with self._condition:
            self._closed = True
            emissions = self._take_all_locked(barrier=True)
            self._seen_runs.clear()
            self._condition.notify_all()
            self._emit_all(emissions)
        if self._dispatcher and self._dispatcher is not threading.current_thread():
            self._dispatcher.join(timeout=1.0)

    def diagnostics(self) -> dict[str, int]:
        with self._condition:
            return {
                **self._counters,
                "activeBuckets": len(self._buckets),
                "bufferedBytes": self._total_bytes,
                "maxBuckets": self.max_buckets,
                "maxFragmentsPerBucket": self.max_fragments,
                "maxBytesPerBucket": self.max_bucket_bytes,
                "maxBufferedBytes": self.max_bytes,
            }

    def _remember_run_locked(self, run_key: tuple[str, str, str]) -> None:
        self._seen_runs[run_key] = None
        self._seen_runs.move_to_end(run_key)
        while len(self._seen_runs) > self.max_buckets * 2:
            candidate = next(
                (item for item in self._seen_runs if not any(key[:3] == item for key in self._buckets)),
                None,
            )
            if candidate is None:
                break
            self._seen_runs.pop(candidate, None)

    def _adaptive_window_locked(self) -> int:
        pressure = max(
            len(self._buckets) / self.max_buckets,
            self._total_bytes / self.max_bytes,
        )
        return int(self.min_ns + min(1.0, pressure) * (self.max_ns - self.min_ns))

    def _take_bucket_locked(self, key, *, forced=False, barrier=False, dispatcher=False):
        bucket = self._buckets.pop(key, None)
        if not bucket:
            return []
        self._total_bytes = max(0, self._total_bytes - bucket.byte_count)
        payload = self._merge(bucket)
        self._counters["coalescedFragments"] += len(bucket.payloads)
        if forced:
            self._counters["forcedFlushes"] += 1
        if barrier:
            self._counters["barrierFlushes"] += 1
        if dispatcher:
            self._counters["dispatcherFlushes"] += 1
        return [(bucket.emit, bucket.event_name, payload)]

    def _take_run_locked(self, run_key, *, barrier=False):
        keys = sorted(
            (key for key in self._buckets if key[:3] == run_key),
            key=lambda key: self._buckets[key].ordinal,
        )
        emissions = []
        for key in keys:
            emissions.extend(self._take_bucket_locked(key, barrier=barrier))
        return emissions

    def _take_due_locked(self, now_ns: int, *, dispatcher: bool):
        keys = sorted(
            (key for key, bucket in self._buckets.items() if bucket.due_ns <= now_ns),
            key=lambda key: self._buckets[key].ordinal,
        )
        emissions = []
        for key in keys:
            emissions.extend(self._take_bucket_locked(key, dispatcher=dispatcher))
        return emissions

    def _take_all_locked(self, *, barrier=False):
        keys = sorted(self._buckets, key=lambda key: self._buckets[key].ordinal)
        emissions = []
        for key in keys:
            emissions.extend(self._take_bucket_locked(key, barrier=barrier))
        return emissions

    @staticmethod
    def _merge(bucket: _CoalesceBucket) -> dict[str, Any]:
        payload = copy.deepcopy(bucket.payloads[0])
        for key, value in bucket.payloads[-1].items():
            if key not in {"delta", "text", "thinking", "content", "activity"}:
                payload[key] = copy.deepcopy(value)
        for text_key in ("delta", "text", "thinking", "content"):
            if any(isinstance(item.get(text_key), str) for item in bucket.payloads):
                payload[text_key] = "".join(str(item.get(text_key) or "") for item in bucket.payloads)
        activities = [item.get("activity") for item in bucket.payloads if isinstance(item.get("activity"), dict)]
        if activities:
            activity = copy.deepcopy(activities[0])
            for key, value in activities[-1].items():
                if key not in {"delta", "text", "thinking", "content"}:
                    activity[key] = copy.deepcopy(value)
            for text_key in ("delta", "text", "thinking", "content"):
                if any(isinstance(item.get(text_key), str) for item in activities):
                    activity[text_key] = "".join(str(item.get(text_key) or "") for item in activities)
            activity["coalescedCount"] = len(activities)
            payload["activity"] = activity
        payload["coalescedCount"] = len(bucket.payloads)
        return payload

    @staticmethod
    def _emit_all(emissions) -> None:
        for emit, event_name, payload in emissions:
            emit(event_name, payload)

    def _dispatch_loop(self) -> None:
        while True:
            with self._condition:
                if self._closed:
                    return
                now_ns = self._clock_ns()
                emissions = self._take_due_locked(now_ns, dispatcher=True)
                if not emissions:
                    due_ns = min((bucket.due_ns for bucket in self._buckets.values()), default=0)
                    timeout = max(0.001, (due_ns - now_ns) / 1_000_000_000) if due_ns else None
                    self._condition.wait(timeout=timeout)
                    continue
                self._emit_all(emissions)


def classify_codex_event(event: Mapping[str, Any] | None) -> str:
    event = event if isinstance(event, Mapping) else {}
    event_type = str(event.get("type") or "").strip().lower()
    status = str(event.get("status") or "").strip().lower()
    if event_type in {"turn", "run"} and status in TERMINAL_STATUSES:
        return "terminal"
    if event_type in {"interaction", "approval"}:
        return "durable_key"
    if event_type in {"message", "assistant_message", "assistant", "text", "output"} and status in TERMINAL_STATUSES:
        return "durable_key"
    if event_type in {"reasoning", "thinking", "message", "assistant_message", "assistant", "text", "output", "activity", "tool", "command"}:
        return "transient"
    return "durable_key"


class CodexEventFastPath:
    """Bounded Codex event normalization without owning run or SSE state."""

    def __init__(
        self,
        settings: CodexFastPathSettings,
        *,
        max_scopes: int = MAX_LIVE_SCOPES,
        clock_ns: Callable[[], int] | None = None,
        sanitizer: Callable[[Any], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.max_scopes = max(1, int(max_scopes))
        self._clock_ns = clock_ns or time.monotonic_ns
        self._sanitize = sanitizer or sanitize_payload
        self._lock = threading.Lock()
        self._scopes: OrderedDict[tuple[str, str, str], _LiveScope] = OrderedDict()
        self._conversation_sequences: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._counters = {
            "disabledPassThrough": 0,
            "normalized": 0,
            "transient": 0,
            "durableKey": 0,
            "terminal": 0,
            "scopeEvictions": 0,
            "capacityBypass": 0,
        }

    @staticmethod
    def scope_key(agent_id: str, conversation_id: str, run_id: str) -> tuple[str, str, str]:
        return (
            str(agent_id or "")[:160],
            str(conversation_id or "")[:240],
            str(run_id or "")[:200],
        )

    def begin(self, agent_id: str, conversation_id: str, run_id: str, *, initial_sequence: int = 0) -> bool:
        if not self.settings.enabled:
            return False
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._get_or_create_locked(key)
            if scope is None:
                self._counters["capacityBypass"] += 1
                return False
            scope.active += 1
            scope.last_used_ns = self._clock_ns()
            sequence_key = key[:2]
            self._conversation_sequences[sequence_key] = max(
                self._conversation_sequences.get(sequence_key, 0),
                max(0, int(initial_sequence or 0)),
            )
            self._conversation_sequences.move_to_end(sequence_key)
            self._prune_sequences_locked()
            return True

    def end(self, agent_id: str, conversation_id: str, run_id: str) -> None:
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._scopes.get(key)
            if not scope:
                return
            scope.active = max(0, scope.active - 1)
            scope.last_used_ns = self._clock_ns()
            self._scopes.move_to_end(key)
            self._prune_locked()

    def process_event(
        self,
        agent_id: str,
        conversation_id: str,
        run_id: str,
        event: dict[str, Any],
        *,
        legacy_callback: Callable[[dict[str, Any]], Any] | None = None,
    ) -> Any:
        if not self.settings.enabled:
            with self._lock:
                self._counters["disabledPassThrough"] += 1
            return legacy_callback(event) if legacy_callback else event

        event_class = classify_codex_event(event)
        cleaned = self._sanitize(event)
        cleaned = copy.deepcopy(cleaned) if isinstance(cleaned, dict) else {}
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._get_or_create_locked(key)
            if scope is None:
                self._counters["capacityBypass"] += 1
                return legacy_callback(event) if legacy_callback else event
            sequence_key = key[:2]
            sequence = self._conversation_sequences.get(sequence_key, 0) + 1
            self._conversation_sequences[sequence_key] = sequence
            self._conversation_sequences.move_to_end(sequence_key)
            self._prune_sequences_locked()
            scope.sequence = sequence
            scope.last_used_ns = self._clock_ns()
            cleaned.setdefault("providerSequence", int(event.get("sequence") or 0))
            cleaned["sequence"] = sequence
            cleaned["agentId"] = key[0]
            cleaned["conversationId"] = key[1]
            if key[2]:
                cleaned.setdefault("runId", key[2])
            cleaned["eventClass"] = event_class
            scope.last_event = copy.deepcopy(cleaned)
            self._scopes.move_to_end(key)
            self._counters["normalized"] += 1
            counter = "transient" if event_class == "transient" else "terminal" if event_class == "terminal" else "durableKey"
            self._counters[counter] += 1
        return cleaned

    def live_snapshot(self, agent_id: str, conversation_id: str, run_id: str) -> dict[str, Any] | None:
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._scopes.get(key)
            return copy.deepcopy(scope.last_event) if scope and scope.last_event else None

    def live_events(self, agent_id: str, conversation_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        prefix = self.scope_key(agent_id, conversation_id, "")[:2]
        with self._lock:
            events = [
                copy.deepcopy(scope.last_event)
                for key, scope in self._scopes.items()
                if key[:2] == prefix and scope.last_event and int(scope.last_event.get("sequence") or 0) > int(after or 0)
            ]
        return sorted(events, key=lambda item: int(item.get("sequence") or 0))

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            active = sum(scope.active for scope in self._scopes.values())
            return {
                **self.settings.diagnostics(),
                **self._counters,
                "liveScopes": len(self._scopes),
                "activeScopes": active,
                "maxLiveScopes": self.max_scopes,
            }

    def _get_or_create_locked(self, key: tuple[str, str, str]) -> _LiveScope | None:
        scope = self._scopes.get(key)
        if scope is not None:
            self._scopes.move_to_end(key)
            return scope
        self._prune_locked(required=1)
        if len(self._scopes) >= self.max_scopes:
            return None
        scope = _LiveScope(last_used_ns=self._clock_ns())
        self._scopes[key] = scope
        return scope

    def _prune_locked(self, required: int = 0) -> None:
        target = max(0, self.max_scopes - max(0, int(required)))
        for key, scope in list(self._scopes.items()):
            if len(self._scopes) <= target:
                break
            if scope.active == 0:
                self._scopes.pop(key, None)
                self._counters["scopeEvictions"] += 1

    def _prune_sequences_locked(self) -> None:
        while len(self._conversation_sequences) > self.max_scopes:
            self._conversation_sequences.popitem(last=False)


def _configured_value(environ: Mapping[str, Any], env_key: str, config: Mapping[str, Any], config_key: str, default: Any):
    raw = environ.get(env_key)
    if raw is not None and str(raw).strip() != "":
        return raw
    return config.get(config_key, default)


def _strict_bool(value: Any, default: bool, issue: str, issues: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    issues.append(issue)
    return default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int, issue: str, issues: list[str]) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        issues.append(issue)
        return default
    if parsed < minimum or parsed > maximum:
        issues.append(issue)
        return default
    return parsed


def load_codex_fast_path_settings(environ: Mapping[str, Any], codex_config: Mapping[str, Any] | None = None) -> CodexFastPathSettings:
    codex_config = codex_config if isinstance(codex_config, Mapping) else {}
    nested = codex_config.get("fastPath")
    fast_config = nested if isinstance(nested, Mapping) else codex_config
    issues: list[str] = []
    requested_enabled = _strict_bool(
        _configured_value(environ, "VO_CODEX_CHAT_FAST_PATH_ENABLED", fast_config, "enabled", False),
        False,
        "invalid_enabled",
        issues,
    )
    max_turns = _bounded_int(
        _configured_value(environ, "VO_CODEX_MAX_CONCURRENT_TURNS", fast_config, "maxConcurrentTurns", 1),
        1,
        1,
        4,
        "invalid_max_concurrent_turns",
        issues,
    )
    minimum_ms = _bounded_int(
        _configured_value(environ, "VO_CODEX_STREAM_COALESCE_MIN_MS", fast_config, "streamCoalesceMinMs", 33),
        33,
        33,
        100,
        "invalid_coalesce_min_ms",
        issues,
    )
    maximum_ms = _bounded_int(
        _configured_value(environ, "VO_CODEX_STREAM_COALESCE_MAX_MS", fast_config, "streamCoalesceMaxMs", 100),
        100,
        33,
        100,
        "invalid_coalesce_max_ms",
        issues,
    )
    if maximum_ms < minimum_ms:
        issues.append("invalid_coalesce_window")
        minimum_ms, maximum_ms = 33, 100
    valid = not issues
    return CodexFastPathSettings(
        requested_enabled=requested_enabled,
        enabled=requested_enabled and valid,
        valid=valid,
        max_concurrent_turns=max_turns,
        coalesce_min_ms=minimum_ms,
        coalesce_max_ms=maximum_ms,
        issues=tuple(dict.fromkeys(issues)),
    )
