import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');
const stageDispatch = readFileSync(join(root, 'app/services/project_stage_dispatch.py'), 'utf8');
const server = readFileSync(join(root, 'app/server.py'), 'utf8');
const splitProjects = readFileSync(join(root, 'app/server_services/projects.py'), 'utf8');

assert.ok(
  projectsJs.includes('const markedPipeline = isStagePipelineProject(p);'),
  'project execution project-start action should branch on marked pipeline projects'
);
assert.ok(
  projectsJs.includes("const startOpts = markedPipeline ? { ...opts, stagePipeline: true, restartPipeline: false } : opts;"),
  'marked project project-start calls should request the API without legacy restart mode'
);
assert.ok(
  projectsJs.includes('if (opts.stagePipeline !== true)'),
  'project-start API helper should omit mode/restartPipeline when marked pipeline mode is requested'
);
assert.ok(
  projectsJs.includes("if (markedPipeline) return `<button class=\"proj-btn proj-btn-sm\" disabled>"),
  'marked project task detail should not expose task-level start controls'
);
assert.ok(
  projectsJs.includes("if (isStagePipelineProject(p)) {\n            toast('编排项目不支持旧的重启流水线入口', 'error');"),
  'marked project restart action should be blocked in the frontend'
);
assert.ok(
  stageDispatch.includes('legacy_keys = [key for key in ("mode", "startMode", "restartPipeline") if key in body]'),
  'stage dispatcher should detect legacy marked-project start payload fields'
);
assert.ok(
  stageDispatch.includes('"code": "marked_project_legacy_start_payload_forbidden"'),
  'stage dispatcher should reject legacy marked-project start payload fields'
);
assert.ok(
  server.includes('"code": "marked_project_task_start_forbidden"'),
  'server task-level start should reject marked projects'
);
assert.ok(
  splitProjects.includes('server_handler = _server_callable("_handle_marked_project_execution_project_start")'),
  'split project service should delegate marked project-level start to the stage dispatcher handler'
);
assert.ok(
  splitProjects.includes('"code": "marked_project_task_start_forbidden"'),
  'split project service task-level start should reject marked projects'
);

console.log('marked project legacy start removal checks passed');
