import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

export const REQUIRED_NODE_MAJOR = 18;
export const REQUIRED_CHANNEL_VERSION = '0.4.0';
export const TRANSPORT = 'channel-sdk-node';

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

function failure(status, lastError, action) {
  return {
    ok: false,
    scope: 'feishu_chat',
    affectsVoStartup: false,
    enabled: false,
    running: false,
    transport: TRANSPORT,
    status,
    lastError,
    action,
    requiredNodeMajor: REQUIRED_NODE_MAJOR,
    requiredChannelVersion: REQUIRED_CHANNEL_VERSION,
  };
}

function parseNodeMajor(version) {
  const match = String(version || '').trim().replace(/^v/, '').match(/^(\d+)(?:\.|$)/);
  return match ? Number(match[1]) : 0;
}

async function defaultResolveChannelPackage() {
  const require = createRequire(import.meta.url);
  const entry = require.resolve('@larksuite/channel');
  let current = dirname(entry);
  while (current !== dirname(current)) {
    const candidate = join(current, 'package.json');
    try {
      const metadata = JSON.parse(await readFile(candidate, 'utf8'));
      if (metadata.name === '@larksuite/channel') {
        return metadata;
      }
    } catch (error) {
      if (error?.code !== 'ENOENT') {
        throw error;
      }
    }
    current = dirname(current);
  }
  throw Object.assign(new Error('resolved SDK entry has no package metadata'), { code: 'MODULE_NOT_FOUND' });
}

export async function checkDependencies({
  nodeVersion = process.versions?.node,
  resolveChannelPackage = defaultResolveChannelPackage,
} = {}) {
  const nodeMajor = parseNodeMajor(nodeVersion);
  if (!nodeMajor) {
    return failure(
      'missing_node_runtime',
      `Node.js ${REQUIRED_NODE_MAJOR}+ is required for the Feishu Chat channel worker.`,
      `Install Node.js ${REQUIRED_NODE_MAJOR} or newer, then run npm ci --omit=dev in ${PACKAGE_ROOT}.`,
    );
  }
  if (nodeMajor < REQUIRED_NODE_MAJOR) {
    return failure(
      'incompatible_node_runtime',
      `Node.js ${nodeVersion} is incompatible; ${REQUIRED_NODE_MAJOR}+ is required for the Feishu Chat channel worker.`,
      `Upgrade Node.js to ${REQUIRED_NODE_MAJOR} or newer, then run npm ci --omit=dev in ${PACKAGE_ROOT}.`,
    );
  }

  let channelPackage;
  try {
    channelPackage = await resolveChannelPackage();
  } catch (error) {
    return failure(
      'missing_channel_sdk',
      `@larksuite/channel ${REQUIRED_CHANNEL_VERSION} is unavailable for the Feishu Chat channel worker.`,
      `Run npm ci --omit=dev in ${PACKAGE_ROOT}.`,
    );
  }

  if (channelPackage?.version !== REQUIRED_CHANNEL_VERSION) {
    return failure(
      'incompatible_channel_sdk',
      `@larksuite/channel ${String(channelPackage?.version || 'unknown')} is installed; version ${REQUIRED_CHANNEL_VERSION} is required.`,
      `Run npm ci --omit=dev in ${PACKAGE_ROOT} to restore the reviewed lockfile.`,
    );
  }

  return {
    ok: true,
    scope: 'feishu_chat',
    affectsVoStartup: false,
    enabled: true,
    running: false,
    transport: TRANSPORT,
    status: 'dependencies_ready',
    lastError: '',
    nodeVersion: String(nodeVersion),
    channelVersion: channelPackage.version,
    requiredNodeMajor: REQUIRED_NODE_MAJOR,
    requiredChannelVersion: REQUIRED_CHANNEL_VERSION,
  };
}

async function main() {
  const result = await checkDependencies();
  process.stdout.write(`${JSON.stringify(result)}\n`);
  process.exitCode = result.ok ? 0 : 2;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await main();
}
