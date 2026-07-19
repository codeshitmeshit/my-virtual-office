"""Build the Codex app-server command from effective VO permission settings."""

from __future__ import annotations

from collections.abc import Sequence


BYPASS_APPROVALS_AND_SANDBOX_FLAG = "--dangerously-bypass-approvals-and-sandbox"


def should_bypass_approvals_and_sandbox(
    *,
    sandbox: str,
    approval_policy: str,
    route_approvals_through_vo: bool,
) -> bool:
    """Return whether VO requested Codex's native full-access preset."""
    return (
        sandbox == "danger-full-access"
        and approval_policy == "never"
        and not route_approvals_through_vo
    )


def build_codex_app_server_command(
    binary: str,
    *,
    sandbox: str,
    approval_policy: str,
    route_approvals_through_vo: bool,
    app_server_args: Sequence[str] = (),
) -> list[str]:
    """Build a correctly ordered Codex command, including global flags."""
    command = [binary]
    if should_bypass_approvals_and_sandbox(
        sandbox=sandbox,
        approval_policy=approval_policy,
        route_approvals_through_vo=route_approvals_through_vo,
    ):
        command.append(BYPASS_APPROVALS_AND_SANDBOX_FLAG)
    command.append("app-server")
    command.extend(app_server_args)
    command.append("--stdio")
    return command
