// Virtual Office - 2D Visualization
const canvas = document.getElementById('officeCanvas');
const ctx = canvas.getContext('2d');

const DPR = window.devicePixelRatio || 2;
const TILE = 40;
const HALF_TILE = TILE / 2;

// --- DYNAMIC CANVAS SIZE (data-driven) ---
const OFFICE_CONFIG_KEY = 'vo-product-office-config';
const COLOR_FAVORITES_KEY = 'vo-product-color-favorites';
const MIN_TILES_X = 10;
const MIN_TILES_Y = 10;

function _tr(key, params) {
    return typeof i18n !== 'undefined' ? i18n.t(key, params) : key;
}

// Load office config: server first, then localStorage fallback
function loadOfficeConfig() {
    // Try localStorage first for immediate startup (sync)
    try {
        const saved = localStorage.getItem(OFFICE_CONFIG_KEY);
        if (saved) return JSON.parse(saved);
    } catch (e) {}
    return { canvasWidth: 1000, canvasHeight: 700 };
}

// Async: fetch server config and apply if newer/exists
var _serverConfigLoaded = false;
function _loadServerConfig() {
    fetch('/api/office-config').then(function(r) {
        if (!r.ok) return null;
        return r.json();
    }).then(function(data) {
        if (!data || data.error) return;
        _serverConfigLoaded = true;
        // Merge server config into officeConfig
        if (data.canvasWidth) { W = data.canvasWidth; officeConfig.canvasWidth = W; }
        if (data.canvasHeight) { H = data.canvasHeight; officeConfig.canvasHeight = H; }
        if (data.walls) officeConfig.walls = data.walls;
        if (data.floor) officeConfig.floor = data.floor;
        if (data.furniture) officeConfig.furniture = data.furniture;
        if (data.agents) officeConfig.agents = data.agents;
        if (data.branches) officeConfig.branches = data.branches;
        if (data.pet) officeConfig.pet = data.pet;
        // Migration: add default interactive windows if none exist
        if (officeConfig.furniture && !officeConfig.furniture.some(function(f){ return f.type === 'interactiveWindow'; })) {
            officeConfig.furniture.push({ id: 'iw-hq-left',  type: 'interactiveWindow', x: 388, y: 10, weather: true, showSun: true });
            officeConfig.furniture.push({ id: 'iw-hq-right', type: 'interactiveWindow', x: 576, y: 10, weather: true, showSun: false });
        }
        // Trigger proper canvas resize (reads wrapper dimensions, applies DPR)
        if (typeof resizeCanvas === 'function') resizeCanvas();
        if (typeof _refreshWallSectionButtons === 'function') _refreshWallSectionButtons();
        // Re-apply agent overrides
        if (typeof _initAgentsFromDefs === 'function' && _rosterLoaded) _initAgentsFromDefs();
        if (typeof _syncAllDeskAssignments === 'function') _syncAllDeskAssignments();
        if (typeof getInteractionSpots === 'function') getInteractionSpots();
        if (typeof buildCollisionGrid === 'function') buildCollisionGrid();
        if (typeof initPets === 'function') initPets();
        // Cache locally
        localStorage.setItem(OFFICE_CONFIG_KEY, JSON.stringify(officeConfig));
    }).catch(function(e) { /* server not available, use local */ });
}

// Save office config to BOTH server and localStorage
var _saveDebounceTimer = null;
function saveOfficeConfig() {
    officeConfig.canvasWidth = W;
    officeConfig.canvasHeight = H;
    _deskPosCache = null; // invalidate lamp cache
    MEETING_SLOTS = getMeetingSlots(); // re-derive meeting slots from current meeting table position
    // Sync LOCATIONS.meeting with actual meeting table position
    var mtPos = getMeetingTablePos();
    if (mtPos) { LOCATIONS.meeting.x = mtPos.x; LOCATIONS.meeting.y = mtPos.y; }
    // Save to localStorage immediately (fast)
    localStorage.setItem(OFFICE_CONFIG_KEY, JSON.stringify(officeConfig));
    // Debounce server save (avoid hammering on rapid edits)
    clearTimeout(_saveDebounceTimer);
    _saveDebounceTimer = setTimeout(function() {
        fetch('/api/office-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(officeConfig)
        }).catch(function(e) { console.warn('Failed to save to server:', e); });
    }, 500);
}

function loadColorFavorites() {
    try {
        const saved = localStorage.getItem(COLOR_FAVORITES_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed) && parsed.length) return parsed;
        }
    } catch (e) {}
    return ['#ffffff', '#e3f2fd', '#90caf9', '#546e7a', '#37474f', '#263238', '#ffd600', '#ffca28'];
}

function saveColorFavorites() {
    try {
        localStorage.setItem(COLOR_FAVORITES_KEY, JSON.stringify(colorFavorites));
    } catch (e) {}
}

const _officeConfig = loadOfficeConfig();
var colorFavorites = loadColorFavorites();
var W = _officeConfig.canvasWidth;
var H = _officeConfig.canvasHeight;

const DEFAULT_BRANCHES = [
    { id: 'HQ', name: typeof i18n !== 'undefined' ? i18n.t('branch_hq') : 'Office Manager', emoji: '⚡', theme: 'branch-gold' },
    { id: 'PQ', name: typeof i18n !== 'undefined' ? i18n.t('branch_pq') : 'Pro Quality Plumbing', emoji: '🔧', theme: 'branch-blue' },
    { id: 'ENG', name: typeof i18n !== 'undefined' ? i18n.t('branch_eng') : 'Caltran Engineering', emoji: '🏗️', theme: 'branch-orange' },
    { id: 'GEN', name: typeof i18n !== 'undefined' ? i18n.t('branch_gen') : 'General Office', emoji: '🌐', theme: 'branch-cyan' },
    { id: 'BIZ', name: typeof i18n !== 'undefined' ? i18n.t('branch_biz') : 'Business', emoji: '🔥', theme: 'branch-red' }
];
const UNASSIGNED_BRANCH = { id: 'UNASSIGNED', name: typeof i18n !== 'undefined' ? i18n.t('branch_unassigned') : 'Unassigned', emoji: '❓', theme: 'branch-gray' };

var _branchListCache = null;
var _branchMapCache = null;
var _branchCacheKey = '';
function _invalidateBranchCache() { _branchListCache = null; _branchMapCache = null; _branchCacheKey = ''; }
function getBranchList() {
    var src = (officeConfig && officeConfig.branches) || _officeConfig.branches || DEFAULT_BRANCHES;
    var key = src.length + ':' + (src.length > 0 ? src[0].id : '');
    if (_branchListCache && _branchCacheKey === key) return _branchListCache;
    var list = src.slice();
    var hasUnassigned = list.some(function(b){ return b.id === UNASSIGNED_BRANCH.id; });
    if (!hasUnassigned) list.push(UNASSIGNED_BRANCH);
    _branchListCache = list;
    _branchCacheKey = key;
    // Build lookup map
    _branchMapCache = {};
    list.forEach(function(b) { _branchMapCache[b.id] = b; });
    return list;
}
function getBranchById(branchId) {
    if (!_branchMapCache) getBranchList();
    return (_branchMapCache && _branchMapCache[branchId]) || UNASSIGNED_BRANCH;
}
function getBranchDisplayName(branchId) {
    if (branchId === 'UNASSIGNED') return _tr('branch_unassigned');
    return getBranchById(branchId).name;
}
function getBranchTheme(branchId) {
    return getBranchById(branchId).theme || 'branch-gray';
}
function ensureValidAgentBranches() {
    var valid = new Set(getBranchList().map(function(b){ return b.id; }));
    agents.forEach(function(a){ if (!valid.has(a.branch)) a.branch = 'UNASSIGNED'; });
    if (officeConfig.agents) {
        officeConfig.agents.forEach(function(a){ if (!valid.has(a.branch)) a.branch = 'UNASSIGNED'; });
    }
}

