#!/usr/bin/env node

import assert from 'node:assert/strict';
import fs from 'node:fs';

const server = fs.readFileSync('app/server.py', 'utf8');
const service = fs.readFileSync('app/server_services/config_runtime.py', 'utf8');
const route = fs.readFileSync('app/server_routes/config.py', 'utf8');

assert.doesNotMatch(
  server,
  /^def _persist_setup_payload\(/m,
  'server.py must not retain the legacy settings persistence implementation',
);
assert.doesNotMatch(server, /^def _merge_setup_config\(/m);
assert.doesNotMatch(server, /^def _clear_setup_secret_paths\(/m);
assert.doesNotMatch(
  server,
  /result = _persist_setup_payload\(/,
  'server.py callers must use the config runtime service instead of the legacy global',
);
assert.match(
  server,
  /server_routes\.config\.handle_post\(self, parsed_url\)/,
  'the live POST handler must delegate /setup/save to the config route',
);
assert.match(service, /^def _persist_setup_payload\(/m);
assert.match(route, /path == "\/setup\/save"/);
assert.match(route, /service\._persist_setup_payload\(body\)/);

console.log('settings save single-entry contract ok');
