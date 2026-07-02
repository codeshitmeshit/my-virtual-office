#!/usr/bin/env python3
"""Phase 1 coverage for executable Meeting for AI foundations."""

import os
import json
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-meeting-phase1-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server


def with_meeting_store(status_dir):
    old = (server.STATUS_DIR, server.STATUS_FILE)
    server.STATUS_DIR = status_dir
    server.STATUS_FILE = os.path.join(status_dir, "virtual-office-status.json")
    return old


def restore_meeting_store(old):
    server.STATUS_DIR, server.STATUS_FILE = old


def load_scores(status_dir):
    path = os.path.join(status_dir, "project-scores.json")
    with open(path, "r") as f:
        return json.load(f)


def create_meeting(**overrides):
    body = {
        "topic": "Executable Design Review",
        "purpose": "Decide whether the meeting state machine is ready",
        "participants": ["main", "hermes-default", "codex-local"],
        "moderator": "main",
        "meetingType": "discussion",
        "maxRounds": 2,
        "context": "Phase 1 only; no AI calls.",
        "idempotencyKey": "create-review",
    }
    body.update(overrides)
    return server._handle_executable_meeting_create(body)


def test_meeting_hermes_provider_uses_meeting_conversation_id():
    old_lookup = server._office_agent_lookup
    old_chat = server._handle_hermes_chat
    calls = []

    def fake_lookup(agent_id):
        if agent_id == "hermes-default":
            return {"id": agent_id, "providerKind": "hermes", "providerAgentId": "default"}
        return old_lookup(agent_id)

    def fake_chat(body):
        calls.append(dict(body))
        return {
            "ok": True,
            "reply": json.dumps({
                "position": "meeting scoped",
                "reasoning": "uses the executable meeting conversation",
                "disagreements": [],
                "questions": [],
                "suggestedNextStep": "continue",
                "confidence": "high",
            }),
            "sessionId": "hermes-session-meeting",
            "conversationId": body.get("conversationId") or "",
        }

    server._office_agent_lookup = fake_lookup
    server._handle_hermes_chat = fake_chat
    try:
        meeting = {"id": "m-hermes-scope"}
        result = server._meeting_call_provider(meeting, "hermes-default", "meeting prompt")
        expected = "meeting:m-hermes-scope:participant:hermes-default"
        assert result["ok"] is True
        assert result["conversationId"] == expected
        assert result["providerRef"]["conversationId"] == expected
        assert result["providerRef"]["sessionId"] == "hermes-session-meeting"
        assert calls[0]["conversationId"] == expected
        assert calls[0]["fromType"] == "agent"
    finally:
        server._office_agent_lookup = old_lookup
        server._handle_hermes_chat = old_chat


def test_meeting_mixed_openclaw_hermes_codex_participants_use_provider_dispatch():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_lookup = server._office_agent_lookup
        old_codex = server._handle_codex_chat
        old_hermes = server._handle_hermes_chat
        old_wf = server._wf_call_agent
        calls = []

        def fake_lookup(agent_id):
            providers = {
                "main": "openclaw",
                "hermes-default": "hermes",
                "codex-local": "codex",
            }
            return {
                "id": agent_id,
                "statusKey": agent_id,
                "providerAgentId": agent_id.replace("hermes-", "").replace("codex-", ""),
                "providerKind": providers.get(agent_id, "openclaw"),
            }

        def fake_codex(body):
            calls.append(("codex", body.get("agentId"), body.get("conversationId"), body.get("fromType")))
            return {
                "ok": True,
                "reply": "Position: Codex can participate.\nReasoning: native app-server meeting dispatch works.\nSuggested next step: continue.",
                "threadId": "codex-thread-meeting",
                "turnId": "codex-turn-meeting",
            }

        def fake_hermes(body):
            calls.append(("hermes", body.get("agentId"), body.get("conversationId"), body.get("fromType")))
            return {
                "ok": True,
                "reply": "Position: Hermes can participate.\nReasoning: native API meeting dispatch works.\nSuggested next step: continue.",
                "sessionId": "hermes-session-meeting",
            }

        def fake_wf(agent_id, message, timeout=600, project_id=None, task_id=None):
            calls.append(("openclaw", agent_id, task_id, project_id))
            return "Position: OpenClaw can participate.\nReasoning: workflow meeting dispatch works.\nSuggested next step: continue."

        server._office_agent_lookup = fake_lookup
        server._handle_codex_chat = fake_codex
        server._handle_hermes_chat = fake_hermes
        server._wf_call_agent = fake_wf
        try:
            created = create_meeting(maxRounds=1, idempotencyKey="mixed-provider-meeting")
            assert created["ok"] is True
            ran = server._handle_executable_meeting_run(created["meeting"]["id"])
            assert ran["ok"] is True
            turns = [
                event["payload"]
                for event in ran["events"]
                if event["type"] == "participant_turn"
                and (event.get("payload") or {}).get("stage") == "active_opening"
            ]
            assert [turn["speaker"] for turn in turns] == ["main", "hermes-default", "codex-local"]
            refs = {turn["speaker"]: turn["providerRef"] for turn in turns}
            assert refs["main"]["providerKind"] == "openclaw"
            assert refs["main"]["conversationId"] == f"meeting:{created['meeting']['id']}:participant:main"
            assert refs["hermes-default"]["providerKind"] == "hermes"
            assert refs["hermes-default"]["sessionId"] == "hermes-session-meeting"
            assert refs["codex-local"]["providerKind"] == "codex"
            assert refs["codex-local"]["threadId"] == "codex-thread-meeting"
            assert refs["codex-local"]["turnId"] == "codex-turn-meeting"
            assert ("codex", "codex-local", f"meeting:{created['meeting']['id']}:participant:codex-local", "agent") in calls
            assert ("hermes", "hermes-default", f"meeting:{created['meeting']['id']}:participant:hermes-default", "agent") in calls
            assert ("openclaw", "main", f"meeting:{created['meeting']['id']}:participant:main", "meeting-for-ai") in calls
        finally:
            server._office_agent_lookup = old_lookup
            server._handle_codex_chat = old_codex
            server._handle_hermes_chat = old_hermes
            server._wf_call_agent = old_wf
            restore_meeting_store(old_store)


def test_executable_meeting_create_persists_events_and_projects_active():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting()
            assert created["ok"] is True
            meeting = created["meeting"]
            assert meeting["stage"] == "preparing"
            assert meeting["version"] == 1
            assert meeting["lastEventSequence"] == 1
            assert meeting["participantState"]["codex-local"]["status"] == "reserved"

            detail = server._handle_executable_meeting_detail(meeting["id"])
            assert detail["ok"] is True
            assert detail["events"][0]["type"] == "meeting_created"
            assert detail["events"][0]["sequence"] == 1

            active = server._meeting_active_projection()
            projected = [m for m in active if m.get("id") == meeting["id"]][0]
            assert projected["executableMeeting"] is True
            assert projected["executionStage"] == "preparing"
            assert projected["participants"] == ["main", "hermes-default", "codex-local"]

            repeated = create_meeting(idempotencyKey="create-review")
            assert repeated["ok"] is True
            assert repeated["idempotent"] is True
            assert repeated["meeting"]["id"] == meeting["id"]
        finally:
            restore_meeting_store(old)


def test_executable_meeting_rejects_archive_manager_participant():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            blocked = create_meeting(
                participants=["main", "archive-manager"],
                moderator="main",
                idempotencyKey="archive-manager-blocked",
            )
            assert blocked["_status"] == 400
            assert blocked["code"] == "archive_manager_not_meeting_participant"

            blocked_moderator = create_meeting(
                participants=["main", "codex-local"],
                moderator="archive-manager",
                idempotencyKey="archive-manager-moderator-blocked",
            )
            assert blocked_moderator["_status"] == 400
            assert blocked_moderator["code"] == "archive_manager_not_meeting_participant"
        finally:
            restore_meeting_store(old)


