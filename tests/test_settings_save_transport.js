#!/usr/bin/env node

const assert = require('assert');
const path = require('path');

const modulePath = path.join(__dirname, '..', 'app', 'settings-save-transport.js');
delete require.cache[require.resolve(modulePath)];
const transport = require(modulePath);

assert.strictEqual(
  transport.endpointFor({ protocol: 'http:', hostname: '127.0.0.1', port: '8090' }),
  'http://0.0.0.0:8090/setup/save',
);
assert.strictEqual(
  transport.endpointFor({ protocol: 'http:', hostname: 'localhost', port: '8090' }),
  'http://0.0.0.0:8090/setup/save',
);
assert.strictEqual(
  transport.endpointFor({ protocol: 'https:', hostname: 'example.com', port: '' }),
  '/setup/save',
);

(async () => {
  const calls = [];
  const response = { ok: true };
  const result = await transport.request(
    { features: { browserPanel: true } },
    (url, init) => {
      calls.push({ url, init });
      return Promise.resolve(response);
    },
    { location: { protocol: 'http:', hostname: '127.0.0.1', port: '8090' }, timeoutMs: 100 },
  );

  assert.strictEqual(result, response);
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].url, 'http://0.0.0.0:8090/setup/save');
  assert.strictEqual(calls[0].init.method, 'POST');
  assert.deepStrictEqual(JSON.parse(calls[0].init.body), { features: { browserPanel: true } });
  assert.ok(calls[0].init.signal, 'save transport must provide an abort signal');

  await assert.rejects(
    () => transport.request({}, () => new Promise(() => {}), {
      location: { protocol: 'https:', hostname: 'example.com', port: '' },
      timeoutMs: 5,
    }),
    /timed out/i,
  );

  console.log('settings save transport ok');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
