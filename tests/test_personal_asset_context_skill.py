from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "vo-personal-context" / "SKILL.md"
CATALOG = ROOT / "skills" / "catalog.md"
GUIDE = ROOT / "skills" / "vo-operating-guidelines" / "SKILL.md"
ONBOARDING = ROOT / "skills" / "vo-personal-assets" / "SKILL.md"
OPENAI = ROOT / "skills" / "vo-personal-context" / "agents" / "openai.yaml"


def _skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_context_skill_is_discoverable_and_separate_from_onboarding():
    text = _skill()
    assert "name: vo-personal-context" in text
    assert "/skills/vo-personal-context/SKILL.md" in CATALOG.read_text(encoding="utf-8")
    assert "/skills/vo-personal-context/SKILL.md" in GUIDE.read_text(encoding="utf-8")
    assert "/skills/vo-personal-context/SKILL.md" in ONBOARDING.read_text(encoding="utf-8")
    assert "建档或编辑入口" in text
    assert "/skills/vo-personal-assets/SKILL.md" in text


def test_context_skill_supports_implicit_task_time_routing():
    metadata = OPENAI.read_text(encoding="utf-8")
    assert 'default_prompt: "Use $vo-personal-context' in metadata
    assert "allow_implicit_invocation: true" in metadata


def test_context_skill_requires_relevance_and_minimum_exact_scope():
    text = _skill()
    assert "实质改善" in text
    assert "默认不读取" in text
    assert "/api/agent/personal-assets/profile-outline" in text
    assert "/api/agent/personal-assets/request-context" in text
    assert "精确 entry ID" in text
    assert "不要请求 `*`" in text
    assert "完整档案" in text


def test_context_skill_routes_sensitive_reads_through_decisions():
    text = _skill()
    assert "普通条目和敏感条目拆成不同请求" in text
    assert "decision_required" in text
    assert "status=denied" in text
    assert "HUMAN DECISIONS" in text
    assert "超时默认拒绝" in text
    assert "只暂停依赖这些值的分支" in text


def test_context_skill_allows_every_runtime_agent_without_hr_gate():
    text = _skill()
    assert "X-VO-Agent-Action: personal-assets" in text
    assert "X-VO-Agent-Id" in text
    assert "任意具备有效运行时 ID 的本地 VO Agent" in text
    assert "不依赖 HR 名册" in text
    assert "不得索取、读取、缓存或传递 `X-VO-Management-Token`" in text


def test_context_skill_applies_context_without_global_injection_or_silent_write():
    text = _skill()
    assert "当前 owner 的直接指令优先" in text
    assert "不在最终回复、日志、项目 artifact 或跨 Agent 消息中暴露" in text
    assert "本 Skill 默认只读" in text
    assert "不要用 `suggest-change` 假装更新既有条目" in text
    assert "services.bridge_input_output_formatting" in text
    assert "XML" in text
    assert "untrusted" in text
