import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync('app/index.html', 'utf8');
const css = fs.readFileSync('app/skills-library-organization.css', 'utf8');
const organization = fs.readFileSync(
  'app/skills-library-organization-ui.js',
  'utf8',
);
const library = fs.readFileSync('app/skills-library-ui.js', 'utf8');

const modal = html
  .split('<!-- Skills Library Modal -->', 2)[1]
  .split('<!-- MCP Registry Modal -->', 1)[0];

for (const id of [
  'skl-organize-btn',
  'skl-search-input',
  'skl-category-list',
  'skl-cards',
  'skl-detail',
]) {
  assert.ok(modal.includes(`id="${id}"`), `missing Skills Library node ${id}`);
}

const organize = modal.indexOf('智能整理');
const create = modal.indexOf('创建技能');
const importSkill = modal.indexOf('导入技能');
assert.ok(organize >= 0 && organize < create && create < importSkill);
assert.ok(modal.includes('class="skl-header-actions"'));
assert.ok(!modal.includes('openMcpRegistry'));
assert.ok(!modal.includes('MCP 注册表'));

assert.ok(
  html.includes('skills-library-organization.css?v=20260730'),
  'organization stylesheet must be loaded',
);
assert.ok(
  html.includes('skills-library-organization-ui.js?v=20260730'),
  'organization UI module must be loaded',
);
assert.ok(
  html.indexOf('skills-library-organization-ui.js?v=20260730') <
    html.indexOf('skills-library-ui.js?v=20260730'),
  'organization renderer must be available before CRUD bootstrap',
);

assert.match(
  css,
  /\.skl-workspace\s*\{[^}]*grid-template-columns:\s*minmax\([^;]+minmax\([^;]+minmax\(/s,
  'desktop Skills Library must use three columns',
);
assert.match(
  css,
  /\.skl-header-actions\s*\{[^}]*margin-left:\s*auto/s,
  'header actions must stay right aligned',
);
assert.match(css, /@media \(max-width:\s*900px\)/);
assert.match(css, /@media \(max-width:\s*620px\)/);
assert.match(
  css,
  /@media \(max-width:\s*620px\)[\s\S]*?\.skl-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  'mobile layout must collapse to one column',
);

assert.ok(organization.includes("detailField('来源', '本地技能库')"));
assert.ok(organization.includes("categoryId: 'all'"));
assert.ok(organization.includes('skl-category-item'));
assert.ok(organization.includes('skl-detail-actions'));
assert.ok(
  library.includes('window.SkillLibraryOrganizationUI.update(_sklLibraryData)'),
  'legacy CRUD module must delegate organization rendering',
);

for (const source of [modal, css, organization, library]) {
  assert.ok(!source.includes('团队空间'));
  assert.ok(!source.toLowerCase().includes('team space'));
}

console.log('skill library organization static UI contract ok');
