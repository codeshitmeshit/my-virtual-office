import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync('app/index.html', 'utf8');
const game = fs.readFileSync('app/game.js', 'utf8');
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));

assert.match(html, /id="mm-feishu-group-chat-enable"/, 'settings must expose the group chat switch');
assert.match(html, /id="mm-feishu-group-chat-warning"/, 'settings must show the group trust warning');
assert.match(game, /groupChatEnabled:\s*groupChatEnabled/, 'dedicated Chat save must send the group switch');
assert.match(game, /groupChatEnabled:\s*_feishuGroupChatEnabled/, 'generic setup save must preserve the group switch');
assert.match(game, /transport !== 'channel-sdk-node'/, 'UI must reject group chat on legacy transport');
assert.match(game, /if \(!isNode\) groupEnabledEl\.checked = false/, 'switching to legacy must clear a stale checked group switch before save');
assert.match(game, /allowedChatTypes:\s*_feishuGroupChatEnabled[^\n]+\['p2p', 'group'\]/, 'setup payload must project dynamic chat types');
assert.ok(en.feishu_group_chat_warning.includes('every human member'));
assert.ok(zh.feishu_group_chat_warning.includes('所有真人成员'));
assert.ok(en.feishu_group_chat_requires_node.includes('Channel SDK'));
assert.ok(zh.feishu_group_chat_requires_node.includes('Channel SDK'));

console.log('check_feishu_group_chat_config_static.mjs passed');
