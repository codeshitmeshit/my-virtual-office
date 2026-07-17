import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const review = readFileSync('app/project-authoring-review.js', 'utf8');
const projects = readFileSync('app/projects.js', 'utf8');
const index = readFileSync('app/index.html', 'utf8');
const styles = readFileSync('app/project-authoring-review.css', 'utf8');

assert.ok(review.includes("'/api/project-authoring/requests?state=pending,failed,materializing&limit=100'"));
assert.ok(review.includes('window.i18n.managementFetch'), 'review reads must use management authentication');
assert.ok(review.includes('originalDraft'));
assert.ok(review.includes('workingDraft'));
assert.ok(review.includes('approvedSnapshot'));
assert.ok(review.includes('reviewerRecommendation'));
assert.ok(review.includes('rationale'));
assert.ok(review.includes('working.template'));
assert.ok(review.includes('working.recurrence'));
assert.ok(review.includes('request.issues'));
assert.ok(review.includes('request.error'));
assert.ok(review.includes('id="project-authoring-approved-draft"'));
assert.ok(review.includes('data-request-revision'));
assert.ok(projects.includes('ProjectAuthoringReview.show()'));
assert.ok(index.includes('project-authoring-review.css'));
assert.ok(index.includes('project-authoring-review.js'));
assert.ok(styles.includes('.par-two-column'));
assert.ok(styles.includes('@media (max-width: 900px)'));

console.log('project authoring review static checks passed');
