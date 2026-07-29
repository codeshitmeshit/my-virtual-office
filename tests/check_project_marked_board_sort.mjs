#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const projectsJs = readFileSync(new URL('../app/projects.js', import.meta.url), 'utf8');

assert.ok(
  projectsJs.includes('function sortProjectColumnTasks(tasks)'),
  'projects.js should centralize project board task sorting'
);

assert.ok(
  projectsJs.includes('isStagePipelineProject(state.currentProject)') &&
    projectsJs.includes('task && task.executionStage') &&
    projectsJs.includes('const tasks = sortProjectColumnTasks(allTasks.filter(t => t.columnId === col.id));'),
  'marked stage-pipeline board columns should sort by executionStage instead of legacy order alone'
);

assert.ok(
  projectsJs.includes('Array.isArray(d.blockers) && d.blockers.length') &&
    projectsJs.includes("title: '项目无法启动'"),
  'marked stage-pipeline start failures should surface preflight blockers visibly'
);

console.log('marked project board sort checks passed');
