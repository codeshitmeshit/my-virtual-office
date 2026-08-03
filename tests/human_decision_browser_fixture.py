"""Isolated HTTP fixture for manual/in-app-browser decision-center acceptance."""

from __future__ import annotations

import os
import sys
import tempfile
from http.server import ThreadingHTTPServer


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

FIXTURE_STATE = tempfile.TemporaryDirectory(prefix="vo-human-decision-browser-")
os.environ["VO_STATUS_DIR"] = FIXTURE_STATE.name

import server  # noqa: E402


class BrowserFixtureDelivery:
    """Keep browser acceptance deterministic and free of external side effects."""

    def deliver(self, _decision, **_configs):
        return {"ok": True, "status": "fixture_only", "messageId": "", "application": "fixture"}

    def update_terminal(self, _decision, _records, **_configs):
        return []


server._MANAGEMENT_TOKEN = os.environ.get("VO_BROWSER_FIXTURE_TOKEN", "browser-e2e-token")
server.HUMAN_DECISION_WORKFLOW = server.HumanDecisionWorkflow(
    store=server.HumanDecisionStore(os.path.join(FIXTURE_STATE.name, "human-decisions.json")),
    delivery=BrowserFixtureDelivery(),
    notification_config=lambda: {},
    chat_config=lambda: {},
    fallback_chat_id=lambda: "",
)


def seed() -> None:
    server.HUMAN_DECISION_WORKFLOW.create({
        "idempotencyKey": "browser-e2e:task:rollout",
        "source": {"type": "task", "id": "browser-e2e-task", "label": "正式控制面板 E2E"},
        "title": "选择正式控制面板的上线范围",
        "situation": "决策中枢已接入 VO，需要确定第一批使用范围。",
        "reason": "范围会影响验证速度和回滚风险，需要用户裁决。",
        "risk": "medium",
        "urgency": "urgent",
        "timeoutConsequence": "三次提醒后受影响分支继续等待。",
        "options": [
            {"id": "A", "label": "立即全量", "impact": "验证最快，影响范围最大。"},
            {"id": "B", "label": "分阶段灰度", "impact": "先验证关键指标，再逐步扩大。"},
            {"id": "C", "label": "仅内部试用", "impact": "风险最低，外部验证延后。"},
            {"id": "D", "label": "暂缓", "impact": "不增加风险，发布分支继续等待。"},
        ],
        "recommendation": {"optionId": "B", "reason": "兼顾真实验证和快速回滚。"},
        "taskDetail": {
            "summary": "发布嵌入 VO 控制面板的人工决策中枢。",
            "completed": ["静态 UI 评审", "状态服务", "SSE 接线"],
            "blocked": "等待上线范围",
            "context": "本 fixture 使用隔离状态目录，不访问真实飞书。",
            "nextStep": "按决策继续对应发布分支。",
        },
    })


if __name__ == "__main__":
    seed()
    port = int(os.environ.get("VO_BROWSER_FIXTURE_PORT", "4182"))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), server.OfficeHandler)
    print(f"human decision browser fixture: http://127.0.0.1:{port}", flush=True)
    httpd.serve_forever()
