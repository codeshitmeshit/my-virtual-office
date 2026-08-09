"""Runtime config/status service split from server.py."""

import sys

from services import office_branding as office_branding_service
from services.weather_providers import (
    DEFAULT_WEATHER_SERVICE,
    WeatherProviderError,
    WeatherSettings,
)

__all__ = ['_merge_setup_config', '_clear_setup_secret_paths', '_persist_setup_payload', '_build_safe_vo_config', '_handle_health', '_handle_e2e_health', '_handle_status', '_handle_vo_config', '_handle_license_status', '_handle_license_activate', '_handle_license_deactivate', '_handle_office_config_get', '_handle_office_config_save', '_weather_fetch', '_handle_weather_proxy', '_handle_weather_test']


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _hydrate():
    server = _server_module()
    if server is None or server is sys.modules.get(__name__):
        return
    exported = set(__all__)
    for key, value in vars(server).items():
        if key.startswith("__") or key in ("_server_module", "_hydrate", "_wrap_exports"):
            continue
        if key in exported and callable(value) and (
            getattr(value, "_service_wrapper", False) or getattr(value, "_service_wrapped", False)
        ):
            continue
        globals()[key] = value


def _wrap_exports():
    current = sys.modules[__name__]
    for name in __all__:
        value = globals().get(name)
        if not callable(value) or getattr(value, "_service_wrapped", False):
            continue

        def make_wrapper(fn):
            def wrapper(*args, **kwargs):
                _hydrate()
                return fn(*args, **kwargs)
            wrapper.__name__ = fn.__name__
            wrapper.__doc__ = fn.__doc__
            wrapper.__dict__.update(getattr(fn, "__dict__", {}))
            wrapper._service_wrapped = True
            return wrapper

        setattr(current, name, make_wrapper(value))


def _sync_runtime_globals_to_loaded_modules(keys):
    for module_name, module in list(sys.modules.items()):
        if module_name != "server" and not module_name.startswith("server_services."):
            continue
        if module is None or module is sys.modules.get(__name__):
            continue
        for key in keys:
            if key in globals():
                setattr(module, key, globals()[key])


def _merge_setup_config(existing, incoming):
    """Merge setup/settings payloads without erasing saved secrets with empty fields."""
    merged = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    if not isinstance(incoming, dict):
        return merged
    for key, value in incoming.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            target = merged[key]
            for child_key, child_value in value.items():
                if str(child_key).startswith("_"):
                    continue
                if child_key in _SETUP_SECRET_KEYS and child_value in ("", None):
                    continue
                if isinstance(child_value, dict) and isinstance(target.get(child_key), dict):
                    target[child_key] = _merge_setup_config(target[child_key], child_value)
                else:
                    target[child_key] = child_value
        else:
            if key in _SETUP_SECRET_KEYS and value in ("", None):
                continue
            merged[key] = value
    if isinstance(merged.get("codex"), dict):
        # Keep deterministic Codex replies as an explicit env-only test hook.
        # Persisting it in normal setup config silently disables live Codex.
        merged["codex"].pop("replyText", None)
    return merged


def _clear_setup_secret_paths(config, paths):
    allowed = {"notifications.feishuWebhook", "feishu.chatApp.appSecret"}
    if not isinstance(config, dict) or not isinstance(paths, list):
        return
    for path in paths:
        if path not in allowed:
            continue
        node = config
        parts = path.split(".")
        for part in parts[:-1]:
            next_node = node.get(part)
            if not isinstance(next_node, dict):
                node = None
                break
            node = next_node
        if isinstance(node, dict):
            node[parts[-1]] = ""


