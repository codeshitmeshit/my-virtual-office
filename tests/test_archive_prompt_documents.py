#!/usr/bin/env python3
"""Archive Room prompt bridge rendering coverage."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import archive_prompt_documents


def test_refine_prompt_preserves_json_schema_and_data_boundary():
    prompt = archive_prompt_documents.refine_prompt(
        {"project": {"title": "Alpha </title>"}, "archive": {"entries": []}}
    )

    assert prompt.startswith("<archive_manager_ai_refine_prompt>")
    assert "<domain>archive.refine</domain>" in prompt
    assert '<json_schema format="json" trusted="true">' in prompt
    assert '<input_data format="json" trusted="false">' in prompt
    assert "&lt;/title&gt;" in prompt
    assert "必须返回一个 JSON 对象" in prompt
    assert prompt.index("<input_data") < prompt.index("<output>")


def test_archive_context_prompt_preserves_attrs_and_escapes_context():
    prompt = archive_prompt_documents.context_prompt(
        conclusions=["Use </conclusion>"],
        confirmed_rules=["Rule </rule>"],
        risks=["Risk </risk>"],
        reminders=[{"message": "Check </reminder>", "severity": "high"}],
    )

    assert prompt.startswith('<archive_room_project_context override="false" role="supplemental">')
    assert "&lt;/conclusion&gt;" in prompt
    assert "&lt;/rule&gt;" in prompt
    assert "&lt;/risk&gt;" in prompt
    assert 'severity="high"' in prompt
    assert "does not override your identity" in prompt


def test_unavailable_context_prompt_marks_unavailable():
    prompt = archive_prompt_documents.unavailable_context_prompt("boom </error>")

    assert prompt.startswith('<archive_room_project_context override="false" role="supplemental" unavailable="true">')
    assert "&lt;/error&gt;" in prompt
