import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  REQUIRED_CHANNEL_VERSION,
  checkDependencies,
} from '../src/preflight.mjs';

test('accepts Node 18+ with the exactly reviewed channel SDK', async () => {
  const result = await checkDependencies({
    nodeVersion: '20.20.2',
    resolveChannelPackage: async () => ({
      name: '@larksuite/channel',
      version: REQUIRED_CHANNEL_VERSION,
    }),
  });

  assert.equal(result.ok, true);
  assert.equal(result.status, 'dependencies_ready');
  assert.equal(result.transport, 'channel-sdk-node');
  assert.equal(result.channelVersion, '0.4.0');
});

test('reports an actionable Chat-only status for an incompatible Node runtime', async () => {
  const result = await checkDependencies({
    nodeVersion: '16.20.2',
    resolveChannelPackage: async () => ({ version: REQUIRED_CHANNEL_VERSION }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.scope, 'feishu_chat');
  assert.equal(result.affectsVoStartup, false);
  assert.equal(result.status, 'incompatible_node_runtime');
  assert.match(result.lastError, /Node\.js 16\.20\.2/);
  assert.match(result.action, /Node\.js to 18 or newer/);
});

test('reports an actionable Chat-only status when Node cannot be identified', async () => {
  const result = await checkDependencies({ nodeVersion: '' });

  assert.equal(result.ok, false);
  assert.equal(result.scope, 'feishu_chat');
  assert.equal(result.affectsVoStartup, false);
  assert.equal(result.status, 'missing_node_runtime');
  assert.match(result.action, /npm ci --omit=dev/);
});

test('reports an actionable Chat-only status when the SDK is missing', async () => {
  const result = await checkDependencies({
    nodeVersion: '18.0.0',
    resolveChannelPackage: async () => {
      throw Object.assign(new Error('not installed'), { code: 'MODULE_NOT_FOUND' });
    },
  });

  assert.equal(result.ok, false);
  assert.equal(result.scope, 'feishu_chat');
  assert.equal(result.affectsVoStartup, false);
  assert.equal(result.status, 'missing_channel_sdk');
  assert.match(result.lastError, /@larksuite\/channel 0\.4\.0/);
  assert.match(result.action, /npm ci --omit=dev/);
});

test('rejects an SDK version that differs from the reviewed lock', async () => {
  const result = await checkDependencies({
    nodeVersion: '18.0.0',
    resolveChannelPackage: async () => ({
      name: '@larksuite/channel',
      version: '0.4.1',
    }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.scope, 'feishu_chat');
  assert.equal(result.affectsVoStartup, false);
  assert.equal(result.status, 'incompatible_channel_sdk');
  assert.match(result.action, /reviewed lockfile/);
});
