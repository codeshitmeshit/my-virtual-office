#!/usr/bin/env python3
"""Focused Hermes Desktop discovery tests."""
import os
import sys
import tempfile


APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)

from providers import hermes  # noqa: E402


def check(name, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  {mark} {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        raise AssertionError(name)


def main():
    old_test = hermes.HermesDesktopBackendClient.test
    old_listener_ports = hermes._loopback_listener_ports
    old_running_in_docker = hermes.HermesDesktopBackendClient._running_in_docker

    try:
        with tempfile.TemporaryDirectory() as root:
            logs_dir = os.path.join(root, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            log_path = os.path.join(logs_dir, "desktop.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("HERMES_DASHBOARD_READY port=62353\n")
                f.write("dashboard at http://127.0.0.1:62353\n")
                f.write("HERMES_DASHBOARD_READY port=57485\n")

            ports = hermes._desktop_ports_from_log(log_path)
            check("Latest Desktop readiness port is preferred", ports[:2] == [57485, 62353], str(ports))

            calls = []

            def fake_test(self, verify_ws=True):
                calls.append({
                    "baseUrl": self.base_url,
                    "tcpHost": self.tcp_host or "",
                    "tcpPort": self.tcp_port or "",
                    "hostHeader": self.host_header or "",
                    "verifyWs": verify_ws,
                })
                ok = self.base_url == "http://127.0.0.1:57485" and self.tcp_host == "127.0.0.2" and int(self.tcp_port or 0) == 57485
                return {
                    "ok": ok,
                    "chatReady": ok,
                    "websocketOk": ok,
                    "authRequired": False,
                    "version": "test",
                    "tcpHost": self.tcp_host or "",
                    "tcpPort": self.tcp_port or "",
                    "hostHeader": self.host_header or "",
                    "logicalUrl": self._logical_url("/"),
                    "connectUrl": self._connect_url("/"),
                    "error": "" if ok else "not this route",
                }

            hermes.HermesDesktopBackendClient.test = fake_test
            hermes._loopback_listener_ports = lambda: []
            hermes.HermesDesktopBackendClient._running_in_docker = staticmethod(lambda: False)

            result = hermes.discover_desktop_backend(
                hermes_home=root,
                desktop_tcp_host="127.0.0.2",
                desktop_tcp_port="62354",
                timeout_sec=1,
            )
            check("Discovery finds Desktop from readiness log", result.get("found"), result.get("error", ""))
            check("Discovery connects through current Desktop port", result.get("ok"), str(result))
            check("Stale configured TCP port is bypassed", result.get("desktopTcpPort") == 57485, str(result))
            check("Configured route host is preserved", result.get("desktopTcpHost") == "127.0.0.2", str(result))
            check("Logical Desktop URL stays loopback", result.get("desktopUrl") == "http://127.0.0.1:57485", str(result))
            check("Current-port fallback was attempted", any(c["tcpHost"] == "127.0.0.2" and c["tcpPort"] == 57485 for c in calls), str(calls))

            hermes.HermesDesktopBackendClient._running_in_docker = staticmethod(lambda: True)
            os.environ["VO_HERMES_DESKTOP_DOCKER_HOST"] = "docker-host.test"
            client = hermes.HermesDesktopBackendClient(base_url="http://127.0.0.1:57485")
            check("Docker loopback URLs get a physical route host", client.tcp_host == "docker-host.test", client.tcp_host or "")
            check("Docker route keeps the Desktop URL port", client.tcp_port == 57485, str(client.tcp_port))
            check("Docker route keeps loopback Host identity", client.host_header == "127.0.0.1:57485", client.host_header or "")
    finally:
        hermes.HermesDesktopBackendClient.test = old_test
        hermes._loopback_listener_ports = old_listener_ports
        hermes.HermesDesktopBackendClient._running_in_docker = old_running_in_docker
        os.environ.pop("VO_HERMES_DESKTOP_DOCKER_HOST", None)

    print("\n  Hermes Desktop discovery: all checks passed")


if __name__ == "__main__":
    main()