// --- OFFICE CONFIG (data-driven) ---
var officeConfig = {
    canvasWidth: W,
    canvasHeight: H,
    walls: _officeConfig.walls || {
        topWall: { color: '#37474f', accentColor: '#263238', trimColor: '#fff' },
        sections: [
            { x: 0,   w: 380, color: '#37474f', accentColor: '#263238' }
        ],
        height: 90,
        trimColor: '#fff'
    },
    floor: _officeConfig.floor || { color1: '#c0c0c0', color2: '#b0b0b0' },
    furniture: _officeConfig.furniture || [],  // populated by initOfficeConfig() if empty
    branches: _officeConfig.branches || DEFAULT_BRANCHES.slice()
};

function getTopWallConfig() {
    var walls = (officeConfig && officeConfig.walls) || {};
    var topWall = walls.topWall || {};
    var sections = Array.isArray(walls.sections) ? walls.sections : [];
    if (!topWall.color && sections[0]) topWall.color = sections[0].color;
    if (!topWall.accentColor && sections[0]) topWall.accentColor = sections[0].accentColor;
    if (!topWall.trimColor) topWall.trimColor = walls.trimColor || '#fff';
    if (!topWall.color) topWall.color = '#37474f';
    if (!topWall.accentColor) topWall.accentColor = '#263238';
    return topWall;
}

function getRenderedWallSections() {
    var topWall = getTopWallConfig();
    return [{
        x: 0,
        w: W,
        color: topWall.color,
        accentColor: topWall.accentColor,
        trimColor: topWall.trimColor,
        sourceIndex: 0
    }];
}

// --- COLLISION GRID ---
var collisionGrid = null;

// ============================================================
// COLLISION SYSTEM — set to false to disable entirely
// ============================================================
const COLLISION_ENABLED = true;
const COLLISION_RADIUS = 22;       // personal space radius (px)
const COLLISION_PUSH = 1.4;        // steering strength when walking
const COLLISION_SPOT_RADIUS = 24;  // min distance between agents at interaction spots

// ============================================================
// COLLISION HELPERS (only active when COLLISION_ENABLED = true)
// ============================================================
function isSpotOccupied(x, y, excludeId) {
    if (!COLLISION_ENABLED) return false;
    for (let i = 0; i < agents.length; i++) {
        const a = agents[i];
        if (a.id === excludeId) continue;
        const dx = a.x - x, dy = a.y - y;
        if (Math.sqrt(dx * dx + dy * dy) < COLLISION_SPOT_RADIUS) return true;
        // Also check targets (agents heading there)
        const dtx = a.targetX - x, dty = a.targetY - y;
        if (Math.sqrt(dtx * dtx + dty * dty) < COLLISION_SPOT_RADIUS) return true;
    }
    return false;
}

function findOpenSpot(spots, excludeId, propX, propY) {
    // spots: array of {x, y, ...} or {x, y} coords
    // Returns first unoccupied spot, or the least crowded one
    if (!COLLISION_ENABLED) return spots[Math.floor(Math.random() * spots.length)];
    const open = spots.filter(s => !isSpotOccupied(propX ? s[propX] : s.x, propY ? s[propY] : s.y, excludeId));
    if (open.length > 0) return open[Math.floor(Math.random() * open.length)];
    return null; // all spots taken
}

// Generic per-object service queues. Any furniture/action spot can opt in by
// setting `queue: true` or `queue: { positions: [...] }` in FURNITURE_ACTIONS.
// The first queue entry owns the service spot; waiting entries map to numbered
// queue positions 1, 2, 3 before overflowing by the same spacing. Removing the
// queue field or setting it false unapplies the system for that object/action.
var OBJECT_SERVICE_QUEUES = {};
var DEFAULT_OBJECT_QUEUE_POSITIONS = [
    { x: 0, y: 30, slot: 1 },
    { x: 0, y: 60, slot: 2 },
    { x: 0, y: 90, slot: 3 }
];
var DEFAULT_OBJECT_QUEUE_SPACING = { x: 0, y: 30 };

function normalizeObjectQueuePosition(pos, fallbackSlot) {
    pos = pos || {};
    return {
        x: pos.x !== undefined ? pos.x : (pos.dx !== undefined ? pos.dx : 0),
        y: pos.y !== undefined ? pos.y : (pos.dy !== undefined ? pos.dy : DEFAULT_OBJECT_QUEUE_SPACING.y * fallbackSlot),
        slot: pos.slot || pos.queueSlot || fallbackSlot,
        faceDir: pos.faceDir
    };
}

function getObjectQueueConfig(target) {
    if (!target) return null;
    var queueCfg = target.queueConfig;
    if (queueCfg === undefined && target.furnitureType && FURNITURE_ACTIONS[target.furnitureType]) {
        queueCfg = FURNITURE_ACTIONS[target.furnitureType].queue;
    }
    if (!queueCfg) return null;
    if (queueCfg === true) queueCfg = {};
    var rawPositions = queueCfg.positions || queueCfg.slots || queueCfg.queuePositions || DEFAULT_OBJECT_QUEUE_POSITIONS;
    var positions = [];
    for (var i = 0; i < rawPositions.length; i++) {
        positions.push(normalizeObjectQueuePosition(rawPositions[i], i + 1));
    }
    if (positions.length === 0) positions = DEFAULT_OBJECT_QUEUE_POSITIONS.slice();
    return {
        positions: positions,
        spacingX: queueCfg.spacingX !== undefined ? queueCfg.spacingX : (queueCfg.dx !== undefined ? queueCfg.dx : DEFAULT_OBJECT_QUEUE_SPACING.x),
        spacingY: queueCfg.spacingY !== undefined ? queueCfg.spacingY : (queueCfg.dy !== undefined ? queueCfg.dy : DEFAULT_OBJECT_QUEUE_SPACING.y),
        maxWaiters: queueCfg.maxWaiters || queueCfg.maxQueue || null,
        label: queueCfg.label || target.label || target.furnitureType || target.action || 'object'
    };
}

function getObjectQueueKey(target) {
    if (!target) return null;
    if (target.queueKey) return target.queueKey;
    var type = target.furnitureType || target.type || target.action || 'object';
    var id = target.furnitureId || (Math.round(target.x) + ',' + Math.round(target.y));
    return type + ':' + id;
}

function getObjectQueueAgent(agentId) {
    if (typeof agentMap !== 'undefined' && agentMap && agentMap[agentId]) return agentMap[agentId];
    if (typeof agents === 'undefined' || !agents) return null;
    for (var i = 0; i < agents.length; i++) {
        if (agents[i].id === agentId) return agents[i];
    }
    return null;
}

function isObjectServiceActionMatch(agentAction, targetAction) {
    if (!agentAction || !targetAction) return false;
    if (agentAction === targetAction) return true;
    var equivalents = {
        drink: ['get_water'],
        get_water: ['drink'],
        coffee: ['make_coffee'],
        make_coffee: ['coffee'],
        vend: ['get_snack'],
        get_snack: ['vend'],
        microwave: ['make_food'],
        toaster: ['make_food'],
        toast: ['make_food'],
        make_food: ['microwave', 'toaster', 'toast']
    };
    return !!(equivalents[agentAction] && equivalents[agentAction].indexOf(targetAction) !== -1);
}

