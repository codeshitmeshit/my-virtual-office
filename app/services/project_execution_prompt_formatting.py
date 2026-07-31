"""Prompt rendering helpers for project execution Agents."""

from __future__ import annotations

from typing import Any

from services import business_prompt_bridge


def render_project_execution_prompt(
    *,
    project: dict[str, Any],
    task: dict[str, Any],
    attempt: dict[str, Any],
    workspace: str,
    checklist_text: str,
    rework_feedback: str,
    artifact_run_instruction: str = "",
    final_result_instructions: str = "",
    prior_stage_context: str = "",
    unfinished_checklist_focus: str = "",
    meeting_action_block: str = "",
    archive_context: str = "",
) -> str:
    """Render the project execution prompt through the shared bridge formatter."""

    project_id = project.get("id", "")
    task_id = task.get("id", "")
    raw_sections = [
        artifact_run_instruction,
        final_result_instructions,
        unfinished_checklist_focus,
        prior_stage_context,
        meeting_action_block,
        archive_context,
    ]
    sections: list[dict[str, Any]] = [
        {"name": "role", "value": "You are the execution agent for a Virtual Office project task.", "trusted": True},
        {"name": "workspace", "value": workspace},
        {"name": "boundary", "value": "Work only inside this workspace. Do not review or mark the task complete.", "trusted": True},
        {
            "name": "workflow",
            "trusted": True,
            "children": [
                {
                    "name": "step",
                    "attrs": {"id": "read-checklist"},
                    "value": (
                        "Read the task and follow the acceptance checklist shown below. "
                        "Write the task/deliverable acceptance criteria into the task checklist via checklistUpdates. "
                        "Treat the checklist as the task's deliverable acceptance criteria, not a meeting action-item queue. "
                        "Do not redefine the checklist unless the checklist is explicitly empty; if it is empty, include concrete acceptance criteria in checklistUpdates. "
                        "The orchestration service will persist checklistUpdates from your final response; do not call the project API to persist checklist changes yourself."
                    ),
                    "trusted": True,
                },
                {
                    "name": "step",
                    "attrs": {"id": "execute-task"},
                    "value": (
                        "Execute the task. For any Virtual Office operation, first use the vo-operating-guidelines skill to detect the VO environment, "
                        "choose the correct VO skill, and follow its boundaries. If you discover an issue that requires alignment, use vo-operating-guidelines "
                        "to decide whether a formal AI meeting is appropriate; when it is, proactively request a meeting with POST "
                        f"/api/projects/{project_id}/tasks/{task_id}/meeting-requests. Include urgency and resolutionPolicy in the request: "
                        "P0 uses urgency 5 with resolutionPolicy \"user_decision\"; every non-P0 meeting uses urgency 1-4 with resolutionPolicy "
                        "\"moderator_decision\" so the AI moderator decides disagreements. Do not confirm or reject meetings yourself. "
                        "Add the corresponding action items and discussion points as meeting/task context. Do not put those meeting action items or risks into the checklist or comments."
                    ),
                    "trusted": True,
                },
                {
                    "name": "step",
                    "attrs": {"id": "fill-back-checklist"},
                    "value": (
                        "After executing the task, fill back the checklist in your final checklistUpdates. "
                        "Inspect every checklist item, preserve its id/text, set done=true only after concrete verification, and provide non-empty evidence. "
                        "If any item is unfinished, continue working until it is complete before finalizing."
                    ),
                    "trusted": True,
                },
            ],
        },
    ]
    sections.extend(
        {"format": "raw", "trusted": True, "value": value}
        for value in raw_sections[:2]
        if value
    )
    sections.append(
        {
            "name": "task_context",
            "children": [
                {
                    "name": "project",
                    "value": project.get("description", ""),
                    "attrs": {"id": project_id, "title": project.get("title", "")},
                },
                {
                    "name": "task",
                    "value": task.get("description", ""),
                    "attrs": {"id": task_id, "title": task.get("title", ""), "attempt": attempt.get("id", "")},
                },
                {"name": "rework_feedback", "value": rework_feedback},
                {"name": "checklist", "value": checklist_text},
            ],
        }
    )
    sections.extend(
        {"format": "raw", "trusted": True, "value": value}
        for value in raw_sections[2:]
        if value
    )
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.execution",
            "operation": "run",
            "locale": "en-US",
            "root": "project_execution_prompt",
            "target": {"projectId": project_id, "taskId": task_id, "attemptId": attempt.get("id", "")},
            "sections": sections,
            "output": {
                "final_response": {
                    "summary": "First output a human-visible Markdown summary under 1200 characters. It may include short bullets for changed files, tests run, and remaining risks.",
                    "json_block": "Then output exactly one fenced ```json block containing a single object. For a regular task, checklistUpdates is REQUIRED and must be a non-empty array; it must include every acceptance checklist item with its final status. meetingDiscussionPoints and tests are optional.",
                    "json_rules": "Do not print raw JSON outside the fenced json block. Do not put escaped JSON inside the Markdown summary. tests must be an array of short strings only, each under 180 characters. Do not put full logs, full API responses, raw tool output, source material, or nested objects in tests.",
                    "checklist_updates": "checklistUpdates is an array of {id, text, done, evidence}; preserve the checklist IDs shown below. If no checklist was supplied, create concrete acceptance criteria with stable short IDs. Set done=true only for items you actually verified as complete, and write concrete evidence that names the delivered content, file, result, or verification.",
                    "example": '{"checklistUpdates":[{"id":"deliverable","text":"Produce the requested deliverable","done":true,"evidence":"Verified output"}],"tests":["verification passed"]}',
                    "meeting_discussion_points": "meetingDiscussionPoints is an array of {kind, title, text, meetingId, requestId} for meeting conclusions, risks, and discussion notes that belong in the task details.",
                }
            },
        }
    ) + "\n"


