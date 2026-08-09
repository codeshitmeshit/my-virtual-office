"""Read-only management-session probe for the browser entry gate."""

from .http import send_json


GET_PATH = "/api/management/session"


def handle_get(handler, parsed_url):
    if parsed_url.path != GET_PATH:
        return False
    headers = {"Cache-Control": "no-store"}
    if not handler._management_request_allowed():
        return send_json(
            handler,
            {
                "ok": False,
                "authenticated": False,
                "code": "management_token_required",
                "error": "A valid Virtual Office management token is required",
            },
            status=403,
            headers=headers,
        )
    return send_json(
        handler,
        {"ok": True, "authenticated": True},
        status=200,
        headers=headers,
    )