def _persist_setup_payload(body):
    if isinstance(body, dict) and "office" in body:
        try:
            body = copy.deepcopy(body)
            body["office"] = office_branding_service.normalize_office_patch(body.get("office"))
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "code": "invalid_office_branding", "_status": 400}
    cfg_path = _resolve_config_path()
    data_dir = os.environ.get("VO_STATUS_DIR", "/data")
    persistent_path = os.path.join(data_dir, "vo-config.json")
    prefer_status_dir = isinstance(body, dict) and (
        body.get("_preferStatusDir") is True
        or "feishu" in body
        or "notifications" in body
    )
    if os.path.isdir(data_dir) and cfg_path != persistent_path and (
        prefer_status_dir or not os.environ.get("VO_CONFIG")
    ):
        cfg_path = persistent_path
    existing = {}
    for try_path in [cfg_path, os.path.join(os.path.dirname(__file__), "vo-config.json")]:
        try:
            with open(try_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            break
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    incoming_feishu = body.get("feishu") if isinstance(body, dict) and isinstance(body.get("feishu"), dict) else {}
    incoming_chat = incoming_feishu.get("chatApp") if isinstance(incoming_feishu.get("chatApp"), dict) else {}
    if incoming_chat.get("groupChatEnabled") is True:
        existing_chat = ((existing.get("feishu") or {}).get("chatApp") or {}) if isinstance(existing, dict) else {}
        selected_transport = str(
            os.environ.get("VO_FEISHU_CHAT_TRANSPORT")
            or incoming_chat.get("transportImplementation")
            or existing_chat.get("transportImplementation")
            or "channel-sdk-node"
        ).strip().lower()
        if selected_transport != "channel-sdk-node":
            return {
                "ok": False,
                "error": "Feishu group chat requires the Channel SDK (Node) transport",
                "code": "group_chat_requires_channel_sdk",
                "_status": 400,
            }
    existing = _merge_setup_config(existing, body)
    _clear_setup_secret_paths(existing, body.get("_clearSecrets") if isinstance(body, dict) else None)
    existing["_setupComplete"] = True
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    global VO_CONFIG, WORKSPACE_BASE, STATUS_DIR, _discovered_roster, _discovered_at
    old_gw = GATEWAY_URL
    old_token = _get_gateway_token()
    if prefer_status_dir and os.environ.get("VO_CONFIG"):
        explicit_config = os.environ.pop("VO_CONFIG")
        try:
            VO_CONFIG = _load_vo_config()
        finally:
            os.environ["VO_CONFIG"] = explicit_config
    else:
        VO_CONFIG = _load_vo_config()
    STATUS_DIR = VO_CONFIG["presence"]["statusDir"]
    WORKSPACE_BASE = VO_CONFIG["openclaw"]["homePath"]
    _reload_gateway_globals()
    for key in ("GATEWAY_URL", "GATEWAY_HTTP", "OPENCLAW_BIN", "HERMES_HOME", "HERMES_BIN"):
        server = _server_module()
        if server is not None and hasattr(server, key):
            globals()[key] = getattr(server, key)
    _sync_runtime_globals_to_loaded_modules([
        "VO_CONFIG",
        "STATUS_DIR",
        "WORKSPACE_BASE",
        "GATEWAY_URL",
        "GATEWAY_HTTP",
        "OPENCLAW_BIN",
        "HERMES_HOME",
        "HERMES_BIN",
    ])
    _discovered_roster = _discover_roster()
    _discovered_at = time.time()
    _sync_runtime_globals_to_loaded_modules(["_discovered_roster", "_discovered_at"])
    refresh_agent_maps()
    new_token = _get_gateway_token()
    if GATEWAY_URL != old_gw or new_token != old_token:
        gateway_presence.stop()
        if new_token:
            gateway_presence.start(GATEWAY_URL, new_token, port=PORT, client_version=_get_openclaw_version())
    if isinstance(body, dict) and isinstance(body.get("feishu"), dict) and "chatApp" in body.get("feishu", {}):
        _start_feishu_chat_long_connection()
    return {"ok": True}


def _build_safe_vo_config():
    lic = get_license_status()
    hermes_test = _handle_hermes_test()
    return {
        "office": VO_CONFIG["office"],
        "features": VO_CONFIG["features"],
        "weather": WeatherSettings.from_mapping(
            VO_CONFIG.get("weather", {}), os.environ
        ).safe_dict(),
        "openclaw": {
            "gatewayUrl": VO_CONFIG["openclaw"]["gatewayUrl"],
            "gatewayHttp": VO_CONFIG["openclaw"]["gatewayHttp"],
            "homePath": VO_CONFIG["openclaw"]["homePath"],
            "detected": os.path.isdir(VO_CONFIG["openclaw"]["homePath"]),
        },
        "browser": {
            "cdpUrl": VO_CONFIG.get("browser", {}).get("cdpUrl"),
            "viewerUrl": VO_CONFIG.get("browser", {}).get("viewerUrl"),
        },
        "notifications": {
            "feishuEnabled": VO_CONFIG.get("notifications", {}).get("feishuEnabled", True),
            "feishuConfigured": _feishu_app_configured(VO_CONFIG.get("notifications", {})),
            "feishuAppConfigured": _feishu_app_configured(VO_CONFIG.get("notifications", {})),
            "maskedFeishuAppId": _mask_secret_value(VO_CONFIG.get("notifications", {}).get("feishuAppId"), 5, 4),
            "feishuReceiveIdType": VO_CONFIG.get("notifications", {}).get("feishuReceiveIdType") or "chat_id",
            "maskedFeishuReceiveId": _mask_secret_value(VO_CONFIG.get("notifications", {}).get("feishuReceiveId"), 5, 4),
            "topicConversationsEnabled": bool(VO_CONFIG.get("notifications", {}).get("topicConversationsEnabled", False)),
            "topicConversationModels": _normalize_feishu_topic_model_choices(
                VO_CONFIG.get("notifications", {}).get("topicConversationModels")
            ),
        },
        "hermes": {
            "enabled": VO_CONFIG.get("hermes", {}).get("enabled", True),
            "homePath": VO_CONFIG.get("hermes", {}).get("homePath"),
            "binary": VO_CONFIG.get("hermes", {}).get("binary"),
            "timeoutSec": VO_CONFIG.get("hermes", {}).get("timeoutSec", 600),
            "apiEnabled": VO_CONFIG.get("hermes", {}).get("apiEnabled", False),
            "preferApi": VO_CONFIG.get("hermes", {}).get("preferApi", VO_CONFIG.get("hermes", {}).get("apiEnabled", False)),
            "apiUrl": VO_CONFIG.get("hermes", {}).get("apiUrl"),
            "detected": bool(hermes_test.get("ok")),
            "apiDetected": bool((hermes_test.get("api") or {}).get("ok")),
        },
        "codex": {
            "enabled": VO_CONFIG.get("codex", {}).get("enabled", False),
            "homePath": VO_CONFIG.get("codex", {}).get("homePath"),
            "binary": VO_CONFIG.get("codex", {}).get("binary"),
            "workspace": VO_CONFIG.get("codex", {}).get("workspace"),
            "workspaceRoot": VO_CONFIG.get("codex", {}).get("workspaceRoot"),
            "mainWorkspace": VO_CONFIG.get("codex", {}).get("mainWorkspace"),
            "name": VO_CONFIG.get("codex", {}).get("name"),
            "agentId": VO_CONFIG.get("codex", {}).get("agentId"),
            "model": VO_CONFIG.get("codex", {}).get("model"),
            "bridgeUrl": VO_CONFIG.get("codex", {}).get("bridgeUrl"),
            "sandbox": VO_CONFIG.get("codex", {}).get("sandbox"),
            "approvalPolicy": VO_CONFIG.get("codex", {}).get("approvalPolicy"),
            "includeMain": VO_CONFIG.get("codex", {}).get("includeMain", False),
            "includeNativeAgents": VO_CONFIG.get("codex", {}).get("includeNativeAgents", True),
            "registerNativeAgents": VO_CONFIG.get("codex", {}).get("registerNativeAgents", True),
            "detected": bool(_handle_codex_test().get("ok")),
        },
        "claudeCode": {
            "enabled": VO_CONFIG.get("claudeCode", {}).get("enabled", False),
            "homePath": VO_CONFIG.get("claudeCode", {}).get("homePath"),
            "binary": VO_CONFIG.get("claudeCode", {}).get("binary"),
            "workspace": VO_CONFIG.get("claudeCode", {}).get("workspace"),
            "workspaceRoot": VO_CONFIG.get("claudeCode", {}).get("workspaceRoot"),
            "mainWorkspace": VO_CONFIG.get("claudeCode", {}).get("mainWorkspace"),
            "name": VO_CONFIG.get("claudeCode", {}).get("name"),
            "agentId": VO_CONFIG.get("claudeCode", {}).get("agentId"),
            "model": VO_CONFIG.get("claudeCode", {}).get("model"),
            "timeoutSec": VO_CONFIG.get("claudeCode", {}).get("timeoutSec", 900),
            "permissionMode": VO_CONFIG.get("claudeCode", {}).get("permissionMode"),
            "includeMain": VO_CONFIG.get("claudeCode", {}).get("includeMain", False),
            "includeNativeAgents": VO_CONFIG.get("claudeCode", {}).get("includeNativeAgents", True),
            "registerNativeAgents": VO_CONFIG.get("claudeCode", {}).get("registerNativeAgents", True),
            "detected": bool(_handle_claude_code_test().get("ok")),
        },
        "license": {
            "licensed": lic["licensed"],
            "tier": lic["tier"],
            "tierName": lic["tierName"],
            "demo": lic["demo"],
            "limits": lic.get("limits"),
        },
    }




def _handle_health():
    return {"ok": True, "status": "running"}


def _handle_e2e_health():
    return {"status": "ok", "test": "e2e"}


def _handle_status():
    return _get_normalized_presence_state()


def _handle_vo_config():
    return _build_safe_vo_config()


def _handle_license_status():
    return get_license_status()


def _handle_license_activate(body):
    return activate_license((body or {}).get("key", ""))


def _handle_license_deactivate():
    return deactivate_license()


def _handle_office_config_get():
    oc_path = os.path.join(STATUS_DIR, "office-config.json")

    def parse_or_empty(raw):
        try:
            return json.loads(raw or "{}")
        except Exception:
            return {}

    def default_payload():
        default_path = os.path.join(os.path.dirname(__file__) or ".", "..", "default-office-config.json")
        default_path = os.path.abspath(default_path)
        try:
            with open(default_path, "r") as f:
                data = _patch_default_config_agents(f.read())
            return parse_or_empty(data)
        except FileNotFoundError:
            return {"error": "No saved config", "_status": 404}

    try:
        with open(oc_path, "r") as f:
            raw = f.read()
        parsed = parse_or_empty(raw)
        meaningful = bool(
            isinstance(parsed, dict) and (
                parsed.get("canvasWidth") or parsed.get("canvasHeight") or
                (isinstance(parsed.get("furniture"), list) and len(parsed.get("furniture")) > 0) or
                (isinstance(parsed.get("branches"), list) and len(parsed.get("branches")) > 0) or
                parsed.get("floor") or parsed.get("agents") or
                (isinstance(parsed.get("walls"), dict) and (
                    (isinstance(parsed.get("walls", {}).get("interior"), list) and len(parsed.get("walls", {}).get("interior")) > 0) or
                    (isinstance(parsed.get("walls", {}).get("sections"), list) and len(parsed.get("walls", {}).get("sections")) > 0)
                ))
            )
        )
        return parsed if meaningful else default_payload()
    except FileNotFoundError:
        return default_payload()


def _handle_office_config_save(raw_body):
    raw_body = raw_body or b"{}"
    try:
        json.loads(raw_body)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "_status": 400}
    oc_path = os.path.join(STATUS_DIR, "office-config.json")
    with open(oc_path, "w") as f:
        f.write(raw_body.decode())
    os.chmod(oc_path, 0o666)
    return {"ok": True}


