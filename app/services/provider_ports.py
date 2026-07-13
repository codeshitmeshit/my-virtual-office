"""Provider-neutral commands, results, events, capabilities, and adapter ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True)
class AdapterCapabilities:
    background_run: bool = True
    streaming_events: bool = True
    cancel: bool = False
    conversation_continuation: bool = False
    approval_continuation: bool = False
    attachments: bool = False
    queued_delivery: bool = False


@dataclass(frozen=True)
class RunCommand:
    provider_kind: str
    provider_path: str
    agent_id: str
    conversation_id: str = ""
    profile: str = ""
    idempotency_key: str = ""
    timeout_sec: float = 900.0
    run_id: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    start_payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterEvent:
    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    state_updates: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterResult:
    result: Mapping[str, Any]
    terminal_payload: Mapping[str, Any] = field(default_factory=dict)
    terminal_event: str = ""


class ProviderAdapter(Protocol):
    provider_kind: str
    provider_path: str
    capabilities: AdapterCapabilities

    def run(self, command: RunCommand, emit: Callable[[AdapterEvent], bool], cancel_event) -> AdapterResult | Mapping[str, Any]: ...

    def cancel(self, command: RunCommand, snapshot: Mapping[str, Any], payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TaskLauncher(Protocol):
    def launch(self, target: Callable[[], None], *, name: str) -> Any: ...


class ThreadTaskLauncher:
    def launch(self, target: Callable[[], None], *, name: str):
        import threading

        thread = threading.Thread(target=target, daemon=True, name=name)
        thread.start()
        return thread


class AdapterUnavailableError(LookupError):
    pass


class ProviderAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[tuple[str, str], ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        key = (str(adapter.provider_kind).strip().lower(), str(adapter.provider_path).strip().lower())
        if not all(key):
            raise ValueError("provider kind and path are required")
        self._adapters[key] = adapter

    def resolve(self, provider_kind: str, provider_path: str, required: tuple[str, ...] = ()) -> ProviderAdapter:
        key = (str(provider_kind or "").strip().lower(), str(provider_path or "").strip().lower())
        adapter = self._adapters.get(key)
        if adapter is None:
            raise AdapterUnavailableError(f"provider adapter unavailable: {key[0]}/{key[1]}")
        capabilities = adapter.capabilities
        missing = [name for name in required if not bool(getattr(capabilities, name, False))]
        if missing:
            raise AdapterUnavailableError(f"provider adapter lacks capabilities: {', '.join(missing)}")
        return adapter


class CallableProviderAdapter:
    """Thin adapter for existing provider-specific functions during migration."""

    def __init__(self, provider_kind, provider_path, run, *, cancel=None, capabilities=None):
        self.provider_kind = str(provider_kind)
        self.provider_path = str(provider_path)
        self.capabilities = capabilities or AdapterCapabilities(cancel=cancel is not None)
        self._run = run
        self._cancel = cancel

    def run(self, command, emit, cancel_event):
        return self._run(command, emit, cancel_event)

    def cancel(self, command, snapshot, payload):
        if self._cancel is None:
            return {"ok": False, "status": "unsupported", "error": "provider cancellation is unavailable", "_status": 409}
        return self._cancel(command, snapshot, payload)