def render_checklist_planning_prompt(
    *,
    project: dict[str, Any],
    task: dict[str, Any],
    attempt: dict[str, Any],
    workspace: str,
) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.checklist",
            "operation": "plan",
            "locale": "en-US",
            "root": "checklist_planning_prompt",
            "target": {"projectId": project.get("id", ""), "taskId": task.get("id", ""), "attemptId": attempt.get("id")},
            "sections": [
                {"name": "role", "value": "You are preparing the acceptance checklist for a Virtual Office project task.", "trusted": True},
                {"name": "workspace", "value": workspace},
                {"name": "scope", "value": "Do not execute the task yet. Do not create deliverable files. Only analyze the task and define concrete acceptance criteria.", "trusted": True},
                {"name": "checklist_rules", "value": "Use stable short IDs. Set done=false for every item. Keep checklist items focused on deliverable acceptance only; do not include meeting action items, process notes, or generic reminders. Create enough items to verify the requested deliverable, normally 2-5.", "trusted": True},
                {
                    "name": "project",
                    "value": project.get("description", ""),
                    "attrs": {"id": project.get("id", ""), "title": project.get("title", "")},
                },
                {
                    "name": "task",
                    "value": task.get("description", ""),
                    "attrs": {"id": task.get("id", ""), "title": task.get("title", ""), "attempt": attempt.get("id")},
                },
            ],
            "output": "Return a short Markdown note followed by exactly one fenced ```json block containing a single object. The object must contain checklistUpdates: an array of {id, text, done, evidence}.",
        }
    ) + "\n"


def render_artifact_run_instruction(*, run_directory: str) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.artifact_run",
            "operation": "instruction",
            "locale": "en-US",
            "root": "artifact_run_instruction",
            "sections": [
                {"name": "run_directory", "value": f"{run_directory}/"},
                {"name": "rule", "value": "This is a reusable/re-entrant project run. Write new Markdown artifacts under the run directory; do not overwrite artifacts from earlier runs.", "trusted": True},
            ],
        }
    ) + "\n"


