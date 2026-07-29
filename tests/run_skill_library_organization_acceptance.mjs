#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const python = process.env.PYTHON ||
  (existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3');

const commands = [
  {
    label: '103-skill domain flow, busy exclusion, and restart recovery',
    command: python,
    args: [
      '-m',
      'pytest',
      '-q',
      'tests/test_skill_library_organization_acceptance.py',
    ],
  },
  {
    label: 'owner authorization and stable HTTP errors',
    command: python,
    args: [
      '-m',
      'pytest',
      '-q',
      'tests/test_skill_library_organization_http_contract.py',
    ],
  },
  {
    label: 'management-token prompt and retry behavior',
    command: process.execPath,
    args: ['tests/test_management_token_dialog.js'],
  },
  {
    label: 'Skills Library progress and repair DOM behavior',
    command: process.execPath,
    args: ['tests/test_skill_library_organization_ui_states.js'],
  },
];

const evidence = [];
for (const item of commands) {
  const startedAt = Date.now();
  const result = spawnSync(item.command, item.args, {
    cwd: process.cwd(),
    encoding: 'utf8',
    env: process.env,
  });
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  if (result.status !== 0) {
    throw new Error(`${item.label} failed with exit code ${result.status}`);
  }
  evidence.push({
    scenario: item.label,
    durationMs: Date.now() - startedAt,
  });
}

console.log(JSON.stringify({ ok: true, evidence }, null, 2));
