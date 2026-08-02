"""Content-only views for owner-facing project completion reports."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def report_title(project: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    return str(
        report.get("title")
        or project.get("title")
        or project.get("id")
        or "项目结论"
    ).strip()


def report_summary(report: Mapping[str, Any]) -> str:
    """Read the content summary, with conclusion-only legacy compatibility."""

    return str(report.get("summary") or report.get("conclusion") or "").strip()


def report_conclusions(report: Mapping[str, Any]) -> list[str]:
    """Read content conclusions without exposing legacy lifecycle sections."""

    values: Sequence[Any] = report.get("conclusions") or report.get("keyResults") or []
    return [str(value).strip() for value in values if str(value or "").strip()]


def report_organizational_advice(report: Mapping[str, Any]) -> list[str]:
    """Read strategic advice without treating legacy execution follow-ups as advice."""

    values: Sequence[Any] = report.get("organizationalAdvice") or []
    return [str(value).strip() for value in values if str(value or "").strip()]


def render_content_markdown(
    project: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    title_level: int = 1,
) -> str:
    title_prefix = "#" * max(1, min(int(title_level), 6))
    section_prefix = "#" * max(1, min(int(title_level) + 1, 6))
    lines = [
        f"{title_prefix} {report_title(project, report)}",
        "",
        report_summary(report),
        "",
        f"{section_prefix} 核心结论",
        *(f"- {item}" for item in report_conclusions(report)),
    ]
    advice = report_organizational_advice(report)
    if advice:
        lines.extend([
            "",
            "---",
            "",
            *(f"- {item}" for item in advice),
        ])
    return "\n".join(lines).rstrip() + "\n"