function findActiveObjectServiceAgent(target, action, excludeId) {
    if (!target || typeof agents === 'undefined' || !agents) return null;
    for (var i = 0; i < agents.length; i++) {
        var a = agents[i];
        if (!a || a.id === excludeId) continue;
        if (a.objectQueueKey === getObjectQueueKey(target)) continue;
        if (!isObjectServiceActionMatch(a.idleAction, action || target.action)) continue;
        var atServiceSpot = Math.abs(a.x - target.x) < 8 && Math.abs(a.y - target.y) < 8;
        var headedToServiceSpot = Math.abs(a.targetX - target.x) < 8 && Math.abs(a.targetY - target.y) < 8;
        if (atServiceSpot || headedToServiceSpot) return a;
    }
    return null;
}

function seedObjectServiceQueueFromActiveAgent(queue, target, opts, queueConfig, key) {
    if (!queue || queue.entries.length > 0) return;
    var action = opts.action || target.idleAction || target.action;
    var activeAgent = findActiveObjectServiceAgent(target, action, opts.excludeAgentId);
    if (!activeAgent) return;
    if (activeAgent.objectQueueKey && activeAgent.objectQueueKey !== key) {
        releaseObjectServiceQueueForAgent(activeAgent, 'queue-key-merge');
    }
    queue.entries.push({
        agentId: activeAgent.id,
        target: target,
        action: action || activeAgent.idleAction,
        serviceTicks: activeAgent.idleReturnTimer || opts.serviceTicks || 600,
        faceDir: activeAgent.idleFaceDir !== undefined && activeAgent.idleFaceDir !== null ? activeAgent.idleFaceDir : (opts.faceDir !== undefined ? opts.faceDir : -1),
        queueConfig: queueConfig,
        startIntent: null,
        started: true,
        startIntentShown: true
    });
    activeAgent.objectQueueKey = key;
    activeAgent.objectQueueAction = action || activeAgent.idleAction;
    activeAgent.objectQueueTarget = target;
    activeAgent.objectQueueSlot = 0;
    queue.activeAgentId = activeAgent.id;
}

function compactObjectServiceQueue(queue) {
    queue.entries = queue.entries.filter(function(entry) {
        var agent = getObjectQueueAgent(entry.agentId);
        return agent && agent.objectQueueKey === queue.key;
    });
    queue.activeAgentId = queue.entries.length ? queue.entries[0].agentId : null;
    return queue.entries.length > 0;
}

function getObjectQueueEntry(queue, agentId) {
    if (!queue) return null;
    for (var i = 0; i < queue.entries.length; i++) {
        if (queue.entries[i].agentId === agentId) return queue.entries[i];
    }
    return null;
}

function getObjectQueueWaitPosition(entry, waitingIndex) {
    var cfg = entry.queueConfig || getObjectQueueConfig(entry.target) || { positions: DEFAULT_OBJECT_QUEUE_POSITIONS, spacingX: 0, spacingY: 30 };
    var positions = cfg.positions && cfg.positions.length ? cfg.positions : DEFAULT_OBJECT_QUEUE_POSITIONS;
    var pos = positions[waitingIndex];
    if (!pos) {
        var last = positions[positions.length - 1] || { x: 0, y: 0, slot: 0 };
        var overflow = waitingIndex - positions.length + 1;
        pos = {
            x: (last.x || 0) + (cfg.spacingX || 0) * overflow,
            y: (last.y || 0) + (cfg.spacingY || DEFAULT_OBJECT_QUEUE_SPACING.y) * overflow,
            slot: (last.slot || positions.length) + overflow,
            faceDir: last.faceDir
        };
    }
    return pos;
}

function setObjectQueueAgentDestination(agent, entry, index) {
    var tx = entry.target.x;
    var ty = entry.target.y;
    var slot = 0;
    var slotFaceDir;
    if (index > 0) {
        var waitPos = getObjectQueueWaitPosition(entry, index - 1);
        tx += waitPos.x || 0;
        ty += waitPos.y || 0;
        slot = waitPos.slot || index;
        slotFaceDir = waitPos.faceDir;
    }
    if (agent.targetX !== tx || agent.targetY !== ty) {
        agent.targetX = tx;
        agent.targetY = ty;
    }
    agent.idleFaceDir = slotFaceDir !== undefined ? slotFaceDir : entry.faceDir;
    agent.objectQueueSlot = slot;
    if (index === 0 && entry.started) {
        agent.idleAction = entry.action;
    } else {
        agent.idleAction = 'object_queue_wait';
        agent.idleReturnTimer = 0;
    }
}

function updateObjectServiceQueue(queue) {
    if (!queue || !compactObjectServiceQueue(queue)) {
        if (queue) delete OBJECT_SERVICE_QUEUES[queue.key];
        return;
    }
    for (var i = 0; i < queue.entries.length; i++) {
        var entry = queue.entries[i];
        var agent = getObjectQueueAgent(entry.agentId);
        if (!agent) continue;
        setObjectQueueAgentDestination(agent, entry, i);
    }
}

function startObjectServiceIfReady(agent) {
    if (!agent || !agent.objectQueueKey) return false;
    var queue = OBJECT_SERVICE_QUEUES[agent.objectQueueKey];
    if (!queue) return false;
    updateObjectServiceQueue(queue);
    if (queue.activeAgentId !== agent.id) return false;
    var entry = getObjectQueueEntry(queue, agent.id);
    if (!entry || entry.started) return false;
    var atServiceSpot = Math.abs(agent.x - entry.target.x) < 4 && Math.abs(agent.y - entry.target.y) < 4;
    if (!atServiceSpot) return false;
    entry.started = true;
    agent.idleAction = entry.action;
    agent.idleReturnTimer = entry.serviceTicks || (600 + Math.floor(Math.random() * 800));
    agent.interactTimer = 0;
    if (entry.faceDir !== null && entry.faceDir !== undefined) agent.faceDir = entry.faceDir;
    if (entry.startIntent && !entry.startIntentShown) {
        agent.addIntent(entry.startIntent);
        entry.startIntentShown = true;
    }
    return true;
}

function enqueueAgentForObjectService(agent, target, opts) {
    if (!agent || !target) return false;
    opts = opts || {};
    opts.excludeAgentId = agent.id;
    var queueConfig = getObjectQueueConfig(target);
    if (!queueConfig) return false;
    if (agent.objectQueueKey) releaseObjectServiceQueueForAgent(agent, 'requeue');
    var key = getObjectQueueKey(target);
    var queue = OBJECT_SERVICE_QUEUES[key];
    if (!queue) queue = OBJECT_SERVICE_QUEUES[key] = { key: key, activeAgentId: null, entries: [] };
    seedObjectServiceQueueFromActiveAgent(queue, target, opts, queueConfig, key);
    if (queueConfig.maxWaiters !== null && queue.entries.length >= queueConfig.maxWaiters + 1) return false;
    queue.entries.push({
        agentId: agent.id,
        target: target,
        action: opts.action || target.idleAction || target.action,
        serviceTicks: opts.serviceTicks || 600,
        faceDir: opts.faceDir !== undefined ? opts.faceDir : -1,
        queueConfig: queueConfig,
        startIntent: opts.startIntent || null,
        started: false,
        startIntentShown: false
    });
    agent.objectQueueKey = key;
    agent.objectQueueAction = opts.action || target.action;
    agent.objectQueueTarget = target;
    agent.idleReturnTimer = 0;
    updateObjectServiceQueue(queue);
    return true;
}