def _weather_settings(candidate=None):
    merged = copy.deepcopy(VO_CONFIG.get("weather", {}))
    candidate = candidate if isinstance(candidate, dict) else {}
    if candidate:
        if "weather" in candidate and isinstance(candidate.get("weather"), dict):
            candidate = candidate["weather"]
        for key in ("provider", "location", "latitude", "longitude", "fallbackEnabled"):
            value = candidate.get(key)
            if isinstance(value, list):
                value = value[0] if value else None
            if value not in (None, ""):
                merged[key] = value
        qweather = candidate.get("qweather") if isinstance(candidate.get("qweather"), dict) else {}
        if candidate.get("apiHost"):
            qweather = {**qweather, "apiHost": candidate.get("apiHost")}
        if candidate.get("apiKey"):
            qweather = {**qweather, "apiKey": candidate.get("apiKey")}
        if qweather:
            target = merged.get("qweather") if isinstance(merged.get("qweather"), dict) else {}
            target = {**target, **{key: value for key, value in qweather.items() if value and "••" not in str(value)}}
            merged["qweather"] = target
    return WeatherSettings.from_mapping(merged, os.environ)


def _weather_fetch(location=None, candidate=None, *, force=False):
    payload = dict(candidate or {})
    if location and not payload.get("location"):
        payload["location"] = location
    return DEFAULT_WEATHER_SERVICE.current(_weather_settings(payload), force=force)


