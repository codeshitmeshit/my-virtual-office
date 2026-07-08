import fs from 'node:fs';

const source = fs.readFileSync('app/game.js', 'utf8');

function assertIncludes(needle, label = needle) {
  if (!source.includes(needle)) {
    throw new Error(`Missing ${label}`);
  }
}

function extractFunction(name) {
  const pattern = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const match = pattern.exec(source);
  if (!match) throw new Error(`Missing function ${name}`);
  const braceStart = source.indexOf('{', match.index);
  let depth = 0;
  for (let i = braceStart; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '{') depth += 1;
    if (ch === '}') depth -= 1;
    if (depth === 0) return source.slice(braceStart, i + 1);
  }
  throw new Error(`Unclosed function ${name}`);
}

function assertFunctionGuarded(name, keyFragment) {
  const body = extractFunction(name);
  if (!body.includes('_mtgRunActionOnce')) {
    throw new Error(`${name} is not guarded by _mtgRunActionOnce`);
  }
  if (keyFragment && !body.includes(keyFragment)) {
    throw new Error(`${name} does not include key fragment ${keyFragment}`);
  }
}

assertIncludes('var _mtgPendingActions = {};');
assertIncludes('function _mtgRunActionOnce');
assertIncludes('[MEETINGS] duplicate action ignored key=');
assertIncludes("button.setAttribute('aria-busy', 'true')");

[
  ['_mtgConfirmRequest', 'meeting-request-confirm:'],
  ['_mtgRejectRequest', 'meeting-request-reject:'],
  ['submitMeetingIntervention', 'meeting-intervention:'],
  ['submitMeetingAgendaChange', 'meeting-agenda:'],
  ['submitMeetingTargetedQuestion', 'meeting-targeted-question:'],
  ['submitMeetingArbitration', 'meeting-arbitration:'],
  ['submitModeratorTakeover', 'meeting-moderator-takeover:'],
  ['continueMeetingDecisionWindow', 'meeting-decision-continue:'],
  ['_mtgRunMeeting', 'meeting-run:'],
  ['startExecutableMeeting', 'meeting-start:'],
  ['submitNewMeeting', 'meeting-create:new'],
  ['_mtgActionItemRequest', 'meeting-action-item:'],
  ['endExecutableMeetingWithAI', 'meeting-end-ai:'],
  ['_mtgTransitionMeeting', 'meeting-transition:'],
  ['_mtgConflictAction', 'meeting-conflict:'],
  ['submitEndMeeting', 'meeting-end-manual:'],
  ['deleteMeetingHistory', 'meeting-history-delete:'],
].forEach(([name, key]) => assertFunctionGuarded(name, key));

[
  '/api/meetings/requests/',
  '/api/meetings/executable/create',
  '/api/meetings/executable/',
  '/intervention',
  '/agenda-change',
  '/targeted-question',
  '/arbitration',
  '/moderator-takeover',
  '/run',
  '/action-items/',
  '/api/meetings/end',
  '/transition',
  '/conflict',
  '/api/meetings/history/',
].forEach((endpoint) => assertIncludes(endpoint, `endpoint ${endpoint}`));

console.log('ok');