function releaseObjectServiceQueueForAgent(agent, reason) {
    if (!agent || !agent.objectQueueKey) return;
    var key = agent.objectQueueKey;
    var queue = OBJECT_SERVICE_QUEUES[key];
    agent.objectQueueKey = null;
    agent.objectQueueAction = null;
    agent.objectQueueTarget = null;
    agent.objectQueueSlot = null;
    if (!queue) return;
    queue.entries = queue.entries.filter(function(entry) { return entry.agentId !== agent.id; });
    if (queue.entries.length === 0) {
        delete OBJECT_SERVICE_QUEUES[key];
    } else {
        queue.activeAgentId = queue.entries[0].agentId;
        updateObjectServiceQueue(queue);
    }
}

// Dynamic canvas sizing — match display size, no stretching
let displayW = 1000, displayH = 700;

let _resizeRAF = null;
function resizeCanvas(force) {
    // Read size from the wrapper, not the canvas itself, to avoid feedback loops
    const wrapper = canvas.parentElement;
    if (!wrapper) return;
    const newW = wrapper.clientWidth;
    const newH = wrapper.clientHeight;
    if (newW < 1 || newH < 1) return;
    if (!force && newW === Math.round(displayW) && newH === Math.round(displayH)) return;
    displayW = newW;
    displayH = newH;
    canvas.width = displayW * DPR;
    canvas.height = displayH * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
resizeCanvas();
window.addEventListener('resize', function() {
    if (_resizeRAF) cancelAnimationFrame(_resizeRAF);
    _resizeRAF = requestAnimationFrame(resizeCanvas);
});

// --- CAMERA ---
const camera = { x: 0, y: 0, zoom: 1 };
const CAM_ZOOM_MIN = 0.5;
const CAM_ZOOM_MAX = 3.0;
let _isPanning = false;
let _panStartX = 0, _panStartY = 0;
let _camStartX = 0, _camStartY = 0;
let _pinchStartDist = 0, _pinchStartZoom = 1;
let _lastTapTime = 0;

// Convert screen (CSS) coords to world coords
function screenToWorld(sx, sy) {
    const rect = canvas.getBoundingClientRect();
    // CSS pixel to canvas logical coord
    const cx = (sx - rect.left) * (displayW / rect.width);
    const cy = (sy - rect.top) * (displayH / rect.height);
    // Reverse camera transform
    const base = getBaseScale();
    const totalZoom = base * camera.zoom;
    const wx = (cx - displayW / 2) / totalZoom + W / 2 + camera.x;
    const wy = (cy - displayH / 2) / totalZoom + H / 2 + camera.y;
    return { x: wx, y: wy };
}

function clampCamera() {
    const base = getBaseScale();
    const totalZoom = base * camera.zoom;
    const halfViewW = displayW / totalZoom / 2;
    const halfViewH = displayH / totalZoom / 2;
    const CAM_EDGE_BUFFER = TILE * 3; // allow panning 3 tiles past canvas edge
    const maxX = Math.max(0, W / 2 - halfViewW + CAM_EDGE_BUFFER);
    const maxY = Math.max(0, H / 2 - halfViewH + CAM_EDGE_BUFFER);
    camera.x = Math.max(-maxX, Math.min(maxX, camera.x));
    camera.y = Math.max(-maxY, Math.min(maxY, camera.y));
}

let _zoomIndicatorTimer = 0;

function resetCamera() {
    camera.x = 0; camera.y = 0; camera.zoom = 1;
    _zoomIndicatorTimer = Date.now();
}

// Base scale: fit the 1000x700 world into the display without stretching
function getBaseScale() {
    return Math.max(displayW / W, displayH / H);
}

// Apply camera transform (call before drawing world objects)
function applyCameraTransform() {
    const base = getBaseScale();
    ctx.translate(displayW / 2, displayH / 2);
    ctx.scale(base * camera.zoom, base * camera.zoom);
    ctx.translate(-W / 2 - camera.x, -H / 2 - camera.y);
}

// --- MOUSE/TOUCH: PAN & ZOOM ---
canvas.addEventListener('wheel', function(e) {
    e.preventDefault();
    // Check if hovering over a chat bubble — scroll it instead of zooming
    const world = screenToWorld(e.clientX, e.clientY);
    for (var wi = 0; wi < renderedChatBubbles.length; wi++) {
        var wb = renderedChatBubbles[wi];
        var wr = wb.fullRect;
        if (world.x >= wr.x && world.x <= wr.x + wr.w && world.y >= wr.y && world.y <= wr.y + wr.h) {
            if (e.deltaY < 0 && wb.canScrollUp) {
                chatScrollOffset[wb.agentKey] = (chatScrollOffset[wb.agentKey] || 0) + 2;
            } else if (e.deltaY > 0 && wb.canScrollDown) {
                chatScrollOffset[wb.agentKey] = Math.max(0, (chatScrollOffset[wb.agentKey] || 0) - 2);
            }
            return;
        }
    }
    // Zoom toward pointer
    const rect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left) * (displayW / rect.width);
    const mouseY = (e.clientY - rect.top) * (displayH / rect.height);
    const oldZoom = camera.zoom;
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    camera.zoom = Math.max(CAM_ZOOM_MIN, Math.min(CAM_ZOOM_MAX, camera.zoom * zoomFactor));
    // Adjust camera so point under cursor stays fixed
    const base = getBaseScale();
    const zoomRatio = camera.zoom / oldZoom;
    const cx = displayW / 2, cy = displayH / 2;
    camera.x += (mouseX - cx) * (1 - 1 / zoomRatio) / (base * camera.zoom);
    camera.y += (mouseY - cy) * (1 - 1 / zoomRatio) / (base * camera.zoom);
    clampCamera();
    _zoomIndicatorTimer = Date.now();
}, { passive: false });

canvas.addEventListener('mousedown', function(e) {
    if (e.button === 0) { // left click
        _isPanning = true;
        _panStartX = e.clientX;
        _panStartY = e.clientY;
        _camStartX = camera.x;
        _camStartY = camera.y;
        _clickStartX = e.clientX;
        _clickStartY = e.clientY;
    }
});

window.addEventListener('mousemove', function(e) {
    if (!_isPanning) return;
    const rect = canvas.getBoundingClientRect();
    const base = getBaseScale();
    const dx = (e.clientX - _panStartX) * (displayW / rect.width) / (base * camera.zoom);
    const dy = (e.clientY - _panStartY) * (displayH / rect.height) / (base * camera.zoom);
    camera.x = _camStartX - dx;
    camera.y = _camStartY - dy;
    clampCamera();
});

window.addEventListener('mouseup', function() {
    _isPanning = false;
});

// Track tooltip for project work indicator on chat bubbles
canvas.addEventListener('mousemove', function(e) {
    _chatTooltip = null;
    if (editMode) return;
    var world = screenToWorld(e.clientX, e.clientY);
    for (var ti = 0; ti < renderedChatBubbles.length; ti++) {
        var tb = renderedChatBubbles[ti];
        if (tb.projIndicator) {
            var pi = tb.projIndicator;
            if (world.x >= pi.x && world.x <= pi.x + pi.w && world.y >= pi.y && world.y <= pi.h + pi.y) {
                var label = '📋 ' + (pi.info.taskTitle || pi.info.phase || 'Project work');
                _chatTooltip = { x: pi.x, y: pi.y + pi.h + 3, text: label };
                break;
            }
        }
    }
}, { passive: true });

