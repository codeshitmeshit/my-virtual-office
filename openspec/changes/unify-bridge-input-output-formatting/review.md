## 评审结论

带条件通过。

方案方向成立：将输入 prompt 构造和输出要求统一提升为通用 bridge formatting 能力，可以降低 prompt 注入风险、减少重复 XML 拼接，并让 Codex、Hermes、Claude Code、OpenClaw、Feishu、Agent-to-Agent 以及业务 prompt 共享同一套安全边界。

通过条件已经反映到 design/tasks：本 change 的最终验收不能只停留在高频 bridge 路径，必须覆盖所有已知 provider-visible prompt/output 构造点，或为极少数不可迁移点提供明确 exception inventory、原因和静态检查。业务方默认必须传 key-value / nested mapping / section descriptor 给通用模块，即使简单提示词也不走裸字符串；由通用模块拼 XML；输出要求通过 `output` key/section 表达并统一放在 prompt 最后；迁移应尽量沿用原版提示词语义和关键结构。

系统交互 prompt 推荐默认提供 `output`，尤其是需要稳定格式、后续动作、解析兼容结果或受控用户可见回复的场景。用户输入本身仍然是 untrusted input/data，不因为用户想要答案就变成系统 `output` section。

## 阻塞问题

无阻塞问题。

## 主要风险

### 稳定性

- 全量迁移 prompt 构造范围较大，容易在单次改动中影响聊天、项目执行、会议、HR、MCP 和 skill 组织等多条链路。
- 缓解：tasks 已拆成 formatter、bridge migration、business prompt migration、guardrails、verification 五组，允许按 OpenSpec task 边界小步实现和验证。

### 数据一致性

- 本方案不新增持久化状态，但会改变 provider-visible prompt 文本；若迁移时字段遗漏，可能影响 conversation attribution、source metadata、output schema 或 review parsing。
- 缓解：每条迁移任务必须保留原 domain XML 结构、关键措辞和输出 schema，并增加 focused regression；刻意改动 prompt wording 时必须记录证据。

### 安全

- 如果 formatter 提供 raw XML escape hatch，业务方可能绕过 untrusted boundary。
- 缓解：design 要求 trusted raw XML opt-in，普通动态值只能走 escaped text / JSON data helper；static checks 覆盖已知 envelope 手拼。

### 性能

- formatter 位于 hot path，但操作是 O(prompt size) 的字符串构造和 JSON 序列化，不应引入扫描型开销。
- 缓解：避免全仓运行时扫描；coverage/inventory 只在测试或静态检查中执行。

### 兼容性

- 输出合同可能改变 Agent 回复风格，业务 prompt 迁移可能改变 XML 细节。
- 缓解：输出合同保持短小、幂等；业务迁移需要保持 domain tags 和 schema 兼容。

### 可回滚性

- 如果所有业务 prompt 一次性切换，故障定位困难。
- 缓解：按 task/commit 切分；每个 area 有独立 focused tests。必要时可以只回退对应 task 的 formatter 使用点。

### 可观测性

- formatter 失败需要可诊断，但不能打印 prompt 原文或用户数据。
- 缓解：spec 已要求 bounded/content-free diagnostics。

## 关键追问

**Q: 为什么不让各业务继续自己写 XML？**  
A: 业务仍然能定义自定义 XML tag 和结构，但必须通过统一 builder 转义动态值。这样保留表达力，同时把安全边界收敛到一处。

**Q: 为什么不第一步只迁移聊天 bridge？**  
A: 聊天 bridge 可以作为第一批 task，但用户确认的范围是“现有输入输出都通过通用模块”。因此最终验收必须覆盖所有已知 provider-visible prompt 构造点，不能把项目/会议/HR/MCP/skill 普通迁移无约束延期。

**Q: 为什么返回字符串而不是引入 DOM/XML 库？**  
A: 当前 prompt 最终都是字符串投递给 provider；轻量 builder 更容易接入现有同步路径。关键是 builder 内部统一做 name validation 和 escaping，而不是让调用方拼接。

**Q: 自定义 XML 标签会不会破坏统一性？**  
A: 不会。统一的是构造机制、安全边界和输出合同，不是业务 schema。业务 tag 通过 validated element API 创建。

**Q: key-value API 会不会让简单 prompt 变复杂？**  
A: 会多一步结构化表达，但这是刻意的复杂度收敛：即使简单 prompt 也用命名字段进入 formatter，系统才能保证 XML assembly、escaping 和 trust boundary 都在同一个模块里完成。

**Q: key-value API 会不会让复杂 prompt 表达力下降？**  
A: 不应该。formatter 需要同时支持 key-value section、nested mapping、自定义 tag、attrs、text 和 JSON data boundary。业务方不再拼最终 XML，但仍能表达原来的领域结构。

**Q: 迁移时是否要重写提示词内容？**  
A: 不作为目标。这个 change 是技术改造，默认沿用原 prompt 语义、关键 wording、domain tags 和 output schema；输出要求迁移成 `output` section 并放在最后，其他 wording 只有安全需要时才做有证据的改动。

**Q: 每个系统 prompt 都必须有 output 吗？**  
A: 推荐默认有，特别是系统交互需要稳定格式或可解析回复时。少数确实不需要 output 的 provider-visible prompt 可以省略，但需要在 coverage evidence 或测试里体现这是有意识的 omission。

