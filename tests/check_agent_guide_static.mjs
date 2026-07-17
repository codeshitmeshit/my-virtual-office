import fs from 'fs';
import assert from 'assert';

const index = fs.readFileSync('app/index.html', 'utf8');
const js = fs.readFileSync('app/agent-guide.js', 'utf8');
const style = fs.readFileSync('app/style.css', 'utf8');
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const catalog = fs.readFileSync('skills/catalog.md', 'utf8');
const operatingGuidelines = fs.readFileSync('skills/vo-operating-guidelines/SKILL.md', 'utf8');

const expectedSkills = [
  'vo-operating-guidelines',
  'vo-agent-communication',
  'vo-codex-communication',
  'vo-browser-control',
  'vo-agent-workspace',
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
}

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

console.log('agent guide static checks passed');