canvas.addEventListener('mousemove', function(e) {
    _floorWindowTooltip = null;
    var world = screenToWorld(e.clientX, e.clientY);
    var item = _findFurnitureAt(world.x, world.y);
    if (!item || item.type !== 'floorWindow') return;
    var run = _getConnectedFloorWindowRun(item);
    _floorWindowTooltip = {
        x: Math.max(0, Math.min(W - 150, world.x + 10)),
        y: Math.max(0, run.y - 44),
        lines: _getFloorWindowWeatherTooltipLines()
    };
}, { passive: true });

// Touch: pan with one finger, pinch-zoom with two
canvas.addEventListener('touchstart', function(e) {
    if (e.touches.length === 1) {
        _isPanning = true;
        _panStartX = e.touches[0].clientX;
        _panStartY = e.touches[0].clientY;
        _camStartX = camera.x;
        _camStartY = camera.y;
        _touchStartX2 = e.touches[0].clientX;
        _touchStartY2 = e.touches[0].clientY;
        // Double-tap to reset
        const now = Date.now();
        if (now - _lastTapTime < 300) {
            resetCamera();
            _isPanning = false;
        }
        _lastTapTime = now;
    } else if (e.touches.length === 2) {
        _isPanning = false;
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        _pinchStartDist = Math.sqrt(dx * dx + dy * dy);
        _pinchStartZoom = camera.zoom;
    }
}, { passive: true });

canvas.addEventListener('touchmove', function(e) {
    e.preventDefault();
    if (e.touches.length === 1 && _isPanning) {
        const rect = canvas.getBoundingClientRect();
        const base = getBaseScale();
        const dx = (e.touches[0].clientX - _panStartX) * (displayW / rect.width) / (base * camera.zoom);
        const dy = (e.touches[0].clientY - _panStartY) * (displayH / rect.height) / (base * camera.zoom);
        camera.x = _camStartX - dx;
        camera.y = _camStartY - dy;
        clampCamera();
    } else if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        camera.zoom = Math.max(CAM_ZOOM_MIN, Math.min(CAM_ZOOM_MAX, _pinchStartZoom * (dist / _pinchStartDist)));
        clampCamera();
        _zoomIndicatorTimer = Date.now();
    }
}, { passive: false });

canvas.addEventListener('touchend', function() {
    _isPanning = false;
});

// --- LOCATIONS ---
const LOCATIONS = {
    pqDesks: [
        { x: 140, y: 220 },  // Moe
        { x: 140, y: 340 },  // Calen
        { x: 280, y: 220 },  // Mike
        { x: 280, y: 340 },  // Cash
        { x: 280, y: 460 },  // Alan
        { x: 140, y: 460 },  // Filer
    ],
    engDesks: [
        { x: 720, y: 220 },  // Flo
        { x: 720, y: 340 },  // Mark
        { x: 860, y: 220 },  // Ana
        { x: 860, y: 340 },  // Plan
    ],
    bossDesk: { x: 500, y: 180 },
    centerDesk: { x: 500, y: 340 },
    centerDesk2: { x: 600, y: 340 },
    centerDesk3: { x: 400, y: 340 },
    forgeDesk: { x: 460, y: 620 },
    meeting: { x: 370, y: 440, w: 240, h: 120 },
    lounge: { x: 60, y: 550 },
    cooler: { x: 820, y: 540 },
    // Wander destinations for idle agents
    wanderSpots: [
        { x: 450, y: 350, label: 'hallway' },
        { x: 550, y: 350, label: 'hallway' },
        { x: 500, y: 620, label: 'entrance' },
        { x: 350, y: 300, label: 'pq-hall' },
        { x: 650, y: 300, label: 'eng-hall' },
        { x: 420, y: 600, label: 'forge-area' },
    ],
    // Detailed interaction spots
    interactions: {
        windows: [
            { x: 406, y: 100 },    // HQ left window
            { x: 594, y: 100 },    // HQ right window
        ],
        couchSeats: [
            { x: 78, y: 575, faceDir: 1 },     // back of L, top
            { x: 78, y: 598, faceDir: 1 },     // back of L, bottom
            { x: 108, y: 630, faceDir: -1 },   // bottom of L, left
            { x: 138, y: 630, faceDir: -1 },   // bottom of L, middle
            { x: 168, y: 630, faceDir: -1 },   // bottom of L, right
        ],
        bookshelf: { x: 30, y: 660 },
        tvSpot: { x: 155, y: 601, faceDir: 1 },
        vendingMachine: { x: 765, y: 634 },
        coffeeMaker: { x: 850, y: 628 },
        waterCooler: { x: 899, y: 594 },
        microwave: { x: 935, y: 636 },
        toaster: { x: 960, y: 620 },
        dartBoard: { x: 270, y: 670 },  // standing spot in front of dart board
        // ENG lounge couch (under Caltran sign)
        engCouchSeats: [
            { x: 735, y: 89, faceDir: -1 },   // left seat
            { x: 775, y: 89, faceDir: -1 },   // center-left
            { x: 815, y: 89, faceDir: -1 },   // center-right
            { x: 855, y: 89, faceDir: -1 },   // right seat
        ],
    },
};

// --- Meeting slots — derived dynamically from meeting table furniture position ---
// If a meetingTable item exists, slots are relative to its position.
// If no meetingTable exists, returns empty (agents meet at random spots instead).
function getMeetingTablePos() {
    if (typeof officeConfig !== 'undefined' && officeConfig.furniture) {
        var table = officeConfig.furniture.find(function(f) { return f.type === 'meetingTable'; });
        if (table) return { x: table.x, y: table.y, w: 240, h: 120 };
    }
    // Fallback to LOCATIONS.meeting if it exists (backward compat)
    if (LOCATIONS.meeting) return LOCATIONS.meeting;
    return null;
}

function getMeetingSlots() {
    var m = getMeetingTablePos();
    if (!m) return [];
    // 5 chairs per side, evenly spaced across 240px wide table
    return [
        { x: m.x + 27, y: m.y + 15 },    // top row
        { x: m.x + 73, y: m.y + 15 },
        { x: m.x + 120, y: m.y + 15 },
        { x: m.x + 166, y: m.y + 15 },
        { x: m.x + 213, y: m.y + 15 },
        { x: m.x + 27, y: m.y + 103 },   // bottom row
        { x: m.x + 73, y: m.y + 103 },
        { x: m.x + 120, y: m.y + 103 },
        { x: m.x + 166, y: m.y + 103 },
        { x: m.x + 213, y: m.y + 103 },
    ];
}
// Legacy constant — kept for backward compat but now calls dynamic function
var MEETING_SLOTS = getMeetingSlots();

const FUNCTIONAL_MEETING_SPACE_TYPES = ['meetingTable4', 'meetingTable6', 'meetingTable', 'meetingRoom'];

function _isFunctionalMeetingSpace(item) {
    return !!(item && FUNCTIONAL_MEETING_SPACE_TYPES.indexOf(item.type) >= 0);
}

function _meetingSpaceCapacity(item) {
    if (!item) return 0;
    if (item.type === 'meetingTable4') return 4;
    if (item.type === 'meetingTable6') return 6;
    if (item.type === 'meetingTable') return 10;
    if (item.type === 'meetingRoom') return Infinity;
    return 0;
}

