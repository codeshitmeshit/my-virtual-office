(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(root);
    } else {
        root.ProjectOrchestrationTaskDialog = factory(root);
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    var activeDialog = null;

    function text(value) {
        return value == null ? '' : String(value);
    }

    function createEl(doc, tag, className, textValue) {
        var el = doc.createElement(tag);
        if (className) el.className = className;
        if (textValue != null) el.textContent = text(textValue);
        return el;
    }

    function option(doc, value, label) {
        var el = doc.createElement('option');
        el.value = text(value);
        el.textContent = text(label);
        return el;
    }

    function normalizeAgents(agents) {
        if (!Array.isArray(agents)) return [];
        return agents.map(function (agent) {
            if (!agent || typeof agent !== 'object') return null;
            var id = text(agent.id || agent.agentId || agent.name || agent.label).trim();
            if (!id) return null;
            return {
                id: id,
                label: text(agent.displayName || agent.name || agent.label || id).trim() || id,
            };
        }).filter(Boolean);
    }

    function close(result) {
        if (!activeDialog) return;
        var current = activeDialog;
        activeDialog = null;
        if (current.overlay && current.overlay.remove) current.overlay.remove();
        current.resolve(result || { ok: false, cancelled: true });
    }

    function submit(current) {
        if (!current) return;
        var title = text(current.titleInput && current.titleInput.value).trim();
        if (!title) {
            current.error.textContent = '请输入任务标题';
            current.titleInput.focus();
            return;
        }
        var assignee = text(current.assigneeSelect && current.assigneeSelect.value).trim();
        close({
            ok: true,
            task: {
                title: title,
                description: text(current.descriptionInput && current.descriptionInput.value).trim(),
                priority: text(current.prioritySelect && current.prioritySelect.value).trim() || 'medium',
                assignee: assignee || undefined,
                executorAgentId: assignee || undefined,
                executionStage: current.executionStage,
            },
        });
    }

    function open(options) {
        var opts = options || {};
        var doc = opts.document || root.document;
        if (!doc || !doc.body || !doc.createElement) {
            return Promise.resolve({ ok: false, code: 'missing_document' });
        }
        if (activeDialog) close({ ok: false, cancelled: true });

        return new Promise(function (resolve) {
            var executionStage = Math.max(1, Math.trunc(Number(opts.executionStage) || 1));
            var overlay = createEl(doc, 'div', 'project-orchestration-task-dialog-overlay');
            overlay.setAttribute('role', 'dialog');
            overlay.setAttribute('aria-modal', 'true');

            var modal = createEl(doc, 'section', 'project-orchestration-task-dialog');
            overlay.appendChild(modal);

            var header = createEl(doc, 'header', 'project-orchestration-task-dialog-header');
            header.appendChild(createEl(doc, 'h3', 'project-orchestration-task-dialog-title', '添加阶段任务'));
            header.appendChild(createEl(doc, 'p', 'project-orchestration-task-dialog-subtitle', '阶段 ' + executionStage + ' · 新任务'));
            modal.appendChild(header);

            var form = createEl(doc, 'div', 'project-orchestration-task-dialog-form');
            var titleLabel = createEl(doc, 'label', 'project-orchestration-task-dialog-field');
            titleLabel.appendChild(createEl(doc, 'span', '', '标题'));
            var titleInput = createEl(doc, 'input', 'project-orchestration-task-dialog-input');
            titleInput.type = 'text';
            titleInput.value = text(opts.defaultTitle || '');
            titleInput.placeholder = '输入任务标题';
            titleLabel.appendChild(titleInput);
            form.appendChild(titleLabel);

            var descriptionLabel = createEl(doc, 'label', 'project-orchestration-task-dialog-field');
            descriptionLabel.appendChild(createEl(doc, 'span', '', '描述'));
            var descriptionInput = createEl(doc, 'textarea', 'project-orchestration-task-dialog-textarea');
            descriptionInput.value = text(opts.defaultDescription || '');
            descriptionInput.placeholder = '补充目标、验收标准或依赖信息';
            descriptionLabel.appendChild(descriptionInput);
            form.appendChild(descriptionLabel);

            var row = createEl(doc, 'div', 'project-orchestration-task-dialog-row');
            var priorityLabel = createEl(doc, 'label', 'project-orchestration-task-dialog-field');
            priorityLabel.appendChild(createEl(doc, 'span', '', '优先级'));
            var prioritySelect = createEl(doc, 'select', 'project-orchestration-task-dialog-input');
            [['medium', 'MEDIUM'], ['high', 'HIGH'], ['critical', 'CRITICAL'], ['low', 'LOW']].forEach(function (item) {
                prioritySelect.appendChild(option(doc, item[0], item[1]));
            });
            prioritySelect.value = text(opts.defaultPriority || 'medium');
            priorityLabel.appendChild(prioritySelect);
            row.appendChild(priorityLabel);

            var assigneeLabel = createEl(doc, 'label', 'project-orchestration-task-dialog-field');
            assigneeLabel.appendChild(createEl(doc, 'span', '', '执行人'));
            var assigneeSelect = createEl(doc, 'select', 'project-orchestration-task-dialog-input');
            assigneeSelect.appendChild(option(doc, '', 'Unassigned'));
            normalizeAgents(opts.agents).forEach(function (agent) {
                assigneeSelect.appendChild(option(doc, agent.id, agent.label));
            });
            assigneeLabel.appendChild(assigneeSelect);
            row.appendChild(assigneeLabel);
            form.appendChild(row);

            var error = createEl(doc, 'p', 'project-orchestration-task-dialog-error');
            form.appendChild(error);
            modal.appendChild(form);

            var footer = createEl(doc, 'footer', 'project-orchestration-task-dialog-actions');
            var cancelBtn = createEl(doc, 'button', 'project-orchestration-task-dialog-button is-cancel', '取消');
            cancelBtn.type = 'button';
            cancelBtn.addEventListener('click', function () { close({ ok: false, cancelled: true }); });
            var submitBtn = createEl(doc, 'button', 'project-orchestration-task-dialog-button is-submit', '创建任务');
            submitBtn.type = 'button';
            footer.appendChild(cancelBtn);
            footer.appendChild(submitBtn);
            modal.appendChild(footer);

            activeDialog = {
                overlay: overlay,
                resolve: resolve,
                executionStage: executionStage,
                titleInput: titleInput,
                descriptionInput: descriptionInput,
                prioritySelect: prioritySelect,
                assigneeSelect: assigneeSelect,
                error: error,
            };

            submitBtn.addEventListener('click', function () { submit(activeDialog); });
            overlay.addEventListener('keydown', function (event) {
                if (event && event.key === 'Escape') close({ ok: false, cancelled: true });
                if (event && event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit(activeDialog);
            });
            doc.body.appendChild(overlay);
            titleInput.focus();
        });
    }

    return { open: open, close: close };
});
