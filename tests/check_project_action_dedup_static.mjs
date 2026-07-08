import fs from 'fs';
import assert from 'assert';

const source = fs.readFileSync('app/projects.js', 'utf8');

function requireIncludes(needle, message) {
  assert(source.includes(needle), message || `Missing ${needle}`);
}

function functionBody(name) {
  const match = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(source);
  assert(match, `Missing function ${name}`);
  const start = match.index;
  let parenDepth = 0;
  let braceStart = -1;
  for (let i = source.indexOf('(', start); i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '(') parenDepth += 1;
    if (ch === ')') parenDepth -= 1;
    if (parenDepth === 0) {
      braceStart = source.indexOf('{', i);
      break;
    }
  }
  assert(braceStart >= 0, `Could not find body for ${name}`);
  let depth = 0;
  for (let i = braceStart; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '{') depth += 1;
    if (ch === '}') depth -= 1;
    if (depth === 0) return source.slice(braceStart + 1, i);
  }
  throw new Error(`Could not parse function ${name}`);
}

requireIncludes('pendingActions', 'state must track pending actions');
requireIncludes('function runActionOnce', 'project actions must use a shared runActionOnce guard');
requireIncludes('[PROJECTS] duplicate action ignored key=', 'duplicate action ignores need a low-noise testable log');
requireIncludes('aria-busy', 'busy buttons should expose aria-busy');

const requiredActionKeys = [
  'project-exec-start:',
  'project-exec-project-start:',
  'project-exec-project-restart:',
  'project-exec-cancel:',
  'project-exec-review-start:',
  'meeting-blocker:',
  'project-exec-accept:',
  'workflow-start:',
  'workflow-stop:',
  'cron-submit:',
  'cron-pause:',
  'cron-run:',
  'cron-toggle:',
  'cron-delete:',
];
for (const key of requiredActionKeys) {
  requireIncludes(key, `Missing action key prefix ${key}`);
}

const guardedFunctions = [
  'projectExecutionStartAction',
  'projectExecutionProjectStartAction',
  'projectExecutionProjectRestartAction',
  'projectExecutionCancelAction',
  'projectExecutionMeetingBlockerAction',
  'projectExecutionReviewStartAction',
  'submitProjectExecutionAcceptance',
  'workflowStartAction',
  'workflowStopAction',
  'submitProjectCron',
  'toggleProjectCronPauseAction',
  'runProjectCronAction',
  'toggleProjectCronAction',
  'deleteProjectCronAction',
];
for (const name of guardedFunctions) {
  const body = functionBody(name);
  assert(body.includes('runActionOnce'), `${name} must be guarded by runActionOnce`);
}

const confirmBody = functionBody('resolveConfirmAction');
assert(confirmBody.includes('markDialogSubmitting'), 'confirm dialog submit must enter a submitting state');

const textBody = functionBody('submitTextInputDialogAction');
assert(textBody.includes('markDialogSubmitting'), 'text input dialog submit must enter a submitting state');

console.log('ok');