function _meetingSpaceOrder(item) {
    if (!item) return 99;
    if (item.type === 'meetingTable4') return 4;
    if (item.type === 'meetingTable6') return 6;
    if (item.type === 'meetingTable') return 8;
    if (item.type === 'meetingRoom') return 10;
    return 99;
}

function _meetingSpaceDisplayName(item) {
    if (!item) return '';
    if (item.type === 'meetingTable4') return _tr('furniture_meeting_table_4');
    if (item.type === 'meetingTable6') return _tr('furniture_meeting_table_6');
    if (item.type === 'meetingTable') return _tr('furniture_meeting_table');
    if (item.type === 'meetingRoom') return _tr('furniture_meeting_room');
    return _tr('meeting');
}

function _getFunctionalMeetingSpaces() {
    if (typeof officeConfig === 'undefined' || !Array.isArray(officeConfig.furniture)) return [];
    return officeConfig.furniture
        .filter(_isFunctionalMeetingSpace)
        .slice()
        .sort(function(a, b) {
            var oa = _meetingSpaceOrder(a);
            var ob = _meetingSpaceOrder(b);
            if (oa !== ob) return oa - ob;
            var ax = Number(a.x || 0), bx = Number(b.x || 0);
            if (ax !== bx) return ax - bx;
            return Number(a.y || 0) - Number(b.y || 0);
        });
}

function _findMeetingSpaceForCount(count, occupiedSpaceIds) {
    var spaces = _getFunctionalMeetingSpaces();
    var preferred = count <= 4 ? ['meetingTable4', 'meetingTable6', 'meetingTable', 'meetingRoom'] :
        (count <= 6 ? ['meetingTable6', 'meetingTable', 'meetingRoom'] : ['meetingTable', 'meetingRoom']);
    for (var p = 0; p < preferred.length; p++) {
        for (var i = 0; i < spaces.length; i++) {
            var item = spaces[i];
            if (item.type !== preferred[p]) continue;
            if (occupiedSpaceIds && occupiedSpaceIds.has(item.id)) continue;
            if (_meetingSpaceCapacity(item) >= count) return item;
        }
    }
    return null;
}

function _meetingSpaceCenter(item) {
    var b = FURNITURE_BOUNDS[item.type] || { w: 120, h: 80 };
    return { x: item.x + b.w / 2, y: item.y + b.h / 2 };
}

function _tableSlotsForSpace(item, count) {
    var slots = [];
    if (!item) return slots;
    var center = _meetingSpaceCenter(item);
    var pushSlot = function(x, y, faceDir, isSitting) {
        slots.push({
            x: x,
            y: y,
            faceDir: faceDir,
            isSitting: isSitting !== false,
            centerX: center.x,
            centerY: center.y,
            meetingSpaceId: item.id,
            meetingSpaceType: item.type
        });
    };
    if (item.type === 'meetingTable4') {
        pushSlot(item.x + 28, item.y + 18, 2, true);
        pushSlot(item.x + 88, item.y + 18, 2, true);
        pushSlot(item.x + 28, item.y + 78, 0, true);
        pushSlot(item.x + 88, item.y + 78, 0, true);
        return slots;
    }
    if (item.type === 'meetingTable6') {
        [26, 82, 138].forEach(function(dx) { pushSlot(item.x + dx, item.y + 18, 2, true); });
        [26, 82, 138].forEach(function(dx) { pushSlot(item.x + dx, item.y + 86, 0, true); });
        return slots;
    }
    if (item.type === 'meetingTable') {
        [27, 73, 120, 166, 213].forEach(function(dx) { pushSlot(item.x + dx, item.y + 15, 2, true); });
        [27, 73, 120, 166, 213].forEach(function(dx) { pushSlot(item.x + dx, item.y + 103, 0, true); });
        return slots;
    }
    if (item.type === 'meetingRoom') {
        [56, 103, 150, 197, 244].forEach(function(dx) { pushSlot(item.x + dx, item.y + 45, 2, true); });
        [56, 103, 150, 197, 244].forEach(function(dx) { pushSlot(item.x + dx, item.y + 132, 0, true); });
        var overflow = Math.max(0, count - slots.length);
        for (var i = 0; i < overflow; i++) {
            var col = i % 6;
            var row = Math.floor(i / 6);
            pushSlot(item.x + 38 + col * 42, item.y + 160 + row * 24, 0, false);
        }
        return slots;
    }
    return slots;
}

function _buildMeetingSpaceAssignment(meeting, meetingAgents, occupiedSpaceIds) {
    var space = _findMeetingSpaceForCount(meetingAgents.length, occupiedSpaceIds);
    if (!space) return null;
    var slots = _tableSlotsForSpace(space, meetingAgents.length);
    if (!slots.length) return null;
    occupiedSpaceIds.add(space.id);
    return {
        space: space,
        slots: slots,
        slotAssignments: meetingAgents.map(function(agent, i) {
            return { agent: agent.id, slot: slots[i % slots.length] };
        })
    };
}

function _buildFallbackMeetingAssignment(meetingAgents) {
    var slots = getMeetingSlots();
    var slotAssignments = [];
    if (slots.length > 0) {
        meetingAgents.forEach(function(agent, i) {
            var slot = Object.assign({
                isSitting: true,
                centerX: getMeetingTablePos().x + 120,
                centerY: getMeetingTablePos().y + 60
            }, slots[i % slots.length]);
            slotAssignments.push({ agent: agent.id, slot: slot });
        });
    } else {
        var anchor = meetingAgents[0];
        meetingAgents.forEach(function(agent, i) {
            var angle = (i / meetingAgents.length) * Math.PI * 2;
            var slot = {
                x: anchor.x + Math.cos(angle) * 40,
                y: anchor.y + Math.sin(angle) * 40,
                isSitting: false,
                centerX: anchor.x,
                centerY: anchor.y
            };
            slotAssignments.push({ agent: agent.id, slot: slot });
        });
    }
    return { space: null, slots: slots, slotAssignments: slotAssignments };
}

function _applyGroupMeetingAssignment(meetingId, rawMeeting, meetingAgents, topic, occupiedSpaceIds) {
    var assignment = _buildMeetingSpaceAssignment(rawMeeting, meetingAgents, occupiedSpaceIds) || _buildFallbackMeetingAssignment(meetingAgents);
    meetingAgents.forEach(function(agent) {
        var assigned = assignment.slotAssignments.find(function(a) { return a.agent === agent.id; });
        var slot = assigned ? assigned.slot : { x: agent.x, y: agent.y, isSitting: false };
        var slotChanged = !agent.meetingSlot ||
            Math.abs(Number(agent.meetingSlot.x || 0) - Number(slot.x || 0)) > 1 ||
            Math.abs(Number(agent.meetingSlot.y || 0) - Number(slot.y || 0)) > 1 ||
            agent.meetingSpaceId !== (slot.meetingSpaceId || null) ||
            !!agent.isSitting !== !!slot.isSitting;
        if (agent.meetingId !== meetingId || agent.state !== 'meeting' || slotChanged) {
            agent.joinMeeting(meetingId, slot, topic);
        } else {
            agent.meetingSlot = slot;
            if (typeof slot.faceDir !== 'undefined') agent.faceDir = slot.faceDir;
        }
    });
    return assignment;
}

// --- 1-on-1 meeting positions (relative to target desk) ---
const VISIT_OFFSET = { x: -30, y: 15 };  // visitor stands beside desk

