import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');
const serverPy = readFileSync(join(root, 'app/server.py'), 'utf8');

assert.ok(
  projectsJs.includes("if (d.code === 'executor_required')") &&
  projectsJs.includes("title: '需要设置执行 Agent'") &&
  projectsJs.includes("cancelText: null"),
  'missing Project Execution executor should show a VO-style single-action prompt'
);
assert.ok(
  !projectsJs.includes('alert(text);'),
  'Project Execution executor prompt should not use native alert'
);
assert.ok(
  projectsJs.includes('const selectedTaskId = (d.selectedTask || {}).id || d.taskId;') &&
  projectsJs.includes('await refreshProjectExecutionProject(selectedTaskId);'),
  'project-level start/restart should focus the selected task after a missing executor prompt'
);
const restartAction = projectsJs.match(/async function projectExecutionProjectRestartAction[\s\S]*?\n    async function projectExecutionCancelActiveAction/);
assert.ok(restartAction, 'project pipeline restart action should exist');
assert.ok(
  restartAction[0].includes('await showConfirmDialog({') && !restartAction[0].includes('confirm('),
  'project pipeline restart should use the VO-style confirm dialog instead of native confirm'
);
assert.ok(
  projectsJs.includes('proj_exec_error_executor_required'),
  'missing executor prompt should explain how to set an executor agent'
);
assert.ok(
  !serverPy.includes('_project_execution_default_executor_agent_id'),
  'server must not auto-select a default executor agent when none is configured'
);

console.log('project execution executor required prompt check passed');
