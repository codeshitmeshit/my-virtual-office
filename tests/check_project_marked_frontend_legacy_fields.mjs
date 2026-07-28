import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');
const workspacePanelJs = readFileSync(join(root, 'app/agent-workspace-panel.js'), 'utf8');
const gameJs = readFileSync(join(root, 'app/game.js'), 'utf8');

assert.ok(
  projectsJs.includes("const STAGE_PIPELINE_EXECUTION_MODEL = 'stage_pipeline_v1';"),
  'projects frontend should identify marked stage-pipeline projects'
);
assert.ok(
  projectsJs.includes('function syncWorkflowFromProject(project)'),
  'projects frontend should centralize marked vs legacy workflow state hydration'
);
assert.ok(
  !projectsJs.includes('state.workflow.active = !!state.currentProject.workflowActive'),
  'opening a project should not hydrate workflow state directly from legacy active fields'
);
assert.ok(
  projectsJs.includes("state.workflow.phase = project.projectExecutionPhase || project.orchestrationState || 'idle';"),
  'marked project workflow phase should hydrate from orchestration projection'
);
assert.ok(
  projectsJs.includes("state.workflow.currentTaskId = activeIds.length === 1 ? activeIds[0] : null;"),
  'marked project workflow state must not invent a singular active task when multiple are active'
);
assert.ok(
  projectsJs.includes('const executionOrderByTaskId = markedPipeline ? new Map() : projectExecutionOrderMap(tasks);'),
  'marked project board rendering should not synthesize executionOrder badges'
);
assert.ok(
  projectsJs.includes("const stageBadge = markedPipeline && Number.isInteger(stageValue) && stageValue > 0"),
  'marked project task cards should render executionStage instead of legacy executionOrder'
);
assert.ok(
  projectsJs.includes('const d = await api.workflowChat(p.id, workflowChatTaskScope(p));'),
  'workflow chat polling should pass explicit task scope when the selected marked task is active'
);
assert.ok(
  workspacePanelJs.includes("if (!markedPipeline && t.projectExecutionFlowActive) badges.push('flow active');"),
  'standalone workspace panel should guard legacy flow-active badges for marked projects'
);
assert.ok(
  gameJs.includes("if (!markedPipeline && t.projectExecutionFlowActive) badges.push('flow active');"),
  'bundled workspace panel should guard legacy flow-active badges for marked projects'
);

console.log('marked project frontend legacy-field checks passed');