// --- MEETING SYSTEM ---
let activeMeetings = {};  // id -> { agents: [], topic, type, slotAssignments }

function _meetingAgentKeySet(agent) {
    if (!agent) return [];
    return [agent.id, agent.statusKey, agent.name].filter(Boolean).map(function(v) { return String(v); });
}

function _meetingFindAgentByKey(key) {
    if (!key) return null;
    var k = String(key);
    if (agentMap[k]) return agentMap[k];
    for (var i = 0; i < agents.length; i++) {
        var a = agents[i];
        if (a.id === k || a.statusKey === k || a.name === k) return a;
    }
    return null;
}

function _meetingAgentMatchesKey(agent, key) {
    if (!agent || !key) return false;
    var k = String(key);
    return agent.id === k || agent.statusKey === k || agent.name === k;
}

function _meetingRawActiveRecord(meetingId) {
    if (!meetingId || typeof _mtgData === 'undefined' || !_mtgData || !Array.isArray(_mtgData.active)) return null;
    for (var i = 0; i < _mtgData.active.length; i++) {
        var m = _mtgData.active[i];
        if (m && m.id === meetingId) {
            return (typeof _mtgMergeLiveMeeting === 'function') ? _mtgMergeLiveMeeting(m) : m;
        }
    }
    return null;
}

function _meetingSpeakerKeyFromRecord(record) {
    if (!record) return '';
    if (record.currentSpeaker) return String(record.currentSpeaker);
    var pending = Array.isArray(record.pendingCalls) ? record.pendingCalls : [];
    for (var i = 0; i < pending.length; i++) {
        var call = pending[i] || {};
        var speaker = call.speaker || call.agentId || call.participant || call.actorId;
        if (speaker) return String(speaker);
    }
    return '';
}

function _meetingSpeakerFor(meeting) {
    if (!meeting) return null;
    var record = _meetingRawActiveRecord(meeting.id) || meeting.raw || meeting;
    var speakerKey = _meetingSpeakerKeyFromRecord(record);
    if (!speakerKey) return null;
    var speaker = _meetingFindAgentByKey(speakerKey);
    if (!speaker || !meeting.agents || meeting.agents.indexOf(speaker) < 0) return null;
    return speaker;
}

function _meetingForAgent(agent) {
    if (!agent) return null;
    if (agent.meetingId && activeMeetings[agent.meetingId]) return activeMeetings[agent.meetingId];
    var keys = _meetingAgentKeySet(agent);
    var ids = Object.keys(activeMeetings);
    for (var i = 0; i < ids.length; i++) {
        var meeting = activeMeetings[ids[i]];
        if (!meeting || !meeting.agents) continue;
        if (meeting.agents.indexOf(agent) >= 0) return meeting;
        for (var j = 0; j < keys.length; j++) {
            if ((meeting.participantKeys || []).indexOf(keys[j]) >= 0) return meeting;
        }
    }
    return null;
}

function _meetingMotionState(agent) {
    var meeting = _meetingForAgent(agent);
    if (!meeting) return null;
    var speaker = _meetingSpeakerFor(meeting);
    if (!speaker) return { meeting: meeting, speaker: null, role: 'participant', hasSpeaker: false };
    var isSpeaker = speaker === agent || _meetingAgentMatchesKey(agent, speaker.id) || _meetingAgentMatchesKey(agent, speaker.statusKey);
    return {
        meeting: meeting,
        speaker: speaker,
        role: isSpeaker ? 'speaker' : 'listener',
        hasSpeaker: true
    };
}

function _meetingMotionDraw(agent) {
    var state = _meetingMotionState(agent);
    if (!state) return { offsetX: 0, offsetY: 0, mouth: null, hasSpeaker: false, role: 'none' };
    if (!state.hasSpeaker) {
        var slot = agent.meetingSlot || {};
        if (slot.centerX && Math.abs(slot.centerX - agent.x) > 8) agent.faceDir = slot.centerX > agent.x ? 1 : -1;
        return { offsetX: 0, offsetY: 0, mouth: null, hasSpeaker: false, role: 'participant' };
    }
    if (state.role === 'speaker') {
        return {
            offsetX: 0,
            offsetY: -0.8 + Math.sin(agent.tick * 0.22) * 0.8,
            mouth: Math.floor(agent.tick / 5) % 3 === 0 ? 'open' : Math.floor(agent.tick / 5) % 3 === 1 ? 'half' : 'closed',
            hasSpeaker: true,
            role: 'speaker'
        };
    }
    if (state.speaker && Math.abs(state.speaker.x - agent.x) > 8) {
        agent.faceDir = state.speaker.x > agent.x ? 1 : -1;
    }
    var seed = 0;
    var id = String(agent.id || agent.statusKey || '');
    for (var i = 0; i < id.length; i++) seed += id.charCodeAt(i);
    var cycle = (agent.tick + seed * 7) % 210;
    var nod = cycle < 22 ? Math.sin((cycle / 22) * Math.PI) * 3 : 0;
    var turnProgress = Math.max(0, Number(agent._meetingTurnTimer || 0)) / 24;
    var turnLean = turnProgress > 0 ? -agent.faceDir * Math.sin(turnProgress * Math.PI) * 5 : 0;
    return {
        offsetX: turnLean,
        offsetY: nod,
        mouth: null,
        hasSpeaker: true,
        role: 'listener'
    };
}

function _meetingShouldSuppressRandomTalk(agent) {
    var state = _meetingMotionState(agent);
    return !!(state && state.hasSpeaker && state.role !== 'speaker');
}

