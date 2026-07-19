import fs from 'fs';
import assert from 'assert';

const index = fs.readFileSync('app/index.html', 'utf8');
const js = fs.readFileSync('app/agent-guide.js', 'utf8');
const style = fs.readFileSync('app/style.css', 'utf8');
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const catalog = fs.readFileSync('skills/catalog.md', 'utf8');
const operatingGuidelines = fs.readFileSync('skills/vo-operating-guidelines/SKILL.md', 'utf8');
const projectWorkflow = fs.readFileSync('skills/vo-project-workflow/SKILL.md', 'utf8');
const meetingRequestsReference = fs.readFileSync('skills/vo-operating-guidelines/references/meeting-requests.md', 'utf8');

const expectedSkills = [
  'vo-operating-guidelines',
  'vo-agent-communication',
  'vo-codex-communication',
  'vo-browser-control',
  'vo-agent-workspace',
  'vo-project-authoring',
  'vo-project-workflow',
  'vo-meeting-execution',
];

assert.ok(index.includes('id="agent-guide-toggle"'), 'toolbar should include Agent Guide button');
assert.ok(index.includes('onclick="openAgentGuide()"'), 'toolbar button should open Agent Guide');
assert.ok(index.includes('id="agentGuideModal"'), 'index should include Agent Guide modal');
assert.ok(index.includes('id="agentGuideSkillDetailModal"'), 'index should include Agent Guide skill detail modal');
assert.ok(index.includes('id="agent-guide-skill-detail-content"'), 'detail modal should include a SKILL.md content area');
assert.ok(index.includes('agent-guide.js'), 'index should load focused Agent Guide JS module');

const modalStart = index.indexOf('<!-- Agent Guide Modal -->');
const modalEnd = index.indexOf('<!-- Skill Editor Sub-Modal -->');
assert.ok(modalStart >= 0 && modalEnd > modalStart, 'Agent Guide modal slice should be present');
const modalHtml = index.slice(modalStart, modalEnd);
assert.ok(!modalHtml.includes('type="search"'), 'Agent Guide should not include keyword search');
assert.ok(!modalHtml.includes('openSkillEditor'), 'Agent Guide should not expose skill editing');
assert.ok(!modalHtml.includes('handleSkillUpload'), 'Agent Guide should not expose skill upload');
assert.ok(!modalHtml.includes('saveSkill'), 'Agent Guide should not expose skill saving');
assert.ok(js.includes('agent_guide_sections_label'), 'Agent Guide should render section headings parsed from SKILL.md');
assert.ok(js.includes('agent-guide-details'), 'Agent Guide should include a visible details section per card');
assert.ok(!js.includes('<details'), 'Agent Guide details should not be hidden behind a collapsible disclosure');
assert.ok(!js.includes('<summary'), 'Agent Guide should not render a misleading details toggle');
assert.ok(js.includes('<div class="agent-guide-details">'), 'Agent Guide should show skill details directly by default');
assert.ok(js.includes('openAgentGuideSkillDetail'), 'Agent Guide should open a full SKILL.md detail modal');
assert.ok(js.includes("fetchText('/skills/catalog.md')"), 'Agent Guide should read the project VO skill catalog');
assert.ok(js.includes('parseFrontmatter'), 'Agent Guide should parse SKILL.md frontmatter from project files');
assert.ok(js.includes('parseSkill'), 'Agent Guide should derive card content from SKILL.md files');
assert.ok(js.includes('agent-guide-skill-detail-content'), 'Agent Guide should render full SKILL.md content into the detail modal');

for (const skill of expectedSkills) {
  assert.ok(catalog.includes(`/skills/${skill}/SKILL.md`), `catalog should expose ${skill}`);
  assert.ok(js.includes(`'${skill}'`), `Agent Guide category metadata should include ${skill}`);
  assert.ok(fs.existsSync(`skills/${skill}/SKILL.md`), `project skill file should exist for ${skill}`);
  const skillBody = fs.readFileSync(`skills/${skill}/SKILL.md`, 'utf8');
  assert.ok(!skillBody.includes('/home/wo/code/my-virtual-office'), `${skill} should not hardcode a non-current VO project path`);
}
assert.ok(!meetingRequestsReference.includes('/home/wo/code/my-virtual-office'), 'meeting request reference should not hardcode a non-current VO project path');

assert.ok(!js.includes('/Users/'), 'Agent Guide should not hardcode local absolute paths');
assert.ok(!js.includes('.codex/skills'), 'Agent Guide should not scan global Codex skill directories');
assert.ok(!js.includes('.agents/skills'), 'Agent Guide should not scan user agent skill directories');
assert.ok(!/recommend/i.test(js), 'Agent Guide JS should avoid recommendation behavior or copy');
assert.ok(!/推荐/.test(js), 'Agent Guide JS should avoid Chinese recommendation behavior or copy');

assert.ok(js.includes("var activeCategory = 'all'"), 'Agent Guide should default to all category');
assert.ok(js.includes('data-agent-guide-category'), 'Agent Guide should implement category filtering');
assert.ok(js.includes('getSkills'), 'Agent Guide should expose data for E2E inspection');
assert.ok(js.includes('getCategories'), 'Agent Guide should expose categories for E2E inspection');

assert.ok(style.includes('.agent-guide-modal'), 'Agent Guide modal should have dedicated styles');
assert.ok(style.includes('.agent-guide-cards'), 'Agent Guide cards should have dedicated styles');
assert.ok(style.includes('@media (max-width: 640px)'), 'Agent Guide should include narrow viewport styling');

