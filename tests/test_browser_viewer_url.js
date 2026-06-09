const assert = require('assert');
const { buildBrowserViewerUrl } = require('../app/browser-viewer-url.js');

const proxied = new URL(buildBrowserViewerUrl(
  'https://xiaoou.cosh.fun/browser/',
  'https://xiaoou.cosh.fun/'
));
assert.strictEqual(proxied.searchParams.get('path'), 'browser/websockify');
assert.strictEqual(proxied.searchParams.get('resize'), 'scale');
assert.strictEqual(proxied.searchParams.get('autoconnect'), '1');

const direct = new URL(buildBrowserViewerUrl(
  'https://localhost:6901/',
  'https://xiaoou.cosh.fun/'
));
assert.strictEqual(direct.searchParams.get('path'), 'websockify');

const configured = new URL(buildBrowserViewerUrl(
  'https://example.test/view/?path=custom/socket&resize=remote',
  'https://example.test/'
));
assert.strictEqual(configured.searchParams.get('path'), 'custom/socket');
assert.strictEqual(configured.searchParams.get('resize'), 'remote');

console.log('browser viewer URL tests passed');
