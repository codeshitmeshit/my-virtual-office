#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const projectsJs = readFileSync(new URL('../app/projects.js', import.meta.url), 'utf8');

assert.ok(
  projectsJs.includes("task.activeAttemptId && activeStates.has(String(task.executionState || '').toLowerCase())"),
  'stage-pipeline workflow chat should derive active task ids from task runtime state when status summaries are absent'
);

assert.ok(
  projectsJs.includes('project.orchestration || {}') &&
    projectsJs.includes('orchestration.state') &&
    projectsJs.includes('orchestration.pauseReason'),
  'stage-pipeline workflow sync should read orchestration state from the project detail payload'
);

assert.ok(
  projectsJs.includes('project.projectExecutionActive') &&
    projectsJs.includes("['running', 'dispatching', 'executing', 'reviewing', 'reworking'") &&
    projectsJs.includes('return stagePipelineWorkflowActive(project, projectActiveTaskIds(project));'),
  'stage-pipeline polling should stay active across inter-stage gaps without an active task attempt'
);

assert.ok(
  projectsJs.includes('activeTaskIds: Array.isArray(project && project.activeTaskIds)') &&
    projectsJs.includes('currentStage: orchestration.currentStage') &&
    projectsJs.includes('t.executionStage ||') &&
    projectsJs.includes("filter(item => item && item.source !== 'meeting_action_item'"),
  'project execution board signature should include project-level stage state and checklist progress'
);

assert.ok(
  projectsJs.includes('el.dataset.scoreboardSignature === signature') &&
    projectsJs.includes('el.dataset.scoreboardSignature = signature'),
  'project scoreboard should avoid repainting unchanged XP chips during polling'
);

console.log('stage workflow chat active fallback checks passed');
