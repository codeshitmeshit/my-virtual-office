// SMS Panel — threaded inbox with per-contact takeover
(function() {
    const _t = (key) => typeof i18n !== 'undefined' ? i18n.t(key) : key;

    const panel = document.getElementById('sms-panel');
    const toggle = document.getElementById('sms-toggle');
    const closeBtn = document.getElementById('sms-close');
    const moveBtn = document.getElementById('sms-move');
    const header = panel ? panel.querySelector('.sms-header') : null;
    const resizeHandles = panel ? panel.querySelectorAll('.sms-resize-handle') : [];
    const messagesDiv = document.getElementById('sms-messages');
    const threadsDiv = document.getElementById('sms-threads');
    const countBadge = document.getElementById('sms-count');
    const ownerBadge = document.getElementById('sms-owner-badge');
    const recipientSelect = document.getElementById('sms-recipient');
    const phoneManual = document.getElementById('sms-phone-manual');
    const toggleManual = document.getElementById('sms-toggle-manual');
    const openThreadBtn = document.getElementById('sms-open-thread');
    const inputBox = document.getElementById('sms-input');
    const sendBtn = document.getElementById('sms-send');
    const modeCheck = document.getElementById('sms-mode-check');
    const modeLabel = document.getElementById('sms-mode-label');
    const backBtn = document.getElementById('sms-back-to-inbox');
    const threadTitle = document.getElementById('sms-thread-title');
    const threadSubtitle = document.getElementById('sms-thread-subtitle');
    const emptyState = document.getElementById('sms-empty-state');
    const mobileQuery = window.matchMedia('(max-width: 900px)');
    const ACK_STORAGE_KEY = 'vo-sms-acknowledged-threads';

    let acknowledgedThreads = loadAcknowledgedThreads();

    if (!panel || !toggle) return;

    let isOpen = false;
    let manualMode = false;
    let pollTimer = null;
    let selectedPhone = '';
    let threadMap = new Map();
    let contactsMap = {};
    let ownerAgent = null;
    let moveMode = false;
    let dragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragOriginLeft = 0;
    let dragOriginTop = 0;
    let resizeState = null;
    let snapZoneLeft = null;
    let snapZoneRight = null;

    (async function checkSmsStatus() {
        try {
            const res = await fetch('/sms-status');
            const data = await res.json();
            if (!data.enabled) {
                toggle.style.display = 'none';
                return;
            }
            ownerAgent = data.ownerAgent || null;
            renderOwnerBadge();
            startPolling();
        } catch (e) {
            toggle.style.display = 'none';
        }
    })();

    toggle.addEventListener('click', () => {
        isOpen = !isOpen;
        panel.classList.toggle('open', isOpen);
        if (isOpen) {
            updateWindowLayoutState();
            setPanelView('list');
            loadPanel();
        } else {
            resetWindowState();
            setPanelView('list');
        }
    });

    closeBtn.addEventListener('click', () => {
        isOpen = false;
        panel.classList.remove('open');
        resetWindowState();
        setPanelView('list');
    });

    if (backBtn) {
        backBtn.addEventListener('click', () => {
            setPanelView('list');
            renderInboxPlaceholder();
        });
    }

    toggleManual.addEventListener('click', () => {
        manualMode = !manualMode;
        recipientSelect.style.display = manualMode ? 'none' : 'block';
        phoneManual.style.display = manualMode ? 'block' : 'none';
        toggleManual.textContent = manualMode ? '📋' : '✏️';
        toggleManual.title = manualMode ? 'Select from contacts' : 'Type number manually';
        if (manualMode) phoneManual.focus();
    });

    openThreadBtn.addEventListener('click', openSelectedThread);
    recipientSelect.addEventListener('change', () => {
        if (recipientSelect.value) {
            selectedPhone = normalizePhone(recipientSelect.value);
            renderThreadList();
        }
    });
    phoneManual.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            openSelectedThread();
        }
    });

    modeCheck.addEventListener('change', async () => {
        if (!selectedPhone) {
            modeCheck.checked = false;
            return;
        }
        const mode = modeCheck.checked ? 'user' : 'agent';
        applyMode(mode);
        try {
            const resp = await fetch('/sms-thread-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: selectedPhone, active: mode })
            });
            const result = await resp.json();
            if (!result.ok) throw new Error(result.error || 'Failed to save mode');
            const existing = threadMap.get(selectedPhone);
            if (existing) {
                existing.activeMode = mode;
                threadMap.set(selectedPhone, existing);
                renderThreadList();
            }
            updateComposerState();
        } catch (e) {
            alert(_t('failed_update_thread_mode') + ': ' + e.message);
            const revertMode = mode === 'user' ? 'agent' : 'user';
            applyMode(revertMode);
        }
    });

    sendBtn.addEventListener('click', sendSms);
    inputBox.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendSms();
        }
    });

    if (mobileQuery.addEventListener) {
        mobileQuery.addEventListener('change', syncResponsiveState);
    } else if (mobileQuery.addListener) {
        mobileQuery.addListener(syncResponsiveState);
    }
    syncResponsiveState();
    updateWindowLayoutState();

    if (moveBtn) {
        moveBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (isMobileLayout()) return;
            if (moveMode) exitMoveMode({ dock: panel.classList.contains('floating') });
            else enterMoveMode();
        });
    }

    if (header) {
        header.addEventListener('mousedown', startDrag);
    }

    resizeHandles.forEach((handle) => {
        handle.addEventListener('mousedown', startResize);
    });

    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);
    window.addEventListener('resize', onViewportChange);
    const sidebarEdge = document.getElementById('sidebar-edge');
    if (sidebarEdge) sidebarEdge.addEventListener('click', () => setTimeout(onViewportChange, 350));

    async function loadPanel() {
        await Promise.all([loadStatus(), loadContacts(), loadThreads()]);
        if (isMobileLayout()) {
            setPanelView('list');
            renderInboxPlaceholder();
        } else if (selectedPhone) {
            await loadThread(selectedPhone);
        } else if (threadMap.size > 0) {
            await loadThread(threadMap.keys().next().value);
        } else {
            renderEmptyConversation();
        }
    }

    async function loadStatus() {
        try {
            const res = await fetch('/sms-status');
            const data = await res.json();
            ownerAgent = data.ownerAgent || null;
            renderOwnerBadge();
        } catch (e) {
            console.error('SMS status fetch error:', e);
        }
    }

    function renderOwnerBadge() {
        if (!ownerBadge) return;
        if (ownerAgent && ownerAgent.id) {
            const emoji = ownerAgent.emoji || '🤖';
            const name = ownerAgent.name || ownerAgent.id;
            ownerBadge.textContent = `${emoji} ${_t('owner_label')}: ${name}`;
        } else {
            ownerBadge.textContent = _t('owner_not_assigned');
        }
    }

    async function loadContacts() {
        const currentValue = manualMode ? '' : recipientSelect.value;
        try {
            const resp = await fetch('/sms-contacts');
            const data = await resp.json();
            if (!data.ok) return;
            contactsMap = data.contacts || {};
            recipientSelect.innerHTML = `<option value="">${_t('select_contact')}</option>`;
            Object.entries(contactsMap)
                .sort((a, b) => (a[1]?.name || a[0]).localeCompare(b[1]?.name || b[0]))
                .forEach(([phone, info]) => {
                    const opt = document.createElement('option');
                    opt.value = phone;
                    opt.dataset.name = info.name || '';
                    opt.textContent = `${info.name || 'Unknown'} — ${formatPhone(phone)}`;
                    recipientSelect.appendChild(opt);
                });
            if (selectedPhone && !manualMode) recipientSelect.value = selectedPhone;
            else if (currentValue) recipientSelect.value = currentValue;
        } catch (e) {
            console.error('Contacts fetch error:', e);
        }
    }

    async function loadThreads() {
        try {
            const resp = await fetch('/sms-threads?limit=250');
            const data = await resp.json();
            if (!data.ok) return;
            ownerAgent = data.ownerAgent || ownerAgent;
            renderOwnerBadge();
            threadMap = new Map((data.threads || []).map(thread => [thread.phone, thread]));
            renderThreadList();
            if (selectedPhone && !threadMap.has(selectedPhone)) {
                selectedPhone = '';
            }
        } catch (e) {
            console.error('SMS threads fetch error:', e);
        }
    }

    function renderThreadList() {
        threadsDiv.innerHTML = '';
        const threads = Array.from(threadMap.values()).sort(compareThreads);
        const waitingCount = threads.filter(isThreadWaiting).length;

        countBadge.textContent = String(threadMap.size);
        countBadge.classList.toggle('attention', waitingCount > 0);
        countBadge.title = waitingCount
            ? `${waitingCount} ${_t('threads_waiting_latest_reply')}`
            : `${threadMap.size} ${_t('thread_count_label')}`;
        updateToggleAttention(waitingCount);

        if (threadMap.size === 0) {
            const empty = document.createElement('div');
            empty.className = 'sms-empty-state';
            empty.textContent = _t('no_sms_threads');
            threadsDiv.appendChild(empty);
            return;
        }

        for (const thread of threads) {
            const needsAttention = isThreadWaiting(thread);
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'sms-thread-item'
                + (thread.phone === selectedPhone ? ' active' : '')
                + (needsAttention ? ' needs-attention' : '');
            item.innerHTML = `
                <div class="sms-thread-top">
                    <div class="sms-thread-name-wrap">
                        ${needsAttention ? '<span class="sms-thread-alert-dot" aria-hidden="true"></span>' : ''}
                        <div class="sms-thread-name">${escapeHtml(thread.displayName || thread.name || thread.phone)}</div>
                    </div>
                    <div class="sms-thread-time">${escapeHtml(formatThreadTime(thread.lastTimestamp))}</div>
                </div>
                <div class="sms-thread-phone">${escapeHtml(formatPhone(thread.phone))}</div>
                <div class="sms-thread-preview">${escapeHtml(thread.lastMessage || _t('no_messages_in_thread'))}</div>
                <div class="sms-thread-badges">
                    ${needsAttention ? `<span class="sms-thread-badge latest">${_t('latest_reply')}</span>` : ''}
                    <span class="sms-thread-badge ${thread.activeMode === 'user' ? 'user' : 'agent'}">${thread.activeMode === 'user' ? _t('user_active') : _t('agent_active')}</span>
                    <span class="sms-thread-badge">${thread.messageCount || 0} ${_t('msg_count')}</span>
                </div>
            `;
            item.addEventListener('click', () => selectThread(thread.phone));
            threadsDiv.appendChild(item);
        }
    }

    async function selectThread(phone) {
        phone = normalizePhone(phone);
        if (!phone) return;
        selectedPhone = phone;
        if (!manualMode) recipientSelect.value = phone;
        markThreadSeen(threadMap.get(phone));
        renderThreadList();
        if (isMobileLayout()) setPanelView('thread');
        await loadThread(phone);
        scrollToBottom(true);
    }

    async function openSelectedThread() {
        const recipient = getRecipient();
        if (!recipient.phone) return;
        const phone = normalizePhone(recipient.phone);
        if (!phone) return;

        if (manualMode) {
            try {
                await fetch('/sms-thread-mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone, active: 'user' })
                });
            } catch (e) {
                console.error('Could not default new thread to user mode:', e);
            }
        }

        if (!threadMap.has(phone)) {
            threadMap.set(phone, {
                phone,
                name: recipient.name || contactsMap[phone]?.name || 'Unknown',
                displayName: recipient.name || contactsMap[phone]?.name || phone,
                lastMessage: '',
                lastTimestamp: '',
                lastType: '',
                messageCount: 0,
                activeMode: manualMode ? 'user' : 'agent'
            });
            renderThreadList();
        }
        await selectThread(phone);
    }

    async function loadThread(phone) {
        try {
            const resp = await fetch('/sms-thread?phone=' + encodeURIComponent(phone) + '&limit=250');
            const data = await resp.json();
            if (!data.ok) {
                renderEmptyConversation(data.error || 'Failed to load thread');
                return;
            }
            selectedPhone = data.thread.phone;
            const existing = threadMap.get(selectedPhone) || {};
            const mergedThread = Object.assign({}, existing, data.thread, {
                displayName: data.thread.name || existing.name || data.thread.phone
            });
            threadMap.set(selectedPhone, mergedThread);
            markThreadSeen(mergedThread);
            renderThreadList();
            renderConversation(mergedThread, data.messages || []);
        } catch (e) {
            console.error('SMS thread fetch error:', e);
            renderEmptyConversation('Failed to load thread.');
        }
    }

    function renderConversation(thread, messages) {
        if (!thread) {
            renderEmptyConversation();
            return;
        }
        messagesDiv.style.display = 'flex';
        threadTitle.textContent = thread.name && thread.name !== 'Unknown' ? thread.name : formatPhone(thread.phone);
        threadSubtitle.textContent = formatPhone(thread.phone);
        applyMode(thread.activeMode || 'agent');

        messagesDiv.innerHTML = '';
        emptyState.style.display = messages.length ? 'none' : 'block';
        emptyState.textContent = messages.length ? '' : _t('no_messages_yet');
        let lastDate = '';
        messages.forEach(msg => {
            const msgDate = formatDate(msg.timestamp);
            if (msgDate !== lastDate) {
                lastDate = msgDate;
                const sep = document.createElement('div');
                sep.style.cssText = 'text-align:center;font-size:10px;color:#888;padding:4px 0;';
                sep.textContent = `— ${msgDate} —`;
                messagesDiv.appendChild(sep);
            }
            appendMessage(msg, thread);
        });
        scrollToBottom(true);
    }

    function renderInboxPlaceholder() {
        messagesDiv.innerHTML = '';
        messagesDiv.style.display = 'none';
        emptyState.style.display = 'block';
        emptyState.textContent = _t('select_thread_to_open');
        threadTitle.textContent = _t('sms_inbox');
        threadSubtitle.textContent = getInboxSummary();
    }

    function renderEmptyConversation(message) {
        messagesDiv.innerHTML = '';
        messagesDiv.style.display = 'none';
        emptyState.style.display = 'block';
        emptyState.textContent = message || _t('select_contact_thread');
        threadTitle.textContent = _t('select_a_contact');
        threadSubtitle.textContent = _t('choose_thread');
        selectedPhone = '';
        applyMode('agent');
        updateComposerState();
        renderThreadList();
    }

    function applyMode(mode) {
        const isUser = mode === 'user';
        modeCheck.checked = isUser;
        modeLabel.textContent = isUser ? _t('user_mode') : _t('agent_mode');
        modeLabel.style.color = isUser ? '#ffd700' : '#fff';
        updateComposerState();
    }

    function updateComposerState() {
        if (!selectedPhone) {
            inputBox.disabled = true;
            sendBtn.disabled = true;
            inputBox.placeholder = _t('open_thread_first');
            return;
        }
        const thread = threadMap.get(selectedPhone);
        const isUser = thread && thread.activeMode === 'user';
        inputBox.disabled = !isUser;
        sendBtn.disabled = !isUser;
        inputBox.placeholder = isUser
            ? _t('type_message')
            : _t('agent_owns_thread');
    }

    function appendMessage(msg, thread) {
        const div = document.createElement('div');
        const type = msg.type || 'inbound';
        const cls = type === 'blocked' ? 'blocked' : type === 'intervention' ? 'intervention' : type === 'outbound' ? 'outbound' : 'inbound';
        div.className = `sms-msg ${cls}`;

        let label = '';
        if (type === 'blocked') {
            label = `Blocked · ${formatPhone(msg.phone || thread.phone)}`;
        } else if (type === 'intervention') {
            label = `You · ${formatTime(msg.timestamp)}`;
        } else if (type === 'outbound') {
            const ownerName = ownerAgent?.name || 'Agent';
            label = `${ownerName} · ${formatTime(msg.timestamp)}`;
        } else {
            label = `${thread.name && thread.name !== 'Unknown' ? thread.name : formatPhone(thread.phone)} · ${formatTime(msg.timestamp)}`;
        }

        const body = escapeHtml(msg.body || '');
        const mediaHtml = renderMessageMedia(msg.media || msg.mediaUrls || msg.attachments || []);
        div.innerHTML = `<div class="sms-msg-meta">${escapeHtml(label)}</div><div class="sms-msg-body">${body}${mediaHtml}</div>`;
        messagesDiv.appendChild(div);
    }

    function normalizeMessageMedia(media) {
        if (!media) return [];
        if (!Array.isArray(media)) media = [media];
        return media.map((item, idx) => {
            if (typeof item === 'string') {
                return { url: item, proxyUrl: item, contentType: '', filename: `Media ${idx + 1}` };
            }
            if (!item || typeof item !== 'object') return null;
            const url = item.proxyUrl || item.url || item.mediaUrl || item.MediaUrl || item.href || '';
            if (!url) return null;
            return {
                url,
                originalUrl: item.url || item.mediaUrl || item.MediaUrl || item.href || url,
                contentType: item.contentType || item.mediaContentType || item.ContentType || item.type || '',
                filename: item.filename || item.name || `Media ${idx + 1}`
            };
        }).filter(Boolean);
    }

    function renderMessageMedia(media) {
        const items = normalizeMessageMedia(media);
        if (!items.length) return '';
        return `<div class="sms-media-list">${items.map(renderMediaItem).join('')}</div>`;
    }

    function renderMediaItem(item) {
        const url = item.url;
        const type = (item.contentType || '').toLowerCase();
        const label = escapeHtml(item.filename || item.contentType || 'Open media');
        const safeUrl = escapeHtml(url);
        const link = `<a class="sms-media-link" href="${safeUrl}" target="_blank" rel="noopener">${label}</a>`;
        if (type.startsWith('image/')) {
            return `<figure class="sms-media-item"><a href="${safeUrl}" target="_blank" rel="noopener"><img class="sms-media-image" src="${safeUrl}" alt="${label}" loading="lazy"></a><figcaption>${label}</figcaption></figure>`;
        }
        if (type.startsWith('video/')) {
            return `<figure class="sms-media-item"><video class="sms-media-video" src="${safeUrl}" controls preload="metadata"></video><figcaption>${link}</figcaption></figure>`;
        }
        if (type.startsWith('audio/')) {
            return `<figure class="sms-media-item"><audio class="sms-media-audio" src="${safeUrl}" controls preload="metadata"></audio><figcaption>${link}</figcaption></figure>`;
        }
        return `<div class="sms-media-file">📎 ${link}${type ? `<span>${escapeHtml(type)}</span>` : ''}</div>`;
    }

    async function sendSms() {
        if (!selectedPhone) {
            await openSelectedThread();
            if (!selectedPhone) return;
        }
        const body = inputBox.value.trim();
        const thread = threadMap.get(selectedPhone);
        if (!body || !thread || thread.activeMode !== 'user') return;

        sendBtn.disabled = true;
        sendBtn.textContent = '⏳';
        try {
            const resp = await fetch('/sms-send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    to: selectedPhone,
                    body,
                    name: thread.name || contactsMap[selectedPhone]?.name || '',
                    sender: 'user'
                })
            });
            const result = await resp.json();
            if (!result.ok) throw new Error(result.error || _t('unknown_sms_error'));
            inputBox.value = '';
            await Promise.all([loadContacts(), loadThreads()]);
            await loadThread(selectedPhone);
        } catch (e) {
            alert(_t('sms_failed') + ': ' + e.message);
        } finally {
            sendBtn.textContent = '▶';
            updateComposerState();
        }
    }

    function isMobileLayout() {
        return !!mobileQuery.matches;
    }

    function setPanelView(view) {
        if (!isMobileLayout()) {
            panel.classList.remove('mobile-list-view', 'mobile-thread-view');
            return;
        }
        const nextView = view === 'thread' ? 'thread' : 'list';
        panel.classList.toggle('mobile-list-view', nextView === 'list');
        panel.classList.toggle('mobile-thread-view', nextView === 'thread');
    }

    function syncResponsiveState() {
        if (isMobileLayout()) {
            if (!panel.classList.contains('mobile-thread-view')) {
                setPanelView('list');
            }
            resetWindowState();
        } else {
            panel.classList.remove('mobile-list-view', 'mobile-thread-view');
        }
        updateWindowLayoutState();
    }

    function onViewportChange() {
        updateWindowLayoutState();
        if (panel.classList.contains('snap-left') || panel.classList.contains('snap-right')) {
            updateSnapPosition();
        } else if (panel.classList.contains('floating')) {
            clampFloatingPosition();
        }
    }

    function getToolbarClearance() {
        if (isMobileLayout()) return 0;
        const toolbar = document.querySelector('.toolbar');
        if (!toolbar) return 72;
        const rect = toolbar.getBoundingClientRect();
        return Math.max(56, Math.round(rect.height + 8));
    }

    function getTopClearance() {
        if (isMobileLayout()) return 0;
        const wrapper = document.querySelector('.game-wrapper');
        if (!wrapper) return 8;
        const rect = wrapper.getBoundingClientRect();
        return Math.max(0, Math.round(rect.top));
    }

    function getSidebarWidth() {
        const sidebar = document.querySelector('.sidebar');
        const edge = document.querySelector('.sidebar-edge');
        if (!sidebar || sidebar.classList.contains('collapsed')) return edge ? edge.offsetWidth : 20;
        return sidebar.offsetWidth + (edge ? edge.offsetWidth : 20);
    }

    function getBounds() {
        const top = getTopClearance();
        const bottom = Math.max(top + 40, window.innerHeight - getToolbarClearance());
        const left = 0;
        const right = Math.max(left + 320, window.innerWidth - getSidebarWidth());
        return { top, right, bottom, left, width: right - left, height: bottom - top };
    }

    function updateWindowLayoutState() {
        panel.style.setProperty('--sms-toolbar-clearance', `${getToolbarClearance()}px`);
        panel.style.setProperty('--sms-top-clearance', `${getTopClearance()}px`);
    }

    function createSnapZones() {
        if (snapZoneLeft || isMobileLayout()) return;
        snapZoneLeft = document.createElement('div');
        snapZoneLeft.className = 'sms-snap-zone left';
        snapZoneRight = document.createElement('div');
        snapZoneRight.className = 'sms-snap-zone right';
        document.body.appendChild(snapZoneLeft);
        document.body.appendChild(snapZoneRight);
    }

    function removeSnapZones() {
        if (snapZoneLeft) {
            snapZoneLeft.remove();
            snapZoneLeft = null;
        }
        if (snapZoneRight) {
            snapZoneRight.remove();
            snapZoneRight = null;
        }
    }

    function resetWindowState() {
        moveMode = false;
        dragging = false;
        resizeState = null;
        removeSnapZones();
        panel.classList.remove('floating', 'snap-left', 'snap-right', 'dragging', 'move-active');
        panel.style.removeProperty('left');
        panel.style.removeProperty('top');
        panel.style.removeProperty('right');
        panel.style.removeProperty('bottom');
        panel.style.removeProperty('width');
        panel.style.removeProperty('height');
        if (moveBtn) moveBtn.classList.remove('active');
        document.body.style.userSelect = '';
        document.body.style.webkitUserSelect = '';
        document.body.style.cursor = '';
    }

    function enterMoveMode() {
        if (isMobileLayout()) return;
        moveMode = true;
        if (moveBtn) moveBtn.classList.add('active');
        panel.classList.add('move-active');
        const rect = panel.getBoundingClientRect();
        panel.classList.remove('snap-left', 'snap-right');
        panel.classList.add('floating');
        panel.style.left = `${rect.left}px`;
        panel.style.top = `${rect.top}px`;
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
        panel.style.width = `${rect.width}px`;
        panel.style.height = `${rect.height}px`;
        clampFloatingPosition();
    }

    function exitMoveMode({ dock = false } = {}) {
        moveMode = false;
        dragging = false;
        if (moveBtn) moveBtn.classList.remove('active');
        panel.classList.remove('dragging', 'move-active');
        removeSnapZones();
        if (dock && !panel.classList.contains('snap-left') && !panel.classList.contains('snap-right')) {
            panel.classList.remove('floating');
            panel.style.removeProperty('left');
            panel.style.removeProperty('top');
            panel.style.removeProperty('right');
            panel.style.removeProperty('bottom');
        }
    }

    function updateSnapPosition() {
        const bounds = getBounds();
        const maxWidth = Math.max(360, bounds.width - 12);
        const snappedWidth = clamp(parseFloat(panel.style.width) || panel.offsetWidth || 720, 360, maxWidth);
        panel.style.width = `${snappedWidth}px`;
        panel.style.height = `${Math.max(280, bounds.height)}px`;
        panel.style.top = `${bounds.top}px`;
        panel.style.bottom = 'auto';
        if (panel.classList.contains('snap-left')) {
            panel.style.left = '0px';
            panel.style.right = 'auto';
        } else if (panel.classList.contains('snap-right')) {
            panel.style.left = 'auto';
            panel.style.right = `${getSidebarWidth()}px`;
        }
    }

    function snapTo(side) {
        panel.classList.remove('floating', 'dragging', 'move-active');
        panel.classList.remove(side === 'left' ? 'snap-right' : 'snap-left');
        panel.classList.add(side === 'left' ? 'snap-left' : 'snap-right');
        updateSnapPosition();
        moveMode = false;
        dragging = false;
        if (moveBtn) moveBtn.classList.remove('active');
        removeSnapZones();
    }

    function clampFloatingPosition() {
        if (!panel.classList.contains('floating') || isMobileLayout()) return;
        const bounds = getBounds();
        const width = Math.min(parseFloat(panel.style.width) || panel.offsetWidth || 720, Math.max(360, bounds.width));
        const height = Math.min(parseFloat(panel.style.height) || panel.offsetHeight || 560, Math.max(280, bounds.height));
        panel.style.width = `${width}px`;
        panel.style.height = `${height}px`;
        const left = clamp(parseFloat(panel.style.left) || bounds.left, bounds.left, Math.max(bounds.left, bounds.right - width));
        const top = clamp(parseFloat(panel.style.top) || bounds.top, bounds.top, Math.max(bounds.top, bounds.bottom - height));
        panel.style.left = `${left}px`;
        panel.style.top = `${top}px`;
    }

    function startDrag(e) {
        if (!moveMode || isMobileLayout() || resizeState) return;
        if (e.target.closest('button, select, textarea, input, label')) return;
        e.preventDefault();
        dragging = true;
        panel.classList.add('dragging');
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        const rect = panel.getBoundingClientRect();
        dragOriginLeft = rect.left;
        dragOriginTop = rect.top;
        createSnapZones();
    }

    function getHandleDirection(handle) {
        if (handle.classList.contains('top-left')) return 'topLeft';
        if (handle.classList.contains('top-right')) return 'topRight';
        if (handle.classList.contains('bottom-left')) return 'bottomLeft';
        if (handle.classList.contains('bottom-right')) return 'bottomRight';
        if (handle.classList.contains('top')) return 'top';
        if (handle.classList.contains('bottom')) return 'bottom';
        if (handle.classList.contains('left')) return 'left';
        if (handle.classList.contains('right')) return 'right';
        return '';
    }

    function isRightAnchored() {
        return !panel.classList.contains('floating') && !panel.classList.contains('snap-left') && !isMobileLayout();
    }

    function startResize(e) {
        if (isMobileLayout()) return;
        const handle = e.currentTarget;
        const dir = getHandleDirection(handle);
        if (!dir) return;
        e.preventDefault();
        e.stopPropagation();
        const rect = panel.getBoundingClientRect();
        resizeState = {
            handle,
            dir,
            rightAnchored: isRightAnchored(),
            startX: e.clientX,
            startY: e.clientY,
            startW: rect.width,
            startH: rect.height,
            startRect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom }
        };
        panel.style.transition = 'none';
        handle.classList.add('dragging');
        document.body.style.userSelect = 'none';
        document.body.style.webkitUserSelect = 'none';
        document.body.style.cursor = getCursorForDirection(dir);
    }

    function onPointerMove(e) {
        if (resizeState) {
            applyResize(e.clientX - resizeState.startX, e.clientY - resizeState.startY);
            return;
        }
        if (!dragging) return;
        const bounds = getBounds();
        const width = parseFloat(panel.style.width) || panel.offsetWidth || 720;
        const height = parseFloat(panel.style.height) || panel.offsetHeight || 560;
        const left = clamp(dragOriginLeft + (e.clientX - dragStartX), bounds.left, Math.max(bounds.left, bounds.right - width));
        const top = clamp(dragOriginTop + (e.clientY - dragStartY), bounds.top, Math.max(bounds.top, bounds.bottom - height));
        panel.style.left = `${left}px`;
        panel.style.top = `${top}px`;
        if (snapZoneLeft) snapZoneLeft.classList.toggle('active', e.clientX < 80);
        if (snapZoneRight) {
            snapZoneRight.style.right = `${getSidebarWidth()}px`;
            snapZoneRight.classList.toggle('active', e.clientX > bounds.right - 80);
        }
    }

    function onPointerUp(e) {
        if (resizeState) {
            endResize();
            return;
        }
        if (!dragging) return;
        dragging = false;
        panel.classList.remove('dragging');
        const bounds = getBounds();
        if (e.clientX < 80) snapTo('left');
        else if (e.clientX > bounds.right - 80) snapTo('right');
        else {
            removeSnapZones();
            clampFloatingPosition();
        }
    }

    function applyResize(dx, dy) {
        if (!resizeState) return;
        const bounds = getBounds();
        const dir = resizeState.dir;
        const movesLeft = dir === 'left' || dir === 'topLeft' || dir === 'bottomLeft';
        const movesRight = dir === 'right' || dir === 'topRight' || dir === 'bottomRight';
        const movesTop = dir === 'top' || dir === 'topLeft' || dir === 'topRight';
        const movesBottom = dir === 'bottom' || dir === 'bottomLeft' || dir === 'bottomRight';
        const maxWidthFromLeft = Math.max(360, resizeState.startRect.right - bounds.left);
        const maxWidthFromRight = Math.max(360, bounds.right - resizeState.startRect.left);
        const maxHeight = Math.max(280, bounds.height);

        if (movesRight) {
            const nextWidth = clamp(resizeState.startW + dx, 360, resizeState.rightAnchored ? maxWidthFromLeft : maxWidthFromRight);
            panel.style.width = `${nextWidth}px`;
        }

        if (movesLeft) {
            const nextWidth = clamp(resizeState.startW - dx, 360, resizeState.rightAnchored ? maxWidthFromLeft : maxWidthFromRight);
            panel.style.width = `${nextWidth}px`;
            if (!resizeState.rightAnchored) {
                const nextLeft = clamp(resizeState.startRect.right - nextWidth, bounds.left, bounds.right - nextWidth);
                panel.style.left = `${nextLeft}px`;
            }
        }

        if (movesTop) {
            const nextHeight = clamp(resizeState.startH - dy, 280, maxHeight);
            panel.style.height = `${nextHeight}px`;
            if (panel.classList.contains('floating') || panel.classList.contains('snap-left') || panel.classList.contains('snap-right')) {
                const nextTop = clamp(resizeState.startRect.bottom - nextHeight, bounds.top, bounds.bottom - nextHeight);
                panel.style.top = `${nextTop}px`;
            }
        }

        if (movesBottom && (panel.classList.contains('floating') || panel.classList.contains('snap-left') || panel.classList.contains('snap-right'))) {
            const nextHeight = clamp(resizeState.startH + dy, 280, Math.max(280, bounds.bottom - resizeState.startRect.top));
            panel.style.height = `${nextHeight}px`;
        }
    }

    function endResize() {
        if (!resizeState) return;
        resizeState.handle.classList.remove('dragging');
        resizeState = null;
        panel.style.transition = '';
        document.body.style.userSelect = '';
        document.body.style.webkitUserSelect = '';
        document.body.style.cursor = '';
        if (panel.classList.contains('snap-left') || panel.classList.contains('snap-right')) updateSnapPosition();
        else if (panel.classList.contains('floating')) clampFloatingPosition();
    }

    function getCursorForDirection(dir) {
        return {
            left: 'ew-resize',
            right: 'ew-resize',
            top: 'ns-resize',
            bottom: 'ns-resize',
            topLeft: 'nw-resize',
            topRight: 'ne-resize',
            bottomLeft: 'sw-resize',
            bottomRight: 'se-resize'
        }[dir] || 'default';
    }

    function isThreadWaiting(thread) {
        if ((thread?.lastType || '') !== 'inbound') return false;
        const phone = normalizePhone(thread?.phone || '');
        if (!phone) return false;
        return threadTimestampValue(thread?.lastTimestamp) > threadTimestampValue(acknowledgedThreads[phone]);
    }

    function markThreadSeen(thread) {
        const phone = normalizePhone(thread?.phone || '');
        if (!phone || (thread?.lastType || '') !== 'inbound') return;
        const lastTimestamp = thread?.lastTimestamp || '';
        if (threadTimestampValue(lastTimestamp) <= threadTimestampValue(acknowledgedThreads[phone])) return;
        acknowledgedThreads[phone] = lastTimestamp;
        persistAcknowledgedThreads();
    }

    function loadAcknowledgedThreads() {
        try {
            const raw = window.localStorage.getItem(ACK_STORAGE_KEY);
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch {
            return {};
        }
    }

    function persistAcknowledgedThreads() {
        try {
            window.localStorage.setItem(ACK_STORAGE_KEY, JSON.stringify(acknowledgedThreads));
        } catch {
            // Ignore storage failures, alerts can still work for the current session.
        }
    }

    function threadTimestampValue(ts) {
        const parsed = Date.parse(ts || '');
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function compareThreads(a, b) {
        const timeDiff = threadTimestampValue(b?.lastTimestamp) - threadTimestampValue(a?.lastTimestamp);
        if (timeDiff) return timeDiff;
        return Number(isThreadWaiting(b)) - Number(isThreadWaiting(a));
    }

    function updateToggleAttention(waitingCount) {
        toggle.classList.toggle('sms-toggle-alert', waitingCount > 0);
        if (waitingCount > 0) {
            toggle.dataset.alertCount = waitingCount > 9 ? '9+' : String(waitingCount);
            toggle.title = `${_t('sms_phone_panel')} (${waitingCount} ${_t('threads_with_latest_reply')})`;
        } else {
            delete toggle.dataset.alertCount;
            toggle.title = _t('sms_phone_panel');
        }
    }

    function getInboxSummary() {
        const threads = Array.from(threadMap.values());
        const waitingCount = threads.filter(isThreadWaiting).length;
        if (!threads.length) return _t('no_active_threads');
        if (!waitingCount) return `${threads.length} ${_t('threads_synced')}.`;
        return `${waitingCount} ${_t('threads_with_latest_reply')}.`;
    }

    function getRecipient() {
        if (manualMode) {
            return { phone: phoneManual.value.trim(), name: '' };
        }
        const opt = recipientSelect.options[recipientSelect.selectedIndex];
        return { phone: opt?.value || '', name: opt?.dataset?.name || '' };
    }

    function startPolling() {
        if (pollTimer) return;
        const tick = async () => {
            await loadThreads();
            if (isOpen) {
                await loadContacts();
                if (selectedPhone) await loadThread(selectedPhone);
            }
        };
        tick();
        pollTimer = setInterval(tick, 5000);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function scrollToBottom(force = false) {
        if (!messagesDiv) return;
        const run = () => {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        };
        run();
        window.requestAnimationFrame(run);
        window.setTimeout(run, force ? 120 : 40);
    }

    function normalizePhone(phone) {
        if (!phone) return '';
        phone = String(phone).trim().replace(/[\s\-()]+/g, '');
        if (phone.startsWith('00')) phone = '+' + phone.slice(2);
        if (phone.startsWith('+')) return phone;
        if (/^\d+$/.test(phone)) {
            if (phone.length === 10) return '+1' + phone;
            if (phone.length === 11 && phone.startsWith('1')) return '+' + phone;
        }
        return phone;
    }

    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    function formatPhone(phone) {
        if (phone && phone.startsWith('+1') && phone.length === 12) {
            return `(${phone.slice(2, 5)}) ${phone.slice(5, 8)}-${phone.slice(8)}`;
        }
        return phone || '';
    }

    function formatTime(ts) {
        try {
            const d = new Date(ts);
            return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
        } catch {
            return ts || '';
        }
    }

    function formatThreadTime(ts) {
        if (!ts) return '';
        try {
            const d = new Date(ts);
            const now = new Date();
            if (d.toDateString() === now.toDateString()) {
                return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
            }
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } catch {
            return '';
        }
    }

    function formatDate(ts) {
        try {
            const d = new Date(ts);
            const today = new Date();
            if (d.toDateString() === today.toDateString()) return 'Today';
            const yesterday = new Date(today);
            yesterday.setDate(today.getDate() - 1);
            if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } catch {
            return '';
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }
})();
