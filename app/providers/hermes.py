"""Hermes provider adapter for My Virtual Office.

This module is intentionally isolated from the OpenClaw discovery/runtime paths.
It talks to Hermes through public CLI surfaces only, so the product can add
Hermes support without hardcoding one user's setup or reading private Hermes
internals such as .env, auth.json, memories, raw logs, or state.db contents.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import selectors
import errno
import subprocess
import threading
import time
import json
import asyncio
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urljoin
from typing import Any


@dataclass
class HermesProvider:
    """Provider adapter for local Hermes Agent profiles."""

    home_path: str | None = None
    binary: str | None = None
    enabled: bool = True
    timeout_sec: int = 600

    provider_kind: str = "hermes"
    provider_type: str = "runtime"

    def __post_init__(self) -> None:
        self.binary = os.path.expanduser(
            self.binary
            or os.environ.get("VO_HERMES_BIN")
            or shutil.which("hermes")
            or "~/.local/bin/hermes"
        )
        self.home_path = os.path.expanduser(
            self.home_path
            or os.environ.get("VO_HERMES_HOME")
            or "~/.hermes"
        )

    def is_available(self) -> bool:
        return bool(self.enabled and self.binary and os.path.exists(self.binary) and self.home_path and os.path.isdir(self.home_path))

    def _subprocess_env(self) -> dict[str, str]:
        """Environment for Hermes CLI calls.

        Containers commonly run as root, where `~` would resolve to /root and
        Hermes would accidentally inspect/create /root/.hermes. When the user
        configured a Hermes home path, derive HOME from it so Hermes resolves
        its own profile paths consistently with the configured installation.
        """
        env = os.environ.copy()
        if self.home_path:
            env["VO_HERMES_HOME"] = self.home_path
            if os.path.basename(self.home_path.rstrip(os.sep)) == ".hermes":
                env["HOME"] = os.path.dirname(self.home_path.rstrip(os.sep)) or env.get("HOME", "")
        return env

    def discover_agents(self) -> list[dict[str, Any]]:
        """Return Hermes profiles as normalized OfficeAgent-like dictionaries."""
        if not self.is_available():
            return []

        profiles = self._list_profiles() or [{"profile": "default", "model": "", "gateway": ""}]
        agents: list[dict[str, Any]] = []
        for item in profiles:
            profile = item.get("profile") or "default"
            details = self._show_profile(profile)
            model = details.get("model") or item.get("model") or ""
            provider = details.get("provider") or ""
            gateway = details.get("gateway") or item.get("gateway") or ""
            profile_home = details.get("path") or (
                self.home_path if profile == "default" else os.path.join(self.home_path or "", "profiles", profile)
            )
            scan_home = profile_home if os.path.isdir(profile_home) else (self.home_path or "")
            identity = self._read_identity(profile_home)
            suffix = self._safe_suffix(profile)
            agents.append({
                "id": f"hermes-{suffix}",
                "statusKey": f"hermes-{suffix}",
                "providerKind": self.provider_kind,
                "providerType": self.provider_type,
                "providerAgentId": profile,
                "profile": profile,
                "name": identity.get("name") or self._display_name(profile),
                "emoji": identity.get("emoji") or os.environ.get("VO_HERMES_AGENT_EMOJI", "⚕️"),
                "role": identity.get("role") or "Hermes Agent",
                "model": model,
                "provider": provider,
                "gateway": gateway,
                "workspace": profile_home,
                "home": profile_home,
                "binary": self.binary,
                "lastActiveAt": self._last_active(scan_home),
                "capabilities": ["chat", "status", "sessions"],
            })
        return agents

    def test(self) -> dict[str, Any]:
        """Check whether Hermes is reachable and return discovered profiles."""
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}", "agents": []}
        if not self.home_path or not os.path.isdir(self.home_path):
            return {"ok": False, "error": f"Hermes home not found at {self.home_path}", "agents": []}
        try:
            return {"ok": True, "binary": self.binary, "homePath": self.home_path, "agents": self.discover_agents()}
        except Exception as exc:  # defensive: test endpoint should not crash server
            return {"ok": False, "error": str(exc), "agents": []}

    def send_message(self, profile: str, message: str, timeout_sec: int | None = None) -> dict[str, Any]:
        """Send a one-shot message to Hermes and return stdout as the reply."""
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}", "exitCode": None, "reply": ""}
        if not message.strip():
            return {"ok": False, "error": "message is required", "exitCode": None, "reply": ""}

        cmd = [self.binary]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])
        cmd.extend(["-z", message])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(timeout_sec or self.timeout_sec) + 30,
                env=self._subprocess_env(),
            )
            reply = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.returncode != 0 and not reply:
                reply = f"[Hermes error] {stderr[:1000]}"
            return {
                "ok": result.returncode == 0,
                "reply": reply,
                "stderr": stderr[:2000],
                "exitCode": result.returncode,
                "profile": profile or "default",
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Hermes call timed out", "exitCode": None, "reply": ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "exitCode": None, "reply": ""}

    def send_chat_message(self, profile: str, message: str, session_id: str | None = None, timeout_sec: int | None = None, yolo_once: bool = False) -> dict[str, Any]:
        """Send a message through Hermes chat, optionally resuming a session.

        Unlike ``send_message``/``hermes -z``, this uses the public
        ``hermes chat -Q -q`` surface so Virtual Office can keep real Hermes
        session continuity by storing the returned ``session_id`` and passing it
        back with ``--resume`` on later turns.
        """
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}", "exitCode": None, "reply": "", "sessionId": session_id or ""}
        if not message.strip():
            return {"ok": False, "error": "message is required", "exitCode": None, "reply": "", "sessionId": session_id or ""}

        cmd = [self.binary]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])
        cmd.extend(["chat", "-Q"])
        if session_id:
            cmd.extend(["--resume", session_id])
        if yolo_once:
            cmd.append("--yolo")
        cmd.extend(["-q", message])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(timeout_sec or self.timeout_sec) + 30,
                env=self._subprocess_env(),
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            found_session_id = session_id or ""
            reply_lines: list[str] = []
            for line in stdout.splitlines():
                m = re.match(r"^\s*session_id:\s*(\S+)\s*$", line)
                if m:
                    found_session_id = m.group(1).strip()
                else:
                    reply_lines.append(line)
            for line in stderr.splitlines():
                m = re.match(r"^\s*session_id:\s*(\S+)\s*$", line)
                if m:
                    found_session_id = m.group(1).strip()
            reply = "\n".join(reply_lines).strip()
            if result.returncode != 0 and not reply:
                reply = f"[Hermes error] {stderr[:1000]}"
            return {
                "ok": result.returncode == 0,
                "reply": reply,
                "stderr": stderr[:2000],
                "exitCode": result.returncode,
                "profile": profile or "default",
                "sessionId": found_session_id,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Hermes call timed out", "exitCode": None, "reply": "", "sessionId": session_id or ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "exitCode": None, "reply": "", "sessionId": session_id or ""}

    def list_sessions(self, profile: str, limit: int = 40, timeout_sec: int = 30) -> dict[str, Any]:
        """List recent Hermes sessions through the public sessions CLI."""
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}", "sessions": []}
        cmd = [self.binary]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])
        cmd.extend(["sessions", "list", "--limit", str(max(1, int(limit)))])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=int(timeout_sec), env=self._subprocess_env())
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Hermes sessions list timed out", "sessions": []}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "sessions": []}
        if result.returncode != 0:
            return {"ok": False, "error": (result.stderr or result.stdout or "Hermes sessions list failed").strip()[:1000], "sessions": []}
        sessions = []
        past_header = False
        for line in (result.stdout or "").splitlines():
            stripped = line.rstrip()
            if not stripped:
                continue
            if set(stripped.strip()) <= {"─", "-", "="}:
                past_header = True
                continue
            if not past_header:
                continue
            parts = stripped.split()
            if not parts or not re.match(r"^[A-Za-z0-9_.:-]+$", parts[-1]):
                continue
            columns = re.split(r"\s{2,}", stripped)
            sessions.append({"id": parts[-1], "title": columns[0].strip()[:200], "preview": (columns[1].strip() if len(columns) > 2 else "")[:300], "lastActive": (columns[-2].strip() if len(columns) >= 3 else "")[:60]})
        return {"ok": True, "sessions": sessions, "profile": profile or "default"}

    def export_session(self, profile: str, session_id: str, timeout_sec: int = 30) -> dict[str, Any]:
        """Export one Hermes session through the public CLI JSONL surface."""
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}", "session": None}
        if not session_id:
            return {"ok": False, "error": "session_id is required", "session": None}

        cmd = [self.binary]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])
        cmd.extend(["sessions", "export", "--session-id", session_id, "-"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(timeout_sec),
                env=self._subprocess_env(),
            )
            if result.returncode != 0:
                return {"ok": False, "error": (result.stderr or result.stdout or "Hermes session export failed").strip()[:2000], "session": None}
            sessions: list[dict[str, Any]] = []
            for raw in (result.stdout or "").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    sessions.append(item)
            session = next((s for s in sessions if str(s.get("id") or "") == str(session_id)), sessions[0] if sessions else None)
            return {"ok": bool(session), "session": session, "error": "" if session else "session not found in export"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Hermes session export timed out", "session": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "session": None}

    def create_agent(self, name: str, role: str = "Hermes Agent", model: str | None = None, emoji: str = "⚕️", profile: str | None = None) -> dict[str, Any]:
        """Create a Hermes profile that Virtual Office treats as an agent.

        Hermes' public abstraction for isolated agents is a profile. We create
        profiles through the CLI, then write only non-secret bootstrap files
        into the profile directory for display and behavior guidance.
        """
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}"}
        if not self.home_path or not os.path.isdir(self.home_path):
            return {"ok": False, "error": f"Hermes home not found at {self.home_path}"}

        safe_profile = self._safe_profile_name(profile or name)
        if safe_profile == "default":
            return {"ok": False, "error": "Cannot create or overwrite the default Hermes profile"}
        if any(a.get("profile") == safe_profile for a in self.discover_agents()):
            return {"ok": False, "error": f"Hermes profile '{safe_profile}' already exists"}

        description = (role or "Hermes Agent").strip()[:500]
        cmd = [
            self.binary,
            "profile",
            "create",
            safe_profile,
            "--clone",
            "--clone-from",
            "default",
            "--no-alias",
            "--description",
            description,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=self._subprocess_env())
        if result.returncode != 0:
            # Some Hermes installs may not support clone flags. Fall back to the
            # basic public create command instead of guessing internal files.
            fallback = subprocess.run(
                [self.binary, "profile", "create", safe_profile, "--no-alias", "--description", description],
                capture_output=True,
                text=True,
                timeout=60,
                env=self._subprocess_env(),
            )
            if fallback.returncode != 0:
                return {
                    "ok": False,
                    "error": (fallback.stderr or fallback.stdout or result.stderr or result.stdout or "Hermes profile create failed").strip()[:2000],
                    "exitCode": fallback.returncode,
                }

        if model and str(model).strip():
            # Best-effort: installed Hermes versions may use different model
            # config keys. Creation should still succeed even if this fails.
            subprocess.run(
                [self.binary, "--profile", safe_profile, "config", "set", "model.default", str(model).strip()],
                capture_output=True,
                text=True,
                timeout=30,
                env=self._subprocess_env(),
            )

        profile_home = os.path.join(self.home_path, "profiles", safe_profile)
        os.makedirs(profile_home, exist_ok=True)
        self._write_profile_bootstrap(profile_home, name=name, role=role, emoji=emoji, profile=safe_profile)
        self._chown_like_home(profile_home)

        return {
            "ok": True,
            "profile": safe_profile,
            "agentId": f"hermes-{safe_profile}",
            "name": name,
            "workspace": profile_home,
            "message": f"Hermes profile '{safe_profile}' created successfully",
        }

    def delete_agent(self, profile: str) -> dict[str, Any]:
        """Delete a Hermes profile through the public CLI."""
        safe_profile = self._safe_profile_name(profile)
        if safe_profile == "default":
            return {"ok": False, "error": "Cannot delete the default Hermes profile"}
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}"}

        result = subprocess.run(
            [self.binary, "profile", "delete", safe_profile, "--yes"],
            capture_output=True,
            text=True,
            timeout=60,
            env=self._subprocess_env(),
        )
        return {
            "ok": result.returncode == 0,
            "deleted": result.returncode == 0,
            "profile": safe_profile,
            "agentId": f"hermes-{safe_profile}",
            "stdout": (result.stdout or "").strip()[:1000],
            "stderr": (result.stderr or "").strip()[:1000],
            "error": "" if result.returncode == 0 else ((result.stderr or result.stdout or "Hermes profile delete failed").strip()[:1000]),
            "exitCode": result.returncode,
        }

    def delete_session(self, profile: str, session_id: str) -> dict[str, Any]:
        """Delete a Hermes session through the public sessions CLI."""
        if not session_id:
            return {"ok": True, "deleted": False}
        if not self.binary or not os.path.exists(self.binary):
            return {"ok": False, "error": f"Hermes CLI not found at {self.binary}"}
        cmd = [self.binary]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])
        cmd.extend(["sessions", "delete", session_id, "--yes"])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=self._subprocess_env())
            return {
                "ok": result.returncode == 0,
                "deleted": result.returncode == 0,
                "stdout": (result.stdout or "").strip()[:1000],
                "stderr": (result.stderr or "").strip()[:1000],
                "exitCode": result.returncode,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _list_profiles(self) -> list[dict[str, str]]:
        profiles: list[dict[str, str]] = []
        try:
            result = subprocess.run([self.binary or "hermes", "profile", "list"], capture_output=True, text=True, timeout=15, env=self._subprocess_env())
            if result.returncode != 0:
                return profiles
            for line in (result.stdout or "").splitlines():
                clean = line.strip()
                if not clean or clean.startswith("Profile") or clean.startswith("─"):
                    continue
                clean = clean.replace("◆", " ").strip()
                parts = clean.split()
                if not parts:
                    continue
                profile = parts[0].strip()
                if not profile or profile in {"—", "-"}:
                    continue
                profiles.append({
                    "profile": profile,
                    "model": parts[1].strip() if len(parts) > 1 else "",
                    "gateway": parts[2].strip() if len(parts) > 2 else "",
                })
        except Exception:
            pass
        return profiles

    def _show_profile(self, profile: str) -> dict[str, str]:
        details: dict[str, str] = {}
        try:
            cmd = [self.binary or "hermes"]
            if profile != "default":
                cmd.extend(["--profile", profile])
            cmd.extend(["profile", "show", profile])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=self._subprocess_env())
            text = (result.stdout or "") + "\n" + (result.stderr or "")
            for line in text.splitlines():
                clean = line.strip(" │\t")
                if clean.startswith("Path:"):
                    details["path"] = clean.split(":", 1)[1].strip()
                elif clean.startswith("Model:"):
                    value = clean.split(":", 1)[1].strip()
                    m = re.match(r"(.+?)\s*\((.+?)\)\s*$", value)
                    if m:
                        details["model"] = m.group(1).strip()
                        details["provider"] = m.group(2).strip()
                    else:
                        details["model"] = value
                elif clean.startswith("Gateway:"):
                    details["gateway"] = clean.split(":", 1)[1].strip()
        except Exception:
            pass
        return details

    @staticmethod
    def _safe_suffix(profile: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", profile or "default").strip("-.")
        return safe or "default"

    @staticmethod
    def _safe_profile_name(value: str) -> str:
        safe = re.sub(r"[^a-z0-9_-]+", "-", (value or "").lower().strip()).strip("-_")
        safe = re.sub(r"[-_]{2,}", "-", safe)
        return (safe or f"agent-{int(time.time())}")[:63]

    def _write_profile_bootstrap(self, profile_home: str, *, name: str, role: str, emoji: str, profile: str) -> None:
        files = {
            "IDENTITY.md": f"""# IDENTITY.md

