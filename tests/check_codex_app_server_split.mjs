#!/usr/bin/env node
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const adapter = fs.readFileSync(path.join(root, 'app/providers/codex_app_server.py'), 'utf8');
const shim = fs.readFileSync(path.join(root, 'app/providers/codex_bridge.py'), 'utf8');

const adapterMarkers = [
  'from provider_app_server import',
  'AppServerResponseError',
  'JsonlAppServerRuntime',
  'class CodexAppServerClient',
  'class CodexHttpBridgeClient',
  'def get_codex_bridge',
  'def _handle_server_request',
  'def _handle_notification',
];

for (const marker of adapterMarkers) {
  if (!adapter.includes(marker)) {
    throw new Error(`missing Codex adapter marker: ${marker}`);
  }
}

const shimMarkers = [
  'Compatibility shim',
  'from providers.codex_app_server import',
  'CodexAppServerClient',
  'CodexHttpBridgeClient',
  'get_codex_bridge',
  '__all__',
];

for (const marker of shimMarkers) {
  if (!shim.includes(marker)) {
    throw new Error(`missing Codex bridge shim marker: ${marker}`);
  }
}

const forbiddenShimMarkers = [
  'class _Operation',
  'def _handle_server_request',
  'def _handle_notification',
  'APPROVAL_METHODS =',
];

for (const marker of forbiddenShimMarkers) {
  if (shim.includes(marker)) {
    throw new Error(`codex_bridge shim should not contain protocol implementation: ${marker}`);
  }
}

console.log('codex app-server split checks passed');
