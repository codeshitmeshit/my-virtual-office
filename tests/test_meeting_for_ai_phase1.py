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
            assert ran["meeting"]["stage"] == "completed"
            events = ran["events"]
            turns = [e for e in events if e["type"] == "participant_turn"]
            assert len(turns) == 6
            assert ran["meeting"]["result"]["summary"]
            assert set(ran["meeting"]["result"]["contributions"]) == {"main", "hermes-default", "codex-local"}
            projected = server._exec_meeting_project_history(ran["meeting"], events)
            assert len(projected["transcript"]) == 6
            assert projected["transcript"][0]["stage"] == "active_opening"
            assert projected["transcript"][0]["speaker"] == "main"
            assert projected["transcript"][-1]["round"] == 1

            main_prompts = [p["prompt"] for p in prompts if p["speaker"] == "main"]
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
                server._save_exec_meeting_store(store)

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["lastEventSequence"] == pending["sequence"]
            assert active["pendingCalls"][0]["speaker"] == "main"
            assert active["pendingCalls"][0]["promptChars"] == 123
            assert active["transcript"] == []

            with server._EXEC_MEETING_LOCK:
                store = server._load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                server._append_exec_meeting_event(
                    store,
                    meeting,
                    "participant_turn",
                    actor={"type": "agent", "id": "main"},
                    payload={
                        "speaker": "main",
                        "text": "Live opening statement",
                        "ok": True,
                        "stage": "active_opening",
                        "round": 0,
                        "providerRef": {"providerKind": "fake", "agentId": "main"},
                        "durationMs": 7,
                        "inReplyToSequence": pending["sequence"],
                    },
                )
                server._save_exec_meeting_store(store)

            active = [m for m in server._meeting_active_projection() if m.get("id") == meeting_id][0]
            assert active["pendingCalls"] == []
            assert len(active["transcript"]) == 1
            assert active["transcript"][0]["speaker"] == "main"
            assert active["transcript"][0]["text"] == "Live opening statement"
        finally:
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
            turns = [e for e in ran["events"] if e["type"] == "participant_turn"]
            assert turns
            first_payload = turns[0]["payload"]
            assert first_payload["structured"]["position"] == "main supports the plan"
            assert first_payload["structured"]["disagreements"] == ["Do not expose provider envelope"]
            assert "run-main" in first_payload["providerRaw"]
            assert "run-main" not in first_payload["text"]

            projected = server._exec_meeting_project_history(ran["meeting"], ran["events"])
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
            ended = server._handle_meeting_end({"id": meeting_id, "endedBy": "user"})
            assert ended["ok"] is True
            assert ended["meeting"]["stage"] == "completed"
            assert ended["meeting"]["result"]["summary"] == "Moderator generated summary."
            assert ended["meeting"]["result"]["actionItems"] == [{"owner": "main", "item": "Publish meeting notes"}]
            events = ended["events"]
            assert any(e["type"] == "provider_call_started" and (e["payload"] or {}).get("purpose") == "meeting_result" for e in events)
            assert any(e["type"] == "meeting_result" and (e["payload"] or {}).get("moderator") == "main" for e in events)
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
    test_executable_meeting_events_after_and_reconcile()
    test_phase2_fake_provider_runs_incremental_meeting_to_completion()
    test_phase2_prompt_context_modes()
    test_phase2_provider_timeout_is_configurable_for_real_calls()
    test_phase3_active_projection_includes_live_transcript_and_pending_calls()
    test_phase3_user_intervention_is_projected_and_passed_to_incremental_prompt()
    test_phase3_provider_envelope_is_unwrapped_and_structured_turn_is_projected()
    test_phase3_structured_provider_output_is_saved_without_raw_envelope_in_transcript()
    test_phase3_executable_end_uses_moderator_summary_without_manual_summary()
    test_legacy_meeting_end_still_requires_manual_summary()
    test_phase2_openclaw_workflow_session_key_is_safe_for_meeting_ids()
    print("ok")
