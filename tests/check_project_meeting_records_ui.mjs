import assert from 'node:assert/strict';
import fs from 'node:fs';

const projectsJs = fs.readFileSync('app/projects.js', 'utf8');
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));

const requiredKeys = [
  'proj_meeting_records',
  'proj_meeting_record_status_approved',
  'proj_meeting_record_status_no_consensus',
  'proj_meeting_record_status_rejected',
  'proj_meeting_record_status_needs_user_decision',
  'proj_meeting_record_risks',
  'proj_meeting_record_actions',
  'proj_meeting_record_meeting',
  'proj_meeting_record_request',
];

for (const key of requiredKeys) {
  assert.ok(en[key], `missing en locale key: ${key}`);
  assert.ok(zh[key], `missing zh locale key: ${key}`);
  assert.ok(projectsJs.includes(key), `projects.js does not use locale key: ${key}`);
}

assert.ok(projectsJs.includes('taskMeetingRecords'), 'task detail should derive task meeting records');
assert.ok(projectsJs.includes('meetingRecords'), 'task detail should render explicit meetingRecords');
assert.ok(!projectsJs.includes('会议议论要点'), 'old hard-coded meeting discussion title should be removed');

console.log('project meeting records UI checks passed');
