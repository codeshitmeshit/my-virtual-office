"""Shared bridge-backed prompts for the legacy project workflow pipeline."""

from __future__ import annotations

from typing import Any, Iterable

from services import business_prompt_bridge
from services.human_decision_prompt_guidance import human_decision_section


def _project_context_section(project: dict[str, Any] | None, task: dict[str, Any]) -> dict[str, Any] | None:
    if not project:
        return None
    return {
        "name": "project_context",
        "attrs": {"title": project.get("title") or project.get("name") or "Untitled Project"},
        "children": [
            {"name": "description", "value": project.get("description", "")},
            {"name": "project_tags", "value": ", ".join(project.get("tags") or [])},
            {"name": "task_tags", "value": ", ".join(task.get("tags") or [])},
            {"name": "priority", "value": task.get("priority", "medium")},
            {"name": "assignee", "value": task.get("assignee", "unassigned")},
        ],
    }


def render_workflow_project_context(project: dict[str, Any], task: dict[str, Any]) -> str:
    section = _project_context_section(project, task)
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "workflow.project_context",
            "operation": "context",
            "locale": "en-US",
            "root": "project_context",
            "sections": (section.get("children") if section else []),
            "attrs": section.get("attrs") if section else {},
        }
    )


def _acceptance_checklist_section(acceptance_checklist: Iterable[dict[str, Any]] | None) -> dict[str, Any] | None:
    items = []
    for index, item in enumerate(acceptance_checklist or [], 1):
        status = "✅ DONE" if item.get("done") else "⬜ TODO"
        items.append(
            {
                "name": "item",
                "value": item.get("text", ""),
                "attrs": {"index": index, "status": status},
            }
        )
    if not items:
        return None
    return {"name": "acceptance_checklist", "children": items, "attrs": {"complete_all": "true"}}


def _task_section(task: dict[str, Any], *, self_closing: bool = False) -> dict[str, Any]:
    if self_closing:
        return {"name": "task", "value": "", "attrs": {"title": task.get("title", "Untitled")}}
    return {
        "name": "task",
        "value": {"description": task.get("description", "No description provided.")},
        "attrs": {"title": task.get("title", "Untitled")},
    }


def _workflow_section(*, project_specific_checklist_text: bool) -> dict[str, Any]:
    checklist_phrase = "into the task checklist via checklistUpdates" if project_specific_checklist_text else "into checklistUpdates"
    return {
        "name": "workflow",
        "trusted": True,
        "children": [
            {
                "name": "step",
                "attrs": {"id": "read-checklist"},
                "trusted": True,
                "value": (
                    "First read the task and determine what content or deliverable must be produced. "
                    f"Write the task/deliverable acceptance criteria {checklist_phrase}. "
                    "The checklist is only for deliverable acceptance criteria, not a meeting action-item queue. "
                    "If the task checklist is empty, include the created acceptance criteria in checklistUpdates. "
                    "The orchestration service will persist checklistUpdates from your final response; do not call the project API to persist checklist changes yourself."
                ),
            },
            {
                "name": "step",
                "attrs": {"id": "execute-task"},
                "trusted": True,
                "value": (
                    "Execute the task. For any Virtual Office operation, first use the vo-operating-guidelines skill to detect the VO environment, "
                    "choose the correct VO skill, and follow its boundaries. If you discover an issue that requires alignment, use vo-operating-guidelines "
                    "to decide whether a formal AI meeting is appropriate; when it is, proactively request a meeting with POST "
                    "/api/projects/{projectId}/tasks/{taskId}/meeting-requests. Include urgency and resolutionPolicy in the request: "
                    "P0 uses urgency 5 with resolutionPolicy \"user_decision\"; every non-P0 meeting uses urgency 1-4 with resolutionPolicy "
                    "\"moderator_decision\" so the AI moderator decides disagreements. Do not confirm or reject meetings yourself. "
                    "Add the corresponding action items and discussion points as meeting/task context. Do not put those meeting action items or risks into the checklist or comments."
                ),
            },
            {
                "name": "step",
                "attrs": {"id": "fill-back-checklist"},
                "trusted": True,
                "value": (
                    "After executing the task, fill back the checklist in your final checklistUpdates. "
                    "Inspect every checklist item, preserve its id/text, set done=true only after concrete verification, and provide non-empty evidence. "
                    "If any item is unfinished, continue working until it is complete before finalizing."
                ),
            },
        ],
    }