def test_executable_meeting_occupancy_transition_and_history_projection():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(idempotencyKey="create-conflict")
            meeting = created["meeting"]

            conflict = create_meeting(
                topic="Conflicting Meeting",
                participants=["codex-local", "alt-agent"],
                moderator="codex-local",
                idempotencyKey="create-conflicting-meeting",
            )
            assert conflict["_status"] == 409
            assert conflict["conflicts"]["codex-local"] == meeting["id"]

            illegal = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "completed",
                "expectedVersion": meeting["version"],
            })
            assert illegal["_status"] == 409

            opening = server._handle_executable_meeting_transition(meeting["id"], {
                "action": "start",
                "expectedVersion": meeting["version"],
                "idempotencyKey": "to-opening",
            })
            assert opening["ok"] is True
            assert opening["meeting"]["stage"] == "active_opening"
            assert opening["meeting"]["version"] == 2

            repeated = server._handle_executable_meeting_transition(meeting["id"], {
                "action": "start",
                "idempotencyKey": "to-opening",
            })
            assert repeated["ok"] is True
            assert repeated["idempotent"] is True
            assert repeated["meeting"]["version"] == 2

            discussion = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "active_discussion",
                "expectedVersion": 2,
            })
            assert discussion["meeting"]["round"] == 1
            summarizing = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "summarizing",
                "expectedVersion": 3,
            })
            assert summarizing["meeting"]["stage"] == "summarizing"
            completed = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "completed",
                "expectedVersion": 4,
                "summary": "Phase 1 state machine is durable.",
                "result": {"decision": "Proceed to Phase 2 later", "actionItems": [{"item": "Run gate"}]},
            })
            assert completed["meeting"]["stage"] == "completed"

            active_ids = {m["id"] for m in server._meeting_active_projection()}
            assert meeting["id"] not in active_ids
            history = server._meeting_history_projection()
            projected = [m for m in history if m.get("id") == meeting["id"]][0]
            assert projected["executableMeeting"] is True
            assert projected["status"] == "completed"
            assert projected["summary"] == "Phase 1 state machine is durable."

            next_meeting = create_meeting(
                topic="Post-release Meeting",
                participants=["codex-local", "alt-agent"],
                moderator="codex-local",
                idempotencyKey="post-release",
            )
            assert next_meeting["ok"] is True
        finally:
            restore_meeting_store(old)


def test_executable_meeting_completion_awards_participant_xp_once():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(
                participants=["main", "hermes-default", "main"],
                moderator="main",
                idempotencyKey="meeting-xp-complete",
            )
            meeting = created["meeting"]
            server._handle_executable_meeting_transition(meeting["id"], {"action": "start", "expectedVersion": 1})
            server._handle_executable_meeting_transition(meeting["id"], {"stage": "active_discussion", "expectedVersion": 2})
            server._handle_executable_meeting_transition(meeting["id"], {"stage": "summarizing", "expectedVersion": 3})
            completed = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "completed",
                "expectedVersion": 4,
                "summary": "Meeting XP should be awarded once.",
            })
            assert completed["meeting"]["stage"] == "completed"
            award = completed["meeting"]["scoreAwarded"]["meetingParticipantXp"]
            assert award["awarded"] is True
            assert award["points"] == server.SCORE_MEETING_PARTICIPANT_XP
            assert award["participants"] == ["main", "hermes-default"]

            scores = load_scores(status_dir)
            assert scores["agents"]["main"]["score"] == 3
            assert scores["agents"]["hermes-default"]["score"] == 3
            assert scores["agents"]["main"]["completed"] == 0
            assert scores["agents"]["main"]["meetings"] == 1
            hist = scores["agents"]["main"]["history"][-1]
            assert hist["type"] == "meeting_participation"
            assert hist["meetingId"] == meeting["id"]

            repeated = server._handle_executable_meeting_transition(meeting["id"], {
                "stage": "completed",
                "idempotencyKey": "too-late",
            })
            assert repeated["_status"] == 409
            scores_after = load_scores(status_dir)
            assert scores_after["agents"]["main"]["score"] == 3
            assert scores_after["agents"]["main"]["meetings"] == 1

            leaderboard = server._handle_scores_leaderboard()["leaderboard"]
            main_entry = next(e for e in leaderboard if e["agent"] == "main")
            assert main_entry["meetings"] == 1
            assert main_entry["completed"] == 0
        finally:
            restore_meeting_store(old)


def test_meeting_participant_xp_skips_non_completed_and_invalid_participants():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            pending = {
                "id": "pending-meeting",
                "stage": "awaiting_user_decision",
                "participants": ["main"],
                "topic": "Pending",
            }
            assert server._award_meeting_participation_points(pending)["awarded"] is False
            assert not os.path.exists(os.path.join(status_dir, "project-scores.json"))

            completed = {
                "id": "manual-completed",
                "stage": "completed",
                "participants": ["", "unassigned", "archive-manager", "codex-local", "codex-local"],
                "topic": "Defensive scoring",
            }
            result = server._award_meeting_participation_points(completed)
            assert result["awarded"] is True
            assert result["award"]["participants"] == ["codex-local"]
            repeated = server._award_meeting_participation_points(completed)
            assert repeated["alreadyAwarded"] is True

            scores = load_scores(status_dir)
            assert list(scores["agents"]) == ["codex-local"]
            assert scores["agents"]["codex-local"]["score"] == 3
            assert scores["agents"]["codex-local"]["completed"] == 0
            assert scores["agents"]["codex-local"]["meetings"] == 1
        finally:
            restore_meeting_store(old)


def test_phase3_pause_resume_cancel_controls_project_previous_stage_and_history():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(idempotencyKey="phase3-control")
            meeting_id = created["meeting"]["id"]

            opening = server._handle_executable_meeting_transition(meeting_id, {
                "action": "start",
                "expectedVersion": 1,
            })
            assert opening["meeting"]["stage"] == "active_opening"

            paused = server._handle_executable_meeting_transition(meeting_id, {
                "action": "pause",
                "expectedVersion": 2,
            })
            assert paused["meeting"]["stage"] == "paused"
            assert paused["meeting"]["previousStage"] == "active_opening"

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["executionStage"] == "paused"
            assert active["executionPreviousStage"] == "active_opening"

            resumed = server._handle_executable_meeting_transition(meeting_id, {
                "action": "resume_opening",
                "expectedVersion": 3,
            })
            assert resumed["meeting"]["stage"] == "active_opening"
            assert resumed["meeting"]["previousStage"] == "paused"

            cancelled = server._handle_executable_meeting_transition(meeting_id, {
                "action": "cancel",
                "expectedVersion": 4,
            })
            assert cancelled["meeting"]["stage"] == "cancelled"

            active_ids = {m["id"] for m in server._meeting_active_projection()}
            assert meeting_id not in active_ids
            history = server._meeting_history_projection()
            projected = [m for m in history if m.get("id") == meeting_id][0]
            assert projected["status"] == "cancelled"
            assert projected["executableMeeting"] is True

            rejected = server._handle_executable_meeting_intervention(meeting_id, {"text": "too late"})
            assert rejected["_status"] == 409
        finally:
            restore_meeting_store(old)


def test_phase3_active_executable_meeting_projects_to_status_canvas_meetings():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(
                participants=["main", "hermes-default", "codex-local"],
                idempotencyKey="phase3-canvas",
            )
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {
                "action": "start",
                "expectedVersion": 1,
            })

            projected = server._status_meeting_projection([])
            canvas_meeting = [m for m in projected if m.get("id") == meeting_id][0]
            assert canvas_meeting["executableMeeting"] is True
            assert canvas_meeting["status"] == "active"
            assert canvas_meeting["executionStage"] == "active_opening"
            assert canvas_meeting["participants"] == ["main", "hermes-default", "codex-local"]
            assert canvas_meeting["agents"] == ["main", "hermes-default", "codex-local"]
            assert canvas_meeting["type"] == "group"

            legacy = {"id": "legacy-canvas", "topic": "Legacy Canvas", "participants": ["main", "hermes-default"], "status": "active"}
            mixed = server._status_meeting_projection([legacy])
            mixed_ids = {m.get("id") for m in mixed}
            assert {"legacy-canvas", meeting_id}.issubset(mixed_ids)

            server._handle_executable_meeting_transition(meeting_id, {
                "action": "cancel",
                "expectedVersion": 2,
            })
            after_cancel = server._status_meeting_projection([])
            assert meeting_id not in {m.get("id") for m in after_cancel}
        finally:
            restore_meeting_store(old)


