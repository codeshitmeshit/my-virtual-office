import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createSafeLogger } from './logger.mjs';
import { checkDependencies } from './preflight.mjs';
import { FeishuChannelWorker } from './worker.mjs';

const logger = createSafeLogger({ secrets: [
  process.env.VO_FEISHU_CHAT_APP_SECRET,
  process.env.VO_FEISHU_CHAT_WORKER_TOKEN,
].filter(Boolean) });
const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const statusDir = process.env.VO_STATUS_DIR || join(packageRoot, 'data');

async function main() {
  const preflight = await checkDependencies();
  if (!preflight.ok) {
    const { StatusStore } = await import('./status.mjs');
    const store = new StatusStore(join(statusDir, 'feishu-chat-worker-status.json'));
    await store.update(preflight);
    process.exitCode = 2;
    return;
  }
  const worker = new FeishuChannelWorker({
    appId: process.env.VO_FEISHU_CHAT_APP_ID || '',
    appSecret: process.env.VO_FEISHU_CHAT_APP_SECRET || '',
    statusDir,
    callbackUrl: process.env.VO_FEISHU_CHAT_WORKER_CALLBACK_URL || '',
    callbackToken: process.env.VO_FEISHU_CHAT_WORKER_TOKEN || '',
    parentPid: Number(process.env.VO_FEISHU_CHAT_PARENT_PID || process.ppid),
    workerInstanceId: process.env.VO_FEISHU_CHAT_WORKER_INSTANCE_ID || undefined,
    logger,
  });
  const shutdown = (signal) => worker.stop(signal === 'SIGTERM' ? 'stopped' : 'interrupted').finally(() => process.exit(0));
  process.once('SIGTERM', () => shutdown('SIGTERM'));
  process.once('SIGINT', () => shutdown('SIGINT'));
  process.on('uncaughtException', async (error) => {
    logger.error('uncaught worker error', { error: error.message });
    await worker.status.update({ running: false, status: 'error', lastError: error.message }).catch(() => {});
    process.exit(1);
  });
  process.on('unhandledRejection', async (error) => {
    logger.error('unhandled worker rejection', { error: error?.message || String(error) });
    await worker.status.update({ running: false, status: 'error', lastError: error?.message || String(error) }).catch(() => {});
    process.exit(1);
  });
  await worker.start();
}

await main();