def _handle_weather_proxy():
    try:
        return _weather_fetch()
    except WeatherProviderError as exc:
        status = 400 if exc.code in {"invalid_location", "invalid_qweather_host", "unsupported_provider"} else 503
        return {"ok": False, "code": exc.code, "error": str(exc), "_status": status}
    except Exception:
        return {"ok": False, "code": "weather_unavailable", "error": "Weather is temporarily unavailable", "_status": 503}


def _handle_weather_test(query):
    try:
        data = _weather_fetch(candidate=query, force=True)
        current = data.get("current") or {}
        location = data.get("location") or {}
        return {
            **data,
            "resolvedLocation": location.get("name") or _weather_settings(query).location,
            "weather": current.get("description"),
            "tempF": current.get("temperatureF"),
            "tempC": current.get("temperatureC"),
            "updatedAt": data.get("fetchedAt") or int(time.time() * 1000),
        }
    except WeatherProviderError as exc:
        status = 400 if exc.code in {
            "invalid_location",
            "invalid_qweather_host",
            "unsupported_provider",
            "qweather_location_required",
        } else 503
        return {"ok": False, "code": exc.code, "error": str(exc), "_status": status}
    except Exception:
        return {"ok": False, "code": "weather_unavailable", "error": "Weather is temporarily unavailable", "_status": 503}

_wrap_exports()
_hydrate()