def test_phase3_decision_window_timeout_setting_defaults_and_clamps():
    old = os.environ.pop("VO_MEETING_DECISION_WINDOW_SEC", None)
    try:
        assert server._meeting_decision_window_sec() == 20
        os.environ["VO_MEETING_DECISION_WINDOW_SEC"] = "5"
        assert server._meeting_decision_window_sec() == 10
        os.environ["VO_MEETING_DECISION_WINDOW_SEC"] = "130"
        assert server._meeting_decision_window_sec() == 120
        os.environ["VO_MEETING_DECISION_WINDOW_SEC"] = "bad"
        assert server._meeting_decision_window_sec() == 20
    finally:
        if old is None:
            os.environ.pop("VO_MEETING_DECISION_WINDOW_SEC", None)
        else:
            os.environ["VO_MEETING_DECISION_WINDOW_SEC"] = old


def test_phase3_decision_window_can_be_configured_per_meeting():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_fake = os.environ.get("VO_MEETING_FAKE_PROVIDER")
        os.environ["VO_MEETING_FAKE_PROVIDER"] = "1"
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                decisionWindowSec=120,
                idempotencyKey="phase3-window-per-meeting",
            )
            meeting_id = created["meeting"]["id"]
            opened = server._handle_executable_meeting_run(meeting_id, {})
            assert opened["meeting"]["stage"] == "awaiting_user_decision"
            assert opened["meeting"]["decisionWindowSec"] == 120
            event = [e for e in server._handle_executable_meeting_detail(meeting_id)["events"] if e["type"] == "decision_window_opened"][-1]
            assert event["payload"]["timeoutSec"] == 120

            continued = server._handle_executable_meeting_run(meeting_id, {"action": "continue"})
            assert continued["meeting"]["stage"] == "awaiting_user_decision"
            assert continued["meeting"]["decisionWindowSec"] == 120
            assert continued["meeting"]["decisionNextStage"] == "summarizing"
            assert not continued["meeting"].get("arbitration")
            summary_event = [e for e in server._handle_executable_meeting_detail(meeting_id)["events"] if e["type"] == "decision_window_opened"][-1]
            assert summary_event["payload"]["reason"] == "round_complete"
            assert summary_event["payload"]["timeoutSec"] == 120

            timed_out = server._handle_executable_meeting_run(meeting_id, {"action": "timeout"})
            assert timed_out["meeting"]["stage"] == "completed"

            created_clamped = create_meeting(
                participants=["window-low-a", "window-low-b"],
                moderator="window-low-a",
                decisionWindowSec=5,
                idempotencyKey="phase3-window-clamped",
            )
            assert created_clamped["meeting"]["decisionWindowSec"] == 10
        finally:
            restore_meeting_store(old_store)
            if old_fake is None:
                os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
            else:
                os.environ["VO_MEETING_FAKE_PROVIDER"] = old_fake


def test_phase3_targeted_question_in_decision_window_does_not_advance_round():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_fake = os.environ.get("VO_MEETING_FAKE_PROVIDER")
        old_window = os.environ.get("VO_MEETING_DECISION_WINDOW_SEC")
        os.environ["VO_MEETING_FAKE_PROVIDER"] = "1"
        os.environ["VO_MEETING_DECISION_WINDOW_SEC"] = "20"
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="phase3-targeted",
            )
            meeting_id = created["meeting"]["id"]

            opened = server._handle_executable_meeting_run(meeting_id, {})
            assert opened["awaitingUserDecision"] is True
            meeting = opened["meeting"]
            assert meeting["stage"] == "awaiting_user_decision"
            assert meeting["decisionForStage"] == "active_opening"
            assert meeting["decisionForRound"] == 0
            assert meeting["decisionNextStage"] == "active_discussion"
            assert meeting["decisionNextRound"] == 1
            assert meeting["decisionWindowSec"] == 20

            events = server._handle_executable_meeting_detail(meeting_id)["events"]
            formal_opening = [
                e for e in events
                if e["type"] == "participant_turn"
                and (e.get("payload") or {}).get("stage") == "active_opening"
                and not (e.get("payload") or {}).get("kind")
            ]
            assert len(formal_opening) == 2

            targeted = server._handle_executable_meeting_targeted_question(meeting_id, {
                "target": "hermes-default",
                "question": "请补充你对风险的判断。",
                "idempotencyKey": "risk-followup",
            })
            assert targeted["ok"] is True
            assert targeted["meeting"]["stage"] == "awaiting_user_decision"
            assert targeted["meeting"]["round"] == 0
            assert targeted["questionEvent"]["type"] == "targeted_question"
            assert targeted["event"]["payload"]["kind"] == "targeted_response"
            assert targeted["event"]["payload"]["stage"] == "active_opening"
            assert targeted["event"]["payload"]["round"] == 0

            repeated = server._handle_executable_meeting_targeted_question(meeting_id, {
                "target": "hermes-default",
                "question": "请补充你对风险的判断。",
                "idempotencyKey": "risk-followup",
            })
            assert repeated["idempotent"] is True
            events_after_repeat = server._handle_executable_meeting_detail(meeting_id)["events"]
            assert len([e for e in events_after_repeat if e["type"] == "targeted_question"]) == 1
            assert len([e for e in events_after_repeat if (e.get("payload") or {}).get("kind") == "targeted_response"]) == 1

            rejected = server._handle_executable_meeting_targeted_question(meeting_id, {
                "target": "missing-agent",
                "question": "hello",
            })
            assert rejected["_status"] == 400

            continued = server._handle_executable_meeting_transition(meeting_id, {"action": "continue"})
            assert continued["meeting"]["stage"] == "active_discussion"
            assert continued["meeting"]["round"] == 1

            rejected_after_continue = server._handle_executable_meeting_targeted_question(meeting_id, {
                "target": "hermes-default",
                "question": "too late",
            })
            assert rejected_after_continue["_status"] == 409
        finally:
            restore_meeting_store(old_store)
            if old_fake is None:
                os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
            else:
                os.environ["VO_MEETING_FAKE_PROVIDER"] = old_fake
            if old_window is None:
                os.environ.pop("VO_MEETING_DECISION_WINDOW_SEC", None)
            else:
                os.environ["VO_MEETING_DECISION_WINDOW_SEC"] = old_window


def test_phase3_late_formal_provider_response_is_ignored_after_cancel():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_call = server._meeting_call_provider

        def fake_call(meeting, speaker, prompt):
            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                live = store["meetings"][meeting["id"]]
                previous = live.get("stage")
                live["previousStage"] = previous
                live["stage"] = "cancelled"
                live["currentSpeaker"] = ""
                for participant in live.get("participants", []):
                    store.get("occupancy", {}).pop(participant, None)
                server._append_exec_meeting_event(store, live, "meeting_transitioned", payload={"from": previous, "to": "cancelled", "reason": "cancel_during_provider_call"})
                server._save_exec_meeting_store(store)
            return {
                "ok": True,
                "reply": json.dumps({"position": "late response", "rationale": "should be ignored"}),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 1,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        server._meeting_call_provider = fake_call
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                idempotencyKey="phase3-late-formal-cancel",
            )
            meeting_id = created["meeting"]["id"]
            ran = server._handle_executable_meeting_run(meeting_id, {})
            assert ran["ignoredProviderCompletion"] is True
            assert ran["meeting"]["stage"] == "cancelled"
            detail = server._handle_executable_meeting_detail(meeting_id)
            events = detail["events"]
            assert any(e["type"] == "provider_call_started" for e in events)
            ignored = [e for e in events if e["type"] == "provider_call_ignored"]
            assert len(ignored) == 1
            assert ignored[0]["payload"]["currentStage"] == "cancelled"
            formal_turns = [
                e for e in events
                if e["type"] == "participant_turn"
                and not (e.get("payload") or {}).get("kind")
                and (e.get("payload") or {}).get("purpose") != "meeting_result"
            ]
            assert formal_turns == []
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old_store)


