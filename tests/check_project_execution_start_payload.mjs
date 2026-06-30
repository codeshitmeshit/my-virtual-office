import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');

assert.ok(
  projectsJs.includes('resetExecutionContext: opts.resetExecutionContext === true'),
  'direct Project Execution start API payload should preserve resetExecutionContext'
);
assert.ok(
  projectsJs.includes("ProjMgr.projectExecutionStart('${task.id}', '', { resetExecutionContext: true })"),
  'task detail start buttons should request execution context reset'
);

console.log('project execution start payload check passed');
