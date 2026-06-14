// Feishu Panel — Feishu message sync for Virtual Office
// Floating, draggable, resizable, minimizable popup window
(() => {
  const feishuBtn   = document.getElementById('feishu-toggle');
  const feishuPanel = document.getElementById('feishu-panel');
  const feishuFeed  = document.getElementById('feishu-feed');
  const feishuClose = document.getElementById('feishu-close');
  const feishuMinimize = document.getElementById('feishu-minimize');
  const feishuDragHandle = document.getElementById('feishu-drag-handle');

  let feishuOpen = false;
  let isMinimized = false;
  let eventSource = null;
  let reconnectTimer = null;
  const renderedEvents = new Set();
  const FEISHU_RECONNECT_MS = 5000;

  // ─── Toggle ────────────────────────────────────────────────
  function toggleFeishuPanel() {
    if (feishuOpen) { closeFeishuPanel(); } else { openFeishuPanel(); }
  }

  function openFeishuPanel() {
    if (feishuOpen) return;
    snapToZone(2); // open at bottom-left (opposite of browser)
    feishuPanel.classList.add('open');
    if (feishuBtn) feishuBtn.classList.add('active');
    feishuOpen = true;
    if (isMinimized) {
      feishuPanel.classList.remove('minimized');
      isMinimized = false;
    }
    loadHistory();
    connectSSE();
  }

  function closeFeishuPanel() {
    feishuPanel.classList.remove('open', 'minimized');
    if (feishuBtn) feishuBtn.classList.remove('active');
    feishuOpen = false;
    isMinimized = false;
  }

  feishuBtn.addEventListener('click', toggleFeishuPanel);
  feishuClose.addEventListener('click', closeFeishuPanel);
  feishuMinimize.addEventListener('click', () => {
    if (isMinimized) {
      feishuPanel.classList.remove('minimized');
      isMinimized = false;
    } else {
      feishuPanel.classList.add('minimized');
      isMinimized = true;
    }
  });

  // ─── Snap to zone ──────────────────────────────────────────
  function snapToZone(zoneNum) {
    const sidebar = document.getElementById('sidebar');
    const sidebarWidth = sidebar ? sidebar.offsetWidth : 0;
    const toolbar = document.querySelector('.toolbar');
    const toolbarHeight = toolbar ? toolbar.offsetHeight : 0;
    const availWidth = window.innerWidth - sidebarWidth;
    const availHeight = window.innerHeight - toolbarHeight;
    const halfW = availWidth / 2;
    const halfH = availHeight / 2;

    let zone;
    if (zoneNum === 2) {
      zone = { left: 0, top: halfH, width: halfW, height: halfH };
    } else {
      zone = { left: halfW, top: halfH, width: halfW, height: halfH };
    }

    const panelW = 380;
    const panelH = 420;
    const left = zone.left + Math.max(10, (zone.width - panelW) / 2);
    const top = zone.top + Math.max(10, (zone.height - panelH) / 2);

    feishuPanel.style.left = left + 'px';
    feishuPanel.style.top = top + 'px';
    feishuPanel.style.width = panelW + 'px';
    feishuPanel.style.height = panelH + 'px';
    feishuPanel.style.right = 'auto';
    feishuPanel.style.bottom = 'auto';
  }

  // ─── Drag by header ────────────────────────────────────────
  let dragging = false, startX, startY, origLeft, origTop;
  feishuDragHandle.addEventListener('mousedown', (e) => {
    if (e.target === feishuClose || e.target === feishuMinimize) return;
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = feishuPanel.getBoundingClientRect();
    origLeft = rect.left;
    origTop = rect.top;
    feishuPanel.style.right = 'auto';
    feishuPanel.style.bottom = 'auto';
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    feishuPanel.style.left = (origLeft + e.clientX - startX) + 'px';
    feishuPanel.style.top = (origTop + e.clientY - startY) + 'px';
  });
  document.addEventListener('mouseup', () => { dragging = false; });

  // ─── Custom resize handles ─────────────────────────────────
  const resizeHandles = feishuPanel.querySelectorAll('.feishu-resize-handle');
  resizeHandles.forEach(handle => {
    let resizing = false, dir, startX2, startY2, startW, startH, startL, startT;
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      resizing = true;
      dir = handle.dataset.resize;
      startX2 = e.clientX;
      startY2 = e.clientY;
      const rect = feishuPanel.getBoundingClientRect();
      startW = rect.width;
      startH = rect.height;
      startL = rect.left;
      startT = rect.top;

      function onMove(e2) {
        if (!resizing) return;
        const dx = e2.clientX - startX2;
        const dy = e2.clientY - startY2;
        const minW = 280, minH = 200;

        if (dir.includes('e')) feishuPanel.style.width = Math.max(minW, startW + dx) + 'px';
        if (dir.includes('s')) feishuPanel.style.height = Math.max(minH, startH + dy) + 'px';
        if (dir.includes('w')) {
          const newW = Math.max(minW, startW - dx);
          feishuPanel.style.width = newW + 'px';
          feishuPanel.style.left = (startL + startW - newW) + 'px';
        }
        if (dir.includes('n')) {
          const newH = Math.max(minH, startH - dy);
          feishuPanel.style.height = newH + 'px';
          feishuPanel.style.top = (startT + startH - newH) + 'px';
        }
      }
      function onUp() {
        resizing = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });

  // ─── SSE Connection ────────────────────────────────────────
  async function loadHistory() {
    try {
      const resp = await fetch('/api/feishu/history?limit=80');
      if (!resp.ok) return;
      const data = await resp.json();
      const events = Array.isArray(data.events) ? data.events : [];
      events.forEach(renderFeishuEvent);
    } catch (err) {
      console.log('[FeishuPanel] history load failed', err);
    }
  }

  function connectSSE() {
    if (eventSource) return;
    eventSource = new EventSource('/api/feishu/events');
    eventSource.onopen = () => {
      console.log('[FeishuPanel] SSE connected');
    };
    eventSource.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        renderFeishuEvent(event);
      } catch (err) {
        // ignore comments (: keepalive, : connected)
      }
    };
    eventSource.onerror = () => {
      console.log('[FeishuPanel] SSE error, reconnecting...');
      eventSource.close();
      eventSource = null;
      reconnectTimer = setTimeout(connectSSE, FEISHU_RECONNECT_MS);
    };
  }

  function disconnectSSE() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function renderFeishuEvent(event) {
    if (!event || !event.type) return;
    const eventKey = event.id || [
      event.type,
      event.message_id || '',
      event.message_row_id || '',
      event.tool_call_id || '',
      event.text || '',
      event.ts || ''
    ].join('|');
    if (renderedEvents.has(eventKey)) return;
    renderedEvents.add(eventKey);

    // Remove empty state
    const emptyMsg = feishuFeed.querySelector('.feishu-empty');
    if (emptyMsg) emptyMsg.remove();

    const card = document.createElement('div');
    card.className = 'feishu-msg';
    card.dataset.ts = event.ts || Date.now();

    if (event.type === 'inbound') {
      const senderName = event.sender ? event.sender.replace('user:', '') : '用户';
      card.innerHTML =
        '<div class="feishu-msg-header">' +
        '<span class="feishu-badge">飞书</span>' +
        '<span class="feishu-sender">' + escapeHtml(senderName) + '</span>' +
        '<span class="feishu-time">' + formatFeishuTime(event.ts) + '</span>' +
        '</div>' +
        '<div class="feishu-body">' + escapeHtml(event.text || '') + '</div>';
    } else if (event.type === 'response') {
      const replyText = event.text || '';
      card.innerHTML =
        '<div class="feishu-msg-header">' +
        '<span class="feishu-badge feishu-badge-reply">Hermes</span>' +
        '<span class="feishu-time">' + formatFeishuTime(event.ts) + '</span>' +
        '</div>' +
        '<div class="feishu-body feishu-reply">' + escapeHtml(replyText) +
        '<div class="feishu-reply-meta">(' + event.time_sec + 's, ' + event.api_calls + ' API calls)</div>' +
        '</div>';
    } else if (event.type === 'tool_call') {
      const toolName = event.tool_name || 'tool';
      const summary = event.summary || event.arguments || '';
      card.classList.add('feishu-tool');
      card.innerHTML =
        '<div class="feishu-msg-header">' +
        '<span class="feishu-badge feishu-badge-tool">Tool Call</span>' +
        '<span class="feishu-sender">' + escapeHtml(toolName) + '</span>' +
        '<span class="feishu-time">' + formatFeishuTime(event.ts) + '</span>' +
        '</div>' +
        '<div class="feishu-body feishu-tool-body">' + escapeHtml(summary || '(no arguments)') + '</div>';
    } else if (event.type === 'tool_result') {
      const toolName = event.tool_name || 'tool';
      card.classList.add('feishu-tool-result');
      card.innerHTML =
        '<div class="feishu-msg-header">' +
        '<span class="feishu-badge feishu-badge-result">Result</span>' +
        '<span class="feishu-sender">' + escapeHtml(toolName) + '</span>' +
        '<span class="feishu-time">' + formatFeishuTime(event.ts) + '</span>' +
        '</div>' +
        '<div class="feishu-body feishu-tool-result-body">' + escapeHtml(event.text || '') + '</div>';
    } else {
      return;
    }

    feishuFeed.appendChild(card);
    feishuFeed.scrollTop = feishuFeed.scrollHeight;

    // Limit to last 50 messages
    while (feishuFeed.children.length > 100) {
      feishuFeed.removeChild(feishuFeed.firstChild);
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function formatFeishuTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  }

  connectSSE();
  window.addEventListener('beforeunload', disconnectSSE);
})();
