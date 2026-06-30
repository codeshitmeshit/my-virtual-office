import fs from 'node:fs';

const source = fs.readFileSync('app/projects.js', 'utf8');
const pollingMatch = source.match(/function startProjectExecutionPolling\(\) \{[\s\S]*?\n    \}/);
if (!pollingMatch) {
  throw new Error('startProjectExecutionPolling not found');
}

const pollingSource = pollingMatch[0];
if (pollingSource.includes('refreshProjectExecutionProject(d.currentTaskId')) {
  throw new Error('Project execution polling still forces detail panel to active task');
}
if (!pollingSource.includes('openTaskId') || !pollingSource.includes('state.currentTask && state.currentTask.id')) {
  throw new Error('Project execution polling does not preserve currently opened task detail');
}

console.log('project polling preserves current detail task');
