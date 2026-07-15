import assert from 'node:assert/strict';
import { mkdtemp, readFile, symlink, writeFile } from 'node:fs/promises';
import http from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { CommandServer } from '../src/command-server.mjs';
import { COMMAND_SCHEMA } from '../src/protocol.mjs';
import { ResourceStore } from '../src/resources.mjs';

function request(port, body, token = 'worker-token') {
  return new Promise((resolve, reject) => {
    const payload = Buffer.from(typeof body === 'string' ? body : JSON.stringify(body));
    const req = http.request({ hostname: '127.0.0.1', port, path: '/command', method: 'POST', headers: { 'content-type': 'application/json', 'content-length': payload.length, 'x-vo-feishu-chat-worker-token': token } }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString()) }));
    });
    req.on('error', reject);
    req.end(payload);
  });
}

function command(operation, payload) {
  return { schema: COMMAND_SCHEMA, requestId: `req-${operation}`, workerInstanceId: 'worker-1', operation, payload };
}

test('command server rejects unauthenticated and oversized requests before channel effects', async () => {
  let effects = 0;
  const channel = { async send() { effects += 1; return { messageId: 'om_1' }; } };
  const server = new CommandServer({ channel, token: 'worker-token', workerInstanceId: 'worker-1', maxBodyBytes: 256 });
  await server.start();
  try {
    const denied = await request(server.port, command('send', { to: 'oc_1', content: 'hello' }), 'wrong');
    assert.equal(denied.status, 403);
    assert.equal(denied.body.category, 'authentication_failed');
    const oversized = await request(server.port, 'x'.repeat(300));
    assert.equal(oversized.status, 413);
    assert.equal(effects, 0);
  } finally {
    await server.stop();
  }
});

test('command server executes send, reply, reactions, recall and classifies SDK errors', async () => {
  const calls = [];
  const events = [];
  const channel = {
    async send(to, input, opts) { calls.push(['send', to, input, opts]); if (to === 'fail') throw Object.assign(new Error('limited'), { code: 'rate_limited' }); return { messageId: `om_${calls.length}` }; },
    async addReaction(messageId, emoji) { calls.push(['addReaction', messageId, emoji]); return 'reaction-1'; },
    async removeReaction(messageId, reactionId) { calls.push(['removeReaction', messageId, reactionId]); },
    async recallMessage(messageId) { calls.push(['recall', messageId]); },
  };
  const server = new CommandServer({ channel, token: 'worker-token', workerInstanceId: 'worker-1', onEvent: async (event) => events.push(event) });
  await server.start();
  try {
    assert.equal((await request(server.port, command('send', { to: 'oc_1', content: 'hello', contentType: 'text' }))).body.status, 'sent');
    assert.equal((await request(server.port, command('reply', { to: 'oc_1', messageId: 'om_source', content: '**hi**', contentType: 'markdown', replyInThread: true }))).body.status, 'sent');
    assert.equal((await request(server.port, command('addReaction', { messageId: 'om_source', emojiType: 'LGTM' }))).body.reactionId, 'reaction-1');
    assert.equal((await request(server.port, command('removeReaction', { messageId: 'om_source', reactionId: 'reaction-1' }))).body.status, 'deleted');
    assert.equal((await request(server.port, command('recall', { messageId: 'om_source' }))).body.status, 'recalled');
    const failed = await request(server.port, command('send', { to: 'fail', content: 'hello' }));
    assert.equal(failed.status, 502);
    assert.equal(failed.body.category, 'rate_limited');
    assert.equal(calls.length, 6);
    assert.equal(events.filter((event) => event.type === 'command_success').length, 5);
    assert.deepEqual(events.at(-1), { type: 'command_failure', category: 'rate_limited' });
  } finally {
    await server.stop();
  }
});

test('resource store generates safe files, enforces size, cleans partials, and rejects symlink roots', async () => {
  const parent = await mkdtemp(join(tmpdir(), 'vo-feishu-resource-'));
  const root = join(parent, 'attachments');
  const store = new ResourceStore(root, { maxBytes: 4 });
  const channel = {
    async downloadResourceToFile(messageId, fileKey, type, path) {
      const content = fileKey === 'large' ? '12345' : '1234';
      await writeFile(path, content);
      return { contentType: 'image/png', bytesWritten: content.length };
    },
  };
  const downloaded = await store.download(channel, { messageId: 'om_1', fileKey: 'ok', resourceType: 'image', displayName: '../../avatar' });
  assert.equal(downloaded.size, 4);
  assert.match(downloaded.name, /^avatar-[a-f0-9-]+\.png$/);
  assert.equal((await readFile(downloaded.path, 'utf8')), '1234');
  await assert.rejects(() => store.download(channel, { messageId: 'om_1', fileKey: 'large', resourceType: 'image' }), (error) => error.code === 'resource_too_large');
  const interrupted = {
    async downloadResourceToFile(messageId, fileKey, type, path) {
      await writeFile(path, 'partial');
      throw Object.assign(new Error('network interrupted'), { code: 'download_interrupted' });
    },
  };
  await assert.rejects(() => store.download(interrupted, { messageId: 'om_1', fileKey: 'interrupted', resourceType: 'file', displayName: 'report.bin' }), /network interrupted/);
  await assert.rejects(() => store.download(channel, { messageId: 'om_1', fileKey: 'ok', resourceType: 'audio' }), (error) => error.code === 'unsupported_resource_type');

  const target = join(parent, 'real');
  await writeFile(target, 'not-a-directory');
  const linked = join(parent, 'linked');
  await symlink(target, linked);
  await assert.rejects(() => new ResourceStore(linked).initialize(), (error) => error.code === 'unsafe_resource_path' || error.code === 'EEXIST');
});