def test_phase3_late_targeted_provider_response_is_ignored_after_continue():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_fake = os.environ.get("VO_MEETING_FAKE_PROVIDER")
        old_call = server._meeting_call_provider
        os.environ["VO_MEETING_FAKE_PROVIDER"] = "1"
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="phase3-late-targeted-continue",
            )
            meeting_id = created["meeting"]["id"]
            opened = server._handle_executable_meeting_run(meeting_id, {})
            assert opened["meeting"]["stage"] == "awaiting_user_decision"

            def fake_targeted_call(meeting, speaker, prompt):
                continued = server._handle_executable_meeting_transition(meeting["id"], {
                    "action": "continue",
                    "reason": "continue_during_targeted_provider_call",
                })
                assert continued["meeting"]["stage"] == "active_discussion"
                return {
                    "ok": True,
                    "reply": json.dumps({"position": "late targeted answer", "rationale": "should be ignored"}),
                    "providerRef": {"providerKind": "fake", "agentId": speaker},
                    "durationMs": 1,
                    "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
                }

            server._meeting_call_provider = fake_targeted_call
            targeted = server._handle_executable_meeting_targeted_question(meeting_id, {
                "target": "hermes-default",
                "question": "请补充风险。",
                "idempotencyKey": "late-targeted",
            })
            assert targeted["meeting"]["stage"] == "active_discussion"
            assert targeted["ignored"]["type"] == "provider_call_ignored"
            detail = server._handle_executable_meeting_detail(meeting_id)
            events = detail["events"]
            assert len([e for e in events if e["type"] == "targeted_question"]) == 1
            assert len([e for e in events if e["type"] == "provider_call_ignored" and (e.get("payload") or {}).get("kind") == "targeted_response"]) == 1
            assert len([e for e in events if e["type"] == "participant_turn" and (e.get("payload") or {}).get("kind") == "targeted_response"]) == 0
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old_store)
            if old_fake is None:
                os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
            else:
                os.environ["VO_MEETING_FAKE_PROVIDER"] = old_fake


