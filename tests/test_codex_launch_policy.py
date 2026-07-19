#!/usr/bin/env python3
"""Tests for Codex app-server launch policy selection."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from providers.codex_launch_policy import build_codex_app_server_command


def test_full_access_never_uses_native_bypass_flag_before_subcommand():
    assert build_codex_app_server_command(
        "/usr/local/bin/codex",
        sandbox="danger-full-access",
        approval_policy="never",
        route_approvals_through_vo=False,
    ) == [
        "/usr/local/bin/codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "app-server",
        "--stdio",
    ]


def test_interactive_approval_modes_do_not_bypass():
    assert build_codex_app_server_command(
        "codex",
        sandbox="danger-full-access",
        approval_policy="on-request",
        route_approvals_through_vo=False,
    ) == ["codex", "app-server", "--stdio"]


def test_vo_approval_routing_takes_precedence_over_bypass():
    assert build_codex_app_server_command(
        "codex",
        sandbox="danger-full-access",
        approval_policy="never",
        route_approvals_through_vo=True,
        app_server_args=["-c", "hooks.state={}"],
    ) == [
        "codex",
        "app-server",
        "-c",
        "hooks.state={}",
        "--stdio",
    ]
