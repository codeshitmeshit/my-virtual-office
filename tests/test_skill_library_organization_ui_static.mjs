import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync('app/index.html', 'utf8');
const css = fs.readFileSync('app/skills-library-organization.css', 'utf8');
const organization = fs.readFileSync(
  'app/skills-library-organization-ui.js',
  'utf8',
);
const library = fs.readFileSync('app/skills-library-ui.js', 'utf8');
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));

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

const organize = modal.indexOf('data-i18n="skill_library_smart_organize"');
const create = modal.indexOf('data-i18n="skill_library_create"');
const importSkill = modal.indexOf('data-i18n="skill_library_import"');
assert.ok(organize >= 0 && organize < create && create < importSkill);
assert.ok(modal.includes('class="skl-header-actions"'));
assert.ok(!modal.includes('openMcpRegistry'));
assert.ok(!modal.includes('mcp_registry_title'));

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

assert.ok(organization.includes("'skill_library_local_source'"));
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

for (const key of [
  'skill_library_subtitle',
  'skill_library_search',
  'skill_library_smart_organize',
  'skill_library_create',
  'skill_library_import',
  'skill_library_categories_label',
  'skill_library_list_label',
  'skill_library_detail_label',
  'skill_library_all_skills',
  'skill_library_failed_filter',
  'skill_library_failure_reason',
  'skill_library_failure_reason_unknown',
  'skill_library_failure_reason_aria',
  'skill_library_adjust_category',
  'skill_category_default',
  'skill_category_development_testing',
  'skill_category_collaboration_docs',
  'skill_category_project_process',
  'skill_category_operations_diagnostics',
  'skill_category_knowledge_content',
  'skill_organization_marker_running',
  'skill_organization_marker_completed',
  'skill_organization_marker_partial',
  'skill_organization_marker_failed',
  'skill_organization_marker_resolved',
  'skill_organization_move_failed',
]) {
  assert.equal(typeof en[key], 'string', `missing English locale key ${key}`);
  assert.equal(typeof zh[key], 'string', `missing Chinese locale key ${key}`);
}

console.log('skill library organization static UI contract ok');
