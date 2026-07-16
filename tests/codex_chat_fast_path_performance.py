#!/usr/bin/env python3
"""Deterministic failing-before baseline for the warm Codex chat fast path.

The fixture intentionally exercises the current production path end to end:
background run reservation, an already-started fake Codex app-server, resumed
thread execution, native callbacks, legacy activity/progress persistence,
Provider journal publication, and run SSE framing.  It records operation counts
and stage latency without using a real model or external credentials.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
TESTS_DIR = ROOT / "tests"
for entry in (str(APP_DIR), str(TESTS_DIR), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-codex-fast-path-import-"))

import server  # noqa: E402
from providers.codex_app_server import CodexAppServerClient  # noqa: E402
from services.provider_events import ProviderEventJournal  # noqa: E402
from services.provider_registry import ProviderRunRepository  # noqa: E402
from services.provider_runs import ProviderRunCoordinator  # noqa: E402
from test_codex_bridge import make_fake_codex  # noqa: E402


AGENT = {
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "profile": "local",
    "providerKind": "codex",
    "name": "Codex Local",
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"samples": 0, "p50Ms": 0.0, "p95Ms": 0.0, "maxMs": 0.0}
    return {
        "samples": len(values),
        "p50Ms": round(statistics.median(values), 3),
        "p95Ms": round(percentile(values, 0.95), 3),
        "maxMs": round(max(values), 3),
    }


def delta_ms(later: int | None, earlier: int | None) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier) / 1_000_000


class RecordingWriter(io.BytesIO):
    def __init__(self, timeline: dict[str, Any]):
        super().__init__()
        self.timeline = timeline
        self._lock = threading.Lock()

    def write(self, value):
        now = time.perf_counter_ns()
        with self._lock:
            written = super().write(value)
            text = value.decode("utf-8", errors="replace")
            if "event: run.started" in text:
                self.timeline.setdefault("runStartedSseNs", now)
            event_names = (
                "provider.activity",
                "reasoning.available",
                "message.delta",
                "tool.started",
                "tool.completed",
                "approval.request",
            )
            if any(f"event: {name}" in text for name in event_names):
                self.timeline.setdefault("firstNativeSseNs", now)
            fragment_names = ("provider.activity", "reasoning.available", "message.delta", "tool.started")
            if any(f"event: {name}" in text for name in fragment_names):
                self.timeline.setdefault("firstFragmentSseNs", now)
            payload = {}
            for line in text.splitlines():
                if line.startswith("data: "):
                    try:
                        payload = json.loads(line.removeprefix("data: "))
                    except json.JSONDecodeError:
                        payload = {}
                    break
            if "event: message.delta" in text or payload.get("reply") or payload.get("text"):
                self.timeline.setdefault("firstTextSseNs", now)
            if any(f"event: {name}" in text for name in ("run.completed", "run.failed", "run.cancelled")):
                self.timeline.setdefault("terminalSseNs", now)
            return written

    def flush(self):
        return None


class RecordingHandler:
    def __init__(self, timeline: dict[str, Any]):
        self.headers = {}
        self.status = None
        self.response_headers = []
        self.close_connection = False
        self.wfile = RecordingWriter(timeline)
        self.ready = threading.Event()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        self.ready.set()


class WarmCodexProvider:
    """Thin provider wrapper around the real Codex app-server client."""

    def __init__(self, workspace: str, binary: str):
        self.workspace = workspace
        self.client = CodexAppServerClient(workspace, binary=binary)
        self.current: dict[str, Any] | None = None

    def close(self):
        self.client.close()

    def send_message(
        self,
        message,
        conversation_id="",
        timeout_sec=None,
        thread_id="",
        event_callback=None,
        allow_interaction=False,
        attachments=None,
    ):
        current = self.current
        if current is None:
            raise RuntimeError("performance fixture turn was not prepared")
        current["providerRequestSentNs"] = time.perf_counter_ns()
        if not current["releaseProvider"].wait(timeout=5):
            raise TimeoutError("performance fixture did not release provider")

        def measured_callback(event):
            entered = time.perf_counter_ns()
            current.setdefault("firstNativeEventNs", entered)
            event_type = str(event.get("type") or "").lower()
            status = str(event.get("status") or "").lower()
            if event_type in {"reasoning", "message", "assistant_message", "activity", "tool"}:
                current.setdefault("firstDisplayableEventNs", entered)
            if event_type in {"message", "assistant_message"} and event.get("text"):
                current.setdefault("firstTextEventNs", entered)
            if event_type in {"turn", "run"} and status in {"completed", "done", "success", "failed", "error", "cancelled", "canceled"}:
                current.setdefault("providerTerminalNs", entered)
            event_callback(event)
            current["readerCallbackDurationsMs"].append((time.perf_counter_ns() - entered) / 1_000_000)

        return self.client.execute(
            message,
            thread_id=thread_id,
            timeout_sec=int(timeout_sec or 30),
            event_callback=measured_callback,
            allow_interaction=allow_interaction,
            attachments=attachments,
        )

    def cancel(self, thread_id):
        return self.client.cancel(thread_id)


class CounterPatch:
    def __init__(self):
        self.values = {
            "activityJsonLoads": 0,
            "activityJsonWrites": 0,
            "communicationHistoryLoads": 0,
            "communicationProgressRewrites": 0,
            "communicationAppends": 0,
        }
        self._originals = {}
        self.current: dict[str, Any] | None = None

    def install(self):
        def wrap(name, counter, after=None):
            original = getattr(server, name)
            self._originals[name] = original

            def measured(*args, **kwargs):
                self.values[counter] += 1
                result = original(*args, **kwargs)
                if after:
                    after(args, kwargs, result)
                return result

            setattr(server, name, measured)

        wrap("_load_codex_activity", "activityJsonLoads")
        wrap("_save_codex_activity", "activityJsonWrites")
        wrap("_load_comm_history", "communicationHistoryLoads")
        wrap("_rewrite_comm_events", "communicationProgressRewrites")

        def after_append(args, _kwargs, result):
            event = result if isinstance(result, dict) else (args[0] if args and isinstance(args[0], dict) else {})
            if self.current is not None and event.get("conversationId") == self.current.get("conversationId"):
                if event.get("direction") == "reply" or event.get("operation") in {"provider_terminal", "provider_result"}:
                    self.current.setdefault("durableTerminalCommittedNs", time.perf_counter_ns())

        wrap("_append_comm_event", "communicationAppends", after_append)

    def restore(self):
        for name, original in self._originals.items():
            setattr(server, name, original)

    def snapshot(self):
        return dict(self.values)


def counter_delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: int(after.get(key, 0) - before.get(key, 0)) for key in after}


def summarized_counts(rows: list[dict[str, int]]) -> dict[str, dict[str, float | int]]:
    result = {}
    for key in rows[0] if rows else ():
        values = [row[key] for row in rows]
        result[key] = {
            "total": sum(values),
            "perTurnMedian": round(statistics.median(values), 3),
            "perTurnMax": max(values),
        }
    return result


def stage_summary(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    return distribution([float(row[key]) for row in rows if row.get(key) is not None])


def trend_summary(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    midpoint = max(1, len(rows) // 2)
    return {
        "firstHalf": stage_summary(rows[:midpoint], key),
        "secondHalf": stage_summary(rows[midpoint:], key),
    }


def run_fixture(warmups: int, runs: int) -> dict[str, Any]:
    old_values = {
        "STATUS_DIR": server.STATUS_DIR,
        "get_roster": server.get_roster,
        "_codex_provider_from_config": server._codex_provider_from_config,
        "PROVIDER_RUN_REPOSITORY": server.PROVIDER_RUN_REPOSITORY,
        "PROVIDER_EVENT_JOURNAL": server.PROVIDER_EVENT_JOURNAL,
        "PROVIDER_RUN_COORDINATOR": server.PROVIDER_RUN_COORDINATOR,
        "PROVIDER_SSE_TRANSPORT": server.PROVIDER_SSE_TRANSPORT,
    }
    counter = CounterPatch()
    provider = None
    rows = []
    failures = []
    with tempfile.TemporaryDirectory(prefix="vo-codex-fast-path-baseline-") as tmp:
        status_dir = os.path.join(tmp, "status")
        workspace = os.path.join(tmp, "workspace")
        os.makedirs(status_dir, exist_ok=True)
        os.makedirs(workspace, exist_ok=True)
        server.STATUS_DIR = status_dir
        server.get_roster = lambda: [AGENT]
        repository = ProviderRunRepository(retention_ms=10 * 60 * 1000)
        journal = ProviderEventJournal(max_events=4000)
        server.PROVIDER_RUN_REPOSITORY = repository
        server.PROVIDER_EVENT_JOURNAL = journal
        server.PROVIDER_RUN_COORDINATOR = ProviderRunCoordinator(
            repository,
            journal,
            event_pipeline=server._CODEX_EVENT_COALESCER,
            telemetry=server._CODEX_FAST_PATH_TELEMETRY,
        )
        server.PROVIDER_SSE_TRANSPORT = server._provider_sse_transport_for(repository, journal)
        provider = WarmCodexProvider(workspace, make_fake_codex(tmp))
        server._codex_provider_from_config = lambda: provider
        counter.install()
        conversation_id = "fast-path-warm-conversation"
        server._set_codex_thread_id("codex-local", conversation_id, "thr_fake")
        total = warmups + runs
        measured_counter_start = None
        try:
            for index in range(total):
                if index == warmups:
                    measured_counter_start = counter.snapshot()
                timeline: dict[str, Any] = {
                    "conversationId": conversation_id,
                    "releaseProvider": threading.Event(),
                    "readerCallbackDurationsMs": [],
                }
                provider.current = timeline
                counter.current = timeline
                counts_before = counter.snapshot()
                timeline["browserSubmitNs"] = time.perf_counter_ns()
                # The production browser sets working state synchronously before fetch.
                timeline["browserWorkingVisibleNs"] = time.perf_counter_ns()
                started = server._handle_codex_run_start({
                    "agentId": "codex-local",
                    "message": "change one file",
                    "conversationId": conversation_id,
                    "fromType": "human",
                    "fromDisplayName": "User",
                    "sourceApp": "virtual-office",
                    "sourceSurface": "chat-window",
                    "idempotencyKey": f"fast-path-baseline-{index}",
                    "timeoutSec": 30,
                })
                timeline["runAcceptedNs"] = time.perf_counter_ns()
                if not started.get("ok") or not started.get("runId"):
                    failures.append({"index": index, "stage": "start", "status": started.get("status")})
                    continue
                run_id = started["runId"]
                handler = RecordingHandler(timeline)
                stream = threading.Thread(target=server._handle_codex_run_events, args=(handler, run_id), daemon=True)
                stream.start()
                if not handler.ready.wait(timeout=2):
                    failures.append({"index": index, "stage": "sse_headers"})
                    timeline["releaseProvider"].set()
                    continue
                timeline["releaseProvider"].set()
                stream.join(timeout=10)
                if stream.is_alive():
                    failures.append({"index": index, "stage": "terminal_sse_timeout"})
                    continue
                meta = repository.get(run_id) or {}
                if not meta.get("terminal") or not (meta.get("result") or {}).get("ok"):
                    failures.append({"index": index, "stage": "terminal", "status": (meta.get("result") or {}).get("status")})
                    continue
                counts = counter_delta(counter.snapshot(), counts_before)
                row = {
                    "workingFeedbackMs": delta_ms(timeline.get("browserWorkingVisibleNs"), timeline.get("browserSubmitNs")),
                    "runAcceptanceMs": delta_ms(timeline.get("runAcceptedNs"), timeline.get("browserSubmitNs")),
                    "providerRequestMs": delta_ms(timeline.get("providerRequestSentNs"), timeline.get("browserSubmitNs")),
                    "firstNativeEventMs": delta_ms(timeline.get("firstNativeEventNs"), timeline.get("browserSubmitNs")),
                    "firstNativeSseMs": delta_ms(timeline.get("firstNativeSseNs"), timeline.get("browserSubmitNs")),
                    "firstFragmentSseMs": delta_ms(timeline.get("firstFragmentSseNs"), timeline.get("browserSubmitNs")),
                    "firstTextSseMs": delta_ms(timeline.get("firstTextSseNs"), timeline.get("browserSubmitNs")),
                    "providerTerminalMs": delta_ms(timeline.get("providerTerminalNs"), timeline.get("browserSubmitNs")),
                    "durableTerminalCommitMs": delta_ms(timeline.get("durableTerminalCommittedNs"), timeline.get("browserSubmitNs")),
                    "terminalTailMs": delta_ms(timeline.get("terminalSseNs"), timeline.get("providerTerminalNs")),
                    "readerCallbackTotalMs": round(sum(timeline["readerCallbackDurationsMs"]), 6),
                    "readerCallbackMaxMs": round(max(timeline["readerCallbackDurationsMs"], default=0.0), 6),
                    "counts": counts,
                }
                if index >= warmups:
                    rows.append(row)
            measured_counter_end = counter.snapshot()
        finally:
            counter.current = None
            provider.current = None
            counter.restore()
            provider.close()
            with server._CODEX_ACTIVE_LOCK:
                server._CODEX_ACTIVE_OPERATIONS.pop("codex-local", None)
            server._CODEX_OPERATION_LOCKS.pop("codex-local", None)
            for key, value in old_values.items():
                setattr(server, key, value)

    if len(rows) != runs:
        raise AssertionError(f"expected {runs} measured turns, got {len(rows)}; failures={failures[:5]}")
    stages = {
        key: stage_summary(rows, key)
        for key in (
            "workingFeedbackMs",
            "runAcceptanceMs",
            "providerRequestMs",
            "firstNativeEventMs",
            "firstNativeSseMs",
            "firstFragmentSseMs",
            "firstTextSseMs",
            "providerTerminalMs",
            "durableTerminalCommitMs",
            "terminalTailMs",
            "readerCallbackTotalMs",
            "readerCallbackMaxMs",
        )
    }
    return {
        "fixture": {
            "kind": "deterministic-warm-resumed-codex-chat",
            "warmups": warmups,
            "measuredTurns": runs,
            "existingThread": True,
            "appServerAlreadyRunningForMeasuredTurns": True,
            "browserBoundary": "simulated synchronous production boundary before HTTP fetch",
            "externalModelOrCredentials": False,
            "fakeAppServerEmitsReasoningDeltas": 20,
            "fastPathEnabled": bool(server._CODEX_EVENT_FAST_PATH.settings.enabled),
        },
        "stages": stages,
        "trends": {
            "firstNativeSseMs": trend_summary(rows, "firstNativeSseMs"),
            "firstFragmentSseMs": trend_summary(rows, "firstFragmentSseMs"),
            "terminalTailMs": trend_summary(rows, "terminalTailMs"),
            "readerCallbackTotalMs": trend_summary(rows, "readerCallbackTotalMs"),
        },
        "operationCounts": summarized_counts([row["counts"] for row in rows]),
        "measuredCounterWindow": counter_delta(measured_counter_end, measured_counter_start or {}),
        "failures": failures,
        "baselineObservations": {
            "activityPersistenceComplexity": (
                "Only durable-key and terminal activity is persisted; transient activity stays in the bounded live view."
                if server._CODEX_EVENT_FAST_PATH.settings.enabled else
                "Each native event loads/scans and rewrites the bounded activity JSON file."
            ),
            "communicationProgressComplexity": (
                "Transient progress does not rewrite communication history on the fast path."
                if server._CODEX_EVENT_FAST_PATH.settings.enabled else
                "Initial progress, every native event, and terminal cleanup scan/rewrite communication history."
            ),
            "terminalGrace": "CodexAppServerClient uses callback-drain completion with a bounded malformed-order fallback and no unconditional sleep.",
            "firstTextSlo": "Observed only; no fixed product SLO is asserted.",
        },
    }


def validate(result: dict[str, Any]) -> None:
    fixture = result["fixture"]
    assert fixture["warmups"] >= 10
    assert fixture["measuredTurns"] >= 100
    assert result["stages"]["workingFeedbackMs"]["samples"] == fixture["measuredTurns"]
    assert result["stages"]["firstNativeEventMs"]["samples"] == fixture["measuredTurns"]
    assert result["stages"]["firstFragmentSseMs"]["samples"] == fixture["measuredTurns"]
    assert result["stages"]["terminalTailMs"]["samples"] == fixture["measuredTurns"]
    if fixture.get("fastPathEnabled", False):
        assert result["operationCounts"]["activityJsonWrites"]["total"] <= fixture["measuredTurns"] * 3
        assert result["operationCounts"]["communicationProgressRewrites"]["total"] == 0
    else:
        assert result["operationCounts"]["activityJsonWrites"]["total"] > 0
        assert result["operationCounts"]["communicationProgressRewrites"]["total"] > 0
    assert result["stages"]["readerCallbackTotalMs"]["p95Ms"] > 0
    assert result["failures"] == []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--output")
    parser.add_argument("--check")
    args = parser.parse_args()
    if args.check:
        result = json.loads(Path(args.check).read_text(encoding="utf-8"))
        validate(result)
        print("Codex chat fast-path baseline verified")
        return
    if args.warmups < 10 or args.runs < 100:
        parser.error("the accepted baseline requires at least 10 warmups and 100 measured turns")
    result = {
        "schemaVersion": 1,
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        **run_fixture(args.warmups, args.runs),
    }
    validate(result)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