def render_workflow_task_prompt(
    *,
    task: dict[str, Any],
    acceptance_checklist: Iterable[dict[str, Any]] | None,
    task_file_content: str | None = None,
    project: dict[str, Any] | None = None,
    warning_text: str,
    project_specific_checklist_text: bool,
) -> str:
    sections: list[dict[str, Any]] = [
        {"name": "assignment", "value": "Complete the assigned task fully on your own. Do NOT ask for clarification, followups, or user input.", "trusted": True},
        human_decision_section(
            "task",
            agent_id=str(task.get("executorAgentId") or task.get("assignee") or ""),
            source_id=str(task.get("id") or ""),
            project_id=str((project or {}).get("id") or ""),
        ),
    ]
    project_context = _project_context_section(project, task)
    if project_context:
        sections.append(project_context)
    sections.append(_task_section(task))
    checklist = _acceptance_checklist_section(acceptance_checklist)
    if checklist:
        sections.append(checklist)
    if task_file_content:
        sections.append({"name": "previous_work_log", "value": task_file_content})
        sections.append({"name": "continuation_rule", "value": "Continue from where you left off. Do NOT redo work that was already completed.", "trusted": True})
    sections.extend(
        [
            _workflow_section(project_specific_checklist_text=project_specific_checklist_text),
            {
                "name": "mandatory_rules",
                "trusted": True,
                "children": [
                    {"name": "rule", "value": "You MUST use tools (read, edit, exec, browser) to make REAL changes to actual files. Text-only responses WILL BE REJECTED.", "attrs": {"id": "real-changes"}, "trusted": True},
                    {"name": "rule", "value": "Read the relevant source files FIRST to understand the codebase before making changes.", "attrs": {"id": "read-first"}, "trusted": True},
                    {"name": "rule", "value": "Use the edit tool to modify files. Use exec to run commands, test, or verify. After making changes, verify them yourself — run the app, check the output, confirm it works.", "attrs": {"id": "edit-and-verify"}, "trusted": True},
                    {"name": "rule", "value": "Use the browser tool to visually verify UI changes on the running app/site if applicable.", "attrs": {"id": "visual-verification"}, "trusted": True},
                    {"name": "rule", "value": "In your final report, list EVERY file you modified and what you changed.", "attrs": {"id": "report-files"}, "trusted": True},
                ],
            },
            {"name": "review_notice", "value": "A reviewer will independently verify your work by reading the actual files and browsing the app. If no real file changes are found, ALL items will be marked DID_NOT_PASS.", "trusted": True},
            {"name": "warning", "value": warning_text, "trusted": True},
        ]
    )
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "workflow.task",
            "operation": "execute",
            "locale": "en-US",
            "root": "project_task_prompt",
            "target": {"taskTitle": task.get("title", "Untitled")},
            "sections": sections,
            "output": {
                "checklist_updates": "In your final response include checklistUpdates as JSON: an array of {id, text, done, evidence}. checklistUpdates is REQUIRED for regular tasks and must include every acceptance checklist item, preserving existing ids. Set done=true only for checklist items you actually verified as complete, and write concrete evidence that names the delivered content, file, result, or verification. Include meetingDiscussionPoints as JSON when there are meeting conclusions, risks, or discussion notes for the task."
            },
        }
    )


