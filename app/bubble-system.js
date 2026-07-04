// Manual bubbles and live agent chat bubble rendering.
// --- Bubble Toggle & Manual Triggers ---
let bubblesVisible = true;

function expandAllBubbles() {
    bubblesVisible = true;
    agents.forEach(a => {
        const ms = getBubbleMinState(a);
        ms.thought = false;
        ms.speech = false;
        a.thoughtChars = 0;
        a.speechChars = 0;
        if (a.thought || a.lastThought) a.thoughtUpdatedAt = Date.now();
    });
    addGlobalLog('💬 All bubbles expanded');
    expandAllChat();
}

function minimizeAllBubbles() {
    agents.forEach(a => {
        const ms = getBubbleMinState(a);
        ms.thought = true;
        ms.speech = true;
    });
    addGlobalLog('💬 All bubbles minimized');
    minimizeAllChat();
}

function triggerBubble(type) {
    if (!selectedAgent) return;
    const text = prompt(type === 'thought' ? `💭 What is ${selectedAgent.name} thinking?` : `💬 What does ${selectedAgent.name} say?`);
    if (!text) return;
    if (type === 'thought') {
        selectedAgent.thought = text;
        selectedAgent.lastThought = text;
        selectedAgent.thoughtChars = 0;
        selectedAgent.thoughtAge = 0;
        selectedAgent.thoughtUpdatedAt = Date.now();
        getBubbleMinState(selectedAgent).thought = false;
        addGlobalLog(`💭 ${selectedAgent.name} ${(typeof i18n !== 'undefined' ? i18n.t('chat_thinking') : 'Thinking')}: ${text.substring(0, 40)}...`);
    } else {
    const target = prompt(_tr('message_target_prompt')) || '';
        selectedAgent.speech = text;
        selectedAgent.speechTarget = target;
        selectedAgent.lastSpeech = text;
        selectedAgent.lastSpeechTarget = target;
        selectedAgent.speechChars = 0;
        selectedAgent.speechAge = 0;
        selectedAgent.talkTimer = 60;
        addGlobalLog(`💬 ${selectedAgent.name}${target ? ' → ' + target : ''}: ${text.substring(0, 40)}...`);
    }
}

function clearAgentBubbles() {
    if (!selectedAgent) return;
    selectedAgent.thought = '';
    selectedAgent.speech = '';
    selectedAgent.speechTarget = '';
    addGlobalLog(`🧹 Cleared bubbles for ${selectedAgent.name}`);
}

// --- Wire up bubble buttons ---
// Expand/Minimize all handled via onclick in HTML
document.getElementById('btn-trigger-thought').addEventListener('click', function(e) {
    e.stopPropagation();
    triggerBubble('thought');
});
document.getElementById('btn-trigger-speech').addEventListener('click', function(e) {
    e.stopPropagation();
    triggerBubble('speech');
});
document.getElementById('btn-clear-bubbles').addEventListener('click', function(e) {
    e.stopPropagation();
    clearAgentBubbles();
});

// Canvas click handler for bubble minimize/restore
// This click handler is now handled by handleCanvasClick (mouseup/touchend)
// which properly converts coords through the camera transform.

// Mouse wheel scroll for chat bubbles is now handled in the main wheel listener above.

// Touch scroll on chat bubbles
var chatTouchStart = null;
var chatTouchBubble = null;
canvas.addEventListener('touchstart', function(e) {
    if (!e.touches || e.touches.length !== 1) return;
    const world = screenToWorld(e.touches[0].clientX, e.touches[0].clientY);
    for (var ti = 0; ti < renderedChatBubbles.length; ti++) {
        var tb = renderedChatBubbles[ti];
        var tr = tb.fullRect;
        if (world.x >= tr.x && world.x <= tr.x + tr.w && world.y >= tr.y && world.y <= tr.y + tr.h) {
            chatTouchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
            chatTouchBubble = tb;
            return;
        }
    }
    chatTouchStart = null;
    chatTouchBubble = null;
}, { passive: true });

