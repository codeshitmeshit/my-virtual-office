from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "vo-personal-assets" / "SKILL.md"
CATALOG = ROOT / "skills" / "catalog.md"
GUIDE = ROOT / "skills" / "vo-operating-guidelines" / "SKILL.md"


def _skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_has_manual_only_discovery_contract():
    text = _skill()
    assert "name: vo-personal-assets" in text
    assert "description: Use when" in text
    assert "owner" in text
    assert "手动" in text
    assert "/skills/vo-personal-assets/SKILL.md" in CATALOG.read_text(encoding="utf-8")
    assert "/skills/vo-personal-assets/SKILL.md" in GUIDE.read_text(encoding="utf-8")


def test_skill_keeps_draft_in_conversation_and_requires_exact_confirmation():
    text = _skill()
    for name in (
        "collectionDraft",
        "skippedTopics",
        "confirmedChanges",
        "sensitivityByEntry",
        "idempotencyKey",
    ):
        assert name in text
    assert "确认前零写入" in text
    assert "未确认草稿不持久化" in text
    assert "取消" in text
    assert "跳过" in text
    assert "停止" in text
    assert "修正" in text


def test_skill_uses_value_free_outline_and_never_management_credentials():
    text = _skill()
    assert "/api/agent/personal-assets/profile-outline" in text
    assert "profile-outline" in text
    assert "sensitive label" in text
    assert "value" in text
    assert "不索取、读取、缓存或传递 `X-VO-Management-Token`" in text


def test_skill_confirmed_write_is_idempotent_and_sensitive_is_not_authorization():
    text = _skill()
    assert "/api/agent/personal-assets/apply-confirmed-onboarding" in text
    assert "X-VO-Agent-Action: personal-assets" in text
    assert "X-VO-Agent-Id" in text
    assert "confirmationSummaryDigest" in text
    assert "SHA-256" in text
    assert "敏感 classification 不等于授权" in text
    assert "/skills/vo-human-decision/SKILL.md" in text
    assert "不依赖 HR 名册" in text


def test_skill_preserves_xml_prompt_boundary_when_a_provider_prompt_is_needed():
    text = _skill()
    assert "services.bridge_input_output_formatting" in text
    assert "key-value" in text
    assert "XML" in text
    assert "untrusted" in text
    assert "禁止用裸字符串拼接动态内容" in text


def test_skill_guides_basic_info_with_fixed_fields_and_two_fill_modes():
    text = _skill()
    for field in (
        "称呼",
        "常用语言",
        "所在时区",
        "当前职业或工作身份",
        "所在地区",
    ):
        assert field in text
    assert "默认采用逐项模式" in text
    assert "一次只问一个字段" in text
    assert "一次填写" in text
    assert "我应该如何称呼你" in text
    assert "不要反问 owner 自己设计基本信息字段" in text
    assert "只询问缺失项" in text


def test_skill_uses_one_grouped_feishu_form_and_keeps_confirmation_gate():
    text = _skill()
    assert "/api/agent/personal-assets/feishu-onboarding-form" in text
    assert "一张完整表单" in text
    assert "按类型分区" in text
    assert "基本信息、职业与 VO 方向、兴趣爱好、聊天偏好、办公室目标" in text
    assert "表单提交不等于确认写入" in text
    assert "待填写 → 处理中 → 已提交、等待确认" in text
    assert "处理中时锁定原表单" in text
    assert "HUMAN DECISIONS" in text


def test_skill_normalizes_and_enriches_before_confirmation_without_guessing():
    text = _skill()
    assert "确认前规范化" in text
    assert "原始填写" in text
    assert "规范化建议" in text
    assert "推导补充" in text
    assert "简体中文" in text
    assert "Asia/Shanghai" in text
    assert "所在地区本身仍保存为“上海”" in text
    assert "不猜测低置信度缺失值" in text
    assert "最终 `confirmedChanges`" in text
