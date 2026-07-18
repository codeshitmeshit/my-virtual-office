import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const skillPath = new URL("../skills/vo-project-authoring/SKILL.md", import.meta.url);
const metadataPath = new URL("../skills/vo-project-authoring/agents/openai.yaml", import.meta.url);
const [skill, metadata] = await Promise.all([
  readFile(skillPath, "utf8"),
  readFile(metadataPath, "utf8"),
]);

assert.match(skill, /^---\nname: vo-project-authoring\n/m);
assert.match(skill, /仅当用户明确调用 `\$vo-project-authoring`/);
assert.match(metadata, /allow_implicit_invocation:\s*false/);

for (const required of [
  "/api/agents",
  "/skills/vo-project-authoring/SKILL.md",
  "responsibleActor",
  "executorActor",
  "reviewerRecommendation",
  "high_risk",
  "cross_team",
  "critical_delivery",
  "/api/agent/project-authoring/projects",
  "summaryDigest",
  "projectGrantSecret",
  "/grant-status",
  "/maintenance",
  "strict_confirmation",
  "autonomous",
  "X-VO-Management-Token",
  "vo-project-workflow",
]) {
  assert.ok(skill.includes(required), `missing project-authoring contract: ${required}`);
}

assert.match(skill, /只保存在当前运行内存中/);
assert.match(skill, /不写入文件、日志、项目、聊天消息或命令输出摘要/);
assert.match(skill, /不自动启动项目、任务、review、验收、取消或会议/);
assert.match(skill, /展示方案后停止，不调用创建 API/);
assert.match(skill, /语义变化必须重新确认并使用新 key/);
assert.match(skill, /只用这些只读 HTTP GET 获取 roster/);
assert.match(skill, /不要运行内联 Python/);
assert.match(skill, /不要调用 `_office_agent_lookup`/);
assert.match(skill, /用户确认前只允许读取本地 skill 和 Agent roster/);
assert.match(skill, /不要在确认前调用项目列表、项目详情、项目创建、维护、执行或 review 相关接口/);
assert.match(skill, /尤其不要用 `GET \/api\/projects` 做预检查/);
assert.match(skill, /只有在用户确认当前自然语言方案后，才进入本阶段/);
assert.ok(!skill.includes("/api/agent/project-authoring/requests"));
assert.ok(!skill.includes("PYTHONPATH=app"));

console.log("VO project authoring skill contract passed");
