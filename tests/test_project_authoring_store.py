#!/usr/bin/env python3
"""Root-store repair, sanitization, and terminal retention tests."""

from datetime import datetime, timezone
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore
from services.project_authoring_config import ProjectAuthoringConfig
from services.project_authoring_store import (
    GRANTS_KEY,
    OUTBOX_KEY,
    RECURRENCES_KEY,
    REQUESTS_KEY,
    ProjectAuthoringRootStore,
    agent_request_view,
    management_request_view,
)
from services.project_repository import ProjectRepository


def _config(**overrides):
    values = ProjectAuthoringConfig.from_env({}).__dict__
    values.update(overrides)
    return ProjectAuthoringConfig(**values)


def _root_store(tmp_path, **config_overrides):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    return markdown, repository, ProjectAuthoringRootStore(
        repository, config=_config(**config_overrides),
    )


def test_corrupt_collections_are_repaired_and_histories_are_bounded(tmp_path):
    markdown, repository, store = _root_store(
        tmp_path, audit_history_limit=10, recurrence_history_limit=10,
    )

    def corrupt(root):
        root[REQUESTS_KEY] = {
            "request-1": {"audit": [{"n": n} for n in range(20)] + ["bad"]},
            "broken": "not-a-record",
        }
        root[GRANTS_KEY] = []
        root[RECURRENCES_KEY] = {
            "recurrence-1": {
                "audit": [{"n": n} for n in range(12)],
                "occurrenceHistory": [{"n": n} for n in range(25)] + [None],
            },
        }
        root[OUTBOX_KEY] = [None, {"id": "intent-1"}, "bad"]
        root["projectTemplateVersions"] = {"template-1": [None, {"version": 1}], "bad": {}}
        root["projectAuthoringIdempotency"] = {"valid": "request-1", "bad": []}

    repository.update_root(corrupt)
    repaired = store.snapshot()

    assert list(repaired[REQUESTS_KEY]) == ["request-1"]
    assert [item["n"] for item in repaired[REQUESTS_KEY]["request-1"]["audit"]] == list(range(10, 20))
    assert repaired[GRANTS_KEY] == {}
    assert len(repaired[RECURRENCES_KEY]["recurrence-1"]["audit"]) == 10
    assert len(repaired[RECURRENCES_KEY]["recurrence-1"]["occurrenceHistory"]) == 10
    assert repaired[OUTBOX_KEY] == [{"id": "intent-1"}]
    assert repaired["projectTemplateVersions"] == {"template-1": [{"version": 1}]}
    assert repaired["projectAuthoringIdempotency"] == {"valid": "request-1"}
    assert MarkdownProjectStore(str(tmp_path)).load_all()[OUTBOX_KEY] == [{"id": "intent-1"}]


def test_request_views_never_expose_secrets_or_cross_agent_status():
    request = {
        "id": "request-1",
        "requestingAgentId": "author-agent",
        "state": "pending",
        "revision": 2,
        "requestSecret": "plaintext",
        "requestSecretHash": "hash-1",
        "draft": {"title": "Private draft", "secret_hash": "hash-2"},
        "result": {"status": "waiting", "secretHash": "hash-3"},
    }

    management = management_request_view(request)
    agent = agent_request_view(request, requesting_agent_id="author-agent")

    assert management["draft"] == {"title": "Private draft"}
    assert "requestSecret" not in management
    assert "requestSecretHash" not in management
    assert agent == {"id": "request-1", "state": "pending", "revision": 2, "result": {"status": "waiting"}}
    assert agent_request_view(request, requesting_agent_id="different-agent") is None


