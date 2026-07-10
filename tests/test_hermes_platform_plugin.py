#!/usr/bin/env python3
"""Focused tests for the bundled Hermes My Virtual Office plugin."""
import importlib.util
import os
import sys
import types
from dataclasses import dataclass, field


PLUGIN_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "integrations",
    "hermes-platform",
    "my_virtual_office",
    "adapter.py",
)


def install_gateway_stubs():
    gateway = types.ModuleType("gateway")
    gateway_config = types.ModuleType("gateway.config")
    gateway_platforms = types.ModuleType("gateway.platforms")
    gateway_platforms_base = types.ModuleType("gateway.platforms.base")

    class Platform(str):
        def __new__(cls, value):
            return str.__new__(cls, value)

    class PlatformConfig:
        def __init__(self, extra=None):
            self.extra = extra or {}

    class MessageType:
        TEXT = "text"

    @dataclass
    class MessageEvent:
        text: str
        message_type: str = MessageType.TEXT
        source: object = None
        raw_message: object = None
        message_id: str = ""
        metadata: dict = field(default_factory=dict)

    @dataclass
    class SendResult:
        success: bool
        message_id: str = ""
        error: str = ""

    class BasePlatformAdapter:
        def __init__(self, config, platform):
            self.config = config
            self.platform = platform
            self._running = False
            self._message_handler = True

        def _mark_connected(self):
            self._running = True

        def _mark_disconnected(self):
            self._running = False

        def _set_fatal_error(self, *args, **kwargs):
            self._fatal_error = (args, kwargs)

        def build_source(self, **kwargs):
            return types.SimpleNamespace(platform=self.platform, **kwargs)

        async def handle_message(self, event):
            self.last_event = event

    gateway_config.Platform = Platform
    gateway_config.PlatformConfig = PlatformConfig
    gateway_platforms_base.BasePlatformAdapter = BasePlatformAdapter
    gateway_platforms_base.MessageEvent = MessageEvent
    gateway_platforms_base.MessageType = MessageType
    gateway_platforms_base.SendResult = SendResult
    gateway.platforms = gateway_platforms
    gateway.config = gateway_config

    sys.modules["gateway"] = gateway
    sys.modules["gateway.config"] = gateway_config
    sys.modules["gateway.platforms"] = gateway_platforms
    sys.modules["gateway.platforms.base"] = gateway_platforms_base
    return PlatformConfig


def load_plugin():
    spec = importlib.util.spec_from_file_location("my_virtual_office_adapter_under_test", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HTTPX_AVAILABLE = True
    return module


def check(name, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  {mark} {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        raise AssertionError(name)


class Ctx:
    def __init__(self):
        self.platform = None

    def register_platform(self, **kwargs):
        self.platform = kwargs


def main():
    old_env = os.environ.copy()
    old_modules = {k: sys.modules.get(k) for k in ("gateway", "gateway.config", "gateway.platforms", "gateway.platforms.base")}
    try:
        PlatformConfig = install_gateway_stubs()
        os.environ.update({
            "MY_VIRTUAL_OFFICE_URL": "http://office.test:8090/",
            "MY_VIRTUAL_OFFICE_TOKEN": "shared",
            "MY_VIRTUAL_OFFICE_ADAPTER_ID": "adapter-1",
            "MY_VIRTUAL_OFFICE_POLL_SECONDS": "3",
            "MY_VIRTUAL_OFFICE_HOME_CHANNEL": "home-chat",
        })
        plugin = load_plugin()

        check("Requirements pass with URL/token", plugin.check_requirements())
        seed = plugin._env_enablement()
        check("Env enablement seeds base URL without trailing slash", seed["base_url"] == "http://office.test:8090", str(seed))
        check("Env enablement seeds home channel", seed["home_channel"]["chat_id"] == "home-chat", str(seed))

        adapter = plugin.MyVirtualOfficeAdapter(PlatformConfig(extra={}))
        check("Adapter platform name is official plugin name", str(adapter.platform) == "my_virtual_office", str(adapter.platform))
        check("Adapter poll seconds comes from env", adapter.poll_seconds == 3, str(adapter.poll_seconds))

        ctx = Ctx()
        plugin.register(ctx)
        check("register_platform called", isinstance(ctx.platform, dict))
        check("Registered platform name", ctx.platform.get("name") == "my_virtual_office", str(ctx.platform))
        check("Allowed-users env registered", ctx.platform.get("allowed_users_env") == "MY_VIRTUAL_OFFICE_ALLOWED_USERS", str(ctx.platform))
        check("Cron env registered", ctx.platform.get("cron_deliver_env_var") == "MY_VIRTUAL_OFFICE_HOME_CHANNEL", str(ctx.platform))
        check("Standalone sender registered", callable(ctx.platform.get("standalone_sender_fn")), str(ctx.platform))
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        for key, value in old_modules.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    print("\n  Hermes platform plugin: all checks passed")


if __name__ == "__main__":
    main()