def render_workflow_review_prompt(
    *,
    task: dict[str, Any],
    checklist_items_text: str,
    visual_steps: str,
    pass_line: str,
    critical_line: str,
    project: dict[str, Any] | None = None,
) -> str:
    sections: list[dict[str, Any]] = []
    project_context = _project_context_section(project, task)
    if project_context:
        sections.append(project_context)
    sections.extend(
        [
            _task_section(task, self_closing=True),
            {"name": "review_goal", "value": "You must INDEPENDENTLY VERIFY each checklist item. Do NOT trust your previous claims — verify by actually checking.", "trusted": True},
            {
                "name": "mandatory_review_steps",
                "trusted": True,
                "children": [
                    {"name": "step", "value": "Use the read tool to open the actual source files that were supposed to be modified. Confirm the changes exist in the code.", "attrs": {"id": "read-files"}, "trusted": True},
                    {"name": "step", "value": "Use exec to run any tests, linters, or verification commands.", "attrs": {"id": "verify-commands"}, "trusted": True},
                    {"name": "step", "value": visual_steps.strip(), "attrs": {"id": "visual-review"}, "trusted": True},
                ],
            },
            {
                "name": "review_statuses",
                "trusted": True,
                "children": [
                    {"name": "status", "value": pass_line, "attrs": {"name": "PASS"}, "trusted": True},
                    {"name": "status", "value": "Partially implemented but has issues you can identify in the code.", "attrs": {"name": "NEEDS_MORE_WORK"}, "trusted": True},
                    {"name": "status", "value": "No real changes found in files, or changes do not work.", "attrs": {"name": "DID_NOT_PASS"}, "trusted": True},
                    {"name": "status", "value": "ONLY if the item truly cannot be judged by an agent after using tools, such as a subjective product/design decision, required human sign-off, unavailable external system access that only the user can provide, or a genuinely destructive/approval-gated action. Do NOT use REQUIRES_USER_REVIEW for ordinary coding uncertainty, incomplete implementation, missing evidence, failed verification, or because one item previously needed rework. In those cases you MUST use NEEDS_MORE_WORK or DID_NOT_PASS.", "attrs": {"name": "REQUIRES_USER_REVIEW"}, "trusted": True},
                ],
            },
            {"name": "judgment_rule", "value": "If you can read the code, run tests, inspect outputs, or otherwise verify the implementation yourself, you MUST make your own judgment and use PASS, NEEDS_MORE_WORK, or DID_NOT_PASS.", "trusted": True},
            {"name": "checklist_items_to_review", "value": checklist_items_text},
            {"name": "critical_rule", "value": critical_line, "trusted": True},
        ]
    )
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "workflow.review",
            "operation": "verify",
            "locale": "en-US",
            "root": "project_review_prompt",
            "target": {"taskTitle": task.get("title", "Untitled")},
            "sections": sections,
            "output": {
                "response_format": "Respond in this EXACT format (one line per item, after your verification):\nREVIEW_ITEM_1: <status>\nREVIEW_ITEM_2: <status>\n..."
            },
        }
    )


def render_workflow_rework_prompt(
    *,
    task: dict[str, Any],
    failed_items_text: str,
    task_file_content: str | None = None,
) -> str:
    sections: list[dict[str, Any]] = [
        _task_section(task, self_closing=True),
        {"name": "rework_goal", "value": "The following checklist items did NOT pass review. Fix them yourself. Do not ask for help.", "trusted": True},
        {"name": "items_that_need_work", "value": failed_items_text},
    ]
    if task_file_content:
        sections.append({"name": "previous_work_log", "value": task_file_content})
    sections.extend(
        [
            {
                "name": "mandatory_rework_rules",
                "trusted": True,
                "children": [
                    {"name": "rule", "value": "You MUST use tools (read, edit, exec, browser) to make REAL changes to actual files.", "attrs": {"id": "real-changes"}, "trusted": True},
                    {"name": "rule", "value": "Read the relevant files first, then use edit to fix the issues.", "attrs": {"id": "read-and-edit"}, "trusted": True},
                    {"name": "rule", "value": "After fixing, verify your changes work — use exec to test and browser to visually confirm UI changes.", "attrs": {"id": "verify"}, "trusted": True},
                    {"name": "rule", "value": "If you open any browser/session during rework or verification, you MUST close it before finishing your response. Do not leave browser instances running.", "attrs": {"id": "close-browser"}, "trusted": True},
                    {"name": "rule", "value": "Only fix the items listed above. Do NOT redo work that already passed.", "attrs": {"id": "scope"}, "trusted": True},
                    {"name": "rule", "value": "In your report, list EVERY file you modified and what you changed.", "attrs": {"id": "report-files"}, "trusted": True},
                ],
            },
            {"name": "review_notice", "value": "A reviewer will independently verify your fixes by reading the actual files and browsing the app.", "trusted": True},
        ]
    )
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "workflow.rework",
            "operation": "fix",
            "locale": "en-US",
            "root": "project_rework_prompt",
            "target": {"taskTitle": task.get("title", "Untitled")},
            "sections": sections,
            "output": {
                "checklist_updates": "For every item above, include checklistUpdates with the same id/text and done=true only after you have concrete evidence."
            },
        }
    )


__all__ = [
    "render_workflow_project_context",
    "render_workflow_review_prompt",
    "render_workflow_rework_prompt",
    "render_workflow_task_prompt",
]
