"""Claude Code provider adapter for My Virtual Office.

This shallow integration exposes one optional Claude Code-backed office agent,
supports safe discovery/test behavior, and can run basic non-interactive chat
through the Claude Code CLI when available.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any


_ACTIVE_RUNS: dict[str, subprocess.Popen] = {}
_ACTIVE_RUNS_LOCK = threading.Lock()


def _env_bool(key: str, fallback: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None or str(value).strip() == "":
        return bool(fallback)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


@dataclass
class ClaudeCodeProvider:
    enabled: bool = False
    home_path: str | None = None
    binary: str | None = None
    workspace: str | None = None
    workspace_root: str | None = None
    main_workspace: str | None = None
    name: str | None = None
    agent_id: str | None = None
    model: str | None = None
    reply_text: str | None = None
    timeout_sec: int = 900
    permission_mode: str = "acceptEdits"
    include_main: bool = True
    include_native_agents: bool = True
    register_native_agents: bool = True

    provider_kind: str = "claude-code"
    provider_type: str = "harness"

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.home_path = os.path.expanduser(
            self.home_path
            or os.environ.get("VO_CLAUDE_CODE_HOME")
            or os.environ.get("VO_CLAUDE_HOME")
            or "~/.claude"
        )
        self.binary = self._resolve_binary(self.binary)
        self.workspace = os.path.abspath(os.path.expanduser(
            self.workspace
            or os.environ.get("VO_CLAUDE_CODE_WORKSPACE")
            or os.getcwd()
        ))
        status_dir = os.environ.get("VO_STATUS_DIR", "/tmp")
        self.workspace_root = os.path.abspath(os.path.expanduser(
            self.workspace_root
            or os.environ.get("VO_CLAUDE_CODE_WORKSPACE_ROOT")
            or os.path.join(status_dir, "claude-code-agents")
        ))
        self.main_workspace = os.path.abspath(os.path.expanduser(
            self.main_workspace
            or os.environ.get("VO_CLAUDE_CODE_MAIN_WORKSPACE")
            or self.workspace
        ))
        self.name = self.name or os.environ.get("VO_CLAUDE_CODE_AGENT_NAME") or "Claude Code"
        self.agent_id = self._safe_suffix(self.agent_id or os.environ.get("VO_CLAUDE_CODE_AGENT_ID") or "local")
        self.model = self.model or os.environ.get("VO_CLAUDE_CODE_MODEL") or ""
        self.reply_text = self.reply_text if self.reply_text is not None else os.environ.get("VO_CLAUDE_CODE_REPLY_TEXT")
        self.permission_mode = str(self.permission_mode or os.environ.get("VO_CLAUDE_CODE_PERMISSION_MODE") or "acceptEdits")
        self.include_main = _env_bool("VO_CLAUDE_CODE_INCLUDE_MAIN", self.include_main)
        self.include_native_agents = _env_bool("VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS", self.include_native_agents)
        self.register_native_agents = _env_bool("VO_CLAUDE_CODE_REGISTER_NATIVE_AGENTS", self.register_native_agents)
        try:
            self.timeout_sec = int(self.timeout_sec or os.environ.get("VO_CLAUDE_CODE_TIMEOUT_SEC") or 900)
        except (TypeError, ValueError):
            self.timeout_sec = 900

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.reply_text:
            return True
        return bool(self.binary and os.path.isfile(self.binary) and os.access(self.binary, os.X_OK))

    def discover_agents(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        agents = [self._agent_entry(
            profile=self.agent_id or "local",
            name=self.name or "Claude Code",
            emoji=os.environ.get("VO_CLAUDE_CODE_AGENT_EMOJI", "🧠"),
            role="Claude Code Collaborator",
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
                role="Default Claude Code agent",
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
                role=meta.get("role") or "Claude Code Agent",
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
            return {"ok": False, "error": "Claude Code provider is disabled. Set VO_CLAUDE_CODE_ENABLED=1 to expose it.", "agents": []}
        if self.reply_text:
            return {"ok": True, "mode": "replyText", "workspace": self.workspace, "agents": self.discover_agents()}
        if not self.binary or not os.path.isfile(self.binary):
            return {"ok": False, "installed": False, "error": "Claude Code CLI not found. Set VO_CLAUDE_CODE_BIN or install claude on PATH.", "agents": []}
        if not os.access(self.binary, os.X_OK):
            return {"ok": False, "installed": True, "error": f"Claude Code CLI is not executable at {self.binary}", "agents": []}
        try:
            auth = subprocess.run(
                [self.binary, "auth", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=20,
                env=self._subprocess_env(),
            )
            raw = (auth.stdout or auth.stderr or "").strip()
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {}
            if auth.returncode == 0 or parsed:
                auth_ok = bool(parsed.get("loggedIn") or parsed.get("authenticated") or parsed.get("account"))
                return {
                    "ok": auth_ok,
                    "installed": True,
                    "authOk": auth_ok,
                    "authStatus": parsed or raw[:500],
                    "binary": self.binary,
                    "homePath": self.home_path,
                    "workspace": self.workspace,
                    "workspaceRoot": self.workspace_root,
                    "mainWorkspace": self.main_workspace,
                    "error": "" if auth_ok else "Claude Code is installed but not authenticated. Run claude auth login for this environment.",
                    "agents": self.discover_agents() if auth_ok else [],
                }
            result = subprocess.run(
                [self.binary, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                env=self._subprocess_env(),
            )
            text = (result.stdout or result.stderr or "").strip()[:500]
            return {
                "ok": result.returncode == 0,
                "installed": True,
                "authOk": None,
                "authStatus": text,
                "binary": self.binary,
                "homePath": self.home_path,
                "workspace": self.workspace,
                "workspaceRoot": self.workspace_root,
                "mainWorkspace": self.main_workspace,
                "version": text,
                "error": "" if result.returncode == 0 else (text or "Claude Code version check failed"),
                "agents": self.discover_agents() if result.returncode == 0 else [],
            }
        except Exception as exc:
            return {"ok": False, "installed": True, "error": str(exc), "agents": []}

    def send_chat_message(
        self,
        message: str,
        conversation_id: str = "",
        timeout_sec: int | None = None,
        session_id: str | None = None,
        on_progress: Any | None = None,
    ) -> dict[str, Any]:
        text = str(message or "").strip()
        def emit_progress(payload: dict[str, Any]) -> None:
            if not callable(on_progress):
                return
            try:
                on_progress(payload)
            except Exception:
                pass

        if not self.enabled:
            return {"ok": False, "error": "Claude Code provider is disabled", "reply": "", "sessionId": session_id or ""}
        if not text:
            return {"ok": False, "error": "message is required", "reply": "", "sessionId": session_id or ""}
        if self.reply_text:
            demo_session = session_id or f"demo-{self._safe_suffix(conversation_id or 'conversation')}"
            result = {
                "ok": True,
                "reply": self.reply_text,
                "conversationId": conversation_id,
                "mode": "replyText",
                "status": "completed",
                "sessionId": demo_session,
                "runId": demo_session,
                "tools": [],
                "thinking": "",
                "modifiedFiles": [],
            }
            emit_progress({
                "status": "completed",
                "reply": self.reply_text,
                "conversationId": conversation_id,
                "sessionId": demo_session,
                "runId": demo_session,
                "providerPath": "claude-code-cli",
                "tools": [],
                "thinking": "",
                "tokenUsage": {},
                "model": self.model or "",
            })
            return result
        if not self.binary or not os.path.isfile(self.binary):
            return {"ok": False, "error": f"Claude Code CLI not found at {self.binary}", "reply": "", "sessionId": session_id or ""}

        profile = self._safe_profile_name(self.agent_id or "local")
        workspace = self._workspace_for_profile(profile)
        os.makedirs(workspace or self.workspace or os.getcwd(), exist_ok=True)
        cmd = [self.binary, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        if session_id:
            cmd.extend(["--resume", session_id])
        if profile and profile not in {"main", "local"}:
            cmd.extend(["--agent", profile])
        if self.model:
            cmd.extend(["--model", self.model])
        permission_mode = str(self.permission_mode or "").strip()
        if permission_mode == "bypassPermissions":
            cmd.append("--dangerously-skip-permissions")
        elif permission_mode:
            cmd.extend(["--permission-mode", permission_mode])
        cmd.append(text)

        state = _ClaudeStreamState(session_id=session_id or "")
        stderr_lines: list[str] = []
        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=workspace or self.workspace,
                env=self._subprocess_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with _ACTIVE_RUNS_LOCK:
                _ACTIVE_RUNS[profile] = proc

            def read_stderr() -> None:
                if not proc or not proc.stderr:
                    return
                for raw in proc.stderr:
                    if raw:
                        stderr_lines.append(raw.rstrip("\n"))

            threading.Thread(target=read_stderr, daemon=True).start()

            deadline = time.time() + int(timeout_sec or self.timeout_sec or 900)
            if not proc.stdout:
                return {"ok": False, "error": "Claude Code stdout pipe was not available", "reply": "", "sessionId": session_id or ""}
            for raw in proc.stdout:
                if time.time() > deadline:
                    proc.kill()
                    return {"ok": False, "status": "timeout", "error": "Claude Code call timed out", "reply": state.reply, "sessionId": state.session_id or session_id or ""}
                line = raw.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    state.add_text(line)
                    emit_progress(state.snapshot(
                        conversation_id=conversation_id,
                        token_usage=self._usage_to_token_usage(state.usage),
                    ))
                    continue
                state.ingest(item)
                emit_progress(state.snapshot(
                    conversation_id=conversation_id,
                    token_usage=self._usage_to_token_usage(state.usage),
                ))
            exit_code = proc.wait(timeout=5)
            reply = state.final_result or state.reply
            return {
                "ok": exit_code == 0 and not state.is_error,
                "status": "completed" if exit_code == 0 and not state.is_error else "execution_failed",
                "reply": reply,
                "stderr": "\n".join(stderr_lines)[-4000:],
                "exitCode": exit_code,
                "conversationId": conversation_id,
                "sessionId": state.session_id or session_id or "",
                "runId": state.session_id or "",
                "providerPath": "claude-code-cli",
                "tools": state.tools,
                "thinking": state.status,
                "tokenUsage": self._usage_to_token_usage(state.usage),
                "usage": state.usage,
                "model": state.model,
                "error": state.error,
                "modifiedFiles": [],
            }
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            return {"ok": False, "status": "timeout", "error": "Claude Code call timed out", "reply": state.reply, "sessionId": state.session_id or session_id or ""}
        except Exception as exc:
            return {"ok": False, "status": "execution_failed", "error": str(exc), "reply": state.reply, "sessionId": state.session_id or session_id or ""}
        finally:
            with _ACTIVE_RUNS_LOCK:
                if _ACTIVE_RUNS.get(profile) is proc:
                    _ACTIVE_RUNS.pop(profile, None)

    def interrupt(self, profile: str | None = None) -> dict[str, Any]:
        safe_profile = self._safe_suffix(profile or self.agent_id or "local")
        with _ACTIVE_RUNS_LOCK:
            proc = _ACTIVE_RUNS.get(safe_profile)
        if not proc:
            return {"ok": False, "error": "No active Claude Code turn is running for this agent."}
        try:
            proc.terminate()
            return {"ok": True, "interrupted": True, "profile": safe_profile}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def create_agent(
        self,
        name: str,
        role: str = "Claude Code Agent",
        model: str | None = None,
        emoji: str = "🤖",
        profile: str | None = None,
        prompt: str | None = None,
        creation_mode: str = "standard",
        custom_directory: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "Claude Code provider is disabled"}
        safe_profile = self._safe_profile_name(profile or name)
        if not safe_profile or safe_profile == "main":
            return {"ok": False, "error": "Invalid Claude Code profile name"}
        if self._profile_exists(safe_profile):
            return {"ok": False, "error": f"Claude Code agent '{safe_profile}' already exists"}
        mode = str(creation_mode or "standard").strip().lower()
        if mode not in {"standard", "custom"}:
            mode = "standard"
        if mode == "custom":
            parent = self._resolve_custom_parent(custom_directory)
            if not parent:
                return {"ok": False, "error": "A custom parent directory is required"}
            native_dir = self._native_agents_dir()
            if native_dir and self._path_is_inside(parent, native_dir):
                return {"ok": False, "error": "Custom workspace cannot be inside the Claude Code native agents directory"}
            agent_dir = os.path.join(parent, safe_profile)
        else:
            agent_dir = os.path.join(self.workspace_root or "", safe_profile)
        if os.path.exists(os.path.join(agent_dir, "office-agent.json")):
            return {"ok": False, "error": f"Claude Code agent '{safe_profile}' already exists"}
        native_path = self._native_agent_file_path(safe_profile) if mode == "standard" else ""
        should_register_native = bool(mode == "standard" and self.register_native_agents and native_path)
        if should_register_native and os.path.exists(native_path):
            return {"ok": False, "error": f"Native Claude Code agent '{safe_profile}' already exists"}
        os.makedirs(os.path.join(agent_dir, ".claude", "agents"), exist_ok=True)
        model_value = (model or self.model or "").strip()
        instructions = (prompt or role or "Claude Code Agent").strip()
        project_agent_path = os.path.join(agent_dir, ".claude", "agents", f"{safe_profile}.md")
        meta = {
            "profile": safe_profile,
            "name": name,
            "emoji": emoji or "🤖",
            "role": role or "Claude Code Agent",
            "prompt": instructions,
            "model": model_value,
            "providerKind": self.provider_kind,
            "providerType": self.provider_type,
            "creationMode": mode,
            "customParentDirectory": os.path.dirname(agent_dir) if mode == "custom" else "",
            "nativeAgentPath": native_path if should_register_native else "",
            "projectAgentPath": project_agent_path,
            "createdAt": int(time.time()),
        }
        self._write_json(os.path.join(agent_dir, "office-agent.json"), meta)
        self._write_text(os.path.join(agent_dir, "IDENTITY.md"), self._identity_md(name, role, emoji))
        self._write_text(os.path.join(agent_dir, "AGENTS.md"), self._agents_md(name, role, instructions))
        self._write_text(os.path.join(agent_dir, "CLAUDE.md"), self._claude_md(name, role, instructions))
        self._write_text(project_agent_path, self._agent_md(safe_profile, role, instructions, model_value))
        if should_register_native:
            self._write_text(native_path, self._agent_md(safe_profile, role, instructions, model_value))
        if mode == "custom":
            self._save_external_agent(safe_profile, agent_dir)
        return {
            "ok": True,
            "profile": safe_profile,
            "agentId": f"claude-code-{safe_profile}",
            "name": name,
            "workspace": agent_dir,
            "creationMode": mode,
            "nativeAgentPath": native_path if should_register_native else "",
            "message": f"Claude Code agent '{name}' created successfully",
        }

    def delete_agent(self, profile: str) -> dict[str, Any]:
        safe_profile = self._safe_profile_name(profile)
        if not safe_profile:
            return {"ok": False, "error": "profile is required"}
        if safe_profile == "main" or safe_profile == self._safe_profile_name(self.agent_id):
            return {"ok": False, "error": "The built-in Claude Code agent cannot be deleted"}
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
        return {"ok": True, "deleted": deleted, "profile": safe_profile, "agentId": f"claude-code-{safe_profile}"}

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.home_path:
            env["VO_CLAUDE_CODE_HOME"] = self.home_path
            env.setdefault("CLAUDE_CONFIG_DIR", self.home_path)
            if os.path.basename(self.home_path.rstrip(os.sep)) == ".claude":
                env["HOME"] = os.path.dirname(self.home_path.rstrip(os.sep)) or env.get("HOME", "")
        return env

    @staticmethod
    def _resolve_binary(value: str | None) -> str:
        candidates = [
            value,
            os.environ.get("VO_CLAUDE_CODE_BIN"),
            os.environ.get("VO_CLAUDE_BIN"),
            shutil.which("claude"),
            os.path.expanduser("~/.npm-global/bin/claude"),
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/local/bin/claude",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            expanded = os.path.expanduser(str(candidate))
            resolved = shutil.which(expanded) if os.path.basename(expanded) == expanded else expanded
            if resolved and os.path.isfile(resolved):
                return resolved
        return os.path.expanduser(str(value or os.environ.get("VO_CLAUDE_CODE_BIN") or "claude"))

    @staticmethod
    def _safe_suffix(value: str | None) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "local")).strip("-")[:80] or "local"

    @staticmethod
    def _last_active(path: str | None) -> int:
        if not path or not os.path.isdir(path):
            return int(time.time())
        latest = 0.0
        try:
            for name in (".git", ".claude", "CLAUDE.md"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    latest = max(latest, os.path.getmtime(candidate))
            latest = max(latest, os.path.getmtime(path))
        except OSError:
            pass
        return int(latest or time.time())

    def _agent_entry(self, *, profile: str, name: str, emoji: str, role: str, model: str, workspace: str, source: str, last_active: int = 0, native_agent_path: str = "") -> dict[str, Any]:
        suffix = self._safe_suffix(profile)
        return {
            "id": f"claude-code-{suffix}",
            "statusKey": f"claude-code-{suffix}",
            "providerKind": self.provider_kind,
            "providerType": self.provider_type,
            "providerAgentId": profile,
            "profile": profile,
            "name": name or self._display_name(profile),
            "emoji": emoji or "🤖",
            "role": role or "Claude Code Agent",
            "model": model or self.model or "",
            "provider": "Claude Code",
            "workspace": workspace,
            "home": workspace,
            "binary": self.binary,
            "lastActiveAt": last_active or self._last_active(workspace),
            "claudeCodeSource": source,
            "nativeAgentPath": native_agent_path,
            "capabilities": ["chat", "status", "sessions", "files", "streaming", "interrupt"],
            "bridgeConfigured": bool(self.reply_text or (self.binary and os.path.isfile(self.binary))),
        }

    def _office_agent_dirs(self) -> list[str]:
        dirs: list[str] = []
        seen: set[str] = set()
        if self.workspace_root and os.path.isdir(self.workspace_root):
            for name in sorted(os.listdir(self.workspace_root)):
                agent_dir = os.path.join(self.workspace_root, name)
                if os.path.isdir(agent_dir) and os.path.isfile(os.path.join(agent_dir, "office-agent.json")):
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
        for root, dirs, files in os.walk(agents_dir):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git"}]
            for filename in sorted(files):
                if not filename.endswith(".md"):
                    continue
                path = os.path.join(root, filename)
                meta = self._load_agent_md(path)
                if not meta:
                    continue
                profile = self._safe_profile_name(meta.get("name") or os.path.splitext(filename)[0])
                if profile in seen_profiles:
                    continue
                seen_profiles.add(profile)
                agents.append(self._agent_entry(
                    profile=profile,
                    name=self._display_name(profile),
                    emoji="🤖",
                    role=meta.get("description") or "Claude Code Agent",
                    model=meta.get("model") or self.model or "",
                    workspace=self._workspace_for_profile(profile),
                    source="native-user-agent",
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

    def _load_agent_md(self, path: str) -> dict[str, str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(20000)
        except (OSError, UnicodeError):
            return {}
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        meta: dict[str, str] = {}
        for raw in parts[1].splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("'\"")
        return meta if meta.get("name") and meta.get("description") else {}

    def _profile_exists(self, profile: str) -> bool:
        safe_profile = self._safe_profile_name(profile)
        if safe_profile in {"main", self._safe_profile_name(self.agent_id)}:
            return True
        if os.path.isdir(os.path.join(self.workspace_root or "", safe_profile)):
            return True
        if self._external_agent_dir(safe_profile):
            return True
        native = self._native_agent_file_path(safe_profile)
        return bool(native and os.path.exists(native))

    def _native_agents_dir(self) -> str:
        return os.path.join(os.path.expanduser(self.home_path or "~/.claude"), "agents")

    def _native_agent_file_path(self, profile: str) -> str:
        return os.path.join(self._native_agents_dir(), f"{self._safe_profile_name(profile)}.md")

    def _registry_path(self) -> str:
        root = self.workspace_root or os.environ.get("VO_STATUS_DIR", "/tmp")
        return os.path.join(os.path.expanduser(root), "office-claude-code-agent-registry.json")

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
            "schema": "my-virtual-office.claude-code-agent-registry.v1",
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

    def _workspace_for_profile(self, profile: str) -> str:
        safe_profile = self._safe_profile_name(profile or self.agent_id or "local")
        if safe_profile == "main":
            return self.main_workspace or self.workspace
        if safe_profile == "local" and safe_profile == self._safe_profile_name(self.agent_id or "local"):
            return self.workspace
        external = self._external_agent_dir(safe_profile)
        if external:
            return external
        candidate = os.path.join(self.workspace_root or "", safe_profile)
        if os.path.isdir(candidate):
            return candidate
        return self.workspace

    @staticmethod
    def _resolve_custom_parent(value: str | None) -> str:
        raw = str(value or "").strip()
        return os.path.abspath(os.path.expanduser(raw)) if raw else ""

    def _is_native_agent_path(self, path: str) -> bool:
        agents_dir = self._native_agents_dir()
        return bool(path and agents_dir and self._path_is_inside(path, agents_dir))

    @staticmethod
    def _path_is_inside(path: str, parent: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(parent), os.path.abspath(path)]) == os.path.abspath(parent)
        except ValueError:
            return False

    @staticmethod
    def _display_name(profile: str) -> str:
        if profile == "main":
            return "Main"
        return str(profile or "claude").replace("-", " ").replace("_", " ").title()

    @staticmethod
    def _safe_profile_name(value: str | None) -> str:
        raw = str(value or "").strip().lower()
        raw = re.sub(r"[^a-z0-9_.-]+", "-", raw).strip("-._")
        return raw[:64] or "claude-agent"

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
    def _yaml_string(value: str) -> str:
        text = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
        return f'"{text}"'

    def _identity_md(self, name: str, role: str, emoji: str) -> str:
        return "# IDENTITY.md\n\n" f"- **Name:** {name}\n" f"- **Creature:** {role or 'Claude Code Agent'}\n" f"- **Emoji:** {emoji or '🤖'}\n"

    def _agents_md(self, name: str, role: str, instructions: str) -> str:
        return f"# {name}\n\nRole: {role or 'Claude Code Agent'}\n\n## Standing Instructions\n\n{instructions.strip()}\n"

    def _claude_md(self, name: str, role: str, instructions: str) -> str:
        return f"# {name}\n\nYou are {name}, a Claude Code-backed Virtual Office agent.\n\nRole: {role or 'Claude Code Agent'}\n\nFollow these standing instructions:\n\n{instructions.strip()}\n"

    def _agent_md(self, profile: str, role: str, instructions: str, model: str) -> str:
        lines = ["---", f"name: {self._yaml_string(profile)}", f"description: {self._yaml_string(role or 'Virtual Office Claude Code agent')}"]
        if model:
            lines.append(f"model: {self._yaml_string(model)}")
        lines.extend(["---", instructions.strip(), ""])
        return "\n".join(lines)

    @staticmethod
    def _usage_to_token_usage(usage: dict[str, Any]) -> dict[str, Any]:
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = _to_int(usage.get("input_tokens") or usage.get("inputTokens"), 0)
        output_tokens = _to_int(usage.get("output_tokens") or usage.get("outputTokens"), 0)
        cache_create = _to_int(usage.get("cache_creation_input_tokens") or usage.get("cacheCreationInputTokens"), 0)
        cache_read = _to_int(usage.get("cache_read_input_tokens") or usage.get("cacheReadInputTokens"), 0)
        total = input_tokens + output_tokens + cache_create + cache_read
        if not total:
            return {}
        return {
            "last": {"inputTokens": input_tokens + cache_create + cache_read, "outputTokens": output_tokens, "totalTokens": total},
            "total": {"inputTokens": input_tokens + cache_create + cache_read, "outputTokens": output_tokens, "totalTokens": total},
        }


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _ClaudeStreamState:
    def __init__(self, session_id: str = "") -> None:
        self.session_id = session_id
        self.reply = ""
        self.final_result = ""
        self.status = "Starting Claude Code."
        self.model = ""
        self.usage: dict[str, Any] = {}
        self.tools: list[dict[str, Any]] = []
        self.is_error = False
        self.error = ""

    def add_text(self, text: str) -> None:
        if text:
            self.reply += text

    def snapshot(self, conversation_id: str = "", token_usage: dict[str, Any] | None = None) -> dict[str, Any]:
        status = "error" if self.is_error else "completed" if self.final_result else "running"
        return {
            "status": status,
            "reply": self.final_result or self.reply,
            "conversationId": conversation_id,
            "sessionId": self.session_id,
            "runId": self.session_id,
            "providerPath": "claude-code-cli",
            "tools": [dict(tool) for tool in self.tools],
            "thinking": self.status,
            "tokenUsage": token_usage if isinstance(token_usage, dict) else {},
            "usage": dict(self.usage),
            "model": self.model,
            "error": self.error,
            "modifiedFiles": [],
        }

    def ingest(self, item: dict[str, Any]) -> None:
        item_type = item.get("type")
        if item.get("session_id"):
            self.session_id = str(item.get("session_id") or self.session_id)
        if item_type == "system":
            if item.get("subtype") == "init":
                self.model = str(item.get("model") or self.model)
                self.status = "Claude Code initialized."
        elif item_type == "assistant":
            self._ingest_message(item.get("message"))
        elif item_type == "stream_event":
            self._ingest_stream_event(item.get("event") if isinstance(item.get("event"), dict) else {})
        elif item_type == "result":
            self.final_result = str(item.get("result") or self.final_result or self.reply)
            self.is_error = bool(item.get("is_error") or item.get("subtype") == "error")
            self.error = str(item.get("error") or item.get("message") or "") or self.error
            if isinstance(item.get("usage"), dict):
                self.usage = item["usage"]
            for tool in self.tools:
                if tool.get("status") == "running":
                    tool["status"] = "error" if self.is_error else "done"
            self.status = "Claude Code completed."
        elif item_type == "error":
            self.is_error = True
            self.error = str(item.get("error") or item.get("message") or "Claude Code error")

    def _ingest_message(self, message: Any) -> None:
        if not isinstance(message, dict):
            return
        if isinstance(message.get("usage"), dict):
            self.usage = message["usage"]
        content = message.get("content")
        if not isinstance(content, list):
            return
        text_parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                text_parts.append(str(block.get("text") or ""))
            elif btype == "tool_use":
                self._upsert_tool(block)
            elif btype == "tool_result":
                self._ingest_tool_result(block)
        if text_parts:
            self.reply += "\n".join(text_parts)

    def _ingest_stream_event(self, event: dict[str, Any]) -> None:
        etype = str(event.get("type") or "")
        if etype == "content_block_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            if delta.get("type") == "text_delta":
                self.reply += str(delta.get("text") or "")
            elif delta.get("type") in {"input_json_delta", "input_delta"}:
                self._ingest_tool_argument_delta(event.get("index"), str(delta.get("partial_json") or delta.get("text") or ""))
        elif etype:
            self.status = etype.replace("_", " ")

    def _upsert_tool(self, block: dict[str, Any]) -> dict[str, Any]:
        tool_id = str(block.get("id") or f"claude-tool-{len(self.tools) + 1}")
        found = next((tool for tool in self.tools if tool.get("id") == tool_id), None)
        if not found:
            found = {
                "id": tool_id,
                "name": block.get("name") or "Claude tool",
                "status": "running",
                "arguments": block.get("input") if isinstance(block.get("input"), dict) else {},
                "result": "",
                "source": "claude-code",
            }
            self.tools.append(found)
        return found

    def _ingest_tool_result(self, block: dict[str, Any]) -> None:
        tool_id = str(block.get("tool_use_id") or block.get("id") or "")
        found = next((tool for tool in self.tools if tool.get("id") == tool_id), None)
        if not found:
            found = {"id": tool_id or f"claude-tool-result-{len(self.tools) + 1}", "name": "Claude tool", "status": "running", "arguments": {}, "result": "", "source": "claude-code"}
            self.tools.append(found)
        is_error = bool(block.get("is_error") or block.get("error"))
        found["status"] = "error" if is_error else "done"
        result = block.get("content")
        if isinstance(result, list):
            result = "\n".join(str(item.get("text") or item.get("content") or item) for item in result if item)
        if is_error:
            found["error"] = str(result or block.get("error") or "Claude tool failed")
        else:
            found["result"] = str(result or "")

    def _ingest_tool_argument_delta(self, index: Any, delta: str) -> None:
        if not delta:
            return
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = len(self.tools) - 1
        if idx < 0 or idx >= len(self.tools):
            return
        tool = self.tools[idx]
        raw = str(tool.get("_arguments_json") or "") + delta
        tool["_arguments_json"] = raw
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            tool["arguments"] = {"partial_json": raw}
            return
        if isinstance(parsed, dict):
            tool["arguments"] = parsed
