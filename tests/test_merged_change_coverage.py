#!/usr/bin/env python3
"""Guard the integration points brought in from eliautobot/main.

These checks intentionally inspect public entry points, not just helper
definitions, so a conflict resolution cannot leave a feature orphaned while
its focused unit test still passes.
"""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"
CHAT = ROOT / "app" / "chat.js"
MODELS = ROOT / "app" / "models.html"
GAME = ROOT / "app" / "game.js"
SETUP = ROOT / "app" / "setup.html"


def check(name, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'} {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        raise AssertionError(name)


def function_node(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"missing function {name}")


def calls(node):
    result = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            result.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            result.add(child.func.attr)
    return result


def source_segment(source, node):
    return ast.get_source_segment(source, node) or ""


def main():
    server_source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(server_source)

    chat_entry = function_node(tree, "_handle_hermes_chat")
    chat_calls = calls(chat_entry)
    check("Gateway Platform is called from Hermes chat", "_handle_hermes_platform_chat" in chat_calls)
    check("Desktop Backend is called from synchronous Hermes chat", "_handle_hermes_desktop_chat" in chat_calls)

    platform_chat = source_segment(server_source, function_node(tree, "_handle_hermes_platform_chat"))
    check("Gateway Platform isolates history by conversation", "_load_hermes_history(profile, conversation_id)" in platform_chat and "_save_hermes_history(profile, history, conversation_id)" in platform_chat)

    desktop_chat = source_segment(server_source, function_node(tree, "_handle_hermes_desktop_chat"))
    desktop_start = source_segment(server_source, function_node(tree, "_handle_hermes_desktop_run_start"))
    desktop_events = source_segment(server_source, function_node(tree, "_handle_hermes_desktop_run_events"))
    check("Desktop synchronous chat resumes the selected conversation", "_get_hermes_session_id(profile, conversation_id)" in desktop_chat)
    check("Desktop streaming run stores conversation identity", '"conversationId": conversation_id' in desktop_start and "_save_hermes_history(profile, history, conversation_id)" in desktop_start)
    check("Desktop streaming events preserve conversation history", "_load_hermes_history(profile, conversation_id)" in desktop_events and "_set_hermes_session_id(profile, session_id, conversation_id)" in desktop_events)

    run_entry = function_node(tree, "_handle_hermes_run_start")
    run_source = source_segment(server_source, run_entry)
    check("Hermes run start recognizes Gateway Platform", "_is_hermes_gateway_platform_agent" in calls(run_entry) and "gateway-platform" in run_source)
    check("Hermes run start calls Desktop Backend", "_handle_hermes_desktop_run_start" in calls(run_entry))

    test_entry = function_node(tree, "_handle_hermes_test")
    test_calls = calls(test_entry)
    check("Hermes test includes API", "_test_hermes_api" in test_calls)
    check("Hermes test includes Desktop", "_test_hermes_desktop" in test_calls)
    check("Hermes test includes Gateway Platform", "_handle_hermes_platform_status" in test_calls)
    check("Hermes test discovers merged agents", "discover_hermes_agents" in test_calls)

    save_key = function_node(tree, "_handle_save_key")
    delete_key = function_node(tree, "_handle_delete_key")
    check("Watcher API-key save synchronizes all agents", "sync_all=True" in source_segment(server_source, save_key))
    check("Watcher API-key delete synchronizes all agents", "sync_all=True" in source_segment(server_source, delete_key))

    office = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OfficeHandler")
    post = next(node for node in office.body if isinstance(node, ast.FunctionDef) and node.name == "do_POST")
    post_source = source_segment(server_source, post)
    check("Native auth save route synchronizes all agents", '"/api/native-models/openclaw/auth/api-key"' in post_source and "sync_all=True" in post_source)
    check("Native auth delete route synchronizes all agents", '"/api/native-models/openclaw/auth/delete"' in post_source and "_delete_openclaw_auth" in post_source)

    chat_source = CHAT.read_text(encoding="utf-8")
    check("Session browser renders timestamps", "session.updatedAt" in chat_source and "formatSessionTimestamp" in chat_source)
    check("Session browser renders Live Mode", "session.liveMode" in chat_source and "cs-live-badge" in chat_source)
    check("New managed Hermes session rotates conversation identity", "async createManagedSession()" in chat_source and "this.rotateProviderConversationId(providerKind)" in chat_source)
    create_session_source = chat_source.split("async createManagedSession()", 1)[1].split("async deleteManagedSession", 1)[0]
    check("New managed session rebinds SSE after reset", create_session_source.rfind("this.updateProviderEventSource()") > create_session_source.find("this.resetConversation("))
    switch_session_source = chat_source.split("async switchManagedSession(session)", 1)[1].split("async createManagedSession", 1)[0]
    check("Managed session switch rebinds provider SSE", "this.updateProviderEventSource()" in switch_session_source)
    check("Managed session list highlights provider conversation", "session.id === activeConversationId" in chat_source)
    check("Managed session delete sends provider conversation", "sessionKey: session.sessionKey, conversationId" in chat_source)

    settings = MODELS.read_text(encoding="utf-8") + GAME.read_text(encoding="utf-8") + SETUP.read_text(encoding="utf-8")
    check("All settings surfaces expose Desktop discovery", settings.count("/api/hermes/desktop/discover") >= 3)
    check("All settings surfaces persist discovered Desktop routes", settings.count("preferDesktop = true") + settings.count("preferDesktop: true") >= 3)

    print("\n  Merged change coverage: all entry-point checks passed")


if __name__ == "__main__":
    main()