def render_task_final_result_fallback() -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.task_final_result",
            "operation": "fallback_requirement",
            "locale": "en-US",
            "root": "task_final_result_requirement",
            "sections": [
                {"name": "rule", "value": "Include a concise final conclusion, changed files/artifacts, tests, risks, and notes for later stages.", "trusted": True},
            ],
        }
    )


def render_unfinished_checklist_focus(items: str) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.unfinished_checklist",
            "operation": "focus",
            "locale": "en-US",
            "root": "unfinished_checklist_focus",
            "sections": [
                {"name": "label", "value": "UNFINISHED CHECKLIST FOCUS", "trusted": True},
                {
                    "name": "rule",
                    "value": "The previous attempt/rework did not satisfy these acceptance items. Complete these items first, produce concrete evidence for each one, and include matching checklistUpdates with done=true only after verification.",
                    "trusted": True,
                },
                {"name": "items", "value": items},
            ],
        }
    )


def render_meeting_action_phase(*, pending_items: str, meeting_decision_context: str) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.meeting_action",
            "operation": "phase",
            "locale": "en-US",
            "root": "meeting_action_item_phase",
            "sections": [
                {
                    "name": "rules",
                    "trusted": True,
                    "value": [
                        "Complete ONLY the meeting-created action items listed below. Do not continue the original task yet.",
                        "After completing them, return a concise summary of what was done and any remaining risk.",
                    ],
                },
                {"name": "pending_items", "value": pending_items},
                {"name": "meeting_decision_context", "value": meeting_decision_context},
            ],
        }
    )


def render_project_execution_review_prompt(
    *,
    project: dict[str, Any],
    task: dict[str, Any],
    attempt: dict[str, Any],
    prior_user_feedback: str,
    checklist_text: str,
    executor_summary: str,
    changed_files: str,
    test_evidence: str,
    provider_status: str,
    error: str,
) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "project.execution_review",
            "operation": "review",
            "locale": "en-US",
            "root": "project_execution_review_prompt",
            "target": {"taskId": task.get("id", ""), "attemptId": attempt.get("id")},
            "sections": [
                {"name": "role", "value": "You are the independent read-only reviewer for a Virtual Office Project Execution task.", "trusted": True},
                {
                    "name": "review_rules",
                    "value": (
                        "Review the evidence below first. If your runtime exposes a workspace, it is the authorized task workspace "
                        "and may be inspected read-only to verify the evidence. Do not modify files, run write-capable tools, or mark the task done. "
                        "Treat earlier rework feedback as historical context that may already be stale. The checklist contains deliverable acceptance criteria only; "
                        "meeting action items and risks are context, not acceptance checklist items."
                    ),
                    "trusted": True,
                },
                {
                    "name": "project",
                    "value": project.get("description", ""),
                    "attrs": {"title": project.get("title", "")},
                },
                {
                    "name": "task",
                    "value": task.get("description", ""),
                    "attrs": {"title": task.get("title", ""), "attempt": attempt.get("id")},
                },
                {"name": "prior_user_feedback", "value": prior_user_feedback},
                {"name": "checklist", "value": checklist_text},
                {"name": "executor_summary", "value": f"EXECUTOR SUMMARY\n{executor_summary}"},
                {"name": "changed_files", "value": changed_files},
                {"name": "test_evidence", "value": test_evidence},
                {"name": "provider_status", "value": provider_status},
                {"name": "error", "value": error},
            ],
            "output": "Return one JSON object with fields: status, summary, rationale, items. status must be one of: pass, needs_more_work, blocked.",
        }
    ) + "\n"


__all__ = [
    "render_artifact_run_instruction",
    "render_checklist_planning_prompt",
    "render_meeting_action_phase",
    "render_project_execution_prompt",
    "render_project_execution_review_prompt",
    "render_task_final_result_fallback",
    "render_unfinished_checklist_focus",
]
