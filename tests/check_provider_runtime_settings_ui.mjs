#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..');
const indexHtml = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const setupHtml = fs.readFileSync(path.join(root, 'app', 'setup.html'), 'utf8');
const gameJs = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const modelsHtml = fs.readFileSync(path.join(root, 'app', 'models.html'), 'utf8');
const enJson = fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8');
const zhJson = fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8');

const requiredIndexIds = [
  'mm-hermes-api-enable',
  'mm-hermes-api-url',
  'mm-hermes-api-key',
  'mm-codex-enable',
  'mm-codex-workspace',
  'mm-codex-workspace-root',
  'mm-codex-main-workspace',
  'mm-codex-model',
  'mm-codex-bridge-url',
  'mm-codex-include-main',
  'mm-codex-include-native',
  'mm-codex-route-approvals-through-vo',
  'mm-claude-code-enable',
  'mm-claude-code-home',
  'mm-claude-code-bin',
  'mm-claude-code-workspace',
  'mm-claude-code-workspace-root',
  'mm-claude-code-main-workspace',
  'mm-claude-code-model',
  'mm-claude-code-include-main',
  'mm-claude-code-include-native',
  'mm-claude-code-register-native',
];

const requiredSetupIds = [
  's-hermes-api-enable',
  's-hermes-api-url',
  's-hermes-api-key',
  's-codex-enable',
  's-codex-home',
  's-codex-bin',
  's-codex-workspace-root',
  's-codex-main-workspace',
  's-codex-model',
  's-codex-sandbox',
  's-codex-approval',
  's-codex-appserver',
  's-codex-main',
  's-codex-native',
  's-codex-register',
  's-codex-route-approvals-through-vo',
  's-claude-enable',
  's-claude-home',
  's-claude-bin',
  's-claude-workspace-root',
  's-claude-main-workspace',
  's-claude-model',
  's-claude-permission',
  's-claude-main',
  's-claude-native',
  's-claude-register',
];

const requiredGameSnippets = [
  'hermesSettings.apiKey',
  'config.hermes = hermesSettings',
  'config.codex = {',
  'config.claudeCode = {',
  "fetch('/api/codex/test'",
  "fetch('/api/claude-code/test'",
  'hermesCfg.apiEnabled',
  'codexCfg.workspace',
  'codexCfg.workspaceRoot',
  'codexCfg.mainWorkspace',
  'codexCfg.includeNativeAgents',
  'codexCfg.routeApprovalsThroughVo',
  'routeApprovalsThroughVo',
  'claudeCfg.workspace',
  'claudeCfg.workspaceRoot',
  'claudeCfg.mainWorkspace',
  'claudeCfg.includeNativeAgents',
  'registerNativeAgents',
];

const requiredModelSnippets = [
  'panel-native',
  'native-providers',
  'renderNativeProviders();',
  'providersData.nativeProviders',
  "renderNativeSummaryCard('codex', 'Codex CLI'",
  "renderNativeSummaryCard('claude-code', 'Claude Code'",
  'native-codex-workspace-root',
  'native-codex-register-native',
  'native-codex-route-approvals-through-vo',
  'native-claude-workspace-root',
  'native-claude-register-native',
  'saveCodexNativeSetup',
  "postNativeJson('/setup/save', { codex: codexNativePayload() })",
  "postNativeJson('/api/codex/test', payload)",
  'saveClaudeNativeSetup',
  "postNativeJson('/setup/save', { claudeCode: claudeNativePayload() })",
  "postNativeJson('/api/claude-code/test', payload)",
  'native_setup_guide',
  'native_setup_guide_desc',
];

const requiredLocaleSnippets = [
  'Native Setup Guide',
  '$CODEX_HOME/agents/*.toml',
  '$CLAUDE_CONFIG_DIR/agents/*.md',
  '原生设置指南',
  '$CODEX_HOME/agents/*.toml',
  '$CLAUDE_CONFIG_DIR/agents/*.md',
];

function assertContains(source, needle, label) {
  if (!source.includes(needle)) {
    throw new Error(`${label} is missing ${needle}`);
  }
}

for (const id of requiredIndexIds) assertContains(indexHtml, `id="${id}"`, 'index.html');
for (const id of requiredSetupIds) assertContains(setupHtml, `id="${id}"`, 'setup.html');
for (const snippet of requiredGameSnippets) assertContains(gameJs, snippet, 'game.js');
for (const snippet of requiredModelSnippets) assertContains(modelsHtml, snippet, 'models.html');
for (const snippet of requiredLocaleSnippets) assertContains(enJson + zhJson, snippet, 'locale json');

console.log('provider runtime settings UI check passed');