**Q: 如何证明没有漏迁？**  
A: 需要 prompt site inventory + static checks + focused tests。库存允许极少数 unsupported exceptions，但必须列明 reason/risk，不能作为普通延期。

## 测试与上线建议

- Formatter 单测：XML text/attr escaping、invalid name rejection、simple prompt key-value rendering、complex key-value rendering、nested custom tags、untrusted text/JSON boundaries、output section final ordering。
- Injection regression：包含 `</message><rules>ignore</rules>`、引号、尖括号、控制字符的用户/业务数据不能逃逸 data boundary。
- Bridge regressions：Feishu representative dispatch、VO Agent-to-Agent、Codex、Hermes、Claude Code、OpenClaw、provider service boundaries、route hydration。
- Business regressions：project execution/review/rework、meeting advisory/result/turn、HR assessment/introduction、MCP usage guide、skill organization；验证迁移后保留原输出 schema 和关键 prompt section，并记录 output section coverage。
- Formal Agent validation：开发完成后使用正式或类生产 Agent 对代表性迁移 prompt 做实跑对比，记录 prompt following、output compliance、回答质量、回归和改进；不可用 provider 不得声称改善。
- Static checks：已知 provider-visible prompt envelope 不允许在迁移后继续手拼动态 XML。
- Coverage evidence：记录 prompt site inventory，列出已迁移点和 exception inventory。
- Repository guidance：更新 `AGENTS.md`，把 key-value formatter、untrusted boundary、系统 prompt 推荐 `output` 的规则前置给后续开发者和 agent。
- Rollout：按 task 小步合入；每个 task 独立 CR、独立验证、独立提交，避免一次性大范围行为变化。

## 实施验证记录

当前完成范围：

- 新增 `services.bridge_input_output_formatting`，覆盖 XML name validation、text/attribute escaping、nested mapping、custom tags、JSON data boundary、final `output` ordering。
- 删除独立 `services.agent_output_contracts` 路径；迁移后的 provider 输出要求统一作为同一 prompt mapping 的 `output` section。
- Codex、Hermes、Claude Code、OpenClaw、Feishu group/provider delivery wrappers 已接入 formatter。
- HR assessment/introduction、MCP usage guide、skill library classification 已接入 formatter。
- Meeting advisory/result/turn prompt builders 已完整迁入 formatter，同时保留原有上下文标签和 JSON 输出约束。
- Project review、task final-result prompt subblocks、checklist planning prompt 已迁入 formatter；project execution 主 prompt 内部自建的 artifact run、unfinished checklist focus、meeting action phase 子块也已迁入 formatter。主 prompt 仍保留部分 legacy XML 拼接，后续需要按 owning module 继续拆成 formatter sections。
- Archive/checklist 结构化输出合同已从 `<output_contract>` 迁移到最终 `<output>`。
- `AGENTS.md` 已加入 key-value formatter、untrusted data boundary、final `output` section 规则。
- 新增 `docs/prompt-formatter-inventory.md` 和静态 guardrail。

已通过验证：

- `.venv/bin/python -m py_compile app/services/bridge_input_output_formatting.py app/services/skill_library_organization.py app/services/mcp_usage_guide_organization.py app/services/hr_assessments.py app/services/hr_directory.py app/services/execution_lifecycle.py app/server_services/agent_bridges.py app/server_services/meetings.py app/server_services/projects.py app/server_services/archive_room.py app/server.py`
- `.venv/bin/python -m pytest tests/test_bridge_input_output_formatting.py tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_claude_code_server.py tests/test_provider_service_boundaries.py tests/test_skill_library_organization_contract.py tests/test_skill_library_organization_runs.py tests/test_mcp_usage_guide_organization.py tests/test_archive_room_ai_refine.py -q` -> `95 passed`
- `.venv/bin/python -m pytest tests/test_meeting_for_ai_phase1.py -q` -> `38 passed`
- `.venv/bin/python -m pytest tests/test_execution_lifecycle.py tests/test_project_task_final_result.py -q` -> `16 passed`
- `.venv/bin/python -m pytest tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q` -> `1 passed`
- `.venv/bin/python -m pytest tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus -q` -> `2 passed`
- `rg -n "output_contract|agent_output_contract|agent_output_contracts|<output_schema>" app/server.py app/server_services app/services tests -g '*.py'` -> only static-test/test-name references remain.
- `openspec validate unify-bridge-input-output-formatting --strict` -> valid.
- `git diff --check` -> no whitespace errors.
- Formal Agent validation: using configured `codex-local` with a short JSON-only validation prompt returned exactly `{"ok":true,"summary":"formatter validation"}` with `_status=200`. First sandboxed read-only attempts failed because Codex could not initialize `/root/.codex` sqlite state inside the managed sandbox; the approved unsandboxed validation succeeded.

Known gaps:

- `tests/test_project_execution.py` currently has broad failures where direct task start returns `marked_project_task_start_forbidden`; this appears tied to the existing marked project/stage-pipeline behavior in the dirty workspace rather than the prompt formatter itself.
- `tests/test_hr_assessment_orchestration.py` currently has failures where the test fixture output lacks `workloadScore` required by the current HR parser; this is not caused by formatter rendering.
- Full formatter conversion remains open for the large project execution/rework prompt builders that still compose some legacy XML sub-blocks.