def test_phase3_no_consensus_arbitration_decide_end_and_continue():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_fake = os.environ.get("VO_MEETING_FAKE_PROVIDER")
        old_call = server._meeting_call_provider

        def disagreement_call(meeting, speaker, prompt):
            return {
                "ok": True,
                "reply": json.dumps({
                    "position": f"{speaker} keeps a distinct option",
                    "reasoning": "deterministic disagreement fixture",
                    "disagreements": [f"{speaker} disagrees with the other option"],
                    "questions": [],
                    "suggestedNextStep": "ask user to arbitrate",
                    "confidence": "high",
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 0,
                "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
            }

        summary_prompts = []

        def summary_call(meeting, speaker, prompt):
            summary_prompts.append({"speaker": speaker, "prompt": prompt})
            return {
                "ok": True,
                "reply": json.dumps({
                    "outcome": "approved",
                    "summary": "Moderator summarized the user-confirmed consensus.",
                    "decision": "AI positions are aligned; close with the shared conclusion.",
                    "rationale": "The user confirmed that the remaining differences are non-substantive.",
                    "unresolvedQuestions": [],
                    "disagreements": [],
                    "actionItems": [],
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 0,
                "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
            }

        os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
        server._meeting_call_provider = disagreement_call
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="phase3-arbitration-decide",
            )
            meeting_id = created["meeting"]["id"]
            opened = server._handle_executable_meeting_run(meeting_id, {})
            assert opened["meeting"]["stage"] == "awaiting_user_decision"
            assert not opened["meeting"].get("arbitration")
            discussion = server._handle_executable_meeting_run(meeting_id, {"action": "continue"})
            assert discussion["meeting"]["stage"] == "awaiting_user_decision"
            assert discussion["meeting"]["decisionNextStage"] == "summarizing"
            assert discussion["meeting"]["arbitration"]["reason"] == "no_consensus"
            assert discussion["meeting"]["arbitration"]["positions"]

            decided = server._handle_executable_meeting_arbitration(meeting_id, {
                "action": "decide",
                "decision": "采纳 main 的方案。",
                "rationale": "风险更低。",
                "idempotencyKey": "arb-decide",
            })
            assert decided["ok"] is True
            assert decided["meeting"]["stage"] == "completed"
            assert decided["event"]["type"] == "arbitration_decision"
            assert decided["meeting"]["result"]["decision"] == "采纳 main 的方案。"
            assert decided["meeting"]["result"]["arbitration"]["action"] == "decide"

            repeated = server._handle_executable_meeting_arbitration(meeting_id, {
                "action": "decide",
                "decision": "采纳 main 的方案。",
                "idempotencyKey": "arb-decide",
            })
            assert repeated["_status"] == 409

            created_end = create_meeting(
                participants=["arb-end-a", "arb-end-b"],
                moderator="arb-end-a",
                maxRounds=1,
                idempotencyKey="phase3-arbitration-end",
            )
            end_id = created_end["meeting"]["id"]
            server._handle_executable_meeting_run(end_id, {})
            server._handle_executable_meeting_run(end_id, {"action": "continue"})
            ended = server._handle_executable_meeting_arbitration(end_id, {
                "action": "end_no_consensus",
                "rationale": "双方仍保留互斥判断。",
                "idempotencyKey": "arb-end",
            })
            assert ended["meeting"]["stage"] == "completed"
            assert ended["meeting"]["result"]["decision"].startswith("No consensus")
            assert ended["meeting"]["result"]["disagreements"]

            created_continue = create_meeting(
                participants=["arb-cont-a", "arb-cont-b"],
                moderator="arb-cont-a",
                maxRounds=1,
                idempotencyKey="phase3-arbitration-continue",
            )
            continue_id = created_continue["meeting"]["id"]
            server._handle_executable_meeting_run(continue_id, {})
            server._handle_executable_meeting_run(continue_id, {"action": "continue"})
            continued = server._handle_executable_meeting_arbitration(continue_id, {
                "action": "continue_discussion",
                "rationale": "再给一轮收敛分歧。",
                "idempotencyKey": "arb-continue",
            })
            assert continued["meeting"]["stage"] == "active_discussion"
            assert continued["meeting"]["round"] == 2
            assert continued["meeting"]["maxRounds"] >= 2
            continued_run = server._handle_executable_meeting_run(continue_id, {"action": "continue"})
            assert continued_run["meeting"]["stage"] == "awaiting_user_decision"
            detail = server._handle_executable_meeting_detail(continue_id)
            assert len([e for e in detail["events"] if e["type"] == "arbitration_decision"]) == 1
            assert any(e["type"] == "provider_call_started" and e["payload"]["round"] == 2 for e in detail["events"])
            assert any(e["type"] == "participant_turn" and e["payload"]["round"] == 2 for e in detail["events"])

            created_consensus = create_meeting(
                participants=["arb-sum-a", "arb-sum-b"],
                moderator="arb-sum-a",
                maxRounds=1,
                idempotencyKey="phase3-arbitration-consensus-summary",
            )
            consensus_id = created_consensus["meeting"]["id"]
            server._meeting_call_provider = disagreement_call
            server._handle_executable_meeting_run(consensus_id, {})
            server._handle_executable_meeting_run(consensus_id, {"action": "continue"})
            server._meeting_call_provider = summary_call
            summarized = server._handle_executable_meeting_arbitration(consensus_id, {
                "action": "consensus_summary",
                "rationale": "用户确认这些差异不是实质分歧。",
                "idempotencyKey": "arb-consensus-summary",
            })
            assert summarized["ok"] is True
            assert summarized["meeting"]["stage"] == "completed"
            assert summarized["event"]["type"] == "arbitration_decision"
            assert summarized["event"]["payload"]["action"] == "consensus_summary"
            assert summarized["meeting"]["result"]["summary"] == "Moderator summarized the user-confirmed consensus."
            assert summary_prompts and summary_prompts[-1]["speaker"] == "arb-sum-a"
            consensus_detail = server._handle_executable_meeting_detail(consensus_id)
            assert any(e["type"] == "decision_window_closed" and (e["payload"] or {}).get("reason") == "arbitration_consensus_summary" for e in consensus_detail["events"])
            assert any(e["type"] == "provider_call_started" and (e["payload"] or {}).get("purpose") == "meeting_result" for e in consensus_detail["events"])
            assert any(e["type"] == "meeting_result" and (e["payload"] or {}).get("outcome") == "approved" for e in consensus_detail["events"])
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old_store)
            if old_fake is None:
                os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
            else:
                os.environ["VO_MEETING_FAKE_PROVIDER"] = old_fake


def test_phase3_final_round_without_disagreement_auto_summarizes_on_timeout():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_fake = os.environ.get("VO_MEETING_FAKE_PROVIDER")
        old_call = server._meeting_call_provider
        os.environ["VO_MEETING_FAKE_PROVIDER"] = "1"

        reentrant_results = []

        def summary_call(meeting, speaker, prompt):
            reentrant_results.append(server._handle_executable_meeting_run(meeting["id"], {}))
            return {
                "ok": True,
                "reply": json.dumps({
                    "summary": "Final summary after timeout.",
                    "decision": "Close the meeting automatically.",
                    "unresolvedQuestions": [],
                    "disagreements": [],
                    "actionItems": [],
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 0,
                "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
            }

        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="phase3-final-timeout-summary",
            )
            meeting_id = created["meeting"]["id"]
            opened = server._handle_executable_meeting_run(meeting_id, {})
            assert opened["meeting"]["stage"] == "awaiting_user_decision"
            assert not opened["meeting"].get("arbitration")

            discussion = server._handle_executable_meeting_run(meeting_id, {"action": "continue"})
            assert discussion["meeting"]["stage"] == "awaiting_user_decision"
            assert discussion["meeting"]["decisionNextStage"] == "summarizing"
            assert not discussion["meeting"].get("arbitration")

            server._meeting_call_provider = summary_call
            timed_out = server._handle_executable_meeting_run(meeting_id, {"action": "timeout"})
            assert timed_out["ok"] is True
            assert timed_out["meeting"]["stage"] == "completed"
            assert timed_out["meeting"]["result"]["summary"] == "Final summary after timeout."
            assert reentrant_results
            assert reentrant_results[0]["meeting"]["stage"] == "summarizing"
            assert reentrant_results[0]["summarizing"] is True
            detail = server._handle_executable_meeting_detail(meeting_id)
            assert any(e["type"] == "decision_window_closed" and (e.get("payload") or {}).get("to") == "summarizing" for e in detail["events"])
            assert len([e for e in detail["events"] if e["type"] == "meeting_result"]) == 1
            assert not any(e["type"] == "meeting_transitioned" and (e.get("payload") or {}).get("from") == "completed" for e in detail["events"])
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old_store)
            if old_fake is None:
                os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
            else:
                os.environ["VO_MEETING_FAKE_PROVIDER"] = old_fake


def test_phase3_moderator_resolution_policy_auto_closes_disagreement():
    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_fake = os.environ.get("VO_MEETING_FAKE_PROVIDER")
        old_call = server._meeting_call_provider
        os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)

        def disagreement_call(meeting, speaker, prompt):
            return {
                "ok": True,
                "reply": json.dumps({
                    "position": f"{speaker} recommends a different path",
                    "reasoning": "policy fixture disagreement",
                    "disagreements": [f"{speaker} disagrees with the other path"],
                    "questions": [],
                    "suggestedNextStep": "moderator should decide",
                    "confidence": "high",
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 0,
                "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
            }

        def moderator_decision_call(meeting, speaker, prompt):
            assert "Resolution policy: moderator_decision" in prompt
            assert "approved|rejected|no_consensus|needs_user_decision" in prompt
            return {
                "ok": True,
                "reply": json.dumps({
                    "outcome": "rejected",
                    "summary": "Moderator closed the disagreement.",
                    "decision": "不通过当前方案。",
                    "rationale": "The risks are still unresolved.",
                    "unresolvedQuestions": [],
                    "disagreements": ["Path A and Path B remain incompatible."],
                    "actionItems": [],
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 0,
                "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
            }

        server._meeting_call_provider = disagreement_call
        try:
            created = create_meeting(
                participants=["policy-a", "policy-b"],
                moderator="policy-a",
                maxRounds=1,
                resolutionPolicy="moderator_decision",
                idempotencyKey="phase3-moderator-resolution-policy",
            )
            meeting_id = created["meeting"]["id"]
            assert created["meeting"]["resolutionPolicy"] == "moderator_decision"
            opened = server._handle_executable_meeting_run(meeting_id, {})
            assert opened["meeting"]["stage"] == "awaiting_user_decision"
            discussion = server._handle_executable_meeting_run(meeting_id, {"action": "continue"})
            assert discussion["meeting"]["stage"] == "awaiting_user_decision"
            assert discussion["meeting"]["decisionNextStage"] == "summarizing"
            assert not discussion["meeting"].get("arbitration")

            detail_before = server._handle_executable_meeting_detail(meeting_id)
            opened_events = [e for e in detail_before["events"] if e["type"] == "decision_window_opened"]
            assert opened_events[-1]["payload"]["resolutionPolicy"] == "moderator_decision"
            assert opened_events[-1]["payload"]["arbitration"]["reason"] == "no_consensus"

            server._meeting_call_provider = moderator_decision_call
            timed_out = server._handle_executable_meeting_run(meeting_id, {"action": "timeout"})
            assert timed_out["meeting"]["stage"] == "completed"
            assert timed_out["meeting"]["result"]["outcome"] == "rejected"
            assert timed_out["meeting"]["result"]["decision"] == "不通过当前方案。"
            assert timed_out["meeting"]["result"]["rationale"] == "The risks are still unresolved."
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old_store)
            if old_fake is None:
                os.environ.pop("VO_MEETING_FAKE_PROVIDER", None)
            else:
                os.environ["VO_MEETING_FAKE_PROVIDER"] = old_fake


def test_executable_meeting_events_after_and_reconcile():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(idempotencyKey="create-events")
            meeting = created["meeting"]
            server._handle_executable_meeting_transition(meeting["id"], {"action": "start", "expectedVersion": 1})
            events = server._handle_executable_meeting_events(meeting["id"], "after=1")
            assert events["ok"] is True
            assert [e["sequence"] for e in events["events"]] == [2]

            reconciled = server._handle_executable_meeting_reconcile()
            assert reconciled["ok"] is True
            assert reconciled["activeMeetings"] == 1
            assert reconciled["occupancy"]["main"] == meeting["id"]
        finally:
            restore_meeting_store(old)


def test_phase2_fake_provider_runs_incremental_meeting_to_completion():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        old_call = server._meeting_call_provider
        prompts = []

        def fake_call(meeting, speaker, prompt):
            prompts.append({"speaker": speaker, "prompt": prompt, "stage": meeting.get("stage")})
            return {
                "ok": True,
                "reply": f"Position: {speaker} supports the proposal.\nReasoning: based on the current meeting state.\nSuggested next step: continue.",
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 1,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        server._meeting_call_provider = fake_call
        try:
            created = create_meeting(
                topic="Incremental Context Meeting",
                context="This initial context should only appear in each participant's first turn.",
                contextMode="incremental",
                maxRounds=1,
                idempotencyKey="phase2-incremental",
            )
            meeting_id = created["meeting"]["id"]
            ran = server._handle_executable_meeting_run(meeting_id)
            assert ran["ok"] is True
            assert ran["meeting"]["stage"] == "awaiting_user_decision"
            ran = server._handle_executable_meeting_run(meeting_id, {"action": "continue"})
            assert ran["ok"] is True
            assert ran["meeting"]["stage"] == "awaiting_user_decision"
            ran = server._handle_executable_meeting_run(meeting_id, {"action": "continue"})
            assert ran["ok"] is True
            assert ran["meeting"]["stage"] == "completed"
            events = ran["events"]
            turns = [e for e in events if e["type"] == "participant_turn"]
            formal_turns = [e for e in turns if not (e.get("payload") or {}).get("kind") and (e.get("payload") or {}).get("purpose") != "meeting_result"]
            assert len(formal_turns) == 6
            assert ran["meeting"]["result"]["summary"]
            assert set(ran["meeting"]["result"]["contributions"]) == {"main", "hermes-default", "codex-local"}
            projected = server._exec_meeting_project_history(ran["meeting"], events)
            formal_projected = [t for t in projected["transcript"] if t.get("stage") != "summarizing" and not t.get("kind")]
            assert len(formal_projected) == 6
            assert projected["transcript"][0]["stage"] == "active_opening"
            assert projected["transcript"][0]["speaker"] == "main"
            assert formal_projected[-1]["round"] == 1

            main_prompts = [p["prompt"] for p in prompts if p["speaker"] == "main" and "Summarize and close this meeting" not in p["prompt"]]
            assert len(main_prompts) == 2
            assert "Confirmed context" in main_prompts[0]
            assert "This initial context should only appear" in main_prompts[0]
            assert "New events since your last turn" in main_prompts[1]
            assert "This initial context should only appear" not in main_prompts[1]
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old)


def test_phase2_prompt_context_modes():
    meeting = {
        "id": "m1",
        "topic": "Context Budget",
        "purpose": "Verify prompt modes",
        "meetingType": "discussion",
        "stage": "active_discussion",
        "round": 1,
        "maxRounds": 2,
        "moderator": "main",
        "context": "Initial context",
        "contextBudget": {"maxPromptChars": 12000, "maxInitialContextChars": 4000, "maxSummaryChars": 3000, "maxRecentEvents": 2},
        "rollingSummary": "A compact summary",
        "participantLastSeen": {"main": 1},
    }
    events = [
        {"sequence": 1, "type": "participant_turn", "payload": {"speaker": "main", "text": "Opening"}},
        {"sequence": 2, "type": "participant_turn", "payload": {"speaker": "hermes-default", "text": "Hermes response"}},
        {"sequence": 3, "type": "participant_turn", "payload": {"speaker": "codex-local", "text": "Codex response"}},
    ]

    meeting["contextMode"] = "incremental"
    incremental = server._meeting_build_prompt(meeting, "main", "active_discussion", events)
    assert "New events since your last turn" in incremental
    assert "Hermes response" in incremental
    assert "Initial context" not in incremental

    meeting["contextMode"] = "summary"
    summary = server._meeting_build_prompt(meeting, "main", "active_discussion", events)
    assert "Rolling summary" in summary
    assert "A compact summary" in summary
    assert "Relevant recent statements" in summary

    meeting["contextMode"] = "full"
    full = server._meeting_build_prompt(meeting, "main", "active_discussion", events)
    assert "Full transcript" in full
    assert "Initial context" in full
    assert "Codex response" in full


def test_phase2_provider_timeout_is_configurable_for_real_calls():
    old_env = os.environ.get("VO_MEETING_PROVIDER_TIMEOUT_SEC")
    old_lookup = server._office_agent_lookup
    old_codex = server._handle_codex_chat
    old_hermes = server._handle_hermes_chat
    old_wf = server._wf_call_agent
    calls = []

    def fake_lookup(agent_id):
        provider = {
            "codex-local": "codex",
            "hermes-default": "hermes",
            "main": "openclaw",
        }.get(agent_id, "openclaw")
        return {"id": agent_id, "providerKind": provider}

    def fake_codex(body):
        calls.append(("codex", body.get("timeoutSec")))
        return {"ok": True, "reply": "codex ok"}

    def fake_hermes(body):
        calls.append(("hermes", body.get("timeoutSec")))
        return {"ok": True, "reply": "hermes ok"}

    def fake_wf(agent_id, message, timeout=600, project_id=None, task_id=None):
        calls.append(("openclaw", timeout))
        return "openclaw ok"

    os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = "17"
    server._office_agent_lookup = fake_lookup
    server._handle_codex_chat = fake_codex
    server._handle_hermes_chat = fake_hermes
    server._wf_call_agent = fake_wf
    try:
        meeting = {"id": "m-timeout"}
        for speaker in ("codex-local", "hermes-default", "main"):
            result = server._meeting_call_provider(meeting, speaker, "prompt")
            assert result["ok"] is True
        assert calls == [("codex", 17), ("hermes", 17), ("openclaw", 17)]
    finally:
        if old_env is None:
            os.environ.pop("VO_MEETING_PROVIDER_TIMEOUT_SEC", None)
        else:
            os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = old_env
        server._office_agent_lookup = old_lookup
        server._handle_codex_chat = old_codex
        server._handle_hermes_chat = old_hermes
        server._wf_call_agent = old_wf


def test_phase3_active_projection_includes_live_transcript_and_pending_calls():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        old_timeout = os.environ.get("VO_MEETING_PROVIDER_TIMEOUT_SEC")
        os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = "5"
        try:
            created = create_meeting(idempotencyKey="phase3-live")
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {"action": "start", "expectedVersion": 1})

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                pending = server._append_exec_meeting_event(
                    store,
                    meeting,
                    "provider_call_started",
                    actor={"type": "agent", "id": "main"},
                    payload={"speaker": "main", "stage": "active_opening", "round": 0, "contextMode": "incremental", "promptChars": 123},
                )
                pending["createdAt"] = "2026-06-20T00:00:00+00:00"
                server._save_exec_meeting_store(store)

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["lastEventSequence"] == pending["sequence"]
            assert active["pendingCalls"][0]["speaker"] == "main"
            assert active["pendingCalls"][0]["promptChars"] == 123
            assert active["pendingCalls"][0]["timeoutSec"] == 5
            assert active["pendingCalls"][0]["elapsedSec"] >= 5
            assert active["pendingCalls"][0]["timedOut"] is True
            assert active["transcript"] == []
            assert server._meeting_pending_formal_turn_exists(active["pendingCalls"], "active_opening", 0, "main") is False

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                events = store.get("events", {}).get(meeting_id, [])
            assert server._meeting_pending_formal_turn_exists(events, "active_opening", 0, "main") is True

            skipped = server._handle_executable_meeting_run(meeting_id, {
                "action": "provider_timeout_skip",
                "pendingSequence": pending["sequence"],
                "_noAutoContinue": True,
            })
            assert skipped["ok"] is True
            assert skipped["skipped"] is True
            assert skipped["event"]["type"] == "participant_turn"
            assert skipped["event"]["payload"]["ok"] is False
            assert skipped["event"]["payload"]["skipReason"] == "provider_timeout"
            assert skipped["event"]["payload"]["inReplyToSequence"] == pending["sequence"]

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["pendingCalls"] == []
            assert active["transcript"][0]["speaker"] == "main"
            assert active["transcript"][0]["ok"] is False
            assert active["transcript"][0]["parseError"] == "provider_timeout_skipped"

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                server._append_ignored_provider_completion(
                    store,
                    meeting,
                    "main",
                    {"ok": True, "reply": "Late opening statement", "providerRef": {"providerKind": "fake", "agentId": "main"}, "durationMs": 7},
                    {"text": "Late opening statement", "rawText": "Late opening statement", "structured": {}, "parseError": ""},
                    pending,
                    "meeting_state_changed",
                    "active_opening",
                    0,
                )
                server._save_exec_meeting_store(store)

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["pendingCalls"] == []
            assert len(active["transcript"]) == 1
            assert active["transcript"][0]["speaker"] == "main"
            assert active["transcript"][0]["parseError"] == "provider_timeout_skipped"
            detail = server._handle_executable_meeting_detail(meeting_id)
            assert len([e for e in detail["events"] if e["type"] == "provider_call_ignored"]) == 1
        finally:
            if old_timeout is None:
                os.environ.pop("VO_MEETING_PROVIDER_TIMEOUT_SEC", None)
            else:
                os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = old_timeout
            restore_meeting_store(old)


def test_phase3_provider_timeout_skip_continues_meeting():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        old_timeout = os.environ.get("VO_MEETING_PROVIDER_TIMEOUT_SEC")
        old_call = server._meeting_call_provider
        os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = "5"
        calls = []

        def fake_call(meeting, speaker, prompt):
            calls.append({"speaker": speaker, "stage": meeting.get("stage"), "round": meeting.get("round")})
            return {
                "ok": True,
                "reply": f"Position: {speaker} can continue.\nReasoning: timeout skip should not stall the meeting.\nSuggested next step: continue.",
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 1,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        server._meeting_call_provider = fake_call
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="phase3-timeout-continues",
            )
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {"action": "start", "expectedVersion": 1})

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                pending = server._append_exec_meeting_event(
                    store,
                    meeting,
                    "provider_call_started",
                    actor={"type": "agent", "id": "main"},
                    payload={"speaker": "main", "stage": "active_opening", "round": 0, "contextMode": "incremental", "promptChars": 123},
                )
                pending["createdAt"] = "2026-06-20T00:00:00+00:00"
                meeting["currentSpeaker"] = "main"
                server._save_exec_meeting_store(store)

            skipped = server._handle_executable_meeting_run(meeting_id, {
                "action": "provider_timeout_skip",
                "pendingSequence": pending["sequence"],
            })

            assert skipped["ok"] is True
            assert skipped["timeoutSkipped"] is True
            assert skipped["meeting"]["stage"] == "awaiting_user_decision"
            assert calls == [{"speaker": "hermes-default", "stage": "active_opening", "round": 0}]

            detail = server._handle_executable_meeting_detail(meeting_id)
            turns = [
                e for e in detail["events"]
                if e["type"] == "participant_turn" and (e.get("payload") or {}).get("stage") == "active_opening"
            ]
            assert [(e["payload"]["speaker"], e["payload"].get("parseError", "")) for e in turns] == [
                ("main", "provider_timeout_skipped"),
                ("hermes-default", "structured_json_not_found"),
            ]
            assert not server._meeting_active_projection()[0]["pendingCalls"]
        finally:
            server._meeting_call_provider = old_call
            if old_timeout is None:
                os.environ.pop("VO_MEETING_PROVIDER_TIMEOUT_SEC", None)
            else:
                os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = old_timeout
            restore_meeting_store(old)


def test_phase3_user_intervention_is_projected_and_passed_to_incremental_prompt():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(idempotencyKey="phase3-intervention")
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {"action": "start", "expectedVersion": 1})

            first = server._handle_executable_meeting_intervention(meeting_id, {
                "text": "用户插话：请先确认风险。",
                "context": "补充上下文：预算上限是 2 天。",
                "actorId": "user",
                "idempotencyKey": "user-context-1",
            })
            assert first["ok"] is True
            assert first["event"]["type"] == "user_intervention"
            assert first["event"]["payload"]["kind"] == "statement_context"

            repeated = server._handle_executable_meeting_intervention(meeting_id, {
                "text": "用户插话：请先确认风险。",
                "context": "补充上下文：预算上限是 2 天。",
                "actorId": "user",
                "idempotencyKey": "user-context-1",
            })
            assert repeated["ok"] is True
            assert repeated["idempotent"] is True
            assert repeated["event"]["sequence"] == first["event"]["sequence"]

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            user_rows = [t for t in active["transcript"] if t.get("type") == "user_intervention"]
            assert len(user_rows) == 1
            assert user_rows[0]["text"] == "用户插话：请先确认风险。"
            assert user_rows[0]["context"] == "补充上下文：预算上限是 2 天。"

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                meeting["contextMode"] = "incremental"
                meeting.setdefault("participantLastSeen", {})["hermes-default"] = 1
                prompt = server._meeting_build_prompt(meeting, "hermes-default", "active_opening", store["events"][meeting_id])
            assert "New events since your last turn" in prompt
            assert "用户插话：请先确认风险。" in prompt
            assert "补充上下文：预算上限是 2 天。" in prompt

            events_after = server._handle_executable_meeting_events(meeting_id, f"after={first['event']['sequence'] - 1}")
            assert events_after["events"][0]["type"] == "user_intervention"

            cancelled = server._handle_executable_meeting_transition(meeting_id, {"action": "cancel"})
            assert cancelled["meeting"]["stage"] == "cancelled"
            rejected = server._handle_executable_meeting_intervention(meeting_id, {"text": "too late"})
            assert rejected["_status"] == 409
        finally:
            restore_meeting_store(old)


def test_phase3_agenda_change_updates_future_prompt_and_projection():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            created = create_meeting(idempotencyKey="phase3-agenda")
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {"action": "start", "expectedVersion": 1})

            changed = server._handle_executable_meeting_agenda_change(meeting_id, {
                "agenda": "改为先评估上线风险和回滚方案",
                "reason": "用户临时调整优先级",
                "actorId": "user",
                "idempotencyKey": "agenda-1",
            })
            assert changed["ok"] is True
            assert changed["event"]["type"] == "agenda_change"
            assert changed["meeting"]["topic"] != changed["meeting"]["agenda"]
            assert changed["meeting"]["agenda"] == "改为先评估上线风险和回滚方案"
            assert changed["event"]["payload"]["previousAgenda"] == changed["meeting"]["topic"]

            repeated = server._handle_executable_meeting_agenda_change(meeting_id, {
                "agenda": "改为先评估上线风险和回滚方案",
                "reason": "用户临时调整优先级",
                "actorId": "user",
                "idempotencyKey": "agenda-1",
            })
            assert repeated["ok"] is True
            assert repeated["idempotent"] is True
            assert repeated["event"]["sequence"] == changed["event"]["sequence"]

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["agenda"] == "改为先评估上线风险和回滚方案"
            agenda_rows = [t for t in active["transcript"] if t.get("type") == "agenda_change"]
            assert len(agenda_rows) == 1
            assert agenda_rows[0]["text"] == "改为先评估上线风险和回滚方案"
            assert agenda_rows[0]["reason"] == "用户临时调整优先级"

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                meeting["contextMode"] = "incremental"
                meeting.setdefault("participantLastSeen", {})["hermes-default"] = changed["event"]["sequence"] - 1
                prompt = server._meeting_build_prompt(meeting, "hermes-default", "active_opening", store["events"][meeting_id])
            assert "Current agenda: 改为先评估上线风险和回滚方案" in prompt
            assert "user changed agenda to: 改为先评估上线风险和回滚方案" in prompt
            assert "reason: 用户临时调整优先级" in prompt

            events_after = server._handle_executable_meeting_events(meeting_id, f"after={changed['event']['sequence'] - 1}")
            assert events_after["events"][0]["type"] == "agenda_change"

            cancelled = server._handle_executable_meeting_transition(meeting_id, {"action": "cancel"})
            assert cancelled["meeting"]["stage"] == "cancelled"
            rejected = server._handle_executable_meeting_agenda_change(meeting_id, {"agenda": "too late"})
            assert rejected["_status"] == 409
        finally:
            restore_meeting_store(old)