canvas.addEventListener('touchmove', function(e) {
    if (!chatTouchStart || !chatTouchBubble || !e.touches || e.touches.length !== 1) return;
    var dy = chatTouchStart.y - e.touches[0].clientY;
    if (Math.abs(dy) > 15) {
        e.preventDefault();
        if (dy > 0 && chatTouchBubble.canScrollUp) {
            chatScrollOffset[chatTouchBubble.agentKey] = (chatScrollOffset[chatTouchBubble.agentKey] || 0) + 2;
        } else if (dy < 0 && chatTouchBubble.canScrollDown) {
            chatScrollOffset[chatTouchBubble.agentKey] = Math.max(0, (chatScrollOffset[chatTouchBubble.agentKey] || 0) - 2);
        }
        chatTouchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
}, { passive: false });

canvas.addEventListener('touchend', function() {
    chatTouchStart = null;
    chatTouchBubble = null;
}, { passive: true });


// === LIVE CHAT BUBBLE SYSTEM ===
var agentChatData = {};
var agentChatProjectWork = {}; // agentKey -> { projectId, taskTitle, phase } if working on project task
var agentChatWrapped = {}; // agentKey -> [{text, isUser, separator}] pre-wrapped lines
var agentChatImageCache = {}; // url -> HTMLImageElement

function getAgentChatMediaUrl(url) {
    if (!url) return '';
    url = String(url).trim();
    if (!url) return '';
    var isLocalPath = url.charAt(0) === '/' && url.indexOf('//') !== 0 && url.indexOf('/chat-media') !== 0 && url.indexOf('/sms-media') !== 0;
    return isLocalPath ? '/chat-media?path=' + encodeURIComponent(url) : url;
}

function getAgentChatFirstImage(msg) {
    var media = (msg && msg.media) || [];
    for (var i = 0; i < media.length; i++) {
        var item = media[i] || {};
        var raw = item.url || item.path || item.filePath || item.mediaUrl || '';
        var name = item.name || (raw.split('/').pop() || 'image');
        var type = (item.mimeType || item.contentType || '').toLowerCase();
        if (!type && /\.(png|jpe?g|gif|webp|bmp|svg)(\?|$)/i.test(name || raw)) type = 'image/*';
        if (raw && (type.indexOf('image/') === 0 || type === 'image/*')) {
            return { url: getAgentChatMediaUrl(raw), name: name };
        }
    }
    return null;
}

function getAgentChatCachedImage(url) {
    if (!url) return null;
    var cached = agentChatImageCache[url];
    if (cached) return cached;
    var img = new Image();
    img.onload = function() { agentChatImageCache[url]._loaded = true; };
    img.onerror = function() { agentChatImageCache[url]._error = true; };
    img.src = url;
    agentChatImageCache[url] = img;
    return img;
}
var lastChatPoll = 0;
var chatLastMsg = {}; // agentKey -> last seen message text
var chatTypewriterState = {};
var chatMinimized = {}; // agentKey -> bool
var _chatInitialLoad = true; // first poll: minimize all by default
var renderedChatBubbles = []; // for click detection
var renderedChatIcons = [];
var chatScrollOffset = {}; // agentKey -> scroll offset (lines from bottom)
var chatHoveredBubble = null; // agentKey of bubble mouse is over
var _chatTooltip = null; // { x, y, text } for project indicator tooltip

function truncateAgentChatActivity(text, limit) {
    text = String(text || '').replace(/\s+/g, ' ').trim();
    if (!text) return '';
    return text.length > limit ? text.substring(0, limit - 3) + '...' : text;
}

function getAgentChatToolArg(args, names) {
    if (!args || typeof args !== 'object') return '';
    for (var i = 0; i < names.length; i++) {
        var value = args[names[i]];
        if (value !== undefined && value !== null && value !== '') return String(value);
    }
    return '';
}

function stringifyAgentChatToolPayload(value) {
    if (value === undefined || value === null || value === '') return '';
    if (typeof value === 'string') return value;
    try {
        return JSON.stringify(value);
    } catch (e) {
        return String(value);
    }
}

function formatAgentChatToolLine(tool) {
    tool = tool || {};
    var rawName = tool.name || tool.toolName || tool.tool_name || 'tool';
    var name = String(rawName).replace(/^functions\./, '');
    var args = tool.arguments || tool.args || tool.input || {};
    var result = stringifyAgentChatToolPayload(tool.error || tool.result || tool.output);
    var preview = '';

    if (name === 'exec' || name === 'bash' || name === 'Command') {
        preview = getAgentChatToolArg(args, ['command', 'cmd', 'description', 'value']);
    } else if (name === 'read' || name === 'write' || name === 'edit') {
        preview = getAgentChatToolArg(args, ['path', 'file_path', 'filePath', 'file']);
    } else if (name === 'sessions_send') {
        var target = getAgentChatToolArg(args, ['sessionKey', 'label', 'toAgentId']);
        var message = getAgentChatToolArg(args, ['message', 'text', 'content']);
        preview = [target, message].filter(Boolean).join(': ');
    } else if (name === 'sessions_spawn') {
        preview = [getAgentChatToolArg(args, ['agentId', 'agent']), getAgentChatToolArg(args, ['task', 'message'])].filter(Boolean).join(': ');
    } else if (name === 'browser') {
        preview = [getAgentChatToolArg(args, ['action', 'method']), getAgentChatToolArg(args, ['url', 'selector', 'text'])].filter(Boolean).join(': ');
    } else if (name === 'web_search') {
        preview = getAgentChatToolArg(args, ['query', 'q']);
    } else if (name === 'web_fetch') {
        preview = getAgentChatToolArg(args, ['url']);
    } else if (name === 'process') {
        preview = getAgentChatToolArg(args, ['action', 'status']);
    } else {
        preview = getAgentChatToolArg(args, ['query', 'url', 'action', 'input', 'value', 'message', 'path']);
    }

    if (!preview && result) preview = result;
    if (!preview) preview = tool.status === 'running' ? 'running...' : 'completed';
    var status = tool.error || tool.status === 'error' ? ' error' : '';
    return name + status + ': ' + truncateAgentChatActivity(preview, 96);
}

function getAgentChatActivityLines(msg) {
    var lines = [];
    if (!msg) return lines;
    var tools = Array.isArray(msg.tools) ? msg.tools : [];
    if (tools.length) {
        var shown = tools.slice(-3);
        for (var ti = 0; ti < shown.length; ti++) {
            lines.push(formatAgentChatToolLine(shown[ti]));
        }
        if (tools.length > shown.length) lines.push('+' + (tools.length - shown.length) + ' more tool calls');
    }
    if (msg.thinking || msg.reasoningTokens) {
        var reason = msg.thinking ? String(msg.thinking).replace(/\s+/g, ' ').trim() : ('reasoning tokens: ' + msg.reasoningTokens);
        if (reason.length > 90) reason = reason.substring(0, 87) + '...';
        lines.push('[thinking] ' + reason);
    }
    if (msg.approval) {
        var approvalStatus = msg.approval.status || 'pending';
        var approvalCommand = msg.approval.command || msg.approval.title || 'Hermes command';
        if (approvalCommand.length > 82) approvalCommand = approvalCommand.substring(0, 79) + '...';
        lines.push('[approval ' + approvalStatus + '] ' + approvalCommand);
    }
    return lines;
}

function getAgentChatActivitySignature(msg) {
    if (!msg) return '';
    var tools = Array.isArray(msg.tools) ? msg.tools : [];
    var approval = msg.approval ? ((msg.approval.status || '') + ':' + (msg.approval.id || msg.approval.command || 'approval')) : '';
    return tools.map(function(t) { return (t && (t.status || '') + ':' + (t.name || t.toolName || t.tool_name || 'tool')); }).join('|') + '|' + (msg.thinking || '') + '|' + (msg.reasoningTokens || 0) + '|' + approval;
}

function pollAgentChat() {
    var now = Date.now();
    if (now - lastChatPoll < 3000) return;
    lastChatPoll = now;
    fetch('/agent-chat').then(function(res) {
        if (!res.ok) return;
        return res.json();
    }).then(function(data) {
        if (!data) return;
        // Extract project work metadata (keyed by _projectWork)
        agentChatProjectWork = data._projectWork || {};
        delete data._projectWork;
        for (var key in data) {
            var msgs = data[key];
            var lastMsg = msgs[msgs.length - 1];
            var lastText = lastMsg ? ((lastMsg.text || '') + (getAgentChatActivitySignature(lastMsg) ? ' [activity]' : '') + (getAgentChatFirstImage(lastMsg) ? ' [image]' : '')) : '';
            if (lastText !== chatLastMsg[key]) {
                chatTypewriterState[key] = { charIdx: 0, targetText: lastText, done: false, msgIdx: msgs.length - 1 };
                // On first load, keep minimized. After that, auto-expand on new messages.
                if (_chatInitialLoad) {
                    chatMinimized[key] = true;
                } else {
                    chatMinimized[key] = false;
                }
                chatScrollOffset[key] = 0;
            }
            chatLastMsg[key] = lastText;
            // Pre-wrap all messages EXCEPT the last one (typewriter handles that per-frame)
            var wrapped = [];
            for (var mi = 0; mi < msgs.length; mi++) {
                var msg = msgs[mi];
                var isUser = (msg.role === 'user');
                var timeTag = '';
                if (msg.epochMs) {
                    var d = new Date(msg.epochMs);
                    var h = d.getHours(); var mn = d.getMinutes();
                    var ampm = h >= 12 ? 'PM' : 'AM';
                    h = h % 12 || 12;
                    timeTag = '[' + h + ':' + (mn < 10 ? '0' : '') + mn + ' ' + ampm + '] ';
                } else if (msg.time) {
                    timeTag = '[' + msg.time + '] ';
                }
                var senderLabel = '';
                if (isUser && msg.from) {
                    senderLabel = msg.to ? (msg.from + ' → ' + msg.to) : msg.from;
                }
                var prefix = timeTag + (isUser ? (senderLabel ? senderLabel + ': ' : 'IN: ') : '');
                if (mi < msgs.length - 1) {
                    // Non-last messages: pre-wrap now (they never change)
                    var displayText = msg.text || '';
                    var activityLines = getAgentChatActivityLines(msg);
                    if (displayText.length > 350) displayText = displayText.substring(0, 347) + '...';
                    var lines = wrapChatText(prefix + displayText, 155);
                    for (var li = 0; li < lines.length; li++) {
                        wrapped.push({ text: lines[li], isUser: isUser });
                    }
                    for (var al = 0; al < activityLines.length; al++) {
                        var actLines = wrapChatText(activityLines[al], 155);
                        for (var ali = 0; ali < actLines.length; ali++) {
                            wrapped.push({ text: actLines[ali], isUser: false, activity: true });
                        }
                    }
                    var imgMedia = getAgentChatFirstImage(msg);
                    if (imgMedia) wrapped.push({ image: imgMedia, isUser: isUser });
                    wrapped.push({ text: '', separator: true });
                }
                // Last message stored as marker for per-frame typewriter wrapping
                if (mi === msgs.length - 1) {
                    wrapped.push({ _lastMsg: true, msg: msg, isUser: isUser, prefix: prefix });
                }
            }
            agentChatWrapped[key] = wrapped;
        }
        agentChatData = data;
        _chatInitialLoad = false;
    }).catch(function(e) {});
}

function wrapChatText(text, maxW) {
    ctx.font = '9px Arial, sans-serif';
    var padW = maxW - 12;
    var words = text.split(' ');
    var lines = []; var line = '';
    for (var wi = 0; wi < words.length; wi++) {
        var word = words[wi];
        // Break long words that exceed bubble width
        while (ctx.measureText(word).width > padW) {
            var fit = '';
            for (var ci = 0; ci < word.length; ci++) {
                var tryFit = fit + word[ci];
                if (ctx.measureText(line ? line + ' ' + tryFit : tryFit).width > padW) break;
                fit = tryFit;
            }
            if (fit.length === 0) { fit = word[0]; }
            if (line) { lines.push(line); line = ''; }
            lines.push(fit);
            word = word.substring(fit.length);
        }
        if (!word) continue;
        var test = line ? line + ' ' + word : word;
        if (ctx.measureText(test).width > padW && line) {
            lines.push(line); line = word;
        } else { line = test; }
    }
    if (line) lines.push(line);
    return lines;
}

function minimizeAllChat() {
    agents.forEach(function(agent) {
        if (agent && agent.statusKey) chatMinimized[agent.statusKey] = true;
    });
    addGlobalLog('💬 All chat bubbles minimized');
}

function expandAllChat() {
    agents.forEach(function(agent) {
        if (agent && agent.statusKey) chatMinimized[agent.statusKey] = false;
    });
    addGlobalLog('💬 All chat bubbles expanded');
}

function handleChatBubbleClick(canvasX, canvasY) {
    // Check close buttons on expanded chat bubbles
    for (var i = 0; i < renderedChatBubbles.length; i++) {
        var rb = renderedChatBubbles[i];
        var cr = rb.closeRect;
        if (canvasX >= cr.x && canvasX <= cr.x + cr.w && canvasY >= cr.y && canvasY <= cr.y + cr.h) {
            chatMinimized[rb.agentKey] = true;
            return true;
        }
    }
    // Check minimized icons — click to restore
    for (var j = 0; j < renderedChatIcons.length; j++) {
        var icon = renderedChatIcons[j];
        if (canvasX >= icon.x && canvasX <= icon.x + icon.w && canvasY >= icon.y && canvasY <= icon.y + icon.h) {
            chatMinimized[icon.agentKey] = false;
            return true;
        }
    }
    return false;
}

function _meetingBubbleText(turn) {
    if (!turn) return '';
    if (turn.pending) {
        if (turn.timedOut) return _mtgT('meeting_provider_call_timeout', 'Meeting response timed out');
        var waiting = _mtgT('meeting_provider_calling', 'Preparing meeting response...');
        var elapsed = Number(turn.elapsedSec || 0);
        if (elapsed > 0) waiting += ' · ' + _mtgT('meeting_provider_waited', 'waited') + ' ' + Math.round(elapsed) + 's';
        return waiting;
    }
    if (turn.structured && turn.structured.position) return String(turn.structured.position || '');
    if (turn.structured && turn.structured.summary) return String(turn.structured.summary || '');
    return String(turn.text || turn.rawText || '');
}

function _meetingLatestSpeakerKey(record) {
    if (!record) return '';
    if (record.currentSpeaker) return String(record.currentSpeaker);
    var pending = Array.isArray(record.pendingCalls) ? record.pendingCalls : [];
    if (pending.length) {
        var lastPending = pending[pending.length - 1] || {};
        return String(lastPending.speaker || lastPending.agentId || lastPending.participant || lastPending.actorId || '');
    }
    var transcript = Array.isArray(record.transcript) ? record.transcript : [];
    for (var i = transcript.length - 1; i >= 0; i--) {
        if (transcript[i] && transcript[i].speaker) return String(transcript[i].speaker);
    }
    return '';
}

function _meetingChatSourceForSpeaker(agent) {
    var meeting = _meetingForAgent(agent);
    if (!meeting) return null;
    var record = _meetingRawActiveRecord(meeting.id) || meeting.raw || meeting;
    var rows = [];
    var latestTranscriptSeq = 0;
    (record.transcript || []).forEach(function(turn) {
        if (!turn || !_meetingAgentMatchesKey(agent, turn.speaker)) return;
        latestTranscriptSeq = Math.max(latestTranscriptSeq, Number(turn.sequence || 0));
        rows.push(Object.assign({ pending: false }, turn));
    });
    (record.pendingCalls || []).forEach(function(call) {
        var speaker = call && (call.speaker || call.agentId || call.participant || call.actorId);
        if (!speaker || !_meetingAgentMatchesKey(agent, speaker)) return;
        if (latestTranscriptSeq && Number(call.sequence || 0) <= latestTranscriptSeq) return;
        rows.push(Object.assign({ pending: true, speaker: speaker }, call));
    });
    rows.sort(function(a, b) { return Number(a.sequence || 0) - Number(b.sequence || 0); });
    rows = rows.filter(function(turn) { return _meetingBubbleText(turn); });
    var result = record.result || {};
    if (record.moderator && _meetingAgentMatchesKey(agent, record.moderator) && (record.executionStage === 'summarizing' || result.summary || result.resolution)) {
        var summaryText = String(result.summary || result.resolution || '').trim();
        if (summaryText) {
            rows.push({
                sequence: Number(record.lastEventSequence || 0) + 1,
                speaker: record.moderator,
                text: summaryText,
                createdAt: result.createdAt || record.updatedAt || '',
                pending: false,
                kind: 'meeting_result'
            });
        }
    }
    if (!rows.length) return null;
    var msgs = rows.slice(-1).map(function(turn) {
        return {
            role: 'assistant',
            text: _meetingBubbleText(turn),
            epochMs: Date.parse(turn.createdAt || turn.updatedAt || '') || 0,
            _meetingTurn: true
        };
    });
    var wrapped = [];
    for (var mi = 0; mi < msgs.length; mi++) {
        var msg = msgs[mi];
        if (mi < msgs.length - 1) {
            var displayText = msg.text || '';
            if (displayText.length > 350) displayText = displayText.substring(0, 347) + '...';
            var lines = wrapChatText(displayText, 155);
            for (var li = 0; li < lines.length; li++) wrapped.push({ text: lines[li], isUser: false });
            wrapped.push({ text: '', separator: true });
        } else {
            wrapped.push({ _lastMsg: true, msg: msg, isUser: false, prefix: '' });
        }
    }
    return { msgs: msgs, wrapped: wrapped };
}

function drawChatBubbles() {
    var chatBubbles = [];
    renderedChatBubbles = [];
    renderedChatIcons = [];

    for (var ai = 0; ai < agents.length; ai++) {
        var agent = agents[ai];
        var meeting = _meetingForAgent(agent);
        var meetingSource = meeting ? _meetingChatSourceForSpeaker(agent) : null;
        var msgs = null;
        var preWrapped = null;
        var isMeetingBubble = !!meeting;
        if (meeting) {
            if (!meetingSource) continue;
            msgs = meetingSource.msgs;
            preWrapped = meetingSource.wrapped;
        } else {
            msgs = agentChatData[agent.statusKey];
            preWrapped = agentChatWrapped[agent.statusKey];
            if (!msgs || msgs.length === 0 || !preWrapped) continue;
        }

        var headX = agent.x;
        var headY = agent.y - 50;

        // Minimized icon
        if (chatMinimized[agent.statusKey]) {
            var iconX = headX + 18;
            var iconY = headY - 20;
            // Draw minimized icon
            ctx.save();
            var iconCx = iconX + 7, iconCy = iconY + 7;
            ctx.fillStyle = 'rgba(15,20,30,0.7)';
            ctx.beginPath(); ctx.arc(iconCx, iconCy, 8, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = 'rgba(100,200,255,0.6)';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.arc(iconCx, iconCy, 8, 0, Math.PI * 2); ctx.stroke();
            ctx.font = '8px sans-serif';
            ctx.fillStyle = '#6cf';
            ctx.textAlign = 'center';
            ctx.fillText('💬', iconCx, iconCy + 3);
            ctx.restore();
            renderedChatIcons.push({ agentKey: agent.statusKey, x: iconX, y: iconY, w: 16, h: 16 });
            continue;
        }

        var renderedLines = [];
        for (var pi = 0; pi < preWrapped.length; pi++) {
            var entry = preWrapped[pi];
            if (entry._lastMsg) {
                // Last message — handle typewriter per-frame (only this one wraps)
                var tw = chatTypewriterState[agent.statusKey];
                var displayText = entry.msg.text || '';
                if (tw && !tw.done && tw.msgIdx === msgs.length - 1) {
                    tw.charIdx = Math.min(tw.charIdx + 2, tw.targetText.length);
                    displayText = tw.targetText.substring(0, tw.charIdx);
                    if (tw.charIdx >= tw.targetText.length) tw.done = true;
                }
                if (displayText.length > 350) displayText = displayText.substring(0, 347) + '...';
                var wrapped = wrapChatText(entry.prefix + displayText, 155);
                for (var li = 0; li < wrapped.length; li++) {
                    renderedLines.push({ text: wrapped[li], isUser: entry.isUser });
                }
                var activityLines = getAgentChatActivityLines(entry.msg);
                for (var al = 0; al < activityLines.length; al++) {
                    var actWrapped = wrapChatText(activityLines[al], 155);
                    for (var aw = 0; aw < actWrapped.length; aw++) {
                        renderedLines.push({ text: actWrapped[aw], isUser: false, activity: true });
                    }
                }
                var imgMedia = getAgentChatFirstImage(entry.msg);
                if (imgMedia) renderedLines.push({ image: imgMedia, isUser: entry.isUser });
            } else {
                renderedLines.push(entry);
            }
        }
        var maxVisLines = 10;
        var scrollOff = chatScrollOffset[agent.statusKey] || 0;
        var endIdx = renderedLines.length - scrollOff;
        if (endIdx < maxVisLines) endIdx = Math.min(renderedLines.length, maxVisLines);
        var startIdx = Math.max(0, endIdx - maxVisLines);
        var visLines = renderedLines.slice(startIdx, endIdx);
        var canScrollUp = startIdx > 0;
        var canScrollDown = scrollOff > 0;
        var mediaLineCount = visLines.filter(function(l) { return l.image; }).length;
        var bubbleH = Math.min(220, 26 + (visLines.length - mediaLineCount) * 12 + mediaLineCount * 58);
        chatBubbles.push({ agent: agent, agentKey: agent.statusKey, lines: visLines, canScrollUp: canScrollUp, canScrollDown: canScrollDown, x: headX + 25, y: headY - bubbleH - 10, w: 155, h: bubbleH, anchorX: headX, anchorY: headY, });
    }

    // Compute visible world bounds so bubbles (especially headers with indicators)
    // stay on-screen.  Falls back to 2 if the camera math isn't available.
    var _cbMinX = 2, _cbMinY = 2, _cbMaxX = W - 2, _cbMaxY = H - 20;
    try {
        var _cbBase = getBaseScale();
        var _cbTZ = _cbBase * camera.zoom;
        _cbMinX = Math.max(2, (0 - displayW / 2) / _cbTZ + W / 2 + camera.x + 2);
        _cbMinY = Math.max(2, (0 - displayH / 2) / _cbTZ + H / 2 + camera.y + 2);
        _cbMaxX = Math.min(W - 2, (displayW - displayW / 2) / _cbTZ + W / 2 + camera.x - 2);
        _cbMaxY = Math.min(H - 20, (displayH - displayH / 2) / _cbTZ + H / 2 + camera.y - 20);
    } catch(e) {}

    // Collision resolution
    for (var ci = 0; ci < chatBubbles.length; ci++) {
        chatBubbles[ci].x = Math.max(_cbMinX, Math.min(_cbMaxX - chatBubbles[ci].w, chatBubbles[ci].x));
        chatBubbles[ci].y = Math.max(_cbMinY, Math.min(_cbMaxY - chatBubbles[ci].h, chatBubbles[ci].y));
    }
    for (var pass = 0; pass < 5; pass++) {
        for (var i = 0; i < chatBubbles.length; i++) {
            for (var j = i + 1; j < chatBubbles.length; j++) {
                var a = chatBubbles[i], bb = chatBubbles[j];
                if (a.x < bb.x + bb.w && a.x + a.w > bb.x && a.y < bb.y + bb.h && a.y + a.h > bb.y) {
                    var overlapY = Math.min(a.y + a.h - bb.y, bb.y + bb.h - a.y);
                    var overlapX = Math.min(a.x + a.w - bb.x, bb.x + bb.w - a.x);
                    if (overlapY < overlapX) {
                        if (a.y < bb.y) { a.y -= overlapY / 2 + 2; bb.y += overlapY / 2 + 2; }
                        else { bb.y -= overlapY / 2 + 2; a.y += overlapY / 2 + 2; }
                    } else {
                        if (a.x < bb.x) { a.x -= overlapX / 2 + 2; bb.x += overlapX / 2 + 2; }
                        else { bb.x -= overlapX / 2 + 2; a.x += overlapX / 2 + 2; }
                    }
                }
            }
        }
        for (var ri = 0; ri < chatBubbles.length; ri++) {
            chatBubbles[ri].x = Math.max(_cbMinX, Math.min(_cbMaxX - chatBubbles[ri].w, chatBubbles[ri].x));
            chatBubbles[ri].y = Math.max(_cbMinY, Math.min(_cbMaxY - chatBubbles[ri].h, chatBubbles[ri].y));
        }
    }

    // Draw
    for (var bi = 0; bi < chatBubbles.length; bi++) {
        var b = chatBubbles[bi];
        ctx.save();
        var r = 6;

        // Speech tail
        var edgeX = Math.max(b.x + 8, Math.min(b.x + b.w - 8, b.anchorX));
        var edgeY = b.y + b.h;
        ctx.fillStyle = 'rgba(255,255,230,0.95)';
        ctx.strokeStyle = b.agent.color + '99';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(edgeX - 6, edgeY);
        ctx.lineTo(b.anchorX, b.anchorY);
        ctx.lineTo(edgeX + 6, edgeY);
        ctx.closePath();
        ctx.fill(); ctx.stroke();

        // Bubble body
        ctx.fillStyle = 'rgba(255,255,230,0.95)';
        ctx.strokeStyle = b.agent.color + '99';
        ctx.lineWidth = 1.5;
        drawRoundRect(b.x, b.y, b.w, b.h, r);
        ctx.fill(); ctx.stroke();

        // Header banner
        ctx.fillStyle = b.agent.color + 'dd';
        ctx.save();
        ctx.beginPath(); ctx.rect(b.x, b.y, b.w, 15); ctx.clip();
        drawRoundRect(b.x, b.y, b.w, 18, r); ctx.fill();
        ctx.restore();

        // Header text
        ctx.font = 'bold 9px Arial, sans-serif';
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'left';
        ctx.fillText(b.agent.name, b.x + 8, b.y + 11);

        // Live pulsing dot
        var pulse = 0.5 + Math.sin(Date.now() * 0.005) * 0.5;
        ctx.fillStyle = 'rgba(0,200,80,' + (0.5 + pulse * 0.5) + ')';
        ctx.beginPath(); ctx.arc(b.x + b.w - 22, b.y + 7, 3, 0, Math.PI * 2); ctx.fill();

        // Project work indicator — blinking square next to green dot
        var projWork = agentChatProjectWork[b.agentKey];
        if (projWork) {
            var sqPulse = 0.5 + Math.sin(Date.now() * 0.005) * 0.5;
            var sqAlpha = 0.5 + sqPulse * 0.5;
            // Position square immediately left of the green dot (dot center is at b.x+b.w-22, radius 3)
            var sqS = 6;
            var sqX = b.x + b.w - 22 - 3 - sqS - 2; // 2px gap from dot edge
            var sqY = b.y + 7 - sqS / 2; // vertically centered with dot
            // Blinking square — same animation as the green dot
            ctx.fillStyle = 'rgba(0,150,255,' + sqAlpha + ')';
            ctx.fillRect(sqX, sqY, sqS, sqS);
            ctx.strokeStyle = 'rgba(255,255,255,' + sqAlpha + ')';
            ctx.lineWidth = 1;
            ctx.strokeRect(sqX, sqY, sqS, sqS);
        }

        // Close button
        var closeX = b.x + b.w - 13;
        var closeY = b.y + 3;
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.fillRect(closeX, closeY, 10, 10);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 9px Arial'; ctx.textAlign = 'center';
        ctx.fillText(String.fromCharCode(8722), closeX + 5, closeY + 8);
        renderedChatBubbles.push({ agentKey: b.agentKey, closeRect: { x: closeX, y: closeY, w: 10, h: 10 }, fullRect: { x: b.x, y: b.y, w: b.w, h: b.h }, canScrollUp: b.canScrollUp, canScrollDown: b.canScrollDown, projIndicator: projWork ? { x: b.x + b.w - 33, y: b.y + 4, w: 6, h: 6, info: projWork } : null });

        // Message lines
        var lineY = b.y + 26;
        ctx.font = '9px Arial, sans-serif';
        ctx.textAlign = 'left';
        for (var li = 0; li < b.lines.length; li++) {
            var ln = b.lines[li];
            if (ln.separator) {
                ctx.strokeStyle = b.agent.color + '33';
                ctx.lineWidth = 0.5;
                ctx.beginPath();
                ctx.moveTo(b.x + 6, lineY - 2);
                ctx.lineTo(b.x + b.w - 6, lineY - 2);
                ctx.stroke();
                lineY += 4;
                continue;
            }
            if (ln.image) {
                var imgUrl = ln.image.url;
                var img = getAgentChatCachedImage(imgUrl);
                var ix = b.x + 6, iy = lineY - 8, iw = b.w - 12, ih = 52;
                ctx.fillStyle = 'rgba(0,0,0,0.08)';
                drawRoundRect(ix, iy, iw, ih, 5); ctx.fill();
                if (img && img._loaded) {
                    var scale = Math.min(iw / img.naturalWidth, ih / img.naturalHeight);
                    var dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
                    ctx.drawImage(img, ix + (iw - dw) / 2, iy + (ih - dh) / 2, dw, dh);
                } else {
                    ctx.fillStyle = img && img._error ? '#aa4444' : '#666';
                    ctx.font = '9px Arial, sans-serif';
                    ctx.fillText(img && img._error ? '🖼️ image unavailable' : '🖼️ loading image...', ix + 6, iy + 28);
                }
                lineY += 58;
                continue;
            }
            ctx.fillStyle = ln.isUser ? '#4466aa' : '#222';
            ctx.fillText(ln.text, b.x + 5, lineY);
            lineY += 12;
        }
        // Scroll indicators
        if (b.canScrollUp) {
            ctx.fillStyle = 'rgba(180,150,50,0.6)';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('▲', b.x + b.w / 2, b.y + 24);
        }
        if (b.canScrollDown) {
            ctx.fillStyle = 'rgba(180,150,50,0.6)';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('▼', b.x + b.w / 2, b.y + b.h - 3);
        }
        ctx.restore();
    }
}

Object.assign(window, {
    expandAllBubbles,
    minimizeAllBubbles,
    triggerBubble,
    clearAgentBubbles,
    pollAgentChat,
    wrapChatText,
    minimizeAllChat,
    expandAllChat,
    handleChatBubbleClick,
    drawChatBubbles
});
