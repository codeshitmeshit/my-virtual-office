"""Manual completion of missing Human Resources Agent introductions."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from services.hr_directory import (
    HRConversationPort,
    HRIntroductionSummarizer,
    HRIntroductionWorkflow,
    HRSummarizationPort,
    INELIGIBLE_AVAILABILITY,
)
from services.hr_repository import AgentRecord, HRRepository


INTRODUCTION_REQUEST_MESSAGE = (
    "请介绍你的身份、主要职责、擅长处理的工作，以及其他 Agent 在什么情况下适合与你协作。"
    "请只描述你真实具备的能力，不要推测或虚构。"
)


def introduction_request_message(ai_id: str) -> str:
    context = {
        "schemaVersion": 1,
        "requestType": "vo.hr.agent_introduction",
        "agentAiId": ai_id,
    }
    response = {
        "schemaVersion": 1,
        "agentAiId": ai_id,
        "identity": "<self-described identity>",
        "responsibilities": ["<responsibility>"],
        "strengths": ["<strength>"],
        "collaborationScenarios": ["<when another Agent should collaborate with you>"],
    }
    return (
        f"{INTRODUCTION_REQUEST_MESSAGE}\n\n"
        f"请求上下文（JSON）：\n{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "请优先只返回一个 JSON 对象，字段和类型严格参考以下模板；"
        "没有内容的数组请返回 []，不要添加其他字段或 Markdown 代码块：\n"
        f"{json.dumps(response, ensure_ascii=False, separators=(',', ':'))}\n"
        "如果当前运行环境确实无法输出合法 JSON，可以改用清晰的自然语言回答；"
        "系统仍会保留原始回答并交由 HR 总结。"
    )


class HRInformationCompletionValidationError(ValueError):
    code = "hr_information_completion_validation_failed"


@dataclass(frozen=True, slots=True)
class HRInformationCompletionItem:
    ai_id: str
    status: str
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class HRInformationCompletionResult:
    available: int
    missing: int
    published: int
    no_response: int
    failed: int
    items: tuple[HRInformationCompletionItem, ...]


@dataclass(frozen=True, slots=True)
class HRInformationCompletionReceipt:
    command_id: str
    command: str
    accepted: bool


class CallableHRInformationConversation(HRConversationPort, HRSummarizationPort):
    """Small injected adapter for office-mediated Agent and HR calls."""

    def __init__(
        self,
        ask_agent: Callable[[str, str, str, float], str | None],
        ask_hr: Callable[[str, str, float], str | None],
    ):
        if not callable(ask_agent) or not callable(ask_hr):
            raise HRInformationCompletionValidationError("conversation callbacks are required")
        self._ask_agent = ask_agent
        self._ask_hr = ask_hr

    def ask_agent_as_hr(
        self,
        target_ai_id: str,
        message: str,
        conversation_key: str,
        timeout_seconds: float,
    ) -> str | None:
        return self._ask_agent(target_ai_id, message, conversation_key, timeout_seconds)

    def ask_hr(
        self,
        prompt: str,
        conversation_key: str,
        timeout_seconds: float,
    ) -> str | None:
        return self._ask_hr(prompt, conversation_key, timeout_seconds)


class HRInformationCompletionService:
    """Ask only available Agents whose supported introduction is still missing."""

    def __init__(
        self,
        repository: HRRepository,
        conversation: CallableHRInformationConversation,
        *,
        max_workers: int = 2,
        timeout_seconds: float = 30.0,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ):
        if not isinstance(repository, HRRepository):
            raise HRInformationCompletionValidationError("repository must be an HRRepository")
        if not isinstance(conversation, CallableHRInformationConversation):
            raise HRInformationCompletionValidationError("conversation adapter is invalid")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 16:
            raise HRInformationCompletionValidationError("max_workers must be between 1 and 16")
        if not callable(new_id):
            raise HRInformationCompletionValidationError("new_id is required")
        self._repository = repository
        self._workflow = HRIntroductionWorkflow(
            repository,
            conversation,
            claim_token_factory=lambda ai_id: f"hr-info-{new_id()}-{ai_id}",
            timeout_seconds=timeout_seconds,
            claim_lease_seconds=min(600, max(31, int(timeout_seconds) + 30)),
        )
        self._summarizer = HRIntroductionSummarizer(
            repository,
            conversation,
            timeout_seconds=timeout_seconds,
        )
        self._max_workers = max_workers
        self._new_id = new_id

    def _all_agents(self) -> tuple[AgentRecord, ...]:
        items: list[AgentRecord] = []
        cursor = None
        while True:
            page = self._repository.list_agents(limit=100, cursor=cursor)
            items.extend(page.items)
            if page.next_cursor is None:
                return tuple(items)
            cursor = page.next_cursor

    @staticmethod
    def _available(agent: AgentRecord) -> bool:
        return (
            agent.ai_id != "hr"
            and agent.status == "active"
            and agent.availability not in INELIGIBLE_AVAILABILITY
        )

    def _missing(self, agent: AgentRecord) -> bool:
        introduction = self._repository.get_current_introduction(agent.ai_id)
        return introduction is None or not introduction.introduction.strip()

    def _complete_one(self, ai_id: str) -> HRInformationCompletionItem:
        current = self._repository.get_current_introduction(ai_id)
        if current is None or current.state not in {"response_received", "published"}:
            request = self._workflow.process(
                (ai_id,),
                message=introduction_request_message(ai_id),
            )[0]
            if request.status not in {"response_received", "already_complete"}:
                return HRInformationCompletionItem(ai_id, request.status, request.error_code)
            current = self._repository.get_current_introduction(ai_id)
        if current is None:
            return HRInformationCompletionItem(ai_id, "failed", "hr_introduction_missing")
        summary = self._summarizer.summarize(ai_id, expected_version=current.version)
        return HRInformationCompletionItem(ai_id, summary.status, summary.error_code)

    def complete_missing(self) -> HRInformationCompletionResult:
        available = tuple(agent for agent in self._all_agents() if self._available(agent))
        missing = tuple(agent for agent in available if self._missing(agent))
        if not missing:
            return HRInformationCompletionResult(len(available), 0, 0, 0, 0, ())
        items: list[HRInformationCompletionItem] = []
        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(missing)),
            thread_name_prefix="hr-information",
        ) as executor:
            futures = {executor.submit(self._complete_one, agent.ai_id): agent.ai_id for agent in missing}
            for future in as_completed(futures):
                ai_id = futures[future]
                try:
                    items.append(future.result())
                except Exception as exc:
                    items.append(
                        HRInformationCompletionItem(
                            ai_id,
                            "failed",
                            str(getattr(exc, "code", "hr_information_completion_failed")),
                        )
                    )
        items.sort(key=lambda item: item.ai_id)
        published = sum(item.status in {"published", "already_published"} for item in items)
        no_response = sum(item.status == "no_response" for item in items)
        failed = sum(item.status == "failed" for item in items)
        return HRInformationCompletionResult(
            len(available), len(missing), published, no_response, failed, tuple(items)
        )

    def record_activity(self, command_id: str, result: HRInformationCompletionResult) -> None:
        self._repository.append_hr_activity(
            activity_id=self._new_id(),
            ai_id=None,
            action="complete_information",
            status="failed" if result.failed else "complete",
            message=(
                f"available={result.available}, missing={result.missing}, "
                f"published={result.published}, no_response={result.no_response}"
            ),
            context={
                "available": result.available,
                "missing": result.missing,
                "published": result.published,
                "noResponse": result.no_response,
                "failed": result.failed,
            },
            occurrence_key=f"hr-information-completion:{command_id}:complete",
        )

    def record_failure(self, command_id: str, exc: Exception) -> None:
        self._repository.append_hr_activity(
            activity_id=self._new_id(),
            ai_id=None,
            action="complete_information",
            status="failed",
            error=str(getattr(exc, "code", "hr_information_completion_failed")),
            occurrence_key=f"hr-information-completion:{command_id}:failed",
        )


class HRInformationCompletionCommands:
    """Queue one completion run at a time so HTTP never waits for Agent calls."""

    def __init__(
        self,
        service: HRInformationCompletionService,
        *,
        submit: Callable[[Callable[[], None]], bool] | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ):
        if not isinstance(service, HRInformationCompletionService):
            raise HRInformationCompletionValidationError("completion service is invalid")
        self._service = service
        self._submit = submit or self._thread_submit
        self._new_id = new_id
        self._lock = threading.Lock()
        self._running = False

    @staticmethod
    def _thread_submit(callback: Callable[[], None]) -> bool:
        threading.Thread(
            target=callback,
            daemon=True,
            name="hr-information-completion",
        ).start()
        return True

    def complete(self) -> HRInformationCompletionReceipt:
        command_id = self._new_id()
        with self._lock:
            if self._running:
                return HRInformationCompletionReceipt(command_id, "complete_information", False)
            self._running = True

        def run() -> None:
            try:
                result = self._service.complete_missing()
                self._service.record_activity(command_id, result)
            except Exception as exc:
                try:
                    self._service.record_failure(command_id, exc)
                except Exception:
                    pass
            finally:
                with self._lock:
                    self._running = False

        try:
            accepted = bool(self._submit(run))
        except Exception:
            accepted = False
        if not accepted:
            with self._lock:
                self._running = False
        return HRInformationCompletionReceipt(command_id, "complete_information", accepted)