def test_phase3_provider_envelope_is_unwrapped_and_structured_turn_is_projected():
    envelope = {
        "runId": "r1",
        "status": "ok",
        "result": {
            "payload": [{
                "text": "{\"position\":\"Use a structured transcript\",\"reasoning\":\"It keeps rendering and arbitration deterministic\",\"disagreements\":[],\"questions\":[\"Should raw provider JSON be visible?\"],\"suggestedNextStep\":\"Render structured fields in the UI\",\"confidence\":\"high\"}"
            }],
            "meta": {"durationMs": 12, "provider": "openclaw"},
        },
    }
    normalized = server._meeting_normalize_provider_reply(json.dumps(envelope))
    assert normalized["structured"]["position"] == "Use a structured transcript"
    assert normalized["structured"]["questions"] == ["Should raw provider JSON be visible?"]
    assert "runId" in normalized["providerRaw"]
    assert "Use a structured transcript" in normalized["text"]
    assert "runId" not in normalized["text"]


def test_phase3_openclaw_payloads_envelope_is_unwrapped():
    envelope = {
        "runId": "d71f2829-af2c-46d3-8edf-16a5e562f483",
        "status": "ok",
        "summary": "completed",
        "result": {
            "payloads": [{
                "text": "各位好，我是风控管理委员会 agent。\n\n我的角色是评估交易方案的风险边界。",
                "mediaUrl": None,
            }],
        },
        "meta": {"durationMs": 29933},
    }
    normalized = server._meeting_normalize_provider_reply(json.dumps(envelope, ensure_ascii=False))
    assert normalized["text"].startswith("各位好，我是风控管理委员会 agent。")
    assert "风险边界" in normalized["text"]
    assert "runId" in normalized["providerRaw"]
    assert "payloads" in normalized["providerRaw"]
    assert "d71f2829" not in normalized["text"]
    assert '"status"' not in normalized["text"]


