"""Providers service functions split from server.py.

The functions intentionally hydrate their globals from the importing server module
so this mechanical split can preserve the existing module-level helpers and
configuration while removing domain business bodies from server.py.
"""

import sys

__all__ = ['_handle_codex_test', '_handle_claude_code_test', '_handle_hermes_test']


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _hydrate():
    srv = _server_module()
    if srv is None:
        return
    exported = set(__all__)
    for key, value in vars(srv).items():
        if key in {"_server_module", "_hydrate"}:
            continue
        if key in exported:
            globals()[key] = value
            continue
        globals()[key] = value


def _wrap_exports():
    for name in list(__all__):
        fn = globals().get(name)
        if not callable(fn) or getattr(fn, "_service_wrapper", False):
            continue

        def wrapper(*args, __fn=fn, **kwargs):
            _hydrate()
            return __fn(*args, **kwargs)

        wrapper.__name__ = getattr(fn, "__name__", name)
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        wrapper.__module__ = __name__
        wrapper._service_wrapper = True
        globals()[name] = wrapper


_wrap_exports()
_hydrate()


def _handle_claude_code_test(body=None):
    cfg = dict(VO_CONFIG.get("claudeCode", {}))
    if isinstance(body, dict):
        cfg.update({k: v for k, v in body.items() if v is not None})
    return ClaudeCodeProvider(
        home_path=cfg.get("homePath"),
        binary=cfg.get("binary"),
        workspace_root=cfg.get("workspaceRoot"),
        enabled=cfg.get("enabled", True),
        timeout_sec=int(cfg.get("timeoutSec") or 900),
        model=cfg.get("model") or "",
        permission_mode=cfg.get("permissionMode") or "acceptEdits",
        main_workspace=cfg.get("mainWorkspace"),
        include_main=cfg.get("includeMain", True),
        include_native_agents=cfg.get("includeNativeAgents", True),
        register_native_agents=cfg.get("registerNativeAgents", True),
    ).test()

def _handle_hermes_test(body=None):
    """Test the configured Hermes installation without changing Hermes state."""
    body = body or {}
    hermes_cfg = VO_CONFIG.get("hermes", {})
    hermes_bin = os.path.expanduser(body.get("binary") or hermes_cfg.get("binary") or "~/.local/bin/hermes")
    hermes_home = os.path.expanduser(body.get("homePath") or hermes_cfg.get("homePath") or "~/.hermes")
    result = HermesProvider(home_path=hermes_home, binary=hermes_bin, enabled=True).test()
    api_enabled = bool(body.get("apiEnabled") if "apiEnabled" in body else hermes_cfg.get("apiEnabled", False))
    api_url = body.get("apiUrl") or hermes_cfg.get("apiUrl") or "http://127.0.0.1:8642"
    api_key = body.get("apiKey") if "apiKey" in body else hermes_cfg.get("apiKey", "")
    result["api"] = {"enabled": api_enabled, "ok": False, "url": api_url}
    if api_enabled:
        try:
            client = HermesApiClient(base_url=api_url, api_key=api_key, timeout_sec=min(int(hermes_cfg.get("timeoutSec") or 600), 30))
            caps = client.capabilities()
            features = caps.get("features") if isinstance(caps.get("features"), dict) else {}
            result["api"].update({
                "ok": bool(features.get("run_submission") and features.get("run_events_sse")),
                "features": {
                    "runSubmission": bool(features.get("run_submission")),
                    "runEventsSse": bool(features.get("run_events_sse")),
                    "runApprovalResponse": bool(features.get("run_approval_response")),
                },
                "model": caps.get("model") or caps.get("model_name") or "",
            })
        except Exception as exc:
            result["api"]["error"] = str(exc)[:500]
    return result

def _handle_codex_test(body=None):
    """Test the configured Codex harness without requiring OpenClaw/Hermes."""
    cfg = dict(VO_CONFIG.get("codex", {}) or {})
    if isinstance(body, dict):
        cfg.update({k: v for k, v in body.items() if v is not None})
    return CodexProvider(
        enabled=bool(cfg.get("enabled", False)),
        workspace=cfg.get("workspace"),
        home_path=cfg.get("homePath"),
        binary=cfg.get("binary"),
        workspace_root=cfg.get("workspaceRoot"),
        main_workspace=cfg.get("mainWorkspace"),
        name=cfg.get("name"),
        agent_id=cfg.get("agentId"),
        model=cfg.get("model"),
        reply_text=cfg.get("replyText"),
        bridge_url=cfg.get("bridgeUrl"),
        sandbox=cfg.get("sandbox") or "workspace-write",
        approval_policy=cfg.get("approvalPolicy") or "never",
        prefer_app_server=cfg.get("preferAppServer", True),
        include_main=cfg.get("includeMain", True),
        include_native_agents=cfg.get("includeNativeAgents", True),
        register_native_agents=cfg.get("registerNativeAgents", True),
    ).test()

def _handle_claude_code_test(body=None):
    body = body or {}
    cfg = VO_CONFIG.get("claudeCode", {})
    provider = ClaudeCodeProvider(
        enabled=bool(body.get("enabled", cfg.get("enabled", False))),
        home_path=body.get("homePath") or cfg.get("homePath"),
        binary=body.get("binary") or cfg.get("binary"),
        workspace=body.get("workspace") or cfg.get("workspace"),
        name=body.get("name") or cfg.get("name"),
        agent_id=body.get("agentId") or cfg.get("agentId"),
        model=body.get("model") or cfg.get("model"),
        reply_text=body.get("replyText") if "replyText" in body else cfg.get("replyText"),
        timeout_sec=int(body.get("timeoutSec") or cfg.get("timeoutSec") or 900),
    )
    return provider.test()

_wrap_exports()
_hydrate()
