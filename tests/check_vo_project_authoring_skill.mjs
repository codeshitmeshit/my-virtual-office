import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const skillPath = new URL("../skills/vo-project-authoring/SKILL.md", import.meta.url);
const metadataPath = new URL("../skills/vo-project-authoring/agents/openai.yaml", import.meta.url);
const [skill, metadata] = await Promise.all([
  readFile(skillPath, "utf8"),
  readFile(metadataPath, "utf8"),
]);

assert.match(skill, /^---\nname: vo-project-authoring\n/m);
assert.match(skill, /或用自然语言要求在当前本地 Virtual Office 中创建、复用、周期化项目/);
assert.match(metadata, /allow_implicit_invocation:\s*true/);
assert.match(metadata, /When the user asks to create, reuse, or schedule a VO project/);

for (const required of [
  "/api/agents",
  "/skills/vo-project-authoring/SKILL.md",
  "responsibleActor",
  "executorActor",
  "reviewerRecommendation",
  "projectExecutionEnabled",
  "projectExecutionStartMode",
  "Project Execution：已启用（默认） | 仅跟踪（用户明确要求不执行）",
  "默认执行 Agent：",
  "启动模式：continuous",
  "周期执行模式：不适用 | 仅创建实例（create_only） | 创建并自动执行（create_and_execute）",
  "结构化 `checklist`",
  "任务清单",
  "| # | 任务名称 | 所属列 | 任务输入 | 任务输出 | 执行说明 | 风险/讨论 | 验收标准 | 负责人 | 执行人 | Reviewer |",
  "high_risk",
  "cross_team",
  "critical_delivery",
  "/api/agent/project-authoring/projects",
  "summaryDigest",
  "summaryText",
  "/maintenance",
  "/api/agent/projects/PROJECT_ID/scheduled-cron",
  "strict_confirmation",
  "autonomous",
  "X-VO-Management-Token",
  "vo-project-workflow",
  "维护接口调用样例",
  "\"operation\": \"update_project\"",
  "\"operation\": \"create_task\"",
  "\"operation\": \"update_task\"",
  "\"operation\": \"reassign_roles\"",
  "\"operation\": \"delete_task\"",
  "\"operation\": \"archive_project\"",
  "\"operation\": \"workspace_change\"",
  "\"operation\": \"maintenance_mode_change\"",
  "\"operation\": \"update_recurrence\"",
  "强制流程门禁",
  "S0 读取指南",
  "S1 获取角色",
  "S2 输出方案",
  "S3 等待用户确认",
  "S4 构造请求",
  "S5 创建项目",
  "修改前相似功能检查",
  "/api/projects/PROJECT_ID",
  "GET /api/projects/PROJECT_ID/scheduled-cron",
  "发现已经有类似配置/任务",
  "仍然新增一个独立项",
]) {
  assert.ok(skill.includes(required), `missing project-authoring contract: ${required}`);
}

assert.match(skill, /维护已有项目统一使用下文的“用户确认方案”路径/);
assert.match(skill, /可复用是项目属性，不是模板属性/);
assert.match(skill, /默认不要创建可复用模板/);
assert.match(skill, /只有用户明确说“创建模板 \/ 保存成模板 \/ 复用模板 \/ template\.mode=create \/ 引用某个 templateId”等等价语义/);
assert.match(skill, /不要使用管理面 `\/api\/projects\/PROJECT_ID\/scheduled-cron`/);
assert.match(skill, /VO 已保存并启用项目级定时配置/);
assert.match(skill, /不要把 Gateway token、Gateway registration、`pending_gateway_registration` 或 `reconciliationRequired` 当作用户需要处理的事项/);
assert.match(skill, /到点后应复用原 Project Execution 启动入口/);
assert.match(skill, /不索取、读取、缓存或传递 project grant secret/);
assert.match(skill, /不自动启动项目、任务、review、验收、取消或会议/);
assert.match(skill, /展示方案后停止，不调用创建 API/);
assert.match(skill, /语义变化必须重新确认并使用新 key/);
assert.match(skill, /必须使用下面的 Markdown 模板和字段顺序/);
assert.match(skill, /未知项写“待确认”/);
assert.match(skill, /每个任务必须明确输入、输出、执行说明和验收标准/);
assert.match(skill, /任务输入、输出、执行说明、风险和讨论只进入任务 `description` 的结构化段落/);
assert.match(skill, /Reviewer 默认策略：不指定/);
assert.match(skill, /Agent 创建默认写 `projectExecutionEnabled=true`/);
assert.match(skill, /只有用户明确要求“仅跟踪\/不执行”时才写 false/);
assert.match(skill, /创建动作本身绝不自动启动/);
assert.match(skill, /周期项目必须单独展示并确认 `create_only` 或 `create_and_execute`/);
assert.match(skill, /每个任务表格中的“验收标准”必须逐项转换为该任务的结构化 `checklist`/);
assert.match(skill, /输入、输出模板、执行步骤、会议行动项、风险、讨论点和上下文分别写入 `description` 或对应 meeting 字段，不得自动提升为 checklist/);
assert.match(skill, /请确认是否按以上方案创建真实项目/);
assert.match(skill, /“需要你确认的点”只列真正会影响创建结果的未决事项/);
assert.match(skill, /模板\/复用配置默认写“无”/);
assert.match(skill, /创建请求必须同时携带该精确文本和 digest/);
assert.match(skill, /后端会拒绝缺少 `summaryText`、未使用固定确认模板或 digest 不匹配的请求/);
assert.match(skill, /只用这些只读 HTTP GET 获取 roster/);
assert.match(skill, /不要运行内联 Python/);
assert.match(skill, /不要调用 `_office_agent_lookup`/);
assert.match(skill, /用户确认前只允许读取本地 skill 和 Agent roster/);
assert.match(skill, /创建新项目时，不要在确认前调用项目列表、项目详情、项目创建、维护、执行或 review 相关接口/);
assert.match(skill, /维护已有项目时，如果用户已经给出项目 ID，或必须判断“往哪个已有项目修改”，确认前可以读取目标项目现状和该项目必要配置/);
assert.match(skill, /不要用全量项目列表扩大范围/);
assert.match(skill, /在展示维护方案前，必须先读取目标项目现状/);
assert.match(skill, /如果已存在类似功能，不要直接新增或重复配置/);
assert.match(skill, /只有在用户确认当前自然语言方案后，才进入本阶段/);
assert.match(skill, /必须按下面状态机顺序执行，不得跳步、合并步骤/);
assert.match(skill, /用“我已理解用户意图”替代确认/);
assert.match(skill, /创建新项目时，S3 之前不得调用项目列表、项目详情或项目写接口/);
assert.match(skill, /维护已有项目时，S3 之前只可读取目标项目和必要配置，不得调用任何写接口/);
assert.match(skill, /S5 之前不得提交 `confirmed=true`/);
assert.ok(!skill.includes("/api/agent/project-authoring/requests"));
assert.ok(!skill.includes("PYTHONPATH=app"));

console.log("VO project authoring skill contract passed");