def test_phase3_structured_provider_output_is_saved_without_raw_envelope_in_transcript():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        old_call = server._meeting_call_provider

        def fake_call(meeting, speaker, prompt):
            envelope = {
                "runId": f"run-{speaker}",
                "status": "ok",
                "result": {
                    "payload": [{
                "text": json.dumps({
                            "position": f"{speaker} supports the plan",
                            "reasoning": "The risk is bounded.",
                            "disagreements": ["Do not expose provider envelope"],
                            "questions": [],
                            "suggestedNextStep": "Proceed with structured rendering.",
                            "confidence": "medium",
                        })
                    }],
                    "meta": {"durationMs": 5},
                },
            }
            return {
                "ok": True,
                "reply": json.dumps(envelope),
                "providerRef": {"providerKind": "openclaw", "agentId": speaker},
                "durationMs": 5,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        server._meeting_call_provider = fake_call
        try:
            created = create_meeting(
                topic="Structured Turn Meeting",
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="phase3-structured-run",
            )
            meeting_id = created["meeting"]["id"]
            ran = server._handle_executable_meeting_run(meeting_id)
            assert ran["ok"] is True
            detail = server._handle_executable_meeting_detail(meeting_id)
            events = detail["events"]
            turns = [e for e in events if e["type"] == "participant_turn"]
            assert turns
            first_payload = turns[0]["payload"]
            assert first_payload["structured"]["position"] == "main supports the plan"
            assert first_payload["structured"]["disagreements"] == ["Do not expose provider envelope"]
            assert "run-main" in first_payload["providerRaw"]
            assert "run-main" not in first_payload["text"]

            projected = server._exec_meeting_project_history(detail["meeting"], events)
            first_turn = projected["transcript"][0]
            assert first_turn["structured"]["suggestedNextStep"] == "Proceed with structured rendering."
            assert "run-main" not in first_turn["text"]
            assert "providerRaw" not in first_turn
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old)


