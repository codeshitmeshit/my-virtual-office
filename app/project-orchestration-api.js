(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(root);
    } else {
        root.ProjectOrchestrationAPI = factory(root);
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    function managementFetch() {
        if (root.i18n && typeof root.i18n.managementFetch === 'function') {
            return root.i18n.managementFetch.bind(root.i18n);
        }
        if (typeof root.fetch === 'function') {
            return root.fetch.bind(root);
        }
        throw new Error('No fetch implementation is available');
    }

    function normalizeResponsePayload(payload) {
        return payload && typeof payload === 'object' ? payload : {};
    }

    function savedResult(payload, status) {
        return {
            ok: true,
            saved: true,
            status: status,
            project: payload.project,
            orchestration: payload.orchestration,
            assignments: Array.isArray(payload.assignments) ? payload.assignments : [],
            currentRevision: payload.currentRevision,
        };
    }

    function rejectedResult(payload, status) {
        var result = {
            ok: false,
            saved: false,
            status: status,
            code: payload.code || 'orchestration_autosave_rejected',
            error: payload.error || payload.message || null,
        };
        if (status === 409) {
            result.conflict = true;
            result.currentRevision = payload.currentRevision;
            result.orchestration = payload.orchestration;
            result.assignments = Array.isArray(payload.assignments) ? payload.assignments : [];
        }
        return result;
    }

    async function parseJson(response) {
        if (!response || typeof response.json !== 'function') return {};
        try {
            return normalizeResponsePayload(await response.json());
        } catch (err) {
            var status = response && typeof response.status === 'number' ? response.status : 0;
            return {
                ok: false,
                code: 'invalid_json_response',
                error: 'Server returned a non-JSON response' + (status ? ' (HTTP ' + status + ')' : ''),
            };
        }
    }

    async function autosaveAssignments(options) {
        var opts = options || {};
        var projectId = String(opts.projectId || '').trim();
        if (!projectId) {
            return {
                ok: false,
                saved: false,
                status: 0,
                code: 'missing_project_id',
                error: 'Project id is required',
            };
        }
        var assignments = Array.isArray(opts.assignments) ? opts.assignments : [];
        var fetcher = typeof opts.fetcher === 'function' ? opts.fetcher : managementFetch();
        var response;
        try {
            response = await fetcher('/api/projects/' + encodeURIComponent(projectId) + '/orchestration', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    revision: opts.revision,
                    assignments: assignments.map(function (assignment) {
                        return {
                            taskId: assignment.taskId,
                            executionStage: assignment.executionStage,
                        };
                    }),
                }),
            });
        } catch (err) {
            return {
                ok: false,
                saved: false,
                status: 0,
                code: 'orchestration_autosave_failed',
                error: err && err.message ? err.message : String(err || 'Unknown autosave failure'),
            };
        }

        var payload = await parseJson(response);
        var status = response && typeof response.status === 'number' ? response.status : 0;
        if (!response || response.ok !== true || payload.ok === false) {
            return rejectedResult(payload, status);
        }
        return savedResult(payload, status);
    }

    async function saveCompletedDrag(options) {
        return autosaveAssignments(options);
    }

    async function postProjectAction(projectId, suffix, body, options) {
        var id = String(projectId || '').trim();
        if (!id) {
            return {
                ok: false,
                saved: false,
                status: 0,
                code: 'missing_project_id',
                error: 'Project id is required',
            };
        }
        var opts = options || {};
        var fetcher = typeof opts.fetcher === 'function' ? opts.fetcher : managementFetch();
        try {
            var response = await fetcher('/api/projects/' + encodeURIComponent(id) + suffix, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            });
            var payload = await parseJson(response);
            var status = response && typeof response.status === 'number' ? response.status : 0;
            return {
                ...normalizeResponsePayload(payload),
                ok: Boolean(response && response.ok === true && payload.ok !== false),
                status: status,
            };
        } catch (err) {
            return {
                ok: false,
                status: 0,
                code: 'orchestration_action_failed',
                error: err && err.message ? err.message : String(err || 'Unknown orchestration action failure'),
            };
        }
    }

    async function pauseProject(options) {
        var opts = options || {};
        return postProjectAction(opts.projectId, '/orchestration/pause', opts.body, opts);
    }

    async function resumeProject(options) {
        var opts = options || {};
        return postProjectAction(opts.projectId, '/orchestration/resume', opts.body, opts);
    }

    async function requestTaskSkip(options) {
        var opts = options || {};
        var projectId = String(opts.projectId || '').trim();
        var taskId = String(opts.taskId || '').trim();
        if (!taskId) {
            return { ok: false, status: 0, code: 'missing_task_id', error: 'Task id is required' };
        }
        return postProjectAction(projectId, '/tasks/' + encodeURIComponent(taskId) + '/orchestration/skip-request', opts.body, opts);
    }

    async function decideTaskSkip(options) {
        var opts = options || {};
        var projectId = String(opts.projectId || '').trim();
        var taskId = String(opts.taskId || '').trim();
        if (!taskId) {
            return { ok: false, status: 0, code: 'missing_task_id', error: 'Task id is required' };
        }
        return postProjectAction(projectId, '/tasks/' + encodeURIComponent(taskId) + '/orchestration/skip-decision', opts.body, opts);
    }

    return {
        autosaveAssignments: autosaveAssignments,
        saveCompletedDrag: saveCompletedDrag,
        pauseProject: pauseProject,
        resumeProject: resumeProject,
        requestTaskSkip: requestTaskSkip,
        decideTaskSkip: decideTaskSkip,
    };
});
