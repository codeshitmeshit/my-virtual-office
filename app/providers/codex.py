"""Codex provider adapter for My Virtual Office.

The primary integration uses Codex's app-server JSON-RPC protocol over stdio.
`codex exec` is retained only as a compatibility fallback for installs that
explicitly disable the native path.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


ProgressCallback = Callable[[dict[str, Any]], None]

_ACTIVE_RUNS: dict[str, "CodexAppServerClient"] = {}
_ACTIVE_RUNS_LOCK = threading.Lock()


@dataclass
class CodexProvider:
    """Provider adapter for local Codex-backed Office agents."""

    home_path: str | None = None
    binary: str | None = None
    workspace_root: str | None = None
    enabled: bool = True
    timeout_sec: int = 900
    model: str = ""
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    prefer_app_server: bool = True

    provider_kind: str = "codex"
    provider_type: str = "harness"

    def __post_init__(self) -> None:
        self.home_path = os.path.expanduser(
            self.home_path
            or os.environ.get("VO_CODEX_HOME")
            or os.environ.get("CODEX_HOME")
            or "~/.codex"
        )
        self.binary = self._resolve_binary(self.binary)
        self.workspace_root = os.path.expanduser(
            self.workspace_root
            or os.environ.get("VO_CODEX_WORKSPACE_ROOT")
            or os.path.join(os.environ.get("VO_STATUS_DIR", "/data"), "codex-agents")
        )
        self.sandbox = str(self.sandbox or "workspace-write")
        self.approval_policy = str(self.approval_policy or "never")
        self.model = str(self.model or "")
        self.prefer_app_server = str(os.environ.get("VO_CODEX_PREFER_APP_SERVER", str(self.prefer_app_server))).lower() not in ("0", "false", "no", "off")

    def is_available(self) -> bool:
        return bool(
            self.enabled
            and self.binary
            and os.path.isfile(self.binary)
            and os.access(self.binary, os.X_OK)
        )

    def test(self) -> dict[str, Any]:
        if not self.binary or not os.path.isfile(self.binary):
            return {"ok": False, "error": f"Codex CLI not found. Set VO_CODEX_BIN or install codex on PATH.", "agents": []}
        if not os.access(self.binary, os.X_OK):
            return {"ok": False, "error": f"Codex CLI is not executable at {self.binary}", "agents": []}

        if self.prefer_app_server:
            try:
                self._ensure_paths()
                client = CodexAppServerClient(self, cwd=self.workspace_root or os.getcwd(), timeout_sec=20)
                try:
                    init = client.initialize()
                    account = client.request("account/read", {"refreshToken": False}, timeout_sec=12)
                finally:
                    client.close()
                account_result = account.get("result") if isinstance(account, dict) else {}
                account_info = account_result.get("account") if isinstance(account_result, dict) else None
                auth_ok = bool(account_info) or (isinstance(account_result, dict) and account_result.get("requiresOpenaiAuth") is False)
                return {
                    "ok": auth_ok,
                    "protocol": "app-server",
                    "binary": self.binary,
                    "homePath": self.home_path,
                    "workspaceRoot": self.workspace_root,
                    "authOk": auth_ok,
                    "authStatus": self._account_status_text(account_result),
                    "codexHome": (init.get("result") or {}).get("codexHome") if isinstance(init, dict) else self.home_path,
                    "error": "" if auth_ok else "Codex is installed but not authenticated. Run codex login or configure CODEX_API_KEY/CODEX_HOME for this environment.",
                    "agents": self.discover_agents() if auth_ok else [],
                }
            except Exception as exc:
                return {"ok": False, "protocol": "app-server", "error": str(exc), "agents": []}

        try:
            status = self._run([self.binary, "login", "status"], timeout_sec=15)
            auth_ok = status.returncode == 0
            auth_text = ((status.stdout or status.stderr or "").strip())[:500]
            return {
                "ok": auth_ok,
                "protocol": "exec",
                "binary": self.binary,
                "homePath": self.home_path,
                "workspaceRoot": self.workspace_root,
                "authOk": auth_ok,
                "authStatus": auth_text,
                "error": "" if auth_ok else (auth_text or "Codex is not logged in"),
                "agents": self.discover_agents() if auth_ok else [],
            }
        except Exception as exc:
            return {"ok": False, "protocol": "exec", "error": str(exc), "agents": []}

    def discover_agents(self) -> list[dict[str, Any]]:
        if not self.is_available() or not self.workspace_root or not os.path.isdir(self.workspace_root):
            return []

        agents: list[dict[str, Any]] = []
        for name in sorted(os.listdir(self.workspace_root)):
            agent_dir = os.path.join(self.workspace_root, name)
            if not os.path.isdir(agent_dir):
                continue
            meta_path = os.path.join(agent_dir, "office-agent.json")
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
            profile = self._safe_profile_name(meta.get("profile") or name)
            suffix = self._safe_suffix(profile)
            agents.append({
                "id": f"codex-{suffix}",
                "statusKey": f"codex-{suffix}",
                "providerKind": self.provider_kind,
                "providerType": self.provider_type,
                "providerAgentId": profile,
                "profile": profile,
                "name": meta.get("name") or self._display_name(profile),
                "emoji": meta.get("emoji") or "🤖",
                "role": meta.get("role") or "Codex Agent",
                "model": meta.get("model") or self.model or "",
                "provider": "Codex App Server" if self.prefer_app_server else "Codex CLI",
                "workspace": agent_dir,
                "home": agent_dir,
                "binary": self.binary,
                "lastActiveAt": self._last_active(agent_dir),
                "capabilities": ["chat", "status", "sessions", "files", "streaming", "interrupt"],
            })
        return agents

    def create_agent(self, name: str, role: str = "Codex Agent", model: str | None = None, emoji: str = "🤖", profile: str | None = None, prompt: str | None = None) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "error": f"Codex CLI is not available. Set VO_CODEX_BIN or install codex on PATH."}

        safe_profile = self._safe_profile_name(profile or name)
        if not safe_profile:
            return {"ok": False, "error": "Invalid Codex profile name"}
        agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        meta_path = os.path.join(agent_dir, "office-agent.json")
        if os.path.exists(meta_path):
            return {"ok": False, "error": f"Codex agent '{safe_profile}' already exists"}

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
            "createdAt": int(time.time()),
        }
        self._write_json(meta_path, meta)
        self._write_text(os.path.join(agent_dir, "IDENTITY.md"), self._identity_md(name, role, emoji))
        self._write_text(os.path.join(agent_dir, "AGENTS.md"), self._agents_md(name, role, instructions))
        self._write_text(os.path.join(agent_dir, ".codex", "config.toml"), self._config_toml(model_value))
        self._write_text(os.path.join(agent_dir, ".codex", "agents", f"{safe_profile}.toml"), self._agent_toml(safe_profile, role, instructions, model_value))

        return {
            "ok": True,
            "profile": safe_profile,
            "agentId": f"codex-{safe_profile}",
            "name": name,
            "workspace": agent_dir,
            "message": f"Codex agent '{name}' created successfully",
        }

    def delete_agent(self, profile: str) -> dict[str, Any]:
        safe_profile = self._safe_profile_name(profile)
        if not safe_profile:
            return {"ok": False, "error": "profile is required"}
        agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        if not os.path.isdir(agent_dir):
            return {"ok": True, "deleted": False, "profile": safe_profile, "agentId": f"codex-{safe_profile}"}
        shutil.rmtree(agent_dir)
        return {"ok": True, "deleted": True, "profile": safe_profile, "agentId": f"codex-{safe_profile}"}

    def send_chat_message(
        self,
        profile: str,
        message: str,
        session_id: str | None = None,
        timeout_sec: int | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        if self.prefer_app_server:
            return self._send_app_server_message(profile, message, session_id=session_id, timeout_sec=timeout_sec, on_progress=on_progress)
        return self._send_exec_message(profile, message, session_id=session_id, timeout_sec=timeout_sec)

    def interrupt(self, profile: str) -> dict[str, Any]:
        safe_profile = self._safe_profile_name(profile)
        with _ACTIVE_RUNS_LOCK:
            client = _ACTIVE_RUNS.get(safe_profile)
        if not client:
            return {"ok": False, "error": "No active Codex turn is running for this agent."}
        return client.interrupt()

    def _send_app_server_message(
        self,
        profile: str,
        message: str,
        session_id: str | None = None,
        timeout_sec: int | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "error": f"Codex CLI is not available at {self.binary}", "reply": "", "sessionId": session_id or ""}
        if not message.strip():
            return {"ok": False, "error": "message is required", "reply": "", "sessionId": session_id or ""}

        self._ensure_paths()
        safe_profile = self._safe_profile_name(profile)
        agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        if not os.path.isdir(agent_dir):
            return {"ok": False, "error": f"Codex agent workspace not found: {agent_dir}", "reply": "", "sessionId": session_id or ""}

        timeout = int(timeout_sec or self.timeout_sec)
        client = CodexAppServerClient(self, cwd=agent_dir, timeout_sec=timeout + 30)
        state = CodexAppRunState()
        started = time.time()
        last_progress = 0.0

        def emit_progress(force: bool = False) -> None:
            nonlocal last_progress
            if not on_progress:
                return
            now = time.time()
            if force or now - last_progress >= 0.25:
                on_progress(state.snapshot())
                last_progress = now

        try:
            client.initialize()
            thread_params = {
                "cwd": agent_dir,
                "approvalPolicy": self.approval_policy,
                "sandbox": self.sandbox,
                "developerInstructions": self._thread_instructions(agent_dir),
                "threadSource": "user",
            }
            if self.model:
                thread_params["model"] = self.model
            if session_id:
                thread_params["threadId"] = session_id
                thread_response = client.request("thread/resume", thread_params, event_handler=state.handle_message)
            else:
                thread_response = client.request("thread/start", thread_params, event_handler=state.handle_message)
            thread = ((thread_response.get("result") or {}).get("thread") or {}) if isinstance(thread_response, dict) else {}
            state.thread_id = str(thread.get("id") or thread.get("sessionId") or session_id or "")
            if not state.thread_id:
                return {"ok": False, "error": "Codex app-server did not return a thread id", "reply": "", "sessionId": session_id or ""}

            turn_response = client.request(
                "turn/start",
                {
                    "threadId": state.thread_id,
                    "input": [{"type": "text", "text": message, "text_elements": []}],
                    "cwd": agent_dir,
                    "approvalPolicy": self.approval_policy,
                    "model": self.model or None,
                },
                event_handler=lambda msg: (state.handle_message(msg), emit_progress())[0],
            )
            turn = ((turn_response.get("result") or {}).get("turn") or {}) if isinstance(turn_response, dict) else {}
            state.turn_id = str(turn.get("id") or state.turn_id or "")
            client.thread_id = state.thread_id
            client.turn_id = state.turn_id
            with _ACTIVE_RUNS_LOCK:
                _ACTIVE_RUNS[safe_profile] = client
            emit_progress(force=True)

            deadline = started + timeout
            while not state.completed:
                if time.time() > deadline:
                    client.interrupt()
                    return {"ok": False, "error": "Codex app-server call timed out", "reply": state.reply_text(), "sessionId": state.thread_id, "runId": state.turn_id, "providerPath": "app-server", "tools": state.tools(), "thinking": state.thinking()}
                msg = client.next_message(timeout=0.5)
                if msg is None:
                    if client.poll() is not None:
                        break
                    continue
                state.handle_message(msg)
                emit_progress()

            emit_progress(force=True)
            reply = state.reply_text()
            error_text = state.error_text()
            ok = state.status in {"completed", "interrupted"} and not (state.status == "completed" and error_text)
            return {
                "ok": ok,
                "reply": reply.strip(),
                "stderr": client.stderr_text(),
                "exitCode": 0 if ok else 1,
                "profile": safe_profile,
                "sessionId": state.thread_id,
                "runId": state.turn_id,
                "tools": state.tools(),
                "thinking": state.thinking(),
                "error": "" if ok else (error_text or f"Codex turn {state.status or 'failed'}"),
                "providerPath": "app-server",
                "interrupted": state.status == "interrupted",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "reply": state.reply_text(), "sessionId": state.thread_id or session_id or "", "runId": state.turn_id, "providerPath": "app-server", "tools": state.tools(), "thinking": state.thinking()}
        finally:
            with _ACTIVE_RUNS_LOCK:
                if _ACTIVE_RUNS.get(safe_profile) is client:
                    _ACTIVE_RUNS.pop(safe_profile, None)
            client.close()

    def _send_exec_message(self, profile: str, message: str, session_id: str | None = None, timeout_sec: int | None = None) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "error": f"Codex CLI is not available at {self.binary}", "reply": "", "sessionId": session_id or ""}
        if not message.strip():
            return {"ok": False, "error": "message is required", "reply": "", "sessionId": session_id or ""}

        safe_profile = self._safe_profile_name(profile)
        agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        if not os.path.isdir(agent_dir):
            return {"ok": False, "error": f"Codex agent workspace not found: {agent_dir}", "reply": "", "sessionId": session_id or ""}

        prompt = self._delivery_prompt(agent_dir, message)
        cmd = [self.binary, "exec"]
        if session_id:
            cmd.extend(["resume", "--json", "--skip-git-repo-check"])
            if self.model:
                cmd.extend(["-m", self.model])
            cmd.extend([session_id, "-"])
        else:
            cmd.extend(["--json", "--skip-git-repo-check", "-C", agent_dir, "--sandbox", self.sandbox])
            if self.model:
                cmd.extend(["-m", self.model])
            cmd.append("-")

        try:
            result = self._run(cmd, cwd=agent_dir, stdin=prompt, timeout_sec=int(timeout_sec or self.timeout_sec) + 30)
            parsed = self._parse_exec_json(result.stdout or "")
            stderr = (result.stderr or "").strip()
            reply = parsed.get("reply") or self._fallback_reply(result.stdout or "")
            if result.returncode != 0 and not reply:
                reply = f"[Codex error] {stderr[:1000] or 'Codex request failed'}"
            return {
                "ok": result.returncode == 0,
                "reply": reply.strip(),
                "stderr": stderr[:4000],
                "exitCode": result.returncode,
                "profile": safe_profile,
                "sessionId": parsed.get("sessionId") or session_id or "",
                "tools": parsed.get("tools") or [],
                "thinking": parsed.get("thinking") or "",
                "error": "" if result.returncode == 0 else (stderr[:2000] or "Codex request failed"),
                "providerPath": "exec",
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Codex call timed out", "reply": "", "sessionId": session_id or "", "exitCode": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "reply": "", "sessionId": session_id or "", "exitCode": None}

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.home_path:
            env["CODEX_HOME"] = self.home_path
        return env

    def _run(self, args: list[str], *, cwd: str | None = None, stdin: str | None = None, timeout_sec: int | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=int(timeout_sec or self.timeout_sec),
            env=self._subprocess_env(),
            cwd=cwd or None,
        )

    def _ensure_paths(self) -> None:
        if self.home_path:
            os.makedirs(self.home_path, exist_ok=True)
        if self.workspace_root:
            os.makedirs(self.workspace_root, exist_ok=True)

    def _thread_instructions(self, agent_dir: str) -> str:
        meta = self._load_meta(agent_dir)
        name = meta.get("name") or "Codex"
        role = meta.get("role") or "Codex Agent"
        instructions = meta.get("prompt") or role
        return (
            f"You are {name}, a Virtual Office Codex agent.\n"
            f"Role: {role}\n\n"
            f"Standing instructions:\n{instructions}\n\n"
            "Respond from that persona. When changing files, keep work scoped to this workspace unless explicitly asked otherwise."
        )

    def _delivery_prompt(self, agent_dir: str, message: str) -> str:
        return f"{self._thread_instructions(agent_dir)}\n\nUser message:\n{message}"

    def _parse_exec_json(self, stdout: str) -> dict[str, Any]:
        session_id = ""
        replies: list[str] = []
        tools: list[dict[str, Any]] = []
        reasoning: list[str] = []
        for raw in stdout.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            etype = str(event.get("type") or "")
            if etype == "thread.started":
                session_id = str(event.get("thread_id") or event.get("threadId") or session_id)
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if not item:
                continue
            itype = str(item.get("type") or "")
            if itype in {"agent_message", "message"}:
                text = item.get("text")
                if text is None and isinstance(item.get("content"), list):
                    text = "\n".join(str(p.get("text") or "") for p in item["content"] if isinstance(p, dict))
                if text:
                    replies.append(str(text))
            elif itype in {"reasoning", "agent_reasoning"}:
                text = item.get("text") or item.get("summary") or ""
                if text:
                    reasoning.append(str(text))
            elif itype in {"command_execution", "tool_call", "mcp_tool_call", "web_search"}:
                tool = self._tool_from_exec_item(item)
                if tool:
                    tools.append(tool)
        return {
            "sessionId": session_id,
            "reply": replies[-1] if replies else "",
            "tools": tools,
            "thinking": "\n".join(reasoning[-4:]),
        }

    def _tool_from_exec_item(self, item: dict[str, Any]) -> dict[str, Any]:
        tool_id = str(item.get("id") or f"codex-tool-{len(str(item))}")
        command = item.get("command") or item.get("name") or item.get("query") or item.get("type") or "tool"
        output = item.get("output") or item.get("result") or item.get("text") or ""
        error = item.get("error") or ""
        status = item.get("status") or ("error" if error else "done")
        return {
            "id": tool_id,
            "name": "codex",
            "status": status,
            "arguments": {"command": command},
            "result": self._limit_text(output),
            "error": self._limit_text(error),
            "source": "codex",
        }

    @staticmethod
    def _fallback_reply(stdout: str) -> str:
        non_json = []
        for raw in stdout.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                non_json.append(raw)
        return "\n".join(non_json[-20:])

    @staticmethod
    def _limit_text(value: Any, limit: int = 2400) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        value = str(value)
        return value if len(value) <= limit else value[:limit] + f"\n\n... [truncated - {len(value)} chars total] ..."

    def _load_meta(self, agent_dir: str) -> dict[str, Any]:
        try:
            with open(os.path.join(agent_dir, "office-agent.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _resolve_binary(value: str | None) -> str:
        candidates = [
            value,
            os.environ.get("VO_CODEX_BIN"),
            shutil.which("codex"),
            os.path.expanduser("~/.local/bin/codex"),
        ]
        home = os.environ.get("VO_CODEX_HOME") or os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
        if home:
            candidates.append(os.path.join(os.path.expanduser(home), "packages", "standalone", "current", "bin", "codex"))
        for candidate in candidates:
            if not candidate:
                continue
            expanded = os.path.expanduser(str(candidate))
            resolved = shutil.which(expanded) if os.path.basename(expanded) == expanded else expanded
            if resolved and os.path.isfile(resolved):
                return resolved
        return os.path.expanduser(str(value or os.environ.get("VO_CODEX_BIN") or "codex"))

    @staticmethod
    def _account_status_text(account_result: Any) -> str:
        if not isinstance(account_result, dict):
            return ""
        account = account_result.get("account")
        if isinstance(account, dict):
            account_type = account.get("type") or "authenticated"
            email = account.get("email")
            plan = account.get("planType")
            suffix = " ".join(str(x) for x in [email, plan] if x)
            return f"{account_type} {suffix}".strip()
        if account_result.get("requiresOpenaiAuth") is False:
            return "No OpenAI auth required for configured provider"
        return "Not authenticated"

    @staticmethod
    def _safe_profile_name(value: str | None) -> str:
        raw = str(value or "").strip().lower()
        raw = re.sub(r"[^a-z0-9_.-]+", "-", raw).strip("-._")
        return raw[:64] or "codex-agent"

    @staticmethod
    def _safe_suffix(value: str | None) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "codex-agent")).strip("-")[:80] or "codex-agent"

    @staticmethod
    def _display_name(profile: str) -> str:
        return str(profile or "codex").replace("-", " ").replace("_", " ").title()

    @staticmethod
    def _last_active(agent_dir: str) -> int:
        latest = 0
        try:
            for root, dirs, files in os.walk(agent_dir):
                dirs[:] = [d for d in dirs if d not in {"node_modules", ".git"}]
                for fname in files:
                    latest = max(latest, int(os.path.getmtime(os.path.join(root, fname))))
        except OSError:
            pass
        return latest

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
        return (
            "# IDENTITY.md\n\n"
            f"- **Name:** {name}\n"
            f"- **Creature:** {role or 'Codex Agent'}\n"
            f"- **Emoji:** {emoji or '🤖'}\n"
        )

    def _agents_md(self, name: str, role: str, instructions: str) -> str:
        return (
            f"# {name}\n\n"
            f"Role: {role or 'Codex Agent'}\n\n"
            "## Standing Instructions\n\n"
            f"{instructions.strip()}\n"
        )

    def _config_toml(self, model: str) -> str:
        lines = []
        if model:
            lines.append(f"model = {self._toml_string(model)}")
        lines.append(f"sandbox_mode = {self._toml_string(self.sandbox)}")
        lines.append(f"approval_policy = {self._toml_string(self.approval_policy)}")
        lines.append("")
        lines.append("[features]")
        lines.append("multi_agent = true")
        return "\n".join(lines) + "\n"

    def _agent_toml(self, profile: str, role: str, instructions: str, model: str) -> str:
        lines = [
            f"name = {self._toml_string(profile)}",
            f"description = {self._toml_string(role or 'Virtual Office Codex agent')}",
            f"developer_instructions = {self._toml_string(instructions)}",
        ]
        if model:
            lines.append(f"model = {self._toml_string(model)}")
        lines.append(f"sandbox_mode = {self._toml_string(self.sandbox)}")
        return "\n".join(lines) + "\n"


class CodexAppServerClient:
    """Small JSON-RPC client for `codex app-server --stdio`."""

    def __init__(self, provider: CodexProvider, cwd: str, timeout_sec: int = 930) -> None:
        self.provider = provider
        self.cwd = cwd
        self.timeout_sec = int(timeout_sec)
        self.thread_id = ""
        self.turn_id = ""
        self._next_id = 1
        self._send_lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._stderr: list[str] = []
        self._closed = False
        self.proc = subprocess.Popen(
            [provider.binary or "codex", "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=provider._subprocess_env(),
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def initialize(self) -> dict[str, Any]:
        response = self.request(
            "initialize",
            {
                "clientInfo": {"name": "my-virtual-office", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
            timeout_sec=15,
        )
        self.notify("initialized")
        return response

    def request(self, method: str, params: Any | None = None, *, timeout_sec: int | None = None, event_handler: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        request_id = self._allocate_id()
        payload: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        deadline = time.time() + int(timeout_sec or self.timeout_sec)
        while time.time() < deadline:
            msg = self.next_message(timeout=0.5)
            if msg is None:
                if self.poll() is not None:
                    raise RuntimeError(self.stderr_text() or "Codex app-server exited")
                continue
            if msg.get("id") == request_id:
                if "error" in msg:
                    raise RuntimeError(self._rpc_error_text(msg.get("error")))
                return msg
            self._handle_or_forward(msg, event_handler)
        raise TimeoutError(f"Timed out waiting for Codex app-server response to {method}")

    def notify(self, method: str, params: Any | None = None) -> None:
        payload: dict[str, Any] = {"method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def next_message(self, timeout: float = 0.5) -> dict[str, Any] | None:
        try:
            msg = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return msg

    def interrupt(self) -> dict[str, Any]:
        if not self.thread_id or not self.turn_id:
            return {"ok": False, "error": "Codex turn id is not known yet."}
        try:
            request_id = self._allocate_id()
            self._send({"id": request_id, "method": "turn/interrupt", "params": {"threadId": self.thread_id, "turnId": self.turn_id}})
            return {"ok": True, "threadId": self.thread_id, "turnId": self.turn_id, "requestId": request_id}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "threadId": self.thread_id, "turnId": self.turn_id}

    def poll(self) -> int | None:
        return self.proc.poll()

    def stderr_text(self) -> str:
        return "\n".join(self._stderr[-80:])[:4000]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass

    def _handle_or_forward(self, msg: dict[str, Any], event_handler: Callable[[dict[str, Any]], None] | None = None) -> None:
        if "id" in msg and msg.get("method"):
            self._answer_server_request(msg)
            return
        if event_handler:
            event_handler(msg)

    def _answer_server_request(self, msg: dict[str, Any]) -> None:
        request_id = msg.get("id")
        method = str(msg.get("method") or "")
        if request_id is None:
            return
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            self._send({"id": request_id, "result": {"decision": "cancel"}})
        elif method == "item/permissions/requestApproval":
            self._send({"id": request_id, "result": {"permissions": {"fileSystem": None, "network": None}, "scope": "turn"}})
        elif method in {"item/tool/requestUserInput", "mcpServer/elicitation/request"}:
            self._send({"id": request_id, "result": {"answers": {}}})
        else:
            self._send({"id": request_id, "error": {"code": -32601, "message": f"Unsupported Codex server request: {method}"}})

    def _send(self, payload: dict[str, Any]) -> None:
        if not self.proc.stdin:
            raise RuntimeError("Codex app-server stdin is closed")
        with self._send_lock:
            self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()

    def _allocate_id(self) -> int:
        with self._send_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def _read_stdout(self) -> None:
        if not self.proc.stdout:
            return
        for line in self.proc.stdout:
            raw = line.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
                if isinstance(msg, dict):
                    self._queue.put(msg)
            except json.JSONDecodeError:
                self._stderr.append(raw)

    def _read_stderr(self) -> None:
        if not self.proc.stderr:
            return
        for line in self.proc.stderr:
            text = line.rstrip("\n")
            if text:
                self._stderr.append(text)

    @staticmethod
    def _rpc_error_text(error: Any) -> str:
        if isinstance(error, dict):
            return str(error.get("message") or error)
        return str(error or "Codex app-server request failed")


class CodexAppRunState:
    """Collects Codex app-server notifications into Office chat artifacts."""

    def __init__(self) -> None:
        self.thread_id = ""
        self.turn_id = ""
        self.status = "inProgress"
        self.completed = False
        self._reply_delta = ""
        self._reply_final = ""
        self._reasoning_parts: list[str] = []
        self._plan = ""
        self._errors: list[str] = []
        self._tools: dict[str, dict[str, Any]] = {}
        self._tool_order: list[str] = []

    def handle_message(self, msg: dict[str, Any]) -> None:
        method = str(msg.get("method") or "")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if params.get("threadId"):
            self.thread_id = str(params.get("threadId") or self.thread_id)
        if params.get("turnId"):
            self.turn_id = str(params.get("turnId") or self.turn_id)

        if method == "turn/started":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            self.turn_id = str(turn.get("id") or self.turn_id)
            self.status = str(turn.get("status") or self.status)
        elif method == "item/agentMessage/delta":
            self._reply_delta += str(params.get("delta") or "")
        elif method in {"item/reasoning/summaryTextDelta", "item/reasoning/textDelta"}:
            delta = str(params.get("delta") or "")
            if delta:
                self._reasoning_parts.append(delta)
        elif method == "turn/plan/updated":
            plan = params.get("plan") if isinstance(params.get("plan"), list) else []
            lines = []
            for step in plan:
                if isinstance(step, dict):
                    status = str(step.get("status") or "").replace("inProgress", "in progress")
                    lines.append(f"- {step.get('step') or ''} ({status})".strip())
            explanation = params.get("explanation")
            self._plan = "\n".join([str(explanation or "").strip(), *lines]).strip()
        elif method in {"item/started", "item/completed"}:
            item = params.get("item") if isinstance(params.get("item"), dict) else {}
            self._handle_item(item, completed=(method == "item/completed"))
        elif method == "item/commandExecution/outputDelta":
            item_id = str(params.get("itemId") or "")
            delta = str(params.get("delta") or "")
            if item_id and delta:
                tool = self._tools.get(item_id)
                if tool:
                    tool["result"] = CodexProvider._limit_text(str(tool.get("result") or "") + delta)
        elif method == "error":
            error = params.get("error") if isinstance(params.get("error"), dict) else {}
            text = error.get("message") or params.get("message") or "Codex turn failed"
            self._errors.append(str(text))
        elif method == "turn/completed":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            self.turn_id = str(turn.get("id") or self.turn_id)
            self.status = str(turn.get("status") or self.status or "completed")
            if isinstance(turn.get("error"), dict):
                err = turn["error"].get("message")
                if err:
                    self._errors.append(str(err))
            for item in turn.get("items") or []:
                if isinstance(item, dict):
                    self._handle_item(item, completed=True)
            self.completed = True

    def snapshot(self) -> dict[str, Any]:
        return {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "runId": self.turn_id,
            "reply": self.reply_text(),
            "tools": self.tools(),
            "thinking": self.thinking(),
            "status": self.status,
            "error": self.error_text(),
        }

    def reply_text(self) -> str:
        return self._reply_final or self._reply_delta

    def thinking(self) -> str:
        parts = []
        if self._plan:
            parts.append(self._plan)
        reasoning = "".join(self._reasoning_parts).strip()
        if reasoning:
            parts.append(reasoning)
        return "\n\n".join(parts)[:12000]

    def tools(self) -> list[dict[str, Any]]:
        return [self._tools[k] for k in self._tool_order if k in self._tools][-60:]

    def error_text(self) -> str:
        return "\n".join(dict.fromkeys([e for e in self._errors if e]))[:2000]

    def _handle_item(self, item: dict[str, Any], completed: bool = False) -> None:
        item_type = str(item.get("type") or "")
        if item_type == "agentMessage":
            text = str(item.get("text") or "")
            if text:
                self._reply_final = text
            return
        if item_type == "reasoning":
            for part in (item.get("summary") or []) + (item.get("content") or []):
                if isinstance(part, str) and part.strip():
                    self._reasoning_parts.append(part)
            return

        tool = self._tool_from_app_item(item, completed=completed)
        if not tool:
            return
        tool_id = tool["id"]
        if tool_id not in self._tools:
            self._tool_order.append(tool_id)
        existing = self._tools.get(tool_id, {})
        existing.update({k: v for k, v in tool.items() if v not in (None, "") or k not in existing})
        self._tools[tool_id] = existing

    def _tool_from_app_item(self, item: dict[str, Any], completed: bool = False) -> dict[str, Any] | None:
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or f"codex-{len(self._tools) + 1}")
        status = self._normalize_status(item.get("status"), completed)
        if item_type == "commandExecution":
            return {
                "id": item_id,
                "name": "shell",
                "status": status,
                "arguments": {"command": item.get("command") or "", "cwd": item.get("cwd") or ""},
                "result": CodexProvider._limit_text(item.get("aggregatedOutput") or ""),
                "error": "" if status != "error" else CodexProvider._limit_text(item.get("aggregatedOutput") or ""),
                "source": "codex",
            }
        if item_type == "fileChange":
            changes = item.get("changes") if isinstance(item.get("changes"), list) else []
            paths = []
            for change in changes:
                if isinstance(change, dict):
                    paths.append(str(change.get("path") or change.get("file") or change.get("uri") or "file"))
            return {
                "id": item_id,
                "name": "file changes",
                "status": status,
                "arguments": {"files": paths[:20], "count": len(changes)},
                "result": f"{len(changes)} file change(s)" if changes else "",
                "error": "",
                "source": "codex",
            }
        if item_type == "mcpToolCall":
            error = item.get("error")
            return {
                "id": item_id,
                "name": ".".join(x for x in [str(item.get("server") or ""), str(item.get("tool") or "mcp")] if x),
                "status": "error" if error else status,
                "arguments": item.get("arguments") or {},
                "result": CodexProvider._limit_text(item.get("result") or ""),
                "error": CodexProvider._limit_text(error or ""),
                "source": "codex",
            }
        if item_type == "dynamicToolCall":
            return {
                "id": item_id,
                "name": item.get("tool") or "tool",
                "status": status,
                "arguments": item.get("arguments") or {},
                "result": CodexProvider._limit_text(item.get("contentItems") or ""),
                "error": "" if item.get("success") is not False else "Tool call failed",
                "source": "codex",
            }
        if item_type == "webSearch":
            return {
                "id": item_id,
                "name": "web search",
                "status": status,
                "arguments": {"query": item.get("query") or ""},
                "result": CodexProvider._limit_text(item.get("action") or ""),
                "error": "",
                "source": "codex",
            }
        return None

    @staticmethod
    def _normalize_status(value: Any, completed: bool) -> str:
        raw = str(value or "").lower()
        if raw in {"completed", "done", "success", "succeeded"}:
            return "done"
        if raw in {"failed", "error", "declined"}:
            return "error"
        if completed:
            return "done"
        return "running"
