import { readFileSync } from 'node:fs';

const source = readFileSync('app/projects.js', 'utf8');
const start = source.indexOf('async function projectResetAction');
const end = source.indexOf('function resolveConfirmAction', start);

if (start < 0 || end < 0) {
  throw new Error('projectResetAction was not found');
}

const resetSource = source.slice(start, end);

if (resetSource.includes('renderProjectDetail()')) {
  throw new Error('Project reset still calls renderProjectDetail instead of rerendering the board');
}
if (!resetSource.includes('syncWorkflowFromProject(state.currentProject)')) {
  throw new Error('Project reset does not resync workflow state from the reset project');
}
if (!resetSource.includes('state.currentTask = null')) {
  throw new Error('Project reset should clear the selected task after state reset');
}
if (!resetSource.includes('rerenderProjectBoard()')) {
  throw new Error('Project reset does not rerender the board with reset data');
}

console.log('project reset rerenders board with reset state');
