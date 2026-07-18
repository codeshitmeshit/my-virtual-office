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
  "任务清单",
  "| # | 任务名称 | 所属列 | 任务细节 | 验收标准 | 负责人 | 执行人 | Reviewer |",
  "high_risk",
  "cross_team",
  "critical_delivery",
  "/api/agent/project-authoring/projects",
  "summaryDigest",
  "summaryText",
  "projectGrantSecret",
  "/grant-status",
  "/maintenance",
  "strict_confirmation",
  "autonomous",
  "X-VO-Management-Token",
  "vo-project-workflow",
  "强制流程门禁",
  "S0 读取指南",
  "S1 获取角色",
  "S2 输出方案",
  "S3 等待用户确认",
  "S4 构造请求",
  "S5 创建项目",
]) {
  assert.ok(skill.includes(required), `missing project-authoring contract: ${required}`);
}

assert.match(skill, /只保存在当前运行内存中/);
assert.match(skill, /不写入文件、日志、项目、聊天消息或命令输出摘要/);
assert.match(skill, /不自动启动项目、任务、review、验收、取消或会议/);
assert.match(skill, /展示方案后停止，不调用创建 API/);
assert.match(skill, /语义变化必须重新确认并使用新 key/);
assert.match(skill, /必须使用下面的 Markdown 模板和字段顺序/);
assert.match(skill, /未知项写“待确认”/);
assert.match(skill, /Reviewer 默认策略：不指定/);
assert.match(skill, /请确认是否按以上方案创建真实项目/);
assert.match(skill, /“需要你确认的点”只列真正会影响创建结果的未决事项/);
assert.match(skill, /创建请求必须同时携带该精确文本和 digest/);
assert.match(skill, /后端会拒绝缺少 `summaryText`、未使用固定确认模板或 digest 不匹配的请求/);
assert.match(skill, /只用这些只读 HTTP GET 获取 roster/);
assert.match(skill, /不要运行内联 Python/);
assert.match(skill, /不要调用 `_office_agent_lookup`/);
assert.match(skill, /用户确认前只允许读取本地 skill 和 Agent roster/);
assert.match(skill, /不要在确认前调用项目列表、项目详情、项目创建、维护、执行或 review 相关接口/);
assert.match(skill, /尤其不要用 `GET \/api\/projects` 做预检查/);
assert.match(skill, /只有在用户确认当前自然语言方案后，才进入本阶段/);
assert.match(skill, /必须按下面状态机顺序执行，不得跳步、合并步骤/);
assert.match(skill, /用“我已理解用户意图”替代确认/);
assert.match(skill, /S3 之前不得调用任何项目状态或项目写接口/);
assert.match(skill, /S5 之前不得提交 `confirmed=true`/);
assert.ok(!skill.includes("/api/agent/project-authoring/requests"));
assert.ok(!skill.includes("PYTHONPATH=app"));

console.log("VO project authoring skill contract passed");
