import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');
const indexHtml = readFileSync(join(root, 'app/index.html'), 'utf8');

assert.ok(
  indexHtml.indexOf('project-orchestration-api.js') > -1,
  'project page must load the orchestration API client'
);
assert.ok(
  indexHtml.indexOf('project-orchestration-api.js') < indexHtml.indexOf('project-orchestration.js'),
  'orchestration API client must load before the modal runtime'
);
assert.ok(
  !indexHtml.includes('project-orchestration-task-dialog.js'),
  'orchestration task dialog should lazy-load so it does not block project page startup'
);
assert.ok(
  projectsJs.includes('id="proj-orchestration-open-btn" onclick="ProjMgr.openProjectOrchestration()">编排</button>` : `<div class="proj-exec-mode-group">'),
  'marked stage-pipeline projects should show the focused orchestration modal entry instead of start-mode radios'
);
assert.ok(
  projectsJs.includes("toast('编排项目不支持旧启动模式', 'error');"),
  'stage-pipeline projects should reject the old start-mode setter'
);
assert.ok(
  projectsJs.includes('function openProjectOrchestrationAction(opts = {})'),
  'project page should expose a thin orchestration modal entry function'
);
assert.ok(
  projectsJs.includes('api: projectOrchestrationApiAdapter()'),
  'project page should inject the focused orchestration API adapter into the modal'
);
assert.ok(
  projectsJs.includes('await refreshProjectExecutionProject((selectedTask && selectedTask(payload, result)) || null, { lightweight: true, skipAuxiliary: true });'),
  'orchestration modal actions should refresh the current project without blocking on auxiliary panels'
);
assert.ok(
  projectsJs.includes('function scheduleProjectIdleWork') && projectsJs.includes('scheduleProjectIdleWork(() => loadProjectBoardAuxiliaryData(id), 80)'),
  'project board auxiliary data should be deferred until after the first project render'
);
assert.ok(
  !projectsJs.includes('await Promise.allSettled(jobs);'),
  'project board auxiliary data should not wait for the slowest panel before updating'
);
assert.ok(
  projectsJs.includes('function openProjectOrchestrationTaskDialog')
    && projectsJs.includes('ProjectOrchestrationTaskDialog')
    && projectsJs.includes('projectOrchestrationCreateTask(p.id, taskBody)'),
  'modal-created tasks should collect task details before passing executionStage through the project-page add-task hook'
);
assert.ok(
  projectsJs.includes('openProjectOrchestration: openProjectOrchestrationAction'),
  'ProjMgr should expose the orchestration modal opener for the board button'
);
assert.ok(
  !projectsJs.includes('name="proj-exec-start-mode"') || projectsJs.includes("${markedPipeline ? `<button"),
  'start-mode radio markup must remain inside the non-marked-project branch'
);

console.log('project orchestration page wiring checks passed');
