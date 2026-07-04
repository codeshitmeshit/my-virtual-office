const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const bubble = fs.readFileSync(path.join(root, 'app', 'bubble-system.js'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8'));

const bubbleFn = bubble.slice(
  bubble.indexOf('function _meetingBubbleText(turn)'),
  bubble.indexOf('function _meetingLatestSpeakerKey(record)')
);

assert.ok(bubbleFn.includes("_mtgT('meeting_provider_calling', 'Preparing meeting response...')"));
assert.ok(!bubbleFn.includes('Calling provider...'));
assert.ok(bubbleFn.includes('turn.structured && turn.structured.position'));
assert.ok(bubbleFn.includes('turn.structured && turn.structured.summary'));

assert.ok(bubble.includes("kind: 'meeting_result'"));
assert.ok(bubble.includes("result.summary || result.resolution"));

const sourceFn = bubble.slice(
  bubble.indexOf('function _meetingChatSourceForSpeaker(agent)'),
  bubble.indexOf('function drawChatBubbles()')
);
assert.ok(!sourceFn.includes('_meetingLatestSpeakerKey(record)'));
assert.ok(sourceFn.includes("if (!turn || !_meetingAgentMatchesKey(agent, turn.speaker)) return;"));
assert.ok(sourceFn.includes("if (!speaker || !_meetingAgentMatchesKey(agent, speaker)) return;"));

const minimizeFn = bubble.slice(
  bubble.indexOf('function minimizeAllChat()'),
  bubble.indexOf('function expandAllChat()')
);
const expandFn = bubble.slice(
  bubble.indexOf('function expandAllChat()'),
  bubble.indexOf('function handleChatBubbleClick')
);
const drawChatFn = bubble.slice(
  bubble.indexOf('function drawChatBubbles()'),
  bubble.indexOf('// Compute visible world bounds')
);
assert.ok(minimizeFn.includes('agents.forEach(function(agent)'));
assert.ok(expandFn.includes('agents.forEach(function(agent)'));
assert.ok(!minimizeFn.includes("agent.state === 'meeting'"));
assert.ok(!expandFn.includes("agent.state === 'meeting'"));
assert.ok(drawChatFn.includes('if (chatMinimized[agent.statusKey])'));
assert.ok(!drawChatFn.includes('if (!isMeetingBubble && chatMinimized[agent.statusKey])'));

assert.strictEqual(zh.meeting_provider_calling, '正在准备会议回应');
assert.strictEqual(en.meeting_provider_calling, 'preparing meeting response');

console.log('meeting bubble output tests passed');
