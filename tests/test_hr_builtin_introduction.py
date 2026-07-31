"""Built-in HR self-introduction bootstrap."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_builtin_introduction import (
    HR_BUILTIN_INTRODUCTION,
    ensure_hr_builtin_introduction,
)
from services.hr_repository import HRRepository


def test_builtin_hr_introduction_creates_agent_and_published_profile(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()

    ensure_hr_builtin_introduction(repository)

    agent = repository.get_agent("hr")
    assert agent is not None
    assert agent.name == "HR"
    assert agent.agent_kind == "system"
    assert agent.availability == "available"
    introduction = repository.get_current_introduction("hr")
    assert introduction is not None
    assert introduction.state == "published"
    assert introduction.introduction == HR_BUILTIN_INTRODUCTION
    assert introduction.source == "hr-builtin"


def test_builtin_hr_introduction_does_not_overwrite_existing_profile(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    ensure_hr_builtin_introduction(repository)
    original = repository.get_current_introduction("hr")
    repository.save_introduction(
        ai_id="hr",
        state="published",
        raw_response="custom",
        introduction="Custom HR introduction.",
        source="human-edit",
        actor_id="hr",
        expected_version=original.version,
    )

    ensure_hr_builtin_introduction(repository)

    current = repository.get_current_introduction("hr")
    assert current.introduction == "Custom HR introduction."
    assert current.source == "human-edit"
