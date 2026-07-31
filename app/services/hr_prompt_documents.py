"""Shared XML prompt documents for Human Resources Agent interactions."""

from __future__ import annotations

from typing import Mapping

from services import business_prompt_bridge


DAILY_REPORT_HISTORY_SCOPE_RULES = (
    "不要只根据当前这条请求或当前对话上下文作答。",
    "请主动回顾你自己在当日可访问的所有会话、任务执行记录、产出记录和相关日志。",
    "如果无法访问自己的历史会话或任务记录，请在 selfAssessment 或 requestedHelp 中明确说明限制。",
    "不要据此猜测或虚构工作。",
)


def _strict_json_output(schema: Mapping[str, object], *, fallback: str) -> Mapping[str, object]:
    return {
        "format": "json_object_preferred",
        "rules": [
            "请优先只返回一个 JSON 对象。",
            "字段和类型严格参考 schema。",
            "没有内容的数组请返回 []。",
            "不要添加其他字段、Markdown 代码块、问候语或解释。",
        ],
        "schema": {"format": "json", "value": schema},
        "fallback": fallback,
    }


def daily_report_request_document(base_message: str, *, ai_id: str, local_date: str) -> str:
    """Render the HR-to-Agent daily report request as a safe XML document."""
    request_context = {
        "schemaVersion": 1,
        "requestType": "vo.hr.daily_report",
        "agentAiId": ai_id,
        "localDate": local_date,
    }
    response_schema = {
        "schemaVersion": 1,
        "agentAiId": ai_id,
        "localDate": local_date,
        "completedWork": [],
        "relatedProjectsOrTasks": [
            {"type": "<project-or-task>", "id": "<stable-id>", "title": "<title>"}
        ],
        "artifacts": [
            {"id": "<artifact-id>", "name": "<artifact-name>", "type": "<artifact-type>"}
        ],
        "blockers": [],
        "requestedHelp": [],
        "selfAssessment": "<简要自评：说明今天的完成质量、信心、风险或需要改进之处>",
    }
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "hr.daily_report",
            "operation": "request",
            "locale": "zh-CN",
            "target": {"agentAiId": ai_id},
            "sections": [
                {"name": "role", "value": "HR 请求 Agent 提交当日日报。", "trusted": True},
                {"name": "task", "value": base_message},
                {
                    "name": "scope",
                    "trusted": True,
                    "value": {
                        "title": "日报取数范围",
                        "rules": list(DAILY_REPORT_HISTORY_SCOPE_RULES),
                    },
                },
                {"name": "request_context", "format": "json", "value": request_context},
            ],
            "output": _strict_json_output(
                response_schema,
                fallback=(
                    "如果当前运行环境确实无法输出合法 JSON，可以改用清晰的自然语言回答；"
                    "系统会保留原始回答供 HR 评估。不要虚构未发生的工作。"
                ),
            ),
        },
    )


def agent_introduction_request_document(ai_id: str) -> str:
    """Render the HR-to-Agent self-introduction request as a safe XML document."""
    request_context = {
        "schemaVersion": 1,
        "requestType": "vo.hr.agent_introduction",
        "agentAiId": ai_id,
    }
    response_schema = {
        "schemaVersion": 1,
        "agentAiId": ai_id,
        "identity": "<self-described identity>",
        "responsibilities": ["<responsibility>"],
        "strengths": ["<strength>"],
        "collaborationScenarios": ["<when another Agent should collaborate with you>"],
    }
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "hr.agent_introduction",
            "operation": "request",
            "locale": "zh-CN",
            "target": {"agentAiId": ai_id},
            "sections": [
                {"name": "role", "value": "HR 请求 Agent 提交身份和协作能力介绍。", "trusted": True},
                {
                    "name": "task",
                    "trusted": True,
                    "value": (
                        "请介绍你的身份、主要职责、擅长处理的工作，以及其他 Agent "
                        "在什么情况下适合与你协作。"
                    ),
                },
                {
                    "name": "rules",
                    "trusted": True,
                    "value": ["请只描述你真实具备的能力。", "不要推测或虚构。"],
                },
                {"name": "request_context", "format": "json", "value": request_context},
            ],
            "output": _strict_json_output(
                response_schema,
                fallback=(
                    "如果当前运行环境确实无法输出合法 JSON，可以改用清晰的自然语言回答；"
                    "系统仍会保留原始回答并交由 HR 总结。"
                ),
            ),
        },
    )
