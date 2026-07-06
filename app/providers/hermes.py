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
                "connectionModes": ["cli"],
                "cliAvailable": True,
                "apiAvailable": False,
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
            body = ""
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

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._json_request("GET", f"/v1/runs/{run_id}")

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
    timeout_sec: int = 10

    def __post_init__(self) -> None:
        self.base_url = (
            self.base_url
            or os.environ.get("VO_HERMES_DESKTOP_URL")
            or ""
        ).rstrip("/")
        self.token = self.token if self.token is not None else os.environ.get("VO_HERMES_DESKTOP_TOKEN", "")
        self.host_header = self.host_header if self.host_header is not None else os.environ.get("VO_HERMES_DESKTOP_HOST_HEADER", "")

    def _url(self, path: str) -> str:
        if not self.base_url:
            return ""
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

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
        req = urllib.request.Request(self._url(path), headers=self._headers(), method=method.upper())
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
        req = urllib.request.Request(self._url("/"), headers={"Accept": "text/html", **({"Host": self.host_header} if self.host_header else {})}, method="GET")
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
        if self.host_header:
            headers["Host"] = self.host_header
        timeout = min(int(self.timeout_sec), 30)
        kwargs = {"open_timeout": timeout, "close_timeout": 1}
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

    def send_chat_message(self, message: str, session_id: str | None = None, timeout_sec: int | None = None) -> dict[str, Any]:
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

                await self._rpc(ws, "prompt.submit", {"session_id": live_session_id, "text": message}, timeout_sec=min(int(timeout_sec or self.timeout_sec), 30))

                reply_parts: list[str] = []
                reasoning_parts: list[str] = []
                tools: list[dict[str, Any]] = []
                tools_by_id: dict[str, dict[str, Any]] = {}
                terminal_error = ""
                deadline = time.monotonic() + int(timeout_sec or self.timeout_sec)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Hermes Desktop Backend chat timed out")
                    item = await self._recv_json(ws, remaining)
                    if item.get("method") != "event":
                        continue
                    params_obj = item.get("params") if isinstance(item.get("params"), dict) else {}
                    event_type = str(params_obj.get("type") or "").lower()
                    payload = params_obj.get("payload") if isinstance(params_obj.get("payload"), dict) else {}
                    event_session = str(params_obj.get("session_id") or payload.get("session_id") or "")
                    if event_session and event_session != live_session_id:
                        continue
                    if event_type in {"message.delta", "thinking.delta", "reasoning.delta"}:
                        text = str(payload.get("text") or payload.get("delta") or "")
                        if event_type == "message.delta":
                            reply_parts.append(text)
                        elif text:
                            reasoning_parts.append(text)
                    elif event_type == "tool.start":
                        tool_id = str(payload.get("tool_id") or payload.get("toolCallId") or f"desktop-tool-{len(tools) + 1}")
                        card = {
                            "id": tool_id,
                            "name": str(payload.get("name") or "Hermes tool"),
                            "status": "running",
                            "args_preview": str(payload.get("context") or payload.get("preview") or ""),
                            "result": "Running",
                        }
                        tools_by_id[tool_id] = card
                        tools.append(card)
                    elif event_type == "tool.complete":
                        tool_id = str(payload.get("tool_id") or payload.get("toolCallId") or "")
                        card = tools_by_id.get(tool_id) if tool_id else None
                        if not card:
                            card = {"id": tool_id or f"desktop-tool-{len(tools) + 1}", "name": str(payload.get("name") or "Hermes tool")}
                            tools.append(card)
                        card.update({
                            "status": "done",
                            "result": str(payload.get("summary") or "Completed"),
                        })
                    elif event_type in {"approval.request", "clarify.request", "sudo.request", "secret.request"}:
                        terminal_error = "Hermes Desktop Backend is waiting for interactive input that Virtual Office cannot answer yet."
                        break
                    elif event_type == "error":
                        terminal_error = str(payload.get("message") or payload.get("error") or "Hermes Desktop Backend error")
                        break
                    elif event_type == "message.complete":
                        text = str(payload.get("text") or "")
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
            "statusEndpoint": self._url("/api/status") if self.base_url else "",
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


def discover_desktop_agents(
    desktop_url: str | None = None,
    desktop_token: str | None = None,
    desktop_host_header: str | None = None,
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
        "lastActiveAt": int(time.time()),
        "capabilities": ["chat", "status", "sessions", "desktop"],
        "connectionModes": ["desktop"],
        "cliAvailable": False,
        "apiAvailable": False,
        "desktopAvailable": True,
    }]
