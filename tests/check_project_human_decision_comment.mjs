import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const UI = require(path.join(root, 'app', 'project-human-decision-comment-ui.js'));
const projects = fs.readFileSync(path.join(root, 'app', 'projects.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const style = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');
const helperSource = fs.readFileSync(path.join(root, 'app', 'project-human-decision-comment-ui.js'), 'utf8');

const webviewContext = { module: { exports: {} } };
webviewContext.globalThis = webviewContext;
vm.runInNewContext(helperSource, webviewContext);
assert.equal(
  typeof webviewContext.ProjectHumanDecisionCommentUI?.render,
  'function',
  'helper must register on the browser global even when a WebView exposes CommonJS module',
);

const comment = {
  id: 'comment-1',
  kind: 'human_decision',
  author: 'human_decision',
  decisionId: 'decision-1',
  decisionTitle: '确认发布策略',
  decisionAnswer: '分阶段发布',
  customAnswer: '',
  createdAt: '2026-08-08T17:00:00+08:00',
};

assert.equal(UI.isDecisionComment(comment), true);
assert.equal(UI.isDecisionComment({ author: 'user', text: 'hello' }), false);
const html = UI.render(comment, {
  t: (_key, fallback) => fallback,
  escape: (value) => String(value),
  timeAgo: (value) => value,
});
assert.match(html, /👤/);
assert.match(html, /确认发布策略/);
assert.match(html, /分阶段发布/);
assert.match(html, /decision-1/);

assert.match(projects, /ProjectHumanDecisionCommentUI\.isDecisionComment\(c\)/);
assert.match(projects, /ProjectHumanDecisionCommentUI\.render\(c/);
assert.ok(
  index.indexOf('<script src="project-human-decision-comment-ui.js') < index.indexOf('<script src="projects.js'),
  'project decision comment helper must load before projects.js',
);
assert.match(style, /\.proj-comment-human-decision/);

console.log('project human decision task comment checks passed');