def test_phase3_executable_end_uses_moderator_summary_without_manual_summary():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        old_call = server._meeting_call_provider

        def fake_call(meeting, speaker, prompt):
            assert "Summarize and close this meeting" in prompt
            return {
                "ok": True,
                "reply": json.dumps({
                    "summary": "Moderator generated summary.",
                    "decision": "Proceed with the accepted direction.",
                    "unresolvedQuestions": ["none"],
                    "disagreements": [],
                    "actionItems": [{"owner": speaker, "item": "Publish meeting notes"}],
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 3,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        server._meeting_call_provider = fake_call
        try:
            created = create_meeting(
                topic="AI End Meeting",
                participants=["main", "hermes-default"],
                moderator="main",
                idempotencyKey="phase3-ai-end",
            )
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {"action": "start", "expectedVersion": 1})
            ended = server._handle_meeting_end({
                "id": meeting_id,
                "endedBy": "user",
                "summary": "Manual text must not bypass the moderator JSON result prompt.",
                "resolution": "Manual resolution must not become the executable meeting result.",
            })
            assert ended["ok"] is True
            assert ended["meeting"]["stage"] == "completed"
            assert ended["meeting"]["result"]["summary"] == "Moderator generated summary."
            assert ended["meeting"]["result"]["decision"] == "Proceed with the accepted direction."
            assert ended["meeting"]["result"]["actionItems"] == [{"owner": "main", "item": "Publish meeting notes"}]
            events = ended["events"]
            assert any(e["type"] == "provider_call_started" and (e["payload"] or {}).get("purpose") == "meeting_result" for e in events)
            assert any(e["type"] == "meeting_result" and (e["payload"] or {}).get("moderator") == "main" for e in events)
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old)


def test_phase3_moderator_failure_user_takeover_and_replacement():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        old_call = server._meeting_call_provider
        calls = []

        def fake_call(meeting, speaker, prompt):
            calls.append(speaker)
            if speaker == "main":
                return {
                    "ok": False,
                    "reply": "[ERROR] moderator quota exhausted",
                    "providerRef": {"providerKind": "fake", "agentId": speaker},
                    "durationMs": 1,
                    "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
                }
            return {
                "ok": True,
                "reply": json.dumps({
                    "summary": f"Replacement summary by {speaker}.",
                    "decision": "Replacement moderator closed the meeting.",
                    "unresolvedQuestions": [],
                    "disagreements": [],
                    "actionItems": [],
                }),
                "providerRef": {"providerKind": "fake", "agentId": speaker},
                "durationMs": 2,
                "conversationId": f"meeting:{meeting['id']}:participant:{speaker}",
            }

        server._meeting_call_provider = fake_call
        try:
            created = create_meeting(
                topic="Moderator Failure",
                participants=["main", "hermes-default"],
                moderator="main",
                idempotencyKey="phase3-moderator-failure-user",
            )
            meeting_id = created["meeting"]["id"]
            server._handle_executable_meeting_transition(meeting_id, {"action": "start", "expectedVersion": 1})
            failed = server._handle_meeting_end({"id": meeting_id, "endedBy": "user"})
            assert failed["ok"] is False
            assert failed["meeting"]["stage"] == "awaiting_user_decision"
            assert failed["meeting"]["moderatorFailure"]["reason"] == "moderator_failed"
            assert failed["meeting"]["moderatorFailure"]["moderator"] == "main"
            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["moderatorFailure"]["reason"] == "moderator_failed"

            takeover = server._handle_executable_meeting_moderator_takeover(meeting_id, {
                "action": "user_takeover",
                "summary": "User closed after moderator failure.",
                "decision": "Ship with manual summary.",
            })
            assert takeover["ok"] is True
            assert takeover["meeting"]["stage"] == "completed"
            assert takeover["meeting"]["result"]["summary"] == "User closed after moderator failure."
            assert takeover["meeting"]["result"]["moderatorTakeover"]["action"] == "user_takeover"
            assert any(e["type"] == "moderator_takeover" for e in takeover["events"])

            created_replace = create_meeting(
                topic="Moderator Replacement",
                participants=["main", "hermes-default"],
                moderator="main",
                idempotencyKey="phase3-moderator-failure-replace",
            )
            replace_id = created_replace["meeting"]["id"]
            server._handle_executable_meeting_transition(replace_id, {"action": "start", "expectedVersion": 1})
            failed_replace = server._handle_meeting_end({"id": replace_id, "endedBy": "user"})
            assert failed_replace["meeting"]["stage"] == "awaiting_user_decision"
            replaced = server._handle_executable_meeting_moderator_takeover(replace_id, {
                "action": "replace_moderator",
                "moderator": "hermes-default",
            })
            assert replaced["ok"] is True
            assert replaced["meeting"]["stage"] == "completed"
            assert replaced["meeting"]["moderator"] == "hermes-default"
            assert replaced["meeting"]["result"]["summary"] == "Replacement summary by hermes-default."
            assert "hermes-default" in calls

            terminal_reject = server._handle_executable_meeting_moderator_takeover(replace_id, {
                "action": "user_takeover",
                "summary": "too late",
            })
            assert terminal_reject["_status"] == 409
        finally:
            server._meeting_call_provider = old_call
            restore_meeting_store(old)


def test_legacy_meeting_end_still_requires_manual_summary():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_meeting_store(status_dir)
        try:
            data = {"_meetings": [{"id": "legacy-m1", "topic": "Legacy", "status": "active", "participants": ["main"], "agents": ["main"]}]}
            server._save_meetings_file(data)
            result = server._handle_meeting_end({"id": "legacy-m1"})
            assert result["_status"] == 400
        finally:
            restore_meeting_store(old)


def test_phase2_openclaw_workflow_session_key_is_safe_for_meeting_ids():
    key = server._wf_task_session_key("main", "meeting-for-ai", "meeting:abc-123:participant:main")
    assert key == "agent-main-openai-wf-meeting-meeting"
    assert ":" not in key
    assert server._agent_id_from_session_key(key) == "main"


if __name__ == "__main__":
    test_executable_meeting_create_persists_events_and_projects_active()
    test_executable_meeting_occupancy_transition_and_history_projection()
    test_executable_meeting_completion_awards_participant_xp_once()
    test_meeting_participant_xp_skips_non_completed_and_invalid_participants()
    test_phase3_pause_resume_cancel_controls_project_previous_stage_and_history()
    test_phase3_active_executable_meeting_projects_to_status_canvas_meetings()
    test_phase3_decision_window_timeout_setting_defaults_and_clamps()
    test_phase3_decision_window_can_be_configured_per_meeting()
    test_phase3_targeted_question_in_decision_window_does_not_advance_round()
    test_phase3_late_formal_provider_response_is_ignored_after_cancel()
    test_phase3_late_targeted_provider_response_is_ignored_after_continue()
    test_phase3_no_consensus_arbitration_decide_end_and_continue()
    test_phase3_final_round_without_disagreement_auto_summarizes_on_timeout()
    test_phase3_moderator_resolution_policy_auto_closes_disagreement()
    test_executable_meeting_events_after_and_reconcile()
    test_phase2_fake_provider_runs_incremental_meeting_to_completion()
    test_phase2_prompt_context_modes()
    test_phase2_provider_timeout_is_configurable_for_real_calls()
    test_phase3_active_projection_includes_live_transcript_and_pending_calls()
    test_phase3_provider_timeout_skip_continues_meeting()
    test_phase3_user_intervention_is_projected_and_passed_to_incremental_prompt()
    test_phase3_agenda_change_updates_future_prompt_and_projection()
    test_phase3_provider_envelope_is_unwrapped_and_structured_turn_is_projected()
    test_phase3_structured_provider_output_is_saved_without_raw_envelope_in_transcript()
    test_phase3_executable_end_uses_moderator_summary_without_manual_summary()
    test_phase3_moderator_failure_user_takeover_and_replacement()
    test_legacy_meeting_end_still_requires_manual_summary()
    test_phase2_openclaw_workflow_session_key_is_safe_for_meeting_ids()
    print("ok")
