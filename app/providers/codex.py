"""Codex provider adapter for My Virtual Office.

This adapter exposes the current/local Codex collaborator as an office agent.
It intentionally starts as an opt-in harness: discovery, status, routing, and
office event visibility work without requiring OpenClaw or Hermes to be
installed. A real live Codex bridge can be added behind this adapter later.
"""

from __future__ import annotations

import os
import json
import re
import shutil
import time
import tomllib
from dataclasses import dataclass
from typing import Any

from providers.codex_bridge import get_codex_bridge


def _env_bool(key: str, fallback: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None or str(value).strip() == "":
        return fallback
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _safe_suffix(value: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value or "local").strip("-")
    return suffix[:80] or "local"


def _bounded_turn_capacity(value: Any) -> int:
    try:
        return max(1, min(int(value or 1), 4))
    except (TypeError, ValueError):
        return 1


@dataclass
class CodexProvider:
    """Provider adapter for a local Codex collaborator harness."""

    enabled: bool = False
    workspace: str | None = None
    home_path: str | None = None
    binary: str | None = None
    workspace_root: str | None = None
    main_workspace: str | None = None
    name: str | None = None
    agent_id: str | None = None
    model: str | None = None
    reply_text: str | None = None
    bridge_url: str | None = None
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    prefer_app_server: bool = True
    include_main: bool = True
    include_native_agents: bool = True
    register_native_agents: bool = True
    route_approvals_through_vo: bool = False
    max_concurrent_turns: int = 1

    provider_kind: str = "codex"
    provider_type: str = "app-server-bridge"

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.workspace = os.path.abspath(os.path.expanduser(
            self.workspace
            or os.environ.get("VO_CODEX_WORKSPACE")
            or os.getcwd()
        ))
        self.home_path = os.path.abspath(os.path.expanduser(
            self.home_path
            or os.environ.get("VO_CODEX_HOME")
            or os.environ.get("CODEX_HOME")
            or "~/.codex"
        ))
        self.binary = self._resolve_binary(self.binary)
        self.workspace_root = os.path.abspath(os.path.expanduser(
            self.workspace_root
            or os.environ.get("VO_CODEX_WORKSPACE_ROOT")
            or os.path.join(os.environ.get("VO_STATUS_DIR", "/tmp"), "codex-agents")
        ))
        self.main_workspace = os.path.abspath(os.path.expanduser(
            self.main_workspace
            or os.environ.get("VO_CODEX_MAIN_WORKSPACE")
            or self.workspace
        ))
        self.name = self.name or os.environ.get("VO_CODEX_AGENT_NAME") or "Codex"
        self.agent_id = _safe_suffix(self.agent_id or os.environ.get("VO_CODEX_AGENT_ID") or "local")
        self.model = self.model or os.environ.get("VO_CODEX_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        self.reply_text = self.reply_text if self.reply_text is not None else os.environ.get("VO_CODEX_REPLY_TEXT")
        self.bridge_url = self.bridge_url or os.environ.get("VO_CODEX_BRIDGE_URL") or ""
        self.sandbox = str(self.sandbox or os.environ.get("VO_CODEX_SANDBOX") or "workspace-write")
        self.approval_policy = str(self.approval_policy or os.environ.get("VO_CODEX_APPROVAL_POLICY") or "never")
        self.prefer_app_server = _env_bool("VO_CODEX_PREFER_APP_SERVER", self.prefer_app_server)
        self.include_main = _env_bool("VO_CODEX_INCLUDE_MAIN", self.include_main)
        self.include_native_agents = _env_bool("VO_CODEX_INCLUDE_NATIVE_AGENTS", self.include_native_agents)
        self.register_native_agents = _env_bool("VO_CODEX_REGISTER_NATIVE_AGENTS", self.register_native_agents)
        self.route_approvals_through_vo = bool(self.route_approvals_through_vo)
        self.max_concurrent_turns = _bounded_turn_capacity(self.max_concurrent_turns)

    def _bridge(self, workspace: str | None = None):
        return get_codex_bridge(
            workspace or self.workspace or os.getcwd(),
            self.model or "",
            self.bridge_url or "",
            max_concurrent_turns=self.max_concurrent_turns,
            route_approvals_through_vo=self.route_approvals_through_vo,
            home_path=self.home_path or "",
            sandbox=self.sandbox,
            approval_policy=self.approval_policy,
        )

    @classmethod
    def from_env(cls) -> "CodexProvider":
        return cls(
            enabled=_env_bool("VO_CODEX_ENABLED", False),
            workspace=os.environ.get("VO_CODEX_WORKSPACE"),
            home_path=os.environ.get("VO_CODEX_HOME") or os.environ.get("CODEX_HOME"),
            binary=os.environ.get("VO_CODEX_BIN"),
            workspace_root=os.environ.get("VO_CODEX_WORKSPACE_ROOT"),
            main_workspace=os.environ.get("VO_CODEX_MAIN_WORKSPACE"),
            name=os.environ.get("VO_CODEX_AGENT_NAME"),
            agent_id=os.environ.get("VO_CODEX_AGENT_ID"),
            model=os.environ.get("VO_CODEX_MODEL") or os.environ.get("OPENAI_MODEL"),
            reply_text=os.environ.get("VO_CODEX_REPLY_TEXT"),
            bridge_url=os.environ.get("VO_CODEX_BRIDGE_URL"),
            sandbox=os.environ.get("VO_CODEX_SANDBOX") or "workspace-write",
            approval_policy=os.environ.get("VO_CODEX_APPROVAL_POLICY") or "never",
            route_approvals_through_vo=_env_bool("VO_CODEX_ROUTE_APPROVALS_THROUGH_VO", False),
            max_concurrent_turns=_bounded_turn_capacity(os.environ.get("VO_CODEX_MAX_CONCURRENT_TURNS")),
        )

    def send_chat_message(
        self,
        profile: str,
        message: str,
        session_id: str | None = None,
        timeout_sec: int | None = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        """Reference-compatible native chat facade over the local app-server bridge."""
        text = str(message or "").strip()
        if not self.enabled:
            return {"ok": False, "error": "Codex harness is disabled", "reply": ""}
        if not text:
            return {"ok": False, "error": "message is required", "reply": ""}
        profile_name = self._safe_profile_name(profile or self.agent_id or "local")
        if self.reply_text:
            demo_thread_id = session_id or f"demo-{_safe_suffix(profile_name)}"
            result = {
                "ok": True,
                "reply": self.reply_text,
                "conversationId": session_id or profile_name,
                "mode": "replyText",
                "status": "completed",
                "threadId": demo_thread_id,
                "turnId": "",
                "modifiedFiles": [],
                "needsHumanIntervention": False,
                "tools": [],
                "thinking": "",
                "approval": None,
                "tokenUsage": {},
            }
        else:
            bridge = self._bridge()
            if hasattr(bridge, "send_chat_message"):
                result = bridge.send_chat_message(
                    text,
                    session_id=session_id or "",
                    timeout_sec=int(timeout_sec or 600),
                    on_progress=on_progress,
                )
            else:
                result = bridge.execute(text, thread_id=session_id or "", timeout_sec=int(timeout_sec or 600))
            result["conversationId"] = session_id or profile_name
            result["mode"] = "externalBridge" if self.bridge_url else "appServer"
        result["profile"] = profile_name
        result["sessionId"] = result.get("threadId") or session_id or ""
        result["runId"] = result.get("turnId") or result.get("runId") or ""
        result["tools"] = result.get("tools") or []
        result["thinking"] = result.get("thinking") or ""
        result["approval"] = result.get("approval")
        result["tokenUsage"] = result.get("tokenUsage") or {}
        result["providerPath"] = "reply-text" if self.reply_text else ("external-bridge" if self.bridge_url else "app-server")
        return result

    def is_available(self) -> bool:
        return bool(self.enabled)

    def _session_workspace(self, profile: str) -> str:
        safe = self._safe_profile_name(profile or self.agent_id or "local")
        external = self._external_agent_dir(safe)
        managed = os.path.join(self.workspace_root or "", safe)
        if external and os.path.isdir(external):
            return external
        if managed and os.path.isdir(managed):
            return managed
        return self.workspace or os.getcwd()

    def _thread_request(self, profile: str, method: str, params: dict[str, Any], timeout_sec: int = 30) -> dict[str, Any]:
        bridge = self._bridge(self._session_workspace(profile))
        if not hasattr(bridge, "_request"):
            return {"ok": False, "error": "Configured Codex HTTP bridge does not expose thread management"}
        try:
            if hasattr(bridge, "_ensure_started"):
                bridge._ensure_started()
            return {"ok": True, "result": bridge._request(method, params, timeout=float(timeout_sec))}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:1000]}

    def list_threads(self, profile: str, limit: int = 40, timeout_sec: int = 30) -> dict[str, Any]:
        workspace = self._session_workspace(profile)
        outcome = self._thread_request(profile, "thread/list", {"cwd": workspace, "limit": max(1, int(limit))}, timeout_sec)
        if not outcome.get("ok"):
            return {"ok": False, "error": outcome.get("error"), "sessions": []}
        rows = (outcome.get("result") or {}).get("data")
        sessions = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            preview = str(row.get("preview") or "")
            sessions.append({"id": str(row.get("id") or ""), "title": str(row.get("name") or "").strip() or preview[:80] or str(row.get("id") or "")[:24], "preview": preview[:300], "updatedAt": row.get("updatedAt"), "createdAt": row.get("createdAt"), "archived": bool(row.get("archived"))})
        return {"ok": True, "sessions": sessions, "profile": self._safe_profile_name(profile)}

    def read_thread(self, profile: str, thread_id: str, timeout_sec: int = 30) -> dict[str, Any]:
        if not thread_id:
            return {"ok": False, "error": "thread_id is required"}
        outcome = self._thread_request(profile, "thread/read", {"threadId": str(thread_id), "includeTurns": True}, timeout_sec)
        if not outcome.get("ok"):
            return {"ok": False, "error": outcome.get("error"), "thread": None}
        result = outcome.get("result") or {}
        return {"ok": True, "thread": result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else result}

    def delete_thread(self, profile: str, thread_id: str, timeout_sec: int = 30) -> dict[str, Any]:
        if not thread_id:
            return {"ok": False, "error": "thread_id is required"}
        outcome = self._thread_request(profile, "thread/delete", {"threadId": str(thread_id)}, timeout_sec)
        return {"ok": bool(outcome.get("ok")), "deleted": bool(outcome.get("ok")), "error": outcome.get("error", "")}

    def discover_agents(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        agents = [self._agent_entry(
            profile=self.agent_id or "local",
            name=self.name or "Codex",
            emoji=os.environ.get("VO_CODEX_AGENT_EMOJI", "⚡"),
            role="Codex Collaborator",
            model=self.model or "",
            workspace=self.workspace,
            source="legacy-local",
            last_active=self._last_active(self.workspace),
        )]
        seen = {self._safe_profile_name(self.agent_id or "local")}
        if self.include_main and self._safe_profile_name(self.agent_id or "") != "main":
            agents.append(self._agent_entry(
                profile="main",
                name="Main",
                emoji="🤖",
                role="Default Codex agent",
                model=self.model or "",
                workspace=self.main_workspace or self.workspace,
                source="native-main",
                last_active=self._last_active(self.main_workspace or self.workspace),
            ))
            seen.add("main")
        for agent_dir in self._office_agent_dirs():
            meta = self._load_meta(agent_dir)
            profile = self._safe_profile_name(meta.get("profile") or os.path.basename(agent_dir))
            if profile in seen:
                continue
            seen.add(profile)
            agents.append(self._agent_entry(
                profile=profile,
                name=meta.get("name") or self._display_name(profile),
                emoji=meta.get("emoji") or "🤖",
                role=meta.get("role") or "Codex Agent",
                model=meta.get("model") or self.model or "",
                workspace=agent_dir,
                source=meta.get("creationMode") or "virtual-office",
                last_active=self._last_active(agent_dir),
                native_agent_path=meta.get("nativeAgentPath") or "",
            ))
        agents.extend(self._discover_native_agents(seen))
        return agents

    def test(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "Codex harness is disabled. Set VO_CODEX_ENABLED=1 to expose it.", "agents": []}
        protocol = "reply-text" if self.reply_text else ("external-bridge" if self.bridge_url else "app-server")
        binary = self.binary or os.environ.get("VO_CODEX_BIN") or shutil.which("codex") or ""
        base = {
            "workspace": self.workspace,
            "workspaceRoot": self.workspace_root,
            "mainWorkspace": self.main_workspace,
            "homePath": self.home_path,
            "protocol": protocol,
            "mode": protocol,
            "nativeRuntime": protocol != "reply-text",
            "binary": binary,
            "binaryDetected": bool(binary),
            "bridgeConfigured": bool(self.bridge_url or self.reply_text or binary),
        }
        if self.reply_text:
            return {
                "ok": True,
                **base,
                "authOk": True,
                "authStatus": "reply-text fixture",
                "agents": self.discover_agents(),
            }
        if not binary and not self.bridge_url:
            return {
                "ok": False,
                **base,
                "authOk": False,
                "authStatus": "",
                "error": "Codex CLI not found. Set VO_CODEX_BIN or install codex on PATH.",
                "agents": [],
            }
        if protocol == "app-server" and self.prefer_app_server:
            try:
                bridge = self._bridge()
                if hasattr(bridge, "probe_auth"):
                    probe = bridge.probe_auth(timeout_sec=15)
                    return {
                        **base,
                        **probe,
                        "protocol": probe.get("protocol") or protocol,
                        "mode": probe.get("protocol") or protocol,
                        "agents": self.discover_agents() if probe.get("ok") else [],
                    }
            except Exception as exc:
                return {
                    "ok": False,
                    **base,
                    "authOk": False,
                    "authStatus": "",
                    "error": str(exc),
                    "agents": [],
                }
        return {
            "ok": bool(self.bridge_url),
            **base,
            "authOk": bool(self.bridge_url),
            "authStatus": "external bridge configured" if self.bridge_url else "",
            "error": "" if self.bridge_url else "Codex app-server auth probe is unavailable.",
            "agents": self.discover_agents(),
        }

    def send_message(
        self,
        message: str,
        conversation_id: str = "",
        timeout_sec: int | None = None,
        thread_id: str = "",
        event_callback: Any = None,
        allow_interaction: bool = False,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        text = str(message or "").strip()
        if not self.enabled:
            return {"ok": False, "error": "Codex harness is disabled", "reply": ""}
        if not text:
            return {"ok": False, "error": "message is required", "reply": ""}
        if self.reply_text:
            demo_thread_id = thread_id or f"demo-{_safe_suffix(conversation_id or 'conversation')}"
            return {
                "ok": True,
                "reply": self.reply_text,
                "conversationId": conversation_id,
                "mode": "replyText",
                "status": "completed",
                "threadId": demo_thread_id,
                "turnId": "",
                "modifiedFiles": [],
                "needsHumanIntervention": False,
            }
        result = self._bridge().execute(
            text,
            thread_id=thread_id,
            timeout_sec=int(timeout_sec or 600),
            event_callback=event_callback,
            allow_interaction=allow_interaction,
            attachments=attachments,
        )
        result["conversationId"] = conversation_id
        result["mode"] = "externalBridge" if self.bridge_url else "appServer"
        return result

    def wait_for_terminal_callbacks(self, thread_id: str, turn_id: str = "", timeout: float | None = None) -> bool:
        bridge = self._bridge()
        waiter = getattr(bridge, "wait_for_terminal_callbacks", None)
        if not callable(waiter):
            return True
        return bool(waiter(thread_id, turn_id=turn_id, timeout=timeout))

    def create_agent(
        self,
        name: str,
        role: str = "Codex Agent",
        model: str | None = None,
        emoji: str = "🤖",
        profile: str | None = None,
        prompt: str | None = None,
        creation_mode: str = "standard",
        custom_directory: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "Codex provider is disabled"}
        safe_profile = self._safe_profile_name(profile or name)
        if not safe_profile or safe_profile == "main":
            return {"ok": False, "error": "Invalid Codex profile name"}
        if self._profile_exists(safe_profile):
            return {"ok": False, "error": f"Codex agent '{safe_profile}' already exists"}
        mode = str(creation_mode or "standard").strip().lower()
        if mode not in {"standard", "custom"}:
            mode = "standard"
        if mode == "custom":
            parent = self._resolve_custom_parent(custom_directory)
            if not parent:
                return {"ok": False, "error": "A custom parent directory is required"}
            native_dir = self._native_agents_dir()
            if native_dir and self._path_is_inside(parent, native_dir):
                return {"ok": False, "error": "Custom workspace cannot be inside the Codex native agents directory"}
            agent_dir = os.path.join(parent, safe_profile)
        else:
            agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        if os.path.exists(os.path.join(agent_dir, "office-agent.json")):
            return {"ok": False, "error": f"Codex agent '{safe_profile}' already exists"}
        native_path = self._native_agent_file_path(safe_profile) if mode == "standard" else ""
        should_register_native = bool(mode == "standard" and self.register_native_agents and native_path)
        if should_register_native and os.path.exists(native_path):
            return {"ok": False, "error": f"Native Codex agent '{safe_profile}' already exists"}
        os.makedirs(os.path.join(agent_dir, ".codex", "agents"), exist_ok=True)
        model_value = (model or self.model or "").strip()
        instructions = (prompt or role or "Codex Agent").strip()
        meta = {
            "profile": safe_profile,
            "name": name,
            "emoji": emoji or "🤖",
            "role": role or "Codex Agent",
            "prompt": instructions,
            "model": model_value,
            "providerKind": self.provider_kind,
            "providerType": self.provider_type,
            "creationMode": mode,
            "customParentDirectory": os.path.dirname(agent_dir) if mode == "custom" else "",
            "nativeAgentPath": native_path if should_register_native else "",
            "createdAt": int(time.time()),
        }
        self._write_json(os.path.join(agent_dir, "office-agent.json"), meta)
        self._write_text(os.path.join(agent_dir, "IDENTITY.md"), self._identity_md(name, role, emoji))
        self._write_text(os.path.join(agent_dir, "AGENTS.md"), self._agents_md(name, role, instructions))
        self._write_text(os.path.join(agent_dir, ".codex", "config.toml"), self._config_toml(model_value))
        self._write_text(os.path.join(agent_dir, ".codex", "agents", f"{safe_profile}.toml"), self._agent_toml(safe_profile, role, instructions, model_value))
        if should_register_native:
            self._write_text(native_path, self._agent_toml(safe_profile, role, instructions, model_value))
        if mode == "custom":
            self._save_external_agent(safe_profile, agent_dir)
        return {
            "ok": True,
            "profile": safe_profile,
            "agentId": f"codex-{safe_profile}",
            "name": name,
            "workspace": agent_dir,
            "creationMode": mode,
            "nativeAgentPath": native_path if should_register_native else "",
            "message": f"Codex agent '{name}' created successfully",
        }

    def delete_agent(self, profile: str) -> dict[str, Any]:
        safe_profile = self._safe_profile_name(profile)
        if not safe_profile:
            return {"ok": False, "error": "profile is required"}
        if safe_profile == "main" or safe_profile == self._safe_profile_name(self.agent_id):
            return {"ok": False, "error": "The built-in Codex agent cannot be deleted"}
        agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        meta = self._load_meta(agent_dir)
        deleted = False
        if os.path.isdir(agent_dir):
            shutil.rmtree(agent_dir)
            deleted = True
        external_dir = self._external_agent_dir(safe_profile)
        if external_dir and os.path.isdir(external_dir):
            shutil.rmtree(external_dir)
            deleted = True
        self._remove_external_agent(safe_profile)
        native_path = str(meta.get("nativeAgentPath") or self._native_agent_file_path(safe_profile) or "")
        if native_path and os.path.isfile(native_path) and self._is_native_agent_path(native_path):
            os.remove(native_path)
            deleted = True
        return {"ok": True, "deleted": deleted, "profile": safe_profile, "agentId": f"codex-{safe_profile}"}

    def respond(self, thread_id: str, interaction_id: str, action: str, answers: dict[str, Any] | None = None) -> bool:
        bridge = self._bridge()
        return bool(hasattr(bridge, "respond") and bridge.respond(thread_id, interaction_id, action, answers))

    def cancel(self, thread_id: str) -> bool:
        bridge = self._bridge()
        return bool(hasattr(bridge, "cancel") and bridge.cancel(thread_id))

    def interrupt(self, profile: str, session_id: str | None = None) -> dict[str, Any]:
        thread_id = str(session_id or "").strip()
        if not thread_id:
            return {"ok": False, "status": "not_found", "error": "No active Codex turn is running for this agent."}
        ok = self.cancel(thread_id)
        return {"ok": ok, "status": "cancelling" if ok else "stale", "sessionId": thread_id, "threadId": thread_id}

    def respond_approval(self, profile: str, approval_id: str, choice: str = "cancel", session_id: str | None = None) -> dict[str, Any]:
        if self.reply_text:
            thread_id = str(session_id or "").strip()
            if not thread_id:
                return {"ok": False, "status": "not_found", "error": "No active Codex turn is running for this agent."}
            return {"ok": False, "status": "stale", "approvalId": approval_id, "sessionId": thread_id, "threadId": thread_id}
        bridge = self._bridge()
        if hasattr(bridge, "respond_approval"):
            result = bridge.respond_approval(approval_id, choice)
            result["profile"] = self._safe_profile_name(profile or self.agent_id or "local")
            if session_id:
                result.setdefault("sessionId", session_id)
                result.setdefault("threadId", session_id)
            result["status"] = "submitted" if result.get("ok") else result.get("status", "stale")
            result["approvalId"] = approval_id
            return result
        thread_id = str(session_id or "").strip()
        if not thread_id:
            return {"ok": False, "status": "not_found", "error": "No active Codex turn is running for this agent."}
        ok = self.respond(thread_id, approval_id, choice, {})
        return {"ok": ok, "status": "submitted" if ok else "stale", "approvalId": approval_id, "sessionId": thread_id, "threadId": thread_id}

    def pending_approval(self, profile: str, session_id: str | None = None, approval_id: str = "") -> dict[str, Any]:
        if self.reply_text:
            return {"ok": True, "pending": None, "pending_count": 0, "profile": self._safe_profile_name(profile or self.agent_id or "local")}
        bridge = self._bridge()
        if hasattr(bridge, "pending_approval"):
            if approval_id:
                result = bridge.pending_approval(str(session_id or ""), approval_id=str(approval_id))
            else:
                result = bridge.pending_approval(str(session_id or ""))
            result["profile"] = self._safe_profile_name(profile or self.agent_id or "local")
            return result
        return {"ok": True, "pending": None, "pending_count": 0, "profile": self._safe_profile_name(profile or self.agent_id or "local")}

    def compact_context(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "status": "disabled", "error": "Codex harness is disabled", "reply": ""}
        if self.reply_text:
            return {"ok": True, "status": "compacted", "reply": "Codex demo context compressed.", "threadId": thread_id, "modifiedFiles": []}
        result = self._bridge().compact(thread_id, timeout_sec=timeout_sec)
        result["mode"] = "externalBridge" if self.bridge_url else "appServer"
        return result

    def _last_active(self, path: str | None) -> int:
        if not path or not os.path.isdir(path):
            return int(time.time())
        latest = 0.0
        try:
            for name in (".git", ".codex", ".agents"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    latest = max(latest, os.path.getmtime(candidate))
            latest = max(latest, os.path.getmtime(path))
        except OSError:
            pass
        return int(latest or time.time())

    def _resolve_binary(self, value: str | None) -> str:
        candidates = [value, os.environ.get("VO_CODEX_BIN"), shutil.which("codex"), os.path.expanduser("~/.local/bin/codex")]
        if self.home_path:
            candidates.append(os.path.join(os.path.expanduser(self.home_path), "packages", "standalone", "current", "bin", "codex"))
        for candidate in candidates:
            if not candidate:
                continue
            expanded = os.path.expanduser(str(candidate))
            resolved = shutil.which(expanded) if os.path.basename(expanded) == expanded else expanded
            if resolved and os.path.isfile(resolved):
                return resolved
        return os.path.expanduser(str(value or os.environ.get("VO_CODEX_BIN") or "codex"))

    @staticmethod
    def _safe_profile_name(value: str | None) -> str:
        raw = str(value or "").strip().lower()
        raw = re.sub(r"[^a-z0-9_.-]+", "-", raw).strip("-._")
        return raw[:64] or "codex-agent"

    @staticmethod
    def _display_name(profile: str) -> str:
        return str(profile or "codex").replace("-", " ").replace("_", " ").title()

    def _agent_entry(self, *, profile: str, name: str, emoji: str, role: str, model: str, workspace: str, source: str, last_active: int = 0, native_agent_path: str = "") -> dict[str, Any]:
        suffix = _safe_suffix(profile)
        return {
            "id": f"codex-{suffix}",
            "statusKey": f"codex-{suffix}",
            "providerKind": self.provider_kind,
            "providerType": self.provider_type,
            "providerAgentId": profile,
            "profile": profile,
            "name": name or self._display_name(profile),
            "emoji": emoji or "🤖",
            "role": role or "Codex Agent",
            "model": model or self.model or "",
            "provider": "OpenAI Codex",
            "workspace": workspace,
            "home": workspace,
            "binary": self.binary,
            "lastActiveAt": last_active or self._last_active(workspace),
            "capabilities": ["chat", "status", "collaboration", "event-stream", "sessions", "files", "interrupt"],
            "bridgeConfigured": bool(self.bridge_url or self.reply_text or shutil.which(os.environ.get("VO_CODEX_BIN") or "codex")),
            "protocol": "reply-text" if self.reply_text else ("external-bridge" if self.bridge_url else "app-server"),
            "nativeRuntime": not bool(self.reply_text),
            "codexSource": source,
            "nativeAgentPath": native_agent_path,
        }

    def _office_agent_dirs(self) -> list[str]:
        dirs: list[str] = []
        seen: set[str] = set()
        if self.workspace_root and os.path.isdir(self.workspace_root):
            for name in sorted(os.listdir(self.workspace_root)):
                agent_dir = os.path.join(self.workspace_root, name)
                if os.path.isdir(agent_dir):
                    dirs.append(agent_dir)
                    seen.add(os.path.abspath(agent_dir))
        for _profile, agent_dir in sorted(self._load_external_agents().items()):
            if os.path.isdir(agent_dir) and os.path.abspath(agent_dir) not in seen:
                dirs.append(agent_dir)
        return dirs

    def _discover_native_agents(self, seen_profiles: set[str]) -> list[dict[str, Any]]:
        if not self.include_native_agents:
            return []
        agents_dir = self._native_agents_dir()
        if not agents_dir or not os.path.isdir(agents_dir):
            return []
        agents: list[dict[str, Any]] = []
        for filename in sorted(os.listdir(agents_dir)):
            if not filename.endswith(".toml"):
                continue
            path = os.path.join(agents_dir, filename)
            meta = self._load_native_agent_file(path)
            if not meta:
                continue
            profile = self._safe_profile_name(meta.get("profile") or meta.get("name") or os.path.splitext(filename)[0])
            if profile in seen_profiles:
                continue
            seen_profiles.add(profile)
            agents.append(self._agent_entry(
                profile=profile,
                name=str(meta.get("name") or self._display_name(profile)),
                emoji=str(meta.get("emoji") or "🤖"),
                role=str(meta.get("description") or meta.get("role") or "Codex Agent"),
                model=str(meta.get("model") or self.model or ""),
                workspace=self.main_workspace or self.workspace,
                source="native-agent",
                last_active=self._last_active(path),
                native_agent_path=path,
            ))
        return agents

    def _load_meta(self, agent_dir: str) -> dict[str, Any]:
        try:
            with open(os.path.join(agent_dir, "office-agent.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _load_native_agent_file(path: str) -> dict[str, Any]:
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        if not str(data.get("name") or "").strip():
            return {}
        return data

    def _profile_exists(self, profile: str) -> bool:
        safe_profile = self._safe_profile_name(profile)
        if safe_profile in {"main", self._safe_profile_name(self.agent_id)}:
            return True
        if os.path.isdir(os.path.join(self.workspace_root or "", safe_profile)):
            return True
        if self._external_agent_dir(safe_profile):
            return True
        native_path = self._native_agent_file_path(safe_profile)
        return bool(native_path and os.path.isfile(native_path))

    def _native_agents_dir(self) -> str:
        return os.path.join(self.home_path, "agents") if self.home_path else ""

    def _native_agent_file_path(self, profile: str) -> str:
        agents_dir = self._native_agents_dir()
        return os.path.join(agents_dir, f"{self._safe_profile_name(profile)}.toml") if agents_dir else ""

    def _is_native_agent_path(self, path: str) -> bool:
        agents_dir = self._native_agents_dir()
        return bool(agents_dir and self._path_is_inside(path, agents_dir))

    @staticmethod
    def _path_is_inside(path: str, parent: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(parent), os.path.abspath(path)]) == os.path.abspath(parent)
        except ValueError:
            return False

    @staticmethod
    def _resolve_custom_parent(value: str | None) -> str:
        raw = str(value or "").strip()
        return os.path.abspath(os.path.expanduser(raw)) if raw else ""

    def _registry_path(self) -> str:
        root = self.workspace_root or self.home_path or os.getcwd()
        return os.path.join(os.path.expanduser(root), "office-codex-agent-registry.json")

    def _load_external_agents(self) -> dict[str, str]:
        try:
            with open(self._registry_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        agents = data.get("agents") if isinstance(data, dict) else {}
        if not isinstance(agents, dict):
            return {}
        return {self._safe_profile_name(k): os.path.abspath(os.path.expanduser(v)) for k, v in agents.items() if isinstance(v, str) and v.strip()}

    def _save_external_agents(self, agents: dict[str, str]) -> None:
        self._write_json(self._registry_path(), {
            "schema": "my-virtual-office.codex-agent-registry.v1",
            "updatedAt": int(time.time()),
            "agents": {self._safe_profile_name(k): os.path.abspath(os.path.expanduser(v)) for k, v in sorted(agents.items()) if k and v},
        })

    def _save_external_agent(self, profile: str, agent_dir: str) -> None:
        agents = self._load_external_agents()
        agents[self._safe_profile_name(profile)] = os.path.abspath(os.path.expanduser(agent_dir))
        self._save_external_agents(agents)

    def _remove_external_agent(self, profile: str) -> None:
        agents = self._load_external_agents()
        agents.pop(self._safe_profile_name(profile), None)
        self._save_external_agents(agents)

    def _external_agent_dir(self, profile: str) -> str:
        return self._load_external_agents().get(self._safe_profile_name(profile), "")

    @staticmethod
    def _write_text(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _write_json(path: str, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _toml_string(value: str) -> str:
        return json.dumps(str(value or ""), ensure_ascii=False)

    def _identity_md(self, name: str, role: str, emoji: str) -> str:
        return "# IDENTITY.md\n\n" f"- **Name:** {name}\n" f"- **Creature:** {role or 'Codex Agent'}\n" f"- **Emoji:** {emoji or '🤖'}\n"

    def _agents_md(self, name: str, role: str, instructions: str) -> str:
        return f"# {name}\n\nRole: {role or 'Codex Agent'}\n\n## Standing Instructions\n\n{instructions.strip()}\n"

    def _config_toml(self, model: str) -> str:
        lines = []
        if model:
            lines.append(f"model = {self._toml_string(model)}")
        lines.append(f"sandbox_mode = {self._toml_string(self.sandbox)}")
        lines.append(f"approval_policy = {self._toml_string(self.approval_policy)}")
        return "\n".join(lines) + "\n"

    def _agent_toml(self, profile: str, role: str, instructions: str, model: str) -> str:
        lines = [
            f"name = {self._toml_string(profile)}",
            f"description = {self._toml_string(role or 'Virtual Office Codex agent')}",
            f"developer_instructions = {self._toml_string(instructions)}",
        ]
        if model:
            lines.append(f"model = {self._toml_string(model)}")
        return "\n".join(lines) + "\n"
