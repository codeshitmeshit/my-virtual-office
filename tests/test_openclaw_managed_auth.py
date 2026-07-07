#!/usr/bin/env python3
"""Focused managed OpenClaw auth-store tests."""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import types


APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
SERVER_PATH = os.path.join(APP_DIR, "server.py")


def load_server():
    sys.path.insert(0, APP_DIR)
    if "websockets" not in sys.modules:
        websockets = types.ModuleType("websockets")
        websockets_asyncio = types.ModuleType("websockets.asyncio")
        websockets_client = types.ModuleType("websockets.asyncio.client")

        async def _missing_connect(*args, **kwargs):
            raise RuntimeError("websockets stub is not available in this isolated test")

        websockets_client.connect = _missing_connect
        websockets_asyncio.client = websockets_client
        websockets.asyncio = websockets_asyncio
        sys.modules["websockets"] = websockets
        sys.modules["websockets.asyncio"] = websockets_asyncio
        sys.modules["websockets.asyncio.client"] = websockets_client
    spec = importlib.util.spec_from_file_location("vo_server_under_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_store(root, agent_id, profiles):
    agent_dir = os.path.join(root, "agents", agent_id, "agent")
    os.makedirs(agent_dir, exist_ok=True)
    db_path = os.path.join(agent_dir, "openclaw-agent.sqlite")
    con = sqlite3.connect(db_path)
    con.execute("create table kv (store_key text primary key, store_json text, updated_at integer)")
    con.execute(
        "insert into kv values (?, ?, ?)",
        ("primary", json.dumps({"version": 1, "profiles": profiles, "lastGood": {}}), 0),
    )
    con.commit()
    con.close()


def read_profiles(root, agent_id):
    db_path = os.path.join(root, "agents", agent_id, "agent", "openclaw-agent.sqlite")
    con = sqlite3.connect(db_path)
    row = con.execute("select store_json from kv where store_key = ?", ("primary",)).fetchone()
    con.close()
    return json.loads(row[0])["profiles"]


def check(name, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  {mark} {name}" + (f" - {detail}" if detail else ""))
    if not condition:
        raise AssertionError(name)


def main():
    with tempfile.TemporaryDirectory() as root:
        os.environ["VO_STATUS_DIR"] = os.path.join(root, "status")
        os.environ["VO_OPENCLAW_PATH"] = root
        server = load_server()
        server.WORKSPACE_BASE = root
        server.CONFIG_PATH = os.path.join(root, "openclaw.json")
        server.AUTH_PROFILES_PATH = os.path.join(root, "agents", "main", "agent", "auth-profiles.json")
        server.OPENCLAW_BIN = ""
        server._signal_openclaw_gateway = lambda restart=False: {"ok": True, "method": "test"}
        with open(server.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"agents": {"list": [{"id": "agent-a"}], "defaults": {"model": {"primary": "openai/gpt-test"}}}}, f)

        main_profiles = {
            "openai:manual": {"type": "api_key", "provider": "openai", "key": "sk-main"},
            "anthropic:static-token": {"type": "token", "provider": "anthropic", "tokenRef": "portable"},
            "google:oauth": {"type": "oauth", "provider": "google", "access": "not-portable"},
        }
        agent_profiles = {
            "anthropic:static-token": {"type": "token", "provider": "anthropic", "tokenRef": "old"},
            "old:manual": {"type": "api_key", "provider": "old", "key": "extra"},
            "google:local-oauth": {"type": "oauth", "provider": "google", "access": "local"},
        }
        write_store(root, "main", main_profiles)
        write_store(root, "agent-a", agent_profiles)

        report = server._openclaw_managed_auth_report()
        managed_ids = {p["id"] for p in report["managedStaticProfiles"]}
        agent_row = next(row for row in report["agentRows"] if row["agent"] == "agent-a")
        check("OAuth is not managed static", "google:oauth" not in managed_ids)
        check("API key is managed static", "openai:manual" in managed_ids)
        check("Static token is managed static", "anthropic:static-token" in managed_ids)
        check("Missing static profile is reported", "openai:manual" in agent_row["missingManagedStatic"])
        check("Stale static profile is reported", "anthropic:static-token" in agent_row["divergentManagedStatic"])
        check("Extra static profile is reported", "old:manual" in agent_row["extraStaticProfiles"])
        check("Local OAuth is reported", "google:local-oauth" in agent_row["localOAuthProfiles"])

        sync = server._sync_openclaw_static_auth_from_main()
        check("Sync succeeds", sync.get("ok"))
        profiles = read_profiles(root, "agent-a")
        check("Sync copies missing API key", profiles.get("openai:manual") == main_profiles["openai:manual"])
        check("Sync updates stale static token", profiles.get("anthropic:static-token") == main_profiles["anthropic:static-token"])
        check("Sync preserves extra static until reset", "old:manual" in profiles)
        check("Sync preserves local OAuth", "google:local-oauth" in profiles)

        reset = server._reset_openclaw_static_auth_overrides("agent-a")
        check("Reset succeeds", reset.get("ok"))
        profiles = read_profiles(root, "agent-a")
        check("Reset removes extra static", "old:manual" not in profiles)
        check("Reset preserves local OAuth", "google:local-oauth" in profiles)

        saved = server._save_openclaw_api_key("openrouter", "sk-global", "openrouter:manual", sync_all=True)
        check("Global save succeeds", saved.get("ok"))
        check("Global save writes main", "openrouter:manual" in read_profiles(root, "main"))
        check("Global save syncs agent", "openrouter:manual" in read_profiles(root, "agent-a"))

        deleted = server._delete_openclaw_auth("openrouter", "openrouter:manual", sync_all=True)
        check("Global delete succeeds", deleted.get("ok"))
        check("Global delete removes main static", "openrouter:manual" not in read_profiles(root, "main"))
        check("Global delete removes agent static", "openrouter:manual" not in read_profiles(root, "agent-a"))
        check("Global delete still preserves OAuth", "google:local-oauth" in read_profiles(root, "agent-a"))

    print("\n  OpenClaw managed auth: all checks passed")


if __name__ == "__main__":
    main()
