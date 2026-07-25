from .http import JsonBodyError, read_json, send_json


def _providers_service():
    from server_services import providers
    providers._hydrate()
    return providers


def _json_body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def handle_get(handler, parsed_url):
    path = parsed_url.path
    providers_service = _providers_service()
    if path == "/config/providers":
        return send_json(handler, handler._get_providers())
    if path == "/api/hermes/test":
        result = providers_service._handle_hermes_test()
        return send_json(handler, result, status=200 if result.get("ok") else 503)
    if path == "/api/codex/test":
        result = providers_service._handle_codex_test()
        return send_json(handler, result, status=200 if result.get("ok") else 503)
    if path == "/api/claude-code/test":
        result = providers_service._handle_claude_code_test()
        return send_json(handler, result, status=200 if result.get("ok") else 503)
    return False


def handle_post(handler, parsed_url):
    path = parsed_url.path
    providers_service = _providers_service()
    body, error = _json_body(handler) if path in {
        "/api/hermes/test",
        "/api/codex/test",
        "/api/claude-code/test",
        "/config/providers/save-key",
        "/config/providers/delete-key",
        "/config/providers/save-custom",
    } else ({}, None)
    if error:
        return send_json(handler, error)
    if path == "/api/hermes/test":
        result = providers_service._handle_hermes_test(body)
        return send_json(handler, result, status=200 if result.get("ok") else 503)
    if path == "/api/codex/test":
        result = providers_service._handle_codex_test(body)
        return send_json(handler, result, status=200 if result.get("ok") else 503)
    if path == "/api/claude-code/test":
        result = providers_service._handle_claude_code_test(body)
        return send_json(handler, result, status=200 if result.get("ok") else 503)
    if path == "/config/providers/save-key":
        return send_json(handler, handler._save_provider_key(body.get("provider", ""), body.get("key", "")))
    if path == "/config/providers/delete-key":
        return send_json(handler, handler._delete_provider_key(body.get("provider", ""), body.get("profileId", "")))
    if path == "/config/providers/save-custom":
        result = handler._save_custom_provider(
            body.get("provider", ""),
            body.get("baseUrl", ""),
            body.get("models", []),
            body.get("params"),
            body.get("api"),
            body.get("apiKey"),
            body.get("timeoutSeconds"),
        )
        return send_json(handler, result)
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
