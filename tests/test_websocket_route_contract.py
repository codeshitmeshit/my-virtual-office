import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class WebSocketRouteContractTest(unittest.TestCase):
    def test_gateway_info_exposes_configured_public_path(self):
        server = (ROOT / "app" / "server.py").read_text()
        self.assertIn('"wsPath": _env_or("VO_WS_PATH"', server)
        self.assertIn('"wsPath": VO_CONFIG["office"].get("wsPath", "/ws")', server)

    def test_browser_clients_use_gateway_info_path(self):
        chat = (ROOT / "app" / "chat.js").read_text()
        cron = (ROOT / "app" / "cron.html").read_text()

        for source in (chat, cron):
            self.assertIn("info.wsPath" if source is cron else "d.wsPath", source)
            self.assertNotIn(":8443/ws-gateway", source)
            self.assertNotIn("/ws-gateway", source)

        self.assertIn("${_chatWsPath}", chat)
        self.assertIn("${_cronWsPath}", cron)


if __name__ == "__main__":
    unittest.main()