function processMeetings(meetingsData) {
    if (!meetingsData || !Array.isArray(meetingsData)) {
        // No meetings — end any active ones
        for (const mid of Object.keys(activeMeetings)) {
            endMeeting(mid);
        }
        return;
    }

    const newIds = new Set(meetingsData.map(m => m.id));

    // End meetings no longer in the data
    for (const mid of Object.keys(activeMeetings)) {
        if (!newIds.has(mid)) endMeeting(mid);
    }

    const occupiedSpaceIds = new Set();
    for (const mid of Object.keys(activeMeetings)) {
        const meeting = activeMeetings[mid];
        if (meeting && meeting.meetingSpaceId && newIds.has(mid)) occupiedSpaceIds.add(meeting.meetingSpaceId);
    }

    // Start or update meetings
    for (const m of meetingsData) {
        const participantKeys = Array.isArray(m.participants) && m.participants.length ? m.participants : (m.agents || []);
        const meetingAgents = participantKeys.map(key => agentMap[key]).filter(Boolean);
        if (meetingAgents.length < 2) continue;

        const topic = m.topic || 'Discussion';
        const purpose = m.purpose || topic;
        const type = m.type || (meetingAgents.length <= 2 ? '1on1' : 'group');
        const existing = activeMeetings[m.id];
        if (existing) {
            existing.agents = meetingAgents;
            existing.participantKeys = participantKeys;
            existing.raw = m;
            existing.topic = topic;
            existing.purpose = purpose;
            existing.type = type;
            if (type === '1on1' && meetingAgents.length === 2) {
                if (existing.meetingSpaceId) {
                    occupiedSpaceIds.delete(existing.meetingSpaceId);
                    existing.meetingSpaceId = null;
                    existing.meetingSpaceType = null;
                    existing.meetingSpaceCapacity = null;
                    existing.meetingSpaceName = '';
                    existing.slotAssignments = [];
                }
                const visitor = meetingAgents[0];
                const host = meetingAgents[1];
                if (visitor.state !== 'visiting' || visitor.visitTarget !== host.id || host.state !== 'visiting' || host.visitTarget !== visitor.id) {
                    visitor.visitAgent(host, topic);
                    host.state = 'visiting';
                    host.visitTarget = visitor.id;
                    host.addIntent(`Meeting with ${visitor.name}: ${topic}`);
                }
            } else {
                if (existing.meetingSpaceId) occupiedSpaceIds.delete(existing.meetingSpaceId);
                const assignment = _applyGroupMeetingAssignment(m.id, m, meetingAgents, topic, occupiedSpaceIds);
                existing.slotAssignments = assignment.slotAssignments;
                existing.meetingSpaceId = assignment.space ? assignment.space.id : null;
                existing.meetingSpaceType = assignment.space ? assignment.space.type : null;
                existing.meetingSpaceCapacity = assignment.space ? _meetingSpaceCapacity(assignment.space) : null;
                existing.meetingSpaceName = assignment.space ? _meetingSpaceDisplayName(assignment.space) : '';
            }
            continue;
        }

        if (type === '1on1' && meetingAgents.length === 2) {
            // 1:1 — first agent visits second agent's desk
            const visitor = meetingAgents[0];
            const host = meetingAgents[1];
            visitor.visitAgent(host, topic);
            host.state = 'visiting';
            host.visitTarget = visitor.id;
            host.addIntent(`Meeting with ${visitor.name}: ${topic}`);
            activeMeetings[m.id] = { id: m.id, agents: meetingAgents, participantKeys, raw: m, topic, purpose, type, organizer: m.organizer || participantKeys[0] || '', kind: m.kind || 'discussion', rules: m.rules || null };
            addGlobalLog(`🤝 ${visitor.name} → ${host.name}: ${topic}`);
        } else {
            // Group meeting — prefer functional meeting spaces, then fall back to the legacy meeting table/cluster behavior.
            const assignment = _applyGroupMeetingAssignment(m.id, m, meetingAgents, topic, occupiedSpaceIds);
            activeMeetings[m.id] = { id: m.id, agents: meetingAgents, participantKeys, raw: m, topic, purpose, type, organizer: m.organizer || participantKeys[0] || '', kind: m.kind || 'discussion', rules: m.rules || null, slotAssignments: assignment.slotAssignments, meetingSpaceId: assignment.space ? assignment.space.id : null, meetingSpaceType: assignment.space ? assignment.space.type : null, meetingSpaceCapacity: assignment.space ? _meetingSpaceCapacity(assignment.space) : null, meetingSpaceName: assignment.space ? _meetingSpaceDisplayName(assignment.space) : '' };
            addGlobalLog(`📊 ` + (typeof i18n !== 'undefined' ? i18n.t('meeting_prefix') : 'Meeting') + `: ${meetingAgents.map(a => a.name).join(', ')} — ${topic}`);
        }
    }
}

function endMeeting(meetingId) {
    const meeting = activeMeetings[meetingId];
    if (!meeting) return;
    meeting.agents.forEach(agent => {
        if (agent.meetingId === meetingId || agent.state === 'visiting') {
            agent.leaveMeeting();
        }
    });
    delete activeMeetings[meetingId];
    addGlobalLog(`✅ ` + (typeof i18n !== 'undefined' ? i18n.t('meeting_ended') : 'Meeting ended') + `: ${meeting.topic}`);
}

// --- STATUS POLLING ---
async function pollStatus() {
    try {
        const res = await fetch('/status');
        if (!res.ok) throw new Error();
        const data = await res.json();

        // Process meetings first
        processMeetings(data._meetings);

        agents.forEach(agent => {
            const entry = data[agent.statusKey];
            if (!entry) return;

            // Don't override state if agent is in an active meeting
            if (agent.meetingId || agent.state === 'visiting') {
                // Still update bubbles though
            } else {
                const newState = entry.state || 'idle';
                const newTask = entry.task || '';
                if (newState !== agent.state || newTask !== agent.task) {
                    agent.task = newTask;
                    if (newState !== agent.state) {
                        agent.moveTo(newState);
                        addGlobalLog(`${agent.emoji} ${agent.name}: ${newState}${newTask ? ' — ' + newTask : ''}`);
                    }
                }
            }

            // Thought bubble
            const newThought = entry.thought || '';
            if (newThought && newThought !== agent.lastThought) {
                agent.thought = newThought;
                agent.lastThought = newThought;
                agent.thoughtChars = 0;
                agent.thoughtAge = 0;
                agent.thoughtUpdatedAt = Date.now();
                // Auto-expand if minimized
                getBubbleMinState(agent).thought = false;
                addGlobalLog(`💭 ${agent.name} ${(typeof i18n !== 'undefined' ? i18n.t('chat_thinking') : 'Thinking')}: ${newThought.substring(0, 40)}...`);
            } else if (!newThought && agent.thought) {
                agent.thought = '';
            }

            // Speech bubble
            const newSpeech = entry.speech || '';
            const newTarget = entry.speechTarget || '';
            if (newSpeech && newSpeech !== agent.speech) {
                agent.speech = newSpeech;
                agent.speechTarget = newTarget;
                agent.lastSpeech = newSpeech;
                agent.lastSpeechTarget = newTarget;
                agent.speechChars = 0;
                agent.speechAge = 0;
                agent.talkTimer = 60;
                // Auto-expand if minimized
                getBubbleMinState(agent).speech = false;
                addGlobalLog(`💬 ${agent.name}${newTarget ? ' → ' + newTarget : ''}: ${newSpeech.substring(0, 40)}...`);
            } else if (!newSpeech && agent.speech) {
                agent.speech = '';
                agent.speechTarget = '';
            }

            // Notification + Task I/O
            if (entry.notify) {
                if (!agent.notify && !dismissedNotify.has(agent.statusKey)) {
                    agent.notify = true;
                    addGlobalLog(`🔔 ${agent.name} ` + (typeof i18n !== 'undefined' ? i18n.t('has_response') : 'has a response') + `!`);
                }
            } else {
                // Server confirmed cleared — remove from dismissed set
                agent.notify = false;
                dismissedNotify.delete(agent.statusKey);
            }
            if (entry.lastInput) agent.lastInput = entry.lastInput;
            if (entry.lastOutput) agent.lastOutput = entry.lastOutput;
        });
    } catch (e) { /* Status unavailable */ }
}
setInterval(pollStatus, 5000);
pollStatus();

// --- GLOBAL LOG (persisted to localStorage) ---
function _saveLog() {
    const list = document.getElementById('log-list');
    const entries = [];
    for (const li of list.children) entries.push(li.textContent);
    try { localStorage.setItem('office-activity-log', JSON.stringify(entries.slice(0, 100))); } catch(e) {}
}
function _restoreLog() {
    try {
        const entries = JSON.parse(localStorage.getItem('office-activity-log') || '[]');
        if (!entries.length) return;
        const list = document.getElementById('log-list');
        list.innerHTML = '';
        for (const text of entries) {
            const li = document.createElement('li');
            li.textContent = text;
            list.appendChild(li);
        }
    } catch(e) {}
}
_restoreLog();

function addGlobalLog(msg) {
    const list = document.getElementById('log-list');
    const li = document.createElement('li');
    li.textContent = `[${timeStr()}] ${msg}`;
    list.prepend(li);
    while (list.children.length > 100) list.removeChild(list.lastChild);
    _saveLog();
}