const requiredLocaleKeys = [
  'agent_guide',
  'agent_guide_title',
  'agent_guide_intro',
  'agent_guide_empty',
  'agent_guide_purpose_label',
  'agent_guide_scenario_label',
  'agent_guide_details_summary',
  'agent_guide_details_label',
  'agent_guide_source_label',
  'agent_guide_sections_label',
  'agent_guide_loading',
  'agent_guide_no_description',
  'agent_guide_open_skill',
  'agent_guide_skill_detail_title',
  'agent_guide_skill_detail_loading',
  'agent_guide_skill_detail_error',
  'agent_guide_skill_path_label',
  'agent_guide_cat_all',
  'agent_guide_cat_operations',
  'agent_guide_cat_communication',
  'agent_guide_cat_browser',
  'agent_guide_cat_workspace',
  'agent_guide_cat_workflow',
  'agent_guide_cat_meeting',
];

for (const key of requiredLocaleKeys) {
  assert.ok(Object.hasOwn(en, key), `English locale should include ${key}`);
  assert.ok(Object.hasOwn(zh, key), `Chinese locale should include ${key}`);
}

assert.ok(!/recommend/i.test(en.agent_guide_intro), 'English intro should not claim recommendation');
assert.ok(!/推荐/.test(zh.agent_guide_intro), 'Chinese intro should not claim recommendation');

assert.ok(operatingGuidelines.includes('VO_REMOTE_CALLER'), 'VO endpoint guidance should require an explicit remote-caller signal');
assert.ok(operatingGuidelines.includes(': "${VO_BASE_URL:?VO_BASE_URL is required for an explicitly remote caller}"'), 'remote callers should provide an explicit base URL');
assert.ok(operatingGuidelines.includes('VO_BASE_URL="http://127.0.0.1:${VO_PORT:-8090}"'), 'local callers should always derive a loopback base URL');
assert.ok(!operatingGuidelines.includes('VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:'), 'local callers must not inherit an external base URL');
assert.ok(operatingGuidelines.includes('/skills/vo-project-authoring/SKILL.md'), 'project authoring should route to the authoring skill');
assert.ok(operatingGuidelines.includes('自然语言要求创建、复用、周期化 VO 项目'), 'natural-language project creation should route to authoring skill');
assert.ok(operatingGuidelines.includes('不要先用普通 Codex 流程读取本地项目文件、运行 Python、查询 `/api/projects` 或自行判断“已存在”'), 'authoring preflight should not bypass the skill with ordinary Codex checks');
assert.ok(operatingGuidelines.includes('/skills/vo-project-workflow/SKILL.md'), 'project execution should remain with the workflow skill');
assert.match(operatingGuidelines, /项目创作\/受控维护与项目执行\/review\/验收已分别路由/);
assert.ok(operatingGuidelines.includes('主入口只判断“是否需要会议”'), 'operating guidelines should keep meeting logic as routing only');
assert.ok(operatingGuidelines.includes('不内联会议申请 API、确认/拒绝流程或会议上下文规则'), 'meeting request details should not live in the main entry skill');
assert.ok(operatingGuidelines.includes('确定需要申请或查询 AI 会议时，停止在本文件展开细节'), 'main entry should route meeting requests to the reference file');
assert.ok(!operatingGuidelines.includes('自动推荐的上下文默认不会进入会议'), 'detailed meeting context rules should stay in meeting-requests reference');
assert.ok(projectWorkflow.includes('/api/agent/projects/PROJECT_ID/project-execution/start'), 'agent project execution should use the agent start endpoint');
assert.ok(projectWorkflow.includes('/api/agent/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start'), 'agent task execution should use the agent task start endpoint');
assert.ok(projectWorkflow.includes('X-VO-Agent-Action: project-execution'), 'agent execution examples should include the required action header');
assert.ok(projectWorkflow.includes('不索取、读取、缓存或传递 `X-VO-Management-Token`'), 'project workflow skill should not ask agents for management tokens');
assert.ok(operatingGuidelines.includes('## 用户确认优先级'), 'main VO entry should define confirmation priority for risky writes');
assert.ok(operatingGuidelines.includes('会改变 VO 项目结构、任务状态、会议状态或自动化策略'), 'main VO entry should require confirmation for state-changing operations');
assert.ok(operatingGuidelines.includes('提交可能影响项目状态的会议申请'), 'main VO entry should gate stateful meeting requests');
assert.ok(operatingGuidelines.includes('设置自动批准、自动执行、定时任务、长期项目或可复用项目策略'), 'main VO entry should gate automation policy changes');
assert.ok(projectWorkflow.includes('## 创建项目确认门禁'), 'project workflow should include project creation confirmation gate');
assert.ok(projectWorkflow.includes('确认草案至少包含：项目名称、目标、任务列表、每个任务的 assignee/executor/reviewer、会议触发点、是否创建模板、是否立即启动执行'), 'project workflow should define required draft fields');
assert.ok(projectWorkflow.includes('不把“规划/拆分/设计项目链路”的讨论当作创建授权'), 'project workflow should not treat planning language as creation authorization');
assert.ok(meetingRequestsReference.includes('## 2. 自动批准风险检查'), 'meeting request reference should include auto-approval risk gate');
assert.ok(meetingRequestsReference.includes('AI 不得在用户未确认的情况下触发可能自动开始的会议'), 'meeting request reference should block unconfirmed auto-start meetings');
assert.ok(meetingRequestsReference.includes('如果不确定服务端是否会自动批准，则不要提交会议申请'), 'meeting request reference should stop when auto-approval behavior is uncertain');

console.log('agent guide static checks passed');
