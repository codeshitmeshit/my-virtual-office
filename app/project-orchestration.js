(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(root);
    } else {
        root.ProjectOrchestration = factory(root);
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    var activeSession = null;
    var FIT_SCALE = 1;
    var STATUS_CLASSES = ['is-saving', 'is-saved', 'has-error', 'has-conflict'];
    var EDITABLE_STATES = { draft: true, paused: true, blocked: true };
    var STAGE_COLUMN_LEFT = 24;
    var STAGE_COLUMN_STEP = 233;
    var TASK_CARD_WIDTH = 190;
    var CANVAS_BASE_WIDTH = 1184;
    var TASK_CARD_TOP = 141;
    var TASK_CARD_HEIGHT = 68;
    var TASK_CARD_GAP = 12;

    function text(value) {
        return value == null ? '' : String(value);
    }

    function numberOr(value, fallback) {
        var parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function isDone(task) {
        var state = text(task && task.executionState).toLowerCase();
        return Boolean(task && task.completedAt) || state === 'done' || state === 'completed';
    }

    function taskState(task) {
        var state = text(task && task.executionState).trim().toLowerCase();
        if (state === 'executing' || state === 'running' || state === 'in_progress' || state === 'in-progress') {
            return { key: 'in-progress', label: 'IN PROGRESS' };
        }
        if (state === 'reviewing' || state === 'review') {
            return { key: 'review', label: 'REVIEW' };
        }
        if (state === 'blocked' || state === 'failed') {
            return { key: state, label: state.toUpperCase() };
        }
        if (isDone(task)) return { key: 'done', label: 'DONE' };
        return { key: 'backlog', label: 'BACKLOG' };
    }

    function normalizeStage(value) {
        var stage = Math.trunc(numberOr(value, 0));
        return stage > 0 ? stage : 1;
    }

    function taskPriority(task) {
        return text(task && task.priority || 'medium').toUpperCase();
    }

    function taskOwner(task) {
        return text(task && (task.assigneeName || task.assignee || task.executorAgentId || task.executor || 'Unassigned'));
    }

    function skipState(task) {
        var skip = task && task.orchestrationSkip && typeof task.orchestrationSkip === 'object' ? task.orchestrationSkip : {};
        var status = text(skip.status || '').trim().toLowerCase();
        if (status === 'requested') return { key: 'skip-requested', label: 'SKIP?' };
        if (status === 'approved') return { key: 'skip-approved', label: 'SKIPPED' };
        if (status === 'rejected') return { key: 'skip-rejected', label: 'SKIP NO' };
        return { key: '', label: '' };
    }

    function cloneProject(project) {
        if (!project || typeof project !== 'object') return {};
        return {
            ...project,
            orchestration: project.orchestration && typeof project.orchestration === 'object' ? { ...project.orchestration } : project.orchestration,
            tasks: Array.isArray(project.tasks) ? project.tasks.map(function (task) { return task && typeof task === 'object' ? { ...task } : task; }) : [],
        };
    }

    function buildViewModel(project) {
        var source = project && typeof project === 'object' ? project : {};
        var tasks = Array.isArray(source.tasks) ? source.tasks.slice() : [];
        var stagesByNumber = new Map();
        tasks.forEach(function (task, index) {
            if (!task || typeof task !== 'object') return;
            var stage = normalizeStage(task.executionStage);
            if (!stagesByNumber.has(stage)) {
                stagesByNumber.set(stage, { stage: stage, tasks: [] });
            }
            var state = taskState(task);
            var skip = skipState(task);
            stagesByNumber.get(stage).tasks.push({
                id: text(task.id || 'task-' + index),
                title: text(task.title || 'Untitled task'),
                stage: stage,
                priority: taskPriority(task),
                owner: taskOwner(task),
                state: state.key,
                stateLabel: state.label,
                skipState: skip.key,
                skipLabel: skip.label,
                source: task,
            });
        });
        var stages = Array.from(stagesByNumber.values()).sort(function (a, b) { return a.stage - b.stage; });
        stages.forEach(function (stage) {
            stage.tasks.sort(function (a, b) {
                return numberOr(a.source.order, 999999) - numberOr(b.source.order, 999999)
                    || text(a.source.createdAt).localeCompare(text(b.source.createdAt))
                    || a.id.localeCompare(b.id);
            });
        });
        var orchestration = source.orchestration && typeof source.orchestration === 'object' ? source.orchestration : {};
        var state = text(orchestration.state || source.orchestrationState || 'draft');
        var locked = !EDITABLE_STATES[state];
        return {
            projectId: text(source.id),
            title: text(source.title || '任务流水线编排'),
            revision: numberOr(orchestration.revision, numberOr(source.orchestrationRevision, 0)),
            state: state,
            currentStage: numberOr(orchestration.currentStage, numberOr(source.currentStage, null)),
            activeTaskIds: Array.isArray(source.activeTaskIds) ? source.activeTaskIds.map(text).filter(Boolean) : [],
            pauseReason: text(orchestration.pauseReason || source.pauseReason || ''),
            locked: locked,
            canEdit: !locked,
            canAddTask: !locked || state === 'completed',
            canPause: state === 'running' || state === 'starting',
            canResume: state === 'paused' || state === 'blocked',
            completed: state === 'completed',
            taskCount: tasks.length,
            stageCount: stages.length,
            stages: stages,
        };
    }

    function createEl(doc, tag, className, textValue) {
        var el = doc.createElement(tag);
        if (className) el.className = className;
        if (textValue != null) el.textContent = text(textValue);
        return el;
    }

    function button(doc, className, textValue, onClick, disabled) {
        var el = createEl(doc, 'button', className, textValue);
        el.type = 'button';
        if (disabled) {
            el.disabled = true;
            el.setAttribute('disabled', 'disabled');
        }
        if (onClick && !disabled) el.addEventListener('click', onClick);
        return el;
    }

    function renderTask(doc, task, session) {
        var item = createEl(doc, 'div', 'project-orchestration-task is-' + task.state);
        item.setAttribute('data-task-id', task.id);
        item.setAttribute('data-stage', String(task.stage));
        if (task.skipState) item.className += ' is-' + task.skipState;
        if (task.skipState) item.setAttribute('data-skip-state', task.skipState);
        if (!session || session.viewModel.canEdit) item.setAttribute('draggable', 'true');
        if (session && session.viewModel.canEdit) {
            item.addEventListener('dragover', function (event) {
                if (event && event.preventDefault) event.preventDefault();
            });
            item.addEventListener('drop', function (event) {
                if (event && event.preventDefault) event.preventDefault();
                if (event && event.stopPropagation) event.stopPropagation();
                var taskId = getDraggedTaskId(session, event);
                if (taskId && taskId !== task.id) {
                    session.dragDropHandled = true;
                    moveTaskToStage(session, taskId, task.stage);
                }
            });
        }

        var row = createEl(doc, 'div', 'project-orchestration-task-row');
        row.appendChild(createEl(doc, 'span', 'project-orchestration-number', task.stage));
        row.appendChild(createEl(doc, 'span', 'project-orchestration-task-title', task.title));
        row.appendChild(createEl(doc, 'span', 'project-orchestration-state is-' + task.state, task.stateLabel));
        if (task.skipLabel) row.appendChild(createEl(doc, 'span', 'project-orchestration-skip-state is-' + task.skipState, task.skipLabel));
        item.appendChild(row);
        item.appendChild(createEl(doc, 'p', 'project-orchestration-task-meta', task.priority + ' · ' + task.owner));
        if (session) {
            var actions = createEl(doc, 'div', 'project-orchestration-task-actions');
            var skipRequested = task.skipState === 'skip-requested';
            var skipDisabled = session.viewModel.completed || session.saving || task.skipState === 'skip-approved';
            actions.appendChild(button(doc, 'project-orchestration-icon-action is-skip-request', 'SKIP', function () {
                requestSkip(session, task.id);
            }, skipDisabled || skipRequested));
            if (skipRequested) {
                actions.appendChild(button(doc, 'project-orchestration-icon-action is-skip-approve', 'OK', function () {
                    decideSkip(session, task.id, 'approve');
                }, session.saving));
                actions.appendChild(button(doc, 'project-orchestration-icon-action is-skip-reject', 'NO', function () {
                    decideSkip(session, task.id, 'reject');
                }, session.saving));
            }
            item.appendChild(actions);
        }
        return item;
    }

    function renderCanvas(doc, viewModel, session) {
        var canvas = createEl(doc, 'div', 'project-orchestration-canvas');
        var surface = createEl(doc, 'div', 'project-orchestration-canvas-surface');
        var layout = canvasLayout(viewModel, session && session.project);
        surface.style.width = layout.width + 'px';
        surface.style.height = layout.height + 'px';
        canvas.setAttribute('data-fit-scale', String(FIT_SCALE));
        if (session) {
            canvas.addEventListener('dragover', function (event) {
                if (event && event.preventDefault) event.preventDefault();
            });
            canvas.addEventListener('drop', function (event) {
                if (event && event.preventDefault) event.preventDefault();
                var taskId = getDraggedTaskId(session, event);
                if (taskId) {
                    session.dragDropHandled = true;
                    moveTaskToStage(session, taskId, stageFromCanvasDrop(session, event));
                }
            });
        }
        viewModel.stages.forEach(function (stage, index) {
            var stageNode = createEl(doc, 'div', 'project-orchestration-stage');
            stageNode.setAttribute('data-stage', String(stage.stage));
            stageNode.style.left = stageColumnLeft(stage.stage) + 'px';
            stageNode.style.top = stageColumnTop(stage.stage) + 'px';
            if (session) {
                stageNode.addEventListener('dragover', function (event) {
                    if (event && event.preventDefault) event.preventDefault();
                });
                stageNode.addEventListener('drop', function (event) {
                    if (event && event.preventDefault) event.preventDefault();
                    if (event && event.stopPropagation) event.stopPropagation();
                    var taskId = getDraggedTaskId(session, event);
                    if (taskId) {
                        session.dragDropHandled = true;
                        moveTaskToStage(session, taskId, stage.stage);
                    }
                });
            }
            stage.tasks.forEach(function (task) {
                var taskNode = renderTask(doc, task, session);
                if (session && session.viewModel.canEdit) attachTaskDragHandlers(taskNode, task, session);
                stageNode.appendChild(taskNode);
            });
            surface.appendChild(stageNode);
            if (index < viewModel.stages.length - 1) {
                var connector = createEl(doc, 'span', 'project-orchestration-connector', '->');
                connector.setAttribute('data-from', String(stage.stage));
                connector.style.left = (stageColumnLeft(stage.stage) + TASK_CARD_WIDTH + 13) + 'px';
                connector.style.top = connectorTop(stage) + 'px';
                surface.appendChild(connector);
                if (session && viewModel.canEdit) {
                    var insertNode = createEl(doc, 'div', 'project-orchestration-insert-stage', '+ 插入阶段');
                    insertNode.setAttribute('data-insert-after-stage', String(stage.stage));
                    insertNode.style.left = interStageTargetLeft(stage.stage) + 'px';
                    insertNode.style.top = stageColumnTop(stage.stage) + 'px';
                    insertNode.addEventListener('dragover', function (event) {
                        if (event && event.preventDefault) event.preventDefault();
                        classListSet(insertNode, 'is-drag-over', true);
                    });
                    insertNode.addEventListener('dragleave', function () {
                        classListSet(insertNode, 'is-drag-over', false);
                    });
                    insertNode.addEventListener('drop', function (event) {
                        if (event && event.preventDefault) event.preventDefault();
                        if (event && event.stopPropagation) event.stopPropagation();
                        classListSet(insertNode, 'is-drag-over', false);
                        var taskId = getDraggedTaskId(session, event);
                        if (taskId) insertTaskAfterStage(session, taskId, stage.stage);
                    });
                    surface.appendChild(insertNode);
                }
            }
        });
        if (session && viewModel.canEdit) {
            var nextStage = maxStage(session.project) + 1;
            var newStageNode = createEl(doc, 'div', 'project-orchestration-new-stage', '+ 新阶段');
            newStageNode.setAttribute('data-stage', String(nextStage));
            newStageNode.style.left = stageColumnLeft(nextStage) + 'px';
            newStageNode.style.top = stageColumnTop(nextStage) + 'px';
            newStageNode.addEventListener('dragover', function (event) {
                if (event && event.preventDefault) event.preventDefault();
                classListSet(newStageNode, 'is-drag-over', true);
            });
            newStageNode.addEventListener('dragleave', function () {
                classListSet(newStageNode, 'is-drag-over', false);
            });
            newStageNode.addEventListener('drop', function (event) {
                if (event && event.preventDefault) event.preventDefault();
                if (event && event.stopPropagation) event.stopPropagation();
                classListSet(newStageNode, 'is-drag-over', false);
                var taskId = getDraggedTaskId(session, event);
                if (taskId) {
                    session.dragDropHandled = true;
                    moveTaskToStage(session, taskId, maxStage(session.project) + 1);
                }
            });
            surface.appendChild(newStageNode);
        }
        canvas.appendChild(surface);
        return canvas;
    }

    function applyFitScale(session) {
        if (!session || !session.canvas) return 1;
        var viewport = session.modal && session.modal.getBoundingClientRect ? session.modal.getBoundingClientRect().width - 36 : 1184;
        var scale = Math.max(0.5, Math.min(1, viewport / 1184));
        session.canvas.style.transformOrigin = 'top left';
        session.canvas.style.transform = 'scale(' + scale.toFixed(3) + ')';
        session.canvas.setAttribute('data-fit-scale', scale.toFixed(3));
        session.fitScale = scale;
        return scale;
    }

    function classListSet(el, className, enabled) {
        if (!el) return;
        if (el.classList && el.classList.toggle) {
            el.classList.toggle(className, Boolean(enabled));
            return;
        }
        var classes = String(el.className || '').split(/\s+/).filter(Boolean);
        var hasClass = classes.indexOf(className) !== -1;
        if (enabled && !hasClass) classes.push(className);
        if (!enabled && hasClass) classes = classes.filter(function (item) { return item !== className; });
        el.className = classes.join(' ');
    }

    function setStatus(session, status, message) {
        if (!session) return;
        session.status = status || 'idle';
        session.statusMessage = text(message);
        STATUS_CLASSES.forEach(function (className) { classListSet(session.modal, className, false); });
        if (status === 'saving') classListSet(session.modal, 'is-saving', true);
        if (status === 'saved') classListSet(session.modal, 'is-saved', true);
        if (status === 'error') classListSet(session.modal, 'has-error', true);
        if (status === 'conflict') classListSet(session.modal, 'has-conflict', true);
        if (session.statusEl) {
            session.statusEl.textContent = session.statusMessage;
            session.statusEl.setAttribute('data-status', session.status);
        }
    }

    function renderModal(doc, viewModel, options, session) {
        var opts = options || {};
        var overlay = createEl(doc, 'div', 'project-orchestration-overlay');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('data-project-id', viewModel.projectId);

        var modal = createEl(doc, 'section', 'project-orchestration-modal is-' + viewModel.state);
        if (viewModel.locked) modal.className += ' is-locked';
        if (viewModel.completed) modal.className += ' is-completed';
        overlay.appendChild(modal);

        var header = createEl(doc, 'header', 'project-orchestration-header');
        var heading = createEl(doc, 'div', 'project-orchestration-heading');
        heading.appendChild(createEl(doc, 'h2', 'project-orchestration-title', opts.title || '任务流水线编排'));
        heading.appendChild(createEl(doc, 'p', 'project-orchestration-subtitle', opts.subtitle || '拖动任务调整执行编号；相同编号的任务并行执行'));
        header.appendChild(heading);
        header.appendChild(button(doc, 'project-orchestration-close', 'x', close));
        modal.appendChild(header);

        var notice = createEl(doc, 'div', 'project-orchestration-notice');
        notice.appendChild(createEl(doc, 'span', 'project-orchestration-notice-icon', 'i'));
        notice.appendChild(createEl(doc, 'span', '', '任务编号就是执行阶段；相同编号的任务并行，全部完成后进入下一个编号。'));
        modal.appendChild(notice);

        var workspace = createEl(doc, 'div', 'project-orchestration-workspace');
        var controls = createEl(doc, 'div', 'project-orchestration-controls');
        controls.appendChild(button(doc, 'project-orchestration-button is-add', '+ 添加任务', function () { addTask(session || activeSession); }, !viewModel.canAddTask));
        controls.appendChild(createEl(doc, 'span', 'project-orchestration-count', viewModel.taskCount + ' TASKS · ' + viewModel.stageCount + ' STEPS'));
        var statusEl = createEl(doc, 'span', 'project-orchestration-status');
        statusEl.setAttribute('data-status', 'idle');
        controls.appendChild(statusEl);
        controls.appendChild(createEl(doc, 'span', 'project-orchestration-spacer'));
        controls.appendChild(createEl(doc, 'span', 'project-orchestration-parallel-hint', '相同编号并行'));
        if (viewModel.canPause) controls.appendChild(button(doc, 'project-orchestration-button is-pause', '暂停', function () { pauseProject(session || activeSession); }));
        if (viewModel.canResume) controls.appendChild(button(doc, 'project-orchestration-button is-resume', '恢复', function () { resumeProject(session || activeSession); }));
        controls.appendChild(button(doc, 'project-orchestration-button is-fit', '适配画布', function () { fitCanvas(); }));
        workspace.appendChild(controls);
        var canvas = renderCanvas(doc, viewModel, session);
        workspace.appendChild(canvas);
        modal.appendChild(workspace);

        var footer = createEl(doc, 'footer', 'project-orchestration-footer');
        footer.appendChild(createEl(doc, 'p', 'project-orchestration-footer-hint', '横向拖动调整任务编号 · 同编号任务纵向排列并行执行'));
        footer.appendChild(createEl(doc, 'span', 'project-orchestration-spacer'));
        footer.appendChild(button(doc, 'project-orchestration-cancel', '取消', close));
        modal.appendChild(footer);

        return { overlay: overlay, modal: modal, canvas: canvas, statusEl: statusEl };
    }

    function resolveApi(options) {
        if (options && options.api) return options.api;
        if (root.ProjectOrchestrationAPI) return root.ProjectOrchestrationAPI;
        return null;
    }

    function assignmentsFromProject(project) {
        var tasks = Array.isArray(project && project.tasks) ? project.tasks : [];
        return tasks.filter(function (task) { return task && task.id; }).map(function (task) {
            return { taskId: task.id, executionStage: normalizeStage(task.executionStage) };
        });
    }

    function maxStage(project) {
        var max = 0;
        (Array.isArray(project && project.tasks) ? project.tasks : []).forEach(function (task) {
            max = Math.max(max, normalizeStage(task && task.executionStage));
        });
        return max || 1;
    }

    function normalizeProjectStages(project) {
        var sourceStages = [];
        var seen = {};
        (Array.isArray(project && project.tasks) ? project.tasks : []).forEach(function (task) {
            var stage = normalizeStage(task && task.executionStage);
            if (!seen[stage]) {
                seen[stage] = true;
                sourceStages.push(stage);
            }
        });
        sourceStages.sort(function (a, b) { return a - b; });
        var remap = {};
        sourceStages.forEach(function (stage, index) { remap[stage] = index + 1; });
        (Array.isArray(project && project.tasks) ? project.tasks : []).forEach(function (task) {
            task.executionStage = remap[normalizeStage(task && task.executionStage)] || 1;
        });
    }

    function applyAssignments(project, assignments) {
        if (!Array.isArray(assignments) || !assignments.length) return;
        var byTask = {};
        assignments.forEach(function (assignment) {
            byTask[text(assignment && assignment.taskId)] = normalizeStage(assignment && assignment.executionStage);
        });
        (Array.isArray(project && project.tasks) ? project.tasks : []).forEach(function (task) {
            if (task && byTask[text(task.id)]) task.executionStage = byTask[text(task.id)];
        });
        normalizeProjectStages(project);
    }

    function applyOrchestration(project, orchestration, revision) {
        if (orchestration && typeof orchestration === 'object') {
            project.orchestration = { ...(project.orchestration && typeof project.orchestration === 'object' ? project.orchestration : {}), ...orchestration };
        }
        if (revision != null) {
            project.orchestration = project.orchestration && typeof project.orchestration === 'object' ? project.orchestration : {};
            project.orchestration.revision = numberOr(revision, project.orchestration.revision || 0);
        }
    }

    function replaceChildren(parent, child) {
        if (parent.replaceChildren) {
            parent.replaceChildren(child);
            return;
        }
        while (parent.firstChild && parent.removeChild) parent.removeChild(parent.firstChild);
        if (Array.isArray(parent.children)) parent.children.slice().forEach(function (existing) { existing.remove(); });
        parent.appendChild(child);
    }

    function renderSession(session, status, message) {
        var viewModel = buildViewModel(session.project);
        var rendered = renderModal(session.document, viewModel, session.options, session);
        replaceChildren(session.overlay, rendered.modal);
        session.modal = rendered.modal;
        session.canvas = rendered.canvas;
        session.statusEl = rendered.statusEl;
        session.viewModel = viewModel;
        setStatus(session, status || session.status || 'idle', message || session.statusMessage || '');
        if (session.fitScale !== FIT_SCALE) applyFitScale(session);
    }

    function loadAuthoritativeProject(session, result) {
        if (result && result.project) {
            session.project = cloneProject(result.project);
        } else {
            applyAssignments(session.project, result && result.assignments);
            applyOrchestration(session.project, result && result.orchestration, result && result.currentRevision);
        }
        renderSession(session, result && result.conflict ? 'conflict' : 'saved', result && result.conflict ? '远端已更新，已重新载入' : '已保存');
    }

    function applyActionResult(session, result, successMessage) {
        if (!session) return result;
        if (result && result.ok !== false) {
            if (result.project) {
                session.project = cloneProject(result.project);
            } else {
                if (result.orchestration || result.currentRevision != null) {
                    applyOrchestration(session.project, result.orchestration, result.currentRevision);
                }
                if (result.task && Array.isArray(session.project.tasks)) {
                    session.project.tasks = session.project.tasks.map(function (task) {
                        return text(task && task.id) === text(result.task.id) ? { ...task, ...result.task } : task;
                    });
                }
                if (result.assignments) applyAssignments(session.project, result.assignments);
            }
            renderSession(session, 'saved', successMessage || '已更新');
        } else {
            setStatus(session, 'error', result && (result.error || result.code) || '操作失败');
        }
        return result;
    }

    function getDraggedTaskId(session, event) {
        if (event && event.dataTransfer && event.dataTransfer.getData) {
            return text(event.dataTransfer.getData('text/plain') || event.dataTransfer.getData('text'));
        }
        return text(session && session.draggingTaskId);
    }

    function stageColumnLeft(stage) {
        return STAGE_COLUMN_LEFT + (normalizeStage(stage) - 1) * STAGE_COLUMN_STEP;
    }

    function stageColumnTop(stage) {
        return TASK_CARD_TOP;
    }

    function interStageTargetLeft(stage) {
        return stageColumnLeft(stage) + Math.round((STAGE_COLUMN_STEP + TASK_CARD_WIDTH) / 2) - Math.round(TASK_CARD_WIDTH / 2);
    }

    function maxStageForLayout(viewModel, project) {
        var maxVisible = maxStage(project);
        (viewModel && viewModel.stages || []).forEach(function (stage) {
            maxVisible = Math.max(maxVisible, normalizeStage(stage && stage.stage));
        });
        return maxVisible || 1;
    }

    function canvasLayout(viewModel, project) {
        var maxVisibleStage = maxStageForLayout(viewModel, project) + (viewModel && viewModel.canEdit ? 1 : 0);
        var width = Math.max(CANVAS_BASE_WIDTH, stageColumnLeft(maxVisibleStage) + TASK_CARD_WIDTH + 64);
        var maxStack = 1;
        (viewModel && viewModel.stages || []).forEach(function (stage) {
            maxStack = Math.max(maxStack, Array.isArray(stage.tasks) ? stage.tasks.length : 0);
        });
        var height = Math.max(
            350,
            TASK_CARD_TOP + maxStack * TASK_CARD_HEIGHT + Math.max(0, maxStack - 1) * TASK_CARD_GAP + 44
        );
        return { width: width, height: height };
    }

    function connectorTop(stage) {
        var taskCount = stage && Array.isArray(stage.tasks) ? Math.max(1, stage.tasks.length) : 1;
        var stackHeight = taskCount * TASK_CARD_HEIGHT + Math.max(0, taskCount - 1) * TASK_CARD_GAP;
        return TASK_CARD_TOP + Math.min(TASK_CARD_HEIGHT, stackHeight) / 2 - 10;
    }

    function taskStage(project, taskId) {
        var targetId = text(taskId);
        var tasks = Array.isArray(project && project.tasks) ? project.tasks : [];
        var task = tasks.find(function (item) { return text(item && item.id) === targetId; });
        return normalizeStage(task && task.executionStage);
    }

    function stageFromCanvasDrop(session, event) {
        if (!session || !session.canvas || !event || !Number.isFinite(Number(event.clientX))) {
            return maxStage(session && session.project);
        }
        var rect = session.canvas.getBoundingClientRect ? session.canvas.getBoundingClientRect() : {};
        var left = numberOr(rect.left, 0);
        var visualWidth = Math.max(1, numberOr(rect.width, CANVAS_BASE_WIDTH));
        var visualScale = Math.max(0.1, numberOr(session.fitScale, visualWidth / CANVAS_BASE_WIDTH));
        var x = ((Number(event.clientX) - left) + numberOr(session.canvas.scrollLeft, 0)) / visualScale;
        var currentMax = maxStage(session.project);
        var target = 1;
        for (var stage = 1; stage <= currentMax; stage += 1) {
            if (x >= stageColumnLeft(stage)) target = stage;
        }
        return target;
    }

    function attachTaskDragHandlers(taskNode, task, session) {
        var doc = taskNode.ownerDocument || (session && session.document);
        function rememberDragEvent(event) {
            if (event && Number.isFinite(Number(event.clientX)) && Number.isFinite(Number(event.clientY))) {
                session.lastDragEvent = event;
            }
        }
        taskNode.addEventListener('dragstart', function (event) {
            session.draggingTaskId = task.id;
            session.dragStartStage = taskStage(session.project, task.id);
            session.dragDropHandled = false;
            session.lastDragEvent = event || null;
            if (doc && typeof doc.addEventListener === 'function') {
                doc.addEventListener('dragover', rememberDragEvent);
            }
            classListSet(taskNode, 'is-dragging', true);
            classListSet(session.modal, 'is-dragging-task', true);
            if (event && event.dataTransfer && event.dataTransfer.setData) {
                event.dataTransfer.setData('text/plain', task.id);
                event.dataTransfer.effectAllowed = 'move';
            }
        });
        taskNode.addEventListener('drag', rememberDragEvent);
        taskNode.addEventListener('dragend', function (event) {
            if (doc && typeof doc.removeEventListener === 'function') {
                doc.removeEventListener('dragover', rememberDragEvent);
            }
            var shouldFallback = !session.dragDropHandled
                && session.draggingTaskId === task.id
                && session.lastDragEvent
                && Number.isFinite(Number(session.lastDragEvent.clientX))
                && Number.isFinite(Number(session.lastDragEvent.clientY));
            var fallbackEvent = session.lastDragEvent;
            classListSet(taskNode, 'is-dragging', false);
            classListSet(session.modal, 'is-dragging-task', false);
            session.draggingTaskId = null;
            session.lastDragEvent = null;
            session.dragDropHandled = false;
            if (shouldFallback) {
                var targetStage = stageFromCanvasDrop(session, fallbackEvent || event);
                if (targetStage !== session.dragStartStage) {
                    moveTaskToStage(session, task.id, targetStage);
                }
            }
            session.dragStartStage = null;
        });
        attachTaskPointerDragFallback(taskNode, task, session);
    }

    function isTaskActionTarget(target) {
        var node = target;
        while (node) {
            var classes = String(node.className || '').split(/\s+/);
            if (classes.indexOf('project-orchestration-icon-action') !== -1 || classes.indexOf('proj-orchestration-icon-action') !== -1) {
                return true;
            }
            node = node.parentNode;
        }
        return false;
    }

    function attachTaskPointerDragFallback(taskNode, task, session) {
        taskNode.addEventListener('pointerdown', function (event) {
            if (!session || !session.viewModel.canEdit || session.saving) return;
            if (event && event.button != null && event.button !== 0) return;
            if (isTaskActionTarget(event && event.target)) return;
            var doc = taskNode.ownerDocument || (session && session.document);
            if (!doc || typeof doc.addEventListener !== 'function') return;
            var startX = Number(event && event.clientX);
            var startY = Number(event && event.clientY);
            if (!Number.isFinite(startX) || !Number.isFinite(startY)) return;
            var active = false;
            var lastEvent = event;

            function cleanup() {
                if (typeof doc.removeEventListener === 'function') {
                    doc.removeEventListener('pointermove', onMove);
                    doc.removeEventListener('pointerup', onUp);
                    doc.removeEventListener('pointercancel', onCancel);
                }
                if (active) {
                    classListSet(taskNode, 'is-dragging', false);
                    classListSet(session.modal, 'is-dragging-task', false);
                }
                if (session.draggingTaskId === task.id) session.draggingTaskId = null;
            }

            function onMove(moveEvent) {
                lastEvent = moveEvent || lastEvent;
                var dx = Number(lastEvent.clientX) - startX;
                var dy = Number(lastEvent.clientY) - startY;
                if (!active && Math.sqrt(dx * dx + dy * dy) >= 6) {
                    active = true;
                    session.draggingTaskId = task.id;
                    classListSet(taskNode, 'is-dragging', true);
                    classListSet(session.modal, 'is-dragging-task', true);
                }
                if (active && lastEvent && lastEvent.preventDefault) lastEvent.preventDefault();
            }

            function onUp(upEvent) {
                lastEvent = upEvent || lastEvent;
                var shouldMove = active;
                cleanup();
                if (!shouldMove) return;
                if (lastEvent && lastEvent.preventDefault) lastEvent.preventDefault();
                moveTaskToStage(session, task.id, stageFromCanvasDrop(session, lastEvent));
            }

            function onCancel() {
                cleanup();
            }

            doc.addEventListener('pointermove', onMove);
            doc.addEventListener('pointerup', onUp);
            doc.addEventListener('pointercancel', onCancel);
        });
    }

    function moveTaskToStage(session, taskId, targetStage) {
        if (!session) return Promise.resolve(null);
        if (!session.viewModel.canEdit) {
            setStatus(session, 'error', '当前状态不可编辑');
            return Promise.resolve({ ok: false, code: 'orchestration_locked' });
        }
        var stage = normalizeStage(targetStage);
        var task = (Array.isArray(session.project.tasks) ? session.project.tasks : []).find(function (candidate) {
            return text(candidate && candidate.id) === text(taskId);
        });
        if (!task || normalizeStage(task.executionStage) === stage) return Promise.resolve(null);
        task.executionStage = stage;
        normalizeProjectStages(session.project);
        renderSession(session, 'saved', '本地已更新');
        return saveCompletedEdit(session, { silent: true });
    }

    function insertTaskAfterStage(session, taskId, afterStage) {
        if (!session) return Promise.resolve(null);
        if (!session.viewModel.canEdit) {
            setStatus(session, 'error', '当前状态不可编辑');
            return Promise.resolve({ ok: false, code: 'orchestration_locked' });
        }
        var targetId = text(taskId);
        var tasks = Array.isArray(session.project.tasks) ? session.project.tasks : [];
        var task = tasks.find(function (candidate) {
            return text(candidate && candidate.id) === targetId;
        });
        if (!task) return Promise.resolve(null);

        var previousAssignments = JSON.stringify(assignmentsFromProject(session.project));
        var insertAfter = normalizeStage(afterStage);
        var remainingStages = (session.viewModel && session.viewModel.stages || []).filter(function (stage) {
            return Array.isArray(stage.tasks) && stage.tasks.some(function (stageTask) {
                return text(stageTask && stageTask.id) !== targetId;
            });
        });
        var stageRemap = {};
        remainingStages.forEach(function (stage, index) {
            stageRemap[normalizeStage(stage && stage.stage)] = index + 1;
        });
        var insertStage = remainingStages.filter(function (stage) {
            return normalizeStage(stage && stage.stage) <= insertAfter;
        }).length + 1;

        tasks.forEach(function (candidate) {
            if (!candidate || text(candidate.id) === targetId) return;
            var compactedStage = stageRemap[normalizeStage(candidate.executionStage)] || 1;
            candidate.executionStage = compactedStage >= insertStage ? compactedStage + 1 : compactedStage;
        });
        task.executionStage = insertStage;
        normalizeProjectStages(session.project);

        if (JSON.stringify(assignmentsFromProject(session.project)) === previousAssignments) return Promise.resolve(null);
        renderSession(session, 'saved', '本地已更新');
        return saveCompletedEdit(session, { silent: true });
    }

    function saveCompletedEdit(session, options) {
        var opts = options || {};
        var api = resolveApi(session.options);
        if (!api || typeof api.saveCompletedDrag !== 'function') {
            setStatus(session, 'error', '缺少保存接口');
            return Promise.resolve({ ok: false, saved: false, code: 'missing_orchestration_api' });
        }
        session.saving = true;
        if (!opts.silent) setStatus(session, 'saving', '保存中');
        return api.saveCompletedDrag({
            projectId: session.viewModel.projectId,
            revision: session.viewModel.revision,
            assignments: assignmentsFromProject(session.project),
            fetcher: session.options && session.options.fetcher,
        }).then(function (result) {
            session.saving = false;
            if (result && result.ok && result.saved) {
                loadAuthoritativeProject(session, result);
            } else if (result && result.conflict) {
                loadAuthoritativeProject(session, result);
            } else {
                setStatus(session, 'error', result && (result.error || result.code) || '保存失败');
            }
            return result;
        }).catch(function (err) {
            session.saving = false;
            setStatus(session, 'error', err && err.message ? err.message : '保存失败');
            return { ok: false, saved: false, error: err };
        });
    }

    function addTask(session) {
        if (!session || session.saving) return Promise.resolve(null);
        if (!session.viewModel.canAddTask) {
            setStatus(session, 'error', '当前状态不可添加任务');
            return Promise.resolve({ ok: false, code: 'orchestration_locked' });
        }
        var nextStage = maxStage(session.project) + 1;
        if (!session.options || typeof session.options.onAddTask !== 'function') {
            setStatus(session, 'error', '缺少添加任务接口');
            return Promise.resolve({ ok: false, code: 'missing_add_task_handler' });
        }
        setStatus(session, 'saving', '添加中');
        return Promise.resolve(session.options.onAddTask({
            projectId: session.viewModel.projectId,
            revision: session.viewModel.revision,
            executionStage: nextStage,
        })).then(function (result) {
            if (result && result.cancelled) {
                setStatus(session, 'idle', '');
                return result;
            }
            if (result && result.project) {
                session.project = cloneProject(result.project);
            } else if (result && result.task) {
                session.project.tasks = Array.isArray(session.project.tasks) ? session.project.tasks : [];
                session.project.tasks.push({ ...result.task, executionStage: normalizeStage(result.task.executionStage || nextStage) });
                if (result.orchestration || result.currentRevision != null) {
                    applyOrchestration(session.project, result.orchestration, result.currentRevision);
                }
            } else {
                setStatus(session, 'error', '添加任务失败');
                return result || { ok: false, code: 'add_task_failed' };
            }
            normalizeProjectStages(session.project);
            renderSession(session, 'saved', '已添加');
            return result;
        }).catch(function (err) {
            setStatus(session, 'error', err && err.message ? err.message : '添加任务失败');
            return { ok: false, error: err };
        });
    }

    function callApiAction(session, method, payload, successMessage) {
        var api = resolveApi(session && session.options);
        if (!session || !api || typeof api[method] !== 'function') {
            setStatus(session, 'error', '缺少编排操作接口');
            return Promise.resolve({ ok: false, code: 'missing_orchestration_action_api' });
        }
        session.saving = true;
        setStatus(session, 'saving', '处理中');
        return api[method]({
            projectId: session.viewModel.projectId,
            taskId: payload && payload.taskId,
            body: payload && payload.body,
            fetcher: session.options && session.options.fetcher,
        }).then(function (result) {
            session.saving = false;
            return applyActionResult(session, result, successMessage);
        }).catch(function (err) {
            session.saving = false;
            setStatus(session, 'error', err && err.message ? err.message : '操作失败');
            return { ok: false, error: err };
        });
    }

    function pauseProject(session) {
        if (!session || !session.viewModel.canPause) {
            setStatus(session, 'error', '当前状态不可暂停');
            return Promise.resolve({ ok: false, code: 'orchestration_not_pausable' });
        }
        return callApiAction(session, 'pauseProject', { body: { reason: 'manual_pause' } }, '已暂停');
    }

    function resumeProject(session) {
        if (!session || !session.viewModel.canResume) {
            setStatus(session, 'error', '当前状态不可恢复');
            return Promise.resolve({ ok: false, code: 'orchestration_not_resumable' });
        }
        return callApiAction(session, 'resumeProject', { body: {} }, '已恢复');
    }

    function requestSkip(session, taskId) {
        return callApiAction(session, 'requestTaskSkip', {
            taskId: taskId,
            body: { reason: 'requested_from_orchestration_modal' },
        }, '已请求跳过');
    }

    function decideSkip(session, taskId, decision) {
        return callApiAction(session, 'decideTaskSkip', {
            taskId: taskId,
            body: { decision: decision },
        }, decision === 'approve' ? '已批准跳过' : '已拒绝跳过');
    }

    function close() {
        if (!activeSession) return;
        var session = activeSession;
        activeSession = null;
        if (session.keydownHandler && session.document && session.document.removeEventListener) {
            session.document.removeEventListener('keydown', session.keydownHandler);
        }
        if (session.overlay && session.overlay.remove) session.overlay.remove();
        if (session.previousFocus && session.previousFocus.focus) {
            try { session.previousFocus.focus(); } catch (err) {}
        }
        if (typeof session.onClose === 'function') session.onClose();
    }

    function open(project, options) {
        var doc = (options && options.document) || root.document;
        if (!doc || !doc.body || !doc.createElement) {
            throw new Error('Project orchestration requires a document');
        }
        close();
        var viewModel = buildViewModel(project);
        var session = {
            document: doc,
            overlay: null,
            modal: null,
            canvas: null,
            statusEl: null,
            viewModel: viewModel,
            project: cloneProject(project),
            options: options || {},
            keydownHandler: null,
            previousFocus: doc.activeElement,
            onClose: options && options.onClose,
            fitScale: FIT_SCALE,
            status: 'idle',
            statusMessage: '',
            draggingTaskId: null,
            saving: false,
        };
        var rendered = renderModal(doc, viewModel, options, session);
        var keydownHandler = function (event) {
            if (event && event.key === 'Escape') close();
        };
        if (doc.addEventListener) doc.addEventListener('keydown', keydownHandler);
        rendered.overlay.addEventListener('click', function (event) {
            if (event && event.target === rendered.overlay) close();
        });
        doc.body.appendChild(rendered.overlay);
        session.overlay = rendered.overlay;
        session.modal = rendered.modal;
        session.canvas = rendered.canvas;
        session.statusEl = rendered.statusEl;
        session.keydownHandler = keydownHandler;
        activeSession = session;
        return activeSession;
    }

    function reopen(project, options) {
        close();
        return open(project, options);
    }

    function fitCanvas() {
        return applyFitScale(activeSession);
    }

    function current() {
        return activeSession;
    }

    return {
        buildViewModel: buildViewModel,
        open: open,
        close: close,
        reopen: reopen,
        fitCanvas: fitCanvas,
        current: current,
        moveTaskToStage: function (taskId, targetStage) { return moveTaskToStage(activeSession, taskId, targetStage); },
        insertTaskAfterStage: function (taskId, afterStage) { return insertTaskAfterStage(activeSession, taskId, afterStage); },
        stageFromCanvasDrop: function (event) { return stageFromCanvasDrop(activeSession, event); },
        addTask: function () { return addTask(activeSession); },
        pauseProject: function () { return pauseProject(activeSession); },
        resumeProject: function () { return resumeProject(activeSession); },
        requestSkip: function (taskId) { return requestSkip(activeSession, taskId); },
        decideSkip: function (taskId, decision) { return decideSkip(activeSession, taskId, decision); },
    };
});