- **Name:** {name}
- **Creature:** {role} — Hermes profile
- **Vibe:** Helpful, direct, ready to work
- **Emoji:** {emoji}
""",
            "SOUL.md": f"""# SOUL.md — {name}

You are **{name}** {emoji} — {role}.

## Style
- Be helpful and direct
- Keep work visible through Virtual Office when possible
- Use your Hermes profile `{profile}` for isolated context
""",
            "AGENTS.md": f"""# {name} {emoji} — {role}

## Role
{role}

## Core Rules
- Follow instructions carefully
- Keep replies concise and useful
- Do not expose secrets from your Hermes profile

## Memory
- Use Hermes profile memory and sessions normally.
""",
            "MEMORY.md": f"# MEMORY.md - {name}\n\n_No memories yet._\n",
            "TOOLS.md": f"# TOOLS.md — {name}\n\n_Add tool-specific notes here._\n",
        }
        for filename, content in files.items():
            with open(os.path.join(profile_home, filename), "w", encoding="utf-8") as f:
                f.write(content)

    def _chown_like_home(self, path: str) -> None:
        try:
            st = os.stat(self.home_path or path)
            for root, dirs, files in os.walk(path):
                os.chown(root, st.st_uid, st.st_gid)
                for name in dirs + files:
                    try:
                        os.chown(os.path.join(root, name), st.st_uid, st.st_gid)
                    except OSError:
                        pass
        except OSError:
            pass

    def _display_name(self, profile: str) -> str:
        env_key = f"VO_HERMES_PROFILE_NAME_{self._safe_suffix(profile).upper().replace('-', '_')}"
        override = os.environ.get(env_key)
        if override:
            return override
        if profile == "default":
            return "Hermes"
        return profile.replace("-", " ").replace("_", " ").title()

    @staticmethod
    def _read_identity(profile_home: str) -> dict[str, str]:
        identity: dict[str, str] = {}
        try:
            with open(os.path.join(profile_home, "IDENTITY.md"), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    m = re.match(r'-\s*\*\*Name:\*\*\s*(.+)', line)
                    if m:
                        identity["name"] = m.group(1).strip()
                    m = re.match(r'-\s*\*\*Emoji:\*\*\s*(.+)', line)
                    if m:
                        identity["emoji"] = m.group(1).strip()
                    m = re.match(r'-\s*\*\*Creature:\*\*\s*(.+)', line)
                    if m:
                        identity["role"] = m.group(1).split("—")[0].strip().rstrip(" -")
        except (OSError, UnicodeError):
            pass
        return identity

    @staticmethod
    def _last_active(home_path: str) -> int:
        latest = 0
        for rel in ("state.db", os.path.join("logs", "agent.log"), os.path.join("logs", "errors.log")):
            path = os.path.join(home_path, rel)
            try:
                if os.path.exists(path):
                    latest = max(latest, int(os.path.getmtime(path)))
            except OSError:
                pass
        return latest


@dataclass
class HermesApiClient:
    """Small client for Hermes Agent's native API Server run/event surface."""

    base_url: str | None = None
    api_key: str | None = None
    timeout_sec: int = 30

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or os.environ.get("VO_HERMES_API_URL") or "http://127.0.0.1:8642").rstrip("/")
        self.api_key = self.api_key if self.api_key is not None else os.environ.get("VO_HERMES_API_KEY", "")

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update({k: v for k, v in extra.items() if v is not None})
        return headers

    def _json_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        data = None
        req_headers = self._headers(headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._url(path), data=data, headers=req_headers, method=method.upper())
        with urllib.request.urlopen(req, timeout=int(timeout_sec or self.timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            if isinstance(parsed, dict):
                parsed["_status"] = getattr(resp, "status", 200)
                return parsed
            return {"data": parsed, "_status": getattr(resp, "status", 200)}

    def capabilities(self) -> dict[str, Any]:
        return self._json_request("GET", "/v1/capabilities")

    def health(self) -> dict[str, Any]:
        return self._json_request("GET", "/health", timeout_sec=min(self.timeout_sec, 5))

    def models(self) -> dict[str, Any]:
        return self._json_request("GET", "/v1/models")

    def is_available(self) -> bool:
        try:
            health = self.health()
            if health.get("status") not in {"ok", "healthy"}:
                return False
            caps = self.capabilities()
            features = caps.get("features") if isinstance(caps.get("features"), dict) else {}
            return bool(features.get("run_submission") and features.get("run_events_sse"))
        except Exception:
            return False

    def start_run(
        self,
        message: str,
        *,
        session_id: str | None = None,
        session_key: str | None = None,
        instructions: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"input": message}
        if session_id:
            body["session_id"] = session_id
        if instructions:
            body["instructions"] = instructions
        if conversation_history:
            body["conversation_history"] = conversation_history
        headers = {"X-Hermes-Session-Key": session_key} if session_key and self.api_key else None
        return self._json_request("POST", "/v1/runs", body, headers=headers)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._json_request("GET", f"/v1/runs/{run_id}")

    def get_session_messages(self, session_id: str) -> dict[str, Any]:
        """Fetch a persisted Hermes session transcript through the public API."""
        session_id = str(session_id or "").strip()
        if not session_id:
            return {"ok": False, "error": "session_id is required", "data": []}
        try:
            result = self._json_request("GET", f"/api/sessions/{quote(session_id, safe='')}/messages")
            result["ok"] = True
            return result
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "ok": False,
                "status": exc.code,
                "notFound": exc.code == 404,
                "error": body[:1000] or str(exc),
                "data": [],
            }

    def respond_approval(self, run_id: str, choice: str) -> dict[str, Any]:
        return self._json_request("POST", f"/v1/runs/{run_id}/approval", {"choice": choice})

    def stop_run(self, run_id: str) -> dict[str, Any]:
        return self._json_request("POST", f"/v1/runs/{run_id}/stop", {})

    def stream_run_events(self, run_id: str, timeout_sec: int | None = None):
        """Yield dict events from Hermes' SSE run stream."""
        req = urllib.request.Request(
            self._url(f"/v1/runs/{run_id}/events"),
            headers=self._headers({"Accept": "text/event-stream"}),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=int(timeout_sec or self.timeout_sec)) as resp:
            data_lines: list[str] = []
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if data_lines:
                        payload = "\n".join(data_lines)
                        data_lines = []
                        try:
                            item = json.loads(payload)
                            if isinstance(item, dict):
                                yield item
                        except json.JSONDecodeError:
                            continue
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
@dataclass
class HermesDesktopBackendClient:
    """Client for Hermes Desktop's `hermes serve` TUI-gateway backend."""

    base_url: str | None = None
    token: str | None = None
    host_header: str | None = None
    tcp_host: str | None = None
    tcp_port: int | str | None = None
    timeout_sec: int = 10

    def __post_init__(self) -> None:
        self.base_url = (
            self.base_url
            or os.environ.get("VO_HERMES_DESKTOP_URL")
            or ""
        ).rstrip("/")
        self.token = self.token if self.token is not None else os.environ.get("VO_HERMES_DESKTOP_TOKEN", "")
        self.host_header = self.host_header if self.host_header is not None else os.environ.get("VO_HERMES_DESKTOP_HOST_HEADER", "")
        self.tcp_host = self.tcp_host if self.tcp_host is not None else os.environ.get("VO_HERMES_DESKTOP_TCP_HOST", "")
        self.tcp_port = self.tcp_port if self.tcp_port is not None else os.environ.get("VO_HERMES_DESKTOP_TCP_PORT", "")
        try:
            self.tcp_port = int(self.tcp_port) if str(self.tcp_port or "").strip() else None
        except Exception:
            self.tcp_port = None

        parsed = self._parsed_base_url()
        if parsed and self.host_header and not self.tcp_host and self.host_header != parsed.netloc:
            self.tcp_host = parsed.hostname or ""
        if parsed and self._is_loopback_host(parsed.hostname) and self._running_in_docker() and not self.tcp_host:
            self.tcp_host = os.environ.get("VO_HERMES_DESKTOP_DOCKER_HOST", "host.docker.internal")
        if parsed and self.tcp_host and not self.tcp_port:
            self.tcp_port = parsed.port
        if parsed and self._uses_tcp_override() and not self.host_header:
            self.host_header = parsed.netloc

    def _url(self, path: str) -> str:
        return self._logical_url(path)

    @staticmethod
    def _running_in_docker() -> bool:
        if os.path.exists("/.dockerenv"):
            return True
        try:
            with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as f:
                return any(token in f.read() for token in ("docker", "containerd", "kubepods"))
        except Exception:
            return False

    @staticmethod
    def _is_loopback_host(hostname: str | None) -> bool:
        host = (hostname or "").strip().lower().strip("[]")
        return host in {"127.0.0.1", "localhost", "::1"}

    def _parsed_base_url(self):
        if not self.base_url:
            return None
        return urllib.parse.urlparse(self.base_url)

    def _logical_netloc(self) -> str:
        parsed = self._parsed_base_url()
        if not parsed:
            return ""
        return (self.host_header or parsed.netloc or "").strip()

    def _uses_tcp_override(self) -> bool:
        return bool(str(self.tcp_host or "").strip())

    def _resolve_tcp_host_ipv4(self, host: str, port: int | None) -> str:
        if not host:
            return host
        try:
            socket.inet_aton(host)
            return host
        except OSError:
            pass
        try:
            infos = socket.getaddrinfo(host, int(port or 0), family=socket.AF_INET, type=socket.SOCK_STREAM)
            if infos:
                return infos[0][4][0]
        except Exception:
            pass
        return host

    def _logical_url(self, path: str) -> str:
        if not self.base_url:
            return ""
        parsed = urllib.parse.urlparse(self.base_url.rstrip("/") + "/" + path.lstrip("/"))
        logical_netloc = self._logical_netloc()
        if logical_netloc:
            parsed = parsed._replace(netloc=logical_netloc)
        return urllib.parse.urlunparse(parsed)

    def _connect_netloc(self) -> str:
        parsed = self._parsed_base_url()
        if not parsed:
            return ""
        port = int(self.tcp_port or parsed.port or (443 if parsed.scheme == "https" else 80))
        host = self._resolve_tcp_host_ipv4(str(self.tcp_host or parsed.hostname or ""), port)
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{host}:{port}"

    def _connect_url(self, path: str) -> str:
        if not self.base_url:
            return ""
        parsed = urllib.parse.urlparse(self.base_url.rstrip("/") + "/" + path.lstrip("/"))
        if self._uses_tcp_override():
            parsed = parsed._replace(netloc=self._connect_netloc())
        return urllib.parse.urlunparse(parsed)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.host_header:
            headers["Host"] = self.host_header
        if self.token:
            headers["X-Hermes-Session-Token"] = self.token
        if extra:
            headers.update({k: v for k, v in extra.items() if v is not None})
        return headers

    def _json_request(self, method: str, path: str, timeout_sec: int | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise ValueError("Hermes Desktop Backend URL is not configured")
        req = urllib.request.Request(self._connect_url(path), headers=self._headers(), method=method.upper())
        with urllib.request.urlopen(req, timeout=int(timeout_sec or self.timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            if isinstance(parsed, dict):
                parsed["_status"] = getattr(resp, "status", 200)
                return parsed
            return {"data": parsed, "_status": getattr(resp, "status", 200)}

    def status(self) -> dict[str, Any]:
        return self._json_request("GET", "/api/status", timeout_sec=min(self.timeout_sec, 5))

    def _dashboard_index_html(self) -> str:
        if not self.base_url:
            return ""
        req = urllib.request.Request(self._connect_url("/"), headers={"Accept": "text/html", **({"Host": self.host_header} if self.host_header else {})}, method="GET")
        with urllib.request.urlopen(req, timeout=min(int(self.timeout_sec), 5)) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _served_dashboard_token(self) -> str:
        if self.token:
            return self.token
        try:
            html = self._dashboard_index_html()
        except Exception:
            return ""
        match = re.search(r"window\.__HERMES_SESSION_TOKEN__\s*=\s*(\"(?:\\.|[^\"\\])*\")", html)
        if not match:
            return ""
        try:
            token = json.loads(match.group(1))
            return token if isinstance(token, str) else ""
        except Exception:
            return ""

    def _ws_url(self) -> str:
        if not self.base_url:
            return ""
        parsed = urllib.parse.urlparse(self._url("/api/ws"))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        query = parsed.query
        token = self._served_dashboard_token()
        if token and "token=" not in query:
            token_q = urllib.parse.urlencode({"token": token})
            query = f"{query}&{token_q}" if query else token_q
        return urllib.parse.urlunparse(parsed._replace(scheme=scheme, query=query))

    def _connect_ws(self):
        ws_url = self._ws_url()
        if not ws_url:
            raise ValueError("Hermes Desktop Backend URL is not configured")
        try:
            from websockets.asyncio.client import connect as ws_connect
        except Exception:
            from websockets import connect as ws_connect  # type: ignore
        headers = {}
        if self.host_header and not self._uses_tcp_override():
            headers["Host"] = self.host_header
        timeout = min(int(self.timeout_sec), 30)
        kwargs = {"open_timeout": timeout, "close_timeout": 1}
        parsed = urllib.parse.urlparse(ws_url)
        if self._uses_tcp_override():
            port = int(self.tcp_port or parsed.port or (443 if parsed.scheme == "wss" else 80))
            kwargs["host"] = self._resolve_tcp_host_ipv4(str(self.tcp_host or ""), port)
            kwargs["port"] = port
        try:
            return ws_connect(ws_url, additional_headers=headers or None, **kwargs)
        except TypeError:
            return ws_connect(ws_url, extra_headers=headers or None, **kwargs)

    async def _recv_json(self, ws, timeout_sec: float) -> dict[str, Any]:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(timeout_sec, 0.1))
        data = json.loads(str(raw).strip())
        return data if isinstance(data, dict) else {"data": data}

    async def _rpc(self, ws, method: str, params: dict[str, Any] | None = None, timeout_sec: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rid = f"vo-{int(time.time() * 1000)}-{os.getpid()}"
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}))
        deadline = time.monotonic() + int(timeout_sec or self.timeout_sec)
        events: list[dict[str, Any]] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Hermes Desktop Backend RPC timed out: {method}")
            item = await self._recv_json(ws, remaining)
            if item.get("id") == rid:
                if item.get("error"):
                    err = item.get("error") if isinstance(item.get("error"), dict) else {"message": str(item.get("error"))}
                    raise RuntimeError(err.get("message") or f"Hermes Desktop Backend RPC failed: {method}")
                result = item.get("result")
                return (result if isinstance(result, dict) else {"value": result}, events)
            if item.get("method") == "event":
                params_obj = item.get("params") if isinstance(item.get("params"), dict) else {}
                events.append(params_obj)

    def _run_async(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result: dict[str, Any] = {}
        error: list[BaseException] = []

        def worker() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:
                error.append(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result.get("value")

    def rpc_call(self, method: str, params: dict[str, Any] | None = None, timeout_sec: int | None = None) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            async with self._connect_ws() as ws:
                result, events = await self._rpc(ws, method, params, timeout_sec=timeout_sec)
                return {"ok": True, "result": result, "events": events, "websocketUrl": self._ws_url()}

        return self._run_async(run())

    @staticmethod
    def _payload_text(payload: dict[str, Any]) -> str:
        for key in ("text", "delta", "content", "output", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        value = payload.get("chunk")
        if isinstance(value, dict):
            for key in ("text", "delta", "content"):
                if isinstance(value.get(key), str):
                    return value.get(key) or ""
        return ""

    @staticmethod
    def _coerce_reasoning_text(text: str) -> str:
        raw = str(text or "")
        cleaned = re.sub(
            r"^\s*(?:(?:[^\s.]{1,16})\s+)?(?:processing|thinking|reasoning|analyzing|pondering|contemplating|musing|cogitating|ruminating|deliberating|mulling|reflecting|computing|synthesizing|formulating|brainstorming)\.\.\.\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        )
        if re.search(r"\b(?:current rewritten thinking|next thinking to process|provide the thinking content|don't see any .*thinking)\b", cleaned, flags=re.IGNORECASE):
            return ""
        return cleaned

    @staticmethod
    def _payload_tool_card(payload: dict[str, Any], status: str, fallback_id: str) -> dict[str, Any]:
        nested = payload.get("tool") if isinstance(payload.get("tool"), dict) else {}
        function = payload.get("function") if isinstance(payload.get("function"), dict) else {}
        tool_id = str(
            payload.get("tool_id")
            or payload.get("toolCallId")
            or payload.get("tool_call_id")
            or payload.get("call_id")
            or payload.get("id")
            or nested.get("id")
            or fallback_id
        )
        name = str(
            payload.get("name")
            or payload.get("tool_name")
            or payload.get("toolName")
            or nested.get("name")
            or function.get("name")
            or "Hermes tool"
        )
        args = (
            payload.get("arguments")
            or payload.get("args")
            or payload.get("input")
            or payload.get("parameters")
            or nested.get("arguments")
            or nested.get("args")
            or function.get("arguments")
            or {}
        )
        if not isinstance(args, dict):
            args = {"input": args}
        if not args and payload.get("args_text"):
            args = {"input": payload.get("args_text")}
        preview = payload.get("context") or payload.get("preview") or payload.get("command") or ""
        if preview and not any(args.get(k) for k in ("command", "description", "input")):
            args["command"] = str(preview)
        result = (
            payload.get("result")
            or payload.get("summary")
            or payload.get("output")
            or payload.get("content")
            or nested.get("result")
            or nested.get("output")
            or ""
        )
        error = payload.get("error") or nested.get("error") or ""
        return {
            "id": tool_id,
            "name": name,
            "status": "error" if error else status,
            "arguments": args,
            "args_preview": str(preview or ""),
            "result": error or result or ("Running" if status == "running" else "Completed"),
            "error": str(error or ""),
        }

    def send_chat_message(
        self,
        message: str,
        session_id: str | None = None,
        timeout_sec: int | None = None,
        on_event=None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        def emit_event(event_name: str, payload: dict[str, Any]) -> None:
            if not on_event:
                return
            try:
                on_event(event_name, payload)
            except Exception:
                pass

        async def run() -> dict[str, Any]:
            async with self._connect_ws() as ws:
                stored_session_id = str(session_id or "").strip()
                live_session_id = ""
                if stored_session_id:
                    try:
                        resumed, _ = await self._rpc(ws, "session.resume", {"session_id": stored_session_id, "source": "virtual-office"}, timeout_sec=min(int(timeout_sec or self.timeout_sec), 30))
                        live_session_id = str(resumed.get("session_id") or "")
                        stored_session_id = str(resumed.get("session_key") or resumed.get("resumed") or stored_session_id)
                    except Exception:
                        live_session_id = ""
                if not live_session_id:
                    created, _ = await self._rpc(ws, "session.create", {"source": "virtual-office"}, timeout_sec=min(int(timeout_sec or self.timeout_sec), 30))
                    live_session_id = str(created.get("session_id") or "")
                    stored_session_id = str(created.get("stored_session_id") or created.get("session_key") or live_session_id)
                if not live_session_id:
                    raise RuntimeError("Hermes Desktop Backend did not return a live session id")

                _, submit_events = await self._rpc(ws, "prompt.submit", {"session_id": live_session_id, "text": message}, timeout_sec=min(int(timeout_sec or self.timeout_sec), 30))

                reply_parts: list[str] = []
                reasoning_parts: list[str] = []
                tools: list[dict[str, Any]] = []
                tools_by_id: dict[str, dict[str, Any]] = {}
                terminal_error = ""
                tool_seq = 0
                pending_events = list(submit_events or [])
                deadline = time.monotonic() + int(timeout_sec or self.timeout_sec)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Hermes Desktop Backend chat timed out")
                    if pending_events:
                        params_obj = pending_events.pop(0)
                        if not isinstance(params_obj, dict):
                            continue
                    else:
                        item = await self._recv_json(ws, remaining)
                        if item.get("method") != "event":
                            continue
                        params_obj = item.get("params") if isinstance(item.get("params"), dict) else {}
                    payload = params_obj.get("payload") if isinstance(params_obj.get("payload"), dict) else {}
                    event_type = str(params_obj.get("type") or params_obj.get("event") or payload.get("type") or payload.get("event") or "").lower()
                    if not payload:
                        payload = {k: v for k, v in params_obj.items() if k not in {"type", "event", "session_id"}}
                    event_session = str(params_obj.get("session_id") or payload.get("session_id") or "")
                    if event_session and event_session != live_session_id:
                        continue
                    if event_type in {"message.delta", "message_delta", "assistant.delta", "assistant_delta", "output.delta"}:
                        text = self._payload_text(payload)
                        if event_type == "message.delta":
                            reply_parts.append(text)
                        else:
                            reply_parts.append(text)
                        if text:
                            emit_event("message.delta", {
                                "delta": text,
                                "reply": "".join(reply_parts),
                                "sessionId": stored_session_id,
                                "liveSessionId": live_session_id,
                                "runId": run_id or "",
                            })
                    elif event_type in {"thinking.delta", "thinking_delta", "reasoning.delta", "reasoning_delta", "thought.delta", "thought_delta", "analysis.delta", "analysis_delta", "reasoning.available"}:
                        text = self._coerce_reasoning_text(self._payload_text(payload))
                        if text and text.strip() != "".join(reply_parts).strip():
                            reasoning_parts.append(text)
                            emit_event("reasoning.available", {
                                    "text": text,
                                    "thinking": "\n".join(reasoning_parts).strip(),
                                    "sessionId": stored_session_id,
                                    "liveSessionId": live_session_id,
                                    "runId": run_id or "",
                                })
                    elif event_type in {"tool.start", "tool.started", "tool.progress", "tool.generating", "tool.update", "tool.updated", "tool_start", "tool_progress", "tool_generating", "tool_update", "tool.call.start", "tool_call.start", "tool_call.started", "tool_call.progress", "tool_call.generating", "tool_call.update"}:
                        tool_seq += 1
                        card = self._payload_tool_card(payload, "running", f"desktop-tool-{tool_seq}")
                        tool_id = card["id"]
                        tools_by_id[tool_id] = card
                        tools.append(card)
                        emit_event("tool.started", {
                                "toolCard": card,
                                "tool": card.get("name") or "Hermes tool",
                                "preview": card.get("args_preview") or "",
                                "sessionId": stored_session_id,
                                "liveSessionId": live_session_id,
                                "runId": run_id or "",
                            })
                    elif event_type in {"tool.complete", "tool.completed", "tool.end", "tool.ended", "tool.result", "tool.failed", "tool.error", "tool_complete", "tool_result", "tool_call.complete", "tool_call.completed", "tool_call.result", "tool_call.failed"}:
                        tool_id = str(payload.get("tool_id") or payload.get("toolCallId") or payload.get("tool_call_id") or payload.get("call_id") or payload.get("id") or "")
                        card = tools_by_id.get(tool_id) if tool_id else None
                        if not card:
                            card = self._payload_tool_card(payload, "done", tool_id or f"desktop-tool-{len(tools) + 1}")
                            tools.append(card)
                        update = self._payload_tool_card(payload, "error" if "fail" in event_type or "error" in event_type else "done", card.get("id") or "")
                        card.update({k: v for k, v in update.items() if v not in ("", {}, None)})
                        emit_event("tool.failed" if card.get("status") == "error" else "tool.completed", {
                                "toolCard": card,
                                "tool": card.get("name") or "Hermes tool",
                                "preview": card.get("args_preview") or "",
                                "error": card.get("error") or "",
                                "sessionId": stored_session_id,
                                "liveSessionId": live_session_id,
                                "runId": run_id or "",
                            })
                    elif event_type in {"approval.request", "clarify.request", "sudo.request", "secret.request"}:
                        terminal_error = "Hermes Desktop Backend is waiting for interactive input that Virtual Office cannot answer yet."
                        break
                    elif event_type in {"error", "run.failed", "message.error"}:
                        terminal_error = str(payload.get("message") or payload.get("error") or "Hermes Desktop Backend error")
                        break
                    elif event_type in {"message.complete", "message.completed", "run.completed", "complete", "done"}:
                        text = self._payload_text(payload)
                        status = str(payload.get("status") or "complete")
                        final_reply = text or "".join(reply_parts)
                        return {
                            "ok": status not in {"error", "interrupted"} and not terminal_error,
                            "reply": final_reply,
                            "stderr": terminal_error,
                            "exitCode": 0 if status not in {"error", "interrupted"} and not terminal_error else 1,
                            "sessionId": stored_session_id,
                            "liveSessionId": live_session_id,
                            "providerPath": "desktop",
                            "tools": tools,
                            "thinking": "\n".join(reasoning_parts).strip(),
                            "reasoningTokens": 0,
                            "error": terminal_error or (status if status in {"error", "interrupted"} else None),
                        }
                return {
                    "ok": False,
                    "reply": "".join(reply_parts),
                    "stderr": terminal_error,
                    "exitCode": 1,
                    "sessionId": stored_session_id,
                    "liveSessionId": live_session_id,
                    "providerPath": "desktop",
                    "tools": tools,
                    "thinking": "\n".join(reasoning_parts).strip(),
                    "reasoningTokens": 0,
                    "error": terminal_error or "Hermes Desktop Backend chat ended without a final message.",
                }

        if not message.strip():
            return {"ok": False, "error": "message is required", "reply": "", "exitCode": None, "sessionId": session_id or ""}
        try:
            return self._run_async(run())
        except Exception as exc:
            return {"ok": False, "error": str(exc), "reply": "", "stderr": str(exc)[:2000], "exitCode": None, "sessionId": session_id or "", "providerPath": "desktop"}

    def test(self, verify_ws: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "url": self.base_url,
            "logicalUrl": self._logical_url("/") if self.base_url else "",
            "connectUrl": self._connect_url("/") if self.base_url else "",
            "tcpHost": self.tcp_host or "",
            "tcpPort": self.tcp_port or "",
            "hostHeader": self.host_header or "",
            "statusEndpoint": self._logical_url("/api/status") if self.base_url else "",
            "websocketUrl": "",
            "authRequired": False,
            "chatReady": False,
            "features": {"tuiGatewayJsonRpc": False},
        }
        if not self.base_url:
            result["error"] = "Hermes Desktop Backend URL is not configured"
            return result
        try:
            status = self.status()
            auth_required = bool(status.get("auth_required"))
            result.update({
                "ok": True,
                "status": status.get("status") or "ok",
                "version": status.get("version") or "",
                "activeSessions": status.get("active_sessions"),
                "authRequired": auth_required,
                "authProviders": status.get("auth_providers") or [],
                "hermesHome": status.get("hermes_home") or "",
                "websocketUrl": self._ws_url(),
            })
            if auth_required:
                result["error"] = "Hermes Desktop Backend is reachable but requires dashboard authentication."
                return result
            if verify_ws:
                rpc = self.rpc_call("session.active_list", {}, timeout_sec=min(int(self.timeout_sec), 5))
                result["websocketOk"] = bool(rpc.get("ok"))
                result["features"]["tuiGatewayJsonRpc"] = bool(rpc.get("ok"))
                result["chatReady"] = bool(rpc.get("ok"))
                if not rpc.get("ok"):
                    result["error"] = rpc.get("error") or "Hermes Desktop Backend WebSocket did not accept JSON-RPC."
            else:
                result["chatReady"] = True
                result["features"]["tuiGatewayJsonRpc"] = True
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            result["status"] = exc.code
            result["error"] = body[:500] or str(exc)
        except Exception as exc:
            result["error"] = str(exc)[:500]
        return result


def discover_api_agents(
    api_url: str | None = None,
    api_key: str | None = None,
    *,
    enabled: bool = True,
    timeout_sec: int = 5,
) -> list[dict[str, Any]]:
    """Return an API-backed Hermes agent when the Hermes API Server is reachable."""
    if not enabled:
        return []

    client = HermesApiClient(base_url=api_url, api_key=api_key, timeout_sec=timeout_sec)
    try:
        health = client.health()
        if health.get("status") not in {"ok", "healthy"}:
            return []
        caps = client.capabilities()
        features = caps.get("features") if isinstance(caps.get("features"), dict) else {}
        if not (features.get("run_submission") and features.get("run_events_sse")):
            return []
        model = caps.get("model") or caps.get("model_name") or ""
        try:
            models = client.models()
            data = models.get("data") if isinstance(models.get("data"), list) else []
            if not model and data:
                first = data[0] if isinstance(data[0], dict) else {}
                model = first.get("id") or first.get("name") or ""
        except Exception:
            pass
    except Exception:
        return []

    model = model or "hermes-agent"
    return [{
        "id": "hermes-default",
        "statusKey": "hermes-default",
        "providerKind": "hermes",
        "providerType": "runtime",
        "providerAgentId": "default",
        "profile": "default",
        "name": "Hermes API",
        "emoji": os.environ.get("VO_HERMES_AGENT_EMOJI", "⚕️"),
        "role": "Hermes Agent",
        "model": model,
        "provider": "Hermes API",
        "gateway": "api",
        "workspace": "",
        "home": "",
        "binary": "",
        "apiUrl": client.base_url,
        "lastActiveAt": int(time.time()),
        "capabilities": ["chat", "status", "sessions", "api"],
        "connectionModes": ["api"],
        "cliAvailable": False,
        "apiAvailable": True,
    }]


def _expand_candidate_path(path: str | None) -> str:
    return os.path.expandvars(os.path.expanduser(str(path or "").strip()))


def _default_desktop_log_paths(hermes_home: str | None = None, extra_paths: list[str] | None = None) -> list[str]:
    paths: list[str] = []
    for item in extra_paths or []:
        if item:
            paths.append(_expand_candidate_path(item))
    for env_name in ("VO_HERMES_DESKTOP_LOG_PATH", "HERMES_DESKTOP_LOG_PATH"):
        value = os.environ.get(env_name)
        if value:
            paths.append(_expand_candidate_path(value))
    if hermes_home:
        paths.append(os.path.join(_expand_candidate_path(hermes_home), "logs", "desktop.log"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        paths.append(os.path.join(_expand_candidate_path(local_app_data), "hermes", "logs", "desktop.log"))
    paths.append(os.path.expanduser("~/.hermes/logs/desktop.log"))

    seen = set()
    result = []
    for path in paths:
        norm = os.path.normpath(path) if path else ""
        key = norm.lower() if os.name == "nt" else norm
        if norm and key not in seen:
            seen.add(key)
            result.append(norm)
    return result


def _tail_text(path: str, max_bytes: int = 262_144) -> str:
    try:
        with open(path, "rb") as f:
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
            except OSError:
                pass
            return f.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _desktop_ports_from_log(path: str) -> list[int]:
    text = _tail_text(path)
    if not text:
        return []
    matches = []
    pattern = re.compile(
        r"HERMES_DASHBOARD_READY\s+port=(\d{2,5})|https?://(?:127\.0\.0\.1|localhost|\[::1\]):(\d{2,5})",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        matches.append(match.group(1) or match.group(2))
    ports: list[int] = []
    for item in reversed(matches):
        try:
            port = int(item)
        except Exception:
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports


def _port_from_url_or_host(value: str | None) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = urllib.parse.urlparse(value if "://" in value else f"http://{value}")
        if parsed.port:
            return int(parsed.port)
    except Exception:
        pass
    match = re.search(r":(\d{2,5})(?:/|$)", value)
    if not match:
        return None
    try:
        port = int(match.group(1))
        return port if 1 <= port <= 65535 else None
    except Exception:
        return None


def _port_range_from_env() -> list[int]:
    """Return bounded ports for optional Desktop route probing."""
    raw = os.environ.get("VO_HERMES_DESKTOP_DISCOVERY_PORTS", "49152-65535")
    ports: list[int] = []
    for item in re.split(r"[\s,]+", raw.strip()):
        if not item:
            continue
        if "-" in item:
            left, right = item.split("-", 1)
            try:
                start = max(1, min(65535, int(left.strip())))
                end = max(1, min(65535, int(right.strip())))
            except Exception:
                continue
            if start > end:
                start, end = end, start
            ports.extend(range(start, end + 1))
        else:
            try:
                port = int(item)
            except Exception:
                continue
            if 1 <= port <= 65535:
                ports.append(port)
    seen = set()
    result = []
    for port in ports:
        if port not in seen:
            seen.add(port)
            result.append(port)
    return result[:20000]


def _resolve_ipv4_host(host: str) -> str:
    host = str(host or "").strip()
    if not host:
        return ""
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    try:
        infos = socket.getaddrinfo(host, 80, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        return ""
    return ""


def _desktop_route_host_candidates(configured_host: str | None = None) -> list[tuple[str, str]]:
    hosts: list[tuple[str, str]] = []
    seen = set()

    def add(host: str | None, source: str) -> None:
        clean = str(host or "").strip()
        if not clean:
            return
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            hosts.append((clean, source))

    add(configured_host, "configured-route-host")
    for item in re.split(r"[\s,]+", os.environ.get("VO_HERMES_DESKTOP_DISCOVERY_HOSTS", "").strip()):
        add(item, "env-route-host")
    add(os.environ.get("VO_HERMES_DESKTOP_DOCKER_HOST"), "env-docker-host")
    add("host.docker.internal", "docker-host")
    add("127.0.0.1", "direct-loopback")
    return hosts


def _scan_open_tcp_ports(host: str, ports: list[int], timeout_sec: float = 4.0) -> list[int]:
    """Fast bounded TCP connect scan for user-triggered local Desktop discovery."""
    target = _resolve_ipv4_host(host)
    if not target or not ports:
        return []
    selector = selectors.DefaultSelector()
    pending: dict[int, tuple[socket.socket, int]] = {}
    open_ports: list[int] = []
    deadline = time.monotonic() + max(0.25, min(float(timeout_sec or 4.0), 12.0))
    batch_size = max(16, min(int(os.environ.get("VO_HERMES_DESKTOP_DISCOVERY_BATCH", "256") or 256), 1024))
    remaining = iter(ports)

    def close_fd(fd: int) -> None:
        item = pending.pop(fd, None)
        if not item:
            return
        sock, _ = item
        try:
            selector.unregister(sock)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    try:
        exhausted = False
        while time.monotonic() < deadline and (pending or not exhausted):
            while len(pending) < batch_size and time.monotonic() < deadline and not exhausted:
                try:
                    port = next(remaining)
                except StopIteration:
                    exhausted = True
                    break
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setblocking(False)
                    err = sock.connect_ex((target, int(port)))
                    if err == 0:
                        open_ports.append(int(port))
                        sock.close()
                    elif err in {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY}:
                        selector.register(sock, selectors.EVENT_WRITE)
                        pending[sock.fileno()] = (sock, int(port))
                    else:
                        sock.close()
                except Exception:
                    try:
                        sock.close()  # type: ignore[name-defined]
                    except Exception:
                        pass

            wait = max(0.0, min(0.05, deadline - time.monotonic()))
            events = selector.select(wait)
            if not events and len(pending) >= batch_size:
                continue
            for key, _ in events:
                fd = key.fd
                sock, port = pending.get(fd, (None, None))  # type: ignore[assignment]
                if not sock:
                    continue
                try:
                    err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if err == 0:
                        open_ports.append(int(port))
                except Exception:
                    pass
                close_fd(fd)
    finally:
        for fd in list(pending):
            close_fd(fd)
        try:
            selector.close()
        except Exception:
            pass

    seen = set()
    result = []
    for port in open_ports:
        if port not in seen:
            seen.add(port)
            result.append(port)
    return result


def _loopback_listener_ports(limit: int = 12) -> list[tuple[int, str]]:
    commands = [
        ["ss", "-ltnp"],
        ["ss", "-ltn"],
        ["netstat", "-an"],
        ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
    ]
    found: dict[int, tuple[int, str]] = {}
    for command in commands:
        if not shutil.which(command[0]):
            continue
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=2)
        except Exception:
            continue
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or "LISTEN" not in line.upper():
                continue
            if not re.search(r"(?:127\.0\.0\.1|localhost|\[::1\]|::1)", line, flags=re.IGNORECASE):
                continue
            ports = re.findall(r"(?:127\.0\.0\.1|localhost|\[::1\]|::1)[\].:]*(\d{2,5})", line, flags=re.IGNORECASE)
            if not ports:
                ports = re.findall(r"\*:(\d{2,5})", line)
            for item in ports:
                try:
                    port = int(item)
                except Exception:
                    continue
                if not (1 <= port <= 65535):
                    continue
                lower = line.lower()
                priority = 0
                if "hermes" in lower:
                    priority = 3
                elif "python" in lower:
                    priority = 2
                elif port >= 49152:
                    priority = 1
                if priority <= 0:
                    continue
                existing = found.get(port)
                if not existing or priority > existing[0]:
                    label = "hermes" if priority == 3 else ("python" if priority == 2 else "loopback")
                    found[port] = (priority, label)
        if found:
            break
    ordered = sorted(found.items(), key=lambda item: (-item[1][0], -item[0]))
    return [(port, detail) for port, (_, detail) in ordered[:limit]]


def discover_desktop_backend(
    *,
    hermes_home: str | None = None,
    desktop_url: str | None = None,
    desktop_token: str | None = None,
    desktop_host_header: str | None = None,
    desktop_tcp_host: str | None = None,
    desktop_tcp_port: int | str | None = None,
    desktop_log_path: str | None = None,
    timeout_sec: int = 2,
) -> dict[str, Any]:
    """Find a running Hermes Desktop `hermes serve` backend when possible."""
    port_sources: dict[int, list[str]] = {}

    def add_port(port: int | None, source: str) -> None:
        if not port or not (1 <= int(port) <= 65535):
            return
        port_sources.setdefault(int(port), [])
        if source not in port_sources[int(port)]:
            port_sources[int(port)].append(source)

    for path in _default_desktop_log_paths(hermes_home, [desktop_log_path] if desktop_log_path else []):
        for port in _desktop_ports_from_log(path)[:5]:
            add_port(port, "log:desktop.log")

    add_port(_port_from_url_or_host(desktop_url), "configured-url")
    add_port(_port_from_url_or_host(desktop_host_header), "configured-host-header")
    for port, detail in _loopback_listener_ports():
        add_port(port, f"listener:{detail}")

    candidates: list[dict[str, Any]] = []
    route_seen = set()
    for port, sources in port_sources.items():
        logical_url = f"http://127.0.0.1:{port}"
        host_header = f"127.0.0.1:{port}"
        route_options: list[tuple[str, int | str | None, str]] = []
        if desktop_tcp_host:
            route_options.append((str(desktop_tcp_host), desktop_tcp_port or None, "configured-route"))
            route_options.append((str(desktop_tcp_host), None, "configured-host-current-port"))
        route_options.append(("", None, "direct-loopback"))

        for tcp_host, tcp_port, route_source in route_options:
            key = (logical_url, host_header, tcp_host or "", str(tcp_port or ""))
            if key in route_seen:
                continue
            route_seen.add(key)
            client = HermesDesktopBackendClient(
                base_url=logical_url,
                token=desktop_token,
                host_header=host_header,
                tcp_host=tcp_host,
                tcp_port=tcp_port,
                timeout_sec=max(1, min(int(timeout_sec or 2), 5)),
            )
            status = client.test(verify_ws=True)
            candidate = {
                "ok": bool(status.get("ok")),
                "chatReady": bool(status.get("chatReady")),
                "desktopUrl": logical_url,
                "desktopHostHeader": host_header,
                "desktopTcpHost": status.get("tcpHost") or tcp_host or "",
                "desktopTcpPort": status.get("tcpPort") or tcp_port or "",
                "logicalUrl": status.get("logicalUrl") or logical_url,
                "connectUrl": status.get("connectUrl") or "",
                "websocketOk": bool(status.get("websocketOk")),
                "authRequired": bool(status.get("authRequired")),
                "version": status.get("version") or "",
                "error": status.get("error") or "",
                "sources": sources + [route_source],
            }
            candidates.append(candidate)

    candidates.sort(key=lambda item: (
        not item.get("chatReady"),
        not item.get("ok"),
        "log:" not in " ".join(item.get("sources") or []),
        item.get("error") or "",
    ))
    best = candidates[0] if candidates else {}
    discovered = any(
        item.get("chatReady") or any(str(source).startswith("log:") for source in (item.get("sources") or []))
        for item in candidates
    )
    result = {
        "ok": bool(best.get("chatReady")),
        "found": bool(discovered),
        "desktopUrl": best.get("desktopUrl") or "",
        "desktopHostHeader": best.get("desktopHostHeader") or "",
        "desktopTcpHost": best.get("desktopTcpHost") or "",
        "desktopTcpPort": best.get("desktopTcpPort") or "",
        "logicalUrl": best.get("logicalUrl") or "",
        "connectUrl": best.get("connectUrl") or "",
        "chatReady": bool(best.get("chatReady")),
        "websocketOk": bool(best.get("websocketOk")),
        "authRequired": bool(best.get("authRequired")),
        "version": best.get("version") or "",
        "sources": best.get("sources") or [],
        "candidates": candidates[:12],
    }
    if not candidates or not discovered:
        result["error"] = "No Hermes Desktop backend was found. Open Hermes Desktop, then try discovery again."
    elif not best.get("chatReady"):
        result["error"] = best.get("error") or "Hermes Desktop was found, but the backend was not reachable from this server."
    return result


def discover_desktop_agents(
    desktop_url: str | None = None,
    desktop_token: str | None = None,
    desktop_host_header: str | None = None,
    desktop_tcp_host: str | None = None,
    desktop_tcp_port: int | str | None = None,
    *,
    enabled: bool = True,
    timeout_sec: int = 5,
) -> list[dict[str, Any]]:
    """Return a Desktop Backend-backed Hermes agent when `hermes serve` is reachable."""
    if not enabled or not desktop_url:
        return []

    client = HermesDesktopBackendClient(
        base_url=desktop_url,
        token=desktop_token,
        host_header=desktop_host_header,
        tcp_host=desktop_tcp_host,
        tcp_port=desktop_tcp_port,
        timeout_sec=timeout_sec,
    )
    status = client.test(verify_ws=False)
    if not status.get("ok") or status.get("authRequired"):
        return []

    return [{
        "id": "hermes-default",
        "statusKey": "hermes-default",
        "providerKind": "hermes",
        "providerType": "runtime",
        "providerAgentId": "default",
        "profile": "default",
        "name": "Hermes Desktop",
        "emoji": os.environ.get("VO_HERMES_AGENT_EMOJI", "⚕️"),
        "role": "Hermes Agent",
        "model": status.get("model") or "Hermes Desktop",
        "provider": "Hermes Desktop Backend",
        "gateway": "desktop",
        "workspace": "",
        "home": status.get("hermesHome") or "",
        "binary": "",
        "desktopUrl": client.base_url,
        "desktopLogicalUrl": status.get("logicalUrl") or "",
        "desktopTcpHost": status.get("tcpHost") or "",
        "desktopTcpPort": status.get("tcpPort") or "",
        "desktopHostHeader": status.get("hostHeader") or "",
        "lastActiveAt": int(time.time()),
        "capabilities": ["chat", "status", "sessions", "desktop"],
        "connectionModes": ["desktop"],
        "cliAvailable": False,
        "apiAvailable": False,
        "desktopAvailable": True,
    }]