def test_old_terminal_requests_compact_to_retention_tombstones(tmp_path):
    _, _, store = _root_store(tmp_path, terminal_retention_days=30)
    store.update(lambda root: root[REQUESTS_KEY].update({
        "old-confirmed": {
            "id": "old-confirmed",
            "requestingAgentId": "agent-1",
            "state": "confirmed",
            "revision": 4,
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-02T00:00:00+00:00",
            "terminalAt": "2025-01-02T00:00:00+00:00",
            "projectId": "project-1",
            "requestSecretHash": "must-disappear",
            "originalDraft": {"title": "large payload"},
            "result": {"projectId": "project-1", "secretHash": "nested"},
        },
        "recent-rejected": {
            "id": "recent-rejected", "state": "rejected",
            "terminalAt": "2025-02-20T00:00:00+00:00",
        },
        "pending": {"id": "pending", "state": "pending", "createdAt": "2024-01-01T00:00:00+00:00"},
    }))

    count = store.compact_terminal_requests(now=datetime(2025, 3, 1, tzinfo=timezone.utc))
    requests = store.snapshot()[REQUESTS_KEY]

    assert count == 1
    tombstone = requests["old-confirmed"]
    assert tombstone["tombstone"] is True
    assert tombstone["projectId"] == "project-1"
    assert tombstone["result"] == {"projectId": "project-1"}
    assert tombstone["retention"] == {
        "terminalRetentionDays": 30,
        "compactedAt": "2025-03-01T00:00:00+00:00",
    }
    assert "originalDraft" not in tombstone
    assert "requestSecretHash" not in tombstone
    assert requests["recent-rejected"].get("tombstone") is not True
    assert requests["pending"]["state"] == "pending"


def test_update_repairs_mutator_output_before_persisting(tmp_path):
    _, _, store = _root_store(tmp_path)

    result = store.update(lambda root: (
        root.update({OUTBOX_KEY: ["bad", {"id": "intent-2"}]}),
        "updated",
    )[1])

    assert result == "updated"
    assert store.snapshot()[OUTBOX_KEY] == [{"id": "intent-2"}]


def test_update_enforces_pending_and_outbox_capacities_atomically(tmp_path):
    _, _, store = _root_store(
        tmp_path, max_pending_per_agent=1, max_pending_global=2, outbox_capacity=1,
    )
    store.update(lambda root: root[REQUESTS_KEY].update({
        "request-1": {"state": "pending", "requestingAgentId": "agent-1"},
    }))

    with pytest.raises(RuntimeError) as agent_limit:
        store.update(lambda root: root[REQUESTS_KEY].update({
            "request-2": {"state": "failed", "requestingAgentId": "agent-1"},
        }))
    assert agent_limit.value.as_dict()["code"] == "project_authoring_pending_limit"
    assert agent_limit.value.as_dict()["scope"] == "agent"
    assert "request-2" not in store.snapshot()[REQUESTS_KEY]

    store.update(lambda root: root[REQUESTS_KEY].update({
        "request-2": {"state": "materializing", "requestingAgentId": "agent-2"},
    }))
    with pytest.raises(RuntimeError) as global_limit:
        store.update(lambda root: root[REQUESTS_KEY].update({
            "request-3": {"state": "pending", "requestingAgentId": "agent-3"},
        }))
    assert global_limit.value.as_dict()["scope"] == "global"

    store.update(lambda root: root[OUTBOX_KEY].append({"id": "intent-1"}))
    with pytest.raises(RuntimeError) as outbox_limit:
        store.update(lambda root: root[OUTBOX_KEY].append({"id": "intent-2"}))
    assert outbox_limit.value.as_dict()["code"] == "project_authoring_outbox_full"
    assert store.snapshot()[OUTBOX_KEY] == [{"id": "intent-1"}]


def test_failed_request_remains_recoverable_and_is_not_compacted(tmp_path):
    _, _, store = _root_store(tmp_path, terminal_retention_days=1)
    store.update(lambda root: root[REQUESTS_KEY].update({
        "retryable": {
            "state": "failed",
            "requestingAgentId": "agent-1",
            "terminalAt": "2020-01-01T00:00:00+00:00",
            "approvedSnapshot": {"title": "Retry me"},
        },
    }))

    assert store.compact_terminal_requests(now=datetime(2025, 1, 1, tzinfo=timezone.utc)) == 0
    assert store.snapshot()[REQUESTS_KEY]["retryable"]["approvedSnapshot"] == {"title": "Retry me"}
