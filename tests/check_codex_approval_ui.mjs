#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..');
const chatJs = fs.readFileSync(path.join(root, 'app', 'chat.js'), 'utf8');
const enJson = fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8');
const zhJson = fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8');

function assertContains(source, needle, label) {
  if (!source.includes(needle)) throw new Error(`${label} is missing ${needle}`);
}

[
  'startCodexApprovalPolling()',
  'pollCodexApproval()',
  'appendCodexPendingApproval(',
  "fetch('/api/codex/approval/pending?agentId='",
  "fetch('/api/codex/approval/respond'",
  'respondCodexApproval(approval',
  'this.startCodexApprovalPolling();',
  'this.stopCodexApprovalPolling();',
  'this.appendCodexPendingApproval(progress.approval',
  "fetch('/api/codex/interaction'",
].forEach(snippet => assertContains(chatJs, snippet, 'chat.js'));

[
  'chat_codex_approval_required',
  'chat_codex_needs_approval',
  'chat_codex_approval_gated_action',
  'chat_codex_approval_allow_hint',
  'chat_codex_approval_cancel_hint',
  'chat_codex_approval_failed',
].forEach(key => {
  assertContains(enJson, `"${key}"`, 'en.json');
  assertContains(zhJson, `"${key}"`, 'zh.json');
});

console.log('codex approval UI check passed');
