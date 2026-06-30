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

// --- EDIT MODE STATE ---
var editMode = false;
var editHoverTile = null; // {tx, ty} tile coords under mouse
var _floorEditMode = false; // separate mode for floor tile editing

// --- MULTI-SELECT (marquee) ---
var _multiSelected = []; // array of furniture ids
var _marqueeStart = null; // {x, y} world coords
var _marqueeEnd = null;
var _multiDragging = false;
var _multiDragStart = null; // {x, y}

// --- SNAP ZONE SYSTEM (5 zones per tile) ---
// 4 quadrants + center. Items snap to zone centers, staying INSIDE the tile.
var activeSnapZone = 'center'; // 'center' | 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
const SNAP_ZONES = {
    'center':       { ox: 0.50, oy: 0.50, key: 'snap_center' },
    'top-left':     { ox: 0.25, oy: 0.25, key: 'snap_top_left' },
    'top-right':    { ox: 0.75, oy: 0.25, key: 'snap_top_right' },
    'bottom-left':  { ox: 0.25, oy: 0.75, key: 'snap_bottom_left' },
    'bottom-right': { ox: 0.75, oy: 0.75, key: 'snap_bottom_right' },
};

// --- UNDO / SAVE SYSTEM ---
var _undoStack = [];
var _hasUnsavedChanges = false;
const MAX_UNDO = 30;

function _pushUndo() {
    _undoStack.push(JSON.stringify(officeConfig));
    if (_undoStack.length > MAX_UNDO) _undoStack.shift();
    _hasUnsavedChanges = true;
    _updateSaveUndoButtons();
}

function undoEdit() {
    if (_undoStack.length === 0) return;
    var prev = JSON.parse(_undoStack.pop());
    officeConfig.walls = prev.walls;
    officeConfig.floor = prev.floor;
    officeConfig.furniture = prev.furniture;
    W = prev.canvasWidth || W;
    H = prev.canvasHeight || H;
    officeConfig.canvasWidth = W;
    officeConfig.canvasHeight = H;
    getInteractionSpots();
    if (!officeConfig.walls.interior) officeConfig.walls.interior = [];
    buildCollisionGrid();
    if (typeof _refreshWallSectionButtons === 'function') _refreshWallSectionButtons();
    _hasUnsavedChanges = _undoStack.length > 0;
    _updateSaveUndoButtons();
}

function saveEdits() {
    saveOfficeConfig();
    _hasUnsavedChanges = false;
    _undoStack = [];
    _updateSaveUndoButtons();
}

function _updateSaveUndoButtons() {
    var saveBtn = document.getElementById('btn-save-edits');
    var undoBtn = document.getElementById('btn-undo-edit');
    if (saveBtn) {
        saveBtn.disabled = !_hasUnsavedChanges;
        saveBtn.style.opacity = _hasUnsavedChanges ? '1' : '0.4';
    }
    if (undoBtn) {
        undoBtn.disabled = _undoStack.length === 0;
        undoBtn.style.opacity = _undoStack.length > 0 ? '1' : '0.4';
    }
}

// --- FURNITURE EDITOR CONSTANTS ---
// FURNITURE_BOUNDS: actual visual size (w x h) + origin offset (ox, oy).
// ox, oy = where the draw function's (x,y) sits relative to the item's TOP-LEFT corner.
//   ox:0, oy:0 = draw function uses (x,y) as top-left (default)
//   ox:0.5, oy:0.5 = draw function uses (x,y) as center (e.g. desk with translate)
//   ox:0.5, oy:0 = draw function uses (x,y) as center-top
const FURNITURE_BOUNDS = {
    'desk':          { w: 72,  h: 76,  ox: 0.5,  oy: 0.66 },  // translate(x,y), visual from -36,-50 to 36,26 → origin at center-ish
    'bossDesk':      { w: 130, h: 90,  ox: 0.5,  oy: 0.5  },  // executive desk, centered origin
    'trashCan':      { w: 14,  h: 14,  ox: 0.5,  oy: 0    },  // (x,y)=center-top, ellipse ±7
    'filingCabinet': { w: 28,  h: 55,  ox: 0,    oy: 0    },  // top-left
    'whiteboard':    { w: 28,  h: 43,  ox: 0,    oy: 0    },  // top-left
    'plant':         { w: 18,  h: 26,  ox: 0,    oy: 0.23 },  // leaves start above (x,y)
    'tallPlant':     { w: 22,  h: 58,  ox: 0.09, oy: 0.17 },  // pot at y+28, leaves above
    'meetingTable':  { w: 240, h: 120, ox: 0,    oy: 0    },
    'meetingTable4': { w: 116, h: 96,  ox: 0,    oy: 0    },
    'meetingTable6': { w: 164, h: 104, ox: 0,    oy: 0    },
    'meetingRoom':   { w: 300, h: 180, ox: 0,    oy: 0    },
    'lounge':        { w: 200, h: 140, ox: 0,    oy: 0    },
    'breakArea':     { w: 240, h: 130, ox: 0,    oy: 0    },
    'engLounge':     { w: 168, h: 38,  ox: 0,    oy: 0    },
    'pingPongTable': { w: 80,  h: 48,  ox: 0.5,  oy: 0.5  },  // translate-style, draws ±40,±24
    'dartBoard':     { w: 36,  h: 52,  ox: 0.5,  oy: 0.0  },  // (x,y)=top-center, legs go down
    'vendingMachine':{ w: 45,  h: 75,  ox: 0,    oy: 0    },  // top-left
    'waterCooler':   { w: 28,  h: 48,  ox: 0.5,  oy: 0.08 },  // (x,y) center ref, body -14..14, legs to y+42
    'coffeeMaker':   { w: 24,  h: 22,  ox: 0,    oy: 0    },
    'microwave':     { w: 30,  h: 24,  ox: 0,    oy: 0    },
    'toaster':       { w: 18,  h: 16,  ox: 0,    oy: 0    },
    'window':        { w: 44,  h: 52,  ox: 0.09, oy: 0.08 },  // frame extends beyond glass
    'interactiveWindow': { w: 44, h: 52, ox: 0.09, oy: 0.08 },  // interactive window with weather/sun settings
    'floorWindow':   { w: 80,  h: 80,  ox: 0,    oy: 0    },  // 2x2 frameless floor window, top-wall mounted
    'clock':         { w: 28,  h: 28,  ox: 0.5,  oy: 0.5  },  // (x,y)=center, radius 14
    'bookshelf':     { w: 50,  h: 80,  ox: 0,    oy: 0    },  // top-left, tall bookshelf
    'functionalBookshelf': { w: 50, h: 80, ox: 0, oy: 0 },    // top-left, clickable archive bookshelf
    'couch':         { w: 160, h: 80,  ox: 0,    oy: 0    },  // L-shaped couch (4×1 tiles + 1×1 daybed)
    'endTable':      { w: 20,  h: 20,  ox: 0,    oy: 0    },  // small decor table with plant
    'coffeeTable':   { w: 64,  h: 34,  ox: 0,    oy: 0    },
    'tv':            { w: 50,  h: 34,  ox: 0,    oy: 0    },
    'kitchenCounter':{ w: 72,  h: 34,  ox: 0,    oy: 0    },
    'branchSign':    { w: 160, h: 24,  ox: 0.5,  oy: 0.5, noCollision: true },  // text label, no collision
    'textLabel':     { w: 120, h: 20,  ox: 0.5,  oy: 0.5, noCollision: true },  // custom text label
    'floorLamp':     { w: 16,  h: 40,  ox: 0.5,  oy: 0.8  },  // standing lamp
};

const CATALOG_CATEGORIES = [
    { key: 'catalog_office', items: [
        { type: 'desk',          key: 'furniture_desk',           icon: '🖥️' },
        { type: 'bossDesk',      key: 'furniture_boss_desk',      icon: '💼' },
        { type: 'trashCan',      key: 'furniture_trash_can',      icon: '🗑️' },
        { type: 'filingCabinet', key: 'furniture_filing_cabinet', icon: '🗂️' },
        { type: 'whiteboard',    key: 'furniture_whiteboard',     icon: '📋' },
    ]},
    { key: 'catalog_comfort', items: [
        { type: 'couch',      key: 'furniture_l_couch',         icon: '🛋️' },
        { type: 'engLounge',  key: 'furniture_straight_couch',  icon: '🪑' },
        { type: 'coffeeTable',key: 'furniture_coffee_table',    icon: '☕' },
        { type: 'tv',         key: 'furniture_tv',              icon: '📺' },
        { type: 'bookshelf',  key: 'furniture_bookshelf',       icon: '📚' },
        { type: 'plant',      key: 'furniture_plant',           icon: '🪴' },
        { type: 'tallPlant',  key: 'furniture_tall_plant',      icon: '🌿' },
        { type: 'endTable',   key: 'furniture_end_table_plant', icon: '🪴' },
    ]},
    { key: 'catalog_functional', items: [
        { type: 'functionalBookshelf', key: 'furniture_functional_bookshelf', icon: '📚' },
        { type: 'meetingTable4', key: 'furniture_meeting_table_4', icon: '▣' },
        { type: 'meetingTable6', key: 'furniture_meeting_table_6', icon: '▤' },
        { type: 'meetingRoom',   key: 'furniture_meeting_room',    icon: '▥' },
        { type: 'floorWindow',   key: 'furniture_floor_window',    icon: '🪟' },
    ]},
    { key: 'catalog_kitchen', items: [
        { type: 'kitchenCounter',key: 'furniture_kitchen_counter', icon: '🏪' },
        { type: 'coffeeMaker',   key: 'furniture_coffee_maker',    icon: '☕' },
        { type: 'vendingMachine',key: 'furniture_vending_machine', icon: '🥤' },
        { type: 'waterCooler',   key: 'furniture_water_cooler',    icon: '💧' },
        { type: 'microwave',     key: 'furniture_microwave',       icon: '📦' },
        { type: 'toaster',       key: 'furniture_toaster',         icon: '🍞' },
    ]},
    { key: 'catalog_fun', items: [
        { type: 'pingPongTable', key: 'furniture_ping_pong_table', icon: '🏓' },
        { type: 'dartBoard',     key: 'furniture_dart_board',      icon: '🎯' },
    ]},
    { key: 'catalog_structure', items: [
        { type: 'meetingTable',      key: 'furniture_meeting_table',  icon: '📊' },
        { type: 'window',            key: 'furniture_window',         icon: '🪟' },
        { type: 'interactiveWindow', key: 'furniture_weather_window', icon: '🌤️' },
        { type: 'clock',             key: 'furniture_clock',          icon: '🕐' },
        { type: 'floorLamp',         key: 'furniture_floor_lamp',     icon: '💡' },
    ]},
    { key: 'catalog_labels', items: [
        { type: 'textLabel', key: 'furniture_custom_text', icon: '✏️' },
    ]},
    { key: 'catalog_walls', items: [
        { type: 'wall', key: 'furniture_wall_segment', icon: '🧱' },
        { type: 'door', key: 'furniture_door_opening', icon: '🚪' },
    ]},
];

// --- FURNITURE PLACEMENT STATE ---
var placingType = null;      // furniture type being placed, or null
var selectedItemId = null;   // id of selected furniture item, or null
var isDragging = false;      // dragging a selected item
var dragOffset = { x: 0, y: 0 };
var _ghostPos = null;        // snapped world pos for ghost preview
var _catalogPanel = null;
var _floatingToolbar = null;
var _skipNextEditClick = false; // prevent click after drag

// --- WALL PLACEMENT STATE ---
var wallPlacingPhase = 0;   // 0=idle, 1=awaiting second click
var wallPlacingStart = null; // {tx, ty} first click tile
var selectedWallIdx = null;  // index into officeConfig.walls.interior

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

// ============================================================
// REAL WEATHER SYSTEM — fetches weather for configured location, renders on windows
// ============================================================
var weatherData = { condition: 'clear', description: '', code: 113, temp: 0, tempC: null, wind: 0, humidity: 0, feelsLike: 0, uvIndex: 0, visibility: 0, precipMM: 0, cloudcover: 0 };
var _displayPrefs = { showBubbles: true, showWeather: true, showNames: true, internalBubbleTimeoutSec: 60, fontScale: 1 };
try {
    var _dp = JSON.parse(localStorage.getItem("vo-display-prefs") || "{}");
    if (_dp.showBubbles !== undefined) _displayPrefs.showBubbles = _dp.showBubbles;
    if (_dp.showWeather !== undefined) _displayPrefs.showWeather = _dp.showWeather;
    if (_dp.showNames !== undefined) _displayPrefs.showNames = _dp.showNames;
    if (typeof VOFontScale !== 'undefined') {
        _displayPrefs.fontScale = VOFontScale.sanitizeStoredFontScale();
        VOFontScale.applyFontScale(_displayPrefs.fontScale);
    }
    if (typeof InternalBubbleSettings !== 'undefined') {
        _displayPrefs.internalBubbleTimeoutSec = InternalBubbleSettings.normalizeTimeoutSec(_dp.internalBubbleTimeoutSec);
    }
} catch(e) {}
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
        var fontScaleInput = document.getElementById('mm-font-scale');
        if (fontScaleInput && typeof VOFontScale !== 'undefined') {
            fontScaleInput.value = String(VOFontScale.normalizeFontScale(_displayPrefs.fontScale));
        }
    });
}
var lastWeatherPoll = 0;
var weatherParticles = []; // rain/snow particles
var _weatherTick = 0;
var _floorWindowTooltip = null;
var _voWeatherLocation = '';
var _tod = { sky: "#2196f3", upper: "#42a5f5", top: "#bbdefb", cloud: "rgba(255,255,255,0.5)", glow: "rgba(255,255,240,0.08)", stars: false }; // global time-of-day sky
var _lastLightningFlash = 0;
var _nextLightningAt = 0;
var _lightningBoltX = 0;
var _rainDroplets = []; // persistent rain droplets on glass
var _snowAccum = []; // snow accumulation on window sill

function pollWeather() {
    var now = Date.now();
    if (now - lastWeatherPoll < 600000) return; // every 10 minutes
    lastWeatherPoll = now;
    fetch('/weather-proxy').then(function(res) {
        if (!res.ok) throw new Error('Weather proxy error');
        return res;
    }).catch(function() {
        // No fallback — weather requires server-side config
        return null;
    }).then(function(res) {
        if (!res) return null;
        if (!res || !res.ok) return null;
        return res.json();
    }).then(function(data) {
        if (!data || !data.current_condition) return;
        var c = data.current_condition[0];
        var code = parseInt(c.weatherCode);
        var cond = 'clear';
        // Map weather codes to conditions — expanded categories
        if ([113].includes(code)) cond = 'sunny';
        else if ([116].includes(code)) cond = 'partly_cloudy';
        else if ([119, 122].includes(code)) cond = 'overcast';
        else if ([143, 248, 260].includes(code)) cond = 'foggy';
        else if ([176, 263, 266].includes(code)) cond = 'drizzle';
        else if ([293, 296].includes(code)) cond = 'light_rain';
        else if ([299, 302, 353, 356].includes(code)) cond = 'rain';
        else if ([305, 308, 359].includes(code)) cond = 'heavy_rain';
        else if ([200, 386, 389].includes(code)) cond = 'thunderstorm';
        else if ([392, 395].includes(code)) cond = 'snow_storm';
        else if ([179, 323, 326].includes(code)) cond = 'light_snow';
        else if ([227, 230, 329, 332, 335, 338, 368, 371].includes(code)) cond = 'snow';
        else if ([182, 185, 281, 284, 311, 314, 317, 320, 362, 365, 374, 377].includes(code)) cond = 'sleet';
        else cond = 'cloudy';
        weatherData = {
            condition: cond,
            description: ((c.weatherDesc || [{}])[0] || {}).value || '',
            code: code,
            temp: parseInt(c.temp_F) || 0,
            tempC: Number.isFinite(parseInt(c.temp_C)) ? parseInt(c.temp_C) : null,
            wind: parseInt(c.windspeedMiles) || 0,
            humidity: parseInt(c.humidity) || 0,
            feelsLike: parseInt(c.FeelsLikeF) || 0,
            uvIndex: parseInt(c.uvIndex) || 0,
            visibility: parseInt(c.visibility) || 10,
            precipMM: parseFloat(c.precipMM) || 0,
            cloudcover: parseInt(c.cloudcover) || 0
        };
        // Reset droplets/accumulation on condition change
        _rainDroplets = [];
        _snowAccum = [];
    }).catch(function() {});
}

function _refreshWeatherLocationFromConfig() {
    fetch('/vo-config').then(function(r) { return r.json(); }).then(function(cfg) {
        _voWeatherLocation = (((cfg || {}).weather || {}).location || '').trim();
    }).catch(function() {});
}

// Initialize weather on load
_refreshWeatherLocationFromConfig();
pollWeather();
setInterval(pollWeather, 600000);

function _formatWeatherConditionLabel(condition) {
    var labels = {
        clear: 'weather_condition_clear',
        sunny: 'weather_condition_sunny',
        partly_cloudy: 'weather_condition_partly_cloudy',
        cloudy: 'weather_condition_cloudy',
        overcast: 'weather_condition_overcast',
        foggy: 'weather_condition_foggy',
        drizzle: 'weather_condition_drizzle',
        light_rain: 'weather_condition_light_rain',
        rain: 'weather_condition_rain',
        heavy_rain: 'weather_condition_heavy_rain',
        thunderstorm: 'weather_condition_thunderstorm',
        light_snow: 'weather_condition_light_snow',
        snow: 'weather_condition_snow',
        snow_storm: 'weather_condition_snow_storm',
        sleet: 'weather_condition_sleet'
    };
    var key = labels[condition] || 'weather_condition_unknown';
    return typeof i18n !== 'undefined' ? i18n.t(key) : (condition || 'Unknown').replace(/_/g, ' ');
}

function _getWeatherLocationLabel() {
    var loc = (_voWeatherLocation || (((officeConfig || {}).weather || {}).location || '')).trim();
    return loc || (typeof i18n !== 'undefined' ? i18n.t('weather_location_unconfigured') : 'Not configured');
}

function _getWeatherTemperatureC() {
    if (Number.isFinite(weatherData.tempC)) return weatherData.tempC;
    if (Number.isFinite(weatherData.temp)) return Math.round((weatherData.temp - 32) * 5 / 9);
    return 0;
}

function _getFloorWindowWeatherTooltipLines() {
    return [
        (typeof i18n !== 'undefined' ? i18n.t('weather_location') : 'Weather Location') + ': ' + _getWeatherLocationLabel(),
        (typeof i18n !== 'undefined' ? i18n.t('weather_label') : 'Weather') + ': ' + (weatherData.description || _formatWeatherConditionLabel(weatherData.condition)),
        (typeof i18n !== 'undefined' ? i18n.t('temperature') : 'Temperature') + ': ' + _getWeatherTemperatureC() + '°C'
    ];
}

function _conditionFromWeatherDescription(desc) {
    var text = String(desc || '').toLowerCase();
    if (text.indexOf('thunder') >= 0) return 'thunderstorm';
    if (text.indexOf('snow') >= 0 || text.indexOf('blizzard') >= 0) return text.indexOf('light') >= 0 ? 'light_snow' : 'snow';
    if (text.indexOf('sleet') >= 0 || text.indexOf('ice') >= 0) return 'sleet';
    if (text.indexOf('drizzle') >= 0) return 'drizzle';
    if (text.indexOf('rain') >= 0 || text.indexOf('shower') >= 0) {
        if (text.indexOf('heavy') >= 0) return 'heavy_rain';
        if (text.indexOf('light') >= 0 || text.indexOf('patchy') >= 0) return 'light_rain';
        return 'rain';
    }
    if (text.indexOf('fog') >= 0 || text.indexOf('mist') >= 0) return 'foggy';
    if (text.indexOf('overcast') >= 0) return 'overcast';
    if (text.indexOf('cloud') >= 0) return text.indexOf('partly') >= 0 ? 'partly_cloudy' : 'cloudy';
    if (text.indexOf('sun') >= 0 || text.indexOf('clear') >= 0) return 'sunny';
    return 'clear';
}

function _applyWeatherTestResult(location, result) {
    if (!officeConfig.weather) officeConfig.weather = {};
    officeConfig.weather.location = location || result.location || officeConfig.weather.location || null;
    weatherData.condition = _conditionFromWeatherDescription(result.weather);
    weatherData.description = result.weather || '';
    weatherData.temp = parseInt(result.tempF) || weatherData.temp || 0;
    weatherData.tempC = Number.isFinite(parseInt(result.tempC)) ? parseInt(result.tempC) : weatherData.tempC;
}

// --- Helper: pseudo-random from seed ---
function _wRand(seed) {
    var x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
}

// --- Helper: draw a rounded cloud shape ---
function _drawCloud(cx, cy, w, h, alpha) {
    ctx.fillStyle = 'rgba(180,180,185,' + alpha + ')';
    ctx.beginPath();
    ctx.arc(cx, cy, h * 0.6, 0, Math.PI * 2);
    ctx.arc(cx - w * 0.25, cy + h * 0.15, h * 0.45, 0, Math.PI * 2);
    ctx.arc(cx + w * 0.25, cy + h * 0.15, h * 0.5, 0, Math.PI * 2);
    ctx.arc(cx - w * 0.4, cy + h * 0.3, h * 0.3, 0, Math.PI * 2);
    ctx.arc(cx + w * 0.4, cy + h * 0.3, h * 0.35, 0, Math.PI * 2);
    ctx.fill();
}

// --- Helper: draw a lightning bolt ---
function _drawLightningBolt(x, y, len, branches) {
    ctx.strokeStyle = 'rgba(255,255,220,0.9)';
    ctx.lineWidth = 1.5;
    ctx.shadowColor = 'rgba(255,255,200,0.8)';
    ctx.shadowBlur = 6;
    ctx.beginPath();
    ctx.moveTo(x, y);
    var bx = x, by = y;
    var segs = 4 + Math.floor(Math.random() * 3);
    for (var i = 0; i < segs; i++) {
        bx += (Math.random() - 0.5) * 8;
        by += len / segs;
        ctx.lineTo(bx, by);
        // Branch
        if (branches && Math.random() > 0.6) {
            var ex = bx + (Math.random() - 0.5) * 12;
            var ey = by + len / segs * 0.6;
            ctx.moveTo(bx, by);
            ctx.lineTo(ex, ey);
            ctx.moveTo(bx, by);
        }
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
}

function drawWeatherOnWindow(wx, wy, ww, wh, isLeft) {
    _weatherTick++;
    var cond = weatherData.condition;
    var wind = weatherData.wind;
    var t = _getTimeHour();
    var sun = _getSunTimes();
    var isDaytime = (t >= sun.sunrise && t < sun.sunset);

    // ─── SUNNY ───
    if (cond === 'sunny') {
        if (isDaytime) {
            ctx.save();
            ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
            // Warm golden wash
            ctx.fillStyle = 'rgba(255,235,59,0.5)';
            ctx.fillRect(wx, wy, ww, wh);
            if (isLeft) {
                var sunX = wx + 8, sunY = wy + 8;
                var rayAngle = (_weatherTick * 0.003);
                // Outer glow
                var grad = ctx.createRadialGradient(sunX, sunY, 2, sunX, sunY, 32);
                grad.addColorStop(0, 'rgba(255,245,157,0.92)');
                grad.addColorStop(0.5, 'rgba(255,235,59,0.65)');
                grad.addColorStop(1, 'rgba(255,235,59,0)');
                ctx.fillStyle = grad;
                ctx.fillRect(wx, wy, ww, wh);
                // Rotating rays with varying lengths
                ctx.lineWidth = 2;
                for (var ri = 0; ri < 12; ri++) {
                    var a = rayAngle + ri * (Math.PI / 6);
                    var rayLen = 24 + Math.sin(_weatherTick * 0.02 + ri * 0.7) * 10;
                    var rayAlpha = 0.55 + Math.sin(_weatherTick * 0.015 + ri) * 0.15;
                    ctx.strokeStyle = 'rgba(255,245,157,' + rayAlpha + ')';
                    ctx.beginPath();
                    ctx.moveTo(sunX + Math.cos(a) * 5, sunY + Math.sin(a) * 5);
                    ctx.lineTo(sunX + Math.cos(a) * rayLen, sunY + Math.sin(a) * rayLen);
                    ctx.stroke();
                }
                // Sun core with pulsing
                var pulse = 8 + Math.sin(_weatherTick * 0.02) * 2.5;
                ctx.fillStyle = 'rgba(255,235,59,0.95)';
                ctx.beginPath(); ctx.arc(sunX, sunY, pulse, 0, Math.PI * 2); ctx.fill();
                ctx.fillStyle = 'rgba(255,250,200,1.0)';
                ctx.beginPath(); ctx.arc(sunX, sunY, 3.5, 0, Math.PI * 2); ctx.fill();
                // Lens flare streak
                var flareAlpha = 0.22 + Math.sin(_weatherTick * 0.01) * 0.08;
                ctx.fillStyle = 'rgba(255,255,200,' + flareAlpha + ')';
                ctx.fillRect(wx, sunY - 1, ww, 2);
            }
            // Heat shimmer effect near bottom of window (hot day)
            if (weatherData.temp > 85) {
                var shimmer = Math.sin(_weatherTick * 0.08) * 0.04;
                ctx.fillStyle = 'rgba(255,200,50,' + (0.08 + shimmer) + ')';
                ctx.fillRect(wx, wy + wh - 8, ww, 8);
            }
            ctx.restore();
        }

    // ─── PARTLY CLOUDY ───
    } else if (cond === 'partly_cloudy') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        if (isDaytime) {
            // Soft sunlight filtering through
            ctx.fillStyle = 'rgba(255,235,59,0.18)';
            ctx.fillRect(wx, wy, ww, wh);
            // Sun peeks through if left window
            if (isLeft) {
                var pcSunX = wx + 6, pcSunY = wy + 6;
                ctx.fillStyle = 'rgba(255,235,59,0.22)';
                ctx.beginPath(); ctx.arc(pcSunX, pcSunY, 5, 0, Math.PI * 2); ctx.fill();
            }
        }
        // Drifting clouds
        var drift = (_weatherTick * 0.04);
        _drawCloud(wx + (drift + 5) % (ww + 10) - 5, wy + 7, 14, 5, 0.55);
        _drawCloud(wx + (drift * 0.7 + ww * 0.6) % (ww + 10) - 5, wy + 12, 10, 4, 0.48);
        // Moving cloud shadows on floor area
        var shadowX = wx + (drift * 1.5) % ww;
        ctx.fillStyle = 'rgba(0,0,0,0.04)';
        ctx.fillRect(shadowX - 6, wy + wh - 5, 12, 5);
        ctx.restore();

    // ─── OVERCAST ───
    } else if (cond === 'overcast' || cond === 'cloudy') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Grey blanket
        ctx.fillStyle = 'rgba(120,120,125,0.35)';
        ctx.fillRect(wx, wy, ww, wh);
        // Multiple cloud layers at different speeds
        var drift1 = (_weatherTick * 0.025);
        var drift2 = (_weatherTick * 0.015);
        // Upper layer — darker, slower
        ctx.fillStyle = 'rgba(140,140,145,0.6)';
        ctx.fillRect(wx + (drift2) % ww - 5, wy + 3, 16, 5);
        ctx.fillRect(wx + (drift2 + 20) % ww - 5, wy + 5, 12, 4);
        // Lower layer — lighter, faster
        _drawCloud(wx + (drift1 + 8) % (ww + 10) - 5, wy + 10, 14, 5, 0.48);
        _drawCloud(wx + (drift1 * 0.8 + ww * 0.5) % (ww + 10) - 5, wy + 16, 11, 4, 0.44);
        _drawCloud(wx + (drift1 * 1.2 + ww * 0.3) % (ww + 10) - 5, wy + 22, 9, 3, 0.4);
        // Dim the whole window slightly
        ctx.fillStyle = 'rgba(80,80,85,0.18)';
        ctx.fillRect(wx, wy, ww, wh);
        ctx.restore();

    // ─── DRIZZLE ───
    } else if (cond === 'drizzle') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Slight grey tint
        ctx.fillStyle = 'rgba(130,130,135,0.26)';
        ctx.fillRect(wx, wy, ww, wh);
        // Tiny thin rain lines — sparse, slow
        ctx.strokeStyle = 'rgba(160,195,220,0.8)';
        ctx.lineWidth = 0.5;
        for (var dr = 0; dr < 5; dr++) {
            var dSeed = _wRand(dr * 7 + wx);
            var dx = wx + (dSeed * ww + _weatherTick * 0.3) % ww;
            var dy = wy + (_weatherTick * 1.2 + dr * 17) % wh;
            ctx.beginPath();
            ctx.moveTo(dx, dy);
            ctx.lineTo(dx - 0.3, dy + 3);
            ctx.stroke();
        }
        // Water droplets slowly forming on glass
        ctx.fillStyle = 'rgba(170,210,240,0.65)';
        for (var wd = 0; wd < 8; wd++) {
            var ws = _wRand(wd * 13 + wx + 99);
            var wdx = wx + 2 + ws * (ww - 4);
            var wdy = wy + 2 + _wRand(wd * 17 + 55) * (wh - 4);
            // Droplets slowly grow and drip
            var dropPhase = (_weatherTick * 0.005 + wd * 1.3) % 3;
            var dropR = dropPhase < 2 ? 0.8 + dropPhase * 0.4 : 0.8;
            ctx.beginPath(); ctx.arc(wdx, wdy + (dropPhase > 2 ? (dropPhase - 2) * 3 : 0), dropR, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();

    // ─── LIGHT RAIN ───
    } else if (cond === 'light_rain') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(100,105,110,0.3)';
        ctx.fillRect(wx, wy, ww, wh);
        // Rain streaks — medium density, angled by wind
        var windAngle = Math.min(wind * 0.02, 0.4);
        ctx.strokeStyle = 'rgba(140,185,220,0.85)';
        ctx.lineWidth = 0.8;
        for (var lr = 0; lr < 10; lr++) {
            var lSeed = _wRand(lr * 11 + wx);
            var lx = wx + (lSeed * ww + _weatherTick * (0.4 + windAngle)) % ww;
            var ly = wy + (_weatherTick * 1.8 + lr * 11) % wh;
            ctx.beginPath();
            ctx.moveTo(lx, ly);
            ctx.lineTo(lx - windAngle * 6, ly + 5);
            ctx.stroke();
        }
        // Droplets on glass — more than drizzle
        ctx.fillStyle = 'rgba(150,200,240,0.7)';
        for (var ld = 0; ld < 10; ld++) {
            var ls = _wRand(ld * 19 + wx + 77);
            var ldx = wx + 2 + ls * (ww - 4);
            var ldy = wy + 2 + _wRand(ld * 23 + 33) * (wh - 4);
            var ldPhase = (_weatherTick * 0.008 + ld * 0.9) % 4;
            var ldR = ldPhase < 2.5 ? 1 + ldPhase * 0.3 : 1;
            ctx.beginPath(); ctx.arc(ldx, ldy, ldR, 0, Math.PI * 2); ctx.fill();
            // Drip trail
            if (ldPhase > 2) {
                ctx.fillStyle = 'rgba(150,200,240,0.2)';
                ctx.fillRect(ldx - 0.3, ldy + ldR, 0.6, (ldPhase - 2) * 5);
                ctx.fillStyle = 'rgba(150,200,240,0.7)';
            }
        }
        ctx.restore();

    // ─── RAIN ───
    } else if (cond === 'rain') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(80,85,95,0.38)';
        ctx.fillRect(wx, wy, ww, wh);
        // Dense rain streaks
        var rWindAngle = Math.min(wind * 0.025, 0.5);
        ctx.strokeStyle = 'rgba(130,180,220,0.9)';
        ctx.lineWidth = 1;
        for (var rr = 0; rr < 14; rr++) {
            var rSeed = _wRand(rr * 7 + wx);
            var rx = wx + (rSeed * ww + _weatherTick * (0.5 + rWindAngle)) % ww;
            var ry = wy + (_weatherTick * 2.2 + rr * 9) % wh;
            ctx.beginPath();
            ctx.moveTo(rx, ry);
            ctx.lineTo(rx - rWindAngle * 8, ry + 6);
            ctx.stroke();
        }
        // Splashes at bottom of window
        for (var sp = 0; sp < 4; sp++) {
            var sps = _wRand(sp * 31 + wx + 17);
            var spx = wx + 3 + sps * (ww - 6);
            var spy = wy + wh - 3;
            var spPhase = (_weatherTick * 0.06 + sp * 2.1) % 2;
            if (spPhase < 0.5) {
                ctx.fillStyle = 'rgba(150,200,240,' + (0.4 - spPhase * 0.8) + ')';
                var spR = 1 + spPhase * 4;
                ctx.beginPath(); ctx.arc(spx, spy, spR, Math.PI, 0); ctx.fill();
            }
        }
        // Water droplets + running streams on glass
        ctx.fillStyle = 'rgba(150,200,240,0.75)';
        for (var rd = 0; rd < 12; rd++) {
            var rs = _wRand(rd * 11 + wx + 44);
            var rdx = wx + 2 + rs * (ww - 4);
            var rdy = wy + 2 + _wRand(rd * 7 + 88) * (wh - 8);
            ctx.beginPath(); ctx.arc(rdx, rdy, 1.5, 0, Math.PI * 2); ctx.fill();
            // Running water trail
            ctx.fillStyle = 'rgba(150,200,240,0.2)';
            var trailLen = 3 + _wRand(rd * 3) * 8;
            ctx.fillRect(rdx - 0.4, rdy + 1.5, 0.8, trailLen);
            ctx.fillStyle = 'rgba(150,200,240,0.75)';
        }
        // Clouds
        _drawCloud(wx + (_weatherTick * 0.03 + 5) % (ww + 10) - 5, wy + 5, 14, 5, 0.65);
        ctx.restore();

    // ─── HEAVY RAIN ───
    } else if (cond === 'heavy_rain') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Very dark overlay
        ctx.fillStyle = 'rgba(50,55,65,0.5)';
        ctx.fillRect(wx, wy, ww, wh);
        // Torrential rain — dense, fast, wind-driven
        var hrWind = Math.min(wind * 0.03, 0.6);
        ctx.strokeStyle = 'rgba(120,170,210,0.92)';
        ctx.lineWidth = 1.2;
        for (var hr = 0; hr < 20; hr++) {
            var hSeed = _wRand(hr * 7 + wx);
            var hx = wx + (hSeed * ww + _weatherTick * (0.7 + hrWind)) % ww;
            var hy = wy + (_weatherTick * 3 + hr * 7) % wh;
            ctx.beginPath();
            ctx.moveTo(hx, hy);
            ctx.lineTo(hx - hrWind * 10, hy + 8);
            ctx.stroke();
        }
        // Heavy splashes
        for (var hs = 0; hs < 6; hs++) {
            var hss = _wRand(hs * 23 + wx + 9);
            var hsx = wx + 3 + hss * (ww - 6);
            var hsy = wy + wh - 3;
            var hsPhase = (_weatherTick * 0.08 + hs * 1.7) % 2;
            if (hsPhase < 0.6) {
                ctx.fillStyle = 'rgba(150,200,240,' + (0.5 - hsPhase * 0.8) + ')';
                ctx.beginPath(); ctx.arc(hsx, hsy, 1.5 + hsPhase * 5, Math.PI, 0); ctx.fill();
            }
        }
        // Water streaming down window — thick rivulets
        ctx.strokeStyle = 'rgba(140,190,230,0.7)';
        ctx.lineWidth = 1.5;
        for (var rv = 0; rv < 4; rv++) {
            var rvx = wx + 4 + _wRand(rv * 41 + wx) * (ww - 8);
            ctx.beginPath();
            ctx.moveTo(rvx, wy);
            for (var rvs = 0; rvs < 6; rvs++) {
                rvx += Math.sin(_weatherTick * 0.03 + rv + rvs) * 2;
                ctx.lineTo(rvx, wy + (rvs + 1) * (wh / 6));
            }
            ctx.stroke();
        }
        // Mist/spray at bottom
        ctx.fillStyle = 'rgba(180,200,220,0.28)';
        ctx.fillRect(wx, wy + wh - 10, ww, 10);
        ctx.restore();

    // ─── THUNDERSTORM ───
    } else if (cond === 'thunderstorm') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Very dark sky
        ctx.fillStyle = 'rgba(30,30,40,0.6)';
        ctx.fillRect(wx, wy, ww, wh);
        // Heavy wind-driven rain
        var stWind = Math.min(wind * 0.035, 0.7);
        ctx.strokeStyle = 'rgba(120,165,200,0.9)';
        ctx.lineWidth = 1;
        for (var sr = 0; sr < 18; sr++) {
            var sSeed = _wRand(sr * 7 + wx);
            var sx = wx + (sSeed * ww + _weatherTick * (0.8 + stWind)) % ww;
            var sy = wy + (_weatherTick * 3.5 + sr * 8) % wh;
            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(sx - stWind * 12, sy + 7);
            ctx.stroke();
        }
        // Lightning — irregular timing with multiple bolt types
        if (_weatherTick > _nextLightningAt) {
            _lastLightningFlash = _weatherTick;
            _lightningBoltX = wx + 3 + Math.random() * (ww - 6);
            _nextLightningAt = _weatherTick + 120 + Math.floor(Math.random() * 300);
        }
        var flashAge = _weatherTick - _lastLightningFlash;
        // Flash illumination (fades over ~8 frames)
        if (flashAge < 8) {
            var flashAlpha = 0.5 * Math.pow(0.7, flashAge);
            ctx.fillStyle = 'rgba(255,255,240,' + flashAlpha + ')';
            ctx.fillRect(wx, wy, ww, wh);
        }
        // Lightning bolt visible for a few frames
        if (flashAge < 4 && isLeft) {
            _drawLightningBolt(_lightningBoltX, wy + 2, wh * 0.7, true);
        }
        // Double-flash effect (flickers)
        if (flashAge >= 6 && flashAge < 9) {
            ctx.fillStyle = 'rgba(255,255,240,0.15)';
            ctx.fillRect(wx, wy, ww, wh);
        }
        // Dark roiling clouds
        var stDrift = _weatherTick * 0.04;
        ctx.fillStyle = 'rgba(50,50,60,0.35)';
        _drawCloud(wx + (stDrift + 3) % (ww + 10) - 5, wy + 5, 16, 6, 0.72);
        _drawCloud(wx + (stDrift * 0.6 + ww * 0.5) % (ww + 10) - 5, wy + 10, 12, 5, 0.65);
        // Splashes
        for (var tsp = 0; tsp < 5; tsp++) {
            var tsps = _wRand(tsp * 19 + wx);
            var tspx = wx + 3 + tsps * (ww - 6);
            var tspy = wy + wh - 3;
            var tspPhase = (_weatherTick * 0.09 + tsp * 1.5) % 2;
            if (tspPhase < 0.5) {
                ctx.fillStyle = 'rgba(180,210,240,' + (0.4 - tspPhase * 0.8) + ')';
                ctx.beginPath(); ctx.arc(tspx, tspy, 1.5 + tspPhase * 4, Math.PI, 0); ctx.fill();
            }
        }
        ctx.restore();

    // ─── FOGGY ───
    } else if (cond === 'foggy') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Multi-layer fog with parallax drifting
        var fogPhase = _weatherTick * 0.008;
        // Background haze
        ctx.fillStyle = 'rgba(195,195,200,0.48)';
        ctx.fillRect(wx, wy, ww, wh);
        // Fog bands — three layers at different speeds and heights
        for (var fb = 0; fb < 3; fb++) {
            var bandY = wy + 6 + fb * 10 + Math.sin(fogPhase * (0.8 + fb * 0.3) + fb * 2) * 3;
            var bandAlpha = 0.12 - fb * 0.02;
            var bandW = ww * (0.7 + _wRand(fb * 7) * 0.5);
            var bandX = wx + Math.sin(fogPhase * (0.5 + fb * 0.2)) * 5;
            ctx.fillStyle = 'rgba(210,212,215,' + bandAlpha + ')';
            ctx.fillRect(bandX, bandY, bandW, 6 - fb);
        }
        // Misty particles drifting
        ctx.fillStyle = 'rgba(220,220,225,0.4)';
        for (var mp = 0; mp < 6; mp++) {
            var mpx = wx + (_wRand(mp * 17) * ww + _weatherTick * 0.15) % ww;
            var mpy = wy + _wRand(mp * 29 + 7) * wh;
            ctx.beginPath(); ctx.arc(mpx, mpy, 2 + _wRand(mp) * 2, 0, Math.PI * 2); ctx.fill();
        }
        // Condensation on glass
        ctx.fillStyle = 'rgba(200,210,220,0.2)';
        for (var fc = 0; fc < 6; fc++) {
            var fcx = wx + 2 + _wRand(fc * 11 + wx) * (ww - 4);
            var fcy = wy + 2 + _wRand(fc * 23 + 5) * (wh - 4);
            ctx.beginPath(); ctx.arc(fcx, fcy, 1, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();

    // ─── LIGHT SNOW ───
    } else if (cond === 'light_snow') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(210,215,225,0.25)';
        ctx.fillRect(wx, wy, ww, wh);
        // Gentle floating snowflakes — slow, drifting
        for (var ls = 0; ls < 5; ls++) {
            var lsSeed = _wRand(ls * 13 + wx);
            var lsx = wx + (lsSeed * ww + _weatherTick * 0.12 + Math.sin(_weatherTick * 0.03 + ls * 1.8) * 5) % ww;
            var lsy = wy + (_weatherTick * 0.3 + ls * 13) % wh;
            var lsSize = 1 + _wRand(ls * 7) * 1.5;
            // Snowflake sparkle
            var sparkle = 0.6 + Math.sin(_weatherTick * 0.05 + ls * 2.3) * 0.3;
            ctx.fillStyle = 'rgba(255,255,255,' + sparkle + ')';
            ctx.beginPath(); ctx.arc(lsx, lsy, lsSize, 0, Math.PI * 2); ctx.fill();
        }
        // Light frost on corners
        ctx.fillStyle = 'rgba(230,235,245,0.3)';
        ctx.fillRect(wx, wy, 4, 4);
        ctx.fillRect(wx + ww - 4, wy, 4, 4);
        ctx.restore();

    // ─── SNOW ───
    } else if (cond === 'snow') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Cold blue-grey tint
        ctx.fillStyle = 'rgba(200,205,220,0.32)';
        ctx.fillRect(wx, wy, ww, wh);
        // Dense snowflakes with varied sizes and wobble
        for (var sf = 0; sf < 10; sf++) {
            var fSeed = _wRand(sf * 13 + wx);
            var wobble = Math.sin(_weatherTick * 0.04 + sf * 1.7) * 4;
            var fx = wx + (fSeed * ww + _weatherTick * 0.18 + wobble) % ww;
            var fy = wy + (_weatherTick * 0.6 + sf * 9) % wh;
            var fSize = 1 + _wRand(sf * 3 + 5) * 2;
            var fAlpha = 0.5 + _wRand(sf * 19) * 0.4;
            ctx.fillStyle = 'rgba(255,255,255,' + fAlpha + ')';
            ctx.beginPath(); ctx.arc(fx, fy, fSize, 0, Math.PI * 2); ctx.fill();
            // Some flakes have a tiny cross shape (larger ones)
            if (fSize > 2) {
                ctx.strokeStyle = 'rgba(255,255,255,' + (fAlpha * 0.5) + ')';
                ctx.lineWidth = 0.5;
                ctx.beginPath(); ctx.moveTo(fx - fSize, fy); ctx.lineTo(fx + fSize, fy); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(fx, fy - fSize); ctx.lineTo(fx, fy + fSize); ctx.stroke();
            }
        }
        // Snow accumulation on window sill
        ctx.fillStyle = 'rgba(240,242,248,0.75)';
        ctx.fillRect(wx, wy + wh - 3, ww, 3);
        ctx.fillStyle = 'rgba(250,250,255,0.3)';
        for (var sa = 0; sa < 5; sa++) {
            var sax = wx + sa * (ww / 5) + 2;
            var saH = 2 + _wRand(sa * 7 + wx) * 2;
            ctx.beginPath(); ctx.arc(sax + ww / 10, wy + wh - 2, saH, Math.PI, 0); ctx.fill();
        }
        // Frost on edges
        ctx.fillStyle = 'rgba(220,225,240,0.2)';
        ctx.fillRect(wx, wy, ww, 2);
        ctx.fillRect(wx, wy, 2, wh);
        ctx.fillRect(wx + ww - 2, wy, 2, wh);
        ctx.restore();

    // ─── SNOW STORM ───
    } else if (cond === 'snow_storm') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Whiteout conditions
        ctx.fillStyle = 'rgba(200,205,215,0.2)';
        ctx.fillRect(wx, wy, ww, wh);
        // Blowing snow — fast, wind-driven, dense
        var snWind = Math.min(wind * 0.04, 0.8);
        for (var bs = 0; bs < 16; bs++) {
            var bSeed = _wRand(bs * 11 + wx);
            var bx = wx + (bSeed * ww + _weatherTick * (0.4 + snWind * 2)) % ww;
            var by = wy + (_weatherTick * 1.2 + bs * 7) % wh;
            var bSize = 1 + _wRand(bs * 3) * 2.5;
            var bAlpha = 0.4 + _wRand(bs * 17) * 0.5;
            ctx.fillStyle = 'rgba(255,255,255,' + bAlpha + ')';
            ctx.beginPath(); ctx.arc(bx, by, bSize, 0, Math.PI * 2); ctx.fill();
        }
        // Gusts — periodic horizontal snow streaks
        if ((_weatherTick % 120) < 30) {
            ctx.strokeStyle = 'rgba(255,255,255,0.3)';
            ctx.lineWidth = 0.8;
            for (var gs = 0; gs < 6; gs++) {
                var gsy = wy + 3 + _wRand(gs * 7 + _weatherTick) * (wh - 6);
                ctx.beginPath();
                ctx.moveTo(wx, gsy);
                ctx.lineTo(wx + ww * 0.6, gsy + (Math.random() - 0.5) * 3);
                ctx.stroke();
            }
        }
        // Heavy sill accumulation
        ctx.fillStyle = 'rgba(240,242,248,0.5)';
        ctx.fillRect(wx, wy + wh - 5, ww, 5);
        // Frost covering edges heavily
        ctx.fillStyle = 'rgba(215,220,235,0.25)';
        ctx.fillRect(wx, wy, ww, 3);
        ctx.fillRect(wx, wy, 3, wh);
        ctx.fillRect(wx + ww - 3, wy, 3, wh);
        // Ice crystals in corners
        ctx.strokeStyle = 'rgba(200,210,230,0.2)';
        ctx.lineWidth = 0.5;
        for (var ic = 0; ic < 3; ic++) {
            var icx = wx + 2 + ic * 2, icy = wy + 2 + ic * 2;
            ctx.beginPath(); ctx.moveTo(icx, icy); ctx.lineTo(icx + 4, icy + 4); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(icx + 4, icy); ctx.lineTo(icx, icy + 4); ctx.stroke();
        }
        ctx.restore();

    // ─── SLEET ───
    } else if (cond === 'sleet') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(100,105,115,0.15)';
        ctx.fillRect(wx, wy, ww, wh);
        // Mix of rain streaks and ice pellets
        var slWind = Math.min(wind * 0.025, 0.5);
        // Rain component
        ctx.strokeStyle = 'rgba(130,175,210,0.5)';
        ctx.lineWidth = 0.8;
        for (var sl = 0; sl < 8; sl++) {
            var slSeed = _wRand(sl * 7 + wx);
            var slx = wx + (slSeed * ww + _weatherTick * (0.5 + slWind)) % ww;
            var sly = wy + (_weatherTick * 2 + sl * 11) % wh;
            ctx.beginPath(); ctx.moveTo(slx, sly); ctx.lineTo(slx - slWind * 6, sly + 5); ctx.stroke();
        }
        // Ice pellet component — small bright dots falling faster
        ctx.fillStyle = 'rgba(220,230,240,0.7)';
        for (var ip = 0; ip < 6; ip++) {
            var ipSeed = _wRand(ip * 17 + wx + 33);
            var ipx = wx + (ipSeed * ww + _weatherTick * 0.6) % ww;
            var ipy = wy + (_weatherTick * 2.5 + ip * 12) % wh;
            ctx.fillRect(ipx, ipy, 1.5, 1.5);
        }
        // Ice buildup on glass
        ctx.fillStyle = 'rgba(200,215,230,0.15)';
        ctx.fillRect(wx, wy + wh - 3, ww, 3);
        ctx.restore();
    }
}

// ============================================================
// AMBIENT LIGHTING — day/night cycle for the whole office
// ============================================================
// Debug: set _timeLapse=true to cycle 24h in 60 seconds
var _timeLapse = false;
var _timeLapseStart = 0;

// Time override: null = real time, or fixed hour (0-23)
var _timeOverride = null;
var _timeOverrideModes = [
    null,        // real time
    12,          // noon (full daylight)
    21,          // 9 PM (night)
    6,           // 6 AM (dawn)
    17.5,        // 5:30 PM (sunset)
    'lapse'      // time-lapse
];
var _timeOverrideIdx = 0;

function cycleTimeOverride() {
    _timeOverrideIdx = (_timeOverrideIdx + 1) % _timeOverrideModes.length;
    var mode = _timeOverrideModes[_timeOverrideIdx];
    var btn = document.getElementById('btn-time-override');
    if (mode === null) {
        _timeOverride = null;
        _timeLapse = false;
        if (btn) { btn.textContent = '☀️'; btn.title = typeof i18n !== 'undefined' ? i18n.t('time_real') : 'Time: Real time'; }
        console.log('Time override OFF — real time');
    } else if (mode === 'lapse') {
        _timeOverride = null;
        _timeLapse = true;
        _timeLapseStart = Date.now();
        if (btn) { btn.textContent = '⏩'; btn.title = typeof i18n !== 'undefined' ? i18n.t('time_lapse') : 'Time: Lapse (24h in 60s)'; }
        console.log('Time-lapse ON — 24h in 60s');
    } else {
        _timeOverride = mode;
        _timeLapse = false;
        var labels = { 12: '🌞 Noon', 21: '🌙 Night', 6: '🌅 Dawn', 17.5: '🌇 Sunset' };
        if (btn) { btn.textContent = labels[mode] || '⏰'; btn.title = 'Time: ' + (labels[mode] || mode + 'h'); }
        console.log('Time override: ' + mode + 'h');
    }
}

function _getTimeHour() {
    if (_timeOverride !== null) return _timeOverride;
    if (_timeLapse) {
        var elapsed = (Date.now() - _timeLapseStart) / 1000;
        return (elapsed / 60 * 24) % 24;
    }
    var h = new Date().getHours();
    var m = new Date().getMinutes();
    return h + m / 60;
}

function toggleTimeLapse() {
    _timeLapse = !_timeLapse;
    _timeLapseStart = Date.now();
    console.log(_timeLapse ? 'Time-lapse ON — 24h in 60s' : 'Time-lapse OFF — real time');
}

// Solar calculator for Florida (~27.5°N latitude)
function _calcSunTimes() {
    var now = new Date();
    var start = new Date(now.getFullYear(), 0, 0);
    var diff = now - start;
    var dayOfYear = Math.floor(diff / 86400000);
    var lat = 27.5; // Central Florida latitude
    var latRad = lat * Math.PI / 180;

    // Solar declination
    var decl = -23.45 * Math.cos(2 * Math.PI / 365 * (dayOfYear + 10));
    var declRad = decl * Math.PI / 180;

    // Hour angle for sunrise/sunset (when sun crosses horizon)
    var cosHA = -Math.tan(latRad) * Math.tan(declRad);
    cosHA = Math.max(-1, Math.min(1, cosHA));
    var haHours = Math.acos(cosHA) * 180 / Math.PI / 15;

    // Solar noon (approximate — 12:00 + small correction)
    var noon = 12.0;

    var sunrise = noon - haHours;
    var sunset = noon + haHours;

    // Civil twilight (~30 min before sunrise / after sunset)
    var dawn = sunrise - 0.5;
    var dusk = sunset + 0.5;

    return { dawn: dawn, sunrise: sunrise, sunset: sunset, dusk: dusk };
}

var _sunTimes = _calcSunTimes(); // recalculate once on load
var _sunTimesLastDay = new Date().getDate();

function _getSunTimes() {
    var today = new Date().getDate();
    if (today !== _sunTimesLastDay) {
        _sunTimes = _calcSunTimes();
        _sunTimesLastDay = today;
    }
    return _sunTimes;
}

// --- FPS counter + perf profiling ---
var _fpsFrames = 0, _fpsLast = Date.now(), _fpsDisplay = 0;
var _perfTimes = {};

function _perfStart(label) { _perfTimes[label] = performance.now(); }
function _perfEnd(label) {
    var elapsed = performance.now() - (_perfTimes[label] || 0);
    if (!_perfTimes._totals) _perfTimes._totals = {};
    if (!_perfTimes._counts) _perfTimes._counts = {};
    _perfTimes._totals[label] = (_perfTimes._totals[label] || 0) + elapsed;
    _perfTimes._counts[label] = (_perfTimes._counts[label] || 0) + 1;
    // Log every 120 frames
    if (_perfTimes._counts[label] === 120) {
        var avg = _perfTimes._totals[label] / 120;
        if (avg > 0.5) console.log('[perf] ' + label + ': ' + avg.toFixed(2) + 'ms avg');
        _perfTimes._totals[label] = 0;
        _perfTimes._counts[label] = 0;
    }
}

// --- Rim light cache (Option D: throttled to every 5 frames) ---
var _rimCache = new Map();
var _rimFrame = 0;
var _RIM_INTERVAL = 5;

// Cached ambient light — computed once per frame via _updateAmbientCache()
var _ambientCache = { dark: 0, tint: '0,0,0' };
function _updateAmbientCache() {
    var t = _getTimeHour();
    var sun = _getSunTimes();

    // Phase boundaries based on real sun times
    var nightEnd = sun.dawn;              // civil twilight begins
    var dawnEnd = sun.sunrise;            // sun rises
    var morningEnd = sun.sunrise + 1.5;   // golden hour ends ~1.5h after sunrise
    var afternoonStart = sun.sunset - 2;  // late afternoon begins 2h before sunset
    var sunsetStart = sun.sunset - 0.5;   // sunset glow starts 30min before
    var sunsetEnd = sun.sunset + 0.3;     // sun dips below
    var duskEnd = sun.dusk;               // civil twilight ends — full night

    if (t < nightEnd)         _ambientCache = { dark: 0.25, tint: '0,10,40' };       // deep night
    else if (t < dawnEnd)     _ambientCache = { dark: 0.12, tint: '60,20,0' };       // dawn
    else if (t < morningEnd)  _ambientCache = { dark: 0.05, tint: '40,20,0' };       // morning golden
    else if (t < afternoonStart) _ambientCache = { dark: 0,    tint: '0,0,0' };      // full daylight
    else if (t < sunsetStart) _ambientCache = { dark: 0.03, tint: '40,15,0' };       // late afternoon
    else if (t < sunsetEnd)   _ambientCache = { dark: 0.08, tint: '50,20,0' };       // sunset
    else if (t < duskEnd)     _ambientCache = { dark: 0.15, tint: '20,10,30' };      // dusk
    else                      _ambientCache = { dark: 0.25, tint: '0,10,40' };       // night
}
function getAmbientLight() { return _ambientCache; }

function drawAmbientOverlay() {
    var amb = getAmbientLight();
    if (amb.dark <= 0) return; // full daylight, no overlay needed

    // Dark overlay on entire scene
    ctx.save();
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = 'rgba(' + amb.tint + ',' + amb.dark + ')';
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
}

// Option G helper: check if a world-space point is visible in current viewport
function _isInView(wx, wy, margin) {
    var base = Math.max(displayW / W, displayH / H);
    var totalZoom = base * camera.zoom;
    var viewW = displayW / totalZoom;
    var viewH = displayH / totalZoom;
    var camLeft = W / 2 + camera.x - viewW / 2 - margin;
    var camTop = H / 2 + camera.y - viewH / 2 - margin;
    return wx >= camLeft && wx <= camLeft + viewW + margin * 2 &&
           wy >= camTop && wy <= camTop + viewH + margin * 2;
}

// Rim light — calculated per agent, cached every _RIM_INTERVAL frames
function getRimLight(agent) {
    var key = agent.id || agent.name;
    if (_rimFrame % _RIM_INTERVAL !== 0) {
        var cached = _rimCache.get(key);
        if (cached !== undefined) return cached;
    }
    var result = _getRimLightInner(agent);
    _rimCache.set(key, result);
    return result;
}
function _getRimLightInner(agent) {
    // Hardcoded light sources removed — rim lighting will be driven by dynamic light system
    return null;
}

// Helper: set warm lamp shadow for furniture near a light source
function _setFurnitureLampShadow(objX, objY) {
    // Hardcoded light sources removed — no-op until dynamic light system
}
function _clearFurnitureShadow() {
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
}

// Neon signs (drawn after ambient overlay so they glow through darkness)
// Option B: layered text glow instead of shadowBlur
// Neon sign colors mapped by theme
var _NEON_COLORS = {
    'branch-gold':   '#ffeb3b',
    'branch-blue':   '#00e5ff',
    'branch-orange': '#ff9100',
    'branch-cyan':   '#00e5ff',
    'branch-red':    '#ff6d00',
    'branch-gray':   '#90a4ae',
};

// Cached desk position lookup — rebuilt when furniture changes
var _deskPosCache = null;
var _deskPosCacheKey = '';
function _getDeskPositions() {
    // Simple cache key: furniture count + last item id
    var fLen = officeConfig.furniture.length;
    var key = fLen + ':' + (fLen > 0 ? officeConfig.furniture[fLen - 1].id : '');
    if (_deskPosCache && _deskPosCacheKey === key) return _deskPosCache;
    _deskPosCache = {};
    officeConfig.furniture.forEach(function(f) {
        if (f.type === 'desk' || f.type === 'bossDesk') _deskPosCache[f.x + ',' + f.y] = true;
    });
    _deskPosCacheKey = key;
    return _deskPosCache;
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

// --- FURNITURE ACTION SPOTS (dx/dy relative to furniture item's x,y) ---
// Spot dx/dy values are calibrated to match existing LOCATIONS.interactions positions exactly.
const FURNITURE_ACTIONS = {
    'lounge': {
        spots: [
            // L-couch seats
            { dx: 18, dy: 25, faceDir:  1, action: 'sit' },
            { dx: 18, dy: 48, faceDir:  1, action: 'sit' },
            { dx: 48, dy: 80, faceDir: -1, action: 'sit' },
            { dx: 78, dy: 80, faceDir: -1, action: 'sit' },
            { dx: 108, dy: 80, faceDir: -1, action: 'sit' },
            // Bookshelf (drawn at lx-50, ly inside drawLoungeArea)
            { dx: -30, dy: 35, action: 'read' },
            // TV spot
            { dx: 95, dy: 28, faceDir: 1, action: 'watch' },
            // Dart board spot (drawn at lx+210, ly-8 inside drawLoungeArea)
            { dx: 210, dy: 120, action: 'darts' },
        ]
    },
    'engLounge': {
        spots: [
            { dx:  20, dy: 27, faceDir: -1, action: 'sit' },
            { dx:  60, dy: 27, faceDir: -1, action: 'sit' },
            { dx: 100, dy: 27, faceDir: -1, action: 'sit' },
            { dx: 140, dy: 27, faceDir: -1, action: 'sit' },
        ]
    },
    'breakArea': {
        spots: [
            { dx:  25, dy:  90, action: 'vend'      },  // vending machine
            { dx: 110, dy: 105, action: 'coffee'    },  // coffee maker
            { dx: 165, dy:  62, action: 'drink'     },  // water cooler
            { dx: 195, dy: 105, action: 'microwave' },  // microwave
            { dx: 220, dy: 105, action: 'toast'     },  // toaster
        ]
    },
    'meetingTable': {
        spots: [
            // Top row (5 chairs, evenly spaced across 200px table starting at pad=20, spacing=(200-14)/4=46.5)
            { dx:  27, dy:  15, faceDir: 2 }, { dx:  73, dy:  15, faceDir: 2 }, { dx: 120, dy:  15, faceDir: 2 },
            { dx: 166, dy:  15, faceDir: 2 }, { dx: 213, dy:  15, faceDir: 2 },
            // Bottom row
            { dx:  27, dy: 103, faceDir: 0 }, { dx:  73, dy: 103, faceDir: 0 }, { dx: 120, dy: 103, faceDir: 0 },
            { dx: 166, dy: 103, faceDir: 0 }, { dx: 213, dy: 103, faceDir: 0 },
        ],
        action: 'meeting'
    },
    'couch': {
        spots: [
            { dx: 12, dy: 15, faceDir:  1, action: 'sit' },
            { dx: 12, dy: 38, faceDir:  1, action: 'sit' },
            { dx: 36, dy: 65, faceDir: -1, action: 'sit' },
            { dx: 60, dy: 65, faceDir: -1, action: 'sit' },
            { dx: 84, dy: 65, faceDir: -1, action: 'sit' },
        ]
    },
    'coffeeTable':    { spots: [],                               action: null     },
    'dartBoard':      { spots: [{ dx: 0, dy: 140 }],            action: 'darts'  },
    'pingPongTable':  { spots: [{ dx: -50, dy: 0 }, { dx: 50, dy: 0 }], action: 'pong' },
    'desk':           { spots: [{ dx: 0, dy: 0 }],              action: 'work'   },
    'bossDesk':       { spots: [{ dx: 0, dy: 0 }],              action: 'work'   },
    'waterCooler':    { spots: [{ dx: -6, dy: 54 }],            action: 'drink',  queue: true },
    'coffeeMaker':    { spots: [{ dx: 0, dy: 48 }],             action: 'coffee', queue: true },
    'vendingMachine': { spots: [{ dx: 0, dy: 74 }],             action: 'vend',   queue: true },
    'microwave':      { spots: [{ dx: 0, dy: 56 }],             action: 'microwave', queue: true },
    'toaster':        { spots: [{ dx: 0, dy: 40 }],             action: 'toast',  queue: true },
    'window':         { spots: [{ dx: 0, dy: 90 }],             action: 'gaze'   },
    'interactiveWindow': { spots: [{ dx: 0, dy: 90 }],          action: 'gaze'   },
    'bookshelf':      { spots: [{ dx: 0, dy: 90 }],             action: 'read'   },
    'tv':             { spots: [{ dx: 0, dy: 50, faceDir: 1 }], action: 'watch'  },
    'couch':          {
        spots: [
            // 4 seats ON the main body cushions (matching cushion centers)
            { dx: 23,  dy: 25, faceDir: 1, action: 'sit' },
            { dx: 57,  dy: 25, faceDir: 1, action: 'sit' },
            { dx: 91,  dy: 25, faceDir: 1, action: 'sit' },
            { dx: 125, dy: 25, faceDir: 1, action: 'sit' },
            // 1 seat ON the daybed cushion
            { dx: 135, dy: 58, faceDir: -1, action: 'sit' },
        ],
        rotatable: true,
    },
    'coffeeTable':    { spots: [], action: 'none' },
    'endTable':       { spots: [], action: 'none' },
    'textLabel':      { spots: [], action: 'none' },
};

// --- DEFAULT FURNITURE LAYOUT (matches current hardcoded drawEnvironment exactly) ---
function getDefaultFurniture() {
    var L = LOCATIONS;
    var f = [];
    // PQ desks + trash cans
    L.pqDesks.forEach(function(d, i) {
        f.push({ id: 'desk-pq-' + i,    type: 'desk',      x: d.x,      y: d.y      });
        f.push({ id: 'trash-pq-' + i,   type: 'trashCan',  x: d.x + 45, y: d.y + 20 });
    });
    // PQ area items
    f.push({ id: 'ping-pong',       type: 'pingPongTable',  x: 190,  y: 105 });
    f.push({ id: 'cabinet-pq-0',    type: 'filingCabinet',  x: 50,   y: 200 });
    f.push({ id: 'cabinet-pq-1',    type: 'filingCabinet',  x: 50,   y: 330 });
    f.push({ id: 'whiteboard-pq',   type: 'whiteboard',     x: 50,   y: 260 });
    // Boss desk
    f.push({ id: 'boss-desk',       type: 'bossDesk',       x: L.bossDesk.x,    y: L.bossDesk.y    });
    // Center desks + trash
    f.push({ id: 'desk-center',     type: 'desk',     x: L.centerDesk.x,  y: L.centerDesk.y  });
    f.push({ id: 'trash-center',    type: 'trashCan', x: L.centerDesk.x  + 45, y: L.centerDesk.y  + 20 });
    f.push({ id: 'desk-center2',    type: 'desk',     x: L.centerDesk2.x, y: L.centerDesk2.y });
    f.push({ id: 'trash-center2',   type: 'trashCan', x: L.centerDesk2.x + 45, y: L.centerDesk2.y + 20 });
    f.push({ id: 'desk-center3',    type: 'desk',     x: L.centerDesk3.x, y: L.centerDesk3.y });
    f.push({ id: 'trash-center3',   type: 'trashCan', x: L.centerDesk3.x + 45, y: L.centerDesk3.y + 20 });
    // ENG desks + trash
    L.engDesks.forEach(function(d, i) {
        f.push({ id: 'desk-eng-' + i,  type: 'desk',     x: d.x,      y: d.y      });
        f.push({ id: 'trash-eng-' + i, type: 'trashCan', x: d.x + 45, y: d.y + 20 });
    });
    // ENG area items
    f.push({ id: 'eng-couch',        type: 'engLounge',     x: 715,  y: 62  });
    f.push({ id: 'cabinet-eng-0',    type: 'filingCabinet', x: 950,  y: 200 });
    f.push({ id: 'cabinet-eng-1',    type: 'filingCabinet', x: 950,  y: 330 });
    f.push({ id: 'whiteboard-eng',   type: 'whiteboard',    x: 950,  y: 260 });
    // Meeting table (standalone — no room set)
    f.push({ id: 'meeting-table',    type: 'meetingTable',  x: L.meeting.x, y: L.meeting.y });
    // Lounge pieces (individual items, not a set)
    f.push({ id: 'lounge-couch',     type: 'couch',         x: L.lounge.x,  y: L.lounge.y  });
    f.push({ id: 'lounge-table',     type: 'coffeeTable',   x: L.lounge.x + 45, y: L.lounge.y + 35 });
    f.push({ id: 'lounge-tv',        type: 'tv',            x: L.lounge.x + 100, y: L.lounge.y + 10 });
    f.push({ id: 'lounge-bookshelf', type: 'bookshelf',     x: L.lounge.x - 30,  y: L.lounge.y + 30 });
    // Break area pieces (individual items)
    f.push({ id: 'break-vending',    type: 'vendingMachine', x: 740, y: 500 });
    f.push({ id: 'break-cooler',     type: 'waterCooler',    x: 800, y: 510 });
    f.push({ id: 'break-counter',    type: 'kitchenCounter', x: 830, y: 555 });
    // Plants
    f.push({ id: 'tall-plant-0',     type: 'tallPlant',     x: 395,  y: 100 });
    f.push({ id: 'tall-plant-1',     type: 'tallPlant',     x: 605,  y: 100 });
    f.push({ id: 'tall-plant-2',     type: 'tallPlant',     x: 50,   y: 440 });
    f.push({ id: 'tall-plant-3',     type: 'tallPlant',     x: 950,  y: 440 });
    f.push({ id: 'plant-0',          type: 'plant',         x: 370,  y: 400 });
    f.push({ id: 'plant-1',          type: 'plant',         x: 630,  y: 400 });
    f.push({ id: 'plant-2',          type: 'plant',         x: 300,  y: 140 });
    f.push({ id: 'plant-3',          type: 'plant',         x: 700,  y: 140 });
    // Forge desk + trash
    f.push({ id: 'desk-forge',       type: 'desk',     x: L.forgeDesk.x,       y: L.forgeDesk.y       });
    f.push({ id: 'trash-forge',      type: 'trashCan', x: L.forgeDesk.x + 45,  y: L.forgeDesk.y + 20  });
    // Branch signs on walls (default positions — movable/editable)
    var topWall = getRenderedWallSections()[0];
    var defaultBranches = getBranchList().filter(function(b) { return b.id !== 'UNASSIGNED'; });
    for (var _si = 0; _si < defaultBranches.length; _si++) {
        var frac = (_si + 1) / (defaultBranches.length + 1);
        f.push({ id: 'sign-' + defaultBranches[_si].id.toLowerCase(), type: 'branchSign', x: topWall.x + topWall.w * frac, y: 42, branchId: defaultBranches[_si].id });
    }
    // HQ interactive windows (north wall, flanking center)
    f.push({ id: "iw-hq-left",  type: "interactiveWindow", x: 388, y: 10, weather: true, showSun: true });
    f.push({ id: "iw-hq-right", type: "interactiveWindow", x: 576, y: 10, weather: true, showSun: false });
    return f;
}

// --- COMPUTE INTERACTION SPOTS FROM FURNITURE CONFIG ---
// Updates LOCATIONS.interactions in-place so existing agent code keeps working.
// Window spots are wall-based (not furniture) and are left untouched.
function getInteractionSpots() {
    var inter = LOCATIONS.interactions;
    // Reset spots that are derived from furniture items
    inter.couchSeats    = [];
    inter.engCouchSeats = [];
    inter.windows       = [];
    inter.bookshelf     = null;
    inter.tvSpot        = null;
    inter.vendingMachine = null;
    inter.coffeeMaker   = null;
    inter.waterCooler   = null;
    inter.microwave     = null;
    inter.toaster       = null;
    inter.dartBoard     = null;

    officeConfig.furniture.forEach(function(item) {
        var fa = FURNITURE_ACTIONS[item.type];
        if (!fa) return;
        var typeAction = fa.action;
        var rot = item.rotation || 0;
        (fa.spots || []).forEach(function(spot) {
            var action = spot.action || typeAction;
            // Rotate spot offset around item origin
            var rdx = spot.dx, rdy = spot.dy;
            if (rot === 90)       { rdx = -spot.dy; rdy = spot.dx; }
            else if (rot === 180) { rdx = -spot.dx; rdy = -spot.dy; }
            else if (rot === 270) { rdx = spot.dy;  rdy = -spot.dx; }
            var ws = { x: item.x + rdx, y: item.y + rdy, furnitureId: item.id, furnitureType: item.type, action: action };
            if (fa.queue) {
                ws.queueKey = item.type + ':' + (item.id || (Math.round(item.x) + ',' + Math.round(item.y)));
                ws.queueConfig = fa.queue;
            }
            if (spot.faceDir !== undefined) ws.faceDir = spot.faceDir;
            switch (action) {
                case 'sit':
                    if (item.type === 'lounge' || item.type === 'couch') inter.couchSeats.push(ws);
                    else if (item.type === 'engLounge') inter.engCouchSeats.push(ws);
                    break;
                case 'read':      inter.bookshelf     = ws; break;
                case 'watch':     inter.tvSpot        = ws; break;
                case 'vend':      inter.vendingMachine = ws; break;
                case 'coffee':    inter.coffeeMaker   = ws; break;
                case 'drink':     inter.waterCooler   = ws; break;
                case 'microwave': inter.microwave     = ws; break;
                case 'toast':     inter.toaster       = ws; break;
                case 'darts':     inter.dartBoard     = ws; break;
                case 'gaze':      inter.windows.push(ws);  break;
            }
        });
    });
    _updatePongTablePos();
}

// --- INITIALIZE OFFICE CONFIG ---
// Populates furniture from defaults if empty, then syncs interaction spots.
function initOfficeConfig() {
    if (officeConfig.furniture.length === 0) {
        officeConfig.furniture = getDefaultFurniture();
    }
    // Migrate: ensure all furniture items have an id
    officeConfig.furniture.forEach(function(item, idx) {
        if (!item.id) item.id = 'migrated_' + item.type + '_' + idx;
    });
    getInteractionSpots();
    initPets();
}

initOfficeConfig();

// Load server config (async — merges on arrival)
_loadServerConfig();

// Migrate: ensure interior walls array exists
if (!officeConfig.walls.interior) officeConfig.walls.interior = [];
buildCollisionGrid();

// --- AGENT DEFINITIONS ---
// --- AGENT ROSTER (populated dynamically from /api/agents + saved officeConfig) ---
// Fallback roster used if /api/agents hasn't loaded yet
var AGENT_DEFS = [];

// Color palette for auto-assigning agent colors
var _AGENT_COLORS = ['#ffd700','#d32f2f','#1976d2','#388e3c','#f9a825','#e65100','#00897b','#7b1fa2','#6d4c41','#5c6bc0','#78909c','#4caf50','#00bcd4','#e91e90','#ff6d00','#795548','#607d8b','#9c27b0','#009688','#ff5722'];

function _agentConfigKeys(agent) {
    if (!agent) return [];
    var keys = [];
    function add(value) {
        if (value !== undefined && value !== null && String(value).trim()) keys.push(String(value));
    }
    add(agent.id);
    add(agent.statusKey);
    add(agent.agentId);
    var providerKind = String(agent.providerKind || '').trim();
    var providerAgentId = String(agent.providerAgentId || agent.profile || '').trim();
    if (providerKind && providerAgentId) add(providerKind + '-' + providerAgentId);
    if (!providerKind || providerKind === 'openclaw') {
        add(agent.providerAgentId);
        add(agent.profile);
    }
    return Array.from(new Set(keys));
}

function _agentConfigMatches(saved, agent) {
    if (!saved || !agent) return false;
    var savedKeys = _agentConfigKeys(saved);
    var agentKeys = _agentConfigKeys(agent);
    return savedKeys.some(function(k) { return agentKeys.indexOf(k) >= 0; });
}

function _findOfficeAgentConfig(agent) {
    var savedAgents = (officeConfig && officeConfig.agents) || [];
    return savedAgents.find(function(saved) { return _agentConfigMatches(saved, agent); }) || null;
}

function _buildAgentDefs(apiAgents) {
    // Build AGENT_DEFS from API response, merging with saved officeConfig.agents for overrides
    var defs = [];
    apiAgents.forEach(function(a, idx) {
        var saved = _findOfficeAgentConfig(a) || {};
        defs.push({
            id: a.statusKey || a.id,
            statusKey: a.statusKey || a.id,
            providerKind: a.providerKind || 'openclaw',
            providerType: a.providerType || 'runtime',
            providerAgentId: a.providerAgentId || a.id,
            profile: a.profile || a.providerAgentId || '',
            provider: a.provider || '',
            name: saved.name || a.name || a.id,
            emoji: saved.emoji || a.emoji || '🤖',
            role: saved.role || a.role || '',
            branch: saved.branch || 'UNASSIGNED',
            color: saved.color || _AGENT_COLORS[idx % _AGENT_COLORS.length],
            gender: saved.gender || (idx % 2 === 0 ? 'M' : 'F'),
        });
    });
    return defs;
}

// Auto-assign desk positions for any number of agents
function _autoAssignDesks(agentDefs) {
    // Check for furniture desk assignments first
    var assigned = {};
    if (officeConfig && officeConfig.furniture) {
        officeConfig.furniture.forEach(function(f) {
            if (f.assignedTo && (f.type === 'desk' || f.type === 'bossDesk')) {
                assigned[f.assignedTo] = { x: f.x, y: f.y };
            }
        });
    }

    // For unassigned agents, generate grid positions
    var unassigned = agentDefs.filter(function(a) { return !assigned[a.id] && !assigned[a.statusKey]; });
    var gridStartX = 140, gridStartY = 200;
    var colSpacing = 160, rowSpacing = 120;
    var cols = Math.max(2, Math.ceil(Math.sqrt(unassigned.length)));

    unassigned.forEach(function(a, idx) {
        var col = idx % cols;
        var row = Math.floor(idx / cols);
        assigned[a.statusKey || a.id] = {
            x: gridStartX + col * colSpacing,
            y: gridStartY + row * rowSpacing
        };
    });

    // Apply to defs
    agentDefs.forEach(function(a) {
        var desk = assigned[a.id] || assigned[a.statusKey];
        if (desk) {
            a._autoDesk = desk;
        }
    });
}

// Fetch roster from server
var _rosterLoaded = false;
function _fetchRoster() {
    fetch('/api/agents').then(function(r) { return r.json(); }).then(function(data) {
        if (data.agents && data.agents.length > 0) {
            AGENT_DEFS = _buildAgentDefs(data.agents);
            _autoAssignDesks(AGENT_DEFS);
            if (!_rosterLoaded) {
                _rosterLoaded = true;
                _initAgentsFromDefs();
            }
        }
    }).catch(function(e) { console.warn('Failed to fetch roster:', e); });
}

// --- AGENT APPEARANCE DEFAULTS ---
// Accepts either an agent object or (agentId, gender) for backward compatibility.
function getDefaultAppearance(agentOrId, gender) {
    const agentId = typeof agentOrId === 'string' ? agentOrId : agentOrId.id;
    const g = typeof agentOrId === 'string' ? gender : agentOrId.gender;
    // Generate deterministic appearance from agent ID (seeded pseudo-random)
    function _hashCode(s) { var h = 0; for (var i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0; return Math.abs(h); }
    var _h = _hashCode(agentId);
    var _skinTones = ['#ffcc80','#d4a574','#c68642','#e8b88a','#fddcb5','#f5d0b0','#8d5524','#c68642'];
    var _hairStyles = ['short','medium','long','curly','spiky','buzz','wavy'];
    var _hairColors = ['#1a1a1a','#333333','#5d4037','#616161','#bf360c','#dcc282','#ffd700','#263238'];
    var _deskItems = ['trophy','envelope','calendar','chart','plans','checklist','files','ruler','money','marker'];
    // Use saved config appearance if available
    if (officeConfig && officeConfig.agents) {
        var saved = officeConfig.agents.find(function(a) { return a.id === agentId || a.statusKey === agentId; });
        if (saved && saved.appearance) return saved.appearance;
    }
    return {
        skinTone: _skinTones[_h % _skinTones.length],
        hairStyle: g === 'F' ? _hairStyles[(_h >> 3) % 3 + 2] : _hairStyles[(_h >> 3) % _hairStyles.length],
        hairColor: _hairColors[(_h >> 5) % _hairColors.length],
        hairHighlight: null,
        eyebrowStyle: g === 'F' ? 'thin' : 'thick',
        eyeColor: '#212121',
        facialHair: null, facialHairColor: null,
        headwear: null, headwearColor: null,
        glasses: null, glassesColor: null,
        costume: null,
        heldItem: null,
        deskItem: _deskItems[(_h >> 8) % _deskItems.length]
    };
}

// --- HAIR DRAWING ---
function _drawHairByConfig(ctx, style, hairColor, hairHighlight) {
    const hc = hairColor || '#333333';
    const hl = hairHighlight || null;
    switch (style) {
        case 'bald':
            break;
        case 'buzz':
            ctx.fillStyle = hc;
            ctx.fillRect(-12, -40, 24, 4);
            ctx.fillRect(-13, -38, 3, 4); ctx.fillRect(10, -38, 3, 4);
            break;
        case 'short':
            ctx.fillStyle = hc;
            ctx.fillRect(-13, -40, 26, 5);
            ctx.fillRect(-14, -36, 4, 6); ctx.fillRect(10, -36, 4, 6);
            if (hl) { ctx.fillStyle = hl; ctx.fillRect(-6, -42, 4, 3); ctx.fillRect(2, -43, 4, 3); }
            break;
        case 'medium':
            ctx.fillStyle = hc;
            ctx.fillRect(-13, -40, 26, 4);
            ctx.fillRect(-14, -38, 4, 8); ctx.fillRect(10, -38, 4, 8);
            if (hl) { ctx.fillStyle = hl; ctx.fillRect(-6, -43, 4, 3); ctx.fillRect(2, -44, 4, 3); }
            break;
        case 'long':
            ctx.fillStyle = hc;
            ctx.fillRect(-13, -42, 26, 6);
            ctx.fillRect(-14, -38, 4, 14); ctx.fillRect(10, -38, 4, 14);
            if (hl) {
                ctx.fillStyle = hl;
                ctx.fillRect(-14, -38, 4, 12);
                ctx.fillRect(-8, -43, 16, 4);
            }
            break;
        case 'curly':
            ctx.fillStyle = hc;
            ctx.fillRect(-13, -42, 26, 6);
            ctx.fillRect(-14, -38, 4, 6); ctx.fillRect(10, -38, 4, 6);
            ctx.fillStyle = hl || hc;
            ctx.fillRect(-10, -43, 4, 3); ctx.fillRect(0, -44, 4, 3); ctx.fillRect(7, -43, 4, 3);
            break;
        case 'wavy':
            ctx.fillStyle = hc;
            ctx.fillRect(-13, -42, 26, 6);
            ctx.fillRect(-14, -38, 4, 8); ctx.fillRect(10, -38, 4, 8);
            ctx.fillStyle = hl || hc;
            ctx.fillRect(-8, -43, 4, 3); ctx.fillRect(4, -43, 4, 3);
            if (hl) { ctx.fillRect(-14, -28, 3, 4); ctx.fillRect(11, -26, 3, 4); }
            break;
        case 'bun':
            ctx.fillStyle = hc;
            ctx.fillRect(-12, -41, 24, 5);
            ctx.fillRect(-14, -38, 4, 4); ctx.fillRect(10, -38, 4, 4);
            ctx.fillRect(-5, -46, 10, 6); ctx.fillRect(-4, -48, 8, 4);
            if (hl) { ctx.fillStyle = hl; ctx.fillRect(-3, -47, 6, 2); }
            break;
        case 'ponytail':
            ctx.fillStyle = hc;
            ctx.fillRect(-12, -41, 24, 5);
            ctx.fillRect(-13, -38, 3, 6); ctx.fillRect(10, -38, 3, 6);
            ctx.fillRect(12, -38, 4, 18); ctx.fillRect(13, -20, 3, 6);
            if (hl) { ctx.fillStyle = hl; ctx.fillRect(12, -38, 2, 12); }
            break;
        case 'spiky':
            // Three spikes for a distinct 2D hairstyle.
            ctx.fillStyle = hc;
            ctx.fillRect(-12, -41, 24, 5);            // main hair volume
            ctx.fillRect(-13, -38, 26, 2);            // lower edge
            ctx.fillRect(-8, -45, 4, 4);              // left spike
            ctx.fillRect(-1, -47, 4, 6);              // center spike
            ctx.fillRect(6, -45, 4, 4);               // right spike
            ctx.fillStyle = hl || _lighten(hc, 0.2);  // subtle highlight
            ctx.fillRect(-6, -41, 12, 2);
            break;
        case 'mohawk':
            // Tall center strip only
            ctx.fillStyle = hc;
            ctx.fillRect(-12, -40, 24, 2);            // thin base
            ctx.fillRect(-3, -50, 6, 12);             // tall center strip
            if (hl) { ctx.fillStyle = hl; ctx.fillRect(-1, -50, 4, 8); }
            break;
        default:
            ctx.fillStyle = hc;
            ctx.fillRect(-13, -40, 26, 5);
            ctx.fillRect(-14, -36, 4, 8); ctx.fillRect(10, -36, 4, 8);
            break;
    }
}

// --- COSTUME DRAWING (cached to offscreen canvas) ---
var _costumeCache = {};
function _drawCostume(ctx, costume) {
    if (!costume) return;
    var key = costume;
    if (!_costumeCache[key]) {
        var oc = document.createElement('canvas');
        oc.width = 80; oc.height = 80;
        var c2 = oc.getContext('2d');
        c2.translate(40, 60);
        _drawCostumeDirect(c2, costume);
        _costumeCache[key] = oc;
    }
    ctx.drawImage(_costumeCache[key], -40, -60, 80, 80);
}
function _drawCostumeDirect(ctx, costume) {
    switch (costume) {
        case 'lobster': {
            var lc = '#d32f2f', ld = '#a51c1c', ll = '#e05555';
            // Hood body
            ctx.fillStyle = lc;
            ctx.fillRect(-16, -46, 32, 12);
            ctx.fillRect(-18, -42, 36, 6);
            ctx.fillStyle = ld;
            ctx.fillRect(-16, -36, 32, 2);
            // Cheek flaps
            ctx.fillStyle = lc;
            ctx.fillRect(-18, -36, 5, 8);
            ctx.fillRect(13, -36, 5, 8);
            ctx.fillStyle = ld;
            ctx.fillRect(-18, -28, 5, 2);
            ctx.fillRect(13, -28, 5, 2);
            // Antennae
            ctx.fillStyle = lc;
            ctx.fillRect(-8, -52, 2, 6);
            ctx.fillRect(6, -52, 2, 6);
            ctx.fillStyle = ll;
            ctx.fillRect(-10, -54, 3, 3);
            ctx.fillRect(7, -54, 3, 3);
            // Claws
            ctx.fillStyle = lc;
            ctx.fillRect(-14, -50, 5, 4);
            ctx.fillRect(9, -50, 5, 4);
            ctx.fillStyle = ld;
            ctx.fillRect(-16, -52, 3, 3);
            ctx.fillRect(-14, -52, 3, 3);
            ctx.fillRect(11, -52, 3, 3);
            ctx.fillRect(13, -52, 3, 3);
            // Hood eyes
            ctx.fillStyle = '#fff';
            ctx.fillRect(-6, -48, 4, 3);
            ctx.fillRect(2, -48, 4, 3);
            ctx.fillStyle = '#111';
            ctx.fillRect(-5, -47, 2, 2);
            ctx.fillRect(3, -47, 2, 2);
            break;
        }
        case 'chicken': {
            var cc = '#ffd54f', cd = '#e6bf3a';
            // Hood body
            ctx.fillStyle = cc;
            ctx.fillRect(-16, -46, 32, 12);
            ctx.fillRect(-18, -42, 36, 6);
            ctx.fillStyle = cd;
            ctx.fillRect(-16, -36, 32, 2);
            // Cheek flaps
            ctx.fillStyle = cc;
            ctx.fillRect(-18, -36, 5, 7);
            ctx.fillRect(13, -36, 5, 7);
            // Red comb
            ctx.fillStyle = '#e53935';
            ctx.fillRect(-4, -54, 3, 4);
            ctx.fillRect(-1, -56, 3, 6);
            ctx.fillRect(2, -53, 3, 3);
            ctx.fillStyle = '#c62828';
            ctx.fillRect(-4, -50, 9, 4);
            // Beak
            ctx.fillStyle = '#ff8f00';
            ctx.fillRect(-2, -43, 4, 3);
            ctx.fillStyle = '#ff6f00';
            ctx.fillRect(-1, -40, 3, 2);
            // Hood eyes
            ctx.fillStyle = '#fff';
            ctx.fillRect(-8, -47, 4, 3);
            ctx.fillRect(4, -47, 4, 3);
            ctx.fillStyle = '#111';
            ctx.fillRect(-7, -46, 2, 2);
            ctx.fillRect(5, -46, 2, 2);
            // Wattle
            ctx.fillStyle = '#e53935';
            ctx.fillRect(-1, -38, 2, 3);
            break;
        }
    }
}

// --- HEADWEAR DRAWING ---
function _drawHeadwear(ctx, headwear, color, isMoving) {
    if (!headwear) return;
    const c = color || '#888888';
    switch (headwear) {
        case 'hardhat':
            ctx.fillStyle = c; ctx.fillRect(-14, -42, 28, 4);
            ctx.fillStyle = _lighten(c, 0.15); ctx.fillRect(-10, -46, 20, 5);
            ctx.fillStyle = '#fff'; ctx.fillRect(-6, -44, 12, 2);
            break;
        case 'cap':
            ctx.fillStyle = c; ctx.fillRect(-10, -40, 20, 3);
            ctx.fillStyle = _darkenColor(c, 0.2); ctx.fillRect(-12, -40, 24, 2);
            break;
        case 'crown':
            ctx.fillStyle = c; ctx.fillRect(-9, -43, 18, 4);
            ctx.fillStyle = _lighten(c, 0.2);
            ctx.fillRect(-7, -47, 4, 4); ctx.fillRect(-1, -48, 4, 5); ctx.fillRect(5, -47, 4, 4);
            ctx.fillStyle = '#e53935'; ctx.fillRect(-5, -44, 2, 2); ctx.fillRect(0, -45, 2, 2); ctx.fillRect(6, -44, 2, 2);
            break;
        case 'tiara':
            ctx.fillStyle = c; ctx.fillRect(-9, -44, 18, 2);
            ctx.fillStyle = _darkenColor(c, 0.2); ctx.fillRect(-7, -46, 3, 2); ctx.fillRect(4, -46, 3, 2);
            ctx.fillStyle = c; ctx.fillRect(-2, -47, 4, 3);
            ctx.fillStyle = '#ff6d00'; ctx.fillRect(-1, -46, 2, 2);
            break;
        case 'headband':
            ctx.fillStyle = c; ctx.fillRect(-12, -41, 24, 3);
            break;
        case 'goggles':
            ctx.fillStyle = c; ctx.fillRect(-10, -42, 20, 3);
            ctx.fillStyle = '#81d4fa'; ctx.fillRect(-8, -42, 7, 4);
            ctx.fillStyle = '#81d4fa'; ctx.fillRect(1, -42, 7, 4);
            ctx.fillStyle = '#37474f'; ctx.fillRect(-1, -42, 2, 4);
            ctx.fillStyle = '#263238'; ctx.fillRect(-9, -42, 1, 4); ctx.fillRect(8, -42, 1, 4);
            break;
        case 'headset':
            ctx.strokeStyle = color || '#333';
            ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.arc(0, -34, 14, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
            ctx.fillStyle = color || '#333';
            ctx.fillRect(-14, -30, 4, 6); ctx.fillRect(10, -30, 4, 6);
            ctx.strokeStyle = '#555'; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(-14, -27); ctx.lineTo(-16, -24); ctx.stroke();
            ctx.fillStyle = color || '#333'; ctx.fillRect(-18, -25, 3, 3);
            break;
        case 'beanie':
            ctx.fillStyle = c; ctx.fillRect(-13, -43, 26, 7);
            ctx.fillStyle = _darkenColor(c, 0.15); ctx.fillRect(-13, -41, 26, 2);
            ctx.fillStyle = _lighten(c, 0.2); ctx.fillRect(-6, -44, 12, 2);
            ctx.fillStyle = c; ctx.fillRect(-4, -47, 8, 4);
            break;


    }
}

// --- GLASSES DRAWING ---
function _drawGlasses(ctx, glasses, color, eyeShift) {
    if (!glasses) return;
    const c = color || '#333';
    const es = eyeShift || 0;
    switch (glasses) {
        case 'round':
            ctx.strokeStyle = c; ctx.lineWidth = 1;
            ctx.strokeRect(-7 + es, -32, 6, 4); ctx.strokeRect(3 + es, -32, 6, 4);
            ctx.beginPath(); ctx.moveTo(-1 + es, -30); ctx.lineTo(3 + es, -30); ctx.stroke();
            break;
        case 'square':
            ctx.strokeStyle = c; ctx.lineWidth = 1;
            ctx.strokeRect(-6 + es, -32, 5, 4); ctx.strokeRect(3 + es, -32, 5, 4);
            ctx.beginPath(); ctx.moveTo(-1 + es, -30); ctx.lineTo(3 + es, -30); ctx.stroke();
            break;
        case 'sunglasses':
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(-7 + es, -32, 6, 4); ctx.fillRect(3 + es, -32, 6, 4);
            ctx.fillStyle = c;
            ctx.fillRect(-8 + es, -33, 7, 1); ctx.fillRect(2 + es, -33, 7, 1);
            ctx.fillRect(-1 + es, -31, 2, 1);
            break;
    }
}

// --- HELD ITEM DRAWING ---
function _drawHeldItem(ctx, item, isMoving) {
    if (!item || isMoving) return;
    const ix = 13, iy = -18;
    switch (item) {
        case 'tablet':
            ctx.fillStyle = '#263238'; ctx.fillRect(ix - 1, iy, 7, 10);
            ctx.fillStyle = '#4fc3f7'; ctx.fillRect(ix, iy + 1, 5, 7);
            ctx.fillStyle = '#81d4fa'; ctx.fillRect(ix + 1, iy + 3, 3, 2);
            break;
        case 'wrench':
            ctx.fillStyle = '#90a4ae'; ctx.fillRect(ix, iy + 2, 2, 8);
            ctx.fillStyle = '#b0bec5'; ctx.fillRect(ix - 1, iy, 4, 3);
            ctx.fillStyle = '#78909c'; ctx.fillRect(ix, iy + 1, 2, 1);
            break;
        case 'clipboard':
            ctx.fillStyle = '#795548'; ctx.fillRect(ix - 1, iy, 7, 9);
            ctx.fillStyle = '#fff'; ctx.fillRect(ix, iy + 1, 5, 6);
            ctx.fillStyle = '#795548'; ctx.fillRect(ix + 1, iy, 3, 2);
            ctx.fillStyle = '#aaa'; ctx.fillRect(ix + 1, iy + 2, 3, 1); ctx.fillRect(ix + 1, iy + 4, 3, 1);
            break;
        case 'pen':
            ctx.fillStyle = '#f44336'; ctx.fillRect(-14, iy + 2, 2, 8);
            ctx.fillStyle = '#fff'; ctx.fillRect(-14, iy + 2, 2, 2);
            break;
        case 'hammer':
            ctx.fillStyle = '#8d6e63'; ctx.fillRect(ix, iy + 2, 2, 9);
            ctx.fillStyle = '#78909c'; ctx.fillRect(ix - 2, iy, 6, 4);
            ctx.fillStyle = '#546e7a'; ctx.fillRect(ix - 1, iy + 1, 4, 2);
            break;
        case 'testTube':
            ctx.fillStyle = '#81d4fa'; ctx.fillRect(ix, iy + 1, 3, 9);
            ctx.fillStyle = '#4caf50'; ctx.fillRect(ix, iy + 5, 3, 5);
            ctx.fillStyle = '#b0bec5'; ctx.fillRect(ix - 1, iy, 5, 2);
            break;
        case 'coffee':
            ctx.fillStyle = '#fff'; ctx.fillRect(ix - 1, iy + 1, 8, 9);
            ctx.fillStyle = '#6d4c41'; ctx.fillRect(ix, iy + 2, 6, 5);
            ctx.fillStyle = '#fff'; ctx.fillRect(ix + 6, iy + 3, 3, 3);
            break;
        case 'book':
            ctx.fillStyle = '#1565c0'; ctx.fillRect(ix - 1, iy, 8, 11);
            ctx.fillStyle = '#1976d2'; ctx.fillRect(ix, iy + 1, 6, 9);
            ctx.fillStyle = '#fff'; ctx.fillRect(ix + 1, iy + 2, 4, 1); ctx.fillRect(ix + 1, iy + 4, 3, 1);
            break;
    }
}

// --- FACIAL HAIR DRAWING ---
function _drawFacialHair(ctx, facialHair, facialHairColor) {
    if (!facialHair) return;
    const c = facialHairColor || '#3e2723';
    switch (facialHair) {
        case 'stubble':
            // Scattered small dots on jaw area
            ctx.fillStyle = c;
            ctx.fillRect(-4, -24, 2, 1); ctx.fillRect(0, -24, 2, 1); ctx.fillRect(3, -24, 2, 1);
            ctx.fillRect(-3, -25, 1, 1); ctx.fillRect(2, -25, 1, 1);
            break;
        case 'beard':
            // Filled rectangle covering lower jaw
            ctx.fillStyle = c;
            ctx.fillRect(-4, -25, 8, 4);
            break;
        case 'goatee':
            // Small chin patch
            ctx.fillStyle = c;
            ctx.fillRect(-2, -24, 4, 3);
            break;
        case 'mustache':
            // Line above mouth
            ctx.fillStyle = c;
            ctx.fillRect(-3, -26, 6, 1);
            break;
    }
}

// --- COLOR HELPERS ---
function _lighten(hex, amt) {
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    r = Math.min(255, Math.floor(r + (255 - r) * amt));
    g = Math.min(255, Math.floor(g + (255 - g) * amt));
    b = Math.min(255, Math.floor(b + (255 - b) * amt));
    return '#' + [r,g,b].map(v => v.toString(16).padStart(2,'0')).join('');
}
function _lightenColor(hex, pct) {
    var r = parseInt(hex.slice(1,3), 16), g = parseInt(hex.slice(3,5), 16), b = parseInt(hex.slice(5,7), 16);
    r = Math.min(255, r + Math.round((255 - r) * pct / 100));
    g = Math.min(255, g + Math.round((255 - g) * pct / 100));
    b = Math.min(255, b + Math.round((255 - b) * pct / 100));
    return '#' + [r,g,b].map(function(v){ return v.toString(16).padStart(2,'0'); }).join('');
}
function _darkenColor(hex, amt) {
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    r = Math.floor(r * (1 - amt)); g = Math.floor(g * (1 - amt)); b = Math.floor(b * (1 - amt));
    return '#' + [r,g,b].map(v => v.toString(16).padStart(2,'0')).join('');
}
function _hexToRgb(hex) {
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    return { r, g, b };
}

// --- AGENT CLASS ---

class Agent {
    constructor(def) {
        Object.assign(this, def);
        // Default appearance if not provided by def
        if (!this.appearance) {
            this.appearance = getDefaultAppearance(this);
        }
        // Desk assignment: prefer auto-assigned desk, then named desk types, then branch desks
        if (this._autoDesk) {
            this.desk = this._autoDesk;
        } else if (this.deskType === 'boss' && LOCATIONS.bossDesk) {
            this.desk = LOCATIONS.bossDesk;
        } else if (this.deskType === 'center' && LOCATIONS.centerDesk) {
            this.desk = LOCATIONS.centerDesk;
        } else if (this.deskType === 'center2' && LOCATIONS.centerDesk2) {
            this.desk = LOCATIONS.centerDesk2;
        } else if (this.deskType === 'center3' && LOCATIONS.centerDesk3) {
            this.desk = LOCATIONS.centerDesk3;
        } else if (this.deskType === 'forge' && LOCATIONS.forgeDesk) {
            this.desk = LOCATIONS.forgeDesk;
        } else if (this.branch === 'PQ' && LOCATIONS.pqDesks && LOCATIONS.pqDesks[this.deskIdx]) {
            this.desk = LOCATIONS.pqDesks[this.deskIdx];
        } else if (LOCATIONS.engDesks && LOCATIONS.engDesks[this.deskIdx]) {
            this.desk = LOCATIONS.engDesks[this.deskIdx];
        } else {
            // Fallback: center of canvas
            this.desk = { x: Math.floor(W / 2), y: Math.floor(H / 2) };
        }

        this.x = this.desk.x;
        this.y = this.desk.y;
        this.targetX = this.x;
        this.targetY = this.y;
        this.state = 'idle';
        this.task = '';
        this.thought = '';
        this.speech = '';
        this.speechTarget = '';
        this.thoughtChars = 0;
        this.speechChars = 0;
        this.thoughtAge = 0;
        this.thoughtUpdatedAt = 0;
        this.speechAge = 0;
        this.lastThought = '';
        this.lastSpeech = '';
        this.lastSpeechTarget = '';
        this.faceDir = (this.desk && this.desk.x > W / 2) ? -1 : 1;
        this.tick = Math.floor(Math.random() * 1000);
        this.blinkTimer = 0;
        this.talkTimer = 0;
        this.isSitting = true;
        this.speed = 1.6 + Math.random() * 0.8;
        this.intentHistory = ['System initialized.'];
        this.logHistory = [`[${timeStr()}] Boot sequence complete.`];

        // --- Autonomous behavior ---
        this.idleTimer = 0;
        this.idleAction = null;
        this.idleReturnTimer = 0;
        this.resetIdleTimer();

        // --- Carry item system ---
        this.carryItem = null;        // 'coffee', 'water', 'snack'
        this.snackType = null;        // 'candy', 'chips', 'cookies', 'chocolate'
        this.foodType = null;         // 'sandwich', 'popcorn', 'pizza'
        this.foodSource = null;       // 'microwave' | 'toaster'
        this.carryItemTimer = 0;     // ticks to show item at desk
        this.idleFaceDir = null;     // forced face dir during idle action
        this.interactTimer = 0;      // animation ticks at interaction spot
        this.objectQueueKey = null;  // concrete queued object key, if waiting/using a queueable object
        this.objectQueueAction = null;
        this.objectQueueTarget = null;
        this.objectQueueSlot = null;

        // --- Break room browsing ---
        this.breakPhase = 0;         // 0=entering, 1+=browsing items, final=using
        this.breakStops = 0;         // items checked so far
        this.breakMaxStops = 0;      // how many to check before deciding
        this.breakChoice = null;     // final: 'snack','coffee','water'
        this.breakPauseTimer = 0;    // ticks to pause at each browse spot

        // --- Desk idle variety (each agent has unique offset) ---
        this.deskIdlePose = 0; // 0=scratch head, 1=yawn (yawn is rare)
        this.deskIdleTimer = 300 + Math.floor(Math.random() * 900); // randomized per agent

        // --- Social proximity ---
        this.socialTarget = null;    // id of nearby agent to face

        // --- Meeting state ---
        this.meetingId = null;
        this.meetingSlot = null;
        this.visitTarget = null;
        this._meetingTurnTimer = 0;
        this._meetingLastSpeakerKey = '';

        // --- Notification / Task I/O ---
        this.notify = false;          // pulsing notification light
        this.lastInput = null;        // { from: 'User', text: '...' }
        this.lastOutput = null;       // { text: '...' }

        // --- Pathfinding ---
        this._path = null;
        this._prevTargetX = undefined;
        this._prevTargetY = undefined;
    }

    resetIdleTimer() {
        // 15-45 seconds at 60fps = 900-2700 ticks
        this.idleTimer = 3600 + Math.floor(Math.random() * 3600); // 1-2 min at 60fps
    }

    getAppearance() {
        // Check for per-agent config override (used by the appearance panel)
        const cfg = _findOfficeAgentConfig(this);
        if (cfg && cfg.appearance) return cfg.appearance;
        // Use the pre-computed instance appearance (set in constructor)
        return this.appearance || getDefaultAppearance(this);
    }

    update() {
        // Safety: ensure desk reference is never null
        if (!this.desk) this.desk = { x: Math.floor(W / 2), y: Math.floor(H / 2) };
        this.tick++;
        // --- PATH FOLLOWING: recompute when target changes ---
        if (this._prevTargetX === undefined) { this._prevTargetX = this.targetX; this._prevTargetY = this.targetY; this._path = null; }
        if (this.targetX !== this._prevTargetX || this.targetY !== this._prevTargetY) {
            this._prevTargetX = this.targetX;
            this._prevTargetY = this.targetY;
            if (collisionGrid && officeConfig.walls.interior && officeConfig.walls.interior.length > 0) {
                var _fp = findPath(this.x, this.y, this.targetX, this.targetY);
                this._path = (_fp && _fp.length > 0) ? _fp : null;
            } else {
                this._path = null;
            }
        }
        // Advance path: skip waypoints we've passed
        if (this._path && this._path.length > 0) {
            var _wp = this._path[0];
            if (Math.abs(_wp.x - this.x) < this.speed * 2 && Math.abs(_wp.y - this.y) < this.speed * 2) {
                this._path.shift();
            }
        }
        // Effective target: next waypoint or final target
        var _etX = this.targetX, _etY = this.targetY;
        if (this._path && this._path.length > 0) {
            _etX = this._path[0].x;
            _etY = this._path[0].y;
        }
        const dx = _etX - this.x;
        const dy = _etY - this.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > this.speed) {
            let moveX = (dx / dist) * this.speed;
            let moveY = (dy / dist) * this.speed;
            // --- COLLISION: steer around nearby agents while walking ---
            if (COLLISION_ENABLED) {
                for (let i = 0; i < agents.length; i++) {
                    const other = agents[i];
                    if (other.id === this.id) continue;
                    const ox = this.x - other.x, oy = this.y - other.y;
                    const oDist = Math.sqrt(ox * ox + oy * oy);
                    if (oDist < COLLISION_RADIUS * 2 && oDist > 0.1) {
                        const force = COLLISION_PUSH * (1 - oDist / (COLLISION_RADIUS * 2));
                        moveX += (ox / oDist) * force;
                        moveY += (oy / oDist) * force;
                    }
                }
            }

            // --- STUCK DETECTION: if barely moving for too long, maneuver around ---
            var prevX = this.x, prevY = this.y;
            this.x += moveX;
            this.y += moveY;
            // Clamp: don't walk into the top wall zone
            if (this.y < 20) this.y = 20;
            var actualMove = Math.sqrt((this.x - prevX) * (this.x - prevX) + (this.y - prevY) * (this.y - prevY));
            if (!this._stuckTicks) this._stuckTicks = 0;
            if (!this._detourAngle) this._detourAngle = 0;

            if (actualMove < this.speed * 0.3 && dist > 10) {
                // Barely moving — agent is stuck
                this._stuckTicks++;
                if (this._stuckTicks > 30) {
                    // Try perpendicular detour (alternate left/right)
                    if (this._stuckTicks === 31) {
                        this._detourAngle = (Math.random() > 0.5 ? 1 : -1) * (Math.PI / 2);
                    }
                    var detourX = Math.cos(Math.atan2(dy, dx) + this._detourAngle) * this.speed * 1.5;
                    var detourY = Math.sin(Math.atan2(dy, dx) + this._detourAngle) * this.speed * 1.5;
                    this.x += detourX;
                    this.y += detourY;
                }
                // If stuck way too long, give up and pick a new action
                if (this._stuckTicks > 120) {
                    this._stuckTicks = 0;
                    this._detourAngle = 0;
                    if (this.idleAction && this.state === 'idle') {
                        // Abort current idle action — go back to desk or pick something else
                        releaseObjectServiceQueueForAgent(this, 'blocked');
                        this.idleAction = null;
                        this.breakPhase = null;
                        this.breakStops = 0;
                        this.interactTimer = 0;
                        this.targetX = this.desk.x;
                        this.targetY = this.desk.y;
                        this.addLog('Gave up — path blocked, heading back');
                    }
                }
            } else {
                this._stuckTicks = 0;
                this._detourAngle = 0;
            }

            this.isSitting = false;
            if (Math.abs(dx) > 0.5) this.faceDir = dx > 0 ? 1 : -1;
        } else {
            if (this._path && this._path.length > 0) {
                // Reached a waypoint - advance
                this.x = _etX;
                this.y = _etY;
                this._path.shift();
                if (this._path.length === 0) {
                    this._path = null;
                    this.x = this.targetX;
                    this.y = this.targetY;
                    this.onArrive();
                }
            } else {
                if (this.x !== this.targetX || this.y !== this.targetY) {
                    this.x = this.targetX;
                    this.y = this.targetY;
                    this.onArrive();
                }
            }
        }

        // --- COLLISION: static separation (push apart when standing too close) ---
        if (COLLISION_ENABLED && !this.isSitting) {
            for (let i = 0; i < agents.length; i++) {
                const other = agents[i];
                if (other.id === this.id || other.isSitting) continue;
                const ox = this.x - other.x, oy = this.y - other.y;
                const oDist = Math.sqrt(ox * ox + oy * oy);
                if (oDist < COLLISION_RADIUS && oDist > 0.1) {
                    // Strong push — guaranteed separation
                    const push = 1.2 * (1 - oDist / COLLISION_RADIUS);
                    this.x += (ox / oDist) * push;
                    this.y += (oy / oDist) * push;
                } else if (oDist < COLLISION_RADIUS * 1.5 && oDist > 0.1) {
                    // Gentle nudge in buffer zone to prevent clumping
                    const nudge = 0.3 * (1 - oDist / (COLLISION_RADIUS * 1.5));
                    this.x += (ox / oDist) * nudge;
                    this.y += (oy / oDist) * nudge;
                }
            }
        }

        startObjectServiceIfReady(this);

        // --- Autonomous idle wandering ---
        if (this.state === 'idle' && !this.meetingId && !this.idleAction) {
            this.idleTimer--;
            if (this.idleTimer <= 0) {
                this.startIdleAction();
            }
            // Desk idle pose variety (per-agent random timing)
            if (this.isSitting) {
                this.deskIdleTimer--;
                if (this.deskIdleTimer <= 0) {
                    // Pick a different pose than current
                    // Yawn is rare (~15% chance), scratch head is default
                    const newPose = Math.random() < 0.15 ? 1 : 0;
                    this.deskIdlePose = newPose;
                    this.deskIdleTimer = 240 + Math.floor(Math.random() * 900); // 4-19s, wide spread
                }
            }
        }

        // --- Return from idle action ---
        if (this.idleAction && this.idleReturnTimer > 0) {
            this.idleReturnTimer--;
            if (this.idleReturnTimer <= 0) {
                this.returnToDesk();
            }
        }

        // --- Interaction animation timer ---
        if (this.idleAction) this.interactTimer++;
        else this.interactTimer = 0;

        // --- Carry item countdown at desk ---
        if (this.carryItemTimer > 0) {
            this.carryItemTimer--;
            if (this.carryItemTimer <= 0) {
                this.carryItem = null;
            }
        }

        // --- Break room browsing phase system ---
        if (this.idleAction === 'break_browse') {
            const atTarget = Math.abs(this.x - this.targetX) < 3 && Math.abs(this.y - this.targetY) < 3;
            if (atTarget) {
                if (this.breakPauseTimer > 0) {
                    this.breakPauseTimer--;
                } else {
                    const inter = LOCATIONS.interactions;
                    if (this.breakStops < this.breakMaxStops) {
                        // Pick a random item to go look at
                        const spots = [];
                        if (inter.vendingMachine) spots.push({ x: inter.vendingMachine.x, y: inter.vendingMachine.y, label: 'vending machine', item: 'snack' });
                        if (inter.coffeeMaker) spots.push({ x: inter.coffeeMaker.x, y: inter.coffeeMaker.y, label: 'coffee maker', item: 'coffee' });
                        if (inter.waterCooler) spots.push({ x: inter.waterCooler.x, y: inter.waterCooler.y, label: 'water cooler', item: 'water' });
                        if (inter.microwave) spots.push({ x: inter.microwave.x, y: inter.microwave.y, label: 'microwave', item: 'food' });
                        if (inter.toaster) spots.push({ x: inter.toaster.x, y: inter.toaster.y, label: 'toaster', item: 'food' });
                        if (spots.length === 0) { this.returnToDesk(); return; }
                        // Wander to a spot they haven't been to yet (or random if revisiting)
                        const spot = spots[Math.floor(Math.random() * spots.length)];
                        this.targetX = spot.x + (Math.random() - 0.5) * 15;
                        this.targetY = spot.y + (Math.random() - 0.5) * 10;
                        this.breakChoice = spot.item; // tentative choice updates as they browse
                        this.breakStops++;
                        this.breakPauseTimer = 240 + Math.floor(Math.random() * 360); // 4-10s pause at each item
                        this.addIntent(`Checking out the ${spot.label}...`);
                    } else {
                        // Done browsing — commit to final choice and use the machine
                        const finalItems = ['snack', 'coffee', 'water', 'food'];
                        const choice = this.breakChoice || finalItems[Math.floor(Math.random() * finalItems.length)];
                        let target;
                        let targetFurnitureType;
                        this.foodSource = null;
                        if (choice === 'snack') { target = inter.vendingMachine; targetFurnitureType = 'vendingMachine'; }
                        else if (choice === 'coffee') { target = inter.coffeeMaker; targetFurnitureType = 'coffeeMaker'; }
                        else if (choice === 'food') {
                            if (inter.microwave && inter.toaster) {
                                this.foodSource = Math.random() < 0.5 ? 'microwave' : 'toaster';
                                targetFurnitureType = this.foodSource;
                                target = this.foodSource === 'microwave' ? inter.microwave : inter.toaster;
                            } else if (inter.microwave) {
                                this.foodSource = 'microwave';
                                targetFurnitureType = 'microwave';
                                target = inter.microwave;
                            } else if (inter.toaster) {
                                this.foodSource = 'toaster';
                                targetFurnitureType = 'toaster';
                                target = inter.toaster;
                            }
                        } else { target = inter.waterCooler; targetFurnitureType = 'waterCooler'; }
                        if (!target) { this.returnToDesk(); return; }
                        // Use the generic per-object service queue. The queue is attached to
                        // the chosen target object, so water coolers, coffee makers, vending
                        // machines, microwaves, toasters, and future queueable furniture all
                        // share the same FIFO/reservation behavior.
                        const action = choice === 'snack' ? 'get_snack' : choice === 'coffee' ? 'make_coffee' : choice === 'food' ? 'make_food' : 'get_water';
                        const queueTarget = Object.assign({}, target, {
                            furnitureType: target.furnitureType || targetFurnitureType,
                            action: action,
                            queueKey: target.queueKey || (targetFurnitureType + ':' + Math.round(target.x) + ',' + Math.round(target.y)),
                            queueConfig: target.queueConfig
                        });
                        const labels = { snack: 'a snack', coffee: 'coffee', water: 'water', food: 'something to eat' };
                        const queued = enqueueAgentForObjectService(this, queueTarget, {
                            action: action,
                            faceDir: -1,
                            serviceTicks: 600 + Math.floor(Math.random() * 800),
                            startIntent: `Getting ${labels[choice]}`
                        });
                        if (!queued) {
                            this.targetX = target.x;
                            this.targetY = target.y;
                            this.idleAction = action;
                            this.idleReturnTimer = 600 + Math.floor(Math.random() * 800); // fallback for non-queueable objects
                        }
                        this.interactTimer = 0;
                        this.addIntent(`Decided on ${labels[choice]}!`);
                    }
                }
            }
        }

        // --- Face meeting partner in 1:1 ---
        if (this.visitTarget) {
            const target = agentMap[this.visitTarget];
            if (target) {
                const atTarget = Math.abs(this.x - this.targetX) < 3 && Math.abs(this.y - this.targetY) < 3;
                if (atTarget) {
                    this.faceDir = target.x > this.x ? 1 : -1;
                }
            }
        }
        const meetingMotionState = _meetingMotionState(this);
        if (meetingMotionState && meetingMotionState.hasSpeaker && meetingMotionState.role === 'listener') {
            const speaker = meetingMotionState.speaker;
            const speakerKey = speaker ? String(speaker.id || speaker.statusKey || speaker.name || '') : '';
            if (speakerKey && speakerKey !== this._meetingLastSpeakerKey) {
                this._meetingTurnTimer = 24;
                this._meetingLastSpeakerKey = speakerKey;
            }
            if (speaker && Math.abs(speaker.x - this.x) > 2) {
                const nextFaceDir = speaker.x > this.x ? 1 : -1;
                if (nextFaceDir !== this.faceDir) this._meetingTurnTimer = 24;
                this.faceDir = nextFaceDir;
            }
        } else {
            this._meetingLastSpeakerKey = '';
        }
        if (this._meetingTurnTimer > 0) this._meetingTurnTimer--;

        // --- Social proximity: face nearby agents in social areas ---
        const isMovingNow = Math.abs(this.targetX - this.x) > this.speed || Math.abs(this.targetY - this.y) > this.speed;
        const _socialActions = ['couch', 'lounge', 'watch_tv', 'break_browse', 'wander', 'visit', 'gathering', 'darts'];
        const _inSocialArea = !isMovingNow && this.idleAction && _socialActions.includes(this.idleAction);
        const _idleAtDesk = !isMovingNow && this.state === 'idle' && !this.idleAction && this.isSitting;
        if (_inSocialArea || _idleAtDesk) {
            let closest = null, closestDist = 60; // within 60px
            for (let oi = 0; oi < agents.length; oi++) {
                const other = agents[oi];
                if (other.id === this.id) continue;
                // Other agent must be in social area, visiting, or idle at desk
                const otherSocial = other.idleAction && _socialActions.includes(other.idleAction);
                const otherIdleDesk = other.state === 'idle' && !other.idleAction && other.isSitting;
                if (!otherSocial && !otherIdleDesk && other.state !== 'break') continue;
                const dx = other.x - this.x, dy = other.y - this.y;
                const d = Math.sqrt(dx * dx + dy * dy);
                if (d < closestDist) { closest = other; closestDist = d; }
            }
            if (closest) {
                this.socialTarget = closest.id;
                this.faceDir = closest.x > this.x ? 1 : -1;
                // Trigger talk animation when near someone
                if (this.talkTimer === 0 && Math.random() < 0.02) {
                    this.talkTimer = 40 + Math.random() * 80;
                }
            } else {
                this.socialTarget = null;
            }
        } else if (!this.visitTarget) {
            this.socialTarget = null;
        }

        // Talking animation in social/meeting areas
        if (['lounge', 'meeting', 'break', 'visiting'].includes(this.state) || ['visit', 'couch', 'watch_tv', 'lounge'].includes(this.idleAction)) {
            if (this.talkTimer === 0 && Math.random() < 0.012) {
                this.talkTimer = 30 + Math.random() * 60;
            } else if (this.talkTimer > 0) this.talkTimer--;
        } else this.talkTimer = 0;

        // Random work logs
        if (this.state === 'working' && Math.random() < 0.003) {
            const tasks = this.getWorkTasks();
            this.addLog(tasks[Math.floor(Math.random() * tasks.length)]);
        }

        // Blinking
        if (this.blinkTimer > 0) this.blinkTimer--;
        else if (Math.random() < 0.008) this.blinkTimer = 8;

        // Bubble age
        if (this.thought) this.thoughtAge++;
        if (this.speech) this.speechAge++;
    }

    startIdleAction() {
        const roll = Math.random();
        const inter = LOCATIONS.interactions;
        this.interactTimer = 0;

        if (roll < 0.05 && inter.engCouchSeats && inter.engCouchSeats.length > 0) {
            // Sit on ENG lounge couch — find an open seat
            const engSeat = findOpenSpot(inter.engCouchSeats, this.id);
            if (!engSeat) { this.resetIdleTimer(); return; }
            this.targetX = engSeat.x;
            this.targetY = engSeat.y;
            this.idleFaceDir = engSeat.faceDir;
            this.idleAction = 'couch';
            this.idleReturnTimer = 1200 + Math.floor(Math.random() * 2400);
            this.addIntent('Relaxing on the ENG couch');
        } else if (roll < 0.15 && inter.couchSeats && inter.couchSeats.length > 0) {
            // Sit on the lounge couch — find an open seat
            const seat = findOpenSpot(inter.couchSeats, this.id);
            if (!seat) { this.resetIdleTimer(); return; }
            this.targetX = seat.x;
            this.targetY = seat.y;
            this.idleFaceDir = seat.faceDir;
            this.idleAction = 'couch';
            this.idleReturnTimer = 1200 + Math.floor(Math.random() * 2400); // 20-60s
            this.addIntent('Relaxing on the couch');
        } else if (roll < 0.17 && inter.bookshelf) {
            // Read a book from the bookshelf
            const bsX = inter.bookshelf.x + (Math.random() - 0.5) * 10;
            const bsY = inter.bookshelf.y;
            if (isSpotOccupied(bsX, bsY, this.id)) { this.resetIdleTimer(); return; }
            this.targetX = bsX;
            this.targetY = bsY;
            this.idleFaceDir = -1;
            this.idleAction = 'read_book';
            this.idleReturnTimer = 1000 + Math.floor(Math.random() * 2000); // 16-50s
            this.addIntent('Grabbing a book to read');
        } else if (roll < 0.25) {
            // Look out the window — find open one
            const win = findOpenSpot(inter.windows, this.id);
            if (!win) { this.resetIdleTimer(); return; }
            this.targetX = win.x;
            this.targetY = win.y;
            this.idleFaceDir = 0; // special: face up
            this.idleAction = 'look_window';
            this.idleReturnTimer = 600 + Math.floor(Math.random() * 1200); // 10-30s
            this.addIntent('Looking out the window');
        } else if (roll < 0.49 && (inter.vendingMachine || inter.coffeeMaker || inter.waterCooler || inter.microwave || inter.toaster)) {
            // Break room visit — browse first, then pick something
            // Enter the break room area (center of the room)
            const bx = 740, by = 490; // break area origin
            this.targetX = bx + 80 + (Math.random() - 0.5) * 40;
            this.targetY = by + 50 + (Math.random() - 0.5) * 30;
            this.idleAction = 'break_browse';
            this.breakPhase = 0;          // 0=entering, 1=looking around, 2+=visiting items, final=using item
            this.breakStops = 0;          // how many items they've looked at
            this.breakMaxStops = 1 + Math.floor(Math.random() * 3); // 1-3 items to check out
            this.breakChoice = null;      // final choice: 'snack', 'coffee', 'water'
            this.idleReturnTimer = 0;     // managed by phase system
            this.addIntent('Heading to the break room');
        } else if (roll < 0.56 && inter.tvSpot) {
            // Watch TV in the lounge
            if (isSpotOccupied(inter.tvSpot.x, inter.tvSpot.y, this.id)) { this.resetIdleTimer(); return; }
            this.targetX = inter.tvSpot.x;
            this.targetY = inter.tvSpot.y;
            this.idleFaceDir = inter.tvSpot.faceDir;
            this.idleAction = 'watch_tv';
            this.idleReturnTimer = 1000 + Math.floor(Math.random() * 1800); // 16-46s
            this.addIntent('Watching TV');
        } else if (roll < 0.70) {
            // Visit a neighbor
            const neighbors = agents.filter(a => a.id !== this.id && a.state !== 'meeting');
            if (neighbors.length > 0) {
                const sameBranch = neighbors.filter(a => a.branch === this.branch);
                const pool = sameBranch.length > 0 && Math.random() < 0.7 ? sameBranch : neighbors;
                const target = pool[Math.floor(Math.random() * pool.length)];
                this.targetX = target.desk.x + (target.desk.x > 500 ? 35 : -35);
                this.targetY = target.desk.y + 15;
                this.idleAction = 'visit';
                this.visitTarget = target.id;
                this.idleReturnTimer = 800 + Math.floor(Math.random() * 1600);
                this.addIntent(`Visiting ${target.name}`);
            } else {
                this.resetIdleTimer();
            }
        } else if (roll < 0.82) {
            // Wander the hallway — pick an open wander spot
            const wSpot = findOpenSpot(LOCATIONS.wanderSpots, this.id);
            if (!wSpot) { this.resetIdleTimer(); return; }
            this.targetX = wSpot.x + (Math.random() - 0.5) * 30;
            this.targetY = wSpot.y + (Math.random() - 0.5) * 20;
            this.idleAction = 'wander';
            this.idleReturnTimer = 600 + Math.floor(Math.random() * 1200);
            this.addIntent('Stretching legs');
        } else if (roll < 0.91) {
            // Stretch near desk
            this.targetX = this.desk.x + (Math.random() > 0.5 ? 30 : -30);
            this.targetY = this.desk.y + 20;
            this.idleAction = 'stretch';
            this.idleReturnTimer = 360 + Math.floor(Math.random() * 600);
            this.addIntent('Stretching at desk');
        } else if (roll < 0.93) {
            // Wander to ping pong table — max 2 waiting/playing at once
            var _pongBusy = agents.filter(function(a) { return a.idleAction === 'pong' || a.idleAction === 'pong_wait'; }).length;
            if (_pongBusy < 2 && pongGames.length === 0) {
                var ptx = PONG_TABLE.x + (Math.random() > 0.5 ? -50 : 50);
                var pty = PONG_TABLE.y + (Math.random() - 0.5) * 10;
                this.targetX = ptx;
                this.targetY = pty;
                this.idleAction = 'pong_wait';
                this.idleReturnTimer = 1800 + Math.floor(Math.random() * 1200);
                this.addIntent('Heading to the ping pong table');
            } else if (pongGames.length > 0) {
                // Watch the game as a spectator
                var _specSide = Math.random() > 0.5 ? 1 : -1;
                this.targetX = PONG_TABLE.x + _specSide * (30 + Math.floor(Math.random() * 30));
                this.targetY = PONG_TABLE.y + 30 + Math.floor(Math.random() * 20);
                this.idleAction = 'pong_spectator';
                this.idleReturnTimer = 600 + Math.floor(Math.random() * 1200);
                this.addIntent('Watching ping pong');
            } else {
                this.resetIdleTimer(); return;
            }
        } else {
            // Wander to a random spot in the office
            var wanderSpots = LOCATIONS.wanderSpots || [];
            if (wanderSpots.length > 0) {
                var ws = wanderSpots[Math.floor(Math.random() * wanderSpots.length)];
                this.targetX = ws.x + (Math.random() - 0.5) * 40;
                this.targetY = ws.y + (Math.random() - 0.5) * 30;
            } else {
                this.targetX = Math.floor(Math.random() * W * 0.6 + W * 0.2);
                this.targetY = Math.floor(Math.random() * H * 0.6 + H * 0.2);
            }
            this.idleAction = 'wander';
            this.idleReturnTimer = 600 + Math.floor(Math.random() * 1200);
            this.addIntent('Taking a walk');
        }
        this.isSitting = false;
    }

    returnToDesk() {
        // Safety: ensure desk exists
        if (!this.desk) this.desk = { x: Math.floor(W / 2), y: Math.floor(H / 2) };
        // Pick up item if leaving a dispenser
        if (this.idleAction === 'make_coffee') {
            this.carryItem = 'coffee';
            this.addIntent('Carrying coffee back to desk');
        } else if (this.idleAction === 'get_water') {
            this.carryItem = 'water';
            this.addIntent('Carrying water back to desk');
        } else if (this.idleAction === 'get_snack') {
            this.carryItem = 'snack';
            this.snackType = ['candy', 'chips', 'cookies', 'chocolate'][Math.floor(Math.random() * 4)];
            this.addIntent('Carrying ' + this.snackType + ' back to desk');
        } else if (this.idleAction === 'make_food') {
            this.carryItem = 'food';
            if (this.foodSource === 'toaster') {
                this.foodType = 'sandwich';
            } else if (this.foodSource === 'microwave') {
                this.foodType = ['popcorn', 'pizza'][Math.floor(Math.random() * 2)];
            } else {
                this.foodType = 'sandwich';
            }
            this.addIntent('Carrying ' + this.foodType + ' back to desk');
        } else {
            this.addIntent('Returning to desk');
        }
        releaseObjectServiceQueueForAgent(this, 'complete');
        this.idleAction = null;
        this.idleFaceDir = null;
        this.interactTimer = 0;
        this.visitTarget = null;
        this.breakPhase = 0;
        this.breakStops = 0;
        this.breakChoice = null;
        this.breakPauseTimer = 0;
        this.targetX = this.desk.x;
        this.targetY = this.desk.y;
        this.resetIdleTimer();
    }

    getWorkTasks() {
        const base = ['Coffee sip.', 'Reviewing notes...', 'Checking inbox...'];
        // Branch-specific idle text is now generic — agents get varied text from their role
        if (this.role) {
            base.push('Working on ' + this.role.split(' ')[0].toLowerCase() + ' tasks...');
        }
        return [...base, 'Managing office...', 'Reviewing reports...', 'Coordinating teams...'];
    }

    onArrive() {
        const atDesk = Math.abs(this.x - this.desk.x) < 5 && Math.abs(this.y - this.desk.y) < 5;
        if (atDesk) {
            this.isSitting = true;
            if (!this.meetingId && !this.idleAction) {
                if (this.state !== 'working') this.state = this.task ? 'working' : 'idle';
            }
            this.faceDir = (this.desk && this.desk.x > W / 2) ? -1 : 1;
            if (this.deskType === 'boss') this.faceDir = 1;
            // Start consuming carried item at desk
            if (this.carryItem) {
                this.carryItemTimer = 1200 + Math.floor(Math.random() * 1200); // 20-40s
                this.addLog('Enjoying ' + this.carryItem + ' at desk');
            }
        } else {
            this.isSitting = false;
            // Check if spot is occupied by someone who got there first — redirect
            if (COLLISION_ENABLED && this.idleAction && this.idleAction !== 'wander' && this.idleAction !== 'visit' && this.idleAction !== 'stretch') {
                if (isSpotOccupied(this.x, this.y, this.id)) {
                    // Someone beat us here — go back or find alternative
                    releaseObjectServiceQueueForAgent(this, 'spot-taken');
                    this.idleAction = null;
                    this.breakPhase = null;
                    this.breakStops = 0;
                    this.interactTimer = 0;
                    this.targetX = this.desk.x;
                    this.targetY = this.desk.y;
                    this.addLog('Spot taken — heading back');
                    return;
                }
            }
            // Handle idle action arrival poses
            if (this.idleAction === 'couch' || this.idleAction === 'watch_tv') {
                this.isSitting = true;
                if (this.idleFaceDir !== null && this.idleFaceDir !== 0) this.faceDir = this.idleFaceDir;
            }
            if (this.idleFaceDir !== null && this.idleFaceDir !== 0) {
                this.faceDir = this.idleFaceDir;
            }
            startObjectServiceIfReady(this);
        }
    }

    moveTo(state) {
        // Clear idle action when explicitly moved
        if (this._gatheringId) leaveGathering(this.id);
        releaseObjectServiceQueueForAgent(this, 'moveTo');
        this.idleAction = null;
        this.visitTarget = null;
        this.idleReturnTimer = 0;

        const slotI = agents.indexOf(this);
        switch (state) {
            case 'working':
            case 'idle':
                this.meetingId = null;
                this.meetingSlot = null;
                this.targetX = this.desk.x;
                this.targetY = this.desk.y;
                this.state = state;
                this.resetIdleTimer();
                this.addIntent(state === 'working' ? 'Returning to desk' : 'Relaxing at desk');
                break;
            case 'meeting': {
                const m = getMeetingTablePos();
                if (m) {
                    const cols = 5, spacing = 35;
                    const row = Math.floor(slotI / cols);
                    const col = slotI % cols;
                    this.targetX = m.x + 20 + col * spacing;
                    this.targetY = m.y + 25 + row * 40;
                } else {
                    // No meeting table — meet at a random spot near the caller
                    this.targetX = this.x + (Math.random() - 0.5) * 100;
                    this.targetY = this.y + (Math.random() - 0.5) * 100;
                }
                this.state = 'meeting';
                this.addIntent('Joining meeting');
                break;
            }
            case 'lounge': {
                const lx = LOCATIONS.lounge.x;
                const ly = LOCATIONS.lounge.y;
                const slots = [
                    { x: 30, y: 15 }, { x: 30, y: 45 },
                    { x: 70, y: 80 }, { x: 100, y: 80 }, { x: 130, y: 80 },
                    { x: 60, y: 15 }, { x: 90, y: 15 }, { x: 160, y: 40 }, { x: 160, y: 70 }
                ];
                const s = slots[slotI % slots.length];
                this.targetX = lx + s.x;
                this.targetY = ly + s.y;
                this.state = 'lounge';
                this.addIntent('Heading to lounge');
                break;
            }
            case 'break': {
                const cx = LOCATIONS.cooler.x;
                const cy = LOCATIONS.cooler.y;
                const slots = [
                    { x: -40, y: -30 }, { x: 0, y: -30 }, { x: 40, y: -30 },
                    { x: -40, y: 0 }, { x: 0, y: 0 }, { x: 40, y: 0 },
                    { x: -20, y: 30 }, { x: 20, y: 30 }, { x: 0, y: -60 }
                ];
                const s = slots[slotI % slots.length];
                this.targetX = cx + s.x;
                this.targetY = cy + s.y;
                this.state = 'break';
                this.addIntent('On break');
                break;
            }
        }
    }

    // Join a meeting by ID — positions assigned by meeting system
    joinMeeting(meetingId, slot, topic) {
        releaseObjectServiceQueueForAgent(this, 'joinMeeting');
        this.idleAction = null;
        this.visitTarget = null;
        this.idleReturnTimer = 0;
        this.meetingId = meetingId;
        this.meetingSlot = slot;
        this.targetX = slot.x;
        this.targetY = slot.y;
        this.state = 'meeting';
        this.isSitting = !!slot.isSitting;
        this.meetingSpaceId = slot.meetingSpaceId || null;
        if (typeof slot.faceDir !== 'undefined') this.faceDir = slot.faceDir;
        this.addIntent(`Meeting: ${topic || 'discussion'}`);
    }

    // 1:1 visit to another agent's desk
    visitAgent(targetAgent, topic) {
        releaseObjectServiceQueueForAgent(this, 'visitAgent');
        this.idleAction = null;
        this.idleReturnTimer = 0;
        this.visitTarget = targetAgent.id;
        this.state = 'visiting';
        // Stand beside the target's desk
        const side = targetAgent.desk.x > 500 ? 35 : -35;
        this.targetX = targetAgent.desk.x + side;
        this.targetY = targetAgent.desk.y + 15;
        this.isSitting = false;
        this.addIntent(`Discussing with ${targetAgent.name}: ${topic || ''}`);
    }

    leaveMeeting() {
        this.meetingId = null;
        this.meetingSlot = null;
        this.meetingSpaceId = null;
        this.visitTarget = null;
        this.targetX = this.desk.x;
        this.targetY = this.desk.y;
        this.state = this.task ? 'working' : 'idle';
        this.isSitting = false;
        this.resetIdleTimer();
        this.addIntent('Meeting ended, returning to desk');
    }

    addLog(msg) {
        this.logHistory.push(`[${timeStr()}] ${msg}`);
        if (this.logHistory.length > 50) this.logHistory.shift();
    }
    addIntent(msg) {
        this.intent = msg;
        this.intentHistory.push(`[${timeStr()}] ${msg}`);
        if (this.intentHistory.length > 30) this.intentHistory.shift();
    }

    // Draw a snack based on this.snackType at given x,y
    _drawSnack(ctx, sx, sy) {
        const t = this.snackType || 'candy';
        if (t === 'candy') {
            // Orange candy bar (original)
            ctx.fillStyle = '#ffc107'; ctx.fillRect(sx, sy, 10, 5);
            ctx.fillStyle = '#ff9800'; ctx.fillRect(sx + 1, sy + 1, 8, 3);
            ctx.fillStyle = '#ffe082'; ctx.fillRect(sx, sy - 1, 3, 2);
        } else if (t === 'chips') {
            // Big bag of chips (red bag)
            ctx.fillStyle = '#e53935'; ctx.fillRect(sx, sy - 1, 12, 9);
            ctx.fillStyle = '#ef5350'; ctx.fillRect(sx + 1, sy, 10, 7);
            // Crinkle top (open bag)
            ctx.fillStyle = '#c62828';
            ctx.fillRect(sx + 1, sy - 1, 2, 1); ctx.fillRect(sx + 4, sy - 2, 3, 1);
            ctx.fillRect(sx + 8, sy - 1, 2, 1);
            // Yellow label
            ctx.fillStyle = '#ffeb3b'; ctx.fillRect(sx + 2, sy + 1, 8, 3);
            // Brand stripe
            ctx.fillStyle = '#f44336'; ctx.fillRect(sx + 3, sy + 2, 6, 1);
            // Bottom fold
            ctx.fillStyle = '#b71c1c'; ctx.fillRect(sx + 1, sy + 6, 10, 1);
        } else if (t === 'cookies') {
            // Brown cookies with chocolate chips
            // First cookie
            ctx.fillStyle = '#a1887f'; ctx.fillRect(sx, sy + 1, 5, 5);
            ctx.fillStyle = '#8d6e63'; ctx.fillRect(sx + 1, sy + 2, 3, 3);
            // Choc chips on first cookie
            ctx.fillStyle = '#3e2723';
            ctx.fillRect(sx + 1, sy + 2, 1, 1);
            ctx.fillRect(sx + 3, sy + 3, 1, 1);
            ctx.fillRect(sx + 2, sy + 4, 1, 1);
            // Second cookie (overlapping)
            ctx.fillStyle = '#a1887f'; ctx.fillRect(sx + 4, sy, 5, 5);
            ctx.fillStyle = '#8d6e63'; ctx.fillRect(sx + 5, sy + 1, 3, 3);
            // Choc chips on second cookie
            ctx.fillStyle = '#3e2723';
            ctx.fillRect(sx + 5, sy + 1, 1, 1);
            ctx.fillRect(sx + 7, sy + 2, 1, 1);
            ctx.fillRect(sx + 6, sy + 3, 1, 1);
            // Third cookie peeking behind
            ctx.fillStyle = '#bcaaa4'; ctx.fillRect(sx + 2, sy - 1, 5, 2);
            ctx.fillStyle = '#3e2723'; ctx.fillRect(sx + 3, sy - 1, 1, 1);
            ctx.fillRect(sx + 5, sy, 1, 1);
        } else if (t === 'chocolate') {
            // Chocolate bar half-opened — wrapper + exposed chocolate
            // Purple wrapper (left half)
            ctx.fillStyle = '#6a1b9a'; ctx.fillRect(sx, sy, 6, 6);
            ctx.fillStyle = '#8e24aa'; ctx.fillRect(sx + 1, sy + 1, 4, 4);
            // Silver foil edge
            ctx.fillStyle = '#bdbdbd'; ctx.fillRect(sx + 5, sy, 2, 6);
            ctx.fillStyle = '#e0e0e0'; ctx.fillRect(sx + 5, sy + 1, 1, 4);
            // Exposed brown chocolate (right half)
            ctx.fillStyle = '#5d4037'; ctx.fillRect(sx + 7, sy, 6, 6);
            ctx.fillStyle = '#4e342e'; ctx.fillRect(sx + 8, sy + 1, 4, 4);
            // Chocolate segments (squares)
            ctx.fillStyle = '#3e2723';
            ctx.fillRect(sx + 8, sy + 1, 2, 2);
            ctx.fillRect(sx + 10, sy + 1, 2, 2);
            ctx.fillRect(sx + 8, sy + 3, 2, 2);
            ctx.fillRect(sx + 10, sy + 3, 2, 2);
            // Segment divider lines
            ctx.fillStyle = '#6d4c41';
            ctx.fillRect(sx + 10, sy + 1, 1, 4);
            ctx.fillRect(sx + 8, sy + 3, 4, 1);
        }
    }

    // Draw food based on this.foodType at given x,y
    _drawFood(ctx, fx, fy) {
        const t = this.foodType || 'sandwich';
        if (t === 'sandwich') {
            // Sandwich on a small plate
            ctx.fillStyle = '#e0e0e0'; ctx.fillRect(fx - 1, fy + 4, 14, 3); // plate
            // Bottom bread
            ctx.fillStyle = '#d4a056'; ctx.fillRect(fx, fy + 1, 12, 3);
            // Lettuce
            ctx.fillStyle = '#66bb6a'; ctx.fillRect(fx + 1, fy, 10, 2);
            // Meat/ham
            ctx.fillStyle = '#e57373'; ctx.fillRect(fx + 1, fy - 1, 10, 2);
            // Cheese
            ctx.fillStyle = '#ffd54f'; ctx.fillRect(fx + 2, fy - 2, 9, 2);
            // Top bread
            ctx.fillStyle = '#c68c3c'; ctx.fillRect(fx + 1, fy - 3, 10, 2);
            ctx.fillStyle = '#d4a056'; ctx.fillRect(fx + 2, fy - 4, 8, 2);
            // Sesame seeds
            ctx.fillStyle = '#fff'; ctx.fillRect(fx + 3, fy - 4, 1, 1);
            ctx.fillRect(fx + 6, fy - 4, 1, 1);
            ctx.fillRect(fx + 8, fy - 3, 1, 1);
        } else if (t === 'popcorn') {
            // Popcorn in a bowl
            // Red bowl
            ctx.fillStyle = '#e53935'; ctx.fillRect(fx, fy + 2, 11, 5);
            ctx.fillStyle = '#ef5350'; ctx.fillRect(fx + 1, fy + 3, 9, 3);
            // White stripe on bowl
            ctx.fillStyle = '#fff'; ctx.fillRect(fx + 1, fy + 4, 9, 1);
            // Popcorn puffs overflowing
            ctx.fillStyle = '#fff9c4';
            ctx.fillRect(fx + 1, fy - 1, 3, 3);
            ctx.fillRect(fx + 4, fy - 2, 3, 3);
            ctx.fillRect(fx + 7, fy - 1, 3, 3);
            ctx.fillRect(fx + 3, fy - 3, 2, 2);
            ctx.fillRect(fx + 6, fy - 3, 2, 2);
            // Butter shading
            ctx.fillStyle = '#ffe082';
            ctx.fillRect(fx + 2, fy, 1, 1);
            ctx.fillRect(fx + 5, fy - 1, 1, 1);
            ctx.fillRect(fx + 8, fy, 1, 1);
        } else if (t === 'pizza') {
            // Pizza slice on plate
            ctx.fillStyle = '#e0e0e0'; ctx.fillRect(fx - 1, fy + 4, 14, 3); // plate
            // Pizza triangle (crust to tip)
            ctx.fillStyle = '#ffc107'; ctx.fillRect(fx, fy + 1, 12, 4); // cheese base
            ctx.fillStyle = '#ff9800'; ctx.fillRect(fx + 1, fy + 2, 10, 2); // sauce
            // Crust (wide end)
            ctx.fillStyle = '#d4a056'; ctx.fillRect(fx, fy + 4, 12, 2);
            ctx.fillStyle = '#c68c3c'; ctx.fillRect(fx + 1, fy + 5, 10, 1);
            // Pepperoni
            ctx.fillStyle = '#c62828';
            ctx.fillRect(fx + 2, fy + 1, 2, 2);
            ctx.fillRect(fx + 6, fy + 2, 2, 2);
            ctx.fillRect(fx + 9, fy + 1, 2, 2);
            // Cheese melt drip
            ctx.fillStyle = '#ffecb3'; ctx.fillRect(fx + 4, fy, 1, 1);
            ctx.fillRect(fx + 8, fy, 1, 1);
            // Tip (narrow end)
            ctx.fillStyle = '#ffc107'; ctx.fillRect(fx + 5, fy - 1, 3, 2);
        }
    }

    // Unique character desk item — top-left corner of desk (~-32, -22)
    _drawDeskCharItem(ctx) {
        const ix = 20, iy = -22;
        switch (this.getAppearance().deskItem) {
            case 'trophy': // Gold star trophy
                ctx.fillStyle = '#ffd700'; ctx.fillRect(ix + 2, iy + 6, 4, 6); // base
                ctx.fillStyle = '#ffeb3b'; ctx.fillRect(ix + 1, iy + 4, 6, 3); // cup
                ctx.fillStyle = '#ffd700'; // star
                ctx.fillRect(ix + 2, iy, 4, 2); ctx.fillRect(ix + 1, iy + 2, 6, 2);
                ctx.fillRect(ix + 3, iy - 1, 2, 1);
                break;
            case 'wrench': // Mini wrench
                ctx.fillStyle = '#9e9e9e'; ctx.fillRect(ix, iy + 2, 2, 10); // handle
                ctx.fillStyle = '#bdbdbd'; ctx.fillRect(ix - 1, iy, 4, 3); // jaw
                ctx.fillStyle = '#757575'; ctx.fillRect(ix, iy + 1, 2, 1); // gap
                ctx.fillStyle = '#5d4037'; ctx.fillRect(ix, iy + 8, 2, 4); // grip
                break;
            case 'calendar': // Mini calendar page
                ctx.fillStyle = '#fff'; ctx.fillRect(ix, iy, 8, 10);
                ctx.fillStyle = '#e53935'; ctx.fillRect(ix, iy, 8, 3); // red header
                ctx.fillStyle = '#333'; ctx.font = '5px Arial'; ctx.textAlign = 'center';
                ctx.fillText('5', ix + 4, iy + 9); // day number
                ctx.font = '8px sans-serif'; // restore font
                break;
            case 'envelope': // Mini envelope
                ctx.fillStyle = '#e3f2fd'; ctx.fillRect(ix, iy + 2, 8, 6);
                ctx.fillStyle = '#1976d2'; // flap
                ctx.beginPath(); ctx.moveTo(ix, iy + 2); ctx.lineTo(ix + 4, iy + 5);
                ctx.lineTo(ix + 8, iy + 2); ctx.closePath(); ctx.fill();
                ctx.fillStyle = '#f44336'; ctx.fillRect(ix + 6, iy + 1, 2, 2); // red dot (new mail)
                break;
            case 'money': // Green cash money
                // Bottom bill
                ctx.fillStyle = '#2e7d32'; ctx.fillRect(ix, iy + 6, 8, 5);
                ctx.fillStyle = '#43a047'; ctx.fillRect(ix + 1, iy + 7, 6, 3);
                // Top bill (slightly offset)
                ctx.fillStyle = '#388e3c'; ctx.fillRect(ix + 1, iy + 3, 8, 5);
                ctx.fillStyle = '#4caf50'; ctx.fillRect(ix + 2, iy + 4, 6, 3);
                // $ symbol
                ctx.fillStyle = '#fff'; ctx.fillRect(ix + 4, iy + 4, 2, 1);
                ctx.fillRect(ix + 5, iy + 5, 1, 1);
                ctx.fillRect(ix + 4, iy + 6, 2, 1);
                break;
            case 'ruler': // Ruler
                // Ruler body (long yellow bar)
                ctx.fillStyle = '#ffc107'; ctx.fillRect(ix - 2, iy + 4, 16, 4);
                ctx.fillStyle = '#ffb300'; ctx.fillRect(ix - 2, iy + 4, 16, 1); // top edge
                // Tick marks along ruler
                ctx.fillStyle = '#333';
                for (let t = 0; t < 7; t++) {
                    const tx = ix - 1 + t * 2;
                    ctx.fillRect(tx, iy + 5, 1, t % 2 === 0 ? 2 : 1);
                }
                // Numbers (tiny dots as number placeholders)
                ctx.fillStyle = '#5d4037';
                ctx.fillRect(ix, iy + 7, 1, 1);
                ctx.fillRect(ix + 6, iy + 7, 1, 1);
                ctx.fillRect(ix + 12, iy + 7, 1, 1);
                break;
            case 'marker': // Red marker pen
                ctx.fillStyle = '#f44336'; ctx.fillRect(ix, iy + 2, 2, 8);
                ctx.fillStyle = '#d32f2f'; ctx.fillRect(ix, iy + 2, 2, 2);
                ctx.fillStyle = '#fff'; ctx.fillRect(ix, iy + 9, 2, 2); // tip
                break;
            case 'chart': // Mini bar chart
                ctx.fillStyle = '#7b1fa2'; ctx.fillRect(ix, iy + 6, 2, 5);
                ctx.fillStyle = '#9c27b0'; ctx.fillRect(ix + 3, iy + 3, 2, 8);
                ctx.fillStyle = '#ce93d8'; ctx.fillRect(ix + 6, iy + 5, 2, 6);
                // axis line
                ctx.fillStyle = '#333'; ctx.fillRect(ix - 1, iy + 11, 10, 1);
                break;
            case 'plans': // Rolled architectural plans
                // Large roll (laid horizontally)
                ctx.fillStyle = '#e3f2fd'; ctx.fillRect(ix - 2, iy + 5, 14, 4);
                ctx.fillStyle = '#bbdefb'; ctx.fillRect(ix - 2, iy + 5, 14, 1); // top highlight
                ctx.fillStyle = '#90caf9'; ctx.fillRect(ix - 2, iy + 8, 14, 1); // bottom shadow
                // Roll ends (circles as rectangles at pixel scale)
                ctx.fillStyle = '#fff'; ctx.fillRect(ix - 3, iy + 5, 2, 4);
                ctx.fillStyle = '#e0e0e0'; ctx.fillRect(ix - 3, iy + 5, 1, 4);
                ctx.fillStyle = '#fff'; ctx.fillRect(ix + 11, iy + 5, 2, 4);
                ctx.fillStyle = '#e0e0e0'; ctx.fillRect(ix + 12, iy + 5, 1, 4);
                // Rubber band
                ctx.fillStyle = '#8d6e63'; ctx.fillRect(ix + 3, iy + 5, 1, 4);
                ctx.fillRect(ix + 8, iy + 5, 1, 4);
                // Second smaller roll on top (slightly offset)
                ctx.fillStyle = '#d1c4e9'; ctx.fillRect(ix, iy + 2, 10, 3);
                ctx.fillStyle = '#b39ddb'; ctx.fillRect(ix, iy + 2, 10, 1);
                ctx.fillStyle = '#ede7f6'; ctx.fillRect(ix, iy + 4, 10, 1);
                // End caps on smaller roll
                ctx.fillStyle = '#fff'; ctx.fillRect(ix - 1, iy + 2, 2, 3);
                ctx.fillRect(ix + 9, iy + 2, 2, 3);
                break;
            case 'checklist': // Mini checklist
                ctx.fillStyle = '#fff'; ctx.fillRect(ix, iy + 1, 8, 10);
                ctx.fillStyle = '#795548'; ctx.fillRect(ix, iy, 8, 2); // clipboard top
                ctx.fillStyle = '#ffd700'; ctx.fillRect(ix + 2, iy, 4, 1); // clip
                ctx.fillStyle = '#00bcd4';
                ctx.fillRect(ix + 1, iy + 3, 2, 2); ctx.fillRect(ix + 1, iy + 6, 2, 2); // checkmarks
                ctx.fillStyle = '#999';
                ctx.fillRect(ix + 4, iy + 4, 3, 1); ctx.fillRect(ix + 4, iy + 7, 3, 1); // lines
                break;
            case 'microscope': // Mini microscope
                // Base
                ctx.fillStyle = '#37474f'; ctx.fillRect(ix, iy + 8, 10, 3);
                ctx.fillStyle = '#455a64'; ctx.fillRect(ix + 1, iy + 9, 8, 1);
                // Stand/pillar
                ctx.fillStyle = '#546e7a'; ctx.fillRect(ix + 4, iy + 2, 3, 7);
                // Eyepiece (top)
                ctx.fillStyle = '#4caf50'; ctx.fillRect(ix + 3, iy, 4, 3);
                ctx.fillStyle = '#66bb6a'; ctx.fillRect(ix + 4, iy + 1, 2, 1);
                // Lens arm (angled)
                ctx.fillStyle = '#546e7a'; ctx.fillRect(ix + 1, iy + 4, 4, 2);
                // Lens
                ctx.fillStyle = '#81d4fa'; ctx.fillRect(ix, iy + 5, 3, 2);
                // Stage/slide
                ctx.fillStyle = '#fff'; ctx.fillRect(ix + 1, iy + 7, 5, 1);
                break;
            case 'shield': // Mini emergency toolkit / shield
                // Shield shape
                ctx.fillStyle = '#e91e90'; ctx.fillRect(ix + 1, iy, 8, 8);
                ctx.fillStyle = '#f48fb1'; ctx.fillRect(ix + 2, iy + 1, 6, 6);
                // Shield point
                ctx.fillStyle = '#e91e90'; ctx.fillRect(ix + 3, iy + 8, 4, 2); ctx.fillRect(ix + 4, iy + 10, 2, 1);
                // Cross/plus on shield
                ctx.fillStyle = '#fff'; ctx.fillRect(ix + 4, iy + 2, 2, 5); ctx.fillRect(ix + 3, iy + 3, 4, 2);
                break;
            case 'phone': // Classic office desk phone
                // Phone base (wider, flatter)
                ctx.fillStyle = '#37474f'; ctx.fillRect(ix - 1, iy + 5, 14, 7);
                ctx.fillStyle = '#455a64'; ctx.fillRect(ix, iy + 6, 12, 5);
                // Number pad (3x3 grid of tiny buttons)
                ctx.fillStyle = '#78909c';
                for (let br = 0; br < 3; br++) for (let bc = 0; bc < 3; bc++)
                    ctx.fillRect(ix + 1 + bc * 3, iy + 6 + br * 2, 2, 1);
                // Handset cradle (two bumps on base)
                ctx.fillStyle = '#263238';
                ctx.fillRect(ix, iy + 5, 2, 2);
                ctx.fillRect(ix + 10, iy + 5, 2, 2);
                // Handset resting on cradle (the receiver)
                ctx.fillStyle = '#1a1a1a';
                ctx.fillRect(ix - 1, iy + 2, 3, 4); // earpiece (left)
                ctx.fillRect(ix + 10, iy + 2, 3, 4); // mouthpiece (right)
                ctx.fillStyle = '#2c2c2c';
                ctx.fillRect(ix + 1, iy + 3, 10, 2); // handle connecting them
                // Coiled cord
                ctx.fillStyle = '#546e7a';
                ctx.fillRect(ix + 12, iy + 8, 1, 1);
                ctx.fillRect(ix + 13, iy + 9, 1, 1);
                ctx.fillRect(ix + 12, iy + 10, 1, 1);
                break;
            case 'anvil': // Mini anvil
                // Anvil base (wide, dark)
                ctx.fillStyle = '#37474f'; ctx.fillRect(ix - 2, iy + 8, 14, 4);
                ctx.fillStyle = '#455a64'; ctx.fillRect(ix - 1, iy + 9, 12, 2);
                // Anvil body (tapered)
                ctx.fillStyle = '#546e7a'; ctx.fillRect(ix, iy + 4, 10, 5);
                ctx.fillStyle = '#607d8b'; ctx.fillRect(ix + 1, iy + 5, 8, 3);
                // Anvil horn (pointed left)
                ctx.fillStyle = '#546e7a'; ctx.fillRect(ix - 3, iy + 5, 4, 3);
                ctx.fillStyle = '#607d8b'; ctx.fillRect(ix - 2, iy + 6, 3, 1);
                // Anvil face (flat top)
                ctx.fillStyle = '#78909c'; ctx.fillRect(ix - 1, iy + 3, 12, 2);
                // Spark (orange dot)
                ctx.fillStyle = '#ff6d00'; ctx.fillRect(ix + 8, iy + 1, 2, 2);
                ctx.fillStyle = '#ffab40'; ctx.fillRect(ix + 10, iy, 1, 1);
                break;
            case 'files': // Blue file stack & envelopes
                // Bottom file (dark blue, wide)
                ctx.fillStyle = '#1565c0'; ctx.fillRect(ix - 2, iy + 6, 14, 6);
                ctx.fillStyle = '#1976d2'; ctx.fillRect(ix - 2, iy + 4, 7, 3); // tab
                // Middle file (medium blue)
                ctx.fillStyle = '#1976d2'; ctx.fillRect(ix - 1, iy + 3, 14, 5);
                ctx.fillStyle = '#1e88e5'; ctx.fillRect(ix + 7, iy + 1, 6, 3); // tab
                // Top file (lighter blue)
                ctx.fillStyle = '#1e88e5'; ctx.fillRect(ix, iy + 1, 13, 4);
                ctx.fillStyle = '#42a5f5'; ctx.fillRect(ix, iy - 1, 6, 3); // tab
                // White label stripes
                ctx.fillStyle = '#fff';
                ctx.fillRect(ix + 2, iy + 2, 6, 1);
                ctx.fillRect(ix + 1, iy + 5, 7, 1);
                // Envelope sticking out the side
                ctx.fillStyle = '#e3f2fd'; ctx.fillRect(ix + 9, iy - 2, 7, 5);
                ctx.fillStyle = '#bbdefb'; ctx.fillRect(ix + 9, iy - 2, 7, 1); // flap
                // Envelope flap triangle
                ctx.fillStyle = '#90caf9';
                ctx.fillRect(ix + 11, iy - 1, 3, 1);
                ctx.fillRect(ix + 12, iy, 1, 1);
                // Second envelope peeking behind
                ctx.fillStyle = '#e8eaf6'; ctx.fillRect(ix + 10, iy - 3, 6, 2);
                ctx.fillStyle = '#c5cae9'; ctx.fillRect(ix + 10, iy - 3, 6, 1);
                break;
        }
    }

    draw() {
        ctx.save();
        ctx.translate(this.x, this.y);
        this._yawning = false; // reset per frame
        const meetingMotion = _meetingMotionDraw(this);

        const breathe = (Math.abs(this.targetX - this.x) < 1 && Math.abs(this.targetY - this.y) < 1) ? Math.sin(this.tick * 0.05) * 1 : 0;
        const isMoving = Math.abs(this.targetX - this.x) > this.speed || Math.abs(this.targetY - this.y) > this.speed;
        const walkBob = isMoving ? Math.abs(Math.sin(this.tick * 0.2)) * 4 : 0;
        const legOffset = isMoving ? Math.sin(this.tick * 0.2) * 6 : 0;
        const sitOffset = this.isSitting ? 8 : 0;

        // Shadow
        ctx.fillStyle = 'rgba(0,0,0,0.2)';
        ctx.beginPath(); ctx.ellipse(0, 4, 12, 5, 0, 0, Math.PI * 2); ctx.fill();
        ctx.translate(meetingMotion.offsetX, 0);

        // === CARRIED ITEM ON DESK (anchored to desk, no body bob) ===
        // (Unique character items drawn in environment pass — always visible)
        // Hide desk item during sip/nibble cycle (item is "in hand")
        if (this.carryItem && this.isSitting && !isMoving && !this.idleAction) {
            const sipCycle = this.tick % 540;  // full cycle ~9 seconds
            const isPickedUp = sipCycle < 120; // first 120 ticks: item is in hand
            if (!isPickedUp) {
                // Item resting on desk
                if (this.carryItem === 'coffee') {
                    ctx.fillStyle = '#fff'; ctx.fillRect(22, 3, 8, 10);
                    ctx.fillStyle = '#6d4c41'; ctx.fillRect(23, 4, 6, 5);
                    ctx.fillStyle = '#fff'; ctx.fillRect(29, 5, 3, 4);
                    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(30, 6, 1, 2);
                    ctx.fillStyle = 'rgba(255,255,255,0.5)';
                    ctx.fillRect(24, -1 + Math.sin(this.tick * 0.1) * 1, 2, 3);
                    ctx.fillRect(27, -2 + Math.cos(this.tick * 0.08) * 1, 2, 3);
                } else if (this.carryItem === 'water') {
                    ctx.fillStyle = 'rgba(220,240,255,0.9)'; ctx.fillRect(22, 3, 6, 9);
                    ctx.fillStyle = 'rgba(33,150,243,0.5)'; ctx.fillRect(23, 6, 4, 5);
                    if (Math.floor(this.tick / 120) % 3 === 0) {
                        ctx.fillStyle = 'rgba(33,150,243,0.3)'; ctx.fillRect(22, 10, 2, 2);
                    }
                } else if (this.carryItem === 'snack') {
                    this._drawSnack(ctx, 22, 4);
                } else if (this.carryItem === 'food') {
                    this._drawFood(ctx, 22, 2);
                }
            }
        }

        ctx.translate(0, -walkBob + sitOffset + meetingMotion.offsetY);

        // --- RIM LIGHT via canvas shadow (physics-based, follows exact shape) ---
        var _rim = getRimLight(this);
        if (_rim) {
            // Shadow offset toward the light = glow on light-facing edges (color matches source)
            var rimStr = Math.min(1, _rim.intensity * 5);
            ctx.shadowColor = 'rgba(' + _rim.color + ',' + rimStr.toFixed(2) + ')';
            ctx.shadowBlur = 0;
            ctx.shadowOffsetX = _rim.dirX * 5;
            ctx.shadowOffsetY = _rim.dirY * 5;
        }

        // Legs
        ctx.fillStyle = this.isSitting ? '#1a1a2e' : '#263238';
        if (!this.isSitting) {
            ctx.fillRect(-10, -7, 8, 12 + legOffset);
            ctx.fillRect(2, -7, 8, 12 - legOffset);
        } else {
            ctx.fillRect(-10, -2, 8, 8);
            ctx.fillRect(2, -2, 8, 8);
        }

        ctx.translate(0, breathe);

        // Body
        const isFemale = this.gender === 'F';
        ctx.fillStyle = this.color;
        if (isFemale) {
            // Slightly narrower torso, tapered waist
            ctx.fillRect(-9, -22, 18, 6);   // shoulders
            ctx.fillRect(-8, -16, 16, 9);   // waist
        } else {
            ctx.fillRect(-10, -22, 20, 15);
        }

        // Arms
        const armW = isFemale ? 3 : 4;
        // Check if sip animation is controlling the right arm
        const _sipActive = this.carryItem && this.isSitting && !isMoving && !this.idleAction && (this.tick % 540) < 120;
        if (this.state === 'working' && this.isSitting && !isMoving) {
            // Working: typing pose
            const typeOff = Math.sin(this.tick * 0.5) * 2;
            ctx.fillStyle = this.color;
            ctx.fillRect(isFemale ? -12 : -13, -15 + typeOff, armW, 8);
            if (!_sipActive) ctx.fillRect(9, -15 - typeOff, armW, 8);

        } else if ((this.state === 'idle' && this.isSitting) && !isMoving) {
            // Idle at desk: arms resting
            ctx.fillStyle = this.color;
            ctx.fillRect(isFemale ? -12 : -13, -15, armW, 8);
            if (!_sipActive) ctx.fillRect(9, -15, armW, 8);
        } else if (this.idleAction === 'pong' && !isMoving) {
            // Ping pong with P1/P2 colors.
            var _pg = pongGames.find(pg => pg.p1.id === this.id || pg.p2.id === this.id);
            var _isP1 = _pg && _pg.p1.id === this.id;
            var _swing = _pg ? (_isP1 ? (_pg.p1Swing || 0) : (_pg.p2Swing || 0)) : 0;
            var racketArm = this.faceDir;
            var swingAngle = _swing * 0.8;
            var _paddleFace = _isP1 ? '#f44336' : '#2196f3';
            var _paddleEdge = _isP1 ? '#d32f2f' : '#1976d2';
            ctx.fillStyle = this.color;
            if (racketArm === 1) {
                // Right arm with racket (facing right toward table)
                ctx.fillRect(isFemale ? -12 : -13, -15, armW, 8); // left arm resting
                ctx.save();
                ctx.translate(10, -18);
                ctx.rotate(-0.3 + swingAngle);
                ctx.fillStyle = this.color;
                ctx.fillRect(0, 0, armW, 10); // forearm
                // Racket
                ctx.fillStyle = '#8d6e63'; ctx.fillRect(1, 10, 2, 5); // handle
                ctx.fillStyle = _paddleFace;
                ctx.beginPath(); ctx.arc(2, 16, 4, 0, Math.PI * 2); ctx.fill();
                ctx.fillStyle = _paddleEdge;
                ctx.beginPath(); ctx.arc(2, 16, 3, 0, Math.PI * 2); ctx.fill();
                ctx.restore();
            } else {
                // Left arm with racket (facing left toward table)
                ctx.fillRect(9, -15, armW, 8); // right arm resting
                ctx.save();
                ctx.translate(-10, -18);
                ctx.rotate(0.3 - swingAngle);
                ctx.fillStyle = this.color;
                ctx.fillRect(-armW, 0, armW, 10); // forearm
                // Racket
                ctx.fillStyle = '#8d6e63'; ctx.fillRect(-2, 10, 2, 5); // handle
                ctx.fillStyle = _paddleFace;
                ctx.beginPath(); ctx.arc(-1, 16, 4, 0, Math.PI * 2); ctx.fill();
                ctx.fillStyle = _paddleEdge;
                ctx.beginPath(); ctx.arc(-1, 16, 3, 0, Math.PI * 2); ctx.fill();
                ctx.restore();
            }
        } else if (this.idleAction === 'stretch' && !isMoving) {
            ctx.fillStyle = this.color;
            ctx.fillRect(-14, -30, armW, 14);
            ctx.fillRect(10, -30, armW, 14);
        } else if (this.idleAction === 'read_book' && !isMoving) {
            // Arms holding a book in front
            ctx.fillStyle = this.color;
            ctx.fillRect(-9, -18, armW, 10);
            ctx.fillRect(6, -18, armW, 10);
            // Book
            ctx.fillStyle = '#e3f2fd'; ctx.fillRect(-5, -10, 12, 14);
            ctx.fillStyle = '#1976d2'; ctx.fillRect(-4, -9, 10, 5);
            // Text lines on page
            ctx.fillStyle = '#90a4ae';
            ctx.fillRect(-3, -3, 8, 1); ctx.fillRect(-3, -1, 6, 1); ctx.fillRect(-3, 1, 7, 1);
            // Page flip animation
            if (Math.floor(this.interactTimer / 120) % 2 === 0) {
                ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.fillRect(3, -9, 3, 12);
            }
        } else if (this.idleAction === 'look_window' && !isMoving) {
            // Arms behind back (viewing from behind)
            ctx.fillStyle = this.color;
            ctx.fillRect(-5, -16, 3, 8);
            ctx.fillRect(3, -16, 3, 8);
        } else if (this.idleAction === 'couch' && !isMoving) {
            // Relaxed arms on couch — one on armrest, one on lap
            ctx.fillStyle = this.color;
            const relaxOff = Math.sin(this.tick * 0.02) * 0.5;
            ctx.fillRect(isFemale ? -14 : -15, -16 + relaxOff, armW, 10); // arm on rest
            ctx.fillRect(6, -12, armW, 6); // arm on lap
        } else if (this.idleAction === 'watch_tv' && !isMoving) {
            // Arms on lap / holding remote
            ctx.fillStyle = this.color;
            ctx.fillRect(-8, -12, armW, 6);
            ctx.fillRect(5, -14, armW, 8);
            // Remote in hand
            ctx.fillStyle = '#212121'; ctx.fillRect(6, -15, 4, 7);
            ctx.fillStyle = '#f44336'; ctx.fillRect(7, -14, 2, 2);
        } else if (this.idleAction === 'break_browse' && !isMoving) {
            // Curious browsing pose — hand on chin, looking around
            ctx.fillStyle = this.color;
            ctx.fillRect(isFemale ? -11 : -12, -18, 3, 10); // left arm at side
            // Right hand on chin (thinking pose)
            ctx.fillRect(8, -20, armW, 6);
            ctx.fillRect(5, -26, armW, 6);
            // Occasional head tilt (looking left/right)
            if (Math.floor(this.interactTimer / 40) % 2 === 0) {
                this.faceDir = 1;
            } else {
                this.faceDir = -1;
            }
        } else if (['get_snack', 'make_coffee', 'get_water', 'make_food'].includes(this.idleAction) && !isMoving) {
            // One arm reaching toward machine, other at side
            ctx.fillStyle = this.color;
            ctx.fillRect(isFemale ? -11 : -12, -18, 3, 10); // left arm at side
            // Right arm extended toward machine
            const reachAnim = Math.sin(this.interactTimer * 0.08) * 2;
            ctx.fillRect(9, -20 + reachAnim, armW, 12);
            // Interaction-specific details
            if (this.idleAction === 'make_coffee' && this.interactTimer > 60) {
                // Steam while brewing
                ctx.fillStyle = 'rgba(255,255,255,0.3)';
                ctx.fillRect(12, -24 + Math.sin(this.interactTimer * 0.1) * 2, 2, 3);
                ctx.fillRect(15, -26 + Math.cos(this.interactTimer * 0.1) * 2, 2, 3);
            }
            if (this.idleAction === 'get_water' && this.interactTimer > 40) {
                // Holding cup under spigot
                ctx.fillStyle = '#fff'; ctx.fillRect(12, -10, 5, 6);
                ctx.fillStyle = 'rgba(33,150,243,0.5)';
                const fillH = Math.min(4, Math.floor((this.interactTimer - 40) / 30));
                ctx.fillRect(13, -10 + (4 - fillH), 3, fillH);
            }
            if (this.idleAction === 'get_snack' && this.interactTimer > 80) {
                // Snack dropping from machine
                const dropY = Math.min(0, -8 + (this.interactTimer - 80) * 0.3);
                ctx.fillStyle = '#ffc107'; ctx.fillRect(12, dropY - 6, 6, 4);
            }
            if (this.idleAction === 'make_food' && this.interactTimer > 50) {
                // Food warming glow
                ctx.fillStyle = 'rgba(255,152,0,0.2)';
                ctx.fillRect(10, -14, 8, 6);
            }
        } else {
            ctx.fillStyle = this.color;
            const armSwing = isMoving ? Math.sin(this.tick * 0.2) * 3 : 0;
            ctx.fillRect(isFemale ? -11 : -12, -20 + armSwing, 3, 10);
            ctx.fillRect(9, -20 - armSwing, 3, 10);
        }

        // Head (appearance-driven skin tone)
        const _appearance = this.getAppearance();
        ctx.fillStyle = _appearance.skinTone || '#ffcc80';
        ctx.fillRect(-12, -38, 24, 18);

        // Hair (data-driven)
        _drawHairByConfig(ctx, _appearance.hairStyle, _appearance.hairColor, _appearance.hairHighlight);

        // Clear rim light shadow — only body parts (legs, body, arms, head, hair) get the glow
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;

        // --- FACIAL FEATURES ---
        const eyeShift = this.faceDir === 1 ? 0 : -2;
        const skin = _appearance.skinTone || '#ffcc80';

        // Eyebrows (data-driven)
        const _ebStyle = _appearance.eyebrowStyle || (isFemale ? 'thin' : 'thick');
        if (_ebStyle === 'thin') {
            ctx.fillStyle = '#5d4037';
            ctx.fillRect(-5 + eyeShift, -33, 4, 1); ctx.fillRect(4 + eyeShift, -33, 4, 1);
            ctx.fillRect(-6 + eyeShift, -34, 2, 1); ctx.fillRect(7 + eyeShift, -34, 2, 1);
        } else if (_ebStyle === 'arched') {
            ctx.fillStyle = '#5d4037';
            ctx.fillRect(-5 + eyeShift, -34, 4, 1); ctx.fillRect(4 + eyeShift, -34, 4, 1);
            ctx.fillRect(-7 + eyeShift, -35, 2, 1); ctx.fillRect(8 + eyeShift, -35, 2, 1);
        } else if (_ebStyle === 'angular') {
            ctx.fillStyle = '#3e2723';
            ctx.fillRect(-5 + eyeShift, -35, 5, 1); ctx.fillRect(4 + eyeShift, -35, 5, 1);
            ctx.fillRect(-5 + eyeShift, -34, 2, 1); ctx.fillRect(8 + eyeShift, -34, 2, 1);
        } else {
            // thick (default male)
            ctx.fillStyle = '#3e2723';
            ctx.fillRect(-5 + eyeShift, -34, 5, 2); ctx.fillRect(4 + eyeShift, -34, 5, 2);
        }

        // Eyes
        if (this.blinkTimer > 0) {
            ctx.fillStyle = '#d7ccc8';
            ctx.fillRect(-5, -29, 5, 2);
            ctx.fillRect(4, -29, 5, 2);
        } else {
            // Eye whites
            ctx.fillStyle = '#fff';
            ctx.fillRect(-6 + eyeShift, -31, 6, 5);
            ctx.fillRect(3 + eyeShift, -31, 6, 5);
            // Pupils
            ctx.fillStyle = _appearance.eyeColor || '#212121';
            ctx.fillRect(-4 + eyeShift, -30, 3, 4);
            ctx.fillRect(5 + eyeShift, -30, 3, 4);
            // Pupil shine
            ctx.fillStyle = '#fff';
            ctx.fillRect(-3 + eyeShift, -30, 1, 1);
            ctx.fillRect(6 + eyeShift, -30, 1, 1);

            if (isFemale) {
                // Eyelashes — small lines above eyes
                ctx.fillStyle = '#212121';
                ctx.fillRect(-7 + eyeShift, -32, 1, 2);  // left outer lash
                ctx.fillRect(-6 + eyeShift, -33, 1, 2);  // left upper lash
                ctx.fillRect(8 + eyeShift, -32, 1, 2);   // right outer lash
                ctx.fillRect(9 + eyeShift, -33, 1, 2);   // right upper lash
            }
        }

        // Nose — small 2px hint
        ctx.fillStyle = darken(skin, 0.15);
        ctx.fillRect(0, -27, 2, 2);

        // Mouth
        const _sm = meetingMotion.mouth || this._socialMouth;
        this._socialMouth = null;
        if (_sm === 'laugh') {
            // Wide open laughing mouth
            ctx.fillStyle = '#3e2723'; ctx.fillRect(-3, -25, 6, 4);
            ctx.fillStyle = '#fff'; ctx.fillRect(-2, -25, 4, 1); // teeth
            ctx.fillStyle = '#c62828'; ctx.fillRect(-2, -23, 4, 2); // tongue
        } else if (_sm === 'open') {
            // Talking — mouth open
            ctx.fillStyle = '#3e2723'; ctx.fillRect(-2, -25, 5, 3);
            ctx.fillStyle = '#fff'; ctx.fillRect(-1, -25, 3, 1); // teeth flash
        } else if (_sm === 'half') {
            // Half open (mid-talk)
            ctx.fillStyle = '#3e2723'; ctx.fillRect(-2, -24, 4, 2);
        } else if (_sm === 'smile') {
            // Smile — curved up
            ctx.fillStyle = '#3e2723'; ctx.fillRect(-3, -24, 6, 1);
            ctx.fillStyle = '#3e2723'; ctx.fillRect(-2, -23, 4, 1); // slight curve down
            // Dimples
            ctx.fillStyle = 'rgba(200,100,100,0.3)';
            ctx.fillRect(-5, -24, 1, 1); ctx.fillRect(5, -24, 1, 1);
        } else if (_sm === 'closed') {
            // Closed but slight smile
            ctx.fillStyle = '#3e2723'; ctx.fillRect(-2, -24, 5, 1);
        } else if (this.talkTimer > 0) {
            ctx.fillStyle = '#3e2723';
            const open = Math.floor(this.tick / 3) % 2 === 0;
            ctx.fillRect(-2, -24, 4, open ? 3 : 1);
        } else if (isFemale) {
            // Lips — subtle color
            ctx.fillStyle = '#c4626a';
            ctx.fillRect(-2, -24, 5, 2);
            ctx.fillStyle = '#d47a82';
            ctx.fillRect(-1, -24, 3, 1); // upper lip highlight
        } else {
            // Neutral closed mouth line for males
            ctx.fillStyle = darken(skin, 0.25);
            ctx.fillRect(-2, -24, 4, 1);
        }

        // --- FACIAL HAIR ---
        if (_appearance.facialHair) {
            const fhColor = _appearance.facialHairColor || darken(_appearance.skinTone || '#ffcc80', 0.4);
            ctx.fillStyle = fhColor;
            if (_appearance.facialHair === 'stubble') {
                ctx.globalAlpha = 0.4;
                ctx.fillRect(-8, -26, 16, 4);
                ctx.globalAlpha = 1;
            } else if (_appearance.facialHair === 'beard') {
                ctx.fillRect(-8, -27, 16, 8);
                ctx.fillStyle = _appearance.skinTone || '#ffcc80';
                ctx.fillRect(-3, -26, 6, 3); // mouth area exposed
            } else if (_appearance.facialHair === 'goatee') {
                ctx.fillRect(-4, -25, 8, 4);
            } else if (_appearance.facialHair === 'mustache') {
                ctx.fillRect(-5, -27, 10, 2);
            }
        }

        // --- COSTUME (cached, drawn over everything) ---
        _drawCostume(ctx, _appearance.costume);

        // --- HEADWEAR (data-driven, skipped if wearing costume) ---
        if (!_appearance.costume) _drawHeadwear(ctx, _appearance.headwear, _appearance.headwearColor, isMoving);

        // --- GLASSES (data-driven) ---
        _drawGlasses(ctx, _appearance.glasses, _appearance.glassesColor, eyeShift);

        // --- HELD ITEM (data-driven) ---
        _drawHeldItem(ctx, _appearance.heldItem, isMoving);

        // Identity accessories are now data-driven via the Agent Editor.
        // No hardcoded per-agent accessories.

        // Emoji badge (on chest/shirt area)
        ctx.font = '8px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(this.emoji, 0, -12);

        // --- CARRIED ITEM (while walking) ---
        if (this.carryItem && isMoving) {
            const itemX = this.faceDir > 0 ? 12 : -19;
            if (this.carryItem === 'coffee') {
                ctx.fillStyle = '#fff'; ctx.fillRect(itemX, -18, 8, 10);
                ctx.fillStyle = '#6d4c41'; ctx.fillRect(itemX + 1, -17, 6, 5);
                ctx.fillStyle = '#fff'; ctx.fillRect(itemX + 7, -16, 3, 4);
                ctx.fillStyle = '#e0e0e0'; ctx.fillRect(itemX + 8, -15, 1, 2);
                // Steam
                ctx.fillStyle = 'rgba(255,255,255,0.4)';
                ctx.fillRect(itemX + 2, -22 + Math.sin(this.tick * 0.15) * 1, 2, 3);
                ctx.fillRect(itemX + 5, -23 + Math.cos(this.tick * 0.15) * 1, 2, 3);
            } else if (this.carryItem === 'water') {
                ctx.fillStyle = 'rgba(220,240,255,0.9)'; ctx.fillRect(itemX, -18, 6, 9);
                ctx.fillStyle = 'rgba(33,150,243,0.5)'; ctx.fillRect(itemX + 1, -15, 4, 5);
            } else if (this.carryItem === 'snack') {
                this._drawSnack(ctx, itemX, -16);
            } else if (this.carryItem === 'food') {
                this._drawFood(ctx, itemX, -18);
            }
        }

        // --- SIPPING / NIBBLING ANIMATION (at desk with item) ---
        // Synced with desk item: tick%540, first 120 ticks = item in hand
        // Phases: 0-25 reach to desk, 25-45 pick up, 45-60 lift to mouth,
        //         60-85 sip/bite (hold), 85-100 lower, 100-120 place back
        if (this.carryItem && this.isSitting && !isMoving && !this.idleAction) {
            const sipCycle = this.tick % 540;
            if (sipCycle < 120) {
                // --- ARM position (reaches toward desk item, then lifts) ---
                // Arm goes from resting (-15) down to desk level (-8) then up to face (-26)
                let armY, armX;
                const isFem = this.gender === 'F';
                const aw = isFem ? 3 : 4;
                if (sipCycle < 25) {
                    // Reach out toward desk: arm extends right and down
                    const t = sipCycle / 25;
                    armX = 9 + t * 6;        // 9 → 15 (reaching right toward item)
                    armY = -15 + t * 7;      // -15 → -8 (down to desk)
                } else if (sipCycle < 45) {
                    // Gripping / picking up
                    const t = (sipCycle - 25) / 20;
                    armX = 15 - t * 12;      // 15 → 3 (pulling back toward body)
                    armY = -8 - t * 10;      // -8 → -18 (lifting)
                } else if (sipCycle < 60) {
                    // Lift to mouth
                    const t = (sipCycle - 45) / 15;
                    armX = 3 - t * 4;        // 3 → -1 (centering)
                    armY = -18 - t * 8;      // -18 → -26
                } else if (sipCycle < 85) {
                    // Hold at mouth
                    armX = -1;
                    armY = -26;
                } else if (sipCycle < 100) {
                    // Lower from mouth
                    const t = (sipCycle - 85) / 15;
                    armX = -1 + t * 4;       // -1 → 3
                    armY = -26 + t * 8;      // -26 → -18
                } else {
                    // Place back on desk
                    const t = (sipCycle - 100) / 20;
                    armX = 3 + t * 12;       // 3 → 15 (reaching back to desk)
                    armY = -18 + t * 10;     // -18 → -8 (down to desk)
                }

                // Draw the reaching/holding arm
                ctx.fillStyle = this.color;
                // Upper arm (shoulder to elbow)
                ctx.fillRect(9, -16, aw, 8);
                // Forearm (elbow to hand) — angled toward item
                const fArmLen = Math.sqrt((armX - 9) ** 2 + (armY - (-10)) ** 2);
                ctx.save();
                ctx.translate(9 + aw / 2, -10);
                const angle = Math.atan2(armY - (-10), armX - 9);
                ctx.rotate(angle);
                ctx.fillRect(0, -aw / 2, Math.min(fArmLen, 14), aw);
                ctx.restore();
                // Hand (skin-colored block at item position)
                const skinTone = _appearance.skinTone || '#ffcc80';
                ctx.fillStyle = skinTone;
                ctx.fillRect(armX - 1, armY - 1, 4, 4);

                // --- ITEM follows the hand ---
                let itemY = armY;
                let itemX = armX;

                if (this.carryItem === 'coffee') {
                    ctx.fillStyle = '#fff'; ctx.fillRect(itemX - 1, itemY + 2, 8, 10);
                    ctx.fillStyle = '#6d4c41'; ctx.fillRect(itemX, itemY + 3, 6, 5);
                    ctx.fillStyle = '#fff'; ctx.fillRect(itemX + 6, itemY + 4, 3, 4);
                    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(itemX + 7, itemY + 5, 1, 2);
                    // Steam near face during sip
                    if (sipCycle >= 55 && sipCycle < 90) {
                        ctx.fillStyle = 'rgba(255,255,255,0.45)';
                        ctx.fillRect(itemX + 1, itemY - 2 + Math.sin(this.tick * 0.1) * 1, 2, 3);
                        ctx.fillRect(itemX + 4, itemY - 3 + Math.cos(this.tick * 0.08) * 1, 2, 3);
                    }
                } else if (this.carryItem === 'water') {
                    ctx.fillStyle = 'rgba(220,240,255,0.9)'; ctx.fillRect(itemX - 1, itemY + 2, 6, 9);
                    ctx.fillStyle = 'rgba(33,150,243,0.5)'; ctx.fillRect(itemX, itemY + 5, 4, 5);
                } else if (this.carryItem === 'snack') {
                    this._drawSnack(ctx, itemX - 1, itemY + 2);
                    // Crumbs during bite phase
                    if (sipCycle >= 62 && sipCycle < 82) {
                        ctx.fillStyle = '#ffe082';
                        const cp = (sipCycle - 62) * 0.6;
                        ctx.fillRect(itemX + 1, itemY + 7 + cp, 2, 1);
                        ctx.fillRect(itemX + 4, itemY + 9 + cp * 0.7, 1, 1);
                    }
                } else if (this.carryItem === 'food') {
                    this._drawFood(ctx, itemX - 1, itemY);
                    // Crumbs during bite phase
                    if (sipCycle >= 62 && sipCycle < 82) {
                        ctx.fillStyle = this.foodType === 'popcorn' ? '#fff9c4' : '#d4a056';
                        const cp = (sipCycle - 62) * 0.6;
                        ctx.fillRect(itemX + 2, itemY + 8 + cp, 2, 1);
                        ctx.fillRect(itemX + 5, itemY + 10 + cp * 0.7, 1, 1);
                    }
                }
            }
        }

        // Name tag
        ctx.fillStyle = this.color;
        ctx.fillRect(-22, -68, 44, 14);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(this.name, 0, -58);

        // Settings gear icon
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('⚙️', 0, -74);
        // Store gear hitbox in world coords (updated each frame)
        this.gearRect = { x: this.x - 10, y: this.y - 86, w: 20, h: 18 };

        // State indicator for visiting/meeting
        if (this.state === 'visiting' || this.state === 'meeting') {
            ctx.fillStyle = this.state === 'meeting' ? 'rgba(33,150,243,0.8)' : 'rgba(76,175,80,0.8)';
            ctx.beginPath(); ctx.arc(16, -60, 4, 0, Math.PI * 2); ctx.fill();
        }

        // Notification light — pulsing red dot
        if (this.notify) {
            const pulse = 0.5 + Math.sin(this.tick * 0.15) * 0.5; // 0-1 pulse
            const radius = 5 + pulse * 2;
            // Glow
            ctx.fillStyle = `rgba(244, 67, 54, ${0.3 + pulse * 0.3})`;
            ctx.beginPath(); ctx.arc(-18, -62, radius + 3, 0, Math.PI * 2); ctx.fill();
            // Solid dot
            ctx.fillStyle = `rgba(244, 67, 54, ${0.7 + pulse * 0.3})`;
            ctx.beginPath(); ctx.arc(-18, -62, radius, 0, Math.PI * 2); ctx.fill();
            // Inner bright spot
            ctx.fillStyle = `rgba(255, 255, 255, ${0.4 + pulse * 0.4})`;
            ctx.beginPath(); ctx.arc(-18, -63, 2, 0, Math.PI * 2); ctx.fill();
            // Exclamation mark
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 8px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('!', -18, -59);
        }

        // Clear rim light shadow
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;

        ctx.restore();
    }
}

// --- HELPERS ---
function timeStr() { return new Date().toLocaleTimeString([], { hour12: false }); }
function darken(hex, amt) {
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    r = Math.floor(r * (1 - amt)); g = Math.floor(g * (1 - amt)); b = Math.floor(b * (1 - amt));
    return `rgb(${r},${g},${b})`;
}

// --- BUBBLE SYSTEM ---
const BUBBLE_W = 170, BUBBLE_LINE_H = 11, BUBBLE_PAD = 8, BUBBLE_MAX_LINES = 8;
const BUBBLE_HEADER_H = 16; // height for name banner
const BUBBLE_CLOSE_SIZE = 10; // close button size
const THOUGHT_BUBBLE_W = 132, THOUGHT_BUBBLE_LINE_H = 10, THOUGHT_BUBBLE_PAD = 6, THOUGHT_BUBBLE_MAX_LINES = 6;

// Per-agent bubble minimize state: { agentKey: { thought: bool, speech: bool } }
const bubbleMinimized = {};
// Store rendered bubble rects for click detection
let renderedBubbles = [];
let renderedIcons = [];

function wrapText(text, maxW) {
    ctx.font = '7px "Press Start 2P", monospace';
    const words = text.split(' ');
    const lines = []; let line = '';
    for (const word of words) {
        const test = line ? line + ' ' + word : word;
        if (ctx.measureText(test).width > maxW - BUBBLE_PAD * 2 && line) { lines.push(line); line = word; }
        else line = test;
    }
    if (line) lines.push(line);
    return lines.slice(0, BUBBLE_MAX_LINES);
}

function wrapThoughtText(text) {
    ctx.font = '7px "Press Start 2P", monospace';
    const maxTextW = THOUGHT_BUBBLE_W - THOUGHT_BUBBLE_PAD * 2;
    const lines = [];
    let line = '';
    for (const char of String(text)) {
        const test = line + char;
        if (line && ctx.measureText(test).width > maxTextW) {
            lines.push(line.trimEnd());
            line = char === ' ' ? '' : char;
            if (lines.length >= THOUGHT_BUBBLE_MAX_LINES) break;
        } else {
            line = test;
        }
    }
    if (line && lines.length < THOUGHT_BUBBLE_MAX_LINES) lines.push(line.trimEnd());
    return lines;
}

function fitBubbleHeader(text, maxW) {
    ctx.font = 'bold 7px "Press Start 2P", monospace';
    const available = maxW - BUBBLE_CLOSE_SIZE - 10;
    let result = String(text || '');
    if (ctx.measureText(result).width <= available) return result;
    while (result.length > 1 && ctx.measureText(result + '...').width > available) result = result.slice(0, -1);
    return result + '...';
}

function getBubbleMinState(agent) {
    if (!bubbleMinimized[agent.statusKey]) bubbleMinimized[agent.statusKey] = { thought: false, speech: false };
    return bubbleMinimized[agent.statusKey];
}

function collectBubbles() {
    const bubbles = [];
    renderedIcons = [];
    agents.forEach(agent => {
        const headX = agent.x, headY = agent.y - 45;
        const minState = getBubbleMinState(agent);

        // Thought bubble
        const hasThought = agent.thought || agent.lastThought;
        if (hasThought) {
            const text = agent.thought || agent.lastThought;
            if (!minState.thought && typeof InternalBubbleSettings !== 'undefined' &&
                InternalBubbleSettings.shouldAutoCollapse(agent.thoughtUpdatedAt, _displayPrefs.internalBubbleTimeoutSec)) {
                minState.thought = true;
            }
            if (minState.thought) {
                // Minimized icon
                renderedIcons.push({ type: 'thought', agent, x: headX - 32, y: headY - 20, w: 14, h: 14 });
            } else {
                agent.thoughtChars = Math.min(agent.thoughtChars + 0.4, text.length);
                const vis = text.substring(0, Math.floor(agent.thoughtChars));
                if (vis.length > 0) {
                    const headerText = fitBubbleHeader(`${agent.name} Internal`, THOUGHT_BUBBLE_W);
                    const lines = wrapThoughtText(vis);
                    const h = BUBBLE_HEADER_H + lines.length * THOUGHT_BUBBLE_LINE_H + THOUGHT_BUBBLE_PAD * 2;
                    bubbles.push({ type: 'thought', agent, lines, w: THOUGHT_BUBBLE_W, h,
                        x: headX - THOUGHT_BUBBLE_W - 20, y: headY - h - 10,
                        anchorX: headX, anchorY: headY, headerText });
                }
            }
        }

        // Speech bubble
        const hasSpeech = agent.speech || agent.lastSpeech;
        if (hasSpeech) {
            const text = agent.speech || agent.lastSpeech;
            const target = agent.speechTarget || agent.lastSpeechTarget || '';
            if (minState.speech) {
                // Minimized icon
                renderedIcons.push({ type: 'speech', agent, x: headX + 16, y: headY - 20, w: 14, h: 14 });
            } else {
                agent.speechChars = Math.min(agent.speechChars + 0.6, text.length);
                const vis = text.substring(0, Math.floor(agent.speechChars));
                if (vis.length > 0) {
                    const targetLabel = target ? `→ ${target}` : '';
                    const headerText = agent.name;
                    const lines = wrapText(vis, BUBBLE_W);
                    const targetH = targetLabel ? 10 : 0;
                    const h = BUBBLE_HEADER_H + targetH + lines.length * BUBBLE_LINE_H + BUBBLE_PAD * 2;
                    bubbles.push({ type: 'speech', agent, lines, w: BUBBLE_W, h, targetH,
                        x: headX + 25, y: headY - h - 10,
                        anchorX: headX, anchorY: headY, targetLabel, headerText });
                }
                if (agent.speechChars < text.length) agent.talkTimer = 10;
            }
        }
    });
    lastCollectedBubbles = bubbles;
    return bubbles;
}

function resolveBubbleCollisions(bubbles) {
    for (const b of bubbles) {
        b.x = Math.max(2, Math.min(W - b.w - 2, b.x));
        b.y = Math.max(2, Math.min(H - b.h - 20, b.y));
    }
    for (let pass = 0; pass < 5; pass++) {
        for (let i = 0; i < bubbles.length; i++) {
            for (let j = i + 1; j < bubbles.length; j++) {
                const a = bubbles[i], bb = bubbles[j];
                if (a.x < bb.x + bb.w && a.x + a.w > bb.x && a.y < bb.y + bb.h && a.y + a.h > bb.y) {
                    const overlapX = Math.min(a.x + a.w - bb.x, bb.x + bb.w - a.x);
                    const overlapY = Math.min(a.y + a.h - bb.y, bb.y + bb.h - a.y);
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
        for (const b of bubbles) {
            b.x = Math.max(2, Math.min(W - b.w - 2, b.x));
            b.y = Math.max(2, Math.min(H - b.h - 20, b.y));
        }
    }
}

function drawMinimizedIcons() {
    // Draws at agent layer (before bubbles) so bubbles render on top
    for (const icon of renderedIcons) {
        ctx.save();
        const isThought = icon.type === 'thought';
        const cx = icon.x + icon.w / 2, cy = icon.y + icon.h / 2;
        ctx.fillStyle = isThought ? 'rgba(180,180,255,0.6)' : 'rgba(255,240,150,0.6)';
        ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = isThought ? 'rgba(100,100,180,0.7)' : 'rgba(200,170,50,0.7)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2); ctx.stroke();
        ctx.font = 'bold 5px "Press Start 2P", monospace';
        ctx.fillStyle = isThought ? '#446' : '#553';
        ctx.textAlign = 'center';
        ctx.fillText(isThought ? '...' : '💬', cx, cy + 2);
        ctx.restore();
    }
}

let lastCollectedBubbles = [];

function drawAllBubbles() {
    const bubbles = lastCollectedBubbles;
    resolveBubbleCollisions(bubbles);
    renderedBubbles = [];

    for (const b of bubbles) {
        ctx.save();
        const r = 6;
        const isThought = b.type === 'thought';

        // Connector to agent head
        if (isThought) {
            const cx = b.x + b.w / 2, cy = b.y + b.h;
            const dx = b.anchorX - cx, dy = b.anchorY - cy;
            for (let i = 1; i <= 3; i++) {
                const t = i / 4;
                ctx.fillStyle = `rgba(200,200,255,${0.5 + i * 0.1})`;
                ctx.beginPath(); ctx.arc(cx + dx * t, cy + dy * t, 2 + i, 0, Math.PI * 2); ctx.fill();
            }
        } else {
            const edgeX = Math.max(b.x + 8, Math.min(b.x + b.w - 8, b.anchorX));
            const edgeY = b.y + b.h;
            ctx.fillStyle = 'rgba(255,255,230,0.95)';
            ctx.strokeStyle = 'rgba(180,150,50,0.6)';
            ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(edgeX - 6, edgeY); ctx.lineTo(b.anchorX, b.anchorY); ctx.lineTo(edgeX + 6, edgeY); ctx.closePath(); ctx.fill(); ctx.stroke();
        }

        // Bubble body
        ctx.fillStyle = isThought ? 'rgba(230,230,255,0.92)' : 'rgba(255,255,230,0.95)';
        ctx.strokeStyle = isThought ? 'rgba(100,100,180,0.5)' : 'rgba(180,150,50,0.6)';
        ctx.lineWidth = 1.5;
        drawRoundRect(b.x, b.y, b.w, b.h, r); ctx.fill(); ctx.stroke();

        // Header banner
        ctx.fillStyle = isThought ? 'rgba(100,100,180,0.85)' : 'rgba(180,150,50,0.85)';
        drawRoundRect(b.x, b.y, b.w, BUBBLE_HEADER_H, r);
        // Clip bottom corners of header (just fill top portion)
        ctx.save();
        ctx.beginPath(); ctx.rect(b.x, b.y, b.w, BUBBLE_HEADER_H); ctx.clip();
        drawRoundRect(b.x, b.y, b.w, BUBBLE_HEADER_H + 4, r); ctx.fill();
        ctx.restore();

        // Header text
        ctx.font = 'bold 7px "Press Start 2P", monospace';
        ctx.fillStyle = '#fff'; ctx.textAlign = 'left';
        ctx.fillText(b.headerText || '', b.x + (isThought ? THOUGHT_BUBBLE_PAD : BUBBLE_PAD), b.y + 11);

        // Close (minimize) button - "−" on the right side of header
        const closeX = b.x + b.w - BUBBLE_CLOSE_SIZE - 3;
        const closeY = b.y + 2;
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.fillRect(closeX, closeY, BUBBLE_CLOSE_SIZE, BUBBLE_CLOSE_SIZE);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 9px Arial'; ctx.textAlign = 'center';
        ctx.fillText('−', closeX + BUBBLE_CLOSE_SIZE / 2, closeY + 8);

        // Store close button rect for click detection
        renderedBubbles.push({
            type: b.type, agent: b.agent,
            closeRect: { x: closeX, y: closeY, w: BUBBLE_CLOSE_SIZE, h: BUBBLE_CLOSE_SIZE },
            fullRect: { x: b.x, y: b.y, w: b.w, h: b.h }
        });

        // Target label (speech only)
        const bodyPad = isThought ? THOUGHT_BUBBLE_PAD : BUBBLE_PAD;
        const bodyLineH = isThought ? THOUGHT_BUBBLE_LINE_H : BUBBLE_LINE_H;
        let textStartY = b.y + BUBBLE_HEADER_H + bodyPad;
        if (!isThought && b.targetLabel) {
            ctx.font = '6px "Press Start 2P", monospace';
            ctx.fillStyle = '#b8860b'; ctx.textAlign = 'left';
            ctx.fillText(b.targetLabel, b.x + BUBBLE_PAD, textStartY + 4);
            textStartY += (b.targetH || 10);
        }

        // Body text
        ctx.font = '7px "Press Start 2P", monospace';
        ctx.fillStyle = isThought ? '#444' : '#222'; ctx.textAlign = 'left';
        b.lines.forEach((line, i) => ctx.fillText(line, b.x + bodyPad, textStartY + 8 + i * bodyLineH));

        ctx.restore();
    }

    // Icons are drawn in drawMinimizedIcons() at agent layer, not here
}

// Bubble click handler
function handleBubbleClick(canvasX, canvasY) {
    // Check close buttons on expanded bubbles
    for (const rb of renderedBubbles) {
        const cr = rb.closeRect;
        if (canvasX >= cr.x && canvasX <= cr.x + cr.w && canvasY >= cr.y && canvasY <= cr.y + cr.h) {
            const minState = getBubbleMinState(rb.agent);
            minState[rb.type] = true;
            return true;
        }
    }
    // Check minimized icons — click to restore
    for (const icon of renderedIcons) {
        if (canvasX >= icon.x && canvasX <= icon.x + icon.w && canvasY >= icon.y && canvasY <= icon.y + icon.h) {
            const minState = getBubbleMinState(icon.agent);
            minState[icon.type] = false;
            // Restore bubble content and reset age so it displays
            if (icon.type === 'thought') {
                if (!icon.agent.thought && icon.agent.lastThought) icon.agent.thought = icon.agent.lastThought;
                icon.agent.thoughtAge = 0;
                icon.agent.thoughtChars = 0;
                icon.agent.thoughtUpdatedAt = Date.now();
            } else {
                if (!icon.agent.speech && icon.agent.lastSpeech) icon.agent.speech = icon.agent.lastSpeech;
                if (icon.agent.lastSpeechTarget) icon.agent.speechTarget = icon.agent.lastSpeechTarget;
                icon.agent.speechAge = 0;
                icon.agent.speechChars = 0;
            }
            return true;
        }
    }
    return false;
}

function drawRoundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r); ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}

// --- CREATE AGENTS (dynamic) ---
var agents = [];
var agentMap = {};

function _initAgentsFromDefs() {
    // Apply saved overrides
    var savedAgents = (officeConfig && officeConfig.agents) || [];
    var savedMap = {};
    savedAgents.forEach(function(s) { savedMap[s.id] = s; });

    agents.length = 0; // clear existing
    AGENT_DEFS.forEach(function(def) {
        var saved = savedMap[def.id] || {};
        if (saved.name) def.name = saved.name;
        if (saved.role) def.role = saved.role;
        if (saved.emoji) def.emoji = saved.emoji;
        if (saved.color) def.color = saved.color;
        if (saved.gender) def.gender = saved.gender;
        if (saved.statusKey) def.statusKey = saved.statusKey;
        if (saved.branch) def.branch = saved.branch;
        if (saved.appearance) def.appearance = JSON.parse(JSON.stringify(saved.appearance));
        agents.push(new Agent(def));
    });

    // Rebuild map
    agentMap = {};
    agents.forEach(function(a) { agentMap[a.id] = a; agentMap[a.statusKey] = a; });

    ensureValidAgentBranches();
    _syncAllDeskAssignments();
    if (typeof updateSidebar === 'function') updateSidebar();
    if (typeof _acpRefreshList === 'function') _acpRefreshList();
}

// Kick off roster fetch immediately
_fetchRoster();
let selectedAgent = null;
const dismissedNotify = new Set();  // track dismissed notifications to prevent poll re-enabling

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
setInterval(pollAgentChat, 3000);
pollAgentChat();

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

// --- SIDEBAR ---
function _agentStateLabel(state) {
    var key = {
        moving: 'agent_state_moving',
        meeting: 'agent_state_meeting',
        lounge: 'agent_state_lounge',
        break: 'agent_state_break',
        chatting: 'agent_state_chatting',
        stretching: 'agent_state_stretching',
        walking: 'agent_state_walking',
        lounging: 'agent_state_lounging',
        reading: 'agent_state_reading',
        gazing: 'agent_state_gazing',
        browsing: 'agent_state_browsing',
        snacking: 'agent_state_snacking',
        cooking: 'agent_state_cooking',
        socializing: 'agent_state_socializing',
        playing_darts: 'agent_state_playing_darts',
        playing_ping_pong: 'agent_state_playing_ping_pong',
        at_ping_pong: 'agent_state_at_ping_pong',
        watching_ping_pong: 'agent_state_watching_ping_pong',
        coffee_break: 'agent_state_coffee_break',
        hydrating: 'agent_state_hydrating',
        watching_tv: 'agent_state_watching_tv',
        sipping: 'agent_state_sipping',
        eating: 'agent_state_eating'
    }[state];
    if (typeof i18n === 'undefined') return state;
    return key ? i18n.t(key) : i18n.t('agent_state_unknown', { state: state });
}

function updateSidebar() {
    const container = document.getElementById('branch-sections-container');
    if (!container) return;
    container.innerHTML = '';
    ensureValidAgentBranches();

    let counts = { working: 0, idle: 0, meeting: 0, break: 0 };
    const byBranch = {};
    getBranchList().forEach(function(branch) { byBranch[branch.id] = []; });

    agents.forEach(agent => {
        const isMoving = Math.abs(agent.targetX - agent.x) > agent.speed || Math.abs(agent.targetY - agent.y) > agent.speed;
        let displayState = isMoving ? 'moving' : agent.state;
        if (agent.state === 'visiting') displayState = 'meeting';
        if (agent.idleAction === 'lounge') displayState = 'lounge';
        if (agent.idleAction === 'break') displayState = 'break';
        if (agent.idleAction === 'visit') displayState = 'chatting';
        if (agent.idleAction === 'stretch') displayState = 'stretching';
        if (agent.idleAction === 'wander') displayState = 'walking';
        if (agent.idleAction === 'couch') displayState = 'lounging';
        if (agent.idleAction === 'read_book') displayState = 'reading';
        if (agent.idleAction === 'look_window') displayState = 'gazing';
        if (agent.idleAction === 'break_browse') displayState = 'browsing';
        if (agent.idleAction === 'object_queue_wait') displayState = 'queued';
        if (agent.idleAction === 'get_snack') displayState = 'snacking';
        if (agent.idleAction === 'make_food') displayState = 'cooking';
        if (agent.idleAction === 'gathering') displayState = 'socializing';
        if (agent.idleAction === 'darts') displayState = 'playing_darts';
        if (agent.idleAction === 'pong') displayState = 'playing_ping_pong';
        if (agent.idleAction === 'pong_wait') displayState = 'at_ping_pong';
        if (agent.idleAction === 'pong_spectator') displayState = 'watching_ping_pong';
        if (agent.idleAction === 'make_coffee') displayState = 'coffee_break';
        if (agent.idleAction === 'get_water') displayState = 'hydrating';
        if (agent.idleAction === 'watch_tv') displayState = 'watching_tv';
        if (agent.carryItem && !agent.idleAction) displayState = agent.carryItem === 'coffee' ? 'sipping' : agent.carryItem === 'water' ? 'hydrating' : agent.carryItem === 'food' ? 'eating' : 'snacking';

        if (agent.state === 'meeting' || agent.state === 'visiting') counts.meeting++;
        else if (agent.state === 'working') counts.working++;
        else if (agent.state === 'lounge' || agent.idleAction === 'lounge') counts.break++;
        else if (agent.state === 'break' || agent.idleAction === 'break') counts.break++;
        else counts.idle++;

        const div = document.createElement('div');
        div.className = 'agent-entry';
        div.innerHTML = `<span class="dot ${displayState}"></span><span class="name">${agent.emoji} ${agent.name}</span><span class="state">${_agentStateLabel(displayState)}</span>`;
        div.onclick = () => openModal(agent);
        const branchId = byBranch[agent.branch] ? agent.branch : 'UNASSIGNED';
        byBranch[branchId].push(div);
    });

    getBranchList().forEach(function(branch) {
        const section = document.createElement('div');
        section.className = 'branch-section collapsible ' + getBranchTheme(branch.id);
        if (branch.color) {
            section.style.borderColor = branch.color;
        }

        const header = document.createElement('h4');
        header.className = 'branch-header-row';
        if (branch.color) header.style.color = branch.color;
        header.innerHTML = `<span class="section-arrow">▼</span> ${branch.emoji} ${branch.name}`;
        header.onclick = function(e) { if (e.target.closest('.branch-actions')) return; toggleSection(header); };

        const actions = document.createElement('span');
        actions.className = 'branch-actions';
        if (branch.id !== 'UNASSIGNED') {
            const editBtn = document.createElement('button');
            editBtn.textContent = '✏️';
            editBtn.title = typeof i18n !== 'undefined' ? i18n.t('edit_branch') : 'Edit branch';
            editBtn.onclick = function(e) { e.stopPropagation(); branchEditPrompt(branch.id); };
            const delBtn = document.createElement('button');
            delBtn.textContent = '🗑️';
            delBtn.title = typeof i18n !== 'undefined' ? i18n.t('delete_branch') : 'Delete branch';
            delBtn.onclick = function(e) { e.stopPropagation(); branchDeletePrompt(branch.id); };
            actions.appendChild(editBtn);
            actions.appendChild(delBtn);
        }
        header.appendChild(actions);
        section.appendChild(header);

        const body = document.createElement('div');
        body.className = 'section-body';
        body.style.display = 'block';
        const list = document.createElement('div');
        list.className = 'agent-list';
        (byBranch[branch.id] || []).forEach(function(node) { list.appendChild(node); });
        body.appendChild(list);
        if (branch.id === 'UNASSIGNED') {
            const note = document.createElement('div');
            note.className = 'branch-unassigned-note';
            note.textContent = typeof i18n !== 'undefined' ? i18n.t('delete_branch_note') : 'Deleting a branch moves agents here.';
            body.appendChild(note);
        }
        section.appendChild(body);
        container.appendChild(section);
    });

    document.getElementById('count-working').textContent = counts.working;
    document.getElementById('count-idle').textContent = counts.idle;
    document.getElementById('count-meeting').textContent = counts.meeting;
    document.getElementById('count-break').textContent = counts.break;
}
setInterval(updateSidebar, 1000);

function branchCreatePrompt() {
    var name = prompt(typeof i18n !== 'undefined' ? i18n.t('new_branch_name_prompt') : 'New branch name:');
    if (!name) return;
    var emoji = prompt(typeof i18n !== 'undefined' ? i18n.t('branch_emoji_prompt') : 'Branch emoji:', '🏢') || '🏢';
    var idBase = name.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 24) || 'BRANCH';
    var id = idBase;
    var n = 2;
    while (officeConfig.branches.some(function(b){ return b.id === id; })) id = idBase + '_' + (n++);
    var defaultColors = ['#ffd700','#1565c0','#e65100','#00bcd4','#ff6d00','#9c27b0','#2e7d32'];
    var color = defaultColors[officeConfig.branches.length % defaultColors.length];
    officeConfig.branches.push({ id: id, name: name, emoji: emoji, color: color, theme: 'branch-gray' });
    _invalidateBranchCache();
    saveOfficeConfig();
    updateSidebar();
    // Immediately open the editor for the new branch
    branchEditPrompt(id);
}

function branchEditPrompt(branchId) {
    var branch = officeConfig.branches.find(function(b){ return b.id === branchId; });
    if (!branch) return;
    // Remove existing popup if any
    var existing = document.getElementById('branch-edit-popup');
    if (existing) existing.remove();

    var popup = document.createElement('div');
    popup.id = 'branch-edit-popup';
    popup.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:99999;background:#1a1a2e;border:2px solid #ffd700;border-radius:12px;padding:20px;min-width:320px;max-width:400px;box-shadow:0 8px 40px rgba(0,0,0,0.6);font-family:Arial,sans-serif;color:#e0e0e0;';

    // Get the current branch color
    var currentColor = branch.color || _getThemeColor(branch.theme) || '#888888';

    popup.innerHTML = '<div style="font-size:14px;font-weight:bold;color:#ffd700;margin-bottom:14px;">✏️ ' + (typeof i18n !== 'undefined' ? i18n.t('edit_branch_title_prefix') : 'Edit Branch') + ': ' + (branch.emoji || '') + ' ' + branch.name + '</div>' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('branch_name_label') : 'Branch Name') + '</label>' +
        '<input id="be-name" type="text" value="' + (branch.name || '') + '" style="width:100%;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:6px;color:#e0e0e0;font-size:14px;margin:4px 0 10px;">' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('emoji_label') : 'Emoji') + '</label>' +
        '<input id="be-emoji" type="text" value="' + (branch.emoji || '🏢') + '" style="width:60px;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:6px;color:#e0e0e0;font-size:14px;margin:4px 0 10px;">' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('branch_color_label') : 'Branch Color') + '</label>' +
        '<div style="display:flex;align-items:center;gap:8px;margin:4px 0 12px;">' +
        '<input id="be-color" type="color" value="' + currentColor + '" style="width:40px;height:32px;border:none;background:none;cursor:pointer;">' +
        '<span id="be-color-hex" style="font-size:12px;color:#888;">' + currentColor + '</span>' +
        '</div>' +
        '<label style="font-size:12px;color:#aaa;">Agents in Branch</label>' +
        '<div id="be-agents" style="max-height:180px;overflow-y:auto;margin:4px 0 12px;border:1px solid #2a2a4e;border-radius:6px;padding:6px;background:#0d0d1e;"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px;">' +
        '<button id="be-cancel" style="padding:6px 16px;background:#333;border:1px solid #555;border-radius:6px;color:#ccc;cursor:pointer;font-size:12px;">Cancel</button>' +
        '<button id="be-save" style="padding:6px 16px;background:#ffd700;border:none;border-radius:6px;color:#000;font-weight:bold;cursor:pointer;font-size:12px;">Save</button>' +
        '</div>';

    document.body.appendChild(popup);

    // Color picker live update
    document.getElementById('be-color').addEventListener('input', function() {
        document.getElementById('be-color-hex').textContent = this.value;
    });

    // Populate agent checkboxes
    var agentDiv = document.getElementById('be-agents');
    var allAgents = agents.slice().sort(function(a,b){ return a.name.localeCompare(b.name); });
    allAgents.forEach(function(a) {
        var row = document.createElement('label');
        row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:3px 4px;cursor:pointer;font-size:12px;border-radius:4px;';
        row.onmouseenter = function(){ this.style.background='rgba(255,255,255,0.05)'; };
        row.onmouseleave = function(){ this.style.background=''; };
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = a.statusKey || a.id;
        cb.checked = (a.branch === branchId);
        row.appendChild(cb);
        row.appendChild(document.createTextNode(a.emoji + ' ' + a.name));
        agentDiv.appendChild(row);
    });

    // Cancel
    document.getElementById('be-cancel').onclick = function() { popup.remove(); };

    // Save
    document.getElementById('be-save').onclick = function() {
        branch.name = document.getElementById('be-name').value || branch.name;
        branch.emoji = document.getElementById('be-emoji').value || '🏢';
        branch.color = document.getElementById('be-color').value;
        // Update agent assignments
        var checkboxes = agentDiv.querySelectorAll('input[type=checkbox]');
        checkboxes.forEach(function(cb) {
            var agentKey = cb.value;
            var agent = agents.find(function(a){ return (a.statusKey || a.id) === agentKey; });
            if (!agent) return;
            if (cb.checked) {
                agent.branch = branchId;
            } else if (agent.branch === branchId) {
                agent.branch = 'UNASSIGNED';
            }
            // Also update officeConfig.agents
            if (officeConfig.agents) {
                var cfgAgent = officeConfig.agents.find(function(a){ return a.id === agentKey || a.statusKey === agentKey; });
                if (cfgAgent) cfgAgent.branch = agent.branch;
            }
        });
        _invalidateBranchCache();
        saveOfficeConfig();
        updateSidebar();
        if (_agentPanelSelectedId) _acpSelectAgent(_agentPanelSelectedId);
        popup.remove();
    };

    // Close on Escape
    var escHandler = function(e) { if (e.key === 'Escape') { popup.remove(); document.removeEventListener('keydown', escHandler); } };
    document.addEventListener('keydown', escHandler);
}

function _getThemeColor(theme) {
    var map = {'branch-gold':'#ffd700','branch-blue':'#1565c0','branch-orange':'#e65100','branch-cyan':'#00bcd4','branch-red':'#ff6d00','branch-gray':'#90a4ae'};
    return map[theme] || '#888888';
}

function branchDeletePrompt(branchId) {
    var branch = officeConfig.branches.find(function(b){ return b.id === branchId; });
    if (!branch) return;
    if (!confirm(_tr('delete_branch_confirm', { name: branch.name }))) return;
    officeConfig.branches = officeConfig.branches.filter(function(b){ return b.id !== branchId; });
    _invalidateBranchCache();
    agents.forEach(function(a){ if (a.branch === branchId) a.branch = 'UNASSIGNED'; });
    if (officeConfig.agents) officeConfig.agents.forEach(function(a){ if (a.branch === branchId) a.branch = 'UNASSIGNED'; });
    saveOfficeConfig();
    updateSidebar();
    if (_agentPanelSelectedId) _acpSelectAgent(_agentPanelSelectedId);
}

// --- ENVIRONMENT DRAWING ---
function drawEnvironment() {
    _tod = getTimeOfDaySky(); // refresh for time-lapse
    // --- FLOOR (from officeConfig) ---
    for (let x = 0; x < W; x += TILE) {
        for (let y = 0; y < H; y += TILE) {
            const alt = (Math.floor(x / TILE) + Math.floor(y / TILE)) % 2 === 0;
            ctx.fillStyle = alt ? officeConfig.floor.color1 : officeConfig.floor.color2;
            ctx.fillRect(x, y, TILE, TILE);
        }
    }

    // --- WALLS (from officeConfig) ---
    const wallH = officeConfig.walls.height;
    const renderedWallSections = getRenderedWallSections();
    const topWall = getTopWallConfig();
    ctx.fillStyle = '#455a64'; ctx.fillRect(0, 0, W, wallH); // base
    renderedWallSections.forEach(function(section) {
        ctx.fillStyle = section.color;
        ctx.fillRect(section.x, 0, section.w, wallH);
        ctx.fillStyle = section.accentColor;
        ctx.fillRect(section.x, wallH - 18, section.w, 18);
    });
    ctx.fillStyle = topWall.trimColor || officeConfig.walls.trimColor;
    ctx.fillRect(0, wallH - 4, W, 4);

    // --- HQ WINDOWS (north wall, flanking center text) ---
    // Time-of-day sky colors
    function getTimeOfDaySky() {
        const t = _getTimeHour();
        const sun = _getSunTimes();
        if (t < sun.dawn)                return { sky: '#0d1b2a', upper: '#162032', top: '#0a1020', cloud: 'rgba(200,200,255,0.12)', glow: 'rgba(40,60,120,0.15)', stars: true };
        if (t < sun.sunrise)             return { sky: '#e65100', upper: '#ff6d00', top: '#ffab40', cloud: 'rgba(255,220,180,0.3)', glow: 'rgba(255,160,60,0.22)', stars: false };
        if (t < sun.sunrise + 1.5)       return { sky: '#ff8a65', upper: '#ffab91', top: '#ffe082', cloud: 'rgba(255,255,255,0.4)', glow: 'rgba(255,200,100,0.18)', stars: false };
        if (t < sun.sunrise + 3)         return { sky: '#42a5f5', upper: '#64b5f6', top: '#e3f2fd', cloud: 'rgba(255,255,255,0.5)', glow: 'rgba(255,240,200,0.12)', stars: false };
        if (t < sun.sunset - 2)          return { sky: '#2196f3', upper: '#42a5f5', top: '#bbdefb', cloud: 'rgba(255,255,255,0.5)', glow: 'rgba(255,255,240,0.08)', stars: false };
        if (t < sun.sunset - 0.5)        return { sky: '#42a5f5', upper: '#64b5f6', top: '#ffe0b2', cloud: 'rgba(255,255,255,0.45)', glow: 'rgba(255,200,100,0.12)', stars: false };
        if (t < sun.sunset + 0.3)        return { sky: '#e65100', upper: '#ff6d00', top: '#ff8a65', cloud: 'rgba(255,200,150,0.35)', glow: 'rgba(255,120,40,0.22)', stars: false };
        if (t < sun.dusk)                return { sky: '#4a148c', upper: '#6a1b9a', top: '#e65100', cloud: 'rgba(180,160,255,0.2)', glow: 'rgba(150,80,180,0.15)', stars: false };
        return                                  { sky: '#0d1b2a', upper: '#162032', top: '#0a1020', cloud: 'rgba(200,200,255,0.12)', glow: 'rgba(40,60,120,0.15)', stars: true };
    }
    _tod = getTimeOfDaySky();

    function drawWindow(wx, wy, ww, wh) {
        // Outer sill / ledge
        ctx.fillStyle = '#999'; ctx.fillRect(wx - 4, wy - 4, ww + 8, wh + 8);
        // Inner frame
        ctx.fillStyle = '#e0e0e0'; ctx.fillRect(wx - 2, wy - 2, ww + 4, wh + 4);
        // Glass — sky (time-of-day)
        ctx.fillStyle = _tod.sky; ctx.fillRect(wx, wy, ww, wh);
        ctx.fillStyle = _tod.upper; ctx.fillRect(wx, wy, ww, Math.floor(wh * 0.35));
        ctx.fillStyle = _tod.top; ctx.fillRect(wx, wy, ww, Math.floor(wh * 0.15));
        // Stars at night (twinkling)
        if (_tod.stars) {
            var _stars = [
                { x: 6, y: 8, s: 2 }, { x: 18, y: 4, s: 1 }, { x: 12, y: 18, s: 2 },
                { x: 28, y: 12, s: 1 }, { x: 24, y: 6, s: 1.5 }, { x: 8, y: 28, s: 1 },
                { x: 32, y: 20, s: 1 }, { x: 15, y: 32, s: 1.5 }, { x: 3, y: 22, s: 1 }
            ];
            for (var si = 0; si < _stars.length; si++) {
                var star = _stars[si];
                // Each star twinkles at its own rate
                var twinkle = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(_weatherTick * 0.04 + si * 2.3));
                ctx.fillStyle = 'rgba(255,255,255,' + twinkle.toFixed(2) + ')';
                ctx.fillRect(wx + star.x, wy + star.y, star.s, star.s);
            }
            // Moon — left window only
            if (wx < 500) {
                ctx.fillStyle = 'rgba(255,255,220,0.8)';
                ctx.fillRect(wx + ww - 12, wy + 4, 6, 6);
                ctx.fillStyle = _tod.sky;
                ctx.fillRect(wx + ww - 10, wy + 3, 5, 5); // crescent cutout
            }
        }
        // Clouds (skip at night)
        if (!_tod.stars) {
            ctx.fillStyle = _tod.cloud;
            ctx.fillRect(wx + 4, wy + 6, 8, 3);
            ctx.fillRect(wx + 6, wy + 4, 4, 2);
            ctx.fillRect(wx + ww - 14, wy + 10, 6, 2);
            ctx.fillRect(wx + ww - 12, wy + 8, 4, 2);
        }
        // Weather effects on glass (isLeft=true for left window only — sun/moon)
        if (_displayPrefs.showWeather !== false) drawWeatherOnWindow(wx, wy, ww, wh, wx < 500);
        // Cross panes (thicker) — always on top
        ctx.fillStyle = '#fff';
        ctx.fillRect(wx + Math.floor(ww / 2) - 1, wy, 3, wh);  // vertical
        ctx.fillRect(wx, wy + Math.floor(wh / 2) - 1, ww, 3);  // horizontal
        // Pane corner accents
        ctx.fillStyle = '#ccc';
        ctx.fillRect(wx + Math.floor(ww/2) - 2, wy + Math.floor(wh/2) - 2, 5, 5);
        // Subtle glass shine — small corner highlights only (don't cover the sky)
        ctx.fillStyle = 'rgba(255,255,255,0.15)';
        ctx.fillRect(wx + 2, wy + 2, 5, 3);   // top-left glint
        ctx.fillRect(wx + 3, wy + 4, 3, 2);
        ctx.fillStyle = 'rgba(255,255,255,0.08)';
        const px = wx + Math.floor(ww/2) + 4, py = wy + Math.floor(wh/2) + 4;
        ctx.fillRect(px, py, 4, 3);            // bottom-right glint
        // Bottom sill detail
        ctx.fillStyle = '#bbb';
        ctx.fillRect(wx - 3, wy + wh + 2, ww + 6, 3);
        ctx.fillStyle = '#ddd';
        ctx.fillRect(wx - 2, wy + wh + 2, ww + 4, 1);
        // --- LIGHT PROJECTION on floor below window (gradient fade) ---
        var lightTop = wy + wh + 5;
        var lightBottom = wy + wh + 120;
        var lightGrad = ctx.createLinearGradient(0, lightTop, 0, lightBottom);
        lightGrad.addColorStop(0, _tod.glow);
        lightGrad.addColorStop(0.4, _tod.glow.replace(/[\d.]+\)$/, function(m) { return (parseFloat(m) * 0.5).toFixed(2) + ')'; }));
        lightGrad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = lightGrad;
        ctx.beginPath();
        ctx.moveTo(wx - 2, lightTop);
        ctx.lineTo(wx + ww + 2, lightTop);
        ctx.lineTo(wx + ww + 40, lightBottom);
        ctx.lineTo(wx - 40, lightBottom);
        ctx.closePath();
        ctx.fill();
    }

    // --- SECTION LABELS ---
    ctx.font = 'bold 10px "Press Start 2P", monospace'; ctx.textAlign = 'center';
    // Branch signs are now rendered as branchSign furniture items

    // --- INTERIOR WALL SHADOWS (above floor, below everything else) ---
    drawInteriorWallShadows();

    // --- INTERIOR WALLS (drawn before furniture so items aren't hidden behind walls) ---
    drawInteriorWalls();

    // --- FURNITURE (data-driven from officeConfig) — non-label items first ---
    officeConfig.furniture.forEach(function(item) {
        if (item.type !== 'branchSign' && item.type !== 'textLabel') drawFurnitureItem(item);
    });

    // --- LABELS (drawn on top of everything) ---
    officeConfig.furniture.forEach(function(item) {
        if (item.type === 'branchSign' || item.type === 'textLabel') drawFurnitureItem(item);
    });
}

// ============================================================
// INTERIOR WALLS
// ============================================================

function _wallMainColor(wall) {
    return (wall && wall.color) || '#546e7a';
}
function _wallAccentColor(wall) {
    return (wall && wall.accentColor) || _wallMainColor(wall);
}
function _wallTrimColor(wall) {
    return (wall && wall.trimColor) || '#ffffff';
}
function _wallTrim2Color(wall) {
    return (wall && wall.trim2Color) || '#37474f';
}

function drawInteriorWallShadows() {
    var interior = officeConfig.walls && officeConfig.walls.interior;
    if (!interior || interior.length === 0) return;
    var wallThick = 6;
    interior.forEach(function(wall) {
        if (wall.x1 === wall.x2) return;
        var px = Math.min(wall.x1, wall.x2) * TILE;
        var py = wall.y1 * TILE - Math.floor(wallThick / 2);
        var pw = Math.abs(wall.x2 - wall.x1) * TILE;
        if (pw <= 0) return;
        ctx.fillStyle = 'rgba(0,0,0,0.12)';
        ctx.fillRect(px, py + wallThick, pw, 15);
    });
}

function _drawSingleWall(wall, idx) {
    var wallThick = 6;
    var isSel = (editMode && selectedWallIdx === idx);
    var mainColor = isSel ? '#ffd600' : _wallMainColor(wall);
    if (wall.x1 === wall.x2) {
        // Vertical wall
        var px = wall.x1 * TILE - Math.floor(wallThick / 2);
        var py = Math.min(wall.y1, wall.y2) * TILE;
        var ph = Math.abs(wall.y2 - wall.y1) * TILE;
        if (ph <= 0) return;
        // Shadow (right side depth)
        ctx.fillStyle = 'rgba(0,0,0,0.28)';
        ctx.fillRect(px + wallThick, py + 2, 3, ph - 2);
        // Main wall body
        ctx.fillStyle = mainColor;
        ctx.fillRect(px, py, wallThick, ph);
        // Highlight (left edge)
        ctx.fillStyle = isSel ? 'rgba(255,255,200,0.5)' : 'rgba(255,255,255,0.20)';
        ctx.fillRect(px, py, 2, ph);
        // Dark right edge (inner shadow)
        ctx.fillStyle = 'rgba(0,0,0,0.18)';
        ctx.fillRect(px + wallThick - 2, py, 2, ph);
    } else {
        // Horizontal wall with upward wall face
        var px = Math.min(wall.x1, wall.x2) * TILE;
        var py = wall.y1 * TILE - Math.floor(wallThick / 2);
        var pw = Math.abs(wall.x2 - wall.x1) * TILE;
        var faceH = 36;
        if (pw <= 0) return;
        // Main wall body / face
        ctx.fillStyle = isSel ? '#f9a825' : mainColor;
        ctx.fillRect(px + 1, py - faceH, pw - 2, faceH);
        // Trim stripe
        ctx.fillStyle = isSel ? '#fff3b0' : _wallTrimColor(wall);
        ctx.fillRect(px + 1, py - 8, pw - 2, 4);
        // Trim 2 lower band + map-plane edge merged together
        ctx.fillStyle = isSel ? '#ffca28' : _wallTrim2Color(wall);
        ctx.fillRect(px, py - 4, pw, wallThick + 4);
        // Top cap highlight
        ctx.fillStyle = isSel ? 'rgba(255,245,180,0.45)' : 'rgba(255,255,255,0.12)';
        ctx.fillRect(px + 2, py - faceH, pw - 4, 2);
    }
}

function _verticalWallGoesDown(wall, interior) {
    // A vertical wall "goes down" if its top end connects to a horizontal wall
    // and the wall extends downward from that junction
    if (wall.x1 !== wall.x2) return false; // not vertical
    var topY = Math.min(wall.y1, wall.y2);
    var wallX = wall.x1;
    for (var i = 0; i < interior.length; i++) {
        var hw = interior[i];
        if (hw.x1 === hw.x2) continue; // skip other verticals
        var hLeft = Math.min(hw.x1, hw.x2);
        var hRight = Math.max(hw.x1, hw.x2);
        if (wallX >= hLeft && wallX <= hRight && Math.abs(topY - hw.y1) <= 1) {
            return true; // top of vertical wall meets a horizontal wall — it goes down
        }
    }
    return false;
}

function drawInteriorWalls() {
    var interior = officeConfig.walls && officeConfig.walls.interior;
    if (!interior || interior.length === 0) return;
    // Pass 1: vertical walls going UP + all horizontal walls
    interior.forEach(function(wall, idx) {
        if (wall.x1 === wall.x2 && _verticalWallGoesDown(wall, interior)) return; // skip downward verticals
        _drawSingleWall(wall, idx);
    });
    // Pass 2: vertical walls going DOWN (drawn on top of horizontal walls)
    interior.forEach(function(wall, idx) {
        if (wall.x1 === wall.x2 && _verticalWallGoesDown(wall, interior)) {
            _drawSingleWall(wall, idx);
        }
    });
}

function drawInteriorWallOccluders() {
    var interior = officeConfig.walls && officeConfig.walls.interior;
    if (!interior || interior.length === 0) return;
    var wallThick = 6;
    var faceH = 36;
    interior.forEach(function(wall, idx) {
        var isSel = (editMode && selectedWallIdx === idx);
        if (wall.x1 !== wall.x2) {
            var px = Math.min(wall.x1, wall.x2) * TILE;
            var py = wall.y1 * TILE - Math.floor(wallThick / 2);
            var pw = Math.abs(wall.x2 - wall.x1) * TILE;
            if (pw <= 0) return;
            ctx.fillStyle = isSel ? '#f9a825' : _wallMainColor(wall);
            ctx.fillRect(px + 1, py - faceH, pw - 2, faceH);
            ctx.fillStyle = isSel ? 'rgba(255,245,180,0.35)' : 'rgba(255,255,255,0.10)';
            ctx.fillRect(px + 2, py - faceH, pw - 4, 2);
            ctx.fillStyle = isSel ? '#fff3b0' : _wallTrimColor(wall);
            ctx.fillRect(px + 1, py - 8, pw - 2, 4);
            ctx.fillStyle = isSel ? '#ffca28' : _wallTrim2Color(wall);
            ctx.fillRect(px, py - 4, pw, wallThick + 4);
            // No manual ambient tint needed — ambient overlay draws after occluders now
        }
    });
}

function _isFurnitureNearHorizontalWall(item) {
    var interior = (officeConfig.walls && officeConfig.walls.interior) || [];
    var bounds = FURNITURE_BOUNDS[item.type] || { w: 40, h: 40 };
    var ix = item.x, iy = item.y, iw = bounds.w, ih = bounds.h;
    for (var i = 0; i < interior.length; i++) {
        var wall = interior[i];
        if (wall.x1 === wall.x2) continue; // skip vertical walls
        var px = Math.min(wall.x1, wall.x2) * TILE;
        var pw = Math.abs(wall.x2 - wall.x1) * TILE;
        var py = wall.y1 * TILE;
        var faceH = 36;
        // Check if furniture overlaps the wall's face area (with some margin)
        if (ix + iw > px && ix < px + pw && iy < py + 10 && iy + ih > py - faceH - 16) {
            return true;
        }
    }
    return false;
}

// Classify furniture as IN FRONT of a horizontal wall (should render on top of occluders)
// vs BEHIND it (should stay behind occluders, i.e. NOT redrawn after occluders).
// "In front" = furniture's bottom edge is at or below the wall base line.
// Uses FURNITURE_BOUNDS to compute the actual visual bottom edge.
function _isFurnitureInFrontOfWall(item) {
    var interior = (officeConfig.walls && officeConfig.walls.interior) || [];
    var bounds = FURNITURE_BOUNDS[item.type] || { w: 40, h: 40, ox: 0, oy: 0 };
    var ox = bounds.ox || 0, oy = bounds.oy || 0;
    // Compute the visual bottom Y of this furniture item
    var itemBottomY = item.y + bounds.h * (1 - oy);

    for (var i = 0; i < interior.length; i++) {
        var wall = interior[i];
        if (wall.x1 === wall.x2) continue; // skip vertical walls
        var px = Math.min(wall.x1, wall.x2) * TILE;
        var pw = Math.abs(wall.x2 - wall.x1) * TILE;
        var py = wall.y1 * TILE; // wall base line in pixels
        var faceH = 36;

        // Item must horizontally overlap the wall
        var itemLeft = item.x - bounds.w * ox;
        var itemRight = itemLeft + bounds.w;
        if (itemRight <= px || itemLeft >= px + pw) continue;

        // Check if near this wall (same vertical range as _isFurnitureNearHorizontalWall)
        var itemTopY = item.y - bounds.h * oy;
        if (itemTopY >= py + 10 || itemBottomY <= py - faceH - 16) continue;

        // Near this wall — is the item IN FRONT (below wall base)?
        // Wall base is at py. Furniture whose bottom edge extends past py is in front.
        if (itemBottomY >= py - 4) {
            return true; // in front — should be redrawn after occluders
        }
        // Otherwise, furniture is behind — should NOT be redrawn after occluders
        return false;
    }
    // Not near any wall
    return false;
}

// Check if a desk (by agent desk coords) is behind a horizontal wall
// Used to decide whether desk char items should be drawn before or after occluders
function _isDeskBehindHorizontalWall(deskX, deskY) {
    var interior = (officeConfig.walls && officeConfig.walls.interior) || [];
    var bounds = FURNITURE_BOUNDS['desk'] || { w: 72, h: 76, ox: 0.5, oy: 0.66 };
    var deskBottomY = deskY + bounds.h * (1 - (bounds.oy || 0));
    for (var i = 0; i < interior.length; i++) {
        var wall = interior[i];
        if (wall.x1 === wall.x2) continue;
        var px = Math.min(wall.x1, wall.x2) * TILE;
        var pw = Math.abs(wall.x2 - wall.x1) * TILE;
        var py = wall.y1 * TILE;
        var faceH = 36;
        // Check horizontal overlap
        if (deskX < px || deskX > px + pw) continue;
        // Check vertical proximity (same as agent behind-wall check)
        if (deskY >= py - faceH - 16 && deskY < py + 10) {
            // Desk is near this wall — is it behind?
            if (deskBottomY < py - 4) return true; // behind
        }
    }
    return false;
}

function _isAgentBehindHorizontalWall(agent) {
    var interior = (officeConfig.walls && officeConfig.walls.interior) || [];
    for (var i = 0; i < interior.length; i++) {
        var wall = interior[i];
        if (wall.x1 === wall.x2) continue;
        var px = Math.min(wall.x1, wall.x2) * TILE;
        var pw = Math.abs(wall.x2 - wall.x1) * TILE;
        var py = wall.y1 * TILE - Math.floor(6 / 2);
        var faceH = 36;
        if (agent.x >= px && agent.x <= px + pw && agent.y >= py - faceH - 8 && agent.y < py + 2) {
            return true;
        }
    }
    return false;
}

// ============================================================
// COLLISION GRID
// ============================================================

function buildCollisionGrid() {
    var cols = Math.ceil(W / TILE);
    var rows = Math.ceil(H / TILE);
    collisionGrid = [];
    for (var ty = 0; ty < rows; ty++) {
        collisionGrid[ty] = [];
        for (var tx = 0; tx < cols; tx++) {
            collisionGrid[ty][tx] = { top: false, right: false, bottom: false, left: false };
        }
    }
    // Mark canvas boundaries
    for (var tx = 0; tx < cols; tx++) {
        collisionGrid[0][tx].top = true;
        collisionGrid[rows - 1][tx].bottom = true;
    }
    for (var ty = 0; ty < rows; ty++) {
        collisionGrid[ty][0].left = true;
        collisionGrid[ty][cols - 1].right = true;
    }
    // Mark interior walls
    var interior = (officeConfig.walls && officeConfig.walls.interior) || [];
    interior.forEach(function(wall) {
        if (wall.x1 === wall.x2) {
            // Vertical wall at tile column wall.x1 (boundary between col x1-1 and x1)
            var minY = Math.min(wall.y1, wall.y2);
            var maxY = Math.max(wall.y1, wall.y2);
            var wallTx = wall.x1;
            for (var ty = minY; ty < maxY; ty++) {
                if (ty < 0 || ty >= rows) continue;
                if (wallTx < cols) collisionGrid[ty][wallTx].left = true;
                if (wallTx > 0 && wallTx - 1 < cols) collisionGrid[ty][wallTx - 1].right = true;
            }
        } else {
            // Horizontal wall at tile row wall.y1 (boundary between row y1-1 and y1)
            var minX = Math.min(wall.x1, wall.x2);
            var maxX = Math.max(wall.x1, wall.x2);
            var wallTy = wall.y1;
            for (var tx = minX; tx < maxX; tx++) {
                if (tx < 0 || tx >= cols) continue;
                if (wallTy < rows) collisionGrid[wallTy][tx].top = true;
                if (wallTy > 0 && wallTy - 1 < rows) collisionGrid[wallTy - 1][tx].bottom = true;
            }
        }
    });
}

// ============================================================
// A* PATHFINDING
// ============================================================

function findPath(startX, startY, endX, endY) {
    if (!collisionGrid) return null;
    var cols = Math.ceil(W / TILE);
    var rows = Math.ceil(H / TILE);
    var sx = Math.max(0, Math.min(cols - 1, Math.floor(startX / TILE)));
    var sy = Math.max(0, Math.min(rows - 1, Math.floor(startY / TILE)));
    var ex = Math.max(0, Math.min(cols - 1, Math.floor(endX / TILE)));
    var ey = Math.max(0, Math.min(rows - 1, Math.floor(endY / TILE)));
    if (sx === ex && sy === ey) return [];
    var startNode = { x: sx, y: sy, g: 0, h: Math.abs(ex - sx) + Math.abs(ey - sy), f: 0, parent: null };
    startNode.f = startNode.h;
    var open = [startNode];
    var closed = {};
    var openMap = {};
    openMap[sy * cols + sx] = startNode;
    var dirs = [
        { dx: 0,  dy: -1, check: 'top'    },
        { dx: 1,  dy:  0, check: 'right'  },
        { dx: 0,  dy:  1, check: 'bottom' },
        { dx: -1, dy:  0, check: 'left'   },
    ];
    var maxIter = cols * rows * 2;
    var iter = 0;
    while (open.length > 0 && iter < maxIter) {
        iter++;
        var bestIdx = 0;
        for (var i = 1; i < open.length; i++) {
            if (open[i].f < open[bestIdx].f) bestIdx = i;
        }
        var current = open[bestIdx];
        open.splice(bestIdx, 1);
        var key = current.y * cols + current.x;
        closed[key] = true;
        delete openMap[key];
        if (current.x === ex && current.y === ey) {
            var path = [];
            var node = current;
            while (node) {
                path.unshift({ x: node.x * TILE + TILE / 2, y: node.y * TILE + TILE / 2 });
                node = node.parent;
            }
            if (path.length > 0) path.shift(); // remove start position
            return path;
        }
        for (var d = 0; d < dirs.length; d++) {
            var dir = dirs[d];
            var nx = current.x + dir.dx;
            var ny = current.y + dir.dy;
            if (nx < 0 || nx >= cols || ny < 0 || ny >= rows) continue;
            var nkey = ny * cols + nx;
            if (closed[nkey]) continue;
            var crow = collisionGrid[current.y];
            if (!crow || !crow[current.x]) continue;
            if (crow[current.x][dir.check]) continue; // wall blocks this direction
            var g = current.g + 1;
            var h = Math.abs(ex - nx) + Math.abs(ey - ny);
            var f = g + h;
            if (openMap[nkey]) {
                if (openMap[nkey].g <= g) continue;
                openMap[nkey].g = g; openMap[nkey].h = h; openMap[nkey].f = f; openMap[nkey].parent = current;
            } else {
                var neighbor = { x: nx, y: ny, g: g, h: h, f: f, parent: current };
                open.push(neighbor);
                openMap[nkey] = neighbor;
            }
        }
    }
    return null; // no path
}

function _deleteSelectedWall() {
    if (selectedWallIdx === null) return;
    _pushUndo();
    officeConfig.walls.interior.splice(selectedWallIdx, 1);
    selectedWallIdx = null;
    buildCollisionGrid();
}

function drawWhiteboard(x, y) {
    ctx.fillStyle = '#eceff1'; ctx.fillRect(x, y, 28, 40);
    ctx.fillStyle = '#fafafa'; ctx.fillRect(x + 2, y + 2, 24, 36);
    // Scribbles
    ctx.strokeStyle = '#1976d2'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x+5,y+8); ctx.lineTo(x+20,y+10); ctx.stroke();
    ctx.strokeStyle = '#d32f2f';
    ctx.beginPath(); ctx.moveTo(x+5,y+16); ctx.lineTo(x+18,y+15); ctx.stroke();
    ctx.strokeStyle = '#388e3c';
    ctx.beginPath(); ctx.moveTo(x+5,y+24); ctx.lineTo(x+22,y+23); ctx.stroke();
    // Marker tray
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 4, y + 40, 20, 3);
    ctx.fillStyle = '#d32f2f'; ctx.fillRect(x + 6, y + 40, 4, 3);
    ctx.fillStyle = '#1976d2'; ctx.fillRect(x + 12, y + 40, 4, 3);
    ctx.fillStyle = '#388e3c'; ctx.fillRect(x + 18, y + 40, 4, 3);
}

function drawWindow(x, y) {
    ctx.fillStyle = '#eceff1'; ctx.fillRect(x, y, 60, 40);
    ctx.fillStyle = '#81d4fa'; ctx.fillRect(x + 4, y + 4, 52, 32);
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.beginPath(); ctx.moveTo(x + 40, y + 4); ctx.lineTo(x + 56, y + 4); ctx.lineTo(x + 10, y + 36); ctx.lineTo(x + 4, y + 36); ctx.fill();
    ctx.strokeStyle = '#b0bec5'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x + 30, y + 4); ctx.lineTo(x + 30, y + 36); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x + 4, y + 20); ctx.lineTo(x + 56, y + 20); ctx.stroke();
    ctx.lineWidth = 1;
}

function drawClock(x, y) {
    ctx.fillStyle = '#546e7a'; ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fill();
    const now = new Date();
    const ha = (now.getHours() % 12 + now.getMinutes() / 60) * (Math.PI * 2 / 12) - Math.PI / 2;
    const ma = (now.getMinutes() / 60) * Math.PI * 2 - Math.PI / 2;
    ctx.strokeStyle = '#333'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(ha) * 6, y + Math.sin(ha) * 6); ctx.stroke();
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(ma) * 9, y + Math.sin(ma) * 9); ctx.stroke();
}

function _getDeskAgent(item) {
    if (!item) return null;
    var assigned = item.assignedTo || item.agentId || item.agent;
    for (var i = 0; i < agents.length; i++) {
        var a = agents[i];
        if (assigned && (a.name === assigned || a.id === assigned || a.statusKey === assigned)) return a;
        if (a.desk && Math.abs(a.desk.x - item.x) < 1 && Math.abs(a.desk.y - item.y) < 1) return a;
    }
    return null;
}

function _isDeskScreenActive(item) {
    var agent = _getDeskAgent(item);
    return !!(agent && (agent.state === 'working' || agent.state === 'finishing'));
}

function _drawCodeScreen(x, y, w, h, active, seed) {
    var bg = active ? '#06243f' : '#0d47a1';
    ctx.fillStyle = bg;
    ctx.fillRect(x, y, w, h);

    if (!active) {
        ctx.fillStyle = '#4fc3f7';
        ctx.fillRect(x + 3, y + 3, Math.min(12, w - 8), 2);
        ctx.fillRect(x + 3, y + 7, Math.min(20, w - 8), 2);
        ctx.fillRect(x + 3, y + 11, Math.min(8, w - 8), 2);
        return;
    }

    var pulse = 0.45 + Math.sin(Date.now() * 0.008 + seed) * 0.25;
    ctx.fillStyle = 'rgba(79,195,247,' + pulse.toFixed(3) + ')';
    ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
    ctx.fillStyle = bg;
    ctx.fillRect(x, y, w, h);

    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    var lineH = 4;
    var offset = Math.floor((Date.now() / 120 + seed * 3) % lineH);
    for (var row = -lineH; row < h + lineH; row += lineH) {
        var ly = y + row - offset;
        var idx = Math.floor((row + seed * 11) / lineH);
        var len = 7 + ((idx * 7 + seed * 5) % Math.max(8, w - 10));
        ctx.fillStyle = (idx % 4 === 0) ? '#a5f3fc' : (idx % 3 === 0) ? '#66bb6a' : '#4fc3f7';
        ctx.fillRect(x + 3, ly + 1, Math.min(len, w - 6), 2);
        if (idx % 5 === 0) {
            ctx.fillStyle = '#ffca28';
            ctx.fillRect(x + w - 7, ly + 1, 4, 2);
        }
    }
    ctx.restore();
}

function drawDesk(x, y, screenActive) {
    ctx.save(); ctx.translate(x, y);
    // Desk shadow
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(-36, -20, 76, 54);
    // Desk surface
    ctx.fillStyle = '#8d6e63'; ctx.fillRect(-35, -25, 70, 45);
    ctx.fillStyle = '#a1887f'; ctx.fillRect(-33, -23, 66, 41);
    // Desk edge
    ctx.fillStyle = '#6d4c41'; ctx.fillRect(-35, 18, 70, 4);
    // Desk legs
    ctx.fillStyle = '#5d4037'; ctx.fillRect(-33, 20, 4, 6); ctx.fillRect(29, 20, 4, 6);
    // Monitor
    ctx.fillStyle = '#263238'; ctx.fillRect(-20, -48, 40, 26);
    // Screen glow
    ctx.fillStyle = screenActive ? 'rgba(79,195,247,0.28)' : 'rgba(33,150,243,0.15)';
    ctx.fillRect(-22, -50, 44, 30);
    _drawCodeScreen(-17, -45, 34, 20, screenActive, 1);
    // Monitor stand
    ctx.fillStyle = '#37474f'; ctx.fillRect(-5, -22, 10, 4);
    // Keyboard
    ctx.fillStyle = '#455a64'; ctx.fillRect(-15, -18, 30, 8);
    ctx.fillStyle = '#546e7a';
    for (let i = 0; i < 5; i++) ctx.fillRect(-13 + i * 6, -16, 4, 2);
    for (let i = 0; i < 4; i++) ctx.fillRect(-10 + i * 6, -13, 4, 2);
    // Mouse
    ctx.fillStyle = '#78909c'; ctx.fillRect(20, -5, 6, 8);
    ctx.fillStyle = '#90a4ae'; ctx.fillRect(21, -4, 4, 3);

    // Desk item spots: left (-28, 5) and right (24, 4)
    // Items drawn dynamically by agent (carry system or defaults)
    ctx.restore();
}

function drawBossDesk(x, y, screenActive) {
    ctx.save(); ctx.translate(x, y);
    // Bounds: 130×90, origin at center (0,0) → draws from -65,-45 to 65,45

    // === LEGS (visible at front, peeking below desk) ===
    ctx.fillStyle = '#3e2723';
    // Front legs
    ctx.fillRect(-58, 36, 6, 10);
    ctx.fillRect(52, 36, 6, 10);
    // Back legs (partially hidden)
    ctx.fillRect(-58, -40, 6, 6);
    ctx.fillRect(52, -40, 6, 6);
    // Leg highlights
    ctx.fillStyle = '#5d4037';
    ctx.fillRect(-57, 37, 2, 8);
    ctx.fillRect(53, 37, 2, 8);

    // === DESK SHADOW ===
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.fillRect(-60, -38, 124, 84);

    // === DESK BODY (L-shaped return) ===
    // Main desktop surface
    ctx.fillStyle = '#5d4037';
    ctx.fillRect(-62, -42, 124, 78);
    // Polished wood surface
    ctx.fillStyle = '#795548';
    ctx.fillRect(-60, -40, 120, 74);
    // Rich wood grain top
    ctx.fillStyle = '#8d6e63';
    ctx.fillRect(-58, -38, 116, 70);

    // Wood grain lines (subtle)
    ctx.fillStyle = 'rgba(0,0,0,0.04)';
    ctx.fillRect(-58, -28, 116, 1);
    ctx.fillRect(-58, -14, 116, 1);
    ctx.fillRect(-58, 0, 116, 1);
    ctx.fillRect(-58, 14, 116, 1);

    // === SIDE PANEL / MODESTY PANEL (front face of desk) ===
    ctx.fillStyle = '#6d4c41';
    ctx.fillRect(-62, 28, 124, 8);
    // Panel detail line
    ctx.fillStyle = '#5d4037';
    ctx.fillRect(-60, 30, 120, 1);
    ctx.fillRect(-60, 34, 120, 1);

    // === DESK EDGE (polished trim) ===
    ctx.fillStyle = '#4e342e';
    ctx.fillRect(-62, -42, 124, 3);
    ctx.fillRect(-62, -42, 3, 78);
    ctx.fillRect(59, -42, 3, 78);

    // Gold accent trim along front edge
    ctx.fillStyle = 'rgba(255,215,0,0.25)';
    ctx.fillRect(-60, 33, 120, 1);

    // === LEFT DRAWER UNIT ===
    ctx.fillStyle = '#6d4c41';
    ctx.fillRect(-56, -10, 28, 36);
    ctx.fillStyle = '#795548';
    ctx.fillRect(-54, -8, 24, 14);
    ctx.fillRect(-54, 8, 24, 16);
    // Drawer handles (gold)
    ctx.fillStyle = '#ffd700';
    ctx.fillRect(-46, -2, 10, 2);
    ctx.fillRect(-46, 14, 10, 2);
    // Handle shine
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.fillRect(-44, -2, 4, 1);
    ctx.fillRect(-44, 14, 4, 1);

    // === RIGHT DRAWER UNIT ===
    ctx.fillStyle = '#6d4c41';
    ctx.fillRect(28, -10, 28, 36);
    ctx.fillStyle = '#795548';
    ctx.fillRect(30, -8, 24, 14);
    ctx.fillRect(30, 8, 24, 16);
    // Drawer handles (gold)
    ctx.fillStyle = '#ffd700';
    ctx.fillRect(38, -2, 10, 2);
    ctx.fillRect(38, 14, 10, 2);
    // Handle shine
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.fillRect(40, -2, 4, 1);
    ctx.fillRect(40, 14, 4, 1);

    // === DUAL MONITORS ===
    // Left monitor
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(-40, -36, 34, 24);
    ctx.fillStyle = '#263238';
    ctx.fillRect(-38, -34, 30, 20);
    // Screen glow
    ctx.fillStyle = screenActive ? 'rgba(79,195,247,0.28)' : '#4fc3f7';
    ctx.fillRect(-36, -32, 26, 16);
    _drawCodeScreen(-36, -32, 26, 16, screenActive, 2);
    // Monitor stand
    ctx.fillStyle = '#37474f';
    ctx.fillRect(-28, -12, 12, 3);
    ctx.fillRect(-25, -14, 6, 2);

    // Right monitor
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(6, -36, 34, 24);
    ctx.fillStyle = '#263238';
    ctx.fillRect(8, -34, 30, 20);
    ctx.fillStyle = screenActive ? 'rgba(79,195,247,0.28)' : '#4fc3f7';
    ctx.fillRect(10, -32, 26, 16);
    if (screenActive) {
        _drawCodeScreen(10, -32, 26, 16, true, 3);
    } else {
        // Chart/graph on screen
        ctx.fillStyle = '#4caf50';
        ctx.fillRect(14, -26, 4, 8);
        ctx.fillRect(20, -28, 4, 10);
        ctx.fillStyle = '#ff9800';
        ctx.fillRect(26, -24, 4, 6);
        ctx.fillRect(32, -30, 4, 12);
    }
    // Monitor stand
    ctx.fillStyle = '#37474f';
    ctx.fillRect(16, -12, 12, 3);
    ctx.fillRect(19, -14, 6, 2);

    // === KEYBOARD ===
    ctx.fillStyle = '#333';
    ctx.fillRect(-14, -8, 28, 8);
    ctx.fillStyle = '#444';
    ctx.fillRect(-12, -6, 24, 4);
    // Key rows
    ctx.fillStyle = '#555';
    ctx.fillRect(-11, -5, 22, 1);
    ctx.fillRect(-11, -3, 22, 1);

    // === MOUSE ===
    ctx.fillStyle = '#333';
    ctx.fillRect(18, -6, 6, 8);
    ctx.fillStyle = '#444';
    ctx.fillRect(19, -5, 4, 3);

    // === DESK ITEMS ===
    // Coffee mug (left side)
    ctx.fillStyle = '#fff';
    ctx.fillRect(-50, -30, 7, 8);
    ctx.fillStyle = '#e0e0e0';
    ctx.fillRect(-49, -29, 5, 6);
    ctx.fillStyle = '#6d4c41';
    ctx.fillRect(-48, -28, 3, 4);
    // Mug handle
    ctx.fillStyle = '#fff';
    ctx.fillRect(-44, -28, 2, 4);

    // Pen holder (right side)
    ctx.fillStyle = '#455a64';
    ctx.fillRect(46, -28, 8, 10);
    ctx.fillStyle = '#546e7a';
    ctx.fillRect(47, -27, 6, 8);
    // Pens
    ctx.fillStyle = '#1565c0';
    ctx.fillRect(48, -32, 1, 6);
    ctx.fillStyle = '#c62828';
    ctx.fillRect(50, -31, 1, 5);
    ctx.fillStyle = '#2e7d32';
    ctx.fillRect(52, -30, 1, 4);

    // Notepad
    ctx.fillStyle = '#fffde7';
    ctx.fillRect(-52, -6, 14, 18);
    ctx.fillStyle = '#fff9c4';
    ctx.fillRect(-51, -5, 12, 16);
    // Lines on notepad
    ctx.fillStyle = '#e0e0e0';
    ctx.fillRect(-50, -2, 10, 1);
    ctx.fillRect(-50, 1, 10, 1);
    ctx.fillRect(-50, 4, 10, 1);

    // Small desk plant
    ctx.fillStyle = '#5d4037';
    ctx.fillRect(44, -6, 10, 8);
    ctx.fillStyle = '#4caf50';
    ctx.fillRect(46, -12, 3, 7);
    ctx.fillRect(50, -10, 3, 5);
    ctx.fillStyle = '#66bb6a';
    ctx.fillRect(45, -14, 4, 3);
    ctx.fillRect(49, -12, 4, 3);

    // === SURFACE HIGHLIGHT (top light reflection) ===
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(-58, -38, 116, 30);

    ctx.restore();
}

function drawFilingCabinet(x, y) {
    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.1)'; ctx.fillRect(x + 2, y + 2, 28, 55);
    // Cabinet body
    ctx.fillStyle = '#607d8b'; ctx.fillRect(x, y, 28, 55);
    ctx.fillStyle = '#78909c'; ctx.fillRect(x + 1, y + 1, 26, 53);
    // Drawers
    ctx.fillStyle = '#b0bec5';
    ctx.fillRect(x + 3, y + 3, 22, 14); ctx.fillRect(x + 3, y + 20, 22, 14); ctx.fillRect(x + 3, y + 37, 22, 14);
    // Handles
    ctx.fillStyle = '#ffd700';
    ctx.fillRect(x + 10, y + 8, 8, 3); ctx.fillRect(x + 10, y + 25, 8, 3); ctx.fillRect(x + 10, y + 42, 8, 3);
    // Label on top drawer
    ctx.fillStyle = '#fff'; ctx.fillRect(x + 7, y + 4, 14, 5);
    ctx.fillStyle = '#1565c0'; ctx.fillRect(x + 8, y + 5, 12, 3);
}

function drawTrashCan(x, y) {
    ctx.fillStyle = '#757575';
    ctx.beginPath(); ctx.ellipse(x, y + 10, 7, 3, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillRect(x - 7, y, 14, 10);
    ctx.fillStyle = '#bdbdbd';
    ctx.beginPath(); ctx.ellipse(x, y, 7, 3, 0, 0, Math.PI * 2); ctx.fill();
}

function drawMeetingRoom(x, y) {
    // Meeting table: 240px wide (6 tiles), 120px tall — inner table is 200px (5 tiles)
    var tw = 240, th = 120;
    var pad = 20;
    var tableX = x + pad, tableY = y + 28;
    var tableW = tw - pad * 2, tableH = 60;  // 200px wide table surface
    _setFurnitureLampShadow(x + tw / 2, y + th / 2);

    // Table shadow
    ctx.fillStyle = 'rgba(0,0,0,0.1)'; ctx.fillRect(tableX + 2, tableY + 4, tableW, tableH);
    // Table frame (dark wood)
    ctx.fillStyle = '#6d4c41'; ctx.fillRect(tableX, tableY, tableW, tableH);
    // Table surface
    ctx.fillStyle = '#8d6e63'; ctx.fillRect(tableX + 2, tableY + 2, tableW - 4, tableH - 4);
    ctx.fillStyle = '#a1887f'; ctx.fillRect(tableX + 4, tableY + 4, tableW - 8, tableH - 8);
    // Table edge
    ctx.fillStyle = '#5d4037'; ctx.fillRect(tableX, tableY + tableH - 4, tableW, 4);
    // Table legs (4 corners, symmetrical)
    ctx.fillStyle = '#4e342e';
    ctx.fillRect(tableX + 3, tableY + tableH, 5, 6);
    ctx.fillRect(tableX + tableW - 8, tableY + tableH, 5, 6);
    ctx.fillRect(tableX + 3, tableY - 4, 5, 4);
    ctx.fillRect(tableX + tableW - 8, tableY - 4, 5, 4);

    // Items on table
    ctx.fillStyle = '#fff'; ctx.fillRect(x + 50, tableY + 8, 14, 18);
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 52, tableY + 10, 10, 4);
    ctx.fillStyle = '#263238'; ctx.fillRect(x + 90, tableY + 6, 28, 18);
    ctx.fillStyle = '#4fc3f7'; ctx.fillRect(x + 92, tableY + 8, 24, 12);
    ctx.fillStyle = '#455a64'; ctx.fillRect(x + 90, tableY + 22, 28, 3);
    ctx.fillStyle = '#fff';
    ctx.fillRect(x + 35, tableY + 16, 5, 6);
    ctx.fillRect(x + tw - 55, tableY + 16, 5, 6);

    // Chairs — 5 per side, evenly spaced across table width
    var chairW = 14;
    var chairSpacing = (tableW - chairW) / 4;  // 4 gaps for 5 chairs
    for (var i = 0; i < 5; i++) {
        var cx = tableX + i * chairSpacing;
        // Top row chairs
        ctx.fillStyle = '#37474f'; ctx.fillRect(cx, y + 8, chairW, 14);
        ctx.fillStyle = '#455a64'; ctx.fillRect(cx + 1, y + 9, chairW - 2, 12);
        ctx.fillStyle = '#546e7a'; ctx.fillRect(cx + 2, y + 10, chairW - 4, 6);
        // Bottom row chairs
        ctx.fillStyle = '#37474f'; ctx.fillRect(cx, y + 96, chairW, 14);
        ctx.fillStyle = '#455a64'; ctx.fillRect(cx + 1, y + 97, chairW - 2, 12);
        ctx.fillStyle = '#546e7a'; ctx.fillRect(cx + 2, y + 98, chairW - 4, 6);
    }
    _clearFurnitureShadow();
}

function _meetingForSpace(item) {
    if (!item || !item.id) return null;
    var ids = Object.keys(activeMeetings || {});
    for (var i = 0; i < ids.length; i++) {
        var meeting = activeMeetings[ids[i]];
        if (meeting && meeting.meetingSpaceId === item.id) return meeting;
    }
    return null;
}

function _drawMeetingSpaceStatus(item, meeting) {
    var b = FURNITURE_BOUNDS[item.type] || { w: 100, h: 80 };
    ctx.save();
    if (meeting) {
        ctx.strokeStyle = 'rgba(76, 175, 80, 0.72)';
        ctx.lineWidth = 2;
        ctx.strokeRect(item.x + 2, item.y + 2, b.w - 4, b.h - 4);
        ctx.fillStyle = '#4caf50';
        ctx.beginPath();
        ctx.arc(item.x + b.w - 12, item.y + 12, 5, 0, Math.PI * 2);
        ctx.fill();
    } else {
        ctx.fillStyle = '#607d8b';
        ctx.fillRect(item.x + b.w - 16, item.y + 8, 8, 8);
    }

    if ((editMode || selectedItemId === item.id) && meeting) {
        var label = meeting.topic || meeting.purpose || _tr('meeting');
        ctx.font = '9px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        var textW = Math.min(168, Math.max(64, ctx.measureText(label).width + 12));
        var lx = item.x + b.w / 2 - textW / 2;
        var ly = item.y - 16;
        ctx.fillStyle = 'rgba(20,20,32,0.86)';
        ctx.fillRect(lx, ly, textW, 13);
        ctx.strokeStyle = '#4caf50';
        ctx.strokeRect(lx, ly, textW, 13);
        ctx.fillStyle = '#fff';
        var clipped = label.length > 22 ? label.slice(0, 21) + '…' : label;
        ctx.fillText(clipped, item.x + b.w / 2, ly + 7);
    }
    ctx.restore();
}

function _drawMeetingChair(cx, cy, faceDir) {
    ctx.fillStyle = '#37474f';
    ctx.fillRect(cx - 7, cy - 7, 14, 14);
    ctx.fillStyle = '#546e7a';
    ctx.fillRect(cx - 5, cy - 5, 10, 8);
    ctx.fillStyle = faceDir === 2 ? '#263238' : '#455a64';
    ctx.fillRect(cx - 6, faceDir === 2 ? cy - 8 : cy + 3, 12, 3);
}

function drawFunctionalMeetingTable(item, seats) {
    var b = FURNITURE_BOUNDS[item.type];
    var meeting = _meetingForSpace(item);
    var tableX = item.x + 18;
    var tableY = item.y + 34;
    var tableW = b.w - 36;
    var tableH = b.h - 52;
    _setFurnitureLampShadow(item.x + b.w / 2, item.y + b.h / 2);
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.fillRect(tableX + 3, tableY + 4, tableW, tableH);
    ctx.fillStyle = '#5d4037';
    drawRoundRect(tableX, tableY, tableW, tableH, 6);
    ctx.fill();
    ctx.fillStyle = '#8d6e63';
    drawRoundRect(tableX + 3, tableY + 3, tableW - 6, tableH - 6, 5);
    ctx.fill();
    ctx.fillStyle = '#cfd8dc';
    ctx.fillRect(tableX + tableW / 2 - 8, tableY + tableH / 2 - 5, 16, 10);
    var slots = _tableSlotsForSpace(item, seats);
    for (var i = 0; i < Math.min(seats, slots.length); i++) {
        _drawMeetingChair(slots[i].x, slots[i].y, slots[i].faceDir);
    }
    _drawMeetingSpaceStatus(item, meeting);
    _clearFurnitureShadow();
}

function drawFunctionalMeetingRoom(item) {
    var b = FURNITURE_BOUNDS[item.type];
    var meeting = _meetingForSpace(item);
    _setFurnitureLampShadow(item.x + b.w / 2, item.y + b.h / 2);
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.fillRect(item.x + 5, item.y + 8, b.w - 10, b.h - 4);
    ctx.fillStyle = '#263238';
    ctx.fillRect(item.x + 8, item.y + 8, b.w - 16, 5);
    ctx.fillRect(item.x + 8, item.y + 8, 5, b.h - 18);
    ctx.fillRect(item.x + b.w - 13, item.y + 8, 5, b.h - 18);
    ctx.fillStyle = 'rgba(69,90,100,0.42)';
    ctx.fillRect(item.x + 14, item.y + 14, b.w - 28, b.h - 28);
    ctx.strokeStyle = '#90a4ae';
    ctx.strokeRect(item.x + 18, item.y + 20, b.w - 36, b.h - 46);
    ctx.fillStyle = '#5d4037';
    drawRoundRect(item.x + 44, item.y + 66, b.w - 88, 48, 7);
    ctx.fill();
    ctx.fillStyle = '#8d6e63';
    drawRoundRect(item.x + 48, item.y + 70, b.w - 96, 40, 6);
    ctx.fill();
    ctx.fillStyle = '#263238';
    ctx.fillRect(item.x + b.w / 2 - 16, item.y + 78, 32, 20);
    ctx.fillStyle = '#4fc3f7';
    ctx.fillRect(item.x + b.w / 2 - 13, item.y + 81, 26, 13);
    var slots = _tableSlotsForSpace(item, 10);
    for (var i = 0; i < 10; i++) _drawMeetingChair(slots[i].x, slots[i].y, slots[i].faceDir);
    _drawMeetingSpaceStatus(item, meeting);
    _clearFurnitureShadow();
}

// --- FURNITURE ITEM DISPATCHER ---
// Called by drawEnvironment for each item in officeConfig.furniture.
function drawFurnitureItem(item) {
    switch (item.type) {
        case 'desk':          drawDesk(item.x, item.y, _isDeskScreenActive(item));          break;
        case 'bossDesk':      drawBossDesk(item.x, item.y, _isDeskScreenActive(item));      break;
        case 'trashCan':      drawTrashCan(item.x, item.y);      break;
        case 'filingCabinet': drawFilingCabinet(item.x, item.y); break;
        case 'whiteboard':    drawWhiteboard(item.x, item.y);    break;
        case 'plant':         drawPlant(item.x, item.y);         break;
        case 'tallPlant':     drawTallPlant(item.x, item.y);     break;
        case 'meetingTable':  drawMeetingRoom(item.x, item.y);   break;
        case 'meetingTable4': drawFunctionalMeetingTable(item, 4); break;
        case 'meetingTable6': drawFunctionalMeetingTable(item, 6); break;
        case 'meetingRoom':   drawFunctionalMeetingRoom(item);   break;
        case 'lounge':        drawLoungeArea(item.x, item.y);    break;
        case 'breakArea':     drawBreakArea(item.x, item.y);     break;
        case 'engLounge':     drawEngLounge(item.x, item.y);     break;
        case 'pingPongTable': drawPingPongTable(item.x, item.y); break;
        case 'dartBoard':     drawDartBoard(item.x, item.y);     break;
        case 'vendingMachine':drawVendingMachine(item.x, item.y);break;
        case 'waterCooler':   drawWaterCooler(item.x, item.y);   break;
        case 'coffeeMaker':   drawCoffeeMakerStandalone(item.x, item.y); break;
        case 'microwave':     drawMicrowaveStandalone(item.x, item.y);   break;
        case 'toaster':       drawToasterStandalone(item.x, item.y);     break;
        case 'window':        drawWindow(item.x, item.y);        break;
        case 'interactiveWindow': drawInteractiveWindow(item); break;
        case 'floorWindow':   drawFloorWindow(item); break;
        case 'clock':         drawClock(item.x, item.y);         break;
        case 'bookshelf':     drawBookshelf(item.x, item.y);     break;
        case 'functionalBookshelf': drawFunctionalBookshelf(item); break;
        case 'couch':         drawCouch(item);                    break;
        case 'coffeeTable':   drawCoffeeTable(item.x, item.y);   break;
        case 'endTable':      drawEndTable(item.x, item.y);      break;
        case 'tv':            drawTV(item.x, item.y);            break;
        case 'kitchenCounter':drawKitchenCounter(item.x, item.y);break;
        case 'branchSign':    drawBranchSign(item);              break;
        case 'textLabel':     drawTextLabel(item);               break;
        case 'floorLamp':     drawFloorLamp(item.x, item.y);    break;
    }
    // When a desk is assigned, update the agent's desk location
    if (item.assignedTo && (item.type === 'desk' || item.type === 'bossDesk')) {
        _syncAgentToDesk(item);
    }
}

// --- INDIVIDUAL LOUNGE PIECES (split from drawLoungeArea) ---
function drawCouch(item) {
    var x, y;
    if (typeof item === 'object' && item.x !== undefined) { x = item.x; y = item.y; }
    else { x = arguments[0]; y = arguments[1]; item = {}; }
    var baseColor = item.couchColor || '#3f51b5';
    var cushionColor = _lightenColor(baseColor, 25);
    var armColor = _darkenColor(baseColor, 0.2);
    var shadowColor = _darkenColor(baseColor, 0.4);
    var backColor = _darkenColor(baseColor, 0.35);
    var rot = item.rotation || 0;

    // Dimensions: main body 160×40, L daybed extension 40×40 at bottom-right
    // Total bounding: 160×80
    ctx.save();
    ctx.translate(x, y);
    if (rot) ctx.rotate(rot * Math.PI / 180);

    _setFurnitureLampShadow(80, 40);

    // Drop shadow
    ctx.fillStyle = 'rgba(0,0,0,0.10)';
    ctx.fillRect(4, 4, 160, 40);
    ctx.fillRect(124, 4, 40, 80);

    // === BACKREST (raised edge along top and right side) ===
    // Top backrest — full width of main body
    ctx.fillStyle = backColor;
    ctx.fillRect(0, 0, 160, 10);
    // Right backrest — runs down the L extension
    ctx.fillRect(150, 0, 10, 80);

    // Backrest highlight (top edge catches light)
    ctx.fillStyle = 'rgba(255,255,255,0.10)';
    ctx.fillRect(0, 0, 160, 3);
    ctx.fillRect(150, 0, 10, 3);

    // Backrest inner shadow (where back meets seat)
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.fillRect(0, 8, 150, 2);
    ctx.fillRect(148, 10, 2, 70);

    // === MAIN SEAT SURFACE (4 tiles wide × 1 tile tall) ===
    ctx.fillStyle = baseColor;
    ctx.fillRect(0, 10, 150, 30);

    // === L DAYBED EXTENSION (below main, right side) ===
    ctx.fillStyle = baseColor;
    ctx.fillRect(120, 40, 30, 40);

    // === ARMRESTS ===
    // Left armrest
    ctx.fillStyle = armColor;
    ctx.fillRect(0, 10, 6, 30);
    // Bottom-left corner arm
    ctx.fillRect(0, 36, 120, 4);
    // Bottom of daybed
    ctx.fillRect(120, 76, 30, 4);

    // Armrest top highlights
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(1, 11, 4, 28);

    // === 4 CUSHIONS on main body ===
    ctx.fillStyle = cushionColor;
    ctx.fillRect(8,  13, 30, 24);
    ctx.fillRect(42, 13, 30, 24);
    ctx.fillRect(76, 13, 30, 24);
    ctx.fillRect(110, 13, 30, 24);

    // Cushion divider lines
    ctx.fillStyle = _darkenColor(cushionColor, 0.1);
    ctx.fillRect(39, 13, 2, 24);
    ctx.fillRect(73, 13, 2, 24);
    ctx.fillRect(107, 13, 2, 24);

    // Cushion top highlights
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.fillRect(9,  14, 28, 4);
    ctx.fillRect(43, 14, 28, 4);
    ctx.fillRect(77, 14, 28, 4);
    ctx.fillRect(111, 14, 28, 4);

    // === DAYBED CUSHION (one long cushion) ===
    ctx.fillStyle = cushionColor;
    ctx.fillRect(123, 43, 24, 30);
    // Highlight
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.fillRect(124, 44, 22, 4);
    // Stitch line down the middle
    ctx.fillStyle = _darkenColor(cushionColor, 0.1);
    ctx.fillRect(134, 43, 1, 30);

        // Feet (small dark circles at corners)
    ctx.fillStyle = '#333';
    ctx.fillRect(1, 38, 3, 3);
    ctx.fillRect(117, 38, 3, 3);
    ctx.fillRect(148, 77, 3, 3);
    ctx.fillRect(1, 8, 3, 3);
    ctx.fillRect(157, 1, 3, 3);

    _clearFurnitureShadow();
    ctx.restore();
}

function drawCoffeeTable(x, y) {
    _setFurnitureLampShadow(x + 32, y + 17);
    ctx.fillStyle = '#5d4037'; ctx.fillRect(x, y, 64, 34);
    ctx.fillStyle = '#8d6e63'; ctx.fillRect(x + 2, y + 2, 60, 30);
    // Legs
    ctx.fillStyle = '#4e342e';
    ctx.fillRect(x + 2, y + 30, 4, 4); ctx.fillRect(x + 58, y + 30, 4, 4);
    // Magazine
    ctx.fillStyle = '#e3f2fd'; ctx.fillRect(x + 7, y + 6, 14, 18);
    ctx.fillStyle = '#1976d2'; ctx.fillRect(x + 9, y + 8, 10, 6);
    // Remote
    ctx.fillStyle = '#212121'; ctx.fillRect(x + 32, y + 10, 12, 6);
    ctx.fillStyle = '#f44336'; ctx.fillRect(x + 34, y + 11, 2, 2);
    _clearFurnitureShadow();
}

function drawEndTable(x, y) {
    _setFurnitureLampShadow(x + 10, y + 10);
    // Small wooden side table
    ctx.fillStyle = '#5d4037'; ctx.fillRect(x, y + 6, 20, 14);
    ctx.fillStyle = '#6d4c41'; ctx.fillRect(x + 1, y + 7, 18, 12);
    // Legs
    ctx.fillStyle = '#4e342e';
    ctx.fillRect(x + 1, y + 18, 3, 3); ctx.fillRect(x + 16, y + 18, 3, 3);
    // Plant on top
    ctx.fillStyle = '#795548'; ctx.fillRect(x + 6, y + 2, 8, 5); // pot
    ctx.fillStyle = '#6d4c41'; ctx.fillRect(x + 7, y + 1, 6, 2); // pot rim
    // Leaves
    ctx.fillStyle = '#388e3c';
    ctx.fillRect(x + 5, y - 2, 4, 4);
    ctx.fillRect(x + 11, y - 2, 4, 4);
    ctx.fillStyle = '#43a047';
    ctx.fillRect(x + 7, y - 4, 6, 4);
    ctx.fillStyle = '#2e7d32';
    ctx.fillRect(x + 8, y - 1, 4, 3);
    _clearFurnitureShadow();
}

function drawTV(x, y) {
    _setFurnitureLampShadow(x + 25, y + 16);
    // TV frame
    ctx.fillStyle = '#212121'; ctx.fillRect(x, y, 50, 32);
    ctx.fillStyle = '#263238'; ctx.fillRect(x + 3, y + 3, 44, 26);
    // Check if any agent is watching THIS TV (within 60px of the TV's watch spot)
    var watchX = x, watchY = y + 50;
    var tvInUse = agents.some(function(a) {
        return a.idleAction === 'watch_tv' && Math.abs(a.x - watchX) < 60 && Math.abs(a.y - watchY) < 60;
    });
    var tvX = x + 5, tvY = y + 5, tvW = 40, tvH = 22;
    if (tvInUse) {
        // Animated channels — only when someone is watching
        var tvChannel = Math.floor(_weatherTick / 480) % 5;
        var tvStatic = (_weatherTick % 480) < 15;
        if (tvStatic) {
            for (var sy = 0; sy < tvH; sy += 2) {
                for (var sx = 0; sx < tvW; sx += 2) {
                    var bright = Math.floor(Math.random() * 200) + 55;
                    ctx.fillStyle = 'rgb(' + bright + ',' + bright + ',' + bright + ')';
                    ctx.fillRect(tvX + sx, tvY + sy, 2, 2);
                }
            }
        } else if (tvChannel === 0) {
            // Sports
            ctx.fillStyle = '#2e7d32'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#4caf50'; ctx.fillRect(tvX, tvY + 10, tvW, 2);
            ctx.fillStyle = '#fff'; ctx.fillRect(tvX + 19, tvY, 2, tvH);
            var ballX = tvX + 10 + Math.sin(_weatherTick * 0.06) * 12;
            ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(ballX, tvY + 11, 2, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#fff'; ctx.font = '3px Arial'; ctx.textAlign = 'center';
            ctx.fillText('3 - 2', tvX + 20, tvY + 5);
        } else if (tvChannel === 1) {
            // News
            ctx.fillStyle = '#1565c0'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#c62828'; ctx.fillRect(tvX, tvY + 15, tvW, 7);
            ctx.save();
            ctx.beginPath(); ctx.rect(tvX, tvY, tvW, tvH); ctx.clip();
            ctx.fillStyle = '#fff'; ctx.font = '3px Arial'; ctx.textAlign = 'left';
            var tickerOff = (_weatherTick * 0.4) % 80;
            ctx.fillText('BREAKING NEWS...', tvX + 40 - tickerOff, tvY + 20);
            ctx.restore();
            ctx.fillStyle = '#0d47a1'; ctx.fillRect(tvX + 14, tvY + 3, 12, 12);
            ctx.fillStyle = '#ffcc80'; ctx.beginPath(); ctx.arc(tvX + 20, tvY + 6, 3, 0, Math.PI * 2); ctx.fill();
        } else if (tvChannel === 2) {
            // Cooking show
            ctx.fillStyle = '#ff8f00'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#6d4c41'; ctx.fillRect(tvX + 5, tvY + 10, 30, 8);
            ctx.fillStyle = '#f44336'; ctx.fillRect(tvX + 10, tvY + 5, 6, 6);
            ctx.fillStyle = 'rgba(255,255,255,0.4)';
            ctx.fillRect(tvX + 12, tvY + 2 + Math.sin(_weatherTick * 0.1) * 1, 2, 3);
        } else if (tvChannel === 3) {
            // Cartoon
            ctx.fillStyle = '#e1f5fe'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#4caf50'; ctx.fillRect(tvX, tvY + 14, tvW, 8);
            ctx.fillStyle = '#ffd600'; ctx.beginPath(); ctx.arc(tvX + 33, tvY + 5, 4, 0, Math.PI * 2); ctx.fill();
            var bounce = Math.abs(Math.sin(_weatherTick * 0.08)) * 6;
            ctx.fillStyle = '#e91e63'; ctx.fillRect(tvX + 12, tvY + 8 - bounce, 6, 6);
            ctx.fillStyle = '#fff'; ctx.fillRect(tvX + 14, tvY + 9 - bounce, 1, 1); ctx.fillRect(tvX + 16, tvY + 9 - bounce, 1, 1);
        } else {
            // Movie — letterbox
            ctx.fillStyle = '#1a1a1a'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#000'; ctx.fillRect(tvX, tvY, tvW, 4); ctx.fillRect(tvX, tvY + 18, tvW, 4);
            ctx.fillStyle = '#37474f'; ctx.fillRect(tvX, tvY + 4, tvW, 14);
            ctx.fillStyle = 'rgba(255,255,200,0.3)'; ctx.beginPath(); ctx.arc(tvX + 30, tvY + 8, 4, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#1a1a1a'; ctx.fillRect(tvX + 10, tvY + 10, 8, 8);
        }
        // Screen glare
        ctx.fillStyle = 'rgba(255,255,255,0.05)'; ctx.fillRect(tvX, tvY, tvW, tvH / 2);
    } else {
        // Off — dark screen with faint power LED
        ctx.fillStyle = '#1a1a2e'; ctx.fillRect(tvX, tvY, tvW, tvH);
        ctx.fillStyle = 'rgba(255,255,255,0.02)'; ctx.fillRect(tvX, tvY, tvW, tvH / 2);
        // Power LED
        ctx.fillStyle = '#f44336'; ctx.fillRect(x + 44, y + 28, 2, 2);
    }
    // Stand
    ctx.fillStyle = '#37474f'; ctx.fillRect(x + 18, y + 30, 14, 3);
    ctx.fillRect(x + 12, y + 32, 26, 2);
    _clearFurnitureShadow();
}

// (old small bookshelf removed — using larger bookshelf below)

// --- KITCHEN COUNTER/CABINET ---
function drawFloorLamp(x, y) {
    // Standing floor lamp
    ctx.save();
    // Base
    ctx.fillStyle = '#37474f';
    ctx.beginPath(); ctx.ellipse(x, y + 2, 8, 3, 0, 0, Math.PI * 2); ctx.fill();
    // Pole
    ctx.strokeStyle = '#546e7a'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, y + 2); ctx.lineTo(x, y - 28); ctx.stroke();
    // Shade
    ctx.fillStyle = '#455a64';
    ctx.beginPath();
    ctx.moveTo(x - 8, y - 28);
    ctx.lineTo(x + 8, y - 28);
    ctx.lineTo(x + 5, y - 34);
    ctx.lineTo(x - 5, y - 34);
    ctx.closePath();
    ctx.fill();
    // Bulb (static, no hardcoded glow — lighting handled dynamically)
    ctx.fillStyle = '#e0e0e0';
    ctx.beginPath(); ctx.arc(x, y - 30, 2, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
}

function drawBranchSign(item) {
    // Neon-style branch name label. item.branchId links to a branch.
    var branchId = item.branchId || 'UNASSIGNED';
    var branch = getBranchById(branchId);
    var text = (branch.name || branchId).toUpperCase();
    var neonColor = branch.color || _NEON_COLORS[branch.theme] || '#ffffff';

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold 10px "Press Start 2P", monospace';

    // Solid text (no hardcoded glow — lighting handled dynamically)
    ctx.globalAlpha = 1;
    ctx.fillStyle = neonColor;
    ctx.fillText(text, item.x, item.y);

    ctx.restore();
}

function _showTextLabelEditor(item) {
    var existing = document.getElementById('text-label-editor');
    if (existing) existing.remove();

    var popup = document.createElement('div');
    popup.id = 'text-label-editor';
    popup.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:99999;background:#1a1a2e;border:2px solid #ffd700;border-radius:12px;padding:20px;min-width:280px;box-shadow:0 8px 40px rgba(0,0,0,0.6);font-family:Arial,sans-serif;color:#e0e0e0;';

    popup.innerHTML = '<div style="font-size:14px;font-weight:bold;color:#ffd700;margin-bottom:14px;">✏️ ' + (typeof i18n !== 'undefined' ? i18n.t('edit_text_label') : 'Edit Text Label') + '</div>' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('text_label') : 'Text') + '</label>' +
        '<input id="tl-text" type="text" value="' + (item.text || (typeof i18n !== 'undefined' ? i18n.t('label_default') : 'Label')).replace(/"/g, '&quot;') + '" style="width:100%;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:6px;color:#e0e0e0;font-size:14px;margin:4px 0 10px;">' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('text_color_label') : 'Text Color') + '</label>' +
        '<div style="display:flex;align-items:center;gap:8px;margin:4px 0 10px;">' +
        '<input id="tl-color" type="color" value="' + (item.labelColor || '#ffffff') + '" style="width:40px;height:32px;border:none;background:none;cursor:pointer;">' +
        '<span id="tl-color-hex" style="font-size:12px;color:#888;">' + (item.labelColor || '#ffffff') + '</span>' +
        '</div>' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('font_size_label') : 'Font Size') + '</label>' +
        '<div style="display:flex;align-items:center;gap:8px;margin:4px 0 12px;">' +
        '<input id="tl-size" type="range" min="8" max="32" value="' + (item.fontSize || 12) + '" style="flex:1;">' +
        '<span id="tl-size-val" style="font-size:12px;color:#888;min-width:28px;">' + (item.fontSize || 12) + 'px</span>' +
        '</div>' +
        '<div id="tl-preview" style="padding:10px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:6px;margin-bottom:12px;text-align:center;"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
        '<button id="tl-cancel" style="padding:6px 16px;background:#333;border:1px solid #555;border-radius:6px;color:#ccc;cursor:pointer;font-size:12px;">' + (typeof i18n !== 'undefined' ? i18n.t('cancel') : 'Cancel') + '</button>' +
        '<button id="tl-save" style="padding:6px 16px;background:#ffd700;border:none;border-radius:6px;color:#000;font-weight:bold;cursor:pointer;font-size:12px;">' + (typeof i18n !== 'undefined' ? i18n.t('save') : 'Save') + '</button>' +
        '</div>';

    document.body.appendChild(popup);

    function updatePreview() {
        var pv = document.getElementById('tl-preview');
        var text = document.getElementById('tl-text').value || 'Label';
        var color = document.getElementById('tl-color').value;
        var size = document.getElementById('tl-size').value;
        pv.innerHTML = '<span style="color:' + color + ';font-size:' + size + 'px;font-weight:bold;">' + text.replace(/</g, '&lt;') + '</span>';
    }

    document.getElementById('tl-color').addEventListener('input', function() {
        document.getElementById('tl-color-hex').textContent = this.value;
        updatePreview();
    });
    document.getElementById('tl-size').addEventListener('input', function() {
        document.getElementById('tl-size-val').textContent = this.value + 'px';
        updatePreview();
    });
    document.getElementById('tl-text').addEventListener('input', updatePreview);
    updatePreview();

    document.getElementById('tl-cancel').onclick = function() { popup.remove(); };
    document.getElementById('tl-save').onclick = function() {
        item.text = document.getElementById('tl-text').value || 'Label';
        item.labelColor = document.getElementById('tl-color').value;
        item.fontSize = parseInt(document.getElementById('tl-size').value) || 12;
        saveOfficeConfig();
        popup.remove();
    };

    var escHandler = function(e) { if (e.key === 'Escape') { popup.remove(); document.removeEventListener('keydown', escHandler); } };
    document.addEventListener('keydown', escHandler);
}


// --- INTERACTIVE WINDOW (weather + sun configurable) ---
function drawInteractiveWindow(item) {
    var wx = item.x, wy = item.y, ww = 36, wh = 44;
    var showWeather = item.weather !== false && _displayPrefs.showWeather !== false; // per-item + global pref
    var showSun = item.showSun || false;      // default false

    // Outer sill / ledge
    ctx.fillStyle = '#999'; ctx.fillRect(wx - 4, wy - 4, ww + 8, wh + 8);
    // Inner frame
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(wx - 2, wy - 2, ww + 4, wh + 4);
    // Glass — sky (time-of-day)
    ctx.fillStyle = _tod.sky; ctx.fillRect(wx, wy, ww, wh);
    ctx.fillStyle = _tod.upper; ctx.fillRect(wx, wy, ww, Math.floor(wh * 0.35));
    ctx.fillStyle = _tod.top; ctx.fillRect(wx, wy, ww, Math.floor(wh * 0.15));
    // Stars at night (twinkling)
    if (_tod.stars) {
        var _stars = [
            { x: 6, y: 8, s: 2 }, { x: 18, y: 4, s: 1 }, { x: 12, y: 18, s: 2 },
            { x: 28, y: 12, s: 1 }, { x: 24, y: 6, s: 1.5 }, { x: 8, y: 28, s: 1 },
            { x: 32, y: 20, s: 1 }, { x: 15, y: 32, s: 1.5 }, { x: 3, y: 22, s: 1 }
        ];
        for (var si = 0; si < _stars.length; si++) {
            var star = _stars[si];
            var twinkle = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(_weatherTick * 0.04 + si * 2.3));
            ctx.fillStyle = 'rgba(255,255,255,' + twinkle.toFixed(2) + ')';
            ctx.fillRect(wx + star.x, wy + star.y, star.s, star.s);
        }
        // Moon — only on windows with showSun enabled
        if (showSun) {
            ctx.fillStyle = 'rgba(255,255,220,0.8)';
            ctx.fillRect(wx + ww - 12, wy + 4, 6, 6);
            ctx.fillStyle = _tod.sky;
            ctx.fillRect(wx + ww - 10, wy + 3, 5, 5);
        }
    }
    // Clouds (skip at night)
    if (!_tod.stars) {
        ctx.fillStyle = _tod.cloud;
        ctx.fillRect(wx + 4, wy + 6, 8, 3);
        ctx.fillRect(wx + 6, wy + 4, 4, 2);
        ctx.fillRect(wx + ww - 14, wy + 10, 6, 2);
        ctx.fillRect(wx + ww - 12, wy + 8, 4, 2);
    }
    // Weather effects on glass
    if (showWeather) {
        drawWeatherOnWindow(wx, wy, ww, wh, showSun);
    }
    // Cross panes
    ctx.fillStyle = '#fff';
    ctx.fillRect(wx + Math.floor(ww / 2) - 1, wy, 3, wh);
    ctx.fillRect(wx, wy + Math.floor(wh / 2) - 1, ww, 3);
    ctx.fillStyle = '#ccc';
    ctx.fillRect(wx + Math.floor(ww/2) - 2, wy + Math.floor(wh/2) - 2, 5, 5);
    // Glass shine
    ctx.fillStyle = 'rgba(255,255,255,0.15)';
    ctx.fillRect(wx + 2, wy + 2, 5, 3);
    ctx.fillRect(wx + 3, wy + 4, 3, 2);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    var px = wx + Math.floor(ww/2) + 4, py = wy + Math.floor(wh/2) + 4;
    ctx.fillRect(px, py, 4, 3);
    // Bottom sill
    ctx.fillStyle = '#bbb';
    ctx.fillRect(wx - 3, wy + wh + 2, ww + 6, 3);
    ctx.fillStyle = '#ddd';
    ctx.fillRect(wx - 2, wy + wh + 2, ww + 4, 1);
    // Light projection on floor
    var lightTop = wy + wh + 5;
    var lightBottom = wy + wh + 120;
    var lightGrad = ctx.createLinearGradient(0, lightTop, 0, lightBottom);
    lightGrad.addColorStop(0, _tod.glow);
    lightGrad.addColorStop(0.4, _tod.glow.replace(/[\d.]+\)$/, function(m) { return (parseFloat(m) * 0.5).toFixed(2) + ')'; }));
    lightGrad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = lightGrad;
    ctx.beginPath();
    ctx.moveTo(wx - 2, lightTop);
    ctx.lineTo(wx + ww + 2, lightTop);
    ctx.lineTo(wx + ww + 40, lightBottom);
    ctx.lineTo(wx - 40, lightBottom);
    ctx.closePath();
    ctx.fill();
    // Edit mode indicator — small weather/sun badges
    if (editMode) {
        ctx.fillStyle = 'rgba(0,0,0,0.5)';
        ctx.fillRect(wx - 4, wy + wh + 6, ww + 8, 10);
        ctx.font = '7px Arial';
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        var badges = [];
        if (showWeather) badges.push('🌧️');
        if (showSun) badges.push('☀️');
        if (badges.length === 0) badges.push('—');
        ctx.fillText(badges.join(' '), wx + ww/2, wy + wh + 13);
    }
}

function _getConnectedFloorWindowRun(item) {
    var b = FURNITURE_BOUNDS['floorWindow'] || { w: TILE * 2, h: TILE * 2 };
    var items = (officeConfig.furniture || []).filter(function(f) {
        return f.type === 'floorWindow' && Math.abs(f.y - item.y) < 1;
    }).sort(function(a, b2) { return a.x - b2.x; });
    var left = item.x;
    var right = item.x + b.w;
    var changed = true;
    while (changed) {
        changed = false;
        for (var i = 0; i < items.length; i++) {
            var f = items[i];
            if (Math.abs(f.x + b.w - left) < 1) {
                left = f.x;
                changed = true;
            }
            if (Math.abs(f.x - right) < 1) {
                right = f.x + b.w;
                changed = true;
            }
        }
    }
    return {
        x: left,
        y: item.y,
        w: right - left,
        h: b.h,
        hasLeft: left < item.x,
        hasRight: right > item.x + b.w
    };
}

function _drawFloorWindowSunMoon(sceneX, sceneY, sceneW, sceneH) {
    var cx = sceneX + sceneW - 18;
    var cy = sceneY + 14;
    if (_tod.stars) {
        ctx.fillStyle = 'rgba(255,255,220,0.86)';
        ctx.beginPath();
        ctx.arc(cx, cy, 7, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = _tod.sky;
        ctx.beginPath();
        ctx.arc(cx + 4, cy - 2, 7, 0, Math.PI * 2);
        ctx.fill();
    } else {
        var pulse = 7 + Math.sin(_weatherTick * 0.025) * 1.5;
        var grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 24);
        grad.addColorStop(0, 'rgba(255,245,157,0.9)');
        grad.addColorStop(0.45, 'rgba(255,213,79,0.45)');
        grad.addColorStop(1, 'rgba(255,213,79,0)');
        ctx.fillStyle = grad;
        ctx.fillRect(cx - 24, cy - 24, 48, 48);
        ctx.fillStyle = 'rgba(255,224,90,0.95)';
        ctx.beginPath();
        ctx.arc(cx, cy, pulse, 0, Math.PI * 2);
        ctx.fill();
    }
}

function drawFloorWindow(item) {
    var run = _getConnectedFloorWindowRun(item);
    if (run.hasLeft) return;

    var x = run.x, y = run.y;
    var bw = run.w, bh = run.h;
    var edge = 3;
    var wx = x + edge, wy = y + edge;
    var ww = bw - edge * 2, wh = bh - edge * 2 - 4;
    var sceneX = run.x + edge;
    var sceneY = run.y + edge;
    var sceneW = run.w - edge * 2;
    var sceneH = run.h - edge * 2 - 4;
    var showWeather = item.weather !== false && _displayPrefs.showWeather !== false;
    var showSun = item.showSun !== false;

    ctx.save();
    _setFurnitureLampShadow(x + bw / 2, y + bh - 10);

    // Floor glow lands behind the glass so the object reads as a passive floor window.
    var lightTop = y + bh - 12;
    var lightBottom = Math.min(H, y + bh + 110);
    var lightGrad = ctx.createLinearGradient(0, lightTop, 0, lightBottom);
    lightGrad.addColorStop(0, _tod.glow);
    lightGrad.addColorStop(0.55, _tod.glow.replace(/[\d.]+\)$/, function(m) { return (parseFloat(m) * 0.35).toFixed(2) + ')'; }));
    lightGrad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = lightGrad;
    ctx.beginPath();
    ctx.moveTo(x + 6, lightTop);
    ctx.lineTo(x + bw - 6, lightTop);
    ctx.lineTo(x + bw + 20, lightBottom);
    ctx.lineTo(x - 20, lightBottom);
    ctx.closePath();
    ctx.fill();

    // One continuous pane of glass with only a thin polished edge.
    ctx.fillStyle = 'rgba(214,232,242,0.18)';
    ctx.fillRect(wx - 1, wy - 1, ww + 2, wh + 2);
    ctx.fillStyle = 'rgba(255,255,255,0.42)';
    ctx.fillRect(wx - 1, wy - 1, ww + 2, 1);
    ctx.fillRect(wx - 1, wy - 1, 1, wh + 2);
    ctx.fillStyle = 'rgba(55,72,84,0.18)';
    ctx.fillRect(wx + ww, wy, 1, wh + 1);
    ctx.fillRect(wx, wy + wh, ww + 1, 1);

    // Time-of-day sky base.
    ctx.save();
    ctx.beginPath();
    ctx.rect(wx, wy, ww, wh);
    ctx.clip();
    ctx.fillStyle = _tod.sky; ctx.fillRect(sceneX, sceneY, sceneW, sceneH);
    ctx.fillStyle = _tod.upper; ctx.fillRect(sceneX, sceneY, sceneW, Math.floor(sceneH * 0.38));
    ctx.fillStyle = _tod.top; ctx.fillRect(sceneX, sceneY, sceneW, Math.floor(sceneH * 0.18));
    ctx.fillStyle = 'rgba(46,79,92,0.18)';
    ctx.fillRect(sceneX, sceneY + Math.floor(sceneH * 0.62), sceneW, Math.floor(sceneH * 0.16));
    ctx.fillStyle = 'rgba(26,71,64,0.20)';
    ctx.fillRect(sceneX, sceneY + Math.floor(sceneH * 0.75), sceneW, Math.floor(sceneH * 0.25));

    if (_tod.stars) {
        for (var si = 0; si < 18; si++) {
            var sx = sceneX + 8 + (si * 23) % Math.max(16, sceneW - 16);
            var sy = sceneY + 8 + (si * 17) % Math.max(20, sceneH - 28);
            var twinkle = 0.25 + 0.65 * (0.5 + 0.5 * Math.sin(_weatherTick * 0.035 + si * 1.7));
            ctx.fillStyle = 'rgba(255,255,255,' + twinkle.toFixed(2) + ')';
            ctx.fillRect(sx, sy, si % 3 === 0 ? 2 : 1, si % 4 === 0 ? 2 : 1);
        }
    } else {
        ctx.fillStyle = _tod.cloud;
        ctx.fillRect(sceneX + 14, sceneY + 20, 24, 7);
        ctx.fillRect(sceneX + 22, sceneY + 15, 12, 7);
        ctx.fillRect(sceneX + sceneW - 46, sceneY + 31, 30, 7);
        ctx.fillRect(sceneX + sceneW - 38, sceneY + 25, 14, 7);
    }

    if (showSun) {
        _drawFloorWindowSunMoon(sceneX, sceneY, sceneW, sceneH);
    }

    if (showWeather) {
        var floorWindowWeatherTick = _weatherTick;
        drawWeatherOnWindow(sceneX, sceneY, sceneW, sceneH, showSun);
        _weatherTick = floorWindowWeatherTick;
    }
    ctx.restore();

    // Restrained glass reflections, no window frame or pane dividers.
    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.fillRect(wx + 7, wy + 8, 18, 3);
    ctx.fillRect(wx + 10, wy + 13, 10, 2);
    ctx.fillStyle = 'rgba(255,255,255,0.10)';
    ctx.fillRect(wx + ww - 22, wy + wh - 24, 14, 4);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.beginPath();
    ctx.moveTo(wx + 45, wy + 5);
    ctx.lineTo(wx + 56, wy + 5);
    ctx.lineTo(wx + 32, wy + wh - 9);
    ctx.lineTo(wx + 23, wy + wh - 9);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = 'rgba(96,113,126,0.32)';
    ctx.fillRect(wx - 2, y + bh - 9, ww + 4, 4);

    _clearFurnitureShadow();
    ctx.restore();
}

function _showInteractiveWindowEditor(item) {
    var existing = document.getElementById('iw-editor');
    if (existing) existing.remove();

    var popup = document.createElement('div');
    popup.id = 'iw-editor';
    popup.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:99999;background:#1a1a2e;border:2px solid #ffd700;border-radius:12px;padding:20px;min-width:300px;box-shadow:0 8px 40px rgba(0,0,0,0.6);font-family:Arial,sans-serif;color:#e0e0e0;';

    var weatherChecked = item.weather !== false ? 'checked' : '';
    var sunChecked = item.showSun ? 'checked' : '';
    var titleKey = item.type === 'floorWindow' ? 'floor_window_settings' : 'weather_window_settings';

    popup.innerHTML = '<div style="font-size:14px;font-weight:bold;color:#ffd700;margin-bottom:14px;">🌤️ ' + (typeof i18n !== 'undefined' ? i18n.t(titleKey) : (item.type === 'floorWindow' ? 'Floor Window Settings' : 'Weather Window Settings')) + '</div>' +
        '<div style="margin-bottom:16px;">' +
        '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:8px;margin-bottom:8px;">' +
        '<input id="iw-weather" type="checkbox" ' + weatherChecked + ' style="width:18px;height:18px;cursor:pointer;">' +
        '<div><div style="font-size:13px;color:#e0e0e0;">🌧️ ' + (typeof i18n !== 'undefined' ? i18n.t('weather_effects_label') : 'Show Weather Effects') + '</div>' +
        '<div style="font-size:11px;color:#888;margin-top:2px;">' + (typeof i18n !== 'undefined' ? i18n.t('weather_effects_desc') : 'Rain, snow, clouds, fog animations on the glass') + '</div></div>' +
        '</label>' +
        '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:8px;">' +
        '<input id="iw-sun" type="checkbox" ' + sunChecked + ' style="width:18px;height:18px;cursor:pointer;">' +
        '<div><div style="font-size:13px;color:#e0e0e0;">☀️ ' + (typeof i18n !== 'undefined' ? i18n.t('sun_moon_label') : 'Show Sun / Moon') + '</div>' +
        '<div style="font-size:11px;color:#888;margin-top:2px;">' + (typeof i18n !== 'undefined' ? i18n.t('sun_moon_desc') : 'Animated sun during the day, crescent moon at night') + '</div></div>' +
        '</label>' +
        '</div>' +
        '<div id="iw-preview" style="padding:12px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:8px;margin-bottom:14px;text-align:center;font-size:12px;color:#aaa;"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
        '<button id="iw-cancel" style="padding:6px 16px;background:#333;border:1px solid #555;border-radius:6px;color:#ccc;cursor:pointer;font-size:12px;">' + (typeof i18n !== 'undefined' ? i18n.t('cancel') : 'Cancel') + '</button>' +
        '<button id="iw-save" style="padding:6px 16px;background:#ffd700;border:none;border-radius:6px;color:#000;font-weight:bold;cursor:pointer;font-size:12px;">' + (typeof i18n !== 'undefined' ? i18n.t('save') : 'Save') + '</button>' +
        '</div>';

    document.body.appendChild(popup);

    function updatePreview() {
        var pv = document.getElementById('iw-preview');
        var w = document.getElementById('iw-weather').checked;
        var s = document.getElementById('iw-sun').checked;
        var desc = [];
        if (w) desc.push('🌧️ ' + (typeof i18n !== 'undefined' ? i18n.t('weather_effects_on') : 'Weather effects ON'));
        else desc.push(typeof i18n !== 'undefined' ? i18n.t('weather_effects_off') : 'Weather effects OFF');
        if (s) desc.push('☀️ ' + (typeof i18n !== 'undefined' ? i18n.t('sun_moon_on') : 'Sun/Moon ON'));
        else desc.push(typeof i18n !== 'undefined' ? i18n.t('sun_moon_off') : 'Sun/Moon OFF');
        pv.innerHTML = desc.join(' &nbsp;|&nbsp; ');
    }

    document.getElementById('iw-weather').addEventListener('change', updatePreview);
    document.getElementById('iw-sun').addEventListener('change', updatePreview);
    updatePreview();

    document.getElementById('iw-cancel').onclick = function() { popup.remove(); };
    document.getElementById('iw-save').onclick = function() {
        item.weather = document.getElementById('iw-weather').checked;
        item.showSun = document.getElementById('iw-sun').checked;
        saveOfficeConfig();
        popup.remove();
    };

    var escHandler = function(e) { if (e.key === 'Escape') { popup.remove(); document.removeEventListener('keydown', escHandler); } };
    document.addEventListener('keydown', escHandler);
}

function drawTextLabel(item) {
    var text = item.text || 'Label';
    var color = item.labelColor || '#ffffff';
    var fontSize = item.fontSize || 12;
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold ' + fontSize + 'px "Press Start 2P", monospace';
    // Shadow for readability
    ctx.fillStyle = 'rgba(0,0,0,0.4)';
    ctx.fillText(text, item.x + 1, item.y + 1);
    // Main text
    ctx.fillStyle = color;
    ctx.fillText(text, item.x, item.y);
    ctx.restore();
}

function drawKitchenCounter(x, y) {
    _setFurnitureLampShadow(x + 36, y + 20);
    // Counter shadow
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x + 2, y + 32, 72, 8);
    // Counter body
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x, y, 72, 34);
    ctx.fillStyle = '#f5f5f5'; ctx.fillRect(x + 2, y + 2, 68, 30);
    // Counter top surface
    ctx.fillStyle = '#fafafa'; ctx.fillRect(x, y, 72, 4);
    // Cabinet doors
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 4, y + 10, 28, 18); ctx.fillRect(x + 36, y + 10, 28, 18);
    // Handles
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 16, y + 17, 4, 3); ctx.fillRect(x + 48, y + 17, 4, 3);
    _clearFurnitureShadow();
}

function drawCoffeeMakerStandalone(x, y) {
    // Counter base
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x, y + 10, 24, 12);
    ctx.fillStyle = '#f5f5f5'; ctx.fillRect(x + 1, y + 11, 22, 10);
    // Machine body
    ctx.fillStyle = '#212121'; ctx.fillRect(x + 2, y, 20, 12);
    ctx.fillStyle = '#333';    ctx.fillRect(x + 4, y + 2, 16, 8);
    // Water tank (blue tint)
    ctx.fillStyle = 'rgba(3,169,244,0.5)'; ctx.fillRect(x + 15, y + 2, 4, 8);
    // Buttons
    ctx.fillStyle = '#4caf50'; ctx.fillRect(x + 5, y + 3, 3, 2);
    ctx.fillStyle = '#f44336'; ctx.fillRect(x + 5, y + 7, 3, 2);
    // Drip tray
    ctx.fillStyle = '#424242'; ctx.fillRect(x + 5, y + 18, 10, 3);
    // Cup
    ctx.fillStyle = '#fff'; ctx.fillRect(x + 7, y + 16, 5, 5);
}

function drawMicrowaveStandalone(x, y) {
    var micInUse = agents.some(function(a) {
        return a.idleAction === 'make_food' && a.foodSource === 'microwave' && !a.isSitting && Math.abs(a.x - x) < 55 && Math.abs(a.y - y) < 70;
    });
    ctx.fillStyle = '#455a64'; ctx.fillRect(x, y, 30, 24);
    ctx.fillStyle = '#37474f'; ctx.fillRect(x + 2, y + 2, 26, 20);
    // Door window
    ctx.fillStyle = '#263238'; ctx.fillRect(x + 3, y + 3, 17, 17);
    if (micInUse) {
        var micGlow = 0.15 + Math.sin(_weatherTick * 0.15) * 0.1;
        ctx.fillStyle = 'rgba(255,200,50,' + micGlow + ')';
        ctx.fillRect(x + 4, y + 4, 15, 15);
        var plateAngle = _weatherTick * 0.08;
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.beginPath(); ctx.arc(x + 11, y + 12 + Math.sin(plateAngle) * 2, 1, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(x + 11 + Math.cos(plateAngle) * 3, y + 12, 1, 0, Math.PI * 2); ctx.fill();
    } else {
        ctx.fillStyle = 'rgba(100,200,255,0.15)'; ctx.fillRect(x + 4, y + 4, 15, 15);
    }
    // Handle
    ctx.fillStyle = '#90a4ae'; ctx.fillRect(x + 21, y + 7, 2, 10);
    // Control panel
    ctx.fillStyle = '#546e7a'; ctx.fillRect(x + 24, y + 3, 4, 17);
    ctx.fillStyle = micInUse ? '#76ff03' : '#4caf50'; ctx.fillRect(x + 25, y + 5, 2, 2);
    ctx.fillStyle = '#f44336'; ctx.fillRect(x + 25, y + 9, 2, 2);
    ctx.fillStyle = '#78909c'; ctx.fillRect(x + 25, y + 13, 2, 2);
    // Display
    ctx.fillStyle = micInUse ? '#1b5e20' : '#0a3010'; ctx.fillRect(x + 4, y + 3, 8, 4);
    ctx.fillStyle = micInUse ? '#76ff03' : '#4caf50'; ctx.font = '3px Arial'; ctx.textAlign = 'left';
    if (micInUse) {
        var secs = Math.floor(_weatherTick * 0.05) % 60;
        ctx.fillText((secs < 10 ? '0:0' : '0:') + secs, x + 5, y + 6);
        ctx.fillStyle = 'rgba(255,200,50,0.08)';
        var humOff = Math.sin(_weatherTick * 0.3) * 0.5;
        ctx.fillRect(x + humOff, y - 1, 30, 1);
    } else {
        ctx.fillText('0:00', x + 5, y + 6);
    }
}

function drawToasterStandalone(x, y) {
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x, y + 4, 18, 12);
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 1, y + 5, 16, 10);
    // Rounded top
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 1, y + 2, 16, 4);
    // Bread slots
    ctx.fillStyle = '#424242'; ctx.fillRect(x + 3, y + 2, 4, 3);
    ctx.fillRect(x + 10, y + 2, 4, 3);
    // Bread peeking
    ctx.fillStyle = '#d4a056'; ctx.fillRect(x + 3, y, 4, 3);
    ctx.fillRect(x + 10, y, 4, 3);
    // Lever
    ctx.fillStyle = '#78909c'; ctx.fillRect(x + 16, y + 8, 2, 5);
    ctx.fillStyle = '#546e7a'; ctx.fillRect(x + 15, y + 8, 4, 2);
    // Front label line
    ctx.fillStyle = '#9e9e9e'; ctx.fillRect(x + 5, y + 13, 8, 1);
}

function drawLoungeArea(lx, ly) {
    _setFurnitureLampShadow(lx + 80, ly + 50);
    // Couch shadow
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.fillRect(lx + 2, ly + 4, 32, 102);
    ctx.fillRect(lx + 2, ly + 74, 142, 32);
    // L-shaped couch
    ctx.fillStyle = '#3f51b5'; 
    ctx.fillRect(lx, ly, 30, 100); ctx.fillRect(lx, ly + 70, 140, 30);
    // Couch cushions
    ctx.fillStyle = '#5c6bc0';
    ctx.fillRect(lx + 3, ly + 5, 24, 22); ctx.fillRect(lx + 3, ly + 32, 24, 22);
    ctx.fillRect(lx + 35, ly + 73, 26, 24); ctx.fillRect(lx + 65, ly + 73, 26, 24); ctx.fillRect(lx + 95, ly + 73, 26, 24);
    // Pillows
    ctx.fillStyle = '#ffb74d'; ctx.fillRect(lx + 5, ly + 8, 10, 8);
    ctx.fillStyle = '#ef5350'; ctx.fillRect(lx + 100, ly + 76, 10, 8);
    // Coffee table
    ctx.fillStyle = '#5d4037'; ctx.fillRect(lx + 48, ly + 18, 64, 34);
    ctx.fillStyle = '#8d6e63'; ctx.fillRect(lx + 50, ly + 20, 60, 30);
    // Table legs
    ctx.fillStyle = '#4e342e';
    ctx.fillRect(lx + 50, ly + 48, 4, 4); ctx.fillRect(lx + 106, ly + 48, 4, 4);
    // Magazine on table
    ctx.fillStyle = '#e3f2fd'; ctx.fillRect(lx + 55, ly + 24, 14, 18);
    ctx.fillStyle = '#1976d2'; ctx.fillRect(lx + 57, ly + 26, 10, 6);
    // Remote control
    ctx.fillStyle = '#212121'; ctx.fillRect(lx + 80, ly + 28, 12, 6);
    ctx.fillStyle = '#f44336'; ctx.fillRect(lx + 82, ly + 29, 2, 2);
    // TV on wall
    ctx.fillStyle = '#212121'; ctx.fillRect(lx + 130, ly - 5, 50, 32);
    ctx.fillStyle = '#263238'; ctx.fillRect(lx + 133, ly - 2, 44, 26);
    // TV screen — animated when someone is watching
    var tvInUse = agents.some(function(a) { return a.idleAction === 'watch_tv'; });
    var tvX = lx + 135, tvY = ly, tvW = 40, tvH = 22;
    if (tvInUse) {
        var tvChannel = Math.floor(_weatherTick / 480) % 5; // switch channel every ~8s
        var tvStatic = (_weatherTick % 480) < 15; // brief static on channel switch
        if (tvStatic) {
            // Static noise
            for (var sy = 0; sy < tvH; sy += 2) {
                for (var sx = 0; sx < tvW; sx += 2) {
                    var bright = Math.floor(Math.random() * 200) + 55;
                    ctx.fillStyle = 'rgb(' + bright + ',' + bright + ',' + bright + ')';
                    ctx.fillRect(tvX + sx, tvY + sy, 2, 2);
                }
            }
        } else if (tvChannel === 0) {
            // Sports — green field with moving dot
            ctx.fillStyle = '#2e7d32'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#4caf50'; ctx.fillRect(tvX, tvY + 10, tvW, 2);
            ctx.fillStyle = '#fff'; ctx.fillRect(tvX + 19, tvY, 2, tvH);
            // Ball
            var ballX = tvX + 10 + Math.sin(_weatherTick * 0.06) * 12;
            ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(ballX, tvY + 11, 2, 0, Math.PI * 2); ctx.fill();
            // Score
            ctx.fillStyle = '#fff'; ctx.font = '3px Arial'; ctx.textAlign = 'center';
            ctx.fillText('3 - 2', tvX + 20, tvY + 5);
        } else if (tvChannel === 1) {
            // News — blue bg with text bars
            ctx.fillStyle = '#1565c0'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#c62828'; ctx.fillRect(tvX, tvY + 15, tvW, 7);
            // Ticker text clipped to TV screen
            ctx.save();
            ctx.beginPath(); ctx.rect(tvX, tvY, tvW, tvH); ctx.clip();
            ctx.fillStyle = '#fff'; ctx.font = '3px Arial'; ctx.textAlign = 'left';
            var tickerOff = (_weatherTick * 0.4) % 80;
            ctx.fillText('BREAKING NEWS...', tvX + 40 - tickerOff, tvY + 20);
            ctx.restore();
            // Anchor silhouette
            ctx.fillStyle = '#0d47a1'; ctx.fillRect(tvX + 14, tvY + 3, 12, 12);
            ctx.fillStyle = '#ffcc80'; ctx.beginPath(); ctx.arc(tvX + 20, tvY + 6, 3, 0, Math.PI * 2); ctx.fill();
        } else if (tvChannel === 2) {
            // Cooking show — warm colors
            ctx.fillStyle = '#ff8f00'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#6d4c41'; ctx.fillRect(tvX + 5, tvY + 10, 30, 8); // counter
            ctx.fillStyle = '#f44336'; ctx.fillRect(tvX + 10, tvY + 5, 6, 6); // pot
            // Steam
            ctx.fillStyle = 'rgba(255,255,255,0.4)';
            ctx.fillRect(tvX + 12, tvY + 2 + Math.sin(_weatherTick * 0.1) * 1, 2, 3);
        } else if (tvChannel === 3) {
            // Cartoon — bright colors, bouncing shapes
            ctx.fillStyle = '#e1f5fe'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#4caf50'; ctx.fillRect(tvX, tvY + 14, tvW, 8); // grass
            // Sun
            ctx.fillStyle = '#ffd600'; ctx.beginPath(); ctx.arc(tvX + 33, tvY + 5, 4, 0, Math.PI * 2); ctx.fill();
            // Bouncing character
            var bounce = Math.abs(Math.sin(_weatherTick * 0.08)) * 6;
            ctx.fillStyle = '#e91e63'; ctx.fillRect(tvX + 12, tvY + 8 - bounce, 6, 6);
            ctx.fillStyle = '#fff'; ctx.fillRect(tvX + 14, tvY + 9 - bounce, 1, 1); ctx.fillRect(tvX + 16, tvY + 9 - bounce, 1, 1);
        } else {
            // Movie — dark with letterbox
            ctx.fillStyle = '#1a1a1a'; ctx.fillRect(tvX, tvY, tvW, tvH);
            ctx.fillStyle = '#000'; ctx.fillRect(tvX, tvY, tvW, 4); ctx.fillRect(tvX, tvY + 18, tvW, 4);
            // Scene: moon + silhouette
            ctx.fillStyle = '#37474f'; ctx.fillRect(tvX, tvY + 4, tvW, 14);
            ctx.fillStyle = 'rgba(255,255,200,0.3)'; ctx.beginPath(); ctx.arc(tvX + 30, tvY + 8, 4, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#1a1a1a'; ctx.fillRect(tvX + 10, tvY + 10, 8, 8);
        }
    } else {
        // Standby — static blue screen
        ctx.fillStyle = '#4fc3f7'; ctx.fillRect(tvX, tvY, tvW, tvH);
        ctx.fillStyle = '#81d4fa'; ctx.fillRect(tvX + 3, tvY + 3, 15, 8);
        ctx.fillStyle = '#b3e5fc'; ctx.fillRect(tvX + 20, tvY + 3, 18, 2); ctx.fillRect(tvX + 20, tvY + 7, 12, 2);
    }
    // Label
    // Dart board on wall
    drawDartBoard(lx + 210, ly - 8);
    ctx.fillStyle = 'rgba(0,0,0,0.25)'; ctx.font = '8px "Press Start 2P"'; ctx.textAlign = 'center';
    _clearFurnitureShadow();
    ctx.fillText('LOUNGE', lx + 90, ly - 20);
    drawBookshelf(lx - 50, ly);
}

function drawDartBoard(x, y) {
    // Tripod legs
    ctx.strokeStyle = '#616161'; ctx.lineWidth = 2;
    // Left leg
    ctx.beginPath(); ctx.moveTo(x - 6, y + 16); ctx.lineTo(x - 18, y + 50); ctx.stroke();
    // Right leg
    ctx.beginPath(); ctx.moveTo(x + 6, y + 16); ctx.lineTo(x + 18, y + 50); ctx.stroke();
    // Center/back leg
    ctx.beginPath(); ctx.moveTo(x, y + 16); ctx.lineTo(x, y + 48); ctx.stroke();
    // Leg feet (small caps)
    ctx.fillStyle = '#424242';
    ctx.fillRect(x - 20, y + 48, 5, 3);
    ctx.fillRect(x + 16, y + 48, 5, 3);
    ctx.fillRect(x - 2, y + 46, 4, 3);
    // Backboard
    ctx.fillStyle = '#5d4037'; ctx.fillRect(x - 16, y - 16, 32, 32);
    ctx.fillStyle = '#795548'; ctx.fillRect(x - 14, y - 14, 28, 28);
    // Board circle (concentric rings)
    ctx.beginPath(); ctx.arc(x, y, 13, 0, Math.PI * 2);
    ctx.fillStyle = '#1a1a1a'; ctx.fill();
    // Outer ring (green/red alternating wedges via simple rects)
    ctx.fillStyle = '#c62828'; ctx.fillRect(x - 12, y - 3, 24, 6);
    ctx.fillStyle = '#2e7d32'; ctx.fillRect(x - 3, y - 12, 6, 24);
    // Middle ring
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2);
    ctx.fillStyle = '#e8e0d4'; ctx.fill();
    ctx.fillStyle = '#c62828'; ctx.fillRect(x - 7, y - 2, 14, 4);
    ctx.fillStyle = '#2e7d32'; ctx.fillRect(x - 2, y - 7, 4, 14);
    // Inner bull
    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#2e7d32'; ctx.fill();
    // Bullseye
    ctx.beginPath(); ctx.arc(x, y, 1.5, 0, Math.PI * 2);
    ctx.fillStyle = '#c62828'; ctx.fill();
    // Wire frame lines
    ctx.strokeStyle = 'rgba(200,200,200,0.4)'; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(x - 13, y); ctx.lineTo(x + 13, y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, y - 13); ctx.lineTo(x, y + 13); ctx.stroke();
    // Draw stuck darts from active games
    for (var di = 0; di < dartStuckDarts.length; di++) {
        var d = dartStuckDarts[di];
        ctx.fillStyle = d.color;
        ctx.fillRect(x + d.ox - 1, y + d.oy - 1, 3, 3); // dart tip
        ctx.fillStyle = d.flightColor;
        ctx.fillRect(x + d.ox - 1, y + d.oy - 4, 3, 3); // flight
    }
}

// --- ENG LOUNGE (under Caltran sign) ---
function drawEngLounge(x, y) {
    _setFurnitureLampShadow(x + 80, y + 20);
    // Couch shadow
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x + 2, y + 4, 162, 38);
    // Black leather couch (horizontal, seats 4)
    ctx.fillStyle = '#1a1a1a'; ctx.fillRect(x, y, 160, 36);
    // Back cushion
    ctx.fillStyle = '#2a2a2a'; ctx.fillRect(x + 2, y, 156, 12);
    // Seat cushions (4)
    ctx.fillStyle = '#333';
    ctx.fillRect(x + 4, y + 14, 34, 18);
    ctx.fillRect(x + 42, y + 14, 34, 18);
    ctx.fillRect(x + 80, y + 14, 34, 18);
    ctx.fillRect(x + 118, y + 14, 34, 18);
    // Cushion seams
    ctx.fillStyle = '#222';
    ctx.fillRect(x + 40, y + 14, 2, 18);
    ctx.fillRect(x + 78, y + 14, 2, 18);
    ctx.fillRect(x + 116, y + 14, 2, 18);
    // Leather shine highlights
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(x + 8, y + 16, 26, 4);
    ctx.fillRect(x + 46, y + 16, 26, 4);
    ctx.fillRect(x + 84, y + 16, 26, 4);
    ctx.fillRect(x + 122, y + 16, 26, 4);
    // Armrests
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(x - 4, y + 2, 6, 32);
    ctx.fillRect(x + 158, y + 2, 6, 32);
    ctx.fillStyle = '#2a2a2a';
    ctx.fillRect(x - 3, y + 3, 4, 8);
    ctx.fillRect(x + 159, y + 3, 4, 8);

    _clearFurnitureShadow();
}

// --- PING PONG TABLE ---
var PONG_TABLE = { x: 190, y: 105, w: 80, h: 48 };
function _updatePongTablePos() {
    if (!PONG_TABLE || !officeConfig || !officeConfig.furniture) return;
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        if (officeConfig.furniture[i].type === 'pingPongTable') {
            PONG_TABLE.x = officeConfig.furniture[i].x;
            PONG_TABLE.y = officeConfig.furniture[i].y;
            return;
        }
    }
}
var pongGames = [];

function drawPingPongTable(x, y) {
    _setFurnitureLampShadow(x, y);
    // Table shadow
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x - 38, y - 20, 80, 52);
    // Table surface (dark green)
    ctx.fillStyle = '#1b5e20'; ctx.fillRect(x - 40, y - 24, 80, 48);
    ctx.fillStyle = '#2e7d32'; ctx.fillRect(x - 38, y - 22, 76, 44);
    // White border lines
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1;
    ctx.strokeRect(x - 37, y - 21, 74, 42);
    // Center net
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x - 1, y - 22, 2, 44);
    // Net posts
    ctx.fillStyle = '#9e9e9e'; ctx.fillRect(x - 2, y - 24, 4, 3);
    ctx.fillStyle = '#9e9e9e'; ctx.fillRect(x - 2, y + 20, 4, 3);
    // Net mesh (dashed look)
    ctx.fillStyle = 'rgba(200,200,200,0.5)';
    for (var ny = -20; ny < 20; ny += 4) {
        ctx.fillRect(x - 1, y + ny, 2, 2);
    }
    // Table legs
    ctx.fillStyle = '#5d4037';
    ctx.fillRect(x - 38, y + 22, 4, 8);
    ctx.fillRect(x + 34, y + 22, 4, 8);
    ctx.fillRect(x - 38, y - 24, 4, 8);
    ctx.fillRect(x + 34, y - 24, 4, 8);
    // Center line
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.fillRect(x - 37, y - 1, 74, 1);
    _clearFurnitureShadow();
}

function startPongGame(a1, a2) {
    var g = {
        p1: a1, p2: a2,
        ballX: 0, ballY: 0, ballVX: 1.5, ballVY: 0.8,
        p1Score: 0, p2Score: 0,
        p1Y: 0, p2Y: 0,
        phase: 'walking', // walking → playing → result
        timer: 0, maxRounds: 5
    };
    a1.idleAction = 'pong'; a1.interactTimer = 0; a1.idleReturnTimer = 0;
    a2.idleAction = 'pong'; a2.interactTimer = 0; a2.idleReturnTimer = 0;
    // Walk to table sides
    a1.targetX = PONG_TABLE.x - 50; a1.targetY = PONG_TABLE.y;
    a2.targetX = PONG_TABLE.x + 50; a2.targetY = PONG_TABLE.y;
    pongGames.push(g);
}

function maybeStartPong(agent) {
    if (agent.idleAction === 'pong' || pongGames.length >= 1) return;
    // Agent waiting at table — look for a partner already there
    if (agent.idleAction === 'pong_wait') {
        // Check if arrived at table first
        var distToTable = Math.abs(agent.x - PONG_TABLE.x) + Math.abs(agent.y - PONG_TABLE.y);
        if (distToTable > 80) return; // still walking
        for (var i = 0; i < agents.length; i++) {
            var other = agents[i];
            if (other.id === agent.id) continue;
            if (other.idleAction === 'pong_wait') {
                var otherDist = Math.abs(other.x - PONG_TABLE.x) + Math.abs(other.y - PONG_TABLE.y);
                if (otherDist < 80) { startPongGame(agent, other); return; }
            }
        }
        // Active recruitment — pull ONE random idle agent to come play (only if < 2 waiting)
        var _waitCount = agents.filter(function(a) { return a.idleAction === 'pong_wait'; }).length;
        if (_waitCount < 2 && Math.random() < 0.02) {
            var candidates = [];
            for (var j = 0; j < agents.length; j++) {
                var c = agents[j];
                if (c.id === agent.id) continue;
                if (c.state === 'idle' && !c.idleAction && !c.meetingId && c.isSitting) candidates.push(c);
            }
            if (candidates.length > 0) {
                var recruit = candidates[Math.floor(Math.random() * candidates.length)];
                recruit.targetX = PONG_TABLE.x + (agent.x < PONG_TABLE.x ? 50 : -50);
                recruit.targetY = PONG_TABLE.y + (Math.random() - 0.5) * 10;
                recruit.idleAction = 'pong_wait';
                recruit.idleReturnTimer = 1800 + Math.floor(Math.random() * 1200);
                recruit.isSitting = false;
                recruit.addIntent('Heading to play ping pong');
            }
        }
        return;
    }
    // Social trigger — two agents near each other anywhere
    if (agent.socialTarget && agent.id < agent.socialTarget && Math.random() < 0.005) {
        var other = agentMap[agent.socialTarget];
        if (other && !other.isSitting && !other.idleAction && agent.state === 'idle' && other.state === 'idle') {
            startPongGame(agent, other);
        }
    }
}

function updatePongGames() {
    _updatePongTablePos();
    for (var i = pongGames.length - 1; i >= 0; i--) {
        var g = pongGames[i];
        var p1 = g.p1, p2 = g.p2;
        g.timer++;

        if (g.phase === 'walking') {
            var d1 = Math.abs(p1.x - (PONG_TABLE.x - 50)) + Math.abs(p1.y - PONG_TABLE.y);
            var d2 = Math.abs(p2.x - (PONG_TABLE.x + 50)) + Math.abs(p2.y - PONG_TABLE.y);
            if (d1 < 5 && d2 < 5) {
                g.phase = 'playing'; g.timer = 0;
                p1.faceDir = 1; p2.faceDir = -1;
                g.ballX = 0; g.ballY = 0;
                g.p1Y = 0; g.p2Y = 0;
            }
            if (g.timer > 300) { pongGames.splice(i, 1); p1.idleAction = null; p2.idleAction = null; continue; }
        }

        if (g.phase === 'playing') {
            // Ball physics
            g.ballX += g.ballVX;
            g.ballY += g.ballVY;
            // Bounce off top/bottom
            if (g.ballY > 18 || g.ballY < -18) g.ballVY *= -1;
            // Paddle AI — with reaction delay and imperfection
            if (!g.p1Offset) g.p1Offset = 0;
            if (!g.p2Offset) g.p2Offset = 0;
            // Randomize target slightly so they don't perfectly track
            if (g.timer % 30 === 0) {
                g.p1Offset = (Math.random() - 0.5) * 12;
                g.p2Offset = (Math.random() - 0.5) * 12;
            }
            // Only track when ball is on their side
            if (g.ballVX < 0) {
                g.p1Y += (g.ballY + g.p1Offset - g.p1Y) * 0.12;
            } else {
                g.p1Y += (0 - g.p1Y) * 0.03; // drift back to center
            }
            if (g.ballVX > 0) {
                g.p2Y += (g.ballY + g.p2Offset - g.p2Y) * 0.10;
            } else {
                g.p2Y += (0 - g.p2Y) * 0.03;
            }
            // Lock agents to table sides + track ball vertically
            p1.x = PONG_TABLE.x - 50;
            p2.x = PONG_TABLE.x + 50;
            p1.y = PONG_TABLE.y + g.p1Y * 0.6;
            p2.y = PONG_TABLE.y + g.p2Y * 0.6;
            // Sync targets so isMoving stays false (paddles render)
            p1.targetX = p1.x; p1.targetY = p1.y;
            p2.targetX = p2.x; p2.targetY = p2.y;
            // Keep facing the table
            p1.faceDir = 1; p2.faceDir = -1;
            // Swing tracking — how close ball is to each paddle
            g.p1Swing = g.ballX < -20 ? Math.min(1, (-20 - g.ballX) / 16) : 0;
            g.p2Swing = g.ballX > 20 ? Math.min(1, (g.ballX - 20) / 16) : 0;
            // Score — ball past paddles
            if (g.ballX > 36) {
                g.p1Score++; g.ballX = 0; g.ballY = 0;
                g.ballVX = -1.5; g.ballVY = (Math.random() - 0.5) * 2;
            }
            if (g.ballX < -36) {
                g.p2Score++; g.ballX = 0; g.ballY = 0;
                g.ballVX = 1.5; g.ballVY = (Math.random() - 0.5) * 2;
            }
            // Paddle hit — with angle variation
            if (g.ballX < -30 && g.ballVX < 0 && Math.abs(g.ballY - g.p1Y) < 8) {
                g.ballVX = Math.abs(g.ballVX) * (1.02 + Math.random() * 0.1);
                g.ballVY = (g.ballY - g.p1Y) * 0.4 + (Math.random() - 0.5) * 1.5;
            }
            if (g.ballX > 30 && g.ballVX > 0 && Math.abs(g.ballY - g.p2Y) < 8) {
                g.ballVX = -Math.abs(g.ballVX) * (1.02 + Math.random() * 0.1);
                g.ballVY = (g.ballY - g.p2Y) * 0.4 + (Math.random() - 0.5) * 1.5;
            }
            // Speed cap
            g.ballVX = Math.max(-3, Math.min(3, g.ballVX));
            g.ballVY = Math.max(-2, Math.min(2, g.ballVY));

            // End after maxRounds total points
            if (g.p1Score + g.p2Score >= g.maxRounds) {
                g.phase = 'result'; g.timer = 0;
            }
        }

        if (g.phase === 'result') {
            if (g.timer > 120) {
                // Winner celebrates
                var winner = g.p1Score > g.p2Score ? p1 : p2;
                winner._socialMouth = 'laugh';
                p1.idleAction = null; p2.idleAction = null;
                p1.targetX = p1.desk.x; p1.targetY = p1.desk.y;
                p2.targetX = p2.desk.x; p2.targetY = p2.desk.y;
                pongGames.splice(i, 1);
            }
        }
    }
}

function drawPongGames() {
    for (var i = 0; i < pongGames.length; i++) {
        var g = pongGames[i];
        if (g.phase !== 'playing' && g.phase !== 'result') continue;
        var tx = PONG_TABLE.x, ty = PONG_TABLE.y;

        // Ball (small white circle)
        ctx.fillStyle = '#fff';
        ctx.beginPath(); ctx.arc(tx + g.ballX, ty + g.ballY, 2, 0, Math.PI * 2); ctx.fill();

        // Paddles removed — rackets are drawn on agents now

        // Scoreboard (names stacked to avoid overlap)
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(tx - 30, ty - 42, 60, 20);
        ctx.font = '7px Arial'; ctx.textAlign = 'center';
        ctx.fillStyle = '#f44336';
        ctx.fillText(g.p1.name + ': ' + g.p1Score, tx, ty - 34);
        ctx.fillStyle = '#2196f3';
        ctx.fillText(g.p2.name + ': ' + g.p2Score, tx, ty - 25);

        // Result
        if (g.phase === 'result') {
            var winnerName = g.p1Score > g.p2Score ? g.p1.name : g.p2.name;
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(tx - 30, ty - 10, 60, 16);
            ctx.fillStyle = '#ffd600'; ctx.font = 'bold 7px Arial';
            ctx.fillText(winnerName + ' wins!', tx, ty + 2);
        }
    }
}

function drawBreakArea(x, y) {
    _setFurnitureLampShadow(x + 120, y + 60);
    drawVendingMachine(x + 5, y + 15);
    drawPlant(x + 60, y + 10);
    drawWaterCooler(x + 160, y + 15);
    // Counter shadow (bottom only)
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x + 80, y + 108, 72, 15);
    // Counter (moved down)
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 80, y + 78, 72, 34);
    ctx.fillStyle = '#f5f5f5'; ctx.fillRect(x + 82, y + 80, 68, 30);
    // Counter top surface
    ctx.fillStyle = '#fafafa'; ctx.fillRect(x + 80, y + 78, 72, 4);
    // Cabinet doors
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 84, y + 88, 28, 18); ctx.fillRect(x + 116, y + 88, 28, 18);
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 96, y + 95, 4, 3); ctx.fillRect(x + 128, y + 95, 4, 3);
    // Coffee machine on counter
    ctx.fillStyle = '#212121'; ctx.fillRect(x + 95, y + 58, 24, 22);
    ctx.fillStyle = '#333'; ctx.fillRect(x + 97, y + 60, 20, 18);
    // Water tank
    ctx.fillStyle = 'rgba(3,169,244,0.5)'; ctx.fillRect(x + 111, y + 60, 5, 14);
    // Buttons
    ctx.fillStyle = '#4caf50'; ctx.fillRect(x + 99, y + 62, 4, 3);
    ctx.fillStyle = '#f44336'; ctx.fillRect(x + 99, y + 67, 4, 3);
    // Drip area
    ctx.fillStyle = '#424242'; ctx.fillRect(x + 99, y + 73, 12, 4);
    // Cup under drip
    ctx.fillStyle = '#fff'; ctx.fillRect(x + 102, y + 71, 6, 6);
    // Steam
    ctx.fillStyle = 'rgba(255,255,255,0.25)';
    ctx.fillRect(x + 104, y + 66, 2, 3); ctx.fillRect(x + 106, y + 64, 2, 3);
    // --- Kitchen counter with microwave & toaster ---
    // Counter shadow
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x + 170, y + 108, 72, 15);
    // Counter body
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 170, y + 78, 72, 34);
    ctx.fillStyle = '#f5f5f5'; ctx.fillRect(x + 172, y + 80, 68, 30);
    // Counter top surface
    ctx.fillStyle = '#fafafa'; ctx.fillRect(x + 170, y + 78, 72, 4);
    // Cabinet doors
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 174, y + 88, 28, 18); ctx.fillRect(x + 206, y + 88, 28, 18);
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 186, y + 95, 4, 3); ctx.fillRect(x + 218, y + 95, 4, 3);

    // Microwave (animated when in use)
    var micInUse = agents.some(function(a) { return a.idleAction === 'make_food' && !a.isSitting && Math.abs(a.x - (x + 190)) < 40; });
    ctx.fillStyle = '#455a64'; ctx.fillRect(x + 175, y + 56, 30, 24);
    ctx.fillStyle = '#37474f'; ctx.fillRect(x + 177, y + 58, 26, 20);
    // Door window
    ctx.fillStyle = '#263238'; ctx.fillRect(x + 178, y + 59, 17, 17);
    if (micInUse) {
        // Glowing interior when running
        var micGlow = 0.15 + Math.sin(_weatherTick * 0.15) * 0.1;
        ctx.fillStyle = 'rgba(255,200,50,' + micGlow + ')';
        ctx.fillRect(x + 179, y + 60, 15, 15);
        // Rotating plate (small dots moving in circle)
        var plateAngle = _weatherTick * 0.08;
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.beginPath(); ctx.arc(x + 186, y + 68 + Math.sin(plateAngle) * 2, 1, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(x + 186 + Math.cos(plateAngle) * 3, y + 68, 1, 0, Math.PI * 2); ctx.fill();
    } else {
        ctx.fillStyle = 'rgba(100,200,255,0.15)'; ctx.fillRect(x + 179, y + 60, 15, 15);
    }
    // Door handle
    ctx.fillStyle = '#90a4ae'; ctx.fillRect(x + 196, y + 63, 2, 10);
    // Control panel (right side)
    ctx.fillStyle = '#546e7a'; ctx.fillRect(x + 199, y + 59, 4, 17);
    // Buttons
    ctx.fillStyle = micInUse ? '#76ff03' : '#4caf50'; ctx.fillRect(x + 200, y + 61, 2, 2);
    ctx.fillStyle = '#f44336'; ctx.fillRect(x + 200, y + 65, 2, 2);
    ctx.fillStyle = '#78909c'; ctx.fillRect(x + 200, y + 69, 2, 2);
    ctx.fillRect(x + 200, y + 73, 2, 2);
    // Digital display
    ctx.fillStyle = micInUse ? '#1b5e20' : '#0a3010'; ctx.fillRect(x + 178, y + 60, 8, 4);
    ctx.fillStyle = micInUse ? '#76ff03' : '#4caf50'; ctx.font = '3px Arial'; ctx.textAlign = 'left';
    if (micInUse) {
        var secs = Math.floor(_weatherTick * 0.05) % 60;
        ctx.fillText((secs < 10 ? '0:0' : '0:') + secs, x + 179, y + 63);
    } else {
        ctx.fillText('0:00', x + 179, y + 63);
    }
    // Microwave hum — small vibration when running
    if (micInUse) {
        ctx.fillStyle = 'rgba(255,200,50,0.08)';
        var humOff = Math.sin(_weatherTick * 0.3) * 0.5;
        ctx.fillRect(x + 175 + humOff, y + 55, 30, 1);
    }

    // Toaster (animated when in use)
    var toastInUse = agents.some(function(a) { return a.idleAction === 'make_food' && !a.isSitting && Math.abs(a.x - (x + 220)) < 30; });
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 212, y + 64, 18, 16);
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 213, y + 65, 16, 14);
    // Rounded top
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 213, y + 62, 16, 4);
    // Bread slots
    ctx.fillStyle = '#424242'; ctx.fillRect(x + 215, y + 62, 4, 3);
    ctx.fillRect(x + 222, y + 62, 4, 3);
    if (toastInUse) {
        // Bread pushed down (not peeking out) + red glow from slots
        ctx.fillStyle = 'rgba(255,80,20,0.4)';
        ctx.fillRect(x + 215, y + 62, 4, 3);
        ctx.fillRect(x + 222, y + 62, 4, 3);
        // Heat glow rising from slots
        ctx.fillStyle = 'rgba(255,100,30,' + (0.15 + Math.sin(_weatherTick * 0.1) * 0.1) + ')';
        ctx.fillRect(x + 215, y + 58 - Math.sin(_weatherTick * 0.08) * 2, 4, 4);
        ctx.fillRect(x + 222, y + 58 - Math.cos(_weatherTick * 0.08) * 2, 4, 4);
        // Lever pushed down
        ctx.fillStyle = '#78909c'; ctx.fillRect(x + 229, y + 72, 2, 4);
        ctx.fillStyle = '#546e7a'; ctx.fillRect(x + 228, y + 72, 4, 2);
        // Heat shimmer lines
        ctx.strokeStyle = 'rgba(255,150,50,0.15)'; ctx.lineWidth = 0.5;
        for (var hi = 0; hi < 3; hi++) {
            var hx = x + 216 + hi * 4;
            var hy = y + 56 - (_weatherTick * 0.3 + hi * 5) % 10;
            ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(hx + Math.sin(_weatherTick * 0.1 + hi) * 2, hy - 3); ctx.stroke();
        }
    } else {
        // Bread peeking out (idle)
        ctx.fillStyle = '#d4a056'; ctx.fillRect(x + 215, y + 60, 4, 3);
        ctx.fillRect(x + 222, y + 60, 4, 3);
        // Lever up
        ctx.fillStyle = '#78909c'; ctx.fillRect(x + 229, y + 68, 2, 6);
        ctx.fillStyle = '#546e7a'; ctx.fillRect(x + 228, y + 68, 4, 2);
    }
    // Front label
    ctx.fillStyle = '#9e9e9e'; ctx.fillRect(x + 217, y + 72, 8, 1);

    // Label
    ctx.fillStyle = 'rgba(0,0,0,0.2)'; ctx.font = '8px "Press Start 2P"'; ctx.textAlign = 'center';
    _clearFurnitureShadow();
    ctx.fillText('BREAK ROOM', x + 100, y - 15);
}

function drawWaterCooler(x, y) {
    // Floor shadow
    ctx.fillStyle = 'rgba(0,0,0,0.1)'; ctx.beginPath(); ctx.ellipse(x, y + 42, 16, 5, 0, 0, Math.PI * 2); ctx.fill();
    // Legs
    ctx.fillStyle = '#757575'; ctx.fillRect(x - 10, y + 34, 4, 8); ctx.fillRect(x + 6, y + 34, 4, 8);
    // Base/stand body (flush with tank bottom)
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x - 12, y, 24, 36);
    ctx.fillStyle = '#eeeeee'; ctx.fillRect(x - 10, y + 2, 20, 32);
    // Front panel detail
    ctx.fillStyle = '#f5f5f5'; ctx.fillRect(x - 8, y + 8, 16, 10);
    // Spigot area
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x - 8, y + 18, 16, 8);
    // Hot spigot (red label + nozzle)
    ctx.fillStyle = '#f44336'; ctx.fillRect(x - 7, y + 19, 6, 6);
    ctx.fillStyle = '#d32f2f'; ctx.fillRect(x - 5, y + 25, 2, 3);
    // Cold spigot (blue label + nozzle)
    ctx.fillStyle = '#2196f3'; ctx.fillRect(x + 1, y + 19, 6, 6);
    ctx.fillStyle = '#1976d2'; ctx.fillRect(x + 3, y + 25, 2, 3);
    // Spigot labels
    ctx.fillStyle = '#fff'; ctx.font = '3px Arial'; ctx.textAlign = 'center';
    ctx.fillText('H', x - 4, y + 24); ctx.fillText('C', x + 4, y + 24);
    // Drip tray
    ctx.fillStyle = '#9e9e9e'; ctx.fillRect(x - 10, y + 28, 20, 4);
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x - 9, y + 29, 18, 2);
    // Water droplet on tray
    ctx.fillStyle = 'rgba(3,169,244,0.4)'; ctx.fillRect(x - 2, y + 29, 3, 2);
    // Water jug
    ctx.fillStyle = 'rgba(3, 169, 244, 0.6)'; ctx.fillRect(x - 9, y - 28, 18, 28);
    // Jug rounded top
    ctx.fillStyle = 'rgba(3, 169, 244, 0.5)';
    ctx.beginPath(); ctx.arc(x, y - 28, 9, Math.PI, 0); ctx.fill();
    // Jug cap/neck
    ctx.fillStyle = '#0277bd'; ctx.fillRect(x - 4, y - 34, 8, 6);
    ctx.fillStyle = '#01579b'; ctx.fillRect(x - 3, y - 36, 6, 3);
    // Water level line
    ctx.fillStyle = 'rgba(2,136,209,0.3)'; ctx.fillRect(x - 8, y - 8, 16, 1);
    // Shine on jug
    ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.fillRect(x - 7, y - 24, 3, 20);
    ctx.fillStyle = 'rgba(255,255,255,0.2)'; ctx.fillRect(x - 3, y - 22, 2, 16);
    // Animated bubbles in jug
    var coolerInUse = agents.some(function(a) { return a.idleAction === 'get_water' && !a.isSitting; });
    var bubbleActive = coolerInUse || (_weatherTick % 18000 < 60); // in-use OR random burst every ~5 min
    var bubbleSpeed = coolerInUse ? 1.5 : 0.8;
    var numBubbles = coolerInUse ? 5 : 3;
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    for (var bi = 0; bi < numBubbles; bi++) {
        var bSeed = bi * 17 + 7;
        var bx = x - 4 + (bSeed % 10);
        var byBase = y - 2;
        var byOff = bubbleActive ? (_weatherTick * bubbleSpeed + bi * 40) % 28 : (bi * 9);
        var bSize = 1 + (bi % 2);
        var bAlpha = bubbleActive ? Math.max(0.1, 0.6 - byOff / 40) : 0.35;
        ctx.globalAlpha = bAlpha;
        ctx.beginPath(); ctx.arc(bx + Math.sin(_weatherTick * 0.04 + bi) * 1.5, byBase - byOff, bSize, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1.0;
    // Cup dispenser on side
    ctx.fillStyle = '#e0e0e0'; ctx.fillRect(x + 14, y + 4, 12, 18);
    ctx.fillStyle = '#f5f5f5'; ctx.fillRect(x + 15, y + 5, 10, 16);
    // Cups inside
    ctx.fillStyle = '#fff';
    ctx.fillRect(x + 16, y + 7, 4, 10); ctx.fillRect(x + 21, y + 7, 4, 10);
    // Cup dispenser slot
    ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 15, y + 19, 10, 2);
}

function drawVendingMachine(x, y) {
    // Shadow (bottom only)
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x, y + 71, 45, 15);
    // Body
    ctx.fillStyle = '#b71c1c'; ctx.fillRect(x, y, 45, 75);
    ctx.fillStyle = '#c62828'; ctx.fillRect(x + 2, y + 2, 41, 71);
    // Window
    ctx.fillStyle = '#e3f2fd'; ctx.fillRect(x + 5, y + 5, 28, 45);
    ctx.fillStyle = 'rgba(255,255,255,0.2)'; ctx.fillRect(x + 5, y + 5, 10, 45); // glass shine
    // Snacks in rows
    const snackCols = ['#ffc107', '#ff5722', '#4caf50', '#795548', '#e91e63', '#2196f3'];
    for (let r = 0; r < 4; r++) {
        for (let c = 0; c < 3; c++) {
            ctx.fillStyle = snackCols[(r * 3 + c) % 6];
            ctx.fillRect(x + 7 + c * 9, y + 7 + r * 11, 6, 8);
            // Highlight
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.fillRect(x + 7 + c * 9, y + 7 + r * 11, 2, 2);
        }
        // Shelf
        ctx.fillStyle = '#bdbdbd'; ctx.fillRect(x + 5, y + 16 + r * 11, 28, 1);
    }
    // Coin slot area
    ctx.fillStyle = '#1a1a1a'; ctx.fillRect(x + 5, y + 55, 35, 15);
    // Buttons
    ctx.fillStyle = '#4caf50'; ctx.fillRect(x + 35, y + 10, 6, 6);
    ctx.fillStyle = '#f44336'; ctx.fillRect(x + 35, y + 20, 6, 6);
    // Dispenser slot
    ctx.fillStyle = '#424242'; ctx.fillRect(x + 8, y + 58, 28, 8);
    // Brand label
    ctx.fillStyle = '#ffd700'; ctx.font = '4px "Press Start 2P"'; ctx.textAlign = 'center';
    ctx.fillText('SNAX', x + 22, y + 54);
}

function drawTallPlant(x, y) {
    // Pot
    ctx.fillStyle = '#a1887f'; ctx.fillRect(x - 2, y + 28, 22, 4);
    ctx.fillStyle = '#d84315'; ctx.fillRect(x, y + 30, 18, 18);
    ctx.fillStyle = '#e64a19'; ctx.fillRect(x + 2, y + 32, 14, 14);
    // Soil
    ctx.fillStyle = '#4e342e'; ctx.fillRect(x + 2, y + 30, 14, 4);
    // Stems
    ctx.fillStyle = '#2e7d32';
    ctx.fillRect(x + 5, y + 2, 3, 32); ctx.fillRect(x + 11, y - 6, 3, 40);
    // Leaves (pixel clusters)
    ctx.fillStyle = '#43a047';
    ctx.fillRect(x + 1, y - 2, 6, 4); ctx.fillRect(x + 3, y - 6, 4, 4);
    ctx.fillRect(x + 8, y - 10, 6, 4); ctx.fillRect(x + 12, y - 14, 4, 4);
    ctx.fillStyle = '#66bb6a';
    ctx.fillRect(x - 1, y + 4, 4, 6); ctx.fillRect(x + 14, y - 4, 4, 6);
    ctx.fillRect(x + 8, y + 6, 4, 4);
    // Leaf highlights
    ctx.fillStyle = '#81c784';
    ctx.fillRect(x + 2, y - 4, 2, 2); ctx.fillRect(x + 10, y - 12, 2, 2);
}

function drawPlant(x, y) {
    // Pot
    ctx.fillStyle = '#eceff1'; ctx.fillRect(x, y + 10, 16, 14);
    ctx.fillStyle = '#fafafa'; ctx.fillRect(x + 2, y + 12, 12, 10);
    // Soil
    ctx.fillStyle = '#4e342e'; ctx.fillRect(x + 2, y + 10, 12, 4);
    // Bush leaves
    ctx.fillStyle = '#2e7d32'; ctx.beginPath(); ctx.arc(x + 8, y + 5, 9, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#388e3c'; ctx.beginPath(); ctx.arc(x + 3, y + 1, 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#43a047'; ctx.beginPath(); ctx.arc(x + 13, y + 1, 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#4caf50'; ctx.beginPath(); ctx.arc(x + 8, y - 3, 5, 0, Math.PI * 2); ctx.fill();
    // Highlights
    ctx.fillStyle = '#66bb6a';
    ctx.fillRect(x + 4, y - 2, 3, 3); ctx.fillRect(x + 10, y + 2, 3, 3);
}

function drawBookshelf(x, y) {
    // Shadow (bottom only)
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(x, y + 76, 50, 15);
    // Frame
    ctx.fillStyle = '#6d4c41'; ctx.fillRect(x, y, 50, 80);
    ctx.fillStyle = '#8d6e63'; ctx.fillRect(x + 2, y + 2, 46, 76);
    ctx.fillStyle = '#5d4037'; ctx.fillRect(x + 4, y + 4, 42, 72);
    // Books in 3 rows
    const bookColors = ['#e57373','#ef5350','#64b5f6','#42a5f5','#fff176','#ffee58','#81c784','#66bb6a','#ce93d8','#ff8a65','#4dd0e1','#a1887f'];
    for (let r = 0; r < 3; r++) {
        const shelfY = y + 6 + r * 24;
        let bx = x + 6;
        for (let i = 0; i < 6; i++) {
            const bw = 3 + (i % 3); // varying widths
            const bh = 14 + (i % 2) * 3; // varying heights
            ctx.fillStyle = bookColors[(r * 6 + i) % bookColors.length];
            ctx.fillRect(bx, shelfY + (18 - bh), bw, bh);
            // Spine detail
            ctx.fillStyle = 'rgba(0,0,0,0.15)';
            ctx.fillRect(bx, shelfY + (18 - bh), 1, bh);
            // Title line
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.fillRect(bx + 1, shelfY + (18 - bh) + 3, bw - 2, 1);
            bx += bw + 1;
        }
        // Shelf
        ctx.fillStyle = '#8d6e63'; ctx.fillRect(x + 4, shelfY + 18, 42, 3);
        ctx.fillStyle = '#a1887f'; ctx.fillRect(x + 4, shelfY + 18, 42, 1);
    }
    // Small ornament on top shelf
    ctx.fillStyle = '#ffd700'; ctx.fillRect(x + 36, y + 6, 6, 8);
    ctx.fillStyle = '#ffeb3b'; ctx.fillRect(x + 37, y + 7, 4, 4);
}

function _archiveBindingLabel(item) {
    return item && (item.archiveProjectTitle || item.archiveTitle || item.archiveProjectId || item.archiveId || '');
}

function drawFunctionalBookshelf(item) {
    drawBookshelf(item.x, item.y);
    var hasArchive = !!(item.archiveProjectId || item.archiveId);
    ctx.save();
    ctx.fillStyle = hasArchive ? '#4caf50' : '#607d8b';
    ctx.fillRect(item.x + 34, item.y + 64, 10, 10);
    ctx.fillStyle = '#ffffff';
    ctx.font = '8px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(hasArchive ? '✓' : '!', item.x + 39, item.y + 69);

    if (editMode || selectedItemId === item.id) {
        var label = hasArchive ? _archiveBindingLabel(item) : _tr('bookshelf_unbound');
        ctx.font = '9px Arial';
        var textW = Math.min(140, Math.max(54, ctx.measureText(label).width + 10));
        var lx = item.x + 25 - textW / 2;
        var ly = item.y - 16;
        ctx.fillStyle = 'rgba(20,20,32,0.85)';
        ctx.fillRect(lx, ly, textW, 13);
        ctx.strokeStyle = hasArchive ? '#4caf50' : '#90a4ae';
        ctx.strokeRect(lx, ly, textW, 13);
        ctx.fillStyle = '#fff';
        var clipped = label.length > 18 ? label.slice(0, 17) + '…' : label;
        ctx.fillText(clipped, item.x + 25, ly + 7);
    }
    ctx.restore();
}

var _bookshelfActionMenu = null;
var _bookshelfBindDialog = null;
var _archiveProjectCache = { loadedAt: 0, projects: [] };

function _isFunctionalBookshelf(item) {
    return item && item.type === 'functionalBookshelf';
}

function _archiveToast(message, type) {
    var el = document.createElement('div');
    el.textContent = message;
    var border = type === 'error' ? '#ef5350' : '#4caf50';
    el.style.cssText = 'position:fixed;bottom:86px;left:50%;transform:translateX(-50%);z-index:100000;background:#15151f;border:1px solid ' + border + ';color:#fff;padding:8px 14px;border-radius:6px;font-size:12px;box-shadow:0 8px 24px rgba(0,0,0,.35);';
    document.body.appendChild(el);
    setTimeout(function(){ if (el.parentNode) el.parentNode.removeChild(el); }, 3000);
}

function _closeBookshelfActionMenu() {
    if (_bookshelfActionMenu && _bookshelfActionMenu.parentNode) _bookshelfActionMenu.parentNode.removeChild(_bookshelfActionMenu);
    _bookshelfActionMenu = null;
}

function _handleFunctionalFurnitureClick(item, screenX, screenY) {
    if (editMode) return false;
    if (_isFunctionalBookshelf(item)) {
        _showBookshelfActionMenu(item, screenX, screenY);
        return true;
    }
    if (_isFunctionalMeetingSpace(item)) {
        _handleMeetingSpaceClick(item, screenX, screenY);
        return true;
    }
    return false;
}

function _handleMeetingSpaceClick(item, screenX, screenY) {
    var meeting = _meetingForSpace(item);
    _closeBookshelfActionMenu();
    if (meeting && meeting.id) {
        _showOccupiedMeetingSpaceMenu(item, meeting, screenX, screenY);
        return;
    }
    _showIdleMeetingSpaceMenu(item, screenX, screenY);
}

function _positionMeetingSpaceMenu(menu, screenX, screenY) {
    document.body.appendChild(menu);
    var left = Math.min(screenX + 10, window.innerWidth - 230);
    var top = Math.min(screenY + 10, window.innerHeight - 120);
    menu.style.left = Math.max(8, left) + 'px';
    menu.style.top = Math.max(8, top) + 'px';
    _bookshelfActionMenu = menu;
    setTimeout(function() {
        document.addEventListener('click', _closeBookshelfActionMenu, { once: true });
    }, 0);
}

function _meetingTopicLabel(meeting) {
    return (meeting && (meeting.topic || meeting.purpose || meeting.title || meeting.id)) || _tr('meeting');
}

function _showOccupiedMeetingSpaceMenu(item, meeting, screenX, screenY) {
    var menu = document.createElement('div');
    menu.className = 'bookshelf-action-menu meeting-space-action-menu';
    var title = document.createElement('div');
    title.className = 'bookshelf-action-title';
    title.textContent = _meetingSpaceDisplayName(item);
    var topic = document.createElement('div');
    topic.className = 'meeting-space-topic';
    topic.textContent = _meetingTopicLabel(meeting);
    topic.title = topic.textContent;
    var viewBtn = document.createElement('button');
    viewBtn.textContent = _tr('meeting_space_view_current');
    viewBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        _closeBookshelfActionMenu();
        openMeetingDetailModal(meeting.id);
    });
    menu.appendChild(title);
    menu.appendChild(topic);
    menu.appendChild(viewBtn);
    _positionMeetingSpaceMenu(menu, screenX, screenY);
}

function _showIdleMeetingSpaceMenu(item, screenX, screenY) {
    var menu = document.createElement('div');
    menu.className = 'bookshelf-action-menu meeting-space-action-menu';
    var title = document.createElement('div');
    title.className = 'bookshelf-action-title';
    title.textContent = _meetingSpaceDisplayName(item);
    var empty = document.createElement('div');
    empty.className = 'meeting-space-empty';
    empty.textContent = _tr('meeting_space_idle');
    var viewBtn = document.createElement('button');
    viewBtn.textContent = _tr('meeting_space_view_all');
    viewBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        _closeBookshelfActionMenu();
        openMeetingsDashboard();
    });
    menu.appendChild(title);
    menu.appendChild(empty);
    menu.appendChild(viewBtn);
    _positionMeetingSpaceMenu(menu, screenX, screenY);
}

function _showBookshelfActionMenu(item, screenX, screenY) {
    _closeBookshelfActionMenu();
    var bound = !!(item.archiveProjectId || item.archiveId);
    var menu = document.createElement('div');
    menu.className = 'bookshelf-action-menu';
    var title = document.createElement('div');
    title.className = 'bookshelf-action-title';
    title.textContent = bound ? _archiveBindingLabel(item) : _tr('bookshelf_unbound');

    var viewBtn = document.createElement('button');
    viewBtn.textContent = _tr('bookshelf_view_archive');
    viewBtn.disabled = !bound;
    viewBtn.title = bound ? _tr('bookshelf_view_archive') : _tr('bookshelf_unbound_hint');
    viewBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        if (!bound) return;
        _closeBookshelfActionMenu();
        _openBoundBookshelfArchive(item);
    });

    var bindBtn = document.createElement('button');
    bindBtn.textContent = bound ? _tr('bookshelf_change_archive') : _tr('bookshelf_bind_archive');
    bindBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        _closeBookshelfActionMenu();
        _showArchiveBindingDialog(item);
    });

    menu.appendChild(title);
    menu.appendChild(viewBtn);
    menu.appendChild(bindBtn);
    document.body.appendChild(menu);
    var left = Math.min(screenX + 10, window.innerWidth - 190);
    var top = Math.min(screenY + 10, window.innerHeight - 120);
    menu.style.left = Math.max(8, left) + 'px';
    menu.style.top = Math.max(8, top) + 'px';
    _bookshelfActionMenu = menu;
    setTimeout(function() {
        document.addEventListener('click', _closeBookshelfActionMenu, { once: true });
    }, 0);
}

function _openBoundBookshelfArchive(item) {
    var archiveId = item.archiveProjectId || item.archiveId;
    if (!archiveId) {
        _archiveToast(_tr('bookshelf_unbound_hint'), 'error');
        return;
    }
    if (typeof window.openArchiveRoomProject === 'function') {
        window.openArchiveRoomProject(archiveId);
        return;
    }
    if (typeof window.openArchiveRoom === 'function') {
        window.openArchiveRoom();
        setTimeout(function() {
            if (window.ArchiveRoom && typeof window.ArchiveRoom.openProject === 'function') {
                window.ArchiveRoom.openProject(archiveId);
            }
        }, 350);
        return;
    }
    _archiveToast(_tr('bookshelf_archive_unavailable'), 'error');
}

function _fetchArchiveProjects() {
    var now = Date.now();
    if (_archiveProjectCache.projects.length && now - _archiveProjectCache.loadedAt < 30000) {
        return Promise.resolve(_archiveProjectCache.projects);
    }
    return fetch('/api/archive-room').then(function(r) { return r.json(); }).then(function(d) {
        if (d.error) throw new Error(d.error);
        _archiveProjectCache = { loadedAt: Date.now(), projects: d.projects || [] };
        return _archiveProjectCache.projects;
    });
}

function _closeArchiveBindingDialog() {
    if (_bookshelfBindDialog && _bookshelfBindDialog.parentNode) _bookshelfBindDialog.parentNode.removeChild(_bookshelfBindDialog);
    _bookshelfBindDialog = null;
}

function _showArchiveBindingDialog(item) {
    _closeArchiveBindingDialog();
    var overlay = document.createElement('div');
    overlay.className = 'bookshelf-bind-overlay';
    overlay.innerHTML = '<div class="bookshelf-bind-dialog"><div class="bookshelf-bind-head"><strong>' + _tr('bookshelf_bind_archive') + '</strong><button type="button" aria-label="' + _tr('close_panel') + '">×</button></div><div class="bookshelf-bind-body">' + _tr('bookshelf_loading_archives') + '</div></div>';
    document.body.appendChild(overlay);
    _bookshelfBindDialog = overlay;
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) _closeArchiveBindingDialog();
    });
    overlay.querySelector('button').addEventListener('click', _closeArchiveBindingDialog);
    _fetchArchiveProjects().then(function(projects) {
        if (!_bookshelfBindDialog) return;
        var body = overlay.querySelector('.bookshelf-bind-body');
        if (!projects.length) {
            body.innerHTML = '<div class="bookshelf-bind-empty">' + _tr('bookshelf_no_archives') + '</div>';
            return;
        }
        body.innerHTML = '';
        projects.forEach(function(p) {
            var btn = document.createElement('button');
            btn.className = 'bookshelf-archive-choice';
            var title = p.title || p.name || p.id;
            var desc = p.description || p.summary || '';
            btn.innerHTML = '<span>' + _escapeHtml(title) + '</span><small>' + _escapeHtml(desc || p.id) + '</small>';
            btn.addEventListener('click', function() {
                _pushUndo();
                item.archiveProjectId = p.id;
                item.archiveProjectTitle = title;
                saveOfficeConfig();
                _closeArchiveBindingDialog();
                _archiveToast(_tr('bookshelf_bound_archive', { name: title }), 'success');
            });
            body.appendChild(btn);
        });
    }).catch(function(e) {
        var body = overlay.querySelector('.bookshelf-bind-body');
        if (body) body.innerHTML = '<div class="bookshelf-bind-empty">' + _tr('bookshelf_archive_load_failed') + ': ' + _escapeHtml(e.message || e) + '</div>';
    });
}

function _escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// --- INTERACTION ---
// Track drag distance to distinguish clicks from pans
let _clickStartX = 0, _clickStartY = 0;
canvas.addEventListener('mouseup', function(e) {
    const dist = Math.abs(e.clientX - _clickStartX) + Math.abs(e.clientY - _clickStartY);
    if (dist > 5) return; // was a drag, not a click
    handleCanvasClick(e.clientX, e.clientY);
});

let _touchStartX2 = 0, _touchStartY2 = 0;
canvas.addEventListener('touchend', function(e) {
    if (e.changedTouches.length === 1) {
        const t = e.changedTouches[0];
        const dist = Math.abs(t.clientX - _touchStartX2) + Math.abs(t.clientY - _touchStartY2);
        if (dist > 10) return; // was a drag
        handleCanvasClick(t.clientX, t.clientY);
    }
});

function handleCanvasClick(clientX, clientY) {
    if (editMode) return; // edit mode handles clicks via click event
    const world = screenToWorld(clientX, clientY);
    const cx = world.x;
    const cy = world.y;
    // Check chat bubble scroll arrows
    for (var si = 0; si < renderedChatBubbles.length; si++) {
        var sb = renderedChatBubbles[si];
        var sr = sb.fullRect;
        if (cx >= sr.x && cx <= sr.x + sr.w && cy >= sr.y && cy <= sr.y + sr.h) {
            if (cy < sr.y + 15) continue;
            if (sb.canScrollUp && cy < sr.y + 28) {
                chatScrollOffset[sb.agentKey] = (chatScrollOffset[sb.agentKey] || 0) + 3;
                return;
            }
            if (sb.canScrollDown && cy > sr.y + sr.h - 18) {
                chatScrollOffset[sb.agentKey] = Math.max(0, (chatScrollOffset[sb.agentKey] || 0) - 3);
                return;
            }
        }
    }
    // Chat bubble close/minimize
    if (handleChatBubbleClick(cx, cy)) return;
    // Thought/speech bubble close/minimize
    if (handleBubbleClick(cx, cy)) return;
    var furnitureHit = _findFurnitureAt(cx, cy);
    if (furnitureHit && _handleFunctionalFurnitureClick(furnitureHit, clientX, clientY)) return;
    // Check gear icon click to open agent modal
    for (const agent of agents) {
        const g = agent.gearRect;
        if (g && cx >= g.x && cx <= g.x + g.w && cy >= g.y && cy <= g.y + g.h) {
            openModal(agent);
            return;
        }
    }
}

function _providerKindDisplay(providerKind) {
    var kind = String(providerKind || 'openclaw').toLowerCase();
    if (kind === 'hermes') return 'Hermes';
    if (kind === 'codex') return 'Codex CLI';
    if (kind === 'claude-code') return 'Claude Code';
    return 'OpenClaw';
}

function _providerAgentLabel(agent) {
    var provider = _providerKindDisplay(agent && agent.providerKind);
    var bits = [provider + ' Agent'];
    if (agent && agent.providerAgentId) bits.push('profile: ' + agent.providerAgentId);
    if (agent && agent.provider && agent.provider !== provider) bits.push(agent.provider);
    return bits.join(' · ');
}

function _isOpenClawAgent(agent) {
    return String((agent && agent.providerKind) || 'openclaw').toLowerCase() === 'openclaw';
}

function openModal(agent) {
    selectedAgent = agent;
    window.selectedAgent = agent;

    // Reset zoom to 1x on mobile so modal renders at normal size
    const vp = document.querySelector('meta[name="viewport"]');
    if (vp) {
        vp._origContent = vp.content;
        vp.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
        // Force reflow
        setTimeout(() => { vp.content = 'width=device-width, initial-scale=1.0, user-scalable=yes'; }, 50);
    }

    // Clear notification on open
    if (agent.notify) {
        agent.notify = false;
        dismissedNotify.add(agent.statusKey);
        clearNotifyOnServer(agent.statusKey);
    }

    document.getElementById('modal-emoji').textContent = agent.emoji;
    document.getElementById('modal-name').textContent = agent.name;
    document.getElementById('modal-role').textContent = agent.role;
    document.getElementById('modal-status').textContent = agent.state.toUpperCase();
    document.getElementById('modal-task').textContent = agent.task || '—';
    document.getElementById('modal-branch').textContent = getBranchDisplayName(agent.branch);
    document.getElementById('modal-updated').textContent = timeStr();

    var providerLabel = agent.providerKind === 'hermes'
        ? ('Hermes Agent' + (agent.providerAgentId ? ' · profile: ' + agent.providerAgentId : '') + (agent.provider ? ' · ' + agent.provider : ''))
        : (agent.providerKind === 'codex'
            ? ('Codex Collaborator' + (agent.providerAgentId ? ' · profile: ' + agent.providerAgentId : '') + (agent.provider ? ' · ' + agent.provider : ''))
            : 'OpenClaw Agent');
    var roleEl = document.getElementById('modal-role');
    if (roleEl) roleEl.textContent = (agent.role || '') + (agent.role ? ' · ' : '') + providerLabel;

    var isOpenClaw = (agent.providerKind || 'openclaw') === 'openclaw';
    var modelSection = document.querySelector('#modal-model-select')?.closest('.modal-section');
    if (modelSection) modelSection.style.display = isOpenClaw ? '' : 'none';
    document.querySelectorAll('.bio-section').forEach(function(el) { el.style.display = isOpenClaw ? '' : 'none'; });

    // Task I/O
    const inputBox = document.getElementById('modal-input');
    if (agent.lastInput) {
        inputBox.innerHTML = `<div class="io-from">📥 ${escHtml(_tr('from_label'))}: <strong>${escHtml(agent.lastInput.from || _tr('unknown'))}</strong></div><div class="io-text">${escHtml(agent.lastInput.text || '—')}</div>`;
    } else {
        inputBox.innerHTML = '<div class="io-text">' + escHtml(_tr('no_recent_request')) + '</div>';
    }

    const outputBox = document.getElementById('modal-output');
    if (agent.lastOutput) {
        outputBox.innerHTML = `<div class="io-text">${escHtml(agent.lastOutput.text || '—')}</div>`;
    } else {
        outputBox.innerHTML = '<div class="io-text">' + escHtml(_tr('no_recent_response')) + '</div>';
    }

    const planBox = document.getElementById('modal-plan');
    planBox.innerHTML = '';
    agent.intentHistory.forEach(item => {
        const div = document.createElement('div'); div.className = 'log-entry'; div.textContent = item;
        planBox.appendChild(div);
    });
    planBox.scrollTop = planBox.scrollHeight;

    const logBox = document.getElementById('modal-logs');
    logBox.innerHTML = '';
    agent.logHistory.forEach(item => {
        const div = document.createElement('div'); div.className = 'log-entry'; div.textContent = item;
        logBox.appendChild(div);
    });
    logBox.scrollTop = logBox.scrollHeight;

    // Load OpenClaw-only editable files/skills for OpenClaw agents.
    if (isOpenClaw) loadAgentSkills(agent.statusKey || agent.id);

    document.getElementById('agentModal').classList.remove('hidden');
}

function escHtml(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}
function escAttr(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escTextarea(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ─── AGENT WORKSPACE WINDOW ──────────────────────────────────
var _agentWorkspace = {
    agent: null,
    desk: null,
    data: null,
    activeTab: 'overview',
    loading: false,
    drag: null,
    resize: null,
    lastRect: null
};

function _worldToScreen(wx, wy) {
    var rect = canvas.getBoundingClientRect();
    var base = getBaseScale();
    var totalZoom = base * camera.zoom;
    var dx = (wx - W / 2 - camera.x) * totalZoom + displayW / 2;
    var dy = (wy - H / 2 - camera.y) * totalZoom + displayH / 2;
    return {
        x: dx * (rect.width / displayW) + rect.left,
        y: dy * (rect.height / displayH) + rect.top
    };
}

function _isDeskItem(item) {
    return !!(item && (item.type === 'desk' || item.type === 'bossDesk'));
}

function _findDeskAtScreen(clientX, clientY) {
    var world = screenToWorld(clientX, clientY);
    var item = _findFurnitureAt(world.x, world.y);
    return _isDeskItem(item) ? item : null;
}

function _agentWorkspaceKey(agent) {
    return (agent && (agent.statusKey || agent.id || agent.name)) || '';
}

function _hideAgentWorkspaceMenu() {
    var menu = document.getElementById('agent-workspace-menu');
    if (menu) menu.classList.add('hidden');
}

function _showAgentWorkspaceMenu(deskItem, clientX, clientY) {
    var agent = _getDeskAgent(deskItem);
    if (!agent) return false;
    var menu = document.getElementById('agent-workspace-menu');
    var btn = document.getElementById('agent-workspace-open-btn');
    if (!menu || !btn) return false;
    _agentWorkspace.agent = agent;
    _agentWorkspace.desk = deskItem;
    btn.textContent = (typeof i18n !== 'undefined' ? i18n.t('open_workspace') : 'Open workspace') + ': ' + (agent.name || 'agent');
    var pos = _worldToScreen(deskItem.x, deskItem.y);
    var left = clientX || pos.x;
    var top = clientY || pos.y;
    menu.classList.remove('hidden');
    var mw = menu.offsetWidth || 210;
    var mh = menu.offsetHeight || 42;
    left = Math.max(8, Math.min(window.innerWidth - mw - 8, left - mw / 2));
    top = Math.max(8, Math.min(window.innerHeight - mh - 8, top - mh - 10));
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
    return true;
}

function _formatAgentWorkspaceTime(value) {
    if (!value) return '';
    var d = new Date(typeof value === 'number' ? (value > 100000000000 ? value : value * 1000) : value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function _agentWorkspaceItemList(items, emptyText, render) {
    if (!items || !items.length) return '<div class="agent-workspace-empty">' + escHtml(emptyText) + '</div>';
    return '<div class="agent-workspace-list">' + items.map(render).join('') + '</div>';
}

function _agentWorkspaceRecentActivity(data, limit) {
    var activity = (data.activity || []).filter(function(msg) {
        var text = msg && (msg.text || msg.content || msg.message || msg.task || '');
        return String(text || '').trim();
    }).slice(-limit).reverse();
    return _agentWorkspaceItemList(activity, 'No recent activity surfaced yet', function(msg) {
        var text = msg.text || msg.content || msg.message || msg.task || JSON.stringify(msg).slice(0, 320);
        return '<div class="agent-workspace-item agent-workspace-activity-item">' +
            '<div>' + escHtml(String(text).slice(0, 700)) + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(_formatAgentWorkspaceTime(msg.ts || msg.time || msg.createdAt || msg.updatedAt)) + '</div>' +
        '</div>';
    });
}

function _agentWorkspaceProjectMeta(t, compact) {
    var parts = [];
    if (t.projectTitle) parts.push(t.projectTitle);
    if (t.role) parts.push(t.role);
    if (t.priority) parts.push(t.priority);
    if (t.column) parts.push(t.column);
    if (t.executionState) parts.push(t.executionState);
    if (!compact && t.projectWorkflowPhase) parts.push('project ' + t.projectWorkflowPhase);
    if (!compact && t.activeAttemptStatus) parts.push('attempt ' + t.activeAttemptStatus);
    if (!compact && t.scheduledRepeatEnabled) parts.push('scheduled');
    return parts.join(' · ');
}

function _agentWorkspaceProjectBadges(t) {
    var badges = [];
    if (t.completed) badges.push('done');
    if (t.activeAttemptId) badges.push('active');
    if (t.meetingBlocker && t.meetingBlocker.status) badges.push('meeting ' + t.meetingBlocker.status);
    if (t.projectExecutionFlowActive) badges.push('flow active');
    if (t.projectExecutionFlowStopReason) badges.push(t.projectExecutionFlowStopReason);
    if (t.blockedReason) badges.push('blocked');
    return badges.length ? '<div class="agent-workspace-badges">' + badges.map(function(label) {
        return '<span>' + escHtml(label) + '</span>';
    }).join('') + '</div>' : '';
}

function _workspaceFolderOptions(current) {
    var notes = ((_agentWorkspace.data || {}).workspace || {}).notes || [];
    var folders = {};
    notes.forEach(function(n) { folders[n.folder || 'General'] = true; });
    folders.General = true;
    var value = current || 'General';
    return Object.keys(folders).sort().map(function(f) {
        return '<option value="' + escAttr(f) + '"' + (f === value ? ' selected' : '') + '>' + escHtml(f) + '</option>';
    }).join('');
}

function _renderAgentWorkspaceOverview(data) {
    var agent = data.agent || {};
    var presence = data.presence || {};
    var workspace = data.workspace || {};
    var tasks = (workspace.tasks || []).filter(function(t) { return !t.done; }).slice(0, 5);
    var bulletin = (workspace.bulletin || []).slice(0, 4);
    var projectTasks = (data.projectTasks || []).slice(0, 5);
    var score = data.score || {};
    return '<div class="agent-workspace-grid">' +
        '<div class="agent-workspace-card"><h3>Status</h3>' +
            '<div>' + escHtml((presence.state || 'idle').toUpperCase()) + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(presence.task || agent.role || 'No active task') + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(agent.providerKind || 'openclaw') + ' · ' + escHtml(agent.model || agent.provider || 'model not set') + '</div>' +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Agent Info</h3>' +
            '<div class="agent-workspace-item">' + escHtml(agent.displayName || agent.name || agent.id) +
                '<div class="agent-workspace-meta">' + escHtml(agent.statusKey || agent.id || '') + ' · ' + escHtml(agent.branch || 'Unassigned') + '</div>' +
                '<div class="agent-workspace-meta">' + escHtml(agent.role || '') + '</div>' +
            '</div>' +
            '<div class="agent-workspace-item">' + escHtml(score.score || 0) + ' points<div class="agent-workspace-meta">' + escHtml(score.completed || 0) + ' completed · streak ' + escHtml(score.streak || 0) + '</div></div>' +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Open Tasks</h3>' +
            _agentWorkspaceItemList(tasks, 'No workspace tasks', function(t) {
                return '<div class="agent-workspace-item">' + escHtml(t.text) + '<div class="agent-workspace-meta">' + escHtml(t.status || 'queued') + (t.due ? ' · Due ' + escHtml(t.due) : '') + '</div></div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Bulletin</h3>' +
            _agentWorkspaceItemList(bulletin, 'No pinned notes', function(n) {
                return '<div class="agent-workspace-item">' + escHtml(n.text) + '<div class="agent-workspace-meta">' + escHtml(n.createdBy || 'user') + ' · ' + escHtml(_formatAgentWorkspaceTime(n.createdAt)) + '</div></div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Project Work</h3>' +
            _agentWorkspaceItemList(projectTasks, 'No assigned project cards', function(t) {
                return '<div class="agent-workspace-item">' + escHtml(t.title) +
                    '<div class="agent-workspace-meta">' + escHtml(_agentWorkspaceProjectMeta(t, true)) + '</div>' +
                    _agentWorkspaceProjectBadges(t) +
                '</div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-card agent-workspace-wide"><h3>Recent Activity</h3>' +
            _agentWorkspaceRecentActivity(data, 12) +
        '</div>' +
    '</div>';
}

function _renderAgentWorkspaceBulletin(data) {
    var items = (data.workspace && data.workspace.bulletin) || [];
    return '<form class="agent-workspace-form" data-aw-form="bulletin">' +
        '<input name="text" maxlength="5000" placeholder="Add note for this agent">' +
        '<button type="submit">Add</button>' +
    '</form>' +
    _agentWorkspaceItemList(items, 'No bulletin notes yet', function(n) {
        return '<div class="agent-workspace-item">' +
            '<div>' + escHtml(n.text) + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(n.createdBy || 'user') + ' · ' + escHtml(_formatAgentWorkspaceTime(n.createdAt)) + '</div>' +
            '<button type="button" data-aw-action="deleteBulletin" data-aw-id="' + escHtml(n.id) + '">Delete</button>' +
        '</div>';
    });
}

function _renderAgentWorkspaceTasks(data) {
    var items = (data.workspace && data.workspace.tasks) || [];
    var projectTasks = data.projectTasks || [];
    var settings = (data.workspace && data.workspace.settings) || {};
    var activeId = (data.workspace && data.workspace.activeTaskId) || '';
    return '<div class="agent-workspace-toolbar">' +
        '<label>Run mode <select data-aw-action="setTaskMode">' +
            '<option value="manual"' + ((settings.taskMode || 'manual') === 'manual' ? ' selected' : '') + '>Manual</option>' +
            '<option value="single"' + (settings.taskMode === 'single' ? ' selected' : '') + '>Single task</option>' +
            '<option value="auto"' + (settings.taskMode === 'auto' ? ' selected' : '') + '>Auto run queue</option>' +
        '</select></label>' +
        (activeId ? '<button type="button" data-aw-action="completeTask" data-aw-id="' + escAttr(activeId) + '">Complete Active</button>' : '') +
    '</div>' +
    '<form class="agent-workspace-form agent-workspace-form-stack" data-aw-form="task">' +
        '<input name="text" maxlength="1000" placeholder="Add workspace task">' +
        '<textarea name="detail" maxlength="5000" placeholder="Details or instructions"></textarea>' +
        '<div class="agent-workspace-row"><input name="due" maxlength="80" placeholder="Due"><select name="priority"><option>normal</option><option>high</option><option>low</option></select></div>' +
        '<button type="submit">Add</button>' +
    '</form>' +
    _agentWorkspaceItemList(items, 'No workspace tasks yet', function(t) {
        return '<div class="agent-workspace-item">' +
            '<label><input type="checkbox" data-aw-action="toggleTask" data-aw-id="' + escAttr(t.id) + '"' + (t.done ? ' checked' : '') + '> ' + escHtml(t.text) + '</label>' +
            (t.detail ? '<div class="agent-workspace-detail">' + escHtml(t.detail) + '</div>' : '') +
            '<div class="agent-workspace-meta">' + escHtml(t.status || (t.done ? 'done' : 'queued')) + ' · ' + escHtml(t.priority || 'normal') + (t.due ? ' · Due ' + escHtml(t.due) : '') + '</div>' +
            '<div class="agent-workspace-actions">' +
                (!t.done ? '<button type="button" data-aw-action="startTask" data-aw-id="' + escAttr(t.id) + '">Run</button>' : '') +
                '<button type="button" data-aw-edit-task="' + escAttr(t.id) + '">Edit</button>' +
                '<button type="button" data-aw-action="deleteTask" data-aw-id="' + escAttr(t.id) + '">Delete</button>' +
            '</div>' +
        '</div>';
    }) +
    '<div class="agent-workspace-card" style="margin-top:10px"><h3>Project Cards</h3>' +
    _agentWorkspaceItemList(projectTasks, 'No assigned project cards', function(t) {
        var blocker = t.meetingBlocker || {};
        return '<div class="agent-workspace-item agent-workspace-project-card">' +
            '<div><b>' + escHtml(t.title) + '</b></div>' +
            (t.description ? '<div class="agent-workspace-detail">' + escHtml(String(t.description).slice(0, 360)) + '</div>' : '') +
            '<div class="agent-workspace-meta">' + escHtml(_agentWorkspaceProjectMeta(t, false)) + '</div>' +
            _agentWorkspaceProjectBadges(t) +
            (blocker.status ? '<div class="agent-workspace-detail">Meeting blocker: ' + escHtml(blocker.status) + (blocker.requestId ? ' · ' + escHtml(blocker.requestId) : '') + '</div>' : '') +
            (t.lastError || t.blockedReason ? '<div class="agent-workspace-detail">' + escHtml(t.lastError || t.blockedReason) + '</div>' : '') +
        '</div>';
    }) + '</div>';
}

function _renderAgentWorkspaceFiles(data) {
    var canEdit = !data.settings || data.settings.filesApplicable !== false;
    var editor = data.fileEditor || null;
    var search = data.fileSearch || '';
    var files = data.files || [];
    if (search) {
        var q = search.toLowerCase();
        files = files.filter(function(f) {
            return String(f.path || f.name || '').toLowerCase().indexOf(q) >= 0 ||
                String(f.kind || '').toLowerCase().indexOf(q) >= 0;
        });
    }
    var html = canEdit ? '<div class="agent-workspace-files-shell">' +
        '<div class="agent-workspace-file-list-pane">' +
        '<form class="agent-workspace-form agent-workspace-file-tools" data-aw-form="file-create">' +
            '<input name="search" data-aw-file-search value="' + escAttr(search) + '" placeholder="Search files">' +
            '<input name="path" placeholder="notes/new-note.md">' +
            '<button type="submit">Create</button>' +
        '</form>' : '<div class="agent-workspace-empty">This platform does not expose editable workspace files through Virtual Office. Use Notes and Tasks for durable dashboard data.</div>';
    if (canEdit) {
        html += _agentWorkspaceItemList(files, 'No matching workspace files', function(f) {
            return '<div class="agent-workspace-item agent-workspace-file-row">' +
                '<button type="button" class="agent-workspace-file-open" data-aw-action="readFile" data-aw-path="' + escAttr(f.path || '') + '">' + escHtml(f.path || f.name) + '</button>' +
                '<div class="agent-workspace-meta">' + escHtml(f.kind || 'file') + ' · ' + escHtml(Math.ceil((f.size || 0) / 1024)) + ' KB · ' + escHtml(_formatAgentWorkspaceTime(f.modified)) + '</div>' +
                (f.path && f.kind !== 'large-text' ? '<div class="agent-workspace-actions"><button type="button" data-aw-action="readFile" data-aw-path="' + escAttr(f.path) + '">Open</button><button type="button" data-aw-action="deleteFile" data-aw-path="' + escAttr(f.path) + '">Delete</button></div>' : '') +
            '</div>';
        }) + '</div>';
    }
    if (editor) {
        html += '<form class="agent-workspace-editor agent-workspace-file-editor-pane" data-aw-form="file-save">' +
            '<div class="agent-workspace-editor-header"><input name="path" value="' + escAttr(editor.path || '') + '" readonly>' +
            '<div class="agent-workspace-actions"><button type="submit">Save</button><button type="button" data-aw-action="closeFile">Close</button></div></div>' +
            '<textarea name="content" spellcheck="false">' + escTextarea(editor.content || '') + '</textarea>' +
        '</form>';
    } else if (canEdit) {
        html += '<div class="agent-workspace-file-editor-pane agent-workspace-empty">Open a file to edit it here.</div>';
    }
    if (canEdit) html += '</div>';
    return html;
}

function _renderAgentWorkspaceSkills(data) {
    var skills = data.skills || [];
    var library = data.skillLibrary || [];
    var editor = data.skillEditor || null;
    var libraryEditor = data.librarySkillEditor || null;
    var agentSkillsAllowed = !data.settings || data.settings.agentSkillsApplicable !== false;
    return '<div class="agent-workspace-skills-shell">' +
        '<div class="agent-workspace-skill-column">' +
            '<div class="agent-workspace-panel-heading"><span>Agent Skills</span>' + (agentSkillsAllowed ? '<button type="button" data-aw-action="newAgentSkill">New</button>' : '') + '</div>' +
            (agentSkillsAllowed ? _agentWorkspaceItemList(skills, 'No skills installed for this agent', function(s) {
                return '<div class="agent-workspace-item">' +
                    '<div><b>' + escHtml(s.name) + '</b></div>' +
                    '<div class="agent-workspace-meta">' + escHtml(s.type || 'skill') + (s.description ? ' · ' + escHtml(s.description) : '') + '</div>' +
                    '<div class="agent-workspace-actions"><button type="button" data-aw-skill-edit="' + escAttr(s.name) + '">Open</button><button type="button" data-aw-action="saveAgentSkillToLibrary" data-aw-id="' + escAttr(s.name) + '">Save to Skill Library</button><button type="button" data-aw-action="deleteAgentSkill" data-aw-id="' + escAttr(s.name) + '">Delete</button></div>' +
                '</div>';
            }) : '<div class="agent-workspace-empty">This platform does not use OpenClaw workspace skills. You can still create and edit reusable skills in the library.</div>') +
        '</div>' +
        '<div class="agent-workspace-skill-column">' +
            '<div class="agent-workspace-panel-heading"><span>Skill Library</span><button type="button" data-aw-action="newLibrarySkill">New</button></div>' +
            _agentWorkspaceItemList(library, 'No library skills found', function(s) {
                return '<div class="agent-workspace-item">' +
                    '<div><b>' + escHtml(s.name) + '</b></div>' +
                    '<div class="agent-workspace-meta">' + escHtml(s.description || 'Reusable library skill') + '</div>' +
                    '<div class="agent-workspace-actions"><button type="button" data-aw-library-edit="' + escAttr(s.name) + '">Open</button>' + (agentSkillsAllowed ? '<button type="button" data-aw-action="applyLibrarySkill" data-aw-id="' + escAttr(s.name) + '">Install</button>' : '') + '</div>' +
                '</div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-skill-editor">' +
            '<div class="agent-workspace-panel-heading"><span>Skill Workshop</span><button type="button" data-aw-action="refreshSkillWorkshop">Refresh</button></div>' +
            '<div id="agent-workspace-skill-workshop-list" class="skill-workshop-list agent-workspace-workshop-list"><span style="color:#666;font-size:11px;">Loading proposals...</span></div>' +
            (editor || libraryEditor ? '<form class="agent-workspace-editor" data-aw-form="' + (libraryEditor ? 'library-skill-save' : 'agent-skill-save') + '">' +
                '<div class="agent-workspace-editor-header"><input name="name" value="' + escAttr((editor || libraryEditor).name || '') + '" placeholder="skill-name">' +
                '<button type="submit">Save</button></div>' +
                '<textarea name="content" spellcheck="false">' + escTextarea((editor || libraryEditor).content || '') + '</textarea>' +
            '</form>' : '<div class="agent-workspace-empty">Open or create a skill to edit its SKILL.md here.</div>') +
        '</div>' +
    '</div>';
}

function _renderAgentWorkspaceNotes(data) {
    var notes = (data.workspace && data.workspace.notes) || [];
    var selectedId = data.selectedNoteId || (notes[0] && notes[0].id) || '';
    var selected = notes.find(function(n) { return n.id === selectedId; }) || null;
    var byFolder = {};
    notes.forEach(function(n) {
        var folder = n.folder || 'General';
        if (!byFolder[folder]) byFolder[folder] = [];
        byFolder[folder].push(n);
    });
    return '<div class="agent-workspace-notes-app">' +
        '<aside class="agent-workspace-notes-folders">' +
            '<button type="button" data-aw-action="newNote">New Note</button>' +
            (Object.keys(byFolder).length ? Object.keys(byFolder).sort().map(function(folder) {
                return '<div class="agent-workspace-note-folder"><div class="agent-workspace-note-folder-title">' + escHtml(folder) + '</div>' +
                    byFolder[folder].map(function(n) {
                        return '<button type="button" class="agent-workspace-note-link' + (n.id === selectedId ? ' active' : '') + '" data-aw-select-note="' + escAttr(n.id) + '">' +
                            '<span>' + escHtml(n.title || 'Untitled note') + '</span><small>' + escHtml(n.kind || 'note') + '</small></button>';
                    }).join('') +
                '</div>';
            }).join('') : '<div class="agent-workspace-empty">No notes yet</div>') +
        '</aside>' +
        '<section class="agent-workspace-note-editor">' +
            '<form data-aw-form="note-save">' +
                '<input type="hidden" name="id" value="' + escAttr(selected ? selected.id : '') + '">' +
                '<div class="agent-workspace-note-title-row"><input name="title" maxlength="160" value="' + escAttr(selected ? selected.title : '') + '" placeholder="Untitled note">' +
                '<button type="submit">Save</button>' +
                (selected ? '<button type="button" data-aw-action="deleteNote" data-aw-id="' + escAttr(selected.id) + '">Delete</button>' : '') + '</div>' +
                '<div class="agent-workspace-row"><select name="folder">' + _workspaceFolderOptions(selected ? selected.folder : 'General') + '</select><input name="newFolder" maxlength="120" placeholder="New folder"><select name="kind">' +
                    ['note','list','page','group'].map(function(k) { return '<option value="' + k + '"' + (selected && selected.kind === k ? ' selected' : '') + '>' + k[0].toUpperCase() + k.slice(1) + '</option>'; }).join('') +
                '</select></div>' +
                '<textarea name="content" maxlength="50000" placeholder="Write notes, lists, pages, or grouped context">' + escTextarea(selected ? selected.content : '') + '</textarea>' +
            '</form>' +
        '</section>' +
    '</div>';
}

function _renderAgentWorkspaceSettings(data) {
    var agent = data.agent || {};
    var provider = agent.providerKind === 'hermes' ? 'Hermes' : (agent.providerKind === 'codex' ? 'Codex' : 'OpenClaw');
    var workspace = data.workspace || {};
    var settings = workspace.settings || {};
    var score = data.score || {};
    var modelEditable = !data.settings || data.settings.modelEditable !== false;
    return '<form class="agent-workspace-settings agent-workspace-settings-polished" data-aw-form="settings">' +
        '<section class="agent-workspace-settings-section"><h3>Agent</h3>' +
            '<div class="agent-workspace-settings-grid">' +
                '<label>Name<input name="name" value="' + escAttr(agent.name || '') + '" placeholder="Name"></label>' +
                '<label>Display<input name="displayName" value="' + escAttr(agent.displayName || agent.name || '') + '" placeholder="Display name"></label>' +
                '<label>Emoji<input name="emoji" value="' + escAttr(agent.emoji || '') + '" placeholder="Emoji"></label>' +
                '<label>Branch<select name="branch">' + getBranchList().map(function(b) { return '<option value="' + escAttr(b.id) + '"' + ((agent.branch || 'UNASSIGNED') === b.id ? ' selected' : '') + '>' + escHtml((b.emoji || '') + ' ' + b.name) + '</option>'; }).join('') + '</select></label>' +
                '<label class="agent-workspace-settings-span">Role<input name="role" value="' + escAttr(agent.role || '') + '" placeholder="Role"></label>' +
                '<label>Points<input name="leaderboardPoints" type="number" value="' + escAttr(settings.leaderboardPoints || score.score || 0) + '"></label>' +
            '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(agent.statusKey || agent.id || '') + ' · completed ' + escHtml(score.completed || 0) + ' · streak ' + escHtml(score.streak || 0) + '</div>' +
        '</section>' +
        '<section class="agent-workspace-settings-section"><h3>Runtime</h3>' +
            '<div class="agent-workspace-settings-grid">' +
                (modelEditable ? '<label class="agent-workspace-settings-span">Model<select name="model" id="agent-workspace-model-select"><option value="">Loading models...</option></select></label>' : '<label class="agent-workspace-settings-span">Model<input name="model" value="' + escAttr(agent.model || agent.provider || (provider + ' managed')) + '" readonly></label>') +
                '<label class="agent-workspace-checkbox"><input type="checkbox" name="cronEnabled"' + (settings.cronEnabled ? ' checked' : '') + (data.settings && data.settings.cronApplicable ? '' : ' disabled') + '> Cron enabled</label>' +
            '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(provider) + ' · current ' + escHtml(agent.model || agent.provider || 'default') + ' · ' + (data.settings && data.settings.cronApplicable ? 'OpenClaw cron supported' : 'Cron not surfaced for this platform') + '</div>' +
        '</section>' +
        '<section class="agent-workspace-settings-section"><h3>Heartbeat</h3>' +
            (data.settings && data.settings.heartbeatApplicable ? '<textarea name="heartbeatContent" spellcheck="false">' + escTextarea(data.settings.heartbeatContent || '') + '</textarea>' : '<div class="agent-workspace-item">Not applicable<div class="agent-workspace-meta">This platform does not use OpenClaw HEARTBEAT.md.</div></div>') +
        '</section>' +
        '<div class="agent-workspace-settings-footer"><button class="agent-workspace-action" type="submit">Save Settings</button><span id="agent-workspace-settings-status" class="agent-workspace-meta"></span></div>' +
    '</form>';
}

function _renderAgentWorkspace() {
    var body = document.getElementById('agent-workspace-body');
    var data = _agentWorkspace.data;
    if (!body) return;
    document.querySelectorAll('.agent-workspace-tabs button').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.awTab === _agentWorkspace.activeTab);
    });
    if (_agentWorkspace.loading) {
    body.innerHTML = '<div class="agent-workspace-empty">' + escHtml(_tr('loading_workspace')) + '</div>';
        return;
    }
    if (!data || !data.ok) {
            body.innerHTML = '<div class="agent-workspace-empty">' + escHtml((data && data.error) || _tr('workspace_unavailable')) + '</div>';
        return;
    }
    if (_agentWorkspace.activeTab === 'bulletin') body.innerHTML = _renderAgentWorkspaceBulletin(data);
    else if (_agentWorkspace.activeTab === 'tasks') body.innerHTML = _renderAgentWorkspaceTasks(data);
    else if (_agentWorkspace.activeTab === 'files') body.innerHTML = _renderAgentWorkspaceFiles(data);
    else if (_agentWorkspace.activeTab === 'skills') body.innerHTML = _renderAgentWorkspaceSkills(data);
    else if (_agentWorkspace.activeTab === 'notes') body.innerHTML = _renderAgentWorkspaceNotes(data);
    else if (_agentWorkspace.activeTab === 'settings') body.innerHTML = _renderAgentWorkspaceSettings(data);
    else body.innerHTML = _renderAgentWorkspaceOverview(data);
    if (_agentWorkspace.activeTab === 'settings' && (!data.settings || data.settings.modelEditable !== false)) _populateAgentWorkspaceModels(data);
    if (_agentWorkspace.activeTab === 'skills') {
        renderSkillWorkshopQueue();
        if (!_skillWorkshopLoaded && !_skillWorkshopLoading) refreshSkillWorkshopQueue();
    }
}

async function _loadAgentWorkspace(agent) {
    var key = _agentWorkspaceKey(agent);
    if (!key) return;
    _agentWorkspace.loading = true;
    _renderAgentWorkspace();
    try {
        var res = await fetch('/api/agent-workspace/' + encodeURIComponent(key), { cache: 'no-store' });
        _agentWorkspace.data = await res.json();
    } catch (e) {
        _agentWorkspace.data = { ok: false, error: e.message || String(e) };
    }
    _agentWorkspace.loading = false;
    _renderAgentWorkspace();
}

async function _populateAgentWorkspaceModels(data) {
    var select = document.getElementById('agent-workspace-model-select');
    if (!select || select.dataset.loaded === '1') return;
    try {
        var res = await fetch('/api/native-models', { cache: 'no-store' });
        var nativeModels = await res.json();
        var models = nativeModels.openclaw || {};
        var agentKey = data.agent && data.agent.statusKey;
        var current = (agentKey && models.agents && models.agents[agentKey] && models.agents[agentKey].model) || (data.agent && data.agent.model) || models.defaultModel || '';
        var html = '<option value="">Use default</option>';
        var grouped = {};
        (models.models || []).forEach(function(m) {
            if (m.missing) return;
            var provider = m.provider || (m.id && m.id.split('/')[0]) || 'Models';
            if (!grouped[provider]) grouped[provider] = [];
            grouped[provider].push(m);
        });
        Object.keys(grouped).sort().forEach(function(provider) {
            html += '<optgroup label="' + escAttr(provider) + '">';
            grouped[provider].sort(function(a, b) { return String(a.id || '').localeCompare(String(b.id || '')); }).forEach(function(m) {
                var label = (m.name && m.name !== m.id) ? (m.id + ' · ' + m.name) : m.id;
                html += '<option value="' + escAttr(m.id) + '"' + (m.id === current ? ' selected' : '') + '>' + escHtml(label) + '</option>';
            });
            html += '</optgroup>';
        });
        select.innerHTML = html;
        select.value = current || '';
        select.dataset.loaded = '1';
    } catch (e) {
        select.innerHTML = '<option value="">' + escHtml(_tr('model_list_unavailable')) + '</option>';
    }
}

async function _agentWorkspacePost(action, payload) {
    var agent = _agentWorkspace.agent;
    var key = _agentWorkspaceKey(agent);
    if (!key) return;
    var body = Object.assign({ action: action, actor: 'user' }, payload || {});
    var res = await fetch('/api/agent-workspace/' + encodeURIComponent(key), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    var json = await res.json();
    if (action === 'readFile' && json.ok && json.file) {
        if (_agentWorkspace.data) _agentWorkspace.data.fileEditor = json.file;
    } else {
        _agentWorkspace.data = json;
    }
    _renderAgentWorkspace();
    return json;
}

async function _agentWorkspaceSetModel(model) {
    var agent = _agentWorkspace.agent;
    var key = _agentWorkspaceKey(agent);
    if (!key) return { ok: false, error: 'No agent selected' };
    var res = await fetch('/api/native-models/openclaw/agent-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent: key, model: model || '' })
    });
    return await res.json();
}

function _findWorkspaceTask(id) {
    return (((_agentWorkspace.data || {}).workspace || {}).tasks || []).find(function(t) { return t.id === id; });
}

function _findWorkspaceNote(id) {
    return (((_agentWorkspace.data || {}).workspace || {}).notes || []).find(function(n) { return n.id === id; });
}

function _findAgentSkill(name) {
    return (((_agentWorkspace.data || {}).skills) || []).find(function(s) { return s.name === name; });
}

async function _openLibrarySkill(name) {
    try {
        var res = await fetch('/api/skills-library/' + encodeURIComponent(name), { cache: 'no-store' });
        var data = await res.json();
        if (!_agentWorkspace.data) return;
        _agentWorkspace.data.librarySkillEditor = { name: data.skill || data.name || name, content: data.content || '' };
        delete _agentWorkspace.data.skillEditor;
        _renderAgentWorkspace();
    } catch (e) {
        if (_agentWorkspace.data) _agentWorkspace.data.librarySkillEditor = { name: name, content: '' };
        _renderAgentWorkspace();
    }
}

function _openAgentWorkspace(agent, deskItem) {
    var panel = document.getElementById('agent-workspace-panel');
    if (!panel || !agent) return;
    _hideAgentWorkspaceMenu();
    _agentWorkspace.agent = agent;
    _agentWorkspace.desk = deskItem || null;
    document.getElementById('agent-workspace-emoji').textContent = agent.emoji || '🤖';
    document.getElementById('agent-workspace-name').textContent = agent.name || 'Agent Workspace';
    var provider = agent.providerKind === 'hermes' ? 'Hermes' : (agent.providerKind === 'codex' ? 'Codex' : 'OpenClaw');
    document.getElementById('agent-workspace-subtitle').textContent = provider + ' · ' + (agent.role || agent.statusKey || agent.id || 'Workspace');
    panel.classList.remove('hidden');
    if (!panel.style.left && !panel.style.right) {
        panel.style.right = '24px';
        panel.style.top = '48px';
    }
    _loadAgentWorkspace(agent);
}

function _clampAgentWorkspacePanel() {
    var panel = document.getElementById('agent-workspace-panel');
    if (!panel || panel.classList.contains('hidden') || panel.classList.contains('maximized')) return;
    var rect = panel.getBoundingClientRect();
    var left = Math.max(0, Math.min(window.innerWidth - Math.min(80, rect.width), rect.left));
    var top = Math.max(0, Math.min(window.innerHeight - Math.min(80, rect.height), rect.top));
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
    panel.style.right = 'auto';
}

function _initAgentWorkspaceUI() {
    var menuBtn = document.getElementById('agent-workspace-open-btn');
    var panel = document.getElementById('agent-workspace-panel');
    var closeBtn = document.getElementById('agent-workspace-close');
    var refreshBtn = document.getElementById('agent-workspace-refresh');
    var maxBtn = document.getElementById('agent-workspace-maximize');
    var header = document.getElementById('agent-workspace-drag-handle');
    var body = document.getElementById('agent-workspace-body');
    var resizeHandle = panel ? panel.querySelector('.agent-workspace-resize-handle') : null;

    if (menuBtn) menuBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        _openAgentWorkspace(_agentWorkspace.agent, _agentWorkspace.desk);
    });
    if (closeBtn) closeBtn.addEventListener('click', function() { panel.classList.add('hidden'); });
    if (refreshBtn) refreshBtn.addEventListener('click', function() { if (_agentWorkspace.agent) _loadAgentWorkspace(_agentWorkspace.agent); });
    if (maxBtn) maxBtn.addEventListener('click', function() {
        if (!panel) return;
        panel.classList.toggle('maximized');
        maxBtn.textContent = panel.classList.contains('maximized') ? '▣' : '□';
    });
    document.querySelectorAll('.agent-workspace-tabs button').forEach(function(btn) {
        btn.addEventListener('click', function() {
            _agentWorkspace.activeTab = btn.dataset.awTab || 'overview';
            _renderAgentWorkspace();
        });
    });
    if (body) {
        body.addEventListener('submit', function(e) {
            var form = e.target.closest('[data-aw-form]');
            if (!form) return;
            e.preventDefault();
            if (form.dataset.awForm === 'bulletin') {
                var text = form.elements.text.value.trim();
                if (text) _agentWorkspacePost('addBulletin', { text: text });
            } else if (form.dataset.awForm === 'task') {
                var taskText = form.elements.text.value.trim();
                var due = form.elements.due.value.trim();
                var detail = form.elements.detail.value.trim();
                var priority = form.elements.priority.value;
                if (taskText) _agentWorkspacePost('addTask', { text: taskText, due: due, detail: detail, priority: priority });
            } else if (form.dataset.awForm === 'file-create') {
                var path = form.elements.path.value.trim();
                if (path) _agentWorkspacePost('createFile', { path: path, content: '# ' + path.split('/').pop().replace(/\.[^.]+$/, '') + '\n' });
            } else if (form.dataset.awForm === 'file-save') {
                _agentWorkspacePost('saveFile', { path: form.elements.path.value, content: form.elements.content.value });
            } else if (form.dataset.awForm === 'note') {
                var folder = form.elements.newFolder.value.trim() || form.elements.folder.value || 'General';
                var tags = [];
                if (form.elements.tags && form.elements.tags.value) tags = form.elements.tags.value.split(',');
                var title = form.elements.title.value.trim();
                if (title || form.elements.content.value.trim()) _agentWorkspacePost('addNote', { title: title || 'Untitled note', folder: folder, kind: form.elements.kind.value, content: form.elements.content.value, tags: tags });
            } else if (form.dataset.awForm === 'note-save') {
                var noteFolder = form.elements.newFolder.value.trim() || form.elements.folder.value || 'General';
                var notePayload = { title: form.elements.title.value || 'Untitled note', folder: noteFolder, kind: form.elements.kind.value, content: form.elements.content.value, tags: [] };
                if (form.elements.id.value) _agentWorkspacePost('updateNote', Object.assign({ id: form.elements.id.value }, notePayload));
                else _agentWorkspacePost('addNote', notePayload);
            } else if (form.dataset.awForm === 'agent-skill-save') {
                _agentWorkspacePost('saveAgentSkill', { name: form.elements.name.value, content: form.elements.content.value });
            } else if (form.dataset.awForm === 'library-skill-save') {
                _agentWorkspacePost('saveLibrarySkill', { name: form.elements.name.value, content: form.elements.content.value });
            } else if (form.dataset.awForm === 'settings') {
                var payload = {
                    name: form.elements.name.value,
                    displayName: form.elements.displayName.value,
                    role: form.elements.role.value,
                    branch: form.elements.branch.value,
                    emoji: form.elements.emoji.value,
                    leaderboardPoints: Number(form.elements.leaderboardPoints.value || 0),
                    cronEnabled: !!(form.elements.cronEnabled && form.elements.cronEnabled.checked)
                };
                if (form.elements.heartbeatContent) payload.heartbeatContent = form.elements.heartbeatContent.value;
                var currentData = _agentWorkspace.data || {};
                var canSetModel = currentData.settings && currentData.settings.modelEditable !== false;
                var selectedModel = canSetModel && form.elements.model ? form.elements.model.value : '';
                Promise.resolve(_agentWorkspacePost('updateSettings', payload)).then(function() {
                    return canSetModel ? _agentWorkspaceSetModel(selectedModel) : { ok: true };
                }).then(function(result) {
                    var status = document.getElementById('agent-workspace-settings-status');
                    if (status) status.textContent = result && result.ok === false ? (result.error || 'Model not changed') : 'Saved';
                    _fetchRoster();
                });
            }
        });
        body.addEventListener('click', function(e) {
            var target = e.target.closest('[data-aw-action]');
            var editTask = e.target.closest('[data-aw-edit-task]');
            var editNote = e.target.closest('[data-aw-edit-note]');
            var skillEdit = e.target.closest('[data-aw-skill-edit]');
            var libraryEdit = e.target.closest('[data-aw-library-edit]');
            var selectNote = e.target.closest('[data-aw-select-note]');
            if (selectNote) {
                if (_agentWorkspace.data) _agentWorkspace.data.selectedNoteId = selectNote.dataset.awSelectNote;
                _renderAgentWorkspace();
                return;
            }
            if (skillEdit) {
                var skill = _findAgentSkill(skillEdit.dataset.awSkillEdit);
                if (!_agentWorkspace.data || !skill) return;
                _agentWorkspace.data.skillEditor = { name: skill.name, content: skill.content || '' };
                delete _agentWorkspace.data.librarySkillEditor;
                _renderAgentWorkspace();
                return;
            }
            if (libraryEdit) {
                _openLibrarySkill(libraryEdit.dataset.awLibraryEdit);
                return;
            }
            if (editTask) {
                var task = _findWorkspaceTask(editTask.dataset.awEditTask);
                if (!task) return;
    var text = prompt(_tr('task_title_prompt'), task.text || '');
                if (text == null) return;
    var detail = prompt(_tr('task_details_prompt'), task.detail || '');
                if (detail == null) return;
                _agentWorkspacePost('updateTask', { id: task.id, text: text, detail: detail, due: task.due || '', priority: task.priority || 'normal' });
                return;
            }
            if (editNote) {
                var note = _findWorkspaceNote(editNote.dataset.awEditNote);
                if (!note) return;
    var title = prompt(_tr('note_title_prompt'), note.title || '');
                if (title == null) return;
    var content = prompt(_tr('note_content_prompt'), note.content || '');
                if (content == null) return;
                _agentWorkspacePost('updateNote', { id: note.id, title: title, content: content, folder: note.folder || 'General', kind: note.kind || 'note', tags: note.tags || [] });
                return;
            }
            if (!target) return;
            var action = target.dataset.awAction;
            var id = target.dataset.awId;
            if (action === 'deleteBulletin') _agentWorkspacePost('deleteBulletin', { id: id });
            if (action === 'deleteTask') _agentWorkspacePost('deleteTask', { id: id });
            if (action === 'startTask') _agentWorkspacePost('startTask', { id: id });
            if (action === 'completeTask') _agentWorkspacePost('completeTask', { id: id });
            if (action === 'deleteNote') _agentWorkspacePost('deleteNote', { id: id });
            if (action === 'readFile') {
                _agentWorkspacePost('readFile', { path: target.dataset.awPath }).then(function() {
                    if (_agentWorkspace.data && _agentWorkspace.data.file) _agentWorkspace.data.fileEditor = _agentWorkspace.data.file;
                    _renderAgentWorkspace();
                });
            }
            if (action === 'deleteFile') {
    if (confirm(_tr('delete_path_confirm', { path: target.dataset.awPath }))) _agentWorkspacePost('deleteFile', { path: target.dataset.awPath });
            }
            if (action === 'closeFile') {
                if (_agentWorkspace.data) delete _agentWorkspace.data.fileEditor;
                _renderAgentWorkspace();
            }
            if (action === 'newNote') {
                if (_agentWorkspace.data) _agentWorkspace.data.selectedNoteId = '';
                _renderAgentWorkspace();
            }
            if (action === 'newAgentSkill') {
                if (_agentWorkspace.data) {
                    _agentWorkspace.data.skillEditor = { name: 'new-skill', content: '---\\nname: new-skill\\ndescription: \"Agent workflow skill.\"\\n---\\n\\n# New Skill\\n\\nUse this skill when...\\n' };
                    delete _agentWorkspace.data.librarySkillEditor;
                }
                _renderAgentWorkspace();
            }
            if (action === 'newLibrarySkill') {
                if (_agentWorkspace.data) {
                    _agentWorkspace.data.librarySkillEditor = { name: 'new-library-skill', content: '---\\nname: new-library-skill\\ndescription: \"Reusable Virtual Office skill.\"\\n---\\n\\n# New Library Skill\\n\\nUse this skill when...\\n' };
                    delete _agentWorkspace.data.skillEditor;
                }
                _renderAgentWorkspace();
            }
            if (action === 'deleteAgentSkill') {
    if (confirm(_tr('delete_skill_confirm', { name: id }))) _agentWorkspacePost('deleteAgentSkill', { name: id });
            }
            if (action === 'applyLibrarySkill') {
                _agentWorkspacePost('applyLibrarySkill', { name: id, overwrite: true });
            }
            if (action === 'refreshSkillWorkshop') {
                refreshSkillWorkshopQueue();
            }
            if (action === 'saveAgentSkillToLibrary') {
                var workspaceAgent = (_agentWorkspace.data && _agentWorkspace.data.agent) || _agentWorkspace.agent || {};
                var workspaceAgentKey = _agentWorkspaceKey(workspaceAgent);
                saveAgentSkillToLibrary(workspaceAgentKey, id, function() {
                    if (_agentWorkspace.agent) _loadAgentWorkspace(_agentWorkspace.agent);
                });
            }
        });
        body.addEventListener('input', function(e) {
            var search = e.target.closest('[data-aw-file-search]');
            if (!search || !_agentWorkspace.data) return;
            _agentWorkspace.data.fileSearch = search.value;
            clearTimeout(_agentWorkspace.fileSearchTimer);
            _agentWorkspace.fileSearchTimer = setTimeout(_renderAgentWorkspace, 120);
        });
        body.addEventListener('change', function(e) {
            var target = e.target.closest('[data-aw-action="toggleTask"]');
            if (target) _agentWorkspacePost('toggleTask', { id: target.dataset.awId });
            var mode = e.target.closest('[data-aw-action="setTaskMode"]');
            if (mode) _agentWorkspacePost('setTaskMode', { mode: mode.value });
        });
    }
    if (header) {
        header.addEventListener('pointerdown', function(e) {
            if (!panel || panel.classList.contains('maximized') || e.target.closest('button')) return;
            var rect = panel.getBoundingClientRect();
            panel.style.left = rect.left + 'px';
            panel.style.top = rect.top + 'px';
            panel.style.right = 'auto';
            _agentWorkspace.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, left: rect.left, top: rect.top };
            header.setPointerCapture(e.pointerId);
        });
    }
    if (resizeHandle) {
        resizeHandle.addEventListener('pointerdown', function(e) {
            if (!panel || panel.classList.contains('maximized')) return;
            e.preventDefault();
            var rect = panel.getBoundingClientRect();
            _agentWorkspace.resize = { id: e.pointerId, x: e.clientX, y: e.clientY, w: rect.width, h: rect.height };
            resizeHandle.setPointerCapture(e.pointerId);
        });
    }
    document.addEventListener('pointermove', function(e) {
        if (_agentWorkspace.drag && panel) {
            var d = _agentWorkspace.drag;
            panel.style.left = (d.left + e.clientX - d.x) + 'px';
            panel.style.top = (d.top + e.clientY - d.y) + 'px';
            _clampAgentWorkspacePanel();
        }
        if (_agentWorkspace.resize && panel) {
            var r = _agentWorkspace.resize;
            panel.style.width = Math.max(360, Math.min(window.innerWidth - 16, r.w + e.clientX - r.x)) + 'px';
            panel.style.height = Math.max(320, Math.min(window.innerHeight - 16, r.h + e.clientY - r.y)) + 'px';
        }
    });
    document.addEventListener('pointerup', function() {
        _agentWorkspace.drag = null;
        _agentWorkspace.resize = null;
    });
    document.addEventListener('click', function(e) {
        var menu = document.getElementById('agent-workspace-menu');
        if (menu && !menu.classList.contains('hidden') && !menu.contains(e.target)) _hideAgentWorkspaceMenu();
    });
    window.addEventListener('resize', _clampAgentWorkspacePanel);
}

_initAgentWorkspaceUI();

async function clearNotifyOnServer(statusKey) {
    try {
        await fetch('/clear-notify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent: statusKey })
        });
    } catch(e) { /* best effort */ }
}

function closeModal() {
    document.getElementById('agentModal').classList.add('hidden');
    selectedAgent = null;
}

function overrideAgent(state) {
    if (selectedAgent) {
        selectedAgent.moveTo(state);
        addGlobalLog(`🎮 Override: ${selectedAgent.name} → ${state}`);
        closeModal();
    }
}

function setGlobalState(state) {
    agents.forEach(agent => agent.moveTo(state));
    addGlobalLog(`🎮 All agents → ${state}`);
}

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

// ============================================================
// PAPER AIRPLANE SYSTEM — idle fun between agents
// ============================================================
const paperAirplanes = [];
const AIRPLANE_SPEED = 2.5;

function launchAirplane(fromAgent, toAgent) {
    paperAirplanes.push({
        x: fromAgent.x, y: fromAgent.y - 30,
        startX: fromAgent.x, startY: fromAgent.y - 30,
        endX: toAgent.x, endY: toAgent.y - 30,
        progress: 0,
        fromId: fromAgent.id,
        toId: toAgent.id,
        wobble: Math.random() * Math.PI * 2,
        caught: false,
        catchTimer: 0,
    });
    fromAgent.addIntent(`Threw a paper airplane at ${toAgent.name}!`);
    // Throw arm animation — briefly set talk timer to animate
    fromAgent.faceDir = toAgent.x > fromAgent.x ? 1 : -1;
}

function updateAirplanes() {
    for (let i = paperAirplanes.length - 1; i >= 0; i--) {
        const p = paperAirplanes[i];
        if (!p.caught) {
            p.progress += 0.005;
            // Bezier-like arc path
            const t = p.progress;
            const arcHeight = -60 * Math.sin(t * Math.PI); // parabolic arc
            p.x = p.startX + (p.endX - p.startX) * t;
            p.y = p.startY + (p.endY - p.startY) * t + arcHeight;
            p.wobble += 0.08;

            if (t >= 1) {
                p.caught = true;
                p.catchTimer = 90; // frames to show catch reaction
                // Target reacts
                const target = agentMap[p.toId];
                if (target) {
                    target.addIntent('Caught a paper airplane!');
                    target.faceDir = p.startX > target.x ? 1 : -1;
                    target.talkTimer = 40;
                }
            }
        } else {
            p.catchTimer--;
            if (p.catchTimer <= 0) {
                paperAirplanes.splice(i, 1);
            }
        }
    }
}

function drawAirplanes() {
    for (let i = 0; i < paperAirplanes.length; i++) {
        const p = paperAirplanes[i];
        if (p.caught) {
            // Show caught airplane in target's hand briefly
            const target = agentMap[p.toId];
            if (target && p.catchTimer > 60) {
                ctx.save();
                ctx.translate(target.x + target.faceDir * 10, target.y - 28);
                ctx.fillStyle = '#fff';
                ctx.fillRect(-3, -1, 6, 3);
                ctx.fillRect(-1, -3, 2, 6);
                ctx.restore();
            }
            continue;
        }
        ctx.save();
        ctx.translate(p.x, p.y);
        // Rotate airplane based on flight direction + wobble
        const dx = p.endX - p.startX;
        const angle = Math.atan2(p.endY - p.startY, dx) + Math.sin(p.wobble) * 0.15;
        const flip = dx < 0 ? -1 : 1;
        ctx.scale(flip, 1);
        ctx.rotate(angle * flip);
        // Paper airplane 2D drawing
        ctx.fillStyle = '#fff';
        // Fuselage
        ctx.fillRect(-6, -1, 12, 2);
        // Wings
        ctx.fillStyle = '#f5f5f5';
        ctx.beginPath();
        ctx.moveTo(-4, -1);
        ctx.lineTo(2, -6);
        ctx.lineTo(6, -1);
        ctx.closePath();
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(-4, 1);
        ctx.lineTo(2, 5);
        ctx.lineTo(6, 1);
        ctx.closePath();
        ctx.fill();
        // Nose
        ctx.fillStyle = '#e0e0e0';
        ctx.fillRect(5, -1, 2, 2);
        // Shadow on ground (faint)
        ctx.restore();
        // Ground shadow
        ctx.fillStyle = 'rgba(0,0,0,0.08)';
        const shadowY = Math.min(p.startY, p.endY) + 60;
        ctx.fillRect(p.x - 4, shadowY, 8, 3);
    }
}

// Check if an agent should throw an airplane (called in update loop)
function maybeThrowAirplane(agent) {
    // Only idle sitting agents, ~0.15% chance per frame (~once every 40-60s per agent)
    if (agent.state !== 'idle' || !agent.isSitting || agent.idleAction) return;
    if (Math.random() > 0.000015) return;
    // Don't stack — max 2 airplanes in flight
    if (paperAirplanes.length >= 2) return;
    // Don't throw if this agent already has one in flight
    if (paperAirplanes.some(p => p.fromId === agent.id || p.toId === agent.id)) return;
    // Pick a random other idle agent at their desk
    const targets = agents.filter(a => a.id !== agent.id && a.isSitting && !a.idleAction && a.state === 'idle');
    if (targets.length === 0) return;
    const target = targets[Math.floor(Math.random() * targets.length)];
    launchAirplane(agent, target);
}

// ============================================================
// ROCK-PAPER-SCISSORS — triggered when 2 idle agents are close
// ============================================================
const rpsGames = [];
const RPS_CHOICES = ['rock', 'paper', 'scissors'];

function startRPS(agent1, agent2) {
    // Don't start if either is already in a game
    if (rpsGames.some(g => [g.p1, g.p2].includes(agent1.id) || [g.p1, g.p2].includes(agent2.id))) return;
    rpsGames.push({
        p1: agent1.id, p2: agent2.id,
        phase: 'shake',    // shake → reveal → react → done
        timer: 0,
        shakeCount: 0,
        c1: RPS_CHOICES[Math.floor(Math.random() * 3)],
        c2: RPS_CHOICES[Math.floor(Math.random() * 3)],
        winner: null,       // set on reveal
    });
    agent1.faceDir = agent2.x > agent1.x ? 1 : -1;
    agent2.faceDir = agent1.x > agent2.x ? 1 : -1;
    agent1.addIntent('Playing rock-paper-scissors!');
    agent2.addIntent('Playing rock-paper-scissors!');
}

function rpsWinner(c1, c2) {
    if (c1 === c2) return 0; // draw
    if ((c1 === 'rock' && c2 === 'scissors') || (c1 === 'scissors' && c2 === 'paper') || (c1 === 'paper' && c2 === 'rock')) return 1;
    return 2;
}

function updateRPS() {
    for (let i = rpsGames.length - 1; i >= 0; i--) {
        const g = rpsGames[i];
        g.timer++;
        if (g.phase === 'shake') {
            // 3 shakes, each 25 frames
            if (g.timer % 25 === 0) g.shakeCount++;
            if (g.shakeCount >= 3) { g.phase = 'reveal'; g.timer = 0; g.winner = rpsWinner(g.c1, g.c2); }
        } else if (g.phase === 'reveal') {
            // Show choices for 90 frames
            if (g.timer >= 90) {
                g.phase = 'react'; g.timer = 0;
                const p1 = agentMap[g.p1], p2 = agentMap[g.p2];
                if (g.winner === 1 && p1) p1.addIntent('Won rock-paper-scissors! 🎉');
                if (g.winner === 2 && p2) p2.addIntent('Won rock-paper-scissors! 🎉');
                if (g.winner === 0) { if (p1) p1.addIntent("Draw! 🤝"); }
            }
        } else if (g.phase === 'react') {
            // Reaction for 60 frames then cleanup
            if (g.timer >= 60) { rpsGames.splice(i, 1); }
        }
    }
}

function drawRPSHand(x, y, choice, shakePhase, faceDir) {
    // x, y = agent position, draw hand extended toward opponent
    const hx = x + faceDir * 16;
    const hy = y - 26;
    const bob = shakePhase !== null ? Math.sin(shakePhase * 0.25) * 4 : 0;

    ctx.save();
    ctx.translate(hx, hy + bob);

    if (choice === null) {
        // Fist during shake (closed hand)
        ctx.fillStyle = '#ffcc80';
        ctx.fillRect(-3, -3, 7, 8);
        ctx.fillStyle = '#f0b860';
        ctx.fillRect(-2, -2, 5, 2); // knuckle line
    } else if (choice === 'rock') {
        // Fist
        ctx.fillStyle = '#ffcc80';
        ctx.fillRect(-3, -3, 7, 8);
        ctx.fillStyle = '#f0b860';
        ctx.fillRect(-2, -2, 5, 2);
    } else if (choice === 'paper') {
        // Open hand (flat)
        ctx.fillStyle = '#ffcc80';
        ctx.fillRect(-4, -5, 9, 10);
        // Fingers
        ctx.fillRect(-4, -7, 2, 3);
        ctx.fillRect(-1, -8, 2, 3);
        ctx.fillRect(2, -7, 2, 3);
        ctx.fillRect(5, -5, 2, 3);
    } else if (choice === 'scissors') {
        // Two fingers out (V shape)
        ctx.fillStyle = '#ffcc80';
        ctx.fillRect(-2, -2, 5, 7);
        // Two extended fingers
        ctx.fillRect(-3, -8, 2, 7);
        ctx.fillRect(2, -8, 2, 7);
        // Curled fingers
        ctx.fillStyle = '#f0b860';
        ctx.fillRect(-1, -1, 3, 2);
    }
    ctx.restore();
}

function drawRPS() {
    for (let i = 0; i < rpsGames.length; i++) {
        const g = rpsGames[i];
        const p1 = agentMap[g.p1], p2 = agentMap[g.p2];
        if (!p1 || !p2) continue;

        if (g.phase === 'shake') {
            // Both show fists bobbing
            drawRPSHand(p1.x, p1.y, null, g.timer, p1.faceDir);
            drawRPSHand(p2.x, p2.y, null, g.timer, p2.faceDir);
            // "..." above them during shake
            ctx.fillStyle = '#fff';
            ctx.font = '8px Arial';
            ctx.textAlign = 'center';
            const dots = '.'.repeat((g.shakeCount % 3) + 1);
            ctx.fillText(dots, p1.x, p1.y - 55);
            ctx.fillText(dots, p2.x, p2.y - 55);
        } else if (g.phase === 'reveal') {
            // Show actual choices
            drawRPSHand(p1.x, p1.y, g.c1, null, p1.faceDir);
            drawRPSHand(p2.x, p2.y, g.c2, null, p2.faceDir);
            // Labels above hands
            ctx.fillStyle = '#ffd700';
            ctx.font = 'bold 7px Arial';
            ctx.textAlign = 'center';
            const emoji = { rock: '✊', paper: '✋', scissors: '✌️' };
            ctx.fillText(emoji[g.c1], p1.x + p1.faceDir * 16, p1.y - 42);
            ctx.fillText(emoji[g.c2], p2.x + p2.faceDir * 16, p2.y - 42);
        } else if (g.phase === 'react') {
            // Winner hops, loser shrugs
            if (g.winner === 1) {
                // p1 hops
                const hopY = -Math.abs(Math.sin(g.timer * 0.15)) * 4;
                ctx.fillStyle = '#ffd700'; ctx.font = '10px Arial'; ctx.textAlign = 'center';
                ctx.fillText('🎉', p1.x, p1.y - 58 + hopY);
            } else if (g.winner === 2) {
                const hopY = -Math.abs(Math.sin(g.timer * 0.15)) * 4;
                ctx.fillStyle = '#ffd700'; ctx.font = '10px Arial'; ctx.textAlign = 'center';
                ctx.fillText('🎉', p2.x, p2.y - 58 + hopY);
            } else {
                // Draw — both shrug
                ctx.fillStyle = '#fff'; ctx.font = '9px Arial'; ctx.textAlign = 'center';
                ctx.fillText('🤝', (p1.x + p2.x) / 2, Math.min(p1.y, p2.y) - 55);
            }
        }
    }
}

// Trigger RPS from social proximity (called per agent in update)
function maybeStartRPS(agent) {
    if (!agent.socialTarget) return;
    if (agent.id > agent.socialTarget) return; // only one agent triggers (alphabetical order prevents double)
    if (Math.random() > 0.003) return; // ~0.3% per frame when near someone
    if (rpsGames.length >= 2) return; // max 2 games at a time
    const other = agentMap[agent.socialTarget];
    if (!other) return;
    // Allow RPS if one is visiting the other's desk
    const visiting = agent.idleAction === 'visit' || other.idleAction === 'visit';
    if (!visiting && other.isSitting) return;
    startRPS(agent, other);
}

// ============================================================
// SOCIAL INTERACTIONS — joke, laugh, talk between nearby agents
// ============================================================
const socialInteractions = [];
const SOCIAL_TYPES = ['joke', 'laugh', 'talk'];

function startSocialInteraction(agent1, agent2) {
    if (socialInteractions.some(s => [s.p1, s.p2].includes(agent1.id) || [s.p1, s.p2].includes(agent2.id))) return;
    if (rpsGames.some(g => [g.p1, g.p2].includes(agent1.id) || [g.p1, g.p2].includes(agent2.id))) return;
    const type = SOCIAL_TYPES[Math.floor(Math.random() * SOCIAL_TYPES.length)];
    socialInteractions.push({
        p1: agent1.id, p2: agent2.id,
        type: type,
        timer: 0,
        duration: type === 'joke' ? 180 : type === 'laugh' ? 120 : 150,
        phase: 0, // used for multi-phase animations
    });
    agent1.faceDir = agent2.x > agent1.x ? 1 : -1;
    agent2.faceDir = agent1.x > agent2.x ? 1 : -1;
}

function updateSocialInteractions() {
    for (let i = socialInteractions.length - 1; i >= 0; i--) {
        const s = socialInteractions[i];
        s.timer++;
        if (s.timer >= s.duration) {
            socialInteractions.splice(i, 1);
        }
    }
}

function drawSocialInteractions() {
    for (let i = 0; i < socialInteractions.length; i++) {
        const s = socialInteractions[i];
        const p1 = agentMap[s.p1], p2 = agentMap[s.p2];
        if (!p1 || !p2) continue;

        const t = s.timer;

        if (s.type === 'joke') {
            // Phase 1: p1 tells joke (0-100), Phase 2: p2 laughs (100-180)
            if (t < 100) {
                // P1 talking — speech lines
                const bob = Math.sin(t * 0.3) * 1;
                ctx.fillStyle = '#fff';
                ctx.font = '7px Arial'; ctx.textAlign = 'center';
                ctx.fillText('🗣️', p1.x, p1.y - 55 + bob);
                // P1 mouth: open-close rapidly (talking)
                p1._socialMouth = Math.floor(t / 6) % 2 === 0 ? 'open' : 'closed';
                p2._socialMouth = 'smile';
            } else {
                // P2 laughing
                const shake = Math.sin(t * 0.5) * 2;
                ctx.fillStyle = '#ffd700';
                ctx.font = '9px Arial'; ctx.textAlign = 'center';
                ctx.fillText('😂', p2.x + shake, p2.y - 55);
                // Small ha ha text
                if (t % 30 < 15) {
                    ctx.fillStyle = '#fff'; ctx.font = '6px Arial';
                    ctx.fillText('ha', p2.x + 12, p2.y - 48 + Math.sin(t * 0.2) * 3);
                }
                p2._socialMouth = 'laugh';
                p1._socialMouth = 'smile';
            }
        } else if (s.type === 'laugh') {
            // Both laugh together
            const shake1 = Math.sin(t * 0.5) * 2;
            const shake2 = Math.cos(t * 0.5) * 2;
            ctx.fillStyle = '#ffd700';
            ctx.font = '9px Arial'; ctx.textAlign = 'center';
            ctx.fillText('😄', p1.x + shake1, p1.y - 55);
            ctx.fillText('😄', p2.x + shake2, p2.y - 55);
            // Both mouths wide open laughing
            p1._socialMouth = 'laugh';
            p2._socialMouth = 'laugh';
            // Shared laughter lines
            const mx = (p1.x + p2.x) / 2;
            const my = Math.min(p1.y, p2.y) - 52;
            if (t % 20 < 10) {
                ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.font = '5px Arial';
                ctx.fillText('haha', mx, my);
            }
        } else if (s.type === 'talk') {
            // They take turns talking
            const turn = Math.floor(t / 40) % 2; // alternates every ~0.7s
            const talker = turn === 0 ? p1 : p2;
            const listener = turn === 0 ? p2 : p1;
            // Speech bubble dots for talker
            const bob = Math.sin(t * 0.25) * 1;
            ctx.fillStyle = '#fff';
            ctx.font = '7px Arial'; ctx.textAlign = 'center';
            const dots = '.'.repeat((Math.floor(t / 10) % 3) + 1);
            ctx.fillText(dots, talker.x, talker.y - 55 + bob);
            // Talker mouth: animated talking
            talker._socialMouth = Math.floor(t / 5) % 3 === 0 ? 'open' : Math.floor(t / 5) % 3 === 1 ? 'half' : 'closed';
            // Listener: occasional nod (slight y offset) and smile
            listener._socialMouth = 'smile';
            // Nod indicator
            if (Math.floor(t / 15) % 4 === 0) {
                ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.font = '6px Arial';
                ctx.fillText('~', listener.x + listener.faceDir * 14, listener.y - 45);
            }
        }
    }
}

// Clear social mouth overrides after drawing (called per agent in draw)
function getSocialMouth(agent) {
    const m = agent._socialMouth || null;
    agent._socialMouth = null;
    return m;
}

// Trigger social interaction from proximity
function maybeStartSocial(agent) {
    if (!agent.socialTarget) return;
    if (agent.id > agent.socialTarget) return;
    if (Math.random() > 0.004) return; // ~0.4% per frame
    // No cap — multiple conversations can happen simultaneously
    const other = agentMap[agent.socialTarget];
    if (!other) return;
    // Allow if either is visiting OR both are in social spots — sitting at desk is OK for visited agents
    const agentVisiting = agent.idleAction === 'visit';
    const otherVisiting = other.idleAction === 'visit';
    const otherIdleDesk = other.state === 'idle' && !other.idleAction && other.isSitting;
    if (!agentVisiting && !otherVisiting && other.isSitting) return; // original guard for non-visit scenarios
    startSocialInteraction(agent, other);
}

// ============================================================
// GROUP GATHERINGS — idle agents form social circles
// ============================================================
const groupGatherings = [];
// Dynamic gathering spots — picks open floor areas near furniture or between agents
function _pickGatheringSpot() {
    // Option 1: near a random piece of social furniture
    var socialTypes = ['couch', 'coffeeTable', 'waterCooler', 'coffeeMaker', 'bookshelf', 'tv', 'vendingMachine', 'plant', 'tallPlant', 'endTable'];
    var socialItems = officeConfig.furniture.filter(function(f) { return socialTypes.indexOf(f.type) >= 0; });
    // Option 2: midpoint between two random idle agents
    var idleAgents = agents.filter(function(a) { return a.state === 'idle' && !a.idleAction; });

    var spot = null;
    var roll = Math.random();

    if (roll < 0.5 && socialItems.length > 0) {
        // Near furniture — offset so they don't stand on it
        var item = socialItems[Math.floor(Math.random() * socialItems.length)];
        var angle = Math.random() * Math.PI * 2;
        spot = {
            x: Math.round(item.x + Math.cos(angle) * 40),
            y: Math.round(item.y + Math.sin(angle) * 40),
            label: 'by the ' + item.type
        };
    } else if (idleAgents.length >= 2) {
        // Between two agents
        var a1 = idleAgents[Math.floor(Math.random() * idleAgents.length)];
        var a2 = idleAgents.filter(function(a) { return a.id !== a1.id; })[Math.floor(Math.random() * (idleAgents.length - 1))];
        if (a2) {
            spot = {
                x: Math.round((a1.x + a2.x) / 2),
                y: Math.round((a1.y + a2.y) / 2),
                label: 'in the hall'
            };
        }
    }

    if (!spot) {
        // Fallback: random open area
        spot = {
            x: 80 + Math.floor(Math.random() * (W - 160)),
            y: 80 + Math.floor(Math.random() * (H - 160)),
            label: 'in the office'
        };
    }

    // Clamp to world bounds
    spot.x = Math.max(60, Math.min(W - 60, spot.x));
    spot.y = Math.max(80, Math.min(H - 60, spot.y));
    return spot;
}

function startGathering() {
    if (groupGatherings.length >= 1) return; // max 1 gathering at a time
    // Find idle agents sitting at desks
    const idleAgents = agents.filter(a => a.state === 'idle' && !a.idleAction && a.isSitting && !a.meetingId);
    if (idleAgents.length < 2) return;
    // Pick 2-4 agents to gather
    const count = Math.min(2 + Math.floor(Math.random() * 3), idleAgents.length);
    const shuffled = idleAgents.sort(() => Math.random() - 0.5);
    const members = shuffled.slice(0, count).map(a => a.id);
    // Pick a dynamic spot
    const spot = _pickGatheringSpot();
    const gathering = {
        id: Math.random().toString(36).substr(2, 8),
        spot: spot,
        members: members,
        phase: 'walking', // walking → socializing → dispersing
        timer: 0,
        socializeDuration: 1800 + Math.floor(Math.random() * 3600), // 30-90 seconds
        activeInteractions: [], // joke/laugh/talk happening within the group
        interactionCooldown: 0,
    };
    groupGatherings.push(gathering);
    // Assign positions in a circle around the spot
    members.forEach((id, i) => {
        const agent = agentMap[id];
        if (!agent) return;
        const angle = (i / members.length) * Math.PI * 2 - Math.PI / 2;
        const radius = 21 + members.length * 5;
        agent.targetX = spot.x + Math.cos(angle) * radius;
        agent.targetY = spot.y + Math.sin(angle) * radius;
        agent.idleAction = 'gathering';
        agent.idleReturnTimer = 0; // managed by gathering system
        agent._gatheringId = gathering.id;
        agent.addIntent('Heading to ' + spot.label + ' to hang out');
    });
}

function updateGatherings() {
    for (let i = groupGatherings.length - 1; i >= 0; i--) {
        const g = groupGatherings[i];
        g.timer++;

        if (g.phase === 'walking') {
            // Check if all members arrived
            let allArrived = true;
            g.members.forEach(id => {
                const a = agentMap[id];
                if (!a) return;
                const dx = a.x - a.targetX, dy = a.y - a.targetY;
                if (Math.sqrt(dx * dx + dy * dy) > a.speed + 1) allArrived = false;
            });
            if (allArrived || g.timer > 300) { // switch after arrival or 5s timeout
                g.phase = 'socializing';
                g.timer = 0;
                // Face each other toward center
                g.members.forEach(id => {
                    const a = agentMap[id];
                    if (a) a.faceDir = g.spot.x > a.x ? 1 : -1;
                });
            }
            // Allow new idle agents to join while walking
            _maybeJoinGathering(g);
        } else if (g.phase === 'socializing') {
            // Trigger random interactions within the group
            g.interactionCooldown--;
            if (g.interactionCooldown <= 0 && g.members.length >= 2) {
                // Pick two random members for an interaction
                const shuffled = g.members.sort(() => Math.random() - 0.5);
                const a1 = agentMap[shuffled[0]], a2 = agentMap[shuffled[1]];
                if (a1 && a2) {
                    // Check they aren't already in a social interaction
                    const busy = socialInteractions.some(s =>
                        [s.p1, s.p2].includes(a1.id) || [s.p1, s.p2].includes(a2.id));
                    if (!busy) {
                        startSocialInteraction(a1, a2);
                    }
                }
                g.interactionCooldown = 90 + Math.floor(Math.random() * 120); // 1.5-3.5s between interactions
            }
            // Allow new idle agents to join during socializing
            _maybeJoinGathering(g);
            // End socializing after duration
            if (g.timer >= g.socializeDuration) {
                g.phase = 'dispersing';
                g.timer = 0;
                g.members.forEach(id => {
                    const a = agentMap[id];
                    if (a) {
                        a.idleAction = null;
                        a._gatheringId = null;
                        a.addIntent('Heading back to desk');
                        a.returnToDesk();
                    }
                });
            }
        } else if (g.phase === 'dispersing') {
            if (g.timer > 60) {
                groupGatherings.splice(i, 1);
            }
        }
    }
}

function _maybeJoinGathering(g) {
    if (g.members.length >= g.spot.capacity) return;
    if (Math.random() > 0.003) return; // ~0.3% per frame
    const joinable = agents.filter(a =>
        a.state === 'idle' && !a.idleAction && a.isSitting && !a.meetingId &&
        !g.members.includes(a.id)
    );
    if (joinable.length === 0) return;
    const joiner = joinable[Math.floor(Math.random() * joinable.length)];
    g.members.push(joiner.id);
    // Assign position in the circle
    const angle = ((g.members.length - 1) / g.members.length) * Math.PI * 2 - Math.PI / 2;
    const radius = 21 + g.members.length * 5;
    joiner.targetX = g.spot.x + Math.cos(angle) * radius;
    joiner.targetY = g.spot.y + Math.sin(angle) * radius;
    joiner.idleAction = 'gathering';
    joiner.idleReturnTimer = 0;
    joiner._gatheringId = g.id;
    joiner.addIntent('Joining the group at ' + g.spot.label);
    // Reposition everyone in a proper circle
    g.members.forEach((id, idx) => {
        const a = agentMap[id];
        if (!a) return;
        const ang = (idx / g.members.length) * Math.PI * 2 - Math.PI / 2;
        const r = 21 + g.members.length * 5;
        a.targetX = g.spot.x + Math.cos(ang) * r;
        a.targetY = g.spot.y + Math.sin(ang) * r;
    });
}

function drawGatherings() {
    for (let i = 0; i < groupGatherings.length; i++) {
        const g = groupGatherings[i];
        if (g.phase !== 'socializing') continue;
        // Draw a subtle circle on the floor to show the gathering area
        ctx.save();
        ctx.globalAlpha = 0.08;
        ctx.fillStyle = '#ffd700';
        ctx.beginPath();
        const r = 30 + g.members.length * 5;
        ctx.arc(g.spot.x, g.spot.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        // Floating social indicator
        const bob = Math.sin(g.timer * 0.05) * 2;
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '10px Arial'; ctx.textAlign = 'center';
        const emojis = ['💬', '😄', '🗣️'];
        const em = emojis[Math.floor(g.timer / 60) % emojis.length];
        ctx.fillText(em, g.spot.x, g.spot.y - 40 + bob);
    }
}

// Remove agent from any active gathering (when they get work or need to leave)
function leaveGathering(agentId) {
    for (let i = 0; i < groupGatherings.length; i++) {
        const g = groupGatherings[i];
        const idx = g.members.indexOf(agentId);
        if (idx !== -1) {
            g.members.splice(idx, 1);
            const a = agentMap[agentId];
            if (a) { a.idleAction = null; a._gatheringId = null; }
            // If only 1 or 0 left, end the gathering
            if (g.members.length <= 1) {
                g.members.forEach(id => {
                    const m = agentMap[id];
                    if (m) { m.idleAction = null; m._gatheringId = null; m.returnToDesk(); }
                });
                groupGatherings.splice(i, 1);
            }
            break;
        }
    }
}

// Check if a gathering should start (called once per frame in loop)
function maybeStartGathering() {
    if (groupGatherings.length >= 1) return;
    if (Math.random() > 0.000012) return; // ~0.0012% per frame, roughly every 15-20 minutes
    startGathering();
}

// ============================================================
// DART BOARD GAME — agents throw darts at the board
// ============================================================
const dartGames = [];
var dartStuckDarts = []; // darts currently stuck on the board
const DART_COLORS = ['#f44336','#2196f3','#4caf50','#ff9800','#9c27b0','#00bcd4'];

function startDartGame(agent1, agent2) {
    if (dartGames.length >= 1) return;
    if (dartGames.some(g => [g.p1, g.p2].includes(agent1.id) || [g.p1, g.p2].includes(agent2.id))) return;
    const inter = LOCATIONS.interactions;
    const spot = inter.dartBoard;
    if (!spot) return;
    dartStuckDarts = []; // clear board
    const game = {
        p1: agent1.id, p2: agent2.id,
        phase: 'walking', // walking → p1_throw → p1_land → p2_throw → p2_land → result
        timer: 0,
        p1Score: 0, p2Score: 0,
        throwNum: 0, // each player throws 3
        maxThrows: 3,
        currentThrower: 1,
        dartX: 0, dartY: 0, // dart animation position
        dartTarget: { ox: 0, oy: 0 }, // where dart lands on board
        resultTimer: 0,
    };
    dartGames.push(game);
    // Position agents 3-4 tiles in front of the dart board
    agent1.targetX = spot.x - 16;
    agent1.targetY = spot.y;
    agent1.idleAction = 'darts';
    agent1.idleReturnTimer = 0;
    agent2.targetX = spot.x + 16;
    agent2.targetY = spot.y;
    agent2.idleAction = 'darts';
    agent2.idleReturnTimer = 0;
    agent1.addIntent('Playing darts with ' + agent2.name);
    agent2.addIntent('Playing darts with ' + agent1.name);
}

function _dartScore(ox, oy) {
    const dist = Math.sqrt(ox * ox + oy * oy);
    if (dist <= 2) return { pts: 50, label: 'BULLSEYE!' };
    if (dist <= 4) return { pts: 25, label: 'Bull' };
    if (dist <= 8) return { pts: 15, label: 'Triple' };
    if (dist <= 12) return { pts: 10, label: 'Single' };
    return { pts: 5, label: 'Outer' };
}

function updateDartGames() {
    var inter = LOCATIONS.interactions;
    for (var i = dartGames.length - 1; i >= 0; i--) {
        var g = dartGames[i];
        var p1 = agentMap[g.p1], p2 = agentMap[g.p2];
        if (!p1 || !p2) { dartGames.splice(i, 1); continue; }
        g.timer++;

        // Lock agents at dart positions during active game
        if (g.phase !== 'walking' && inter.dartBoard) {
            p1.x = inter.dartBoard.x - 16; p1.y = inter.dartBoard.y;
            p2.x = inter.dartBoard.x + 16; p2.y = inter.dartBoard.y;
            p1.targetX = p1.x; p1.targetY = p1.y;
            p2.targetX = p2.x; p2.targetY = p2.y;
        }

        if (g.phase === 'walking') {
            var d1 = Math.abs(p1.x - p1.targetX) + Math.abs(p1.y - p1.targetY);
            var d2 = Math.abs(p2.x - p2.targetX) + Math.abs(p2.y - p2.targetY);
            if ((d1 < 4 && d2 < 4) || g.timer > 300) {
                g.phase = 'p_aim';
                g.timer = 0;
                g.currentThrower = 1;
                p1.faceDir = -1; p2.faceDir = -1; // face the board (left wall area)
            }
        } else if (g.phase === 'p_aim') {
            // Aiming phase — arm wobbles for 1.5 seconds
            if (g.timer >= 90) {
                g.phase = 'p_throw';
                g.timer = 0;
                // Calculate where dart lands (random with skill)
                var spread = 6;
                g.dartTarget = {
                    ox: Math.round((Math.random() - 0.5) * spread * 2),
                    oy: Math.round((Math.random() - 0.5) * spread * 2)
                };
            }
        } else if (g.phase === 'p_throw') {
            // Dart flying animation — 20 frames
            if (g.timer >= 20) {
                g.phase = 'p_land';
                g.timer = 0;
                var score = _dartScore(g.dartTarget.ox, g.dartTarget.oy);
                var thrower = g.currentThrower === 1 ? p1 : p2;
                var flightC = g.currentThrower === 1 ? '#f44336' : '#2196f3';
                dartStuckDarts.push({
                    ox: g.dartTarget.ox, oy: g.dartTarget.oy,
                    color: thrower.color, flightColor: flightC
                });
                if (g.currentThrower === 1) g.p1Score += score.pts;
                else g.p2Score += score.pts;
            }
        } else if (g.phase === 'p_land') {
            // Show score briefly — 60 frames
            if (g.timer >= 60) {
                g.throwNum++;
                if (g.currentThrower === 1) {
                    // Switch to player 2
                    g.currentThrower = 2;
                    g.phase = 'p_aim';
                    g.timer = 0;
                } else {
                    // Both threw, check if more rounds
                    g.currentThrower = 1;
                    if (g.throwNum >= g.maxThrows * 2) {
                        g.phase = 'result';
                        g.timer = 0;
                    } else {
                        g.phase = 'p_aim';
                        g.timer = 0;
                    }
                }
            }
        } else if (g.phase === 'result') {
            if (g.timer >= 150) {
                // Game over — return to desks
                p1.idleAction = null; p2.idleAction = null;
                p1.returnToDesk(); p2.returnToDesk();
                dartStuckDarts = [];
                dartGames.splice(i, 1);
            }
        }
    }
}

function drawDartGames() {
    for (var i = 0; i < dartGames.length; i++) {
        var g = dartGames[i];
        var p1 = agentMap[g.p1], p2 = agentMap[g.p2];
        if (!p1 || !p2) continue;
        var thrower = g.currentThrower === 1 ? p1 : p2;
        // Find actual dart board position from furniture
        var _dbItem = null;
        if (officeConfig && officeConfig.furniture) {
            for (var _dbi = 0; _dbi < officeConfig.furniture.length; _dbi++) {
                if (officeConfig.furniture[_dbi].type === 'dartBoard') { _dbItem = officeConfig.furniture[_dbi]; break; }
            }
        }
        var boardX = _dbItem ? _dbItem.x : (LOCATIONS.lounge.x + 210);
        var boardY = _dbItem ? (_dbItem.y + 10) : (LOCATIONS.lounge.y - 8);

        if (g.phase === 'p_aim') {
            // Aiming wobble indicator
            var wobble = Math.sin(g.timer * 0.15) * 3;
            ctx.fillStyle = 'rgba(255,255,0,0.4)';
            ctx.beginPath();
            ctx.arc(boardX + wobble, boardY + Math.cos(g.timer * 0.12) * 2, 3, 0, Math.PI * 2);
            ctx.fill();
            // Thrower arm extended
            thrower._socialMouth = 'closed';
        } else if (g.phase === 'p_throw') {
            // Dart flying from thrower to board
            var progress = g.timer / 20;
            var startX = thrower.x, startY = thrower.y - 30;
            var dx = boardX + g.dartTarget.ox - startX;
            var dy = boardY + g.dartTarget.oy - startY;
            var dartX = startX + dx * progress;
            var dartY = startY + dy * progress - Math.sin(progress * Math.PI) * 15; // arc
            // Draw flying dart
            ctx.fillStyle = thrower.color;
            ctx.fillRect(dartX - 1, dartY - 1, 3, 3);
            ctx.fillStyle = g.currentThrower === 1 ? '#f44336' : '#2196f3';
            ctx.fillRect(dartX - 1, dartY + 2, 3, 2); // flight
        } else if (g.phase === 'p_land') {
            // Score popup
            var score = _dartScore(g.dartTarget.ox, g.dartTarget.oy);
            var bob = -g.timer * 0.3;
            var alpha = Math.max(0, 1 - g.timer / 60);
            ctx.save();
            ctx.globalAlpha = alpha;
            ctx.fillStyle = score.pts >= 25 ? '#ffd700' : '#fff';
            ctx.font = score.pts >= 25 ? 'bold 10px Arial' : '9px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(score.pts + (score.pts >= 25 ? ' ' + score.label : ''), boardX, boardY - 22 + bob);
            ctx.restore();
        } else if (g.phase === 'result') {
            // Final scores
            var bob = Math.sin(g.timer * 0.08) * 2;
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(boardX - 45, boardY - 40 + bob, 90, 36);
            ctx.strokeStyle = '#ffd700'; ctx.lineWidth = 1;
            ctx.strokeRect(boardX - 45, boardY - 40 + bob, 90, 36);
            ctx.font = 'bold 8px Arial'; ctx.textAlign = 'center';
            // Winner highlight
            var p1Win = g.p1Score > g.p2Score;
            var tie = g.p1Score === g.p2Score;
            ctx.fillStyle = p1Win ? '#ffd700' : '#ccc';
            ctx.fillText(p1.name + ': ' + g.p1Score, boardX, boardY - 28 + bob);
            ctx.fillStyle = !p1Win && !tie ? '#ffd700' : '#ccc';
            ctx.fillText(p2.name + ': ' + g.p2Score, boardX, boardY - 18 + bob);
            ctx.fillStyle = '#ffd700'; ctx.font = 'bold 9px Arial';
            ctx.fillText(tie ? 'TIE!' : '🏆 ' + (p1Win ? p1.name : p2.name) + ' wins!', boardX, boardY - 8 + bob);
            // Winner celebrates
            if (!tie) {
                var winner = p1Win ? p1 : p2;
                winner._socialMouth = 'laugh';
            }
        }

        // Scoreboard during game (small)
        if (g.phase !== 'result' && g.phase !== 'walking') {
            ctx.fillStyle = 'rgba(0,0,0,0.5)';
            ctx.fillRect(boardX - 35, boardY + 18, 70, 14);
            ctx.font = '7px Arial'; ctx.textAlign = 'center';
            ctx.fillStyle = '#f44336';
            ctx.fillText(p1.name + ':' + g.p1Score, boardX - 12, boardY + 28);
            ctx.fillStyle = '#2196f3';
            ctx.fillText(p2.name + ':' + g.p2Score, boardX + 18, boardY + 28);
        }
    }
}

// Trigger dart game from social proximity
function maybeStartDarts(agent) {
    if (!agent.socialTarget) return;
    if (agent.id > agent.socialTarget) return;
    if (Math.random() > 0.001) return; // ~0.1% per frame
    if (dartGames.length >= 1) return;
    // Only trigger near lounge area
    var lx = LOCATIONS.lounge.x, ly = LOCATIONS.lounge.y;
    if (Math.abs(agent.x - lx - 100) > 120 || Math.abs(agent.y - ly - 40) > 80) return;
    var other = agentMap[agent.socialTarget];
    if (!other || other.isSitting) return;
    startDartGame(agent, other);
}

// --- MAIN LOOP ---
// ============================================================
// OFFICE PET SYSTEM
// ============================================================
var officePets = [];

function initPets() {
    officePets = [];
    var petCfg = officeConfig.pet;
    if (!petCfg || !petCfg.enabled) return;
    officePets.push(new OfficePet(petCfg));
}

class OfficePet {
    constructor(cfg) {
        this.species = cfg.species || 'cat'; // 'cat', 'lobster', or 'pug'
        this.name = cfg.name || 'Clawy';
        this.x = cfg.x || Math.floor(W / 2);
        this.y = cfg.y || Math.floor(H / 2);
        this.targetX = this.x;
        this.targetY = this.y;
        this.faceDir = 1;
        this.moveDir = 'side'; // 'up', 'down', 'side' — vertical movement direction for cat/pug sprites
        this.tick = 0;
        this.state = 'sitting'; // starts sitting calmly
        this.stateTimer = 200 + Math.floor(Math.random() * 300);
        this.sleepZ = 0;
        this.tailWag = 0;
        this.curiosityTarget = null;
        this.greetTarget = null;
        this.interactingAgent = null;
        this.animFrame = 0;
        this.speed = 1.2;
        this._blinkTimer = 80 + Math.floor(Math.random() * 120);
        this._blinking = false;
        this._blinkFrames = 0;
        this._path = null;
        this._prevTargetX = this.targetX;
        this._prevTargetY = this.targetY;
        this._stuckTicks = 0;
        this._detourAngle = 0;
    }

    update() {
        this.tick++;
        this.tailWag = Math.sin(this.tick * 0.15) * 3;
        this.animFrame = Math.floor(this.tick / 10) % 4;
        this.isMoving = false;
        // Blink timer
        if (this._blinking) {
            this._blinkFrames--;
            if (this._blinkFrames <= 0) { this._blinking = false; this._blinkTimer = 80 + Math.floor(Math.random() * 200); }
        } else {
            this._blinkTimer--;
            if (this._blinkTimer <= 0) { this._blinking = true; this._blinkFrames = 4 + Math.floor(Math.random() * 3); }
        }

        // === FROZEN STATES: don't move at all ===
        if (this.state === 'sleeping' || this.state === 'sitting' || this.state === 'being_pet' ||
            this.state === 'grooming' || this.state === 'looking_around') {
            this.stateTimer--;
            if (this.state === 'sleeping') this.sleepZ = (this.sleepZ + 0.015) % 1;
            if (this.state === 'being_pet' && this.stateTimer <= 0) {
                this.interactingAgent = null;
                this._transitionTo('sitting', 80 + Math.floor(Math.random() * 120)); // sit after pets
            }
            if (this.state === 'looking_around') {
                // Flip face direction occasionally
                if (this.tick % 40 === 0) this.faceDir *= -1;
            }
            if (this.stateTimer <= 0) this._pickBehavior();
            return;
        }

        // === MOVEMENT STATES ===
        var speed = this.state === 'chased' ? 2.8 : this.speed;

        // Path following (same as agents)
        if (this.targetX !== this._prevTargetX || this.targetY !== this._prevTargetY) {
            this._prevTargetX = this.targetX;
            this._prevTargetY = this.targetY;
            if (collisionGrid && officeConfig.walls.interior && officeConfig.walls.interior.length > 0) {
                var _fp = findPath(this.x, this.y, this.targetX, this.targetY);
                this._path = (_fp && _fp.length > 0) ? _fp : null;
            } else {
                this._path = null;
            }
        }
        if (this._path && this._path.length > 0) {
            var _wp = this._path[0];
            if (Math.abs(_wp.x - this.x) < speed * 2 && Math.abs(_wp.y - this.y) < speed * 2) {
                this._path.shift();
            }
        }
        var _etX = this.targetX, _etY = this.targetY;
        if (this._path && this._path.length > 0) {
            _etX = this._path[0].x;
            _etY = this._path[0].y;
        }

        var dx = _etX - this.x;
        var dy = _etY - this.y;
        var dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > speed) {
            this.isMoving = true;
            var moveX = (dx / dist) * speed;
            var moveY = (dy / dist) * speed;

            // Collision avoidance against agents
            if (COLLISION_ENABLED) {
                for (var i = 0; i < agents.length; i++) {
                    var other = agents[i];
                    var ox = this.x - other.x, oy = this.y - other.y;
                    var oDist = Math.sqrt(ox * ox + oy * oy);
                    if (oDist < COLLISION_RADIUS * 1.5 && oDist > 0.1) {
                        var force = COLLISION_PUSH * (1 - oDist / (COLLISION_RADIUS * 1.5));
                        moveX += (ox / oDist) * force;
                        moveY += (oy / oDist) * force;
                    }
                }
            }

            var prevX = this.x, prevY = this.y;
            this.x += moveX;
            this.y += moveY;
            this.x = Math.max(10, Math.min(W - 10, this.x));
            this.y = Math.max(10, Math.min(H - 10, this.y));
            var actualMove = Math.sqrt((this.x - prevX) * (this.x - prevX) + (this.y - prevY) * (this.y - prevY));
            if (actualMove < speed * 0.3 && dist > 10) {
                this._stuckTicks++;
                if (this._stuckTicks > 30) {
                    if (this._stuckTicks === 31) this._detourAngle = (Math.random() > 0.5 ? 1 : -1) * (Math.PI / 2);
                    this.x += Math.cos(Math.atan2(dy, dx) + this._detourAngle) * speed * 1.5;
                    this.y += Math.sin(Math.atan2(dy, dx) + this._detourAngle) * speed * 1.5;
                }
                if (this._stuckTicks > 120) {
                    this._stuckTicks = 0;
                    this._wander();
                }
            } else {
                this._stuckTicks = 0;
                this._detourAngle = 0;
            }

            if (Math.abs(dx) > 0.5) this.faceDir = dx > 0 ? 1 : -1;
            // Track vertical movement direction for front/back sprites
            if (Math.abs(dy) > Math.abs(dx) * 0.8) {
                this.moveDir = dy < 0 ? 'up' : 'down';
            } else {
                this.moveDir = 'side';
            }
        } else {
            // Arrived at destination
            this.moveDir = 'side';
            if (this._path && this._path.length > 0) {
                this.x = _etX; this.y = _etY;
                this._path.shift();
                if (this._path.length === 0) this._path = null;
            } else {
                this.x = this.targetX;
                this.y = this.targetY;
                this.isMoving = false;
                // Arrived — enter the destination state
                if (this.state === 'walking_to_sleep') {
                    this._transitionTo('sleeping', 600 + Math.floor(Math.random() * 900));
                } else if (this.state === 'walking_to_curious') {
                    this._transitionTo('looking_around', 100 + Math.floor(Math.random() * 120));
                } else if (this.state === 'walking_to_greet') {
                    this._transitionTo('sitting', 80 + Math.floor(Math.random() * 80));
                    if (this.greetTarget) this.faceDir = this.greetTarget.x > this.x ? 1 : -1;
                } else if (this.state === 'chased') {
                    // Ran to safety — freeze and look back
                    this._transitionTo('looking_around', 60 + Math.floor(Math.random() * 40));
                } else {
                    // Generic arrival → sit or idle briefly
                    this._transitionTo('sitting', 60 + Math.floor(Math.random() * 180));
                }
            }
        }

        this.stateTimer--;
        if (this.stateTimer <= 0 && this.state !== 'sleeping') this._pickBehavior();
    }

    _transitionTo(state, duration) {
        this.state = state;
        this.stateTimer = duration;
        this.isMoving = false;
        this._path = null;
    }

    _pickBehavior() {
        var roll = Math.random();
        var inter = LOCATIONS.interactions;

        if (roll < 0.25) {
            // === SLEEP (most common — animals sleep a LOT) ===
            // Walk to a couch or corner first, THEN sleep
            var sleepTarget = null;
            if (inter.couchSeats && inter.couchSeats.length > 0 && Math.random() < 0.6) {
                sleepTarget = inter.couchSeats[Math.floor(Math.random() * inter.couchSeats.length)];
            } else {
                var corners = [
                    { x: 30, y: 60 }, { x: W - 30, y: 60 },
                    { x: 30, y: H - 30 }, { x: W - 30, y: H - 30 }
                ];
                sleepTarget = corners[Math.floor(Math.random() * corners.length)];
            }
            this.state = 'walking_to_sleep';
            this.stateTimer = 999; // overridden on arrival
            this.targetX = sleepTarget.x;
            this.targetY = sleepTarget.y;
        } else if (roll < 0.40) {
            // === SIT / IDLE right here ===
            this._transitionTo('sitting', 200 + Math.floor(Math.random() * 300));
        } else if (roll < 0.50) {
            // === GROOMING (lick paws, clean self) ===
            this._transitionTo('grooming', 120 + Math.floor(Math.random() * 150));
        } else if (roll < 0.58) {
            // === LOOK AROUND (head turning, curious about surroundings) ===
            this._transitionTo('looking_around', 80 + Math.floor(Math.random() * 100));
        } else if (roll < 0.70) {
            // === GREET an idle agent ===
            var idleAgents = agents.filter(function(a) {
                return a.state === 'idle' || a.idleAction === 'couch' || a.idleAction === 'watch_tv';
            });
            if (idleAgents.length > 0) {
                var target = idleAgents[Math.floor(Math.random() * idleAgents.length)];
                this.greetTarget = target;
                this.state = 'walking_to_greet';
                this.stateTimer = 999;
                this.targetX = target.x + (Math.random() < 0.5 ? -18 : 18);
                this.targetY = target.y + 8;
            } else {
                this._transitionTo('sitting', 150 + Math.floor(Math.random() * 100));
            }
        } else if (roll < 0.82) {
            // === CURIOUS about furniture ===
            var curioItems = officeConfig.furniture.filter(function(f) {
                return ['bookshelf','tv','pingPongTable','dartBoard','vendingMachine','coffeeMaker',
                        'microwave','toaster','plant','tallPlant','endTable','trashCan'].indexOf(f.type) >= 0;
            });
            if (curioItems.length > 0) {
                var item = curioItems[Math.floor(Math.random() * curioItems.length)];
                this.curiosityTarget = item;
                this.state = 'walking_to_curious';
                this.stateTimer = 999;
                this.targetX = item.x + 10 + Math.floor(Math.random() * 20);
                this.targetY = item.y + 20 + Math.floor(Math.random() * 10);
            } else {
                this._transitionTo('looking_around', 80);
            }
        } else {
            // === SHORT WANDER ===
            this._wander();
        }
    }

    _wander() {
        this.state = 'walking';
        this.stateTimer = 120 + Math.floor(Math.random() * 200);
        // Short distance wander — not across the whole map
        var wanderDist = 60 + Math.floor(Math.random() * 100);
        var angle = Math.random() * Math.PI * 2;
        this.targetX = Math.max(30, Math.min(W - 30, Math.round(this.x + Math.cos(angle) * wanderDist)));
        this.targetY = Math.max(60, Math.min(H - 30, Math.round(this.y + Math.sin(angle) * wanderDist)));
    }

    // Called by agents when they decide to pet
    startBeingPet(agent) {
        this.state = 'being_pet';
        this.interactingAgent = agent;
        this.stateTimer = 80 + Math.floor(Math.random() * 60);
        this.faceDir = agent.x > this.x ? 1 : -1;
    }

    // Called by agents when they decide to chase
    startChase(agent) {
        this.state = 'chased';
        this.interactingAgent = agent;
        this.stateTimer = 100 + Math.floor(Math.random() * 80);
        // Run away from agent
        var awayX = this.x + (this.x - agent.x) * 2;
        var awayY = this.y + (this.y - agent.y) * 2;
        this.targetX = Math.max(30, Math.min(W - 30, awayX));
        this.targetY = Math.max(60, Math.min(H - 30, awayY));
    }

    draw() {
        var px = Math.round(this.x);
        var py = Math.round(this.y);
        ctx.save();
        ctx.translate(px, py);
        ctx.scale(this.faceDir, 1);
        // Pixel-snapped drawing, no anti-aliasing for the 2D style
        ctx.imageSmoothingEnabled = false;

        if (this.species === 'cat') this._drawCat();
        else if (this.species === 'pug') this._drawPug();
        else this._drawLobster();

        ctx.restore();

        // Sleep Z's
        if (this.state === 'sleeping') {
            var zOff = this.sleepZ * 20;
            var zAlpha = 1 - this.sleepZ;
            ctx.globalAlpha = zAlpha * 0.7;
            ctx.fillStyle = '#fff';
            ctx.font = (8 + this.sleepZ * 6) + 'px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('z', this.x + 8, this.y - 10 - zOff);
            ctx.fillText('Z', this.x + 14, this.y - 18 - zOff * 0.7);
            ctx.globalAlpha = 1;
        }

        // Heart when being pet
        if (this.state === 'being_pet') {
            var hBounce = Math.sin(this.tick * 0.2) * 3;
            ctx.fillStyle = '#e91e63';
            ctx.font = '10px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('♥', this.x, this.y - 16 + hBounce);
        }

        // Curiosity ? when looking around
        if (this.state === 'looking_around' && this.curiosityTarget) {
            ctx.fillStyle = '#ffd600';
            ctx.font = 'bold 9px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('?', this.x + 2, this.y - 12);
        }

        // Grooming sparkles
        if (this.state === 'grooming' && this.tick % 20 < 10) {
            ctx.fillStyle = '#fff';
            ctx.font = '6px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('✨', this.x + 6, this.y - 14);
        }

        // Name tag (above pet head)
        ctx.fillStyle = 'rgba(255,255,255,0.6)';
        ctx.font = '7px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(this.name, this.x, this.y - 24);
    }

    _drawCat() {
        // Soft 2D style, no black outlines, rounded edges, matches office style
        // Dark charcoal cat with white chest spot
        var BD = '#2a2030';  // body darkest
        var BM = '#3d3347';  // body main
        var BL = '#4a4256';  // body light
        var BH = '#5a5066';  // highlights
        var FUR = '#332838'; // fur texture shade
        var WC = '#8a8494';  // white chest spot
        var WC2 = '#a09aaa'; // chest highlight
        var EY = '#f0c040';  // eye yellow
        var PU = '#1a1020';  // pupil
        var PK = '#6a4870';  // inner ear pink
        var walk = this.isMoving ? Math.floor(Math.sin(this.tick * 0.3) * 2) : 0;
        var tailSway = Math.sin(this.tick * 0.12) * 2;
        var earTwitch = (this.tick % 120 < 6) ? 1 : 0;
        var breathe = Math.sin(this.tick * 0.06) * 0.5;
        var isSleeping = this.state === 'sleeping';
        var isSitting = this.state === 'sitting' || this.state === 'being_pet' || this.state === 'looking_around';
        var isGrooming = this.state === 'grooming';

        // Shadow (soft, no outline)
        ctx.fillStyle = 'rgba(30,20,40,0.12)';
        ctx.fillRect(-9, 9, 18, 3);
        ctx.fillRect(-7, 10, 14, 2);

        if (isSleeping) {
            // === SLEEPING — lying on side, head resting on paws ===
            // Body (lying flat, slightly curled)
            ctx.fillStyle = BD;
            ctx.fillRect(-4, 0, 14, 8);
            ctx.fillRect(-3, -1, 12, 10);
            ctx.fillStyle = BM;
            ctx.fillRect(-2, 1, 10, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(-1, 2, 8, 3);
            // White chest
            ctx.fillStyle = WC;
            ctx.fillRect(0, 4, 4, 2);
            // Fur texture
            ctx.fillStyle = FUR;
            ctx.fillRect(2, 2, 2, 1);
            ctx.fillRect(6, 3, 1, 1);
            // Breathing
            ctx.fillStyle = BM;
            ctx.fillRect(-3, 6 + Math.round(breathe), 12, 1);

            // Head (distinct, resting to the left, bigger than body blob)
            ctx.fillStyle = BD;
            ctx.fillRect(-12, -4, 10, 9);
            ctx.fillRect(-11, -5, 8, 11);
            ctx.fillStyle = BM;
            ctx.fillRect(-10, -3, 7, 7);
            ctx.fillRect(-11, -2, 8, 5);
            ctx.fillStyle = BL;
            ctx.fillRect(-9, -3, 5, 3);

            // Ears (clearly visible on top of head)
            ctx.fillStyle = BD;
            ctx.fillRect(-12, -8, 3, 4);
            ctx.fillRect(-7, -8, 3, 4);
            ctx.fillStyle = PK;
            ctx.fillRect(-11, -7, 2, 2);
            ctx.fillRect(-6, -7, 2, 2);

            // Closed eyes (happy curved lines — clearly visible)
            ctx.fillStyle = EY;
            ctx.fillRect(-10, -1, 2, 1);
            ctx.fillRect(-9, -2, 1, 1);
            ctx.fillRect(-6, -1, 2, 1);
            ctx.fillRect(-5, -2, 1, 1);

            // Nose
            ctx.fillStyle = PK;
            ctx.fillRect(-7, 1, 1, 1);

            // Front paws (stretched out under chin)
            ctx.fillStyle = BD;
            ctx.fillRect(-11, 4, 3, 2);
            ctx.fillRect(-7, 4, 3, 2);
            ctx.fillStyle = BH;
            ctx.fillRect(-10, 4, 1, 1);
            ctx.fillRect(-6, 4, 1, 1);

            // Tail curled behind body
            ctx.fillStyle = BM;
            ctx.fillRect(9, 1, 2, 2);
            ctx.fillRect(10, -1, 2, 2);
            ctx.fillRect(9, -3, 2, 2);
            ctx.fillRect(8, -4, 2, 2);
            return;
        }

        if (isSitting) {
            // === SITTING FRONT-FACING ===
            // Body (rounded)
            ctx.fillStyle = BD;
            ctx.fillRect(-6, 0, 12, 10);
            ctx.fillRect(-7, 1, 14, 8);
            ctx.fillStyle = BM;
            ctx.fillRect(-5, 1, 10, 8);
            ctx.fillRect(-6, 2, 12, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(-4, 2, 8, 5);
            // White chest spot
            ctx.fillStyle = WC;
            ctx.fillRect(-2, 3, 4, 3);
            ctx.fillStyle = WC2;
            ctx.fillRect(-1, 4, 2, 1);
            // Fur texture
            ctx.fillStyle = FUR;
            ctx.fillRect(-4, 5, 1, 2);
            ctx.fillRect(4, 4, 1, 2);
            // Breathing
            ctx.fillStyle = BM;
            ctx.fillRect(-6 + Math.round(breathe * 0.5), 7, 1, 2);
            ctx.fillRect(5 - Math.round(breathe * 0.5), 7, 1, 2);

            // Head (big, rounded)
            ctx.fillStyle = BD;
            ctx.fillRect(-6, -11, 12, 11);
            ctx.fillRect(-7, -10, 14, 9);
            ctx.fillStyle = BM;
            ctx.fillRect(-5, -10, 10, 9);
            ctx.fillRect(-6, -9, 12, 7);
            ctx.fillStyle = BL;
            ctx.fillRect(-4, -10, 8, 5);
            ctx.fillStyle = BH;
            ctx.fillRect(-3, -10, 6, 2);

            // Ears (with twitch)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -16 - earTwitch, 3, 6);
            ctx.fillRect(-6, -17 - earTwitch, 2, 2);
            ctx.fillRect(4, -16 - earTwitch, 3, 6);
            ctx.fillRect(4, -17 - earTwitch, 2, 2);
            ctx.fillStyle = PK;
            ctx.fillRect(-6, -15 - earTwitch, 2, 4);
            ctx.fillRect(5, -15 - earTwitch, 2, 4);

            // Eyes
            if (this._blinking) {
                ctx.fillStyle = EY;
                ctx.fillRect(-4, -7, 3, 1);
                ctx.fillRect(1, -7, 3, 1);
            } else {
                ctx.fillStyle = EY;
                ctx.fillRect(-5, -8, 3, 3);
                ctx.fillRect(2, -8, 3, 3);
                ctx.fillStyle = PU;
                ctx.fillRect(-4, -8, 1, 2);
                ctx.fillRect(3, -8, 1, 2);
                ctx.fillStyle = '#fff';
                ctx.fillRect(-5, -8, 1, 1);
                ctx.fillRect(2, -8, 1, 1);
                // Looking around — pupils shift
                if (this.state === 'looking_around') {
                    var lookDir = Math.sin(this.tick * 0.05) > 0 ? 1 : 0;
                    ctx.fillStyle = PU;
                    ctx.fillRect(-4 + lookDir, -8, 1, 2);
                    ctx.fillRect(3 + lookDir, -8, 1, 2);
                }
            }

            // Nose + mouth
            ctx.fillStyle = PK;
            ctx.fillRect(-1, -5, 2, 1);
            ctx.fillStyle = BL;
            ctx.fillRect(-1, -4, 1, 1);
            ctx.fillRect(0, -4, 1, 1);

            // Paws
            ctx.fillStyle = BD;
            ctx.fillRect(-4, 9, 3, 2);
            ctx.fillRect(1, 9, 3, 2);
            ctx.fillStyle = BH;
            ctx.fillRect(-3, 9, 2, 1);
            ctx.fillRect(2, 9, 2, 1);

            // Tail (curling to side with sway)
            ctx.fillStyle = BM;
            ctx.fillRect(5, 5, 2, 2);
            ctx.fillRect(6, 3 + Math.round(tailSway * 0.5), 2, 2);
            ctx.fillRect(7, 1 + Math.round(tailSway * 0.5), 2, 2);
            ctx.fillRect(7, -1 + Math.round(tailSway), 2, 2);
            ctx.fillStyle = BD;
            ctx.fillRect(7, -2 + Math.round(tailSway), 2, 2);
            return;
        }

        if (isGrooming) {
            // === GROOMING — body same as sitting, head tilted ===
            ctx.fillStyle = BD;
            ctx.fillRect(-6, 0, 12, 10);
            ctx.fillRect(-7, 1, 14, 8);
            ctx.fillStyle = BM;
            ctx.fillRect(-5, 1, 10, 8);
            ctx.fillStyle = WC;
            ctx.fillRect(-2, 3, 4, 3);

            // Head tilted to side
            ctx.fillStyle = BD;
            ctx.fillRect(-2, -11, 11, 10);
            ctx.fillRect(-3, -10, 12, 8);
            ctx.fillStyle = BM;
            ctx.fillRect(-1, -10, 9, 8);
            ctx.fillStyle = BL;
            ctx.fillRect(0, -9, 6, 4);

            // Ears
            ctx.fillStyle = BD;
            ctx.fillRect(-1, -15, 3, 5);
            ctx.fillRect(5, -15, 3, 5);
            ctx.fillStyle = PK;
            ctx.fillRect(0, -14, 2, 3);
            ctx.fillRect(6, -14, 2, 3);

            // Eyes closed happy
            ctx.fillStyle = EY;
            ctx.fillRect(1, -7, 2, 1);
            ctx.fillRect(5, -7, 2, 1);

            // Paw raised (licking)
            var lk = Math.floor(Math.sin(this.tick * 0.2));
            ctx.fillStyle = BD;
            ctx.fillRect(7, -5 + lk, 3, 3);
            ctx.fillStyle = BH;
            ctx.fillRect(8, -4 + lk, 1, 1);
            ctx.fillStyle = '#c06080';
            ctx.fillRect(6, -4 + lk, 2, 1);

            ctx.fillStyle = BD;
            ctx.fillRect(-4, 9, 3, 2);
            ctx.fillRect(1, 9, 3, 2);

            // Tail
            ctx.fillStyle = BM;
            ctx.fillRect(5, 5, 2, 2);
            ctx.fillRect(6, 3, 2, 2);
            ctx.fillRect(7, 1, 2, 2);
            return;
        }

        // === WALKING ===
        if (this.moveDir === 'up') {
            // === WALKING UP — rear view (butt facing camera) ===
            // Tail (sticking up, centered, swaying)
            ctx.fillStyle = BM;
            ctx.fillRect(-1, -8, 2, 3);
            ctx.fillRect(-1, -12 + Math.round(tailSway), 2, 5);
            ctx.fillStyle = BD;
            ctx.fillRect(-1, -14 + Math.round(tailSway), 2, 3);

            // Body (rounded from behind)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -4, 14, 11);
            ctx.fillRect(-8, -3, 16, 9);
            ctx.fillStyle = BM;
            ctx.fillRect(-6, -3, 12, 9);
            ctx.fillRect(-7, -2, 14, 7);
            ctx.fillStyle = BL;
            ctx.fillRect(-5, -3, 10, 5);
            // Fur texture on back
            ctx.fillStyle = FUR;
            ctx.fillRect(-3, -1, 2, 1);
            ctx.fillRect(2, 0, 2, 1);
            ctx.fillRect(-1, 2, 1, 2);

            // Back legs (animated, seen from behind)
            ctx.fillStyle = BD;
            ctx.fillRect(-6, 5 - walk, 3, 5);
            ctx.fillRect(3, 5 + walk, 3, 5);
            ctx.fillStyle = BH;
            ctx.fillRect(-6, 8 - walk, 3, 2);
            ctx.fillRect(3, 8 + walk, 3, 2);

            // Head (back of head — no face, just round shape + ears)
            ctx.fillStyle = BD;
            ctx.fillRect(-5, -11, 10, 8);
            ctx.fillRect(-6, -10, 12, 6);
            ctx.fillStyle = BM;
            ctx.fillRect(-4, -10, 8, 6);
            ctx.fillRect(-5, -9, 10, 4);
            ctx.fillStyle = BL;
            ctx.fillRect(-3, -10, 6, 3);

            // Ears (from behind — inner not visible)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -14 - earTwitch, 3, 5);
            ctx.fillRect(-7, -15 - earTwitch, 2, 2);
            ctx.fillRect(4, -14 - earTwitch, 3, 5);
            ctx.fillRect(5, -15 - earTwitch, 2, 2);

        } else if (this.moveDir === 'down') {
            // === WALKING DOWN — front view (face toward camera) ===
            // Tail (behind body, peeking over top)
            ctx.fillStyle = BM;
            ctx.fillRect(5, -2, 2, 2);
            ctx.fillRect(6, -4 + Math.round(tailSway * 0.5), 2, 2);
            ctx.fillRect(7, -6 + Math.round(tailSway), 2, 2);
            ctx.fillStyle = BD;
            ctx.fillRect(7, -8 + Math.round(tailSway), 2, 2);

            // Body (front facing, walking)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -3, 14, 11);
            ctx.fillRect(-8, -2, 16, 9);
            ctx.fillStyle = BM;
            ctx.fillRect(-6, -2, 12, 9);
            ctx.fillRect(-7, -1, 14, 7);
            ctx.fillStyle = BL;
            ctx.fillRect(-5, -2, 10, 5);
            // White chest
            ctx.fillStyle = WC;
            ctx.fillRect(-2, 1, 4, 3);
            ctx.fillStyle = WC2;
            ctx.fillRect(-1, 2, 2, 1);
            // Fur texture
            ctx.fillStyle = FUR;
            ctx.fillRect(-4, 2, 1, 2);
            ctx.fillRect(4, 1, 1, 2);

            // Front legs (animated)
            ctx.fillStyle = BD;
            ctx.fillRect(-5, 6 + walk, 3, 5);
            ctx.fillRect(2, 6 - walk, 3, 5);
            ctx.fillStyle = BH;
            ctx.fillRect(-5, 9 + walk, 3, 2);
            ctx.fillRect(2, 9 - walk, 3, 2);

            // Head (big, front-facing)
            ctx.fillStyle = BD;
            ctx.fillRect(-6, -12, 12, 10);
            ctx.fillRect(-7, -11, 14, 8);
            ctx.fillStyle = BM;
            ctx.fillRect(-5, -11, 10, 8);
            ctx.fillRect(-6, -10, 12, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(-4, -11, 8, 4);
            ctx.fillStyle = BH;
            ctx.fillRect(-3, -11, 6, 2);

            // Ears (front-facing with twitch)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -16 - earTwitch, 3, 6);
            ctx.fillRect(-6, -17 - earTwitch, 2, 2);
            ctx.fillRect(4, -16 - earTwitch, 3, 6);
            ctx.fillRect(4, -17 - earTwitch, 2, 2);
            ctx.fillStyle = PK;
            ctx.fillRect(-6, -15 - earTwitch, 2, 4);
            ctx.fillRect(5, -15 - earTwitch, 2, 4);

            // Eyes
            if (this._blinking) {
                ctx.fillStyle = EY;
                ctx.fillRect(-4, -8, 3, 1);
                ctx.fillRect(1, -8, 3, 1);
            } else {
                ctx.fillStyle = EY;
                ctx.fillRect(-5, -9, 3, 3);
                ctx.fillRect(2, -9, 3, 3);
                ctx.fillStyle = PU;
                ctx.fillRect(-4, -9, 1, 2);
                ctx.fillRect(3, -9, 1, 2);
                ctx.fillStyle = '#fff';
                ctx.fillRect(-5, -9, 1, 1);
                ctx.fillRect(2, -9, 1, 1);
            }

            // Nose + mouth
            ctx.fillStyle = PK;
            ctx.fillRect(-1, -6, 2, 1);
            ctx.fillStyle = BL;
            ctx.fillRect(-1, -5, 1, 1);
            ctx.fillRect(0, -5, 1, 1);

            // Whiskers
            ctx.fillStyle = BH;
            ctx.fillRect(-8, -7, 2, 1);
            ctx.fillRect(6, -7, 2, 1);
            ctx.fillRect(-8, -5, 2, 1);
            ctx.fillRect(6, -5, 2, 1);

        } else {
            // === WALKING SIDE VIEW (original) ===
            // Tail (stands up, sways)
            ctx.fillStyle = BM;
            ctx.fillRect(-9, -1, 2, 2);
            ctx.fillRect(-10, -4, 2, 4);
            ctx.fillRect(-10, -7 + Math.round(tailSway), 2, 4);
            ctx.fillRect(-10, -10 + Math.round(tailSway), 2, 4);
            ctx.fillStyle = BD;
            ctx.fillRect(-10, -12 + Math.round(tailSway), 2, 3);
            ctx.fillRect(-9, -13 + Math.round(tailSway), 2, 2);

            // Back legs (animated)
            ctx.fillStyle = BD;
            ctx.fillRect(-4, 4 - walk, 2, 4);
            ctx.fillRect(-1, 4 + walk, 2, 4);
            ctx.fillStyle = BH;
            ctx.fillRect(-5, 7 - walk, 3, 2);
            ctx.fillRect(-2, 7 + walk, 3, 2);

            // Body (rounded, no outlines)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -4, 16, 10);
            ctx.fillRect(-6, -5, 14, 12);
            ctx.fillStyle = BM;
            ctx.fillRect(-5, -3, 14, 8);
            ctx.fillRect(-6, -2, 14, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(-3, -3, 10, 4);
            // Fur texture
            ctx.fillStyle = FUR;
            ctx.fillRect(-1, -2, 2, 1);
            ctx.fillRect(4, -1, 2, 1);
            ctx.fillRect(-4, 1, 1, 2);
            // White chest spot
            ctx.fillStyle = WC;
            ctx.fillRect(2, 1, 3, 3);
            ctx.fillStyle = WC2;
            ctx.fillRect(3, 2, 1, 1);
            // Breathing
            ctx.fillStyle = BM;
            ctx.fillRect(-6, 3 + Math.round(breathe), 14, 1);

            // Front legs (animated)
            ctx.fillStyle = BD;
            ctx.fillRect(5, 4 + walk, 2, 4);
            ctx.fillRect(7, 4 - walk, 2, 4);
            ctx.fillStyle = BH;
            ctx.fillRect(4, 7 + walk, 3, 2);
            ctx.fillRect(6, 7 - walk, 3, 2);

            // Head (big, rounded)
            ctx.fillStyle = BD;
            ctx.fillRect(6, -10, 12, 10);
            ctx.fillRect(5, -9, 14, 8);
            ctx.fillRect(7, -11, 10, 12);
            ctx.fillStyle = BM;
            ctx.fillRect(7, -9, 10, 8);
            ctx.fillRect(6, -8, 12, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(8, -9, 8, 4);
            ctx.fillStyle = BH;
            ctx.fillRect(9, -9, 5, 2);

            // Ears (with twitch animation)
            ctx.fillStyle = BD;
            ctx.fillRect(6, -14 - earTwitch, 3, 5);
            ctx.fillRect(7, -16 - earTwitch, 2, 3);
            ctx.fillRect(12, -14 - earTwitch, 3, 5);
            ctx.fillRect(13, -16 - earTwitch, 2, 3);
            ctx.fillStyle = PK;
            ctx.fillRect(7, -13 - earTwitch, 2, 3);
            ctx.fillRect(13, -13 - earTwitch, 2, 3);

            // Eye
            if (this._blinking) {
                ctx.fillStyle = EY;
                ctx.fillRect(13, -6, 3, 1);
            } else {
                ctx.fillStyle = EY;
                ctx.fillRect(13, -7, 3, 3);
                ctx.fillStyle = PU;
                ctx.fillRect(14, -7, 1, 2);
                ctx.fillStyle = '#fff';
                ctx.fillRect(13, -7, 1, 1);
            }

            // Nose
            ctx.fillStyle = PK;
            ctx.fillRect(17, -4, 2, 1);

            // Whiskers
            ctx.fillStyle = BH;
            ctx.fillRect(18, -5, 2, 1);
            ctx.fillRect(18, -3, 2, 1);
        }
    }

    _drawPug() {
        // Pug dog: fawn body, dark mask, curly tail, stubby, soft 2D style
        var BF = '#d4a86a';  // fawn body
        var BD = '#b8904e';  // body dark
        var BL = '#e0be82';  // body light
        var BH = '#ecd09a';  // highlight
        var MK = '#4a3828';  // mask (dark face)
        var MKL = '#5c4a38'; // mask lighter
        var NOS = '#2a1a10'; // nose
        var EY = '#2a1810';  // eye dark
        var WH = '#fff';
        var PNK = '#d08080'; // tongue pink
        var walk = this.isMoving ? Math.floor(Math.sin(this.tick * 0.3) * 2) : 0;
        var tailWag = Math.sin(this.tick * 0.25) * 2;
        var breathe = Math.sin(this.tick * 0.06) * 0.5;
        var earFlop = Math.sin(this.tick * 0.08) * 0.5;
        var pant = this.isMoving ? Math.abs(Math.sin(this.tick * 0.2)) : 0;
        var isSleeping = this.state === 'sleeping';
        var isSitting = this.state === 'sitting' || this.state === 'being_pet' || this.state === 'looking_around';
        var isGrooming = this.state === 'grooming';

        // Shadow
        ctx.fillStyle = 'rgba(50,30,10,0.12)';
        ctx.fillRect(-9, 9, 18, 3);
        ctx.fillRect(-7, 10, 14, 2);

        if (isSleeping) {
            // === SLEEPING — lying on side, head on paws ===
            // Body (flat, lying sideways)
            ctx.fillStyle = BD;
            ctx.fillRect(-2, 0, 12, 7);
            ctx.fillRect(-1, -1, 10, 9);
            ctx.fillStyle = BF;
            ctx.fillRect(0, 1, 8, 5);
            ctx.fillStyle = BL;
            ctx.fillRect(1, 2, 6, 3);
            // Belly
            ctx.fillStyle = BH;
            ctx.fillRect(2, 4, 4, 2);
            // Breathing
            ctx.fillStyle = BF;
            ctx.fillRect(-1, 6 + Math.round(breathe), 10, 1);

            // Head (distinct, resting to the left — big round pug head)
            ctx.fillStyle = BF;
            ctx.fillRect(-11, -4, 10, 9);
            ctx.fillRect(-10, -5, 8, 11);
            ctx.fillStyle = BL;
            ctx.fillRect(-9, -4, 6, 4);
            // Dark mask on face
            ctx.fillStyle = MK;
            ctx.fillRect(-10, -2, 8, 5);
            ctx.fillRect(-9, -3, 6, 7);
            ctx.fillStyle = MKL;
            ctx.fillRect(-8, -1, 5, 3);

            // Floppy ears
            ctx.fillStyle = MK;
            ctx.fillRect(-11, -5, 3, 3);
            ctx.fillRect(-5, -5, 3, 3);

            // Eyes closed (happy arches — clearly visible)
            ctx.fillStyle = BF;
            ctx.fillRect(-9, -1, 3, 1);
            ctx.fillRect(-8, -2, 1, 1);
            ctx.fillRect(-5, -1, 3, 1);
            ctx.fillRect(-4, -2, 1, 1);

            // Nose
            ctx.fillStyle = NOS;
            ctx.fillRect(-7, 1, 2, 1);

            // Front paws (stretched under chin)
            ctx.fillStyle = BD;
            ctx.fillRect(-10, 4, 3, 2);
            ctx.fillRect(-6, 4, 3, 2);
            ctx.fillStyle = BL;
            ctx.fillRect(-9, 4, 1, 1);
            ctx.fillRect(-5, 4, 1, 1);

            // Curly tail behind
            ctx.fillStyle = BF;
            ctx.fillRect(9, 1, 2, 2);
            ctx.fillRect(10, -1, 2, 2);
            ctx.fillRect(9, -2, 2, 2);
            return;
        }

        if (isSitting) {
            // === SITTING — front-facing ===
            // Body
            ctx.fillStyle = BD;
            ctx.fillRect(-6, 0, 12, 9);
            ctx.fillRect(-7, 1, 14, 7);
            ctx.fillStyle = BF;
            ctx.fillRect(-5, 1, 10, 7);
            ctx.fillRect(-6, 2, 12, 5);
            ctx.fillStyle = BL;
            ctx.fillRect(-4, 2, 8, 4);
            // Belly
            ctx.fillStyle = BH;
            ctx.fillRect(-3, 4, 6, 3);
            // Breathing
            ctx.fillStyle = BF;
            ctx.fillRect(-6 + Math.round(breathe * 0.5), 7, 1, 1);
            ctx.fillRect(5 - Math.round(breathe * 0.5), 7, 1, 1);

            // Head (big, round, dark mask)
            ctx.fillStyle = BF;
            ctx.fillRect(-7, -11, 14, 12);
            ctx.fillRect(-8, -10, 16, 10);
            ctx.fillStyle = BL;
            ctx.fillRect(-6, -11, 12, 5);
            // Forehead wrinkles
            ctx.fillStyle = BD;
            ctx.fillRect(-4, -9, 8, 1);
            ctx.fillRect(-3, -7, 6, 1);
            // Dark mask around eyes/nose
            ctx.fillStyle = MK;
            ctx.fillRect(-6, -7, 12, 6);
            ctx.fillRect(-5, -8, 10, 8);
            ctx.fillStyle = MKL;
            ctx.fillRect(-4, -6, 8, 4);

            // Ears (floppy, dark)
            ctx.fillStyle = MK;
            ctx.fillRect(-9, -10 + Math.round(earFlop), 3, 5);
            ctx.fillRect(6, -10 - Math.round(earFlop), 3, 5);
            ctx.fillStyle = MKL;
            ctx.fillRect(-8, -9 + Math.round(earFlop), 2, 3);
            ctx.fillRect(6, -9 - Math.round(earFlop), 2, 3);

            // Eyes (big, round, shiny)
            if (this._blinking) {
                ctx.fillStyle = NOS;
                ctx.fillRect(-4, -5, 3, 1);
                ctx.fillRect(1, -5, 3, 1);
            } else {
                ctx.fillStyle = WH;
                ctx.fillRect(-5, -6, 4, 3);
                ctx.fillRect(1, -6, 4, 3);
                ctx.fillStyle = EY;
                ctx.fillRect(-4, -6, 2, 2);
                ctx.fillRect(2, -6, 2, 2);
                ctx.fillStyle = WH;
                ctx.fillRect(-5, -6, 1, 1);
                ctx.fillRect(1, -6, 1, 1);
                // Pupil looking around
                if (this.state === 'looking_around') {
                    var ld = Math.sin(this.tick * 0.05) > 0 ? 1 : 0;
                    ctx.fillStyle = EY;
                    ctx.fillRect(-4 + ld, -6, 2, 2);
                    ctx.fillRect(2 + ld, -6, 2, 2);
                }
            }

            // Nose (wide flat pug nose)
            ctx.fillStyle = NOS;
            ctx.fillRect(-2, -3, 4, 2);
            ctx.fillRect(-1, -4, 2, 1);
            // Nostrils
            ctx.fillStyle = MK;
            ctx.fillRect(-1, -3, 1, 1);
            ctx.fillRect(1, -3, 1, 1);

            // Mouth / tongue
            ctx.fillStyle = MK;
            ctx.fillRect(-2, -1, 4, 1);
            // Tongue out when being pet or happy
            if (this.state === 'being_pet' || pant > 0.3) {
                ctx.fillStyle = PNK;
                ctx.fillRect(-1, -1, 2, 2);
                ctx.fillRect(0, 1, 1, 1);
            }

            // Paws
            ctx.fillStyle = BD;
            ctx.fillRect(-4, 8, 3, 2);
            ctx.fillRect(1, 8, 3, 2);
            ctx.fillStyle = BL;
            ctx.fillRect(-3, 8, 2, 1);
            ctx.fillRect(2, 8, 2, 1);

            // Curly tail (behind, wagging)
            ctx.fillStyle = BF;
            ctx.fillRect(6, 3, 2, 2);
            ctx.fillRect(7, 1 + Math.round(tailWag * 0.5), 2, 2);
            ctx.fillRect(7, -1 + Math.round(tailWag), 2, 2);
            ctx.fillStyle = BD;
            ctx.fillRect(6, -2 + Math.round(tailWag), 2, 2);
            ctx.fillRect(5, -2 + Math.round(tailWag), 2, 1);
            return;
        }

        if (isGrooming) {
            // === GROOMING — scratching ear with back leg ===
            ctx.fillStyle = BD;
            ctx.fillRect(-6, 0, 12, 9);
            ctx.fillRect(-7, 1, 14, 7);
            ctx.fillStyle = BF;
            ctx.fillRect(-5, 1, 10, 7);
            ctx.fillStyle = BH;
            ctx.fillRect(-3, 4, 6, 3);

            // Head tilted
            ctx.fillStyle = BF;
            ctx.fillRect(-3, -10, 12, 10);
            ctx.fillRect(-4, -9, 13, 8);
            ctx.fillStyle = MK;
            ctx.fillRect(-1, -6, 10, 5);
            ctx.fillStyle = MKL;
            ctx.fillRect(0, -5, 8, 3);

            // Ear
            ctx.fillStyle = MK;
            ctx.fillRect(-3, -9, 3, 4);
            ctx.fillRect(7, -9, 3, 4);

            // Eyes closed happy
            ctx.fillStyle = NOS;
            ctx.fillRect(1, -4, 2, 1);
            ctx.fillRect(5, -4, 2, 1);

            // Back leg raised scratching ear
            var scratchBob = Math.floor(Math.sin(this.tick * 0.3) * 1);
            ctx.fillStyle = BF;
            ctx.fillRect(8, -7 + scratchBob, 3, 3);
            ctx.fillStyle = BD;
            ctx.fillRect(9, -8 + scratchBob, 2, 2);

            // Front paws
            ctx.fillStyle = BD;
            ctx.fillRect(-4, 8, 3, 2);
            ctx.fillRect(1, 8, 3, 2);

            // Tail
            ctx.fillStyle = BF;
            ctx.fillRect(6, 3, 2, 2);
            ctx.fillRect(7, 1, 2, 2);
            return;
        }

        // === WALKING ===
        if (this.moveDir === 'up') {
            // === WALKING UP — rear view (pug butt facing camera) ===
            // Curly tail (centered on top, wagging)
            ctx.fillStyle = BF;
            ctx.fillRect(-1, -6, 2, 3);
            ctx.fillRect(-2, -8 + Math.round(tailWag * 0.5), 2, 3);
            ctx.fillStyle = BD;
            ctx.fillRect(-2, -10 + Math.round(tailWag), 3, 3);
            ctx.fillRect(-1, -11 + Math.round(tailWag), 2, 2);

            // Body (rounded from behind)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -4, 14, 11);
            ctx.fillRect(-8, -3, 16, 9);
            ctx.fillStyle = BF;
            ctx.fillRect(-6, -3, 12, 9);
            ctx.fillRect(-7, -2, 14, 7);
            ctx.fillStyle = BL;
            ctx.fillRect(-5, -3, 10, 5);

            // Back legs (animated)
            ctx.fillStyle = BD;
            ctx.fillRect(-6, 5 - walk, 3, 5);
            ctx.fillRect(3, 5 + walk, 3, 5);
            ctx.fillStyle = BL;
            ctx.fillRect(-6, 8 - walk, 3, 2);
            ctx.fillRect(3, 8 + walk, 3, 2);

            // Head (back of head — round, fawn, ears floppy)
            ctx.fillStyle = BF;
            ctx.fillRect(-5, -11, 10, 8);
            ctx.fillRect(-6, -10, 12, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(-4, -11, 8, 4);
            // Back of head wrinkles
            ctx.fillStyle = BD;
            ctx.fillRect(-3, -9, 6, 1);

            // Ears (floppy, from behind)
            ctx.fillStyle = MK;
            ctx.fillRect(-7, -10 + Math.round(earFlop), 3, 4);
            ctx.fillRect(4, -10 - Math.round(earFlop), 3, 4);

        } else if (this.moveDir === 'down') {
            // === WALKING DOWN — front view (face toward camera) ===
            // Tail peeking behind
            ctx.fillStyle = BF;
            ctx.fillRect(5, -2, 2, 2);
            ctx.fillRect(6, -4 + Math.round(tailWag * 0.5), 2, 2);
            ctx.fillStyle = BD;
            ctx.fillRect(6, -6 + Math.round(tailWag), 2, 2);

            // Body
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -3, 14, 11);
            ctx.fillRect(-8, -2, 16, 9);
            ctx.fillStyle = BF;
            ctx.fillRect(-6, -2, 12, 9);
            ctx.fillRect(-7, -1, 14, 7);
            ctx.fillStyle = BL;
            ctx.fillRect(-5, -2, 10, 5);
            // Belly
            ctx.fillStyle = BH;
            ctx.fillRect(-3, 2, 6, 3);

            // Front legs (animated)
            ctx.fillStyle = BD;
            ctx.fillRect(-5, 6 + walk, 3, 5);
            ctx.fillRect(2, 6 - walk, 3, 5);
            ctx.fillStyle = BL;
            ctx.fillRect(-5, 9 + walk, 3, 2);
            ctx.fillRect(2, 9 - walk, 3, 2);

            // Head (big, round, flat-faced, mask)
            ctx.fillStyle = BF;
            ctx.fillRect(-7, -12, 14, 10);
            ctx.fillRect(-8, -11, 16, 8);
            ctx.fillStyle = BL;
            ctx.fillRect(-6, -12, 12, 4);
            // Forehead wrinkles
            ctx.fillStyle = BD;
            ctx.fillRect(-4, -10, 8, 1);
            ctx.fillRect(-3, -8, 6, 1);
            // Dark mask
            ctx.fillStyle = MK;
            ctx.fillRect(-6, -8, 12, 6);
            ctx.fillRect(-5, -9, 10, 8);
            ctx.fillStyle = MKL;
            ctx.fillRect(-4, -7, 8, 4);

            // Ears (floppy)
            ctx.fillStyle = MK;
            ctx.fillRect(-9, -11 + Math.round(earFlop), 3, 5);
            ctx.fillRect(6, -11 - Math.round(earFlop), 3, 5);
            ctx.fillStyle = MKL;
            ctx.fillRect(-8, -10 + Math.round(earFlop), 2, 3);
            ctx.fillRect(6, -10 - Math.round(earFlop), 2, 3);

            // Eyes
            if (this._blinking) {
                ctx.fillStyle = NOS;
                ctx.fillRect(-4, -6, 3, 1);
                ctx.fillRect(1, -6, 3, 1);
            } else {
                ctx.fillStyle = WH;
                ctx.fillRect(-5, -7, 4, 3);
                ctx.fillRect(1, -7, 4, 3);
                ctx.fillStyle = EY;
                ctx.fillRect(-4, -7, 2, 2);
                ctx.fillRect(2, -7, 2, 2);
                ctx.fillStyle = WH;
                ctx.fillRect(-5, -7, 1, 1);
                ctx.fillRect(1, -7, 1, 1);
            }

            // Nose
            ctx.fillStyle = NOS;
            ctx.fillRect(-2, -4, 4, 2);
            ctx.fillRect(-1, -5, 2, 1);
            ctx.fillStyle = MK;
            ctx.fillRect(-1, -4, 1, 1);
            ctx.fillRect(1, -4, 1, 1);

            // Tongue out when panting
            if (pant > 0.3) {
                ctx.fillStyle = PNK;
                ctx.fillRect(-1, -2, 2, 2);
                ctx.fillRect(0, 0, 1, 1);
            }

        } else {
            // === WALKING SIDE VIEW (original) ===
            // Curly tail (stands up, wags)
            ctx.fillStyle = BF;
            ctx.fillRect(-9, -1, 2, 2);
            ctx.fillRect(-9, -4 + Math.round(tailWag * 0.5), 2, 3);
            ctx.fillStyle = BD;
            ctx.fillRect(-9, -6 + Math.round(tailWag), 2, 3);
            ctx.fillRect(-8, -7 + Math.round(tailWag), 2, 2);
            ctx.fillRect(-7, -7 + Math.round(tailWag), 2, 1);

            // Back legs
            ctx.fillStyle = BD;
            ctx.fillRect(-4, 4 - walk, 2, 4);
            ctx.fillRect(-1, 4 + walk, 2, 4);
            ctx.fillStyle = BL;
            ctx.fillRect(-5, 7 - walk, 3, 2);
            ctx.fillRect(-2, 7 + walk, 3, 2);

            // Body (chunky, rounded)
            ctx.fillStyle = BD;
            ctx.fillRect(-7, -4, 16, 10);
            ctx.fillRect(-6, -5, 14, 12);
            ctx.fillStyle = BF;
            ctx.fillRect(-5, -3, 14, 8);
            ctx.fillRect(-6, -2, 14, 6);
            ctx.fillStyle = BL;
            ctx.fillRect(-3, -3, 10, 4);
            // Belly
            ctx.fillStyle = BH;
            ctx.fillRect(-1, 2, 6, 2);
            // Breathing
            ctx.fillStyle = BF;
            ctx.fillRect(-6, 3 + Math.round(breathe), 14, 1);

            // Front legs
            ctx.fillStyle = BD;
            ctx.fillRect(5, 4 + walk, 2, 4);
            ctx.fillRect(7, 4 - walk, 2, 4);
            ctx.fillStyle = BL;
            ctx.fillRect(4, 7 + walk, 3, 2);
            ctx.fillRect(6, 7 - walk, 3, 2);

            // Head (big, flat-faced, dark mask)
            ctx.fillStyle = BF;
            ctx.fillRect(6, -10, 12, 10);
            ctx.fillRect(5, -9, 14, 8);
            ctx.fillRect(7, -11, 10, 12);
            ctx.fillStyle = BL;
            ctx.fillRect(8, -10, 8, 4);
            // Forehead wrinkle
            ctx.fillStyle = BD;
            ctx.fillRect(9, -8, 6, 1);
            // Dark mask
            ctx.fillStyle = MK;
            ctx.fillRect(8, -7, 10, 6);
            ctx.fillRect(7, -6, 12, 4);
            ctx.fillStyle = MKL;
            ctx.fillRect(9, -6, 8, 3);

            // Ear (floppy, dark)
            ctx.fillStyle = MK;
            ctx.fillRect(6, -10 + Math.round(earFlop), 3, 4);
            ctx.fillStyle = MKL;
            ctx.fillRect(7, -9 + Math.round(earFlop), 2, 2);

            // Eye
            if (this._blinking) {
                ctx.fillStyle = NOS;
                ctx.fillRect(14, -5, 3, 1);
            } else {
                ctx.fillStyle = WH;
                ctx.fillRect(13, -6, 3, 3);
                ctx.fillStyle = EY;
                ctx.fillRect(14, -6, 2, 2);
                ctx.fillStyle = WH;
                ctx.fillRect(13, -6, 1, 1);
            }

            // Nose (flat)
            ctx.fillStyle = NOS;
            ctx.fillRect(17, -3, 2, 2);
            ctx.fillRect(16, -2, 1, 1);

            // Tongue out when walking (panting)
            if (pant > 0.3) {
                ctx.fillStyle = PNK;
                ctx.fillRect(17, -1, 2, 2);
                ctx.fillRect(18, 1, 1, 1);
            }
        }
    }

    _drawLobster() {
        // Soft 2D style, no black outlines, rounded, matches office style
        var R = '#d94030';   // main red
        var RD = '#b82820';  // dark red
        var RL = '#e85848';  // light red
        var RR = '#f07060';  // bright highlight
        var RB = '#9a2018';  // darkest / shadow
        var GD = '#d0a030';  // gold feet
        var WH = '#fff';
        var walk = this.isMoving ? Math.floor(Math.sin(this.tick * 0.25) * 2) : 0;
        var clawOpen = Math.sin(this.tick * 0.12) * 1.5;
        var antennaWave = Math.sin(this.tick * 0.08) * 3;
        var breathe = Math.sin(this.tick * 0.06) * 0.5;
        var isSleeping = this.state === 'sleeping';
        var isSitting = this.state === 'sitting' || this.state === 'being_pet' || this.state === 'looking_around' || this.state === 'grooming';

        // Shadow
        ctx.fillStyle = 'rgba(30,10,10,0.12)';
        ctx.fillRect(-9, 11, 18, 3);
        ctx.fillRect(-7, 12, 14, 2);

        if (isSleeping) {
            // === SLEEPING — lying on side, head visible with closed eyes ===
            // Tail behind
            ctx.fillStyle = RD;
            ctx.fillRect(-14, 1, 4, 3);
            ctx.fillStyle = R;
            ctx.fillRect(-17, 2, 4, 2);
            ctx.fillRect(-19, 2, 3, 2);

            // Body (segmented, lying flat)
            ctx.fillStyle = RD;
            ctx.fillRect(-6, 0, 14, 7);
            ctx.fillRect(-5, -1, 12, 9);
            ctx.fillStyle = R;
            ctx.fillRect(-4, 1, 10, 5);
            ctx.fillStyle = RL;
            ctx.fillRect(-3, 1, 8, 2);
            // Segments
            ctx.fillStyle = RD;
            ctx.fillRect(-1, 0, 1, 7);
            ctx.fillRect(3, 0, 1, 7);
            // Legs tucked (red)
            ctx.fillStyle = RD;
            ctx.fillRect(-3, 6, 3, 2);
            ctx.fillRect(1, 6, 3, 2);
            ctx.fillRect(5, 6, 3, 2);

            // Head (distinct, round, resting to the right)
            ctx.fillStyle = RD;
            ctx.fillRect(7, -3, 9, 8);
            ctx.fillRect(8, -4, 7, 10);
            ctx.fillStyle = R;
            ctx.fillRect(9, -2, 5, 6);
            ctx.fillRect(8, -1, 7, 4);
            ctx.fillStyle = RL;
            ctx.fillRect(9, -2, 4, 2);

            // Eyes closed (happy arches)
            ctx.fillStyle = '#fff';
            ctx.fillRect(9, 0, 2, 1);
            ctx.fillRect(10, -1, 1, 1);
            ctx.fillRect(13, 0, 2, 1);
            ctx.fillRect(14, -1, 1, 1);

            // Mouth (happy)
            ctx.fillStyle = RB;
            ctx.fillRect(11, 2, 2, 1);

            // Claw resting in front
            ctx.fillStyle = R;
            ctx.fillRect(14, 3, 4, 3);
            ctx.fillRect(15, 2, 3, 2);
            ctx.fillStyle = RL;
            ctx.fillRect(15, 3, 2, 1);

            // Antennae drooped
            ctx.fillStyle = RD;
            ctx.fillRect(10, -5, 2, 2);
            ctx.fillRect(13, -5, 2, 2);
            return;
        }

        if (isSitting) {
            // === SITTING — front-facing, claws up ===
            // Legs (red, chunky)
            ctx.fillStyle = RD;
            ctx.fillRect(-5, 6, 3, 4);
            ctx.fillRect(0, 6, 3, 4);
            ctx.fillRect(4, 6, 3, 4);
            ctx.fillStyle = R;
            ctx.fillRect(-5, 9, 3, 2);
            ctx.fillRect(0, 9, 3, 2);
            ctx.fillRect(4, 9, 3, 2);

            // Body (rounded)
            ctx.fillStyle = RD;
            ctx.fillRect(-7, -3, 15, 10);
            ctx.fillRect(-6, -4, 13, 12);
            ctx.fillStyle = R;
            ctx.fillRect(-5, -2, 11, 8);
            ctx.fillRect(-6, -1, 13, 6);
            ctx.fillStyle = RL;
            ctx.fillRect(-4, -2, 9, 3);
            ctx.fillStyle = RR;
            ctx.fillRect(-2, -2, 4, 1);
            // Segments
            ctx.fillStyle = RD;
            ctx.fillRect(-5, 0, 11, 1);
            ctx.fillRect(-5, 3, 11, 1);
            // Breathing
            ctx.fillStyle = R;
            ctx.fillRect(-6 + Math.round(breathe * 0.5), 5, 1, 2);

            // Head (rounded)
            ctx.fillStyle = RD;
            ctx.fillRect(-6, -11, 13, 9);
            ctx.fillRect(-5, -12, 11, 10);
            ctx.fillStyle = R;
            ctx.fillRect(-4, -10, 9, 7);
            ctx.fillRect(-5, -9, 11, 5);
            ctx.fillStyle = RL;
            ctx.fillRect(-3, -10, 7, 3);

            // Eyes
            if (this._blinking) {
                ctx.fillStyle = RB;
                ctx.fillRect(-3, -7, 3, 1);
                ctx.fillRect(2, -7, 3, 1);
            } else {
                ctx.fillStyle = WH;
                ctx.fillRect(-4, -8, 3, 3);
                ctx.fillRect(2, -8, 3, 3);
                ctx.fillStyle = '#111';
                ctx.fillRect(-3, -8, 2, 2);
                ctx.fillRect(3, -8, 2, 2);
                ctx.fillStyle = WH;
                ctx.fillRect(-4, -8, 1, 1);
                ctx.fillRect(2, -8, 1, 1);
                // Looking around
                if (this.state === 'looking_around') {
                    var ld = Math.sin(this.tick * 0.05) > 0 ? 1 : 0;
                    ctx.fillStyle = '#111';
                    ctx.fillRect(-3 + ld, -8, 2, 2);
                    ctx.fillRect(3 + ld, -8, 2, 2);
                }
            }

            // Mouth
            ctx.fillStyle = RB;
            ctx.fillRect(-1, -4, 3, 1);

            // Antennae (no outline, just colored)
            ctx.fillStyle = RD;
            ctx.fillRect(-3, -14 + Math.round(antennaWave * 0.3), 2, 4);
            ctx.fillRect(-4, -17 + Math.round(antennaWave * 0.5), 2, 4);
            ctx.fillRect(3, -14 - Math.round(antennaWave * 0.3), 2, 4);
            ctx.fillRect(4, -17 - Math.round(antennaWave * 0.5), 2, 4);

            // Arms + claws (held up)
            ctx.fillStyle = R;
            ctx.fillRect(-10, -3, 4, 4);
            ctx.fillRect(7, -3, 4, 4);
            // Left claw (medium)
            ctx.fillStyle = R;
            ctx.fillRect(-15, -8, 6, 5);
            ctx.fillRect(-14, -2, 5, 3);
            ctx.fillStyle = RL;
            ctx.fillRect(-14, -7, 4, 2);
            ctx.fillStyle = RR;
            ctx.fillRect(-13, -7, 2, 1);
            // Right claw (big one, higher)
            ctx.fillStyle = R;
            ctx.fillRect(8, -14, 8, 7);
            ctx.fillRect(9, -6, 7, 4);
            ctx.fillStyle = RL;
            ctx.fillRect(9, -13, 5, 3);
            ctx.fillStyle = RR;
            ctx.fillRect(10, -13, 3, 1);
            ctx.fillStyle = '#fff';
            ctx.fillRect(11, -12, 1, 1);
            return;
        }

        // === WALKING — front-facing with bounce ===
        // Legs (animated, red, chunky)
        ctx.fillStyle = RD;
        ctx.fillRect(-5, 6 + walk, 3, 4);
        ctx.fillRect(0, 6 - walk, 3, 4);
        ctx.fillRect(4, 6 + walk, 3, 4);
        ctx.fillStyle = R;
        ctx.fillRect(-5, 9 + walk, 3, 2);
        ctx.fillRect(0, 9 - walk, 3, 2);
        ctx.fillRect(4, 9 + walk, 3, 2);

        // Body (rounded)
        ctx.fillStyle = RD;
        ctx.fillRect(-7, -3, 15, 10);
        ctx.fillRect(-6, -4, 13, 12);
        ctx.fillStyle = R;
        ctx.fillRect(-5, -2, 11, 8);
        ctx.fillRect(-6, -1, 13, 6);
        ctx.fillStyle = RL;
        ctx.fillRect(-4, -2, 9, 3);
        ctx.fillStyle = RR;
        ctx.fillRect(-2, -2, 4, 1);
        // Segments
        ctx.fillStyle = RD;
        ctx.fillRect(-5, 0, 11, 1);
        ctx.fillRect(-5, 3, 11, 1);

        // Head (rounded)
        ctx.fillStyle = RD;
        ctx.fillRect(-6, -11, 13, 9);
        ctx.fillRect(-5, -12, 11, 10);
        ctx.fillStyle = R;
        ctx.fillRect(-4, -10, 9, 7);
        ctx.fillRect(-5, -9, 11, 5);
        ctx.fillStyle = RL;
        ctx.fillRect(-3, -10, 7, 3);

        // Eyes
        if (this._blinking) {
            ctx.fillStyle = RB;
            ctx.fillRect(-3, -7, 3, 1);
            ctx.fillRect(2, -7, 3, 1);
        } else {
            ctx.fillStyle = WH;
            ctx.fillRect(-4, -8, 3, 3);
            ctx.fillRect(2, -8, 3, 3);
            ctx.fillStyle = '#111';
            ctx.fillRect(-3, -8, 2, 2);
            ctx.fillRect(3, -8, 2, 2);
            ctx.fillStyle = WH;
            ctx.fillRect(-4, -8, 1, 1);
            ctx.fillRect(2, -8, 1, 1);
        }

        // Mouth
        ctx.fillStyle = RB;
        ctx.fillRect(-1, -4, 3, 1);

        // Antennae (swaying)
        ctx.fillStyle = RD;
        ctx.fillRect(-3, -14 + Math.round(antennaWave * 0.3), 2, 4);
        ctx.fillRect(-4, -18 + Math.round(antennaWave * 0.5), 2, 5);
        ctx.fillRect(-5, -21 + Math.round(antennaWave * 0.7), 2, 4);
        ctx.fillRect(3, -14 - Math.round(antennaWave * 0.3), 2, 4);
        ctx.fillRect(4, -18 - Math.round(antennaWave * 0.5), 2, 5);
        ctx.fillRect(5, -21 - Math.round(antennaWave * 0.7), 2, 4);

        // Arms + claws (bob with walk)
        ctx.fillStyle = R;
        ctx.fillRect(-10, -4 + Math.round(walk * 0.3), 4, 4);
        ctx.fillRect(7, -4 - Math.round(walk * 0.3), 4, 4);
        // Left claw (medium, animated open)
        ctx.fillStyle = R;
        ctx.fillRect(-16, -9 - Math.round(clawOpen) + Math.round(walk * 0.3), 6, 5);
        ctx.fillRect(-15, -3 + Math.round(clawOpen) + Math.round(walk * 0.3), 5, 3);
        ctx.fillStyle = RL;
        ctx.fillRect(-15, -8 - Math.round(clawOpen) + Math.round(walk * 0.3), 4, 2);
        ctx.fillStyle = RR;
        ctx.fillRect(-14, -8 - Math.round(clawOpen) + Math.round(walk * 0.3), 2, 1);
        // Right claw (big, held higher)
        ctx.fillStyle = R;
        ctx.fillRect(9, -15 - Math.round(clawOpen) - Math.round(walk * 0.3), 8, 6);
        ctx.fillRect(10, -8 + Math.round(clawOpen) - Math.round(walk * 0.3), 7, 4);
        ctx.fillStyle = RL;
        ctx.fillRect(10, -14 - Math.round(clawOpen) - Math.round(walk * 0.3), 5, 3);
        ctx.fillStyle = RR;
        ctx.fillRect(11, -14 - Math.round(clawOpen) - Math.round(walk * 0.3), 3, 1);
        ctx.fillStyle = '#fff';
        ctx.fillRect(12, -13 - Math.round(clawOpen) - Math.round(walk * 0.3), 1, 1);
    }
}

// Agent interaction with pet — inject into idle behavior
function _maybePetInteraction(agent) {
    if (officePets.length === 0) return false;
    if (agent.state !== 'idle' || agent._petCooldown > 0) return false;
    var pet = officePets[0];
    if (pet.state === 'sleeping' || pet.state === 'being_pet' || pet.state === 'chased') return false;

    var dx = agent.x - pet.x, dy = agent.y - pet.y;
    var dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > 80) return false; // too far

    var roll = Math.random();
    if (roll < 0.02) {
        // Pet the animal
        agent.idleAction = 'petting';
        agent.targetX = pet.x + (agent.x > pet.x ? 15 : -15);
        agent.targetY = pet.y;
        agent.idleReturnTimer = 100;
        agent.addIntent('Petting ' + pet.name);
        pet.startBeingPet(agent);
        agent._petCooldown = 600;
        return true;
    } else if (roll < 0.03) {
        // Chase the pet playfully
        agent.idleAction = 'chasing_pet';
        agent.idleReturnTimer = 120;
        agent.addIntent('Chasing ' + pet.name + '!');
        pet.startChase(agent);
        agent._petCooldown = 800;
        return true;
    }
    return false;
}

function updatePets() {
    officePets.forEach(function(p) { p.update(); });
    // Update agent chase targets
    officePets.forEach(function(pet) {
        if (pet.state === 'chased' && pet.interactingAgent) {
            var agent = pet.interactingAgent;
            if (agent.idleAction === 'chasing_pet') {
                agent.targetX = pet.x;
                agent.targetY = pet.y;
            }
        }
    });
}

function drawPets() {
    officePets.forEach(function(p) { p.draw(); });
}

function loop() {
    // Update ambient light cache once per frame
    _updateAmbientCache();
    // Clear entire canvas
    ctx.fillStyle = '#263238';
    ctx.fillRect(0, 0, displayW, displayH);

    // Draw world objects with camera
    ctx.save();
    applyCameraTransform();
    // Clip to world bounds so nothing draws outside
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, W, H);
    ctx.clip();
    _perfStart('environment'); drawEnvironment(); _perfEnd('environment');
    _rimFrame++;

    // ─── Z-ORDER FIX: Split desk char items into behind-wall vs normal ───
    // Desk char items for desks NOT behind walls are drawn here (before occluders,
    // they'll be covered if near a wall, but that's handled in the front-of-wall redraw).
    // Desk char items for desks BEHIND walls are drawn with the behind-wall agents.
    _perfStart('deskItems');
    var _behindWallDesks = []; // agents whose desks are behind a wall
    agents.forEach(a => {
        if (_isDeskBehindHorizontalWall(a.desk.x, a.desk.y)) {
            _behindWallDesks.push(a);
        } else {
            ctx.save();
            ctx.translate(a.desk.x, a.desk.y);
            a._drawDeskCharItem(ctx);
            ctx.restore();
        }
    });
    _perfEnd('deskItems');

    _perfStart('agents');
    agents.forEach(a => { a.update(); maybeThrowAirplane(a); maybeStartRPS(a); maybeStartSocial(a); maybeStartDarts(a); maybeStartPong(a); _maybePetInteraction(a); if (a._petCooldown > 0) a._petCooldown--; });
    updatePets();
    // Merge agents + pets into one list for proper Y-sorting
    var _allEntities = agents.concat(officePets);
    _allEntities.sort((a, b) => a.y - b.y);
    var _behindWalls = [];
    var _frontWalls = [];
    _allEntities.forEach(function(a) {
        if (_isAgentBehindHorizontalWall(a)) _behindWalls.push(a);
        else _frontWalls.push(a);
    });

    // ─── Draw behind-wall desk char items, then behind-wall agents ───
    // Both render BEFORE wall occluders, so they appear BEHIND the wall face.
    _behindWallDesks.forEach(function(a) {
        ctx.save();
        ctx.translate(a.desk.x, a.desk.y);
        a._drawDeskCharItem(ctx);
        ctx.restore();
    });
    _behindWalls.forEach(function(a) { a.draw(); });
    _perfEnd('agents');

    _perfStart('wallOccluders'); drawInteriorWallOccluders(); _perfEnd('wallOccluders');

    // Redraw vertical walls going down (they must stay on top of horizontal wall occluders)
    var _intWalls = (officeConfig.walls && officeConfig.walls.interior) || [];
    _intWalls.forEach(function(wall, idx) {
        if (wall.x1 === wall.x2 && _verticalWallGoesDown(wall, _intWalls)) {
            _drawSingleWall(wall, idx);
        }
    });

    // ─── Z-ORDER FIX: Only redraw furniture that is IN FRONT of walls ───
    // Furniture behind walls was already drawn in drawEnvironment() and stays
    // behind the wall occluder. Only furniture in front gets redrawn on top.
    officeConfig.furniture.forEach(function(item) {
        if (item.type === 'branchSign' || item.type === 'textLabel') return;
        if (item.type === 'wall' || item.type === 'door') return;
        if (_isFurnitureNearHorizontalWall(item) && _isFurnitureInFrontOfWall(item)) {
            drawFurnitureItem(item);
        }
    });

    // ─── Desk char items for IN-FRONT desks near walls also need redraw ───
    // (They were drawn before occluders, so they got covered by the wall face.
    // Redraw them now so they appear on top of the wall, matching their desk.)
    agents.forEach(function(a) {
        if (_behindWallDesks.indexOf(a) >= 0) return; // skip behind-wall desks
        // Find the furniture item for this desk
        var deskItem = officeConfig.furniture.find(function(f) {
            return (f.type === 'desk' || f.type === 'bossDesk') && f.x === a.desk.x && f.y === a.desk.y;
        });
        if (deskItem && _isFurnitureNearHorizontalWall(deskItem) && _isFurnitureInFrontOfWall(deskItem)) {
            ctx.save();
            ctx.translate(a.desk.x, a.desk.y);
            a._drawDeskCharItem(ctx);
            ctx.restore();
        }
    });

    // Labels on top of walls
    officeConfig.furniture.forEach(function(item) {
        if (item.type === 'branchSign' || item.type === 'textLabel') drawFurnitureItem(item);
    });
    // Ambient overlay AFTER wall occluders + redrawn furniture — everything gets uniform tint
    _perfStart('ambient'); drawAmbientOverlay(); _perfEnd('ambient');
    // (Legacy lamp/glow/neon functions removed — all now handled by furniture renderers)
    // Front agents drawn after ambient (they appear in front, un-tinted like before)
    _perfStart('agentsFront'); _frontWalls.forEach(function(a) { a.draw(); }); _perfEnd('agentsFront');
    // (drawAgentLampBounce removed — rim light now drawn inside agent draw())
    _perfStart('airplanes'); updateAirplanes(); drawAirplanes(); _perfEnd('airplanes');
    _perfStart('rps'); updateRPS(); drawRPS(); _perfEnd('rps');
    _perfStart('social'); updateSocialInteractions(); drawSocialInteractions(); _perfEnd('social');
    _perfStart('gatherings'); maybeStartGathering(); updateGatherings(); drawGatherings(); _perfEnd('gatherings');
    _perfStart('darts'); updateDartGames(); drawDartGames(); _perfEnd('darts');
    _perfStart('pong'); updatePongGames(); drawPongGames(); _perfEnd('pong');
    ctx.restore(); // close world clip
    ctx.restore(); // close camera transform

    ctx.save();
    applyCameraTransform();
    _perfStart('chatBubbles'); drawChatBubbles(); _perfEnd('chatBubbles');
    // Project work tooltip (rendered in world space, above chat bubble)
    if (_chatTooltip) {
        ctx.font = 'bold 8px Arial, sans-serif';
        var ttW = ctx.measureText(_chatTooltip.text).width + 8;
        var ttH = 14;
        var ttX = _chatTooltip.x - 2;
        var ttY = _chatTooltip.y;
        ctx.fillStyle = 'rgba(20,20,40,0.9)';
        ctx.fillRect(ttX, ttY, ttW, ttH);
        ctx.strokeStyle = 'rgba(100,140,255,0.6)';
        ctx.lineWidth = 0.5;
        ctx.strokeRect(ttX, ttY, ttW, ttH);
        ctx.fillStyle = '#dde';
        ctx.textAlign = 'left';
        ctx.fillText(_chatTooltip.text, ttX + 4, ttY + 10);
    }
    if (_floorWindowTooltip) {
        ctx.font = 'bold 8px Arial, sans-serif';
        var fwLines = _floorWindowTooltip.lines || [];
        var fwW = 0;
        for (var fwi = 0; fwi < fwLines.length; fwi++) fwW = Math.max(fwW, ctx.measureText(fwLines[fwi]).width);
        fwW = Math.max(96, fwW + 12);
        var fwH = 10 + fwLines.length * 11;
        var fwX = _floorWindowTooltip.x;
        var fwY = _floorWindowTooltip.y;
        ctx.fillStyle = 'rgba(20,20,40,0.92)';
        ctx.fillRect(fwX, fwY, fwW, fwH);
        ctx.strokeStyle = 'rgba(255,214,0,0.75)';
        ctx.lineWidth = 0.8;
        ctx.strokeRect(fwX, fwY, fwW, fwH);
        ctx.fillStyle = '#f5f7ff';
        ctx.textAlign = 'left';
        for (var fwl = 0; fwl < fwLines.length; fwl++) {
            ctx.fillText(fwLines[fwl], fwX + 6, fwY + 12 + fwl * 11);
        }
    }
    ctx.restore();

    // FPS counter
    _fpsFrames++;
    var _fpsNow = Date.now();
    if (_fpsNow - _fpsLast >= 1000) {
        _fpsDisplay = _fpsFrames;
        _fpsFrames = 0;
        _fpsLast = _fpsNow;
    }
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(8, 8, 52, 18);
    ctx.fillStyle = _fpsDisplay < 30 ? '#f44336' : (_fpsDisplay < 50 ? '#ffc107' : '#4caf50');
    ctx.font = '10px "Press Start 2P"';
    ctx.textAlign = 'left';
    ctx.fillText(_fpsDisplay + ' fps', 12, 21);
    ctx.restore();

    // Draw zoom indicator (screen space, top-right, fades out)
    const zoomAge = Date.now() - _zoomIndicatorTimer;
    if (zoomAge < 2000) {
        const alpha = zoomAge < 1500 ? 0.8 : 0.8 * (1 - (zoomAge - 1500) / 500);
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(displayW - 80, 8, 72, 22);
        ctx.fillStyle = '#ffd700';
        ctx.font = '10px "Press Start 2P"';
        ctx.textAlign = 'right';
        ctx.fillText(camera.zoom.toFixed(1) + 'x', displayW - 14, 23);
        ctx.restore();
    }

    // --- EDIT MODE OVERLAY ---
    if (editMode) {
        ctx.save();
        applyCameraTransform();
        drawEditOverlay();
        ctx.restore();

        // Edit mode HUD (screen space)
        drawEditHUD();
    }

    requestAnimationFrame(loop);
}

// ============================================================
// EDIT MODE — Canvas expansion/shrink with grid overlay
// ============================================================

const EDIT_BTN_SIZE = 30;
const EDIT_BTN_MARGIN = 8;
var _editButtons = []; // computed each frame for hit testing

function drawEditOverlay() {
    // Dim everything slightly
    ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
    ctx.fillRect(0, 0, W, H);

    // Grid lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= W; x += TILE) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    for (let y = 0; y <= H; y += TILE) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    // Canvas boundary (thick highlight)
    ctx.strokeStyle = '#ffd600';
    ctx.lineWidth = 3;
    ctx.strokeRect(0, 0, W, H);

    // Tile highlight on hover with 5 snap zones
    if (editHoverTile) {
        var _htx = editHoverTile.tx * TILE;
        var _hty = editHoverTile.ty * TILE;
        // Yellow tile outline
        ctx.fillStyle = 'rgba(255, 214, 0, 0.15)';
        ctx.fillRect(_htx, _hty, TILE, TILE);
        ctx.strokeStyle = 'rgba(255, 214, 0, 0.4)';
        ctx.lineWidth = 1;
        ctx.strokeRect(_htx, _hty, TILE, TILE);
        // Quadrant divider lines
        ctx.strokeStyle = 'rgba(255, 214, 0, 0.25)';
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(_htx + TILE / 2, _hty); ctx.lineTo(_htx + TILE / 2, _hty + TILE);
        ctx.moveTo(_htx, _hty + TILE / 2); ctx.lineTo(_htx + TILE, _hty + TILE / 2);
        ctx.stroke();
        // Zone dots (active zone = green, others = gold)
        for (var _zn in SNAP_ZONES) {
            var _zd = SNAP_ZONES[_zn];
            var _zdx = _htx + _zd.ox * TILE;
            var _zdy = _hty + _zd.oy * TILE;
            var _isActive = _zn === activeSnapZone;
            ctx.fillStyle = _isActive ? 'rgba(0,255,150,0.8)' : 'rgba(255,215,0,0.4)';
            ctx.beginPath();
            ctx.arc(_zdx, _zdy, _isActive ? 4 : 2, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    // --- WALL PLACEMENT GHOST PREVIEW ---
    if (placingType === 'wall') {
        // Show start tile highlight when in phase 1
        if (wallPlacingPhase === 1 && wallPlacingStart) {
            ctx.fillStyle = 'rgba(100, 180, 255, 0.4)';
            ctx.fillRect(wallPlacingStart.tx * TILE, wallPlacingStart.ty * TILE, TILE, TILE);
            // Ghost line to hover
            if (editHoverTile) {
                var _wdx = Math.abs(editHoverTile.tx - wallPlacingStart.tx);
                var _wdy = Math.abs(editHoverTile.ty - wallPlacingStart.ty);
                var _isHoriz = _wdx >= _wdy;
                ctx.strokeStyle = 'rgba(100, 180, 255, 0.7)';
                ctx.lineWidth = 6;
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                if (_isHoriz) {
                    var _gx1 = Math.min(wallPlacingStart.tx, editHoverTile.tx) * TILE;
                    var _gx2 = Math.max(wallPlacingStart.tx, editHoverTile.tx) * TILE;
                    var _gy = wallPlacingStart.ty * TILE;
                    ctx.moveTo(_gx1, _gy); ctx.lineTo(_gx2, _gy);
                } else {
                    var _gx = wallPlacingStart.tx * TILE;
                    var _gy1 = Math.min(wallPlacingStart.ty, editHoverTile.ty) * TILE;
                    var _gy2 = Math.max(wallPlacingStart.ty, editHoverTile.ty) * TILE;
                    ctx.moveTo(_gx, _gy1); ctx.lineTo(_gx, _gy2);
                }
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }
    }
    // Show selected wall with yellow dashed outline (extra thick)
    if (selectedWallIdx !== null && officeConfig.walls.interior && officeConfig.walls.interior[selectedWallIdx]) {
        var _sw = officeConfig.walls.interior[selectedWallIdx];
        ctx.setLineDash([6, 3]);
        ctx.strokeStyle = '#ffd600';
        ctx.lineWidth = 3;
        if (_sw.x1 === _sw.x2) {
            var _spx = _sw.x1 * TILE - 3;
            var _spy = Math.min(_sw.y1, _sw.y2) * TILE - 3;
            ctx.strokeRect(_spx, _spy, 12, Math.abs(_sw.y2 - _sw.y1) * TILE + 6);
        } else {
            var _spx = Math.min(_sw.x1, _sw.x2) * TILE - 3;
            var _spy = _sw.y1 * TILE - 3;
            ctx.strokeRect(_spx, _spy, Math.abs(_sw.x2 - _sw.x1) * TILE + 6, 12);
        }
        ctx.setLineDash([]);
    }

    // --- EXPAND/SHRINK BUTTONS (drawn in world space at edges) ---
    _editButtons = [];
    var bS = EDIT_BTN_SIZE;

    // RIGHT edge: + to expand right, - to shrink
    _drawEditBtn(W + EDIT_BTN_MARGIN, H / 2 - bS - 4, bS, '+', 'right', 'expand');
    _drawEditBtn(W + EDIT_BTN_MARGIN, H / 2 + 4, bS, '−', 'right', 'shrink');

    // BOTTOM edge: + to expand down, - to shrink
    _drawEditBtn(W / 2 - bS - 4, H + EDIT_BTN_MARGIN, bS, '+', 'bottom', 'expand');
    _drawEditBtn(W / 2 + 4, H + EDIT_BTN_MARGIN, bS, '−', 'bottom', 'shrink');

    // LEFT and TOP expansion disabled — shifts break agent positions

    // Size label near bottom-right
    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.fillRect(W - 120, H + 8, 120, 22);
    ctx.fillStyle = '#ffd600';
    ctx.font = 'bold 10px "Press Start 2P"';
    ctx.textAlign = 'center';
    ctx.fillText(Math.round(W / TILE) + ' × ' + Math.round(H / TILE) + ' tiles', W - 60, H + 23);

    // --- GHOST PREVIEW ---
    if (placingType && _ghostPos) {
        // Snap kitchen appliances to counter tops for ghost preview
        if (COUNTER_ONLY_ITEMS.indexOf(placingType) >= 0) {
            var snapped = _snapToCounterTop(placingType, _ghostPos.x, _ghostPos.y);
            if (snapped) { _ghostPos.x = snapped.x; _ghostPos.y = snapped.y; }
        }
        _placementValid = _isValidPlacement(placingType, _ghostPos.x, _ghostPos.y);
        // Build ghost item — carry rotation from the source item when dragging
        var ghostItem = { type: placingType, x: _ghostPos.x, y: _ghostPos.y };
        if (isDragging && selectedItemId) {
            var _dragSrc = officeConfig.furniture.find(function(f){ return f.id === selectedItemId; });
            if (_dragSrc && _dragSrc.rotation) ghostItem.rotation = _dragSrc.rotation;
            if (_dragSrc && _dragSrc.couchColor) ghostItem.couchColor = _dragSrc.couchColor;
        }
        var _ghostWR = _getItemWorldRect(ghostItem);
        var _visX = _ghostWR.x;
        var _visY = _ghostWR.y;
        var _visW = _ghostWR.w;
        var _visH = _ghostWR.h;

        // Highlight ALL tiles the item's visual area covers
        var _gStartTX = Math.max(0, Math.floor(_visX / TILE));
        var _gStartTY = Math.max(0, Math.floor(_visY / TILE));
        var _gEndTX = Math.floor((_visX + _visW - 1) / TILE);
        var _gEndTY = Math.floor((_visY + _visH - 1) / TILE);
        ctx.fillStyle = _placementValid ? 'rgba(0, 255, 150, 0.18)' : 'rgba(244, 67, 54, 0.15)';
        ctx.strokeStyle = _placementValid ? 'rgba(0, 255, 150, 0.5)' : 'rgba(244, 67, 54, 0.5)';
        ctx.lineWidth = 1.5;
        for (var _gtx = _gStartTX; _gtx <= _gEndTX; _gtx++) {
            for (var _gty = _gStartTY; _gty <= _gEndTY; _gty++) {
                ctx.fillRect(_gtx * TILE, _gty * TILE, TILE, TILE);
                ctx.strokeRect(_gtx * TILE, _gty * TILE, TILE, TILE);
            }
        }

        // Draw ghost item
        ctx.globalAlpha = _placementValid ? 0.5 : 0.3;
        drawFurnitureItem(ghostItem);
        ctx.globalAlpha = 1;

        // Bounding box outline around visual area
        ctx.setLineDash([]);
        ctx.strokeStyle = _placementValid ? '#00e676' : '#f44336';
        ctx.lineWidth = 2;
        ctx.strokeRect(_visX, _visY, _visW, _visH);

        // Show red X if invalid
        if (!_placementValid) {
            ctx.fillStyle = 'rgba(244, 67, 54, 0.6)';
            ctx.fillRect(_visX, _visY, _visW, _visH);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('✕', _visX + _visW / 2, _visY + _visH / 2 + 5);
        }
    }

    // --- SELECTION HIGHLIGHT (all occupied tiles + bounding box) ---
    if (selectedItemId) {
        var selItem = null;
        for (var _si = 0; _si < officeConfig.furniture.length; _si++) {
            if (officeConfig.furniture[_si].id === selectedItemId) { selItem = officeConfig.furniture[_si]; break; }
        }
        if (selItem) {
            var _selWR = _getItemWorldRect(selItem);
            // Highlight ALL tiles
            var _sTX1 = Math.max(0, Math.floor(_selWR.x / TILE));
            var _sTY1 = Math.max(0, Math.floor(_selWR.y / TILE));
            var _sTX2 = Math.floor((_selWR.x + _selWR.w - 1) / TILE);
            var _sTY2 = Math.floor((_selWR.y + _selWR.h - 1) / TILE);
            ctx.fillStyle = 'rgba(255, 214, 0, 0.1)';
            ctx.strokeStyle = 'rgba(255, 214, 0, 0.4)';
            ctx.lineWidth = 1;
            for (var _stx = _sTX1; _stx <= _sTX2; _stx++) {
                for (var _sty = _sTY1; _sty <= _sTY2; _sty++) {
                    ctx.fillRect(_stx * TILE, _sty * TILE, TILE, TILE);
                    ctx.strokeRect(_stx * TILE, _sty * TILE, TILE, TILE);
                }
            }
            // Dashed bounding box around visual area
            ctx.setLineDash([5, 3]);
            ctx.strokeStyle = '#ffd600';
            ctx.lineWidth = 2;
            ctx.strokeRect(_selWR.x - 3, _selWR.y - 3, _selWR.w + 6, _selWR.h + 6);
            ctx.setLineDash([]);
        }
    }

    // --- MULTI-SELECT highlights ---
    _multiSelected.forEach(function(fid) {
        var fi = null;
        for (var _mi = 0; _mi < officeConfig.furniture.length; _mi++) {
            if (officeConfig.furniture[_mi].id === fid) { fi = officeConfig.furniture[_mi]; break; }
        }
        if (!fi) return;
        var fb = FURNITURE_BOUNDS[fi.type] || { w: TILE, h: TILE, ox: 0, oy: 0 };
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = '#00e5ff';
        ctx.lineWidth = 2;
        var _mox = fb.ox || 0, _moy = fb.oy || 0;
        ctx.strokeRect(fi.x - _mox * fb.w - 2, fi.y - _moy * fb.h - 2, fb.w + 4, fb.h + 4);
        ctx.setLineDash([]);
    });

    // --- MARQUEE RECT ---
    if (_marqueeStart && _marqueeEnd) {
        var mx = Math.min(_marqueeStart.x, _marqueeEnd.x);
        var my = Math.min(_marqueeStart.y, _marqueeEnd.y);
        var mw = Math.abs(_marqueeEnd.x - _marqueeStart.x);
        var mh = Math.abs(_marqueeEnd.y - _marqueeStart.y);
        ctx.fillStyle = 'rgba(0, 229, 255, 0.08)';
        ctx.fillRect(mx, my, mw, mh);
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
        ctx.lineWidth = 1;
        ctx.strokeRect(mx, my, mw, mh);
        ctx.setLineDash([]);
    }

    // --- DRAG TILE HIGHLIGHT (shows target tile during drag) ---
    if (_editDragTileHighlight) {
        var dth = _editDragTileHighlight;
        if (dth.valid) {
            // Green glow for valid position
            ctx.fillStyle = 'rgba(76, 175, 80, 0.15)';
            ctx.fillRect(dth.x, dth.y, dth.w, dth.h);
            ctx.strokeStyle = 'rgba(76, 175, 80, 0.6)';
            ctx.lineWidth = 2;
            ctx.strokeRect(dth.x, dth.y, dth.w, dth.h);
            // Draw half-tile grid within the highlight area
            ctx.lineWidth = 1;
            for (var _thx = dth.x + HALF_TILE; _thx < dth.x + dth.w; _thx += HALF_TILE) {
                ctx.strokeStyle = (_thx - dth.x) % TILE === 0 ? 'rgba(76, 175, 80, 0.3)' : 'rgba(76, 175, 80, 0.15)';
                ctx.beginPath(); ctx.moveTo(_thx, dth.y); ctx.lineTo(_thx, dth.y + dth.h); ctx.stroke();
            }
            for (var _thy = dth.y + HALF_TILE; _thy < dth.y + dth.h; _thy += HALF_TILE) {
                ctx.strokeStyle = (_thy - dth.y) % TILE === 0 ? 'rgba(76, 175, 80, 0.3)' : 'rgba(76, 175, 80, 0.15)';
                ctx.beginPath(); ctx.moveTo(dth.x, _thy); ctx.lineTo(dth.x + dth.w, _thy); ctx.stroke();
            }
        } else {
            // Red glow for invalid position
            ctx.fillStyle = 'rgba(244, 67, 54, 0.12)';
            ctx.fillRect(dth.x, dth.y, dth.w, dth.h);
            ctx.strokeStyle = 'rgba(244, 67, 54, 0.5)';
            ctx.lineWidth = 2;
            ctx.strokeRect(dth.x, dth.y, dth.w, dth.h);
        }
    }
}

function _drawEditBtn(x, y, size, label, edge, action) {
    var isExpand = action === 'expand';
    var canShrink = (edge === 'left' || edge === 'right') ? (W / TILE > MIN_TILES_X) : (H / TILE > MIN_TILES_Y);

    if (!isExpand && !canShrink) {
        // Draw disabled button
        ctx.fillStyle = 'rgba(60, 60, 60, 0.5)';
        ctx.fillRect(x, y, size, size);
        ctx.fillStyle = 'rgba(150, 150, 150, 0.4)';
        ctx.font = 'bold 16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(label, x + size / 2, y + size / 2 + 6);
        return;
    }

    // Active button
    ctx.fillStyle = isExpand ? 'rgba(76, 175, 80, 0.85)' : 'rgba(244, 67, 54, 0.85)';
    ctx.fillRect(x, y, size, size);

    // Border
    ctx.strokeStyle = isExpand ? '#66bb6a' : '#ef5350';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, size, size);

    // Label
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 18px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(label, x + size / 2, y + size / 2 + 7);

    // Store for hit testing
    _editButtons.push({ x: x, y: y, w: size, h: size, edge: edge, action: action });
}

function drawEditHUD() {
    // Top bar with edit mode indicator
    ctx.save();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
    ctx.fillRect(displayW / 2 - 140, 6, 280, 28);
    ctx.strokeStyle = '#ffd600';
    ctx.lineWidth = 1;
    ctx.strokeRect(displayW / 2 - 140, 6, 280, 28);
    ctx.fillStyle = '#ffd600';
    ctx.font = 'bold 10px "Press Start 2P"';
    ctx.textAlign = 'center';
    var hudText;
    if (placingType === 'wall') {
        hudText = wallPlacingPhase === 0 ? '🧱 WALL — Click start tile' : '🧱 WALL — Click end tile (Esc cancel)';
    } else if (placingType === 'door') {
        hudText = '🚪 DOOR — Click wall tile to add opening (Esc cancel)';
    } else if (placingType) {
        hudText = '📦 PLACING: ' + placingType.toUpperCase() + ' — Esc cancel';
    } else {
        hudText = '✏️ EDIT MODE — ' + Math.round(W / TILE) + '×' + Math.round(H / TILE);
    }
    ctx.fillText(hudText, displayW / 2, 24);
    ctx.restore();

    // Update floating toolbar position every frame
    _updateFloatingToolbarPosition();

    // Tile coord on hover (screen space, bottom-left)
    if (editHoverTile) {
        ctx.save();
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(8, displayH - 28, 90, 20);
        ctx.fillStyle = '#ccc';
        ctx.font = '9px "Press Start 2P"';
        ctx.textAlign = 'left';
        ctx.fillText('(' + editHoverTile.tx + ',' + editHoverTile.ty + ')', 14, displayH - 14);
        ctx.restore();
    }
}

function expandCanvas(edge) {
    // Only allow expanding right and bottom (top/left shifts break agent positions)
    if (edge === 'left' || edge === 'top') return;
    _pushUndo();
    if (edge === 'right') {
        W += TILE;
    } else if (edge === 'bottom') {
        H += TILE;
    }
    saveOfficeConfig();
}

function shrinkCanvas(edge) {
    if (edge === 'left' || edge === 'top') return;
    _pushUndo();
    if (edge === 'right' && W / TILE > MIN_TILES_X) {
        W -= TILE;
    } else if (edge === 'bottom' && H / TILE > MIN_TILES_Y) {
        H -= TILE;
    }
    saveOfficeConfig();
}

function _shiftAllPositions(dx, dy) {
    // Shift all agent positions and targets
    agents.forEach(function(a) {
        a.x += dx; a.y += dy;
        a.targetX += dx; a.targetY += dy;
        if (a.desk) { a.desk.x += dx; a.desk.y += dy; }
    });
    // Shift LOCATIONS
    LOCATIONS.pqDesks.forEach(function(d) { d.x += dx; d.y += dy; });
    LOCATIONS.engDesks.forEach(function(d) { d.x += dx; d.y += dy; });
    LOCATIONS.bossDesk.x += dx; LOCATIONS.bossDesk.y += dy;
    LOCATIONS.centerDesk.x += dx; LOCATIONS.centerDesk.y += dy;
    LOCATIONS.centerDesk2.x += dx; LOCATIONS.centerDesk2.y += dy;
    LOCATIONS.centerDesk3.x += dx; LOCATIONS.centerDesk3.y += dy;
    if (LOCATIONS.forgeDesk) { LOCATIONS.forgeDesk.x += dx; LOCATIONS.forgeDesk.y += dy; }
    LOCATIONS.meeting.x += dx; LOCATIONS.meeting.y += dy;
    LOCATIONS.lounge.x += dx; LOCATIONS.lounge.y += dy;
    LOCATIONS.cooler.x += dx; LOCATIONS.cooler.y += dy;
    LOCATIONS.wanderSpots.forEach(function(s) { s.x += dx; s.y += dy; });
    var inter = LOCATIONS.interactions;
    inter.windows.forEach(function(w) { w.x += dx; w.y += dy; });
    inter.couchSeats.forEach(function(s) { s.x += dx; s.y += dy; });
    if (inter.bookshelf)     { inter.bookshelf.x     += dx; inter.bookshelf.y     += dy; }
    if (inter.tvSpot)        { inter.tvSpot.x         += dx; inter.tvSpot.y         += dy; }
    if (inter.vendingMachine){ inter.vendingMachine.x += dx; inter.vendingMachine.y += dy; }
    if (inter.coffeeMaker)   { inter.coffeeMaker.x    += dx; inter.coffeeMaker.y    += dy; }
    if (inter.waterCooler)   { inter.waterCooler.x    += dx; inter.waterCooler.y    += dy; }
    if (inter.microwave)     { inter.microwave.x      += dx; inter.microwave.y      += dy; }
    if (inter.toaster)       { inter.toaster.x        += dx; inter.toaster.y        += dy; }
    if (inter.dartBoard)     { inter.dartBoard.x      += dx; inter.dartBoard.y      += dy; }
    inter.engCouchSeats.forEach(function(s) { s.x += dx; s.y += dy; });
    // Re-derive meeting slots from the (now shifted) meeting table furniture position
    MEETING_SLOTS = getMeetingSlots();
    // Shift officeConfig furniture items to stay in sync
    officeConfig.furniture.forEach(function(item) { item.x += dx; item.y += dy; });
    // Re-sync interaction spots from shifted furniture
    getInteractionSpots();
}

// --- COLLISION DETECTION ---
// Get visual top-left from draw position + bounds
function _visualTopLeft(type, x, y) {
    var b = FURNITURE_BOUNDS[type] || { w: TILE, h: TILE, ox: 0, oy: 0 };
    return { x: x - (b.ox || 0) * b.w, y: y - (b.oy || 0) * b.h, w: b.w, h: b.h };
}

function _itemOverlaps(type, x, y, excludeId) {
    var b1 = FURNITURE_BOUNDS[type] || { w: TILE, h: TILE };
    // Items with noCollision never block or get blocked
    if (b1.noCollision) return false;
    var v1 = _visualTopLeft(type, x, y);
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        var item = officeConfig.furniture[i];
        if (excludeId && item.id === excludeId) continue;
        var b2 = FURNITURE_BOUNDS[item.type] || { w: TILE, h: TILE };
        if (b2.noCollision) continue; // skip non-blocking items
        // Use rotation-aware world rect for placed items
        var v2 = _getItemWorldRect(item);
        if (v1.x < v2.x + v2.w && v1.x + v1.w > v2.x &&
            v1.y < v2.y + v2.h && v1.y + v1.h > v2.y) {
            return true;
        }
    }
    return false;
}

// --- SYNC AGENT DESK ASSIGNMENTS ---
// When a desk has an assignedTo, move that agent's desk reference to this furniture item's position
function _syncAgentToDesk(deskItem) {
    if (!deskItem.assignedTo) return;
    for (var i = 0; i < agents.length; i++) {
        if (agents[i].name === deskItem.assignedTo) {
            var agent = agents[i];
            // Update the agent's desk position
            if (agent.desk.x !== deskItem.x || agent.desk.y !== deskItem.y) {
                agent.desk = { x: deskItem.x, y: deskItem.y };
                // If agent is idle at their old desk, move them to new one
                if (agent.state === 'idle' || agent.state === 'working') {
                    agent.targetX = deskItem.x;
                    agent.targetY = deskItem.y;
                }
            }
            break;
        }
    }
}

// Run desk sync on config load and after any furniture change
function _syncAllDeskAssignments() {
    officeConfig.furniture.forEach(function(item) {
        if (item.assignedTo && (item.type === 'desk' || item.type === 'bossDesk')) {
            _syncAgentToDesk(item);
        }
    });
}

// Kitchen appliance types that must be placed on counters
var COUNTER_ONLY_ITEMS = ['coffeeMaker', 'microwave', 'toaster'];

// Check if a position sits on top of a kitchen counter
function _isOnCounter(type, x, y) {
    var itemB = FURNITURE_BOUNDS[type] || { w: TILE, h: TILE };
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        var f = officeConfig.furniture[i];
        if (f.type !== 'kitchenCounter') continue;
        var cb = FURNITURE_BOUNDS['kitchenCounter']; // w:72, h:34
        // Appliance must be within counter's horizontal span
        // and at the snapped Y position (counter.y - itemHeight + 2, with tolerance)
        var expectedY = f.y - itemB.h + 2;
        if (x >= f.x - 2 && x + itemB.w <= f.x + cb.w + 2 &&
            Math.abs(y - expectedY) < 8) {
            return true;
        }
    }
    // Also check breakArea items (they have built-in counters)
    for (var j = 0; j < officeConfig.furniture.length; j++) {
        var ba = officeConfig.furniture[j];
        if (ba.type !== 'breakArea') continue;
        var counters = [
            { x: ba.x + 80, y: ba.y + 78, w: 72 },
            { x: ba.x + 170, y: ba.y + 78, w: 72 }
        ];
        for (var c = 0; c < counters.length; c++) {
            var ct = counters[c];
            var expectedY2 = ct.y - itemB.h + 2;
            if (x >= ct.x - 2 && x + itemB.w <= ct.x + ct.w + 2 &&
                Math.abs(y - expectedY2) < 8) {
                return true;
            }
        }
    }
    return false;
}

// Snap a kitchen appliance to the nearest counter top surface
function _snapToCounterTop(type, worldX, worldY) {
    var itemB = FURNITURE_BOUNDS[type] || { w: TILE, h: TILE };
    var best = null;
    var bestDist = 999999;

    // Check standalone kitchen counters
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        var f = officeConfig.furniture[i];
        if (f.type !== 'kitchenCounter') continue;
        var cb = FURNITURE_BOUNDS['kitchenCounter']; // w:72, h:34
        // Appliance sits on counter surface: Y = counter.y - itemHeight (on top)
        var snapY = f.y - itemB.h + 2; // +2 so it visually rests on surface
        var snapX = Math.round((worldX - f.x) / 4) * 4 + f.x; // fine snap within counter
        snapX = Math.max(f.x, Math.min(f.x + cb.w - itemB.w, snapX)); // clamp to counter width
        var dist = Math.abs(worldX - snapX) + Math.abs(worldY - snapY);
        if (dist < bestDist) { bestDist = dist; best = { x: snapX, y: snapY }; }
    }

    // Check breakArea built-in counters
    for (var j = 0; j < officeConfig.furniture.length; j++) {
        var ba = officeConfig.furniture[j];
        if (ba.type !== 'breakArea') continue;
        var counters = [
            { x: ba.x + 80, y: ba.y + 78, w: 72 },
            { x: ba.x + 170, y: ba.y + 78, w: 72 }
        ];
        for (var c = 0; c < counters.length; c++) {
            var ct = counters[c];
            var snapY2 = ct.y - itemB.h + 2;
            var snapX2 = Math.round((worldX - ct.x) / 4) * 4 + ct.x;
            snapX2 = Math.max(ct.x, Math.min(ct.x + ct.w - itemB.w, snapX2));
            var dist2 = Math.abs(worldX - snapX2) + Math.abs(worldY - snapY2);
            if (dist2 < bestDist) { bestDist = dist2; best = { x: snapX2, y: snapY2 }; }
        }
    }

    // Only snap if reasonably close (within 120px)
    if (best && bestDist < 120) return best;
    return null;
}

// Check if a position is valid for a given furniture type
function _isValidPlacement(type, x, y) {
    // Windows can only be placed on the top wall
    if (type === 'window' || type === 'interactiveWindow' || type === 'floorWindow') {
        var wallH = officeConfig.walls.height || 70;
        if (y > wallH - 10 || y < 0) return false;
        if (x < 0 || x + (FURNITURE_BOUNDS[type] || {w:40}).w > W) return false;
    }
    // Kitchen appliances can only be placed on kitchen counters
    if (COUNTER_ONLY_ITEMS.indexOf(type) >= 0) {
        if (!_isOnCounter(type, x, y)) return false;
        // Skip overlap check for counter items — they sit ON the counter
        return true;
    }
    // General: visual area must be within canvas bounds
    var _vp = _visualTopLeft(type, x, y);
    if (_vp.x < 0 || _vp.y < 0 || _vp.x + _vp.w > W || _vp.y + _vp.h > H) return false;
    // Check overlap
    if (_itemOverlaps(type, x, y, null)) return false;
    return true;
}

var _placementValid = true; // updated each frame for ghost preview color

// --- EDIT MODE CLICK HANDLING ---
function handleEditClick(worldX, worldY, screenX, screenY, event) {
    // 1. If in placement mode → place item
    if (placingType === 'wall') {
        var _clickTx = Math.floor(worldX / TILE);
        var _clickTy = Math.floor(worldY / TILE);
        if (wallPlacingPhase === 0) {
            wallPlacingStart = { tx: _clickTx, ty: _clickTy };
            wallPlacingPhase = 1;
        } else {
            // Second click - create wall
            var _x1 = wallPlacingStart.tx, _y1 = wallPlacingStart.ty;
            var _x2 = _clickTx, _y2 = _clickTy;
            var _wdx = Math.abs(_x2 - _x1), _wdy = Math.abs(_y2 - _y1);
            if (_wdx > 0 || _wdy > 0) {
                var newWall;
                if (_wdx >= _wdy) {
                    // Horizontal: snap to same Y as start
                    newWall = { x1: Math.min(_x1, _x2), y1: _y1, x2: Math.max(_x1, _x2), y2: _y1, color: '#5d6271', accentColor: '#5d6271', trimColor: '#d2d4da', trim2Color: '#989ca8' };
                } else {
                    // Vertical: snap to same X as start
                    newWall = { x1: _x1, y1: Math.min(_y1, _y2), x2: _x1, y2: Math.max(_y1, _y2), color: '#5d6271', accentColor: '#5d6271', trimColor: '#d2d4da', trim2Color: '#989ca8' };
                }
                _pushUndo();
                if (!officeConfig.walls.interior) officeConfig.walls.interior = [];
                officeConfig.walls.interior.push(newWall);
                buildCollisionGrid();
            }
            wallPlacingPhase = 0;
            wallPlacingStart = null;
        }
        return true;
    }
    if (placingType === 'door') {
        // Click on a wall to add a door (1-tile gap)
        var _dTx = Math.floor(worldX / TILE);
        var _dTy = Math.floor(worldY / TILE);
        var interior = officeConfig.walls.interior || [];
        for (var _di = 0; _di < interior.length; _di++) {
            var _dw = interior[_di];
            if (_dw.x1 === _dw.x2) {
                // Vertical wall - check if click tile row is within it
                var _minY = Math.min(_dw.y1, _dw.y2), _maxY = Math.max(_dw.y1, _dw.y2);
                if (_dTx === _dw.x1 && _dTy >= _minY && _dTy < _maxY) {
                    _pushUndo();
                    officeConfig.walls.interior.splice(_di, 1);
                    // Add two segments split by 1-tile door
                    if (_dTy > _minY) officeConfig.walls.interior.push({ x1: _dw.x1, y1: _minY, x2: _dw.x1, y2: _dTy, color: _dw.color, accentColor: _dw.accentColor, trimColor: _dw.trimColor, trim2Color: _dw.trim2Color });
                    if (_dTy + 1 < _maxY) officeConfig.walls.interior.push({ x1: _dw.x1, y1: _dTy + 1, x2: _dw.x1, y2: _maxY, color: _dw.color, accentColor: _dw.accentColor, trimColor: _dw.trimColor, trim2Color: _dw.trim2Color });
                    buildCollisionGrid();
                    break;
                }
            } else {
                // Horizontal wall
                var _minX = Math.min(_dw.x1, _dw.x2), _maxX = Math.max(_dw.x1, _dw.x2);
                if (_dTy === _dw.y1 && _dTx >= _minX && _dTx < _maxX) {
                    _pushUndo();
                    officeConfig.walls.interior.splice(_di, 1);
                    if (_dTx > _minX) officeConfig.walls.interior.push({ x1: _minX, y1: _dw.y1, x2: _dTx, y2: _dw.y1, color: _dw.color, accentColor: _dw.accentColor, trimColor: _dw.trimColor, trim2Color: _dw.trim2Color });
                    if (_dTx + 1 < _maxX) officeConfig.walls.interior.push({ x1: _dTx + 1, y1: _dw.y1, x2: _maxX, y2: _dw.y1, color: _dw.color, accentColor: _dw.accentColor, trimColor: _dw.trimColor, trim2Color: _dw.trim2Color });
                    buildCollisionGrid();
                    break;
                }
            }
        }
        return true;
    }
    if (placingType) {
        // Check if clicking near a zone dot — switch zone instead of placing
        var _clickTX = Math.floor(worldX / TILE);
        var _clickTY = Math.floor(worldY / TILE);
        for (var _czName in SNAP_ZONES) {
            var _cz = SNAP_ZONES[_czName];
            var _czX = _clickTX * TILE + _cz.ox * TILE;
            var _czY = _clickTY * TILE + _cz.oy * TILE;
            var _czDist = Math.sqrt((worldX - _czX) * (worldX - _czX) + (worldY - _czY) * (worldY - _czY));
            if (_czDist < 10 && _czName !== activeSnapZone) {
                activeSnapZone = _czName;
                var _snapSel = document.getElementById('snap-zone-select');
                if (_snapSel) _snapSel.value = activeSnapZone;
                return true; // consumed click, don't place
            }
        }
        // Snap to active zone center within the hovered tile (origin-aware)
        var _placeZone = SNAP_ZONES[activeSnapZone] || SNAP_ZONES['center'];
        var _placeTX = Math.floor(worldX / TILE);
        var _placeTY = Math.floor(worldY / TILE);
        var _placeZCX = _placeTX * TILE + _placeZone.ox * TILE;
        var _placeZCY = _placeTY * TILE + _placeZone.oy * TILE;
        var _placeBounds = FURNITURE_BOUNDS[placingType] || { w: TILE, h: TILE, ox: 0, oy: 0 };
        var _pox = _placeBounds.ox || 0;
        var _poy = _placeBounds.oy || 0;
        var sx = Math.round(_placeZCX - (0.5 - _pox) * _placeBounds.w);
        var sy = Math.round(_placeZCY - (0.5 - _poy) * _placeBounds.h);
        // Kitchen appliances: snap to counter top surface
        if (COUNTER_ONLY_ITEMS.indexOf(placingType) >= 0) {
            var snapped = _snapToCounterTop(placingType, worldX, worldY);
            if (!snapped) return true; // no valid counter nearby
            sx = snapped.x;
            sy = snapped.y;
        }
        // Validate placement
        if (!_isValidPlacement(placingType, sx, sy)) return true; // block but stay in placement mode
        var newItem = { id: _generateFurnitureId(), type: placingType, x: sx, y: sy };
        // Custom text label — prompt for text on placement
        if (placingType === 'textLabel') {
    var labelText = prompt(_tr('enter_label_text'), _tr('label_default'));
            if (!labelText) return true; // cancelled
            newItem.text = labelText;
            newItem.labelColor = '#ffffff';
            newItem.fontSize = 12;
        }
        _pushUndo();
        officeConfig.furniture.push(newItem);
        getInteractionSpots();
        return true;
    }

    // 2. Check expand/shrink buttons
    for (var i = 0; i < _editButtons.length; i++) {
        var b = _editButtons[i];
        if (worldX >= b.x && worldX <= b.x + b.w && worldY >= b.y && worldY <= b.y + b.h) {
            if (b.action === 'expand') expandCanvas(b.edge);
            else shrinkCanvas(b.edge);
            return true;
        }
    }

    // 3. Hit-test furniture — skip if mousedown already handled it (drag)
    var hit = _findFurnitureAt(worldX, worldY);
    if (hit) {
        if (_handleFunctionalFurnitureClick(hit, screenX || 200, screenY || 200)) return true;
        // Meeting table click → open dashboard (only outside edit mode)
        if (_meetingTableClickCheck(hit)) return true;
        // Furniture selection is handled by mousedown now.
        // Only reach here if it was a quick click (no drag).
        // Selection was already set in mousedown, just return.
        return true;
    }

    // 3d. Hit-test interior walls for selection
    var _hitWallIdx = _findWallAt(worldX, worldY);
    if (_hitWallIdx >= 0) {
        selectedWallIdx = _hitWallIdx;
        selectedItemId = null;
        _multiSelected = [];
        _hideColorPicker();
        return true;
    }

    // 4. Click on floor → floor color picker (only in floor edit mode)
    var wallH = officeConfig.walls.height;
    if (_floorEditMode && worldY >= wallH && worldY < H && worldX >= 0 && worldX < W) {
        _showFloorColorPicker(screenX || 200, screenY || 200);
        return true;
    }

    // 5. Click top wall → top wall color picker
    if (worldY >= 0 && worldY < wallH && worldX >= 0 && worldX < W) {
        _showTopWallColorPicker(screenX || 200, screenY || 60);
        return true;
    }

    // 6. Empty space click — selection clearing handled by mousedown
    return false;
}

// Get effective width/height for an item, accounting for rotation
function _getRotatedBounds(item) {
    var b = FURNITURE_BOUNDS[item.type] || { w: TILE, h: TILE, ox: 0, oy: 0 };
    var rot = item.rotation || 0;
    if (rot === 90 || rot === 270) return { w: b.h, h: b.w, ox: b.oy, oy: b.ox };
    return b;
}

// Get the world-space bounding rect for a possibly-rotated item.
// Accounts for origin offsets (ox/oy) and rotation.
// Drawing uses translate(x,y) then rotate(rot), where (x,y) is the origin
// point defined by (ox,oy) as a fraction of (w,h).
function _getItemWorldRect(item) {
    var b = FURNITURE_BOUNDS[item.type] || { w: TILE, h: TILE, ox: 0, oy: 0 };
    var rot = item.rotation || 0;
    var w = b.w, h = b.h;
    var ox = b.ox || 0, oy = b.oy || 0;
    var ix = item.x, iy = item.y;
    // Visual top-left without rotation
    var vlx = ix - ox * w;
    var vly = iy - oy * h;
    if (!rot) return { x: vlx, y: vly, w: w, h: h };
    // With rotation: the origin (ix,iy) is the pivot.
    // Local corners relative to origin: (-ox*w, -oy*h) to ((1-ox)*w, (1-oy)*h)
    // After rotation, find the new bounding box
    var lx0 = -ox * w, ly0 = -oy * h;
    var lx1 = (1 - ox) * w, ly1 = (1 - oy) * h;
    var corners = [[lx0,ly0],[lx1,ly0],[lx1,ly1],[lx0,ly1]];
    var cosR = Math.round(Math.cos(rot * Math.PI / 180));
    var sinR = Math.round(Math.sin(rot * Math.PI / 180));
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var ci = 0; ci < 4; ci++) {
        var rx = corners[ci][0] * cosR - corners[ci][1] * sinR;
        var ry = corners[ci][0] * sinR + corners[ci][1] * cosR;
        if (rx < minX) minX = rx;
        if (ry < minY) minY = ry;
        if (rx > maxX) maxX = rx;
        if (ry > maxY) maxY = ry;
    }
    return { x: ix + minX, y: iy + minY, w: maxX - minX, h: maxY - minY };
}

function _findFurnitureAt(wx, wy) {
    // Search in reverse so top-drawn items get priority
    for (var i = officeConfig.furniture.length - 1; i >= 0; i--) {
        var item = officeConfig.furniture[i];
        var r = _getItemWorldRect(item);
        if (wx >= r.x && wx <= r.x + r.w && wy >= r.y && wy <= r.y + r.h) {
            return item;
        }
    }
    return null;
}

function _findWallAt(wx, wy) {
    var interior = officeConfig.walls && officeConfig.walls.interior;
    if (!interior) return -1;
    var thresh = 8; // pixels
    for (var i = 0; i < interior.length; i++) {
        var wall = interior[i];
        if (wall.x1 === wall.x2) {
            // Vertical wall
            var wallPx = wall.x1 * TILE;
            var minPy = Math.min(wall.y1, wall.y2) * TILE;
            var maxPy = Math.max(wall.y1, wall.y2) * TILE;
            if (Math.abs(wx - wallPx) < thresh && wy >= minPy && wy <= maxPy) return i;
        } else {
            // Horizontal wall
            var wallPy = wall.y1 * TILE;
            var minPx = Math.min(wall.x1, wall.x2) * TILE;
            var maxPx = Math.max(wall.x1, wall.x2) * TILE;
            if (Math.abs(wy - wallPy) < thresh && wx >= minPx && wx <= maxPx) return i;
        }
    }
    return -1;
}

function _generateFurnitureId() {
    return 'f_' + Date.now() + '_' + Math.floor(Math.random() * 9999);
}

function _updateFloatingToolbarPosition() {
    if (!_floatingToolbar) return;

    // Show toolbar for selected wall
    if (selectedWallIdx !== null && officeConfig.walls.interior && officeConfig.walls.interior[selectedWallIdx]) {
        var _sw = officeConfig.walls.interior[selectedWallIdx];
        var base = getBaseScale();
        var totalZoom = base * camera.zoom;
        var rect = canvas.getBoundingClientRect();
        var wx, wy;
        if (_sw.x1 === _sw.x2) {
            wx = _sw.x1 * TILE;
            wy = (Math.min(_sw.y1, _sw.y2) * TILE + Math.max(_sw.y1, _sw.y2) * TILE) / 2;
        } else {
            wx = (Math.min(_sw.x1, _sw.x2) * TILE + Math.max(_sw.x1, _sw.x2) * TILE) / 2;
            wy = _sw.y1 * TILE;
        }
        var dx = (wx - W / 2 - camera.x) * totalZoom + displayW / 2;
        var dy = (wy - H / 2 - camera.y) * totalZoom + displayH / 2;
        var sx = dx * (rect.width / displayW) + rect.left;
        var sy = dy * (rect.height / displayH) + rect.top;
        _floatingToolbar.style.display = 'flex';
        _floatingToolbar.style.left = (sx - 30) + 'px';
        _floatingToolbar.style.top = (sy - 46) + 'px';
        // Wall toolbar: delete + color + close only
        var assignBtn = document.getElementById('ftb-assign-btn');
        var branchBtn = document.getElementById('ftb-branch-btn');
        var colorBtn = document.getElementById('ftb-color-btn');
        if (assignBtn) assignBtn.style.display = 'none';
        if (branchBtn) branchBtn.style.display = 'none';
        if (colorBtn) colorBtn.style.display = '';
        return;
    }

    if (!selectedItemId) { _floatingToolbar.style.display = 'none'; return; }
    var selItem = null;
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        if (officeConfig.furniture[i].id === selectedItemId) { selItem = officeConfig.furniture[i]; break; }
    }
    if (!selItem) { _floatingToolbar.style.display = 'none'; return; }

    var _wr = _getItemWorldRect(selItem);
    var base = getBaseScale();
    var totalZoom = base * camera.zoom;
    var rect = canvas.getBoundingClientRect();
    // World center-top → display coords
    var wx = _wr.x + _wr.w / 2;
    var wy = _wr.y;
    var dx = (wx - W / 2 - camera.x) * totalZoom + displayW / 2;
    var dy = (wy - H / 2 - camera.y) * totalZoom + displayH / 2;
    // Display → screen CSS
    var sx = dx * (rect.width / displayW) + rect.left;
    var sy = dy * (rect.height / displayH) + rect.top;

    _floatingToolbar.style.display = 'flex';
    _floatingToolbar.style.left = (sx - 52) + 'px';
    _floatingToolbar.style.top  = (sy - 46) + 'px';
    // Show assign button only for desks
    var assignBtn = document.getElementById('ftb-assign-btn');
    if (assignBtn) {
        var isDesk = selItem.type === 'desk' || selItem.type === 'bossDesk';
        assignBtn.style.display = isDesk ? '' : 'none';
        if (isDesk && selItem.assignedTo) {
            assignBtn.title = (typeof i18n !== 'undefined' ? i18n.t('assigned_to') : 'Assigned to') + ': ' + selItem.assignedTo + ' (click to change)';
            assignBtn.textContent = '👤✓';
        } else if (isDesk) {
            assignBtn.title = typeof i18n !== 'undefined' ? i18n.t('assign_agent') : 'Assign agent to this desk';
            assignBtn.textContent = '👤';
        }
    }
    // Show branch button only for branch signs
    var branchBtn = document.getElementById('ftb-branch-btn');
    if (branchBtn) {
        var isSign = selItem.type === 'branchSign';
        branchBtn.style.display = isSign ? '' : 'none';
        if (isSign && selItem.branchId) {
            var _bInfo = getBranchById(selItem.branchId);
            branchBtn.title = _tr('branch_change_title', { name: _bInfo.name });
            branchBtn.textContent = '🏷️✓';
        } else if (isSign) {
            branchBtn.title = (typeof i18n !== 'undefined' ? i18n.t('assign_branch') : 'Assign branch to this sign');
            branchBtn.textContent = '🏷️';
        }
    }
    var colorBtn = document.getElementById('ftb-color-btn');
    if (colorBtn) colorBtn.style.display = 'none';

    // Show label edit buttons for textLabel items
    var labelEditBtn = document.getElementById('ftb-label-edit-btn');
    if (!labelEditBtn) {
        // Create the label edit button dynamically on first use
        labelEditBtn = document.createElement('button');
        labelEditBtn.id = 'ftb-label-edit-btn';
        labelEditBtn.textContent = '✏️';
        labelEditBtn.title = typeof i18n !== 'undefined' ? i18n.t('edit_label') : 'Edit label';
        labelEditBtn.style.cssText = 'padding:4px 6px;background:#2a2a4e;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:12px;';
        labelEditBtn.onclick = function() {
            if (!selectedItemId) return;
            var item = officeConfig.furniture.find(function(f){ return f.id === selectedItemId; });
            if (!item || item.type !== 'textLabel') return;
            _showTextLabelEditor(item);
        };
        _floatingToolbar.appendChild(labelEditBtn);
    }
    labelEditBtn.style.display = (selItem.type === 'textLabel') ? '' : 'none';

    // Show settings button for weather window items
    var iwSettingsBtn = document.getElementById('ftb-iw-settings-btn');
    if (!iwSettingsBtn) {
        iwSettingsBtn = document.createElement('button');
        iwSettingsBtn.id = 'ftb-iw-settings-btn';
        iwSettingsBtn.textContent = '⚙️';
        iwSettingsBtn.title = typeof i18n !== 'undefined' ? i18n.t('window_settings') : 'Window settings (weather/sun)';
        iwSettingsBtn.style.cssText = 'padding:4px 6px;background:#2a2a4e;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:12px;';
        iwSettingsBtn.onclick = function() {
            if (!selectedItemId) return;
            var item = officeConfig.furniture.find(function(f){ return f.id === selectedItemId; });
            if (!item || (item.type !== 'interactiveWindow' && item.type !== 'floorWindow')) return;
            _showInteractiveWindowEditor(item);
        };
        _floatingToolbar.appendChild(iwSettingsBtn);
    }
    iwSettingsBtn.style.display = (selItem.type === 'interactiveWindow' || selItem.type === 'floorWindow') ? '' : 'none';

    var bookshelfBindBtn = document.getElementById('ftb-bookshelf-bind-btn');
    if (!bookshelfBindBtn) {
        bookshelfBindBtn = document.createElement('button');
        bookshelfBindBtn.id = 'ftb-bookshelf-bind-btn';
        bookshelfBindBtn.textContent = '🗄️';
        bookshelfBindBtn.title = _tr('bookshelf_bind_archive');
        bookshelfBindBtn.style.cssText = 'padding:4px 6px;background:#2a2a4e;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:12px;';
        bookshelfBindBtn.onclick = function() {
            if (!selectedItemId) return;
            var item = officeConfig.furniture.find(function(f){ return f.id === selectedItemId; });
            if (!_isFunctionalBookshelf(item)) return;
            _showArchiveBindingDialog(item);
        };
        _floatingToolbar.appendChild(bookshelfBindBtn);
    }
    bookshelfBindBtn.style.display = _isFunctionalBookshelf(selItem) ? '' : 'none';
    if (_isFunctionalBookshelf(selItem)) {
        bookshelfBindBtn.title = selItem.archiveProjectId ? _tr('bookshelf_change_archive') : _tr('bookshelf_bind_archive');
    }

    // Show color button for couch items
    var couchColorBtn = document.getElementById('ftb-couch-color-btn');
    if (!couchColorBtn) {
        couchColorBtn = document.createElement('button');
        couchColorBtn.id = 'ftb-couch-color-btn';
        couchColorBtn.textContent = '🎨';
        couchColorBtn.title = typeof i18n !== 'undefined' ? i18n.t('change_couch_color') : 'Change couch color';
        couchColorBtn.style.cssText = 'padding:4px 6px;background:#2a2a4e;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:12px;';
        couchColorBtn.onclick = function() {
            if (!selectedItemId) return;
            var item = officeConfig.furniture.find(function(f){ return f.id === selectedItemId; });
            if (!item || item.type !== 'couch') return;
            _showCouchColorEditor(item);
        };
        _floatingToolbar.appendChild(couchColorBtn);
    }
    couchColorBtn.style.display = (selItem.type === 'couch') ? '' : 'none';

    // Show rotate button for rotatable items (couch)
    var rotateBtn = document.getElementById('ftb-rotate-btn');
    if (!rotateBtn) {
        rotateBtn = document.createElement('button');
        rotateBtn.id = 'ftb-rotate-btn';
        rotateBtn.textContent = '🔄';
        rotateBtn.title = typeof i18n !== 'undefined' ? i18n.t('rotate_90') : 'Rotate 90°';
        rotateBtn.style.cssText = 'padding:4px 6px;background:#2a2a4e;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:12px;';
        rotateBtn.onclick = function() {
            if (!selectedItemId) return;
            var item = officeConfig.furniture.find(function(f){ return f.id === selectedItemId; });
            if (!item) return;
            var fa = FURNITURE_ACTIONS[item.type];
            if (!fa || !fa.rotatable) return;
            _pushUndo();
            item.rotation = ((item.rotation || 0) + 90) % 360;
            getInteractionSpots();
            _saveOfficeConfig();
        };
        _floatingToolbar.appendChild(rotateBtn);
    }
    var isRotatable = false;
    var selFa = FURNITURE_ACTIONS[selItem.type];
    if (selFa && selFa.rotatable) isRotatable = true;
    rotateBtn.style.display = isRotatable ? '' : 'none';
}

// --- EDIT MODE MOUSE TRACKING ---
canvas.addEventListener('mousemove', function(e) {
    if (!editMode) { editHoverTile = null; _ghostPos = null; return; }
    var world = screenToWorld(e.clientX, e.clientY);
    if (world.x >= 0 && world.x < W && world.y >= 0 && world.y < H) {
        editHoverTile = { tx: Math.floor(world.x / TILE), ty: Math.floor(world.y / TILE) };
        // Snap ghost to active zone center within the hovered tile
        var _snapZone = SNAP_ZONES[activeSnapZone] || SNAP_ZONES['center'];
        var _snapTX = editHoverTile.tx;
        var _snapTY = editHoverTile.ty;
        var _zoneCenterX = _snapTX * TILE + _snapZone.ox * TILE;
        var _zoneCenterY = _snapTY * TILE + _snapZone.oy * TILE;
        // Position ghost so item's visual center lands on the zone center,
        // accounting for where the draw function expects (x,y) to be
        var _ghostBounds = placingType ? (FURNITURE_BOUNDS[placingType] || { w: TILE, h: TILE, ox: 0, oy: 0 }) : { w: TILE, h: TILE, ox: 0, oy: 0 };
        var _gox = _ghostBounds.ox || 0;
        var _goy = _ghostBounds.oy || 0;
        // Zone center = visual center of item → drawX = zoneX - (0.5 - ox) * w
        _ghostPos = { x: Math.round(_zoneCenterX - (0.5 - _gox) * _ghostBounds.w), y: Math.round(_zoneCenterY - (0.5 - _goy) * _ghostBounds.h) };
        // Marquee extend
        if (_marqueeStart && !isDragging && !_multiDragging) {
            _marqueeEnd = { x: world.x, y: world.y };
        }
        // Multi-drag
        if (_multiDragging && _multiDragStart && _multiSelected.length > 0) {
            var mdx = Math.round((world.x - _multiDragStart.x) / HALF_TILE) * HALF_TILE;
            var mdy = Math.round((world.y - _multiDragStart.y) / HALF_TILE) * HALF_TILE;
            if (mdx !== 0 || mdy !== 0) {
                _multiSelected.forEach(function(fid) {
                    var fi = officeConfig.furniture.find(function(f){ return f.id === fid; });
                    if (fi) { fi.x += mdx; fi.y += mdy; }
                });
                _multiDragStart = { x: _multiDragStart.x + mdx, y: _multiDragStart.y + mdy };
            }
        }
        // Drag selected item (tile-snap with highlight)
        if (isDragging && selectedItemId && !placingType) {
            _editMouseMoved = true;
            for (var _di = 0; _di < officeConfig.furniture.length; _di++) {
                if (officeConfig.furniture[_di].id === selectedItemId) {
                    var dragItem = officeConfig.furniture[_di];
                    var dBounds = FURNITURE_BOUNDS[dragItem.type] || {w:TILE, h:TILE, ox:0, oy:0};
                    var snapX = Math.round((world.x - dragOffset.x) / HALF_TILE) * HALF_TILE;
                    var snapY = Math.round((world.y - dragOffset.y) / HALF_TILE) * HALF_TILE;
                    // Highlight matches item's visual footprint (rotation-aware)
                    var _dragTestItem = { type: dragItem.type, x: snapX, y: snapY, rotation: dragItem.rotation || 0 };
                    var _dragWR = _getItemWorldRect(_dragTestItem);
                    _editDragTileHighlight = {
                        x: _dragWR.x, y: _dragWR.y,
                        w: _dragWR.w, h: _dragWR.h
                    };
                    // Only move if valid position
                    if (!_itemOverlaps(dragItem.type, snapX, snapY, selectedItemId) &&
                        _dragWR.x >= 0 && _dragWR.y >= 0 &&
                        _dragWR.x + _dragWR.w <= W &&
                        _dragWR.y + _dragWR.h <= H) {
                        if (dragItem.type === 'window' || dragItem.type === 'interactiveWindow' || dragItem.type === 'floorWindow') {
                            var wallH = officeConfig.walls.height || 70;
                            if (snapY <= wallH - 10) {
                                dragItem.x = snapX;
                                dragItem.y = snapY;
                            }
                        } else {
                            dragItem.x = snapX;
                            dragItem.y = snapY;
                        }
                        _editDragTileHighlight.valid = true;
                    } else {
                        _editDragTileHighlight.valid = false;
                    }
                    break;
                }
            }
        }
        // Multi-drag tile highlight
        if (_multiDragging) {
            _editMouseMoved = true;
        }
    } else {
        editHoverTile = null;
        _ghostPos = null;
    }
});

// --- EDIT MODE TOGGLE (called from toolbar button) ---
function toggleEditMode() {
    if (window._voLicense && window._voLicense.demo) {
        alert(_tr('premium_edit_office'));
        return;
    }
    editMode = !editMode;
    var btn = document.getElementById('btn-edit-office');
    var saveBtn = document.getElementById('btn-save-edits');
    var undoBtn = document.getElementById('btn-undo-edit');
    if (editMode) {
        btn.textContent = typeof i18n !== 'undefined' ? i18n.t('done_editing') : '✅ Done Editing';
        btn.classList.add('active-edit');
        if (saveBtn) saveBtn.style.display = '';
        if (undoBtn) undoBtn.style.display = '';
        _showCatalogPanel();
        _undoStack = [];
        _hasUnsavedChanges = false;
        _updateSaveUndoButtons();
    } else {
        btn.textContent = typeof i18n !== 'undefined' ? i18n.t('edit_office') : '✏️ Edit Office';
        btn.classList.remove('active-edit');
        if (saveBtn) saveBtn.style.display = 'none';
        if (undoBtn) undoBtn.style.display = 'none';
        editHoverTile = null;
        _floorEditMode = false;
        _hideCatalogPanel();
        if (_hasUnsavedChanges) {
            saveOfficeConfig();
        }
        _undoStack = [];
        _hasUnsavedChanges = false;
    }
}

// --- AGENT CREATOR PANEL ---
var _agentPanel = null;
var _agentPanelSelectedId = null;
var _agentPanelPreviewCanvas = null;
var _agentPanelPreviewCtx = null;
var _agentPanelEditState = null; // working copy of appearance being edited
var _acpUndoStack = [];
var _acpUnsaved = false;

// ============================================================
// MAIN MENU
// ============================================================
var _mainMenuOpen = false;

var DEFAULT_BROWSER_CDP_URL = 'http://127.0.0.1:9224';
var DEFAULT_BROWSER_VIEWER_URL = 'https://localhost:6901';

function toggleMainMenu() {
    var panel = document.getElementById('main-menu-panel');
    if (!panel) return;
    _mainMenuOpen = !_mainMenuOpen;
    panel.classList.toggle('open', _mainMenuOpen);
    var btn = document.getElementById('btn-main-menu');
    if (btn) btn.classList.toggle('active-edit', _mainMenuOpen);
    if (_mainMenuOpen) _mmLoadCurrentSettings();
}

function _mmLoadCurrentSettings() {
    // Populate fields from current server config
    fetch('/vo-config').then(function(r){ return r.json(); }).then(function(cfg) {
        var gwInput = document.getElementById('mm-gateway-url');
        var nameInput = document.getElementById('mm-office-name');
        var weatherCityInput = document.getElementById('mm-weather-city');
        var weatherStateInput = document.getElementById('mm-weather-state');
        var pathInput = document.getElementById('mm-oc-path');
        var tokenInput = document.getElementById('mm-gateway-token');
        var hermesCb = document.getElementById('mm-hermes-enable');
        var hermesFields = document.getElementById('mm-hermes-fields');
        var hermesHome = document.getElementById('mm-hermes-home');
        var hermesBin = document.getElementById('mm-hermes-bin');
        var hermesApiEnabled = document.getElementById('mm-hermes-api-enable');
        var hermesApiUrl = document.getElementById('mm-hermes-api-url');
        var codexEnabled = document.getElementById('mm-codex-enable');
        var codexWorkspace = document.getElementById('mm-codex-workspace');
        var codexWorkspaceRoot = document.getElementById('mm-codex-workspace-root');
        var codexMainWorkspace = document.getElementById('mm-codex-main-workspace');
        var codexModel = document.getElementById('mm-codex-model');
        var codexBridgeUrl = document.getElementById('mm-codex-bridge-url');
        var codexIncludeMain = document.getElementById('mm-codex-include-main');
        var codexIncludeNative = document.getElementById('mm-codex-include-native');
        var claudeCodeEnabled = document.getElementById('mm-claude-code-enable');
        var claudeCodeHome = document.getElementById('mm-claude-code-home');
        var claudeCodeBin = document.getElementById('mm-claude-code-bin');
        var claudeCodeWorkspace = document.getElementById('mm-claude-code-workspace');
        var claudeCodeWorkspaceRoot = document.getElementById('mm-claude-code-workspace-root');
        var claudeCodeMainWorkspace = document.getElementById('mm-claude-code-main-workspace');
        var claudeCodeModel = document.getElementById('mm-claude-code-model');
        var claudeCodeIncludeMain = document.getElementById('mm-claude-code-include-main');
        var claudeCodeIncludeNative = document.getElementById('mm-claude-code-include-native');
        var claudeCodeRegisterNative = document.getElementById('mm-claude-code-register-native');
        var meetingPreparingTimeout = document.getElementById('mm-meeting-preparing-timeout');
        if (gwInput) gwInput.value = (cfg.openclaw || {}).gatewayUrl || '';
        if (nameInput) nameInput.value = (cfg.office || {}).name || '';
        // Parse "City,State" or "City+Name,State" back into separate fields
        var _wloc = (cfg.weather || {}).location || '';
        var _wparts = _wloc.split(',');
        if (weatherCityInput) weatherCityInput.value = (_wparts[0] || '').replace(/\+/g, ' ');
        if (weatherStateInput) weatherStateInput.value = (_wparts[1] || '').replace(/\+/g, ' ');
        if (pathInput) pathInput.value = (cfg.openclaw || {}).homePath || '';
        var hermesCfg = cfg.hermes || {};
        var hermesEnabled = hermesCfg.enabled !== false;
        if (hermesCb) hermesCb.checked = hermesEnabled;
        if (hermesFields) hermesFields.style.display = hermesEnabled ? 'block' : 'none';
        if (hermesHome) hermesHome.value = hermesCfg.homePath || '';
        if (hermesBin) hermesBin.value = hermesCfg.binary || '';
        if (hermesApiEnabled) hermesApiEnabled.checked = hermesCfg.apiEnabled === true;
        if (hermesApiUrl) hermesApiUrl.value = hermesCfg.apiUrl || '';
        var codexCfg = cfg.codex || {};
        if (codexEnabled) codexEnabled.checked = codexCfg.enabled === true;
        if (codexWorkspace) codexWorkspace.value = codexCfg.workspace || '';
        if (codexWorkspaceRoot) codexWorkspaceRoot.value = codexCfg.workspaceRoot || '';
        if (codexMainWorkspace) codexMainWorkspace.value = codexCfg.mainWorkspace || '';
        if (codexModel) codexModel.value = codexCfg.model || '';
        if (codexBridgeUrl) codexBridgeUrl.value = codexCfg.bridgeUrl || '';
        if (codexIncludeMain) codexIncludeMain.checked = codexCfg.includeMain !== false;
        if (codexIncludeNative) codexIncludeNative.checked = codexCfg.includeNativeAgents !== false;
        var claudeCfg = cfg.claudeCode || {};
        if (claudeCodeEnabled) claudeCodeEnabled.checked = claudeCfg.enabled === true;
        if (claudeCodeHome) claudeCodeHome.value = claudeCfg.homePath || '';
        if (claudeCodeBin) claudeCodeBin.value = claudeCfg.binary || '';
        if (claudeCodeWorkspace) claudeCodeWorkspace.value = claudeCfg.workspace || '';
        if (claudeCodeWorkspaceRoot) claudeCodeWorkspaceRoot.value = claudeCfg.workspaceRoot || '';
        if (claudeCodeMainWorkspace) claudeCodeMainWorkspace.value = claudeCfg.mainWorkspace || '';
        if (claudeCodeModel) claudeCodeModel.value = claudeCfg.model || '';
        if (claudeCodeIncludeMain) claudeCodeIncludeMain.checked = claudeCfg.includeMain !== false;
        if (claudeCodeIncludeNative) claudeCodeIncludeNative.checked = claudeCfg.includeNativeAgents !== false;
        if (claudeCodeRegisterNative) claudeCodeRegisterNative.checked = claudeCfg.registerNativeAgents !== false;
        // Auto-populate token from /gateway-info (shows current effective token)
        if (tokenInput) {
            fetch('/gateway-info').then(function(r) { return r.json(); }).then(function(gi) {
                if (gi.token && !tokenInput.value) tokenInput.value = gi.token;
            }).catch(function(){});
        }
        // PC Metrics
        var pcmEnabled = ((cfg.features || {}).pcMetrics) || false;
        var pcmUrl = ((cfg.pcMetrics || {}).url) || "";
        var pcmCb = document.getElementById("mm-pcmetrics-enable");
        var pcmUrlEl = document.getElementById("mm-pcmetrics-url");
        var pcmFields = document.getElementById("mm-pcmetrics-fields");
        if (pcmCb) pcmCb.checked = pcmEnabled;
        if (pcmUrlEl) pcmUrlEl.value = pcmUrl;
        if (pcmFields) pcmFields.style.display = pcmEnabled ? "block" : "none";
        // API Usage
        var apiUsageCb = document.getElementById("mm-apiusage-enable");
        if (apiUsageCb) apiUsageCb.checked = (cfg.features || {}).apiUsage === true;
        // Browser
        var brEnabled = ((cfg.features || {}).browserPanel) || false;
        var brCdp = ((cfg.browser || {}).cdpUrl) || DEFAULT_BROWSER_CDP_URL;
        var brViewer = ((cfg.browser || {}).viewerUrl) || DEFAULT_BROWSER_VIEWER_URL;
        var brCb = document.getElementById("mm-browser-enable");
        var brCdpEl = document.getElementById("mm-cdp-url");
        var brViewerEl = document.getElementById("mm-viewer-url");
        var brFields = document.getElementById("mm-browser-fields");
        if (brCb) brCb.checked = brEnabled;
        if (brCdpEl) brCdpEl.value = brCdp;
        if (brViewerEl) brViewerEl.value = brViewer;
        if (brFields) brFields.style.display = brEnabled ? "block" : "none";
        if (meetingPreparingTimeout) {
            meetingPreparingTimeout.value = String(_mtgNormalizePreparingTimeoutSec((cfg.meetings || {}).preparingTimeoutSec));
        }
    }).catch(function(){});
    // Load display prefs from localStorage
    var prefs = {};
    try { prefs = JSON.parse(localStorage.getItem('vo-display-prefs') || '{}'); } catch(e){}
    var cb1 = document.getElementById('mm-show-bubbles');
    var cb2 = document.getElementById('mm-show-weather');
    var cb3 = document.getElementById('mm-show-names');
    var timeoutInput = document.getElementById('mm-internal-bubble-timeout');
    var fontScaleInput = document.getElementById('mm-font-scale');
    if (cb1) cb1.checked = prefs.showBubbles !== false;
    if (cb2) cb2.checked = prefs.showWeather !== false;
    if (cb3) cb3.checked = prefs.showNames !== false;
    if (timeoutInput) {
        timeoutInput.value = typeof InternalBubbleSettings !== 'undefined'
            ? InternalBubbleSettings.normalizeTimeoutSec(prefs.internalBubbleTimeoutSec)
            : 60;
    }
    if (fontScaleInput) {
        fontScaleInput.value = typeof VOFontScale !== 'undefined'
            ? String(VOFontScale.normalizeFontScale(prefs.fontScale))
            : String(prefs.fontScale || 1);
    }
}

function mmApplyFontScaleSetting(value) {
    if (typeof VOFontScale === 'undefined') return 1;
    var scale = VOFontScale.setStoredFontScale(value);
    VOFontScale.applyFontScale(scale);
    _displayPrefs.fontScale = scale;
    var select = document.getElementById('mm-font-scale');
    if (select) select.value = String(scale);
    return scale;
}


// PC Metrics toggle in settings
(function() {
    var _pcmCb = document.getElementById('mm-pcmetrics-enable');
    if (_pcmCb) _pcmCb.addEventListener('change', function() {
        var f = document.getElementById('mm-pcmetrics-fields');
        if (f) f.style.display = this.checked ? 'block' : 'none';
    });
})();

// Browser toggle in settings
(function() {
    var _brCb = document.getElementById('mm-browser-enable');
    if (_brCb) _brCb.addEventListener('change', function() {
        var f = document.getElementById('mm-browser-fields');
        if (f) f.style.display = this.checked ? 'block' : 'none';
    });
})();

// Hermes toggle in settings
(function() {
    var _hCb = document.getElementById('mm-hermes-enable');
    if (_hCb) _hCb.addEventListener('change', function() {
        var f = document.getElementById('mm-hermes-fields');
        if (f) f.style.display = this.checked ? 'block' : 'none';
    });
})();

function mmTestHermes() {
    var statusEl = document.getElementById('mm-hermes-status');
    var enabled = !!(document.getElementById('mm-hermes-enable') || {}).checked;
    var homePath = (document.getElementById('mm-hermes-home') || {}).value || '';
    var binary = (document.getElementById('mm-hermes-bin') || {}).value || '';
    var apiEnabled = !!(document.getElementById('mm-hermes-api-enable') || {}).checked;
    var apiUrl = (document.getElementById('mm-hermes-api-url') || {}).value || '';
    var apiKey = (document.getElementById('mm-hermes-api-key') || {}).value || '';
    if (!enabled) {
        statusEl.innerHTML = '<div class="mm-status info">' + _tr('hermes_disabled') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('testing_hermes') + '</div>';
    var hermesSave = { enabled: enabled, homePath: homePath || null, binary: binary || null, apiEnabled: apiEnabled, apiUrl: apiUrl || null };
    if (apiKey.trim()) hermesSave.apiKey = apiKey.trim();
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hermes: hermesSave })
    }).then(function() {
        return fetch('/api/hermes/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ homePath: homePath || null, binary: binary || null, apiEnabled: apiEnabled, apiUrl: apiUrl || null, apiKey: apiKey.trim() || undefined })
        });
    }).then(function(r) { return r.json().then(function(d){ d._httpOk = r.ok; return d; }); }).then(function(d) {
        if (d.ok) {
            var count = (d.agents || []).length;
            var names = (d.agents || []).slice(0, 5).map(function(a){ return (a.emoji || '⚕️') + ' ' + a.name + (a.model ? ' · ' + a.model : ''); }).join('<br>');
            var api = d.api || {};
            var apiLine = apiEnabled ? '<br>Native API: ' + (api.ok ? 'connected' : ('unavailable' + (api.error ? ' · ' + escHtml(api.error) : ''))) : '';
            statusEl.innerHTML = '<div class="mm-status ok">' + _tr('hermes_connected_profiles', { count: count }) + apiLine + (names ? '<br>' + names : '') + '</div>';
        } else {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('hermes_not_reachable') + ': ' + escHtml(d.error || _tr('unknown')) + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('hermes_test_failed') + ': ' + escHtml(e.message) + '</div>';
    });
}

function mmTestCodex() {
    var statusEl = document.getElementById('mm-codex-status');
    if (!statusEl) return;
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('saving_testing') + '</div>';
    var cfg = {
        enabled: !!(document.getElementById('mm-codex-enable') || {}).checked,
        workspace: ((document.getElementById('mm-codex-workspace') || {}).value || '').trim() || null,
        workspaceRoot: ((document.getElementById('mm-codex-workspace-root') || {}).value || '').trim() || null,
        mainWorkspace: ((document.getElementById('mm-codex-main-workspace') || {}).value || '').trim() || null,
        model: ((document.getElementById('mm-codex-model') || {}).value || '').trim() || null,
        bridgeUrl: ((document.getElementById('mm-codex-bridge-url') || {}).value || '').trim() || null,
        includeMain: !!(document.getElementById('mm-codex-include-main') || {}).checked,
        includeNativeAgents: !!(document.getElementById('mm-codex-include-native') || {}).checked
    };
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codex: cfg })
    }).then(function() {
        return fetch('/api/codex/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    }).then(function(r) { return r.json(); }).then(function(d) {
        statusEl.innerHTML = '<div class="mm-status ' + (d.ok ? 'ok' : 'err') + '">' + (d.ok ? 'Connected' : ('❌ ' + escHtml(d.error || _tr('unknown')))) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(e.message) + '</div>';
    });
}

function mmTestClaudeCode() {
    var statusEl = document.getElementById('mm-claude-code-status');
    if (!statusEl) return;
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('saving_testing') + '</div>';
    var cfg = {
        enabled: !!(document.getElementById('mm-claude-code-enable') || {}).checked,
        homePath: ((document.getElementById('mm-claude-code-home') || {}).value || '').trim() || null,
        binary: ((document.getElementById('mm-claude-code-bin') || {}).value || '').trim() || null,
        workspace: ((document.getElementById('mm-claude-code-workspace') || {}).value || '').trim() || null,
        workspaceRoot: ((document.getElementById('mm-claude-code-workspace-root') || {}).value || '').trim() || null,
        mainWorkspace: ((document.getElementById('mm-claude-code-main-workspace') || {}).value || '').trim() || null,
        model: ((document.getElementById('mm-claude-code-model') || {}).value || '').trim() || null,
        includeMain: !!(document.getElementById('mm-claude-code-include-main') || {}).checked,
        includeNativeAgents: !!(document.getElementById('mm-claude-code-include-native') || {}).checked,
        registerNativeAgents: !!(document.getElementById('mm-claude-code-register-native') || {}).checked
    };
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claudeCode: cfg })
    }).then(function() {
        return fetch('/api/claude-code/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    }).then(function(r) { return r.json(); }).then(function(d) {
        statusEl.innerHTML = '<div class="mm-status ' + (d.ok ? 'ok' : 'err') + '">' + (d.ok ? 'Connected' : ('❌ ' + escHtml(d.error || _tr('unknown')))) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(e.message) + '</div>';
    });
}

function mmTestCdp() {
    var cdpUrl = document.getElementById('mm-cdp-url').value.trim();
    var viewerUrl = document.getElementById('mm-viewer-url').value.trim();
    var statusEl = document.getElementById('mm-cdp-status');
    if (!cdpUrl) { statusEl.innerHTML = '<div class="mm-status err">' + _tr('enter_cdp_first') + '</div>'; return; }
    statusEl.innerHTML = '<div class="mm-status">' + _tr('saving_testing') + '</div>';
    // Save first, then test
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            features: { browserPanel: true },
            browser: { cdpUrl: cdpUrl, viewerUrl: viewerUrl || null }
        })
    }).then(function() {
        return fetch('/browser-status');
    }).then(function(r) { return r.json(); }).then(function(status) {
        if (status.cdpAvailable) {
            fetch('/browser-tabs').then(function(r) { return r.json(); }).then(function(tabs) {
                var count = Array.isArray(tabs) ? tabs.length : 0;
                statusEl.innerHTML = '<div class="mm-status ok">' + _tr('cdp_connected_tabs', { count: count }) + '</div>';
            }).catch(function() {
                statusEl.innerHTML = '<div class="mm-status ok">' + _tr('cdp_reachable') + '</div>';
            });
        } else {
            statusEl.innerHTML = '<div class="mm-status err">\u274c ' + _tr('cdp_check_hint') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">\u274c ' + _tr('error') + ': ' + escHtml(e.message) + '</div>';
    });
}

function mmTestViewer() {
    var cdpUrl = document.getElementById('mm-cdp-url').value.trim();
    var viewerUrl = document.getElementById('mm-viewer-url').value.trim();
    var statusEl = document.getElementById('mm-viewer-status');
    if (!viewerUrl) { statusEl.innerHTML = '<div class="mm-status err">' + _tr('enter_viewer_first') + '</div>'; return; }
    statusEl.innerHTML = '<div class="mm-status">' + _tr('saving_testing') + '</div>';
    // Save first, then test
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            features: { browserPanel: true },
            browser: { cdpUrl: cdpUrl || null, viewerUrl: viewerUrl }
        })
    }).then(function() {
        return fetch(viewerUrl.replace(/\/$/, ''), { mode: 'no-cors', cache: 'no-store' });
    }).then(function() {
            statusEl.innerHTML = '<div class="mm-status ok">' + _tr('viewer_reachable') + '</div>';
    }).catch(function(e) {
            statusEl.innerHTML = '<div class="mm-status err">\u274c ' + _tr('viewer_not_reachable') + ': ' + escHtml(e.message) + '</div>';
    });
}

function mmTestPcMetrics() {
    var url = document.getElementById('mm-pcmetrics-url').value.trim();
    var statusEl = document.getElementById('mm-pcmetrics-status');
    if (!url) { statusEl.innerHTML = '<div class="mm-status err">' + _tr('enter_metrics_url') + '</div>'; return; }
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('saving_testing') + '</div>';
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ features: { pcMetrics: true }, pcMetrics: { url: url } })
    }).then(function() { return fetch('/pc-metrics'); })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + data.error + '</div>';
        } else if (data.cpu) {
            var info = 'CPU: ' + (data.cpu.percent||0).toFixed(0) + '% (' + (data.cpu.threads||'?') + ' threads)';
            info += ' · RAM: ' + (data.memory.percent||0).toFixed(0) + '%';
            if (data.gpus && data.gpus.length > 0) info += ' · GPU: ' + data.gpus[0].name;
            statusEl.innerHTML = '<div class="mm-status ok">' + _tr('connected_label') + '<br>' + info + '</div>';
        } else {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('unexpected_response_format') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + e.message + '</div>';
    });
}

function mmTestConnection() {
    var statusEl = document.getElementById('mm-conn-status');
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('testing') + '</div>';
    // Save current settings first so the server tests with the new values
    var gwUrl = document.getElementById('mm-gateway-url').value;
    var ocPath = document.getElementById('mm-oc-path').value;
    var gwToken = (document.getElementById('mm-gateway-token') || {}).value || '';
    var saveBody = { openclaw: {} };
    if (gwUrl) {
        saveBody.openclaw.gatewayUrl = gwUrl;
        saveBody.openclaw.gatewayHttp = gwUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace(/\/ws.*$/, '');
    }
    if (ocPath) saveBody.openclaw.homePath = ocPath;
    if (gwToken) saveBody.openclaw.gatewayToken = gwToken;

    fetch('/setup/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saveBody) })
    .then(function() {
        // Test agents (OpenClaw path)
        return fetch('/api/agents').then(function(r){ return r.json(); });
    }).then(function(d) {
        var lines = [];
        if (d.agents && d.agents.length > 0) {
            lines.push('✅ OpenClaw: ' + d.agents.length + ' agent' + (d.agents.length === 1 ? '' : 's') + ' found');
        } else {
            lines.push('⚠️ OpenClaw: connected but no agents found');
        }
        // Test gateway WS
        return fetch('/api/gateway/test').then(function(r){ return r.json(); }).then(function(t) {
            if (t.gateway === 'reachable') {
                lines.push('✅ Gateway: reachable');
                if (t.token) lines.push('✅ Token: valid');
                else lines.push('⚠️ Token: not found or invalid');
            } else {
                lines.push('❌ Gateway: ' + (t.error || 'unreachable'));
            }
            var allOk = lines.every(function(l){ return l.indexOf('✅') === 0; });
            statusEl.innerHTML = '<div class="mm-status ' + (allOk ? 'ok' : 'err') + '">' + lines.join('<br>') + '</div>';
        });
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('failed') + escHtml(e.message) + '</div>';
    });
}

function _buildWeatherLocation(city, state) {
    city = (city || '').trim();
    state = (state || '').trim();
    if (!city) return null;
    return state ? city.replace(/ /g, '+') + ',' + state.replace(/ /g, '+') : city.replace(/ /g, '+');
}

function mmTestWeather() {
    var statusEl = document.getElementById('mm-weather-status');
    if (!statusEl) return;
    var location = _buildWeatherLocation(
        (document.getElementById('mm-weather-city') || {}).value,
        (document.getElementById('mm-weather-state') || {}).value
    );
    if (!location) {
        statusEl.innerHTML = '<div class="mm-status err">' + _tr('weather_test_location_required') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('testing_weather') + '</div>';
    fetch('/api/weather/test?location=' + encodeURIComponent(location))
        .then(function(r) { return r.json().then(function(d) { d._httpOk = r.ok; return d; }); })
        .then(function(d) {
            if (!d.ok) {
                statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('weather_test_failed') + ': ' + escHtml(d.error || _tr('unknown')) + '</div>';
                return;
            }
            _applyWeatherTestResult(location, d);
            var details = escHtml(d.resolvedLocation || location) + ' · ' + escHtml(d.weather || '') + ' · ' + escHtml(String(d.tempF || '?')) + '°F / ' + escHtml(String(d.tempC || '?')) + '°C';
            statusEl.innerHTML = '<div class="mm-status ok">✅ ' + _tr('weather_test_ok') + '<br>' + details + '</div>';
        }).catch(function(e) {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('weather_test_failed') + ': ' + escHtml(e.message) + '</div>';
        });
}

function mmSaveSettings() {
    var gwUrl = document.getElementById('mm-gateway-url').value;
    var officeName = document.getElementById('mm-office-name').value;
    var weather = _buildWeatherLocation(
        document.getElementById('mm-weather-city').value,
        document.getElementById('mm-weather-state').value
    );

    // Save display prefs locally
    var _elBubbles = document.getElementById('mm-show-bubbles');
    var _elWeather = document.getElementById('mm-show-weather');
    var _elNames = document.getElementById('mm-show-names');
    var _elInternalTimeout = document.getElementById('mm-internal-bubble-timeout');
    var _elFontScale = document.getElementById('mm-font-scale');
    var fontScale = typeof VOFontScale !== 'undefined'
        ? VOFontScale.normalizeFontScale(_elFontScale ? _elFontScale.value : _displayPrefs.fontScale)
        : Number((_elFontScale || {}).value || 1);
    var displayPrefs = {
        showBubbles: _elBubbles ? _elBubbles.checked : true,
        showWeather: _elWeather ? _elWeather.checked : true,
        showNames: _elNames ? _elNames.checked : true,
        internalBubbleTimeoutSec: typeof InternalBubbleSettings !== 'undefined'
            ? InternalBubbleSettings.normalizeTimeoutSec(_elInternalTimeout ? _elInternalTimeout.value : 60)
            : 60,
        fontScale: fontScale,
    };
    localStorage.setItem('vo-display-prefs', JSON.stringify(displayPrefs));
    _displayPrefs = displayPrefs;
    if (typeof VOFontScale !== 'undefined') VOFontScale.applyFontScale(fontScale);

    // Build server config
    var ocPath = document.getElementById('mm-oc-path').value;
    var gwToken = (document.getElementById('mm-gateway-token') || {}).value || '';
    var config = {};
    config.openclaw = { gatewayUrl: gwUrl || 'ws://127.0.0.1:18789' };
    if (gwUrl) {
        config.openclaw.gatewayHttp = gwUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace(/\/ws.*$/, '');
    }
    if (ocPath) config.openclaw.homePath = ocPath;
    if (gwToken) config.openclaw.gatewayToken = gwToken;
    var _hCb = document.getElementById('mm-hermes-enable');
    var _hHome = document.getElementById('mm-hermes-home');
    var _hBin = document.getElementById('mm-hermes-bin');
    var _hApiEnabled = document.getElementById('mm-hermes-api-enable');
    var _hApiUrl = document.getElementById('mm-hermes-api-url');
    var _hApiKey = document.getElementById('mm-hermes-api-key');
    if (_hCb) {
        var hermesSettings = {
            enabled: _hCb.checked,
            homePath: (_hHome ? _hHome.value.trim() : '') || null,
            binary: (_hBin ? _hBin.value.trim() : '') || null,
            apiEnabled: _hApiEnabled ? _hApiEnabled.checked : false,
            apiUrl: (_hApiUrl ? _hApiUrl.value.trim() : '') || null
        };
        if (_hApiKey && _hApiKey.value.trim()) config.hermes.apiKey = _hApiKey.value.trim();
    }
    var _codexCb = document.getElementById('mm-codex-enable');
    if (_codexCb) {
        config.codex = {
            enabled: _codexCb.checked,
            workspace: ((document.getElementById('mm-codex-workspace') || {}).value || '').trim() || null,
            workspaceRoot: ((document.getElementById('mm-codex-workspace-root') || {}).value || '').trim() || null,
            mainWorkspace: ((document.getElementById('mm-codex-main-workspace') || {}).value || '').trim() || null,
            model: ((document.getElementById('mm-codex-model') || {}).value || '').trim() || null,
            bridgeUrl: ((document.getElementById('mm-codex-bridge-url') || {}).value || '').trim() || null,
            includeMain: !!(document.getElementById('mm-codex-include-main') || {}).checked,
            includeNativeAgents: !!(document.getElementById('mm-codex-include-native') || {}).checked
        };
    }
    var _claudeCb = document.getElementById('mm-claude-code-enable');
    if (_claudeCb) {
        config.claudeCode = {
            enabled: _claudeCb.checked,
            homePath: ((document.getElementById('mm-claude-code-home') || {}).value || '').trim() || null,
            binary: ((document.getElementById('mm-claude-code-bin') || {}).value || '').trim() || null,
            workspace: ((document.getElementById('mm-claude-code-workspace') || {}).value || '').trim() || null,
            workspaceRoot: ((document.getElementById('mm-claude-code-workspace-root') || {}).value || '').trim() || null,
            mainWorkspace: ((document.getElementById('mm-claude-code-main-workspace') || {}).value || '').trim() || null,
            model: ((document.getElementById('mm-claude-code-model') || {}).value || '').trim() || null,
            includeMain: !!(document.getElementById('mm-claude-code-include-main') || {}).checked,
            includeNativeAgents: !!(document.getElementById('mm-claude-code-include-native') || {}).checked,
            registerNativeAgents: !!(document.getElementById('mm-claude-code-register-native') || {}).checked
        };
        var hermesApiKey = (_hApiKey ? _hApiKey.value.trim() : '');
        if (hermesApiKey) hermesSettings.apiKey = hermesApiKey;
        config.hermes = hermesSettings;
    }
    config.office = { name: officeName || 'Virtual Office' };
    config.weather = { location: weather || null };
    config.meetings = {
        preparingTimeoutSec: _mtgNormalizePreparingTimeoutSec((document.getElementById('mm-meeting-preparing-timeout') || {}).value)
    };
    // PC Metrics
    var _pcmCb = document.getElementById("mm-pcmetrics-enable");
    var _pcmUrl = document.getElementById("mm-pcmetrics-url");
    if (_pcmCb) {
        if (!config.features) config.features = {};
        config.features.pcMetrics = _pcmCb.checked;
        config.pcMetrics = { url: (_pcmUrl ? _pcmUrl.value.trim() : "") || null };
    }
    // API Usage
    var _apiCb = document.getElementById("mm-apiusage-enable");
    if (_apiCb) {
        if (!config.features) config.features = {};
        config.features.apiUsage = _apiCb.checked;
    }
    // Browser
    var _brCb = document.getElementById("mm-browser-enable");
    var _brCdp = document.getElementById("mm-cdp-url");
    var _brViewer = document.getElementById("mm-viewer-url");
    if (_brCb) {
        if (!config.features) config.features = {};
        config.features.browserPanel = _brCb.checked;
        config.browser = {
            cdpUrl: (_brCdp ? _brCdp.value.trim() : "") || null,
            viewerUrl: (_brViewer ? _brViewer.value.trim() : "") || null
        };
    }

    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    }).then(function(r){ return r.json(); }).then(function(d) {
        if (d.ok) {
            _acpShowToast('💾 Settings saved! Hard refresh (Ctrl+Shift+R) to apply all changes.');
            _voWeatherLocation = (config.weather || {}).location || '';
            pollWeather();
            // Update brand title live
            var brandEl = document.getElementById('brand-title');
            if (brandEl && officeName) brandEl.textContent = officeName.toUpperCase();
            if (officeName) document.title = officeName;
            if (typeof window.setPcMonitorEnabled === 'function' && config.features && Object.prototype.hasOwnProperty.call(config.features, 'pcMetrics')) {
                window.setPcMonitorEnabled(config.features.pcMetrics === true);
            }
            if (typeof window.setApiUsageEnabled === 'function' && config.features && Object.prototype.hasOwnProperty.call(config.features, 'apiUsage')) {
                window.setApiUsageEnabled(config.features.apiUsage === true);
            }
        } else {
            _acpShowToast('❌ Save failed');
        }
    }).catch(function(e) {
        _acpShowToast('❌ Save failed: ' + e.message);
    });
}

function mmExportConfig() {
    var blob = new Blob([JSON.stringify(officeConfig, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'virtual-office-config.json';
    a.click();
    URL.revokeObjectURL(url);
    _acpShowToast('📤 Config exported');
}

function mmImportConfig() {
    var fileInput = document.getElementById('mm-import-file');
    fileInput.onchange = function() {
        var file = fileInput.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function(e) {
            try {
                var imported = JSON.parse(e.target.result);
                if (!imported.canvasWidth && !imported.furniture) {
                    _acpShowToast('❌ Invalid config file');
                    return;
                }
    if (!confirm(_tr('import_config_confirm'))) return;
                // Merge imported config
                if (imported.canvasWidth) { W = imported.canvasWidth; officeConfig.canvasWidth = W; }
                if (imported.canvasHeight) { H = imported.canvasHeight; officeConfig.canvasHeight = H; }
                if (imported.walls) officeConfig.walls = imported.walls;
                if (imported.floor) officeConfig.floor = imported.floor;
                if (imported.furniture) officeConfig.furniture = imported.furniture;
                if (imported.agents) officeConfig.agents = imported.agents;
                if (imported.branches) officeConfig.branches = imported.branches;
                saveOfficeConfig();
                resizeCanvas(true);
                if (typeof buildCollisionGrid === 'function') buildCollisionGrid();
                if (typeof getInteractionSpots === 'function') getInteractionSpots();
                if (typeof _initAgentsFromDefs === 'function' && _rosterLoaded) _initAgentsFromDefs();
                _acpShowToast('📥 Config imported!');
            } catch (err) {
                _acpShowToast('❌ Invalid JSON: ' + err.message);
            }
        };
        reader.readAsText(file);
        fileInput.value = '';
    };
    fileInput.click();
}

function mmFullReset() {
    if (!confirm('⚠️ ' + _tr('full_reset_confirm'))) return;
    if (!confirm(_tr('reset_type_confirm'))) return;
    var input = prompt(_tr('type_reset'));
    if (input !== 'RESET') { _acpShowToast('Reset cancelled'); return; }

    // Clear everything
    localStorage.removeItem(OFFICE_CONFIG_KEY);
    fetch('/api/office-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
    }).then(function() {
        _acpShowToast('🗑️ Office reset. Reloading...');
        setTimeout(function() { window.location.reload(); }, 1000);
    });
}

function toggleAgentPanel() {
    if (window._voLicense && window._voLicense.demo) {
        alert(_tr('premium_agent_editor'));
        return;
    }
    if (!_agentPanel) _buildAgentPanel();
    if (_agentPanel.classList.contains('visible')) {
        _agentPanel.classList.remove('visible');
    } else {
        _agentPanel.classList.add('visible');
        _acpRefreshList();
        if (!_agentPanelSelectedId && agents.length > 0) {
            _acpSelectAgent(agents[0].id);
        }
    }
}

function _buildAgentPanel() {
    if (_agentPanel) return;

    var panel = document.createElement('div');
    panel.id = 'agent-creator-panel';
    panel.className = 'agent-panel';

    // Header
    var header = document.createElement('div');
    header.className = 'agent-panel-header';
    var title = document.createElement('span');
    title.className = 'agent-panel-title';
    title.textContent = '👤 ' + (typeof i18n !== 'undefined' ? i18n.t('agents_title') : 'AGENTS');
    header.appendChild(title);
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '✕ ' + (typeof i18n !== 'undefined' ? i18n.t('close_btn') : 'Close');
    closeBtn.className = 'catalog-close-btn';
    closeBtn.onclick = toggleAgentPanel;
    header.appendChild(closeBtn);
    panel.appendChild(header);

    // Scrollable body
    var body = document.createElement('div');
    body.className = 'agent-panel-body';

    var addBtn = document.createElement('button');
    addBtn.textContent = '➕ ' + (typeof i18n !== 'undefined' ? i18n.t('new_agent') : 'New Agent');
    addBtn.className = 'agent-add-btn';
    addBtn.onclick = _acpCreateNewAgent;
    body.appendChild(addBtn);

    var listEl = document.createElement('div');
    listEl.id = 'acp-agent-list';
    body.appendChild(listEl);

    var sep = document.createElement('div');
    sep.className = 'agent-panel-sep';
    body.appendChild(sep);

    var editorEl = document.createElement('div');
    editorEl.id = 'acp-editor';
    body.appendChild(editorEl);

    panel.appendChild(body);
    var _agentWrapper = document.querySelector('.game-wrapper');
    (_agentWrapper || document.body).appendChild(panel);
    _agentPanel = panel;
}

function _acpRefreshList() {
    var container = document.getElementById('acp-agent-list');
    if (!container) return;
    container.innerHTML = '';
    agents.forEach(function(agent) {
        var card = document.createElement('div');
        card.className = 'agent-card' + (agent.id === _agentPanelSelectedId ? ' selected' : '');
        card.innerHTML =
            '<span class="agent-card-emoji">' + agent.emoji + '</span>' +
            '<span class="agent-card-info">' +
                '<span class="agent-card-name">' + agent.name + '</span>' +
                '<span class="agent-card-role">' + agent.role + '</span>' +
            '</span>';
        card.onclick = function() { _acpSelectAgent(agent.id); };
        container.appendChild(card);
    });
}

function _acpSelectAgent(agentId) {
    _agentPanelSelectedId = agentId;
    _acpRefreshList();
    var agent = agents.find(function(a){ return a.id === agentId; });
    if (!agent) return;
    _agentPanelEditState = JSON.parse(JSON.stringify({
        id: agent.id,
        name: agent.name,
        role: agent.role,
        emoji: agent.emoji,
        color: agent.color,
        gender: agent.gender,
        branch: agent.branch || 'UNASSIGNED',
        statusKey: agent.statusKey || '',
        providerKind: agent.providerKind || '',
        providerAgentId: agent.providerAgentId || '',
        profile: agent.profile || '',
        appearance: agent.getAppearance()
    }));
    _acpBuildEditor(agent);
}

function _acpBuildEditor(agent) {
    var col = document.getElementById('acp-editor');
    if (!col) return;
    col.innerHTML = '';
    var es = _agentPanelEditState;

    // Preview area
    var previewWrap = document.createElement('div');
    previewWrap.className = 'agent-preview-wrap';
    var previewCanvas = document.createElement('canvas');
    previewCanvas.width = 80; previewCanvas.height = 100;
    previewCanvas.className = 'agent-preview-canvas';
    _agentPanelPreviewCanvas = previewCanvas;
    _agentPanelPreviewCtx = previewCanvas.getContext('2d');
    previewWrap.appendChild(previewCanvas);
    var previewInfo = document.createElement('div');
    previewInfo.className = 'agent-preview-info';
    previewInfo.innerHTML =
        '<div class="agent-preview-name" id="acp-preview-name">' + es.name + '</div>' +
        '<div class="agent-preview-role" id="acp-preview-role">' + es.role + '</div>' +
        '<div class="agent-preview-role" id="acp-preview-branch">' + _tr('branch_field') + ': ' + getBranchDisplayName(es.branch) + '</div>' +
        '<div class="agent-preview-emoji" id="acp-preview-emoji">' + es.emoji + '</div>';
    previewWrap.appendChild(previewInfo);
    col.appendChild(previewWrap);

    // Save / Undo bar for agent edits
    var editBar = document.createElement('div');
    editBar.style.cssText = 'display:flex;gap:6px;padding:4px 8px;justify-content:center;';
    var agentSaveBtn = document.createElement('button');
    agentSaveBtn.textContent = _tr('save_btn');
    agentSaveBtn.id = 'acp-save-btn';
    agentSaveBtn.style.cssText = 'padding:4px 12px;background:#1b5e20;color:#66bb6a;border:1px solid #66bb6a;border-radius:4px;cursor:pointer;font-size:11px;';
    agentSaveBtn.addEventListener('click', function() {
        _acpSave();
        _acpUnsaved = false;
        _acpShowToast('💾 Agent saved!');
    });
    var agentUndoBtn = document.createElement('button');
    agentUndoBtn.textContent = _tr('undo');
    agentUndoBtn.id = 'acp-undo-btn';
    agentUndoBtn.style.cssText = 'padding:4px 12px;background:#b71c1c;color:#ef5350;border:1px solid #ef5350;border-radius:4px;cursor:pointer;font-size:11px;';
    agentUndoBtn.addEventListener('click', function() {
        if (_acpUndoStack.length === 0) { _acpShowToast('Nothing to undo'); return; }
        var prev = _acpUndoStack.pop();
        // Restore agent appearance
        Object.assign(agent, JSON.parse(prev));
        agent.appearance = JSON.parse(prev).appearance;
        _acpSelectAgent(agent.id);
    });
    editBar.appendChild(agentSaveBtn);
    editBar.appendChild(agentUndoBtn);

    var sectionsWrap = document.createElement('div');
    sectionsWrap.className = 'agent-sections-wrap';

    function makeSection(title) {
        var s = document.createElement('div');
        s.className = 'agent-edit-section';
        var h = document.createElement('div');
        h.className = 'agent-section-header';
        h.textContent = '─── ' + title + ' ───';
        s.appendChild(h);
        return s;
    }
    function makeField(label, control) {
        var row = document.createElement('div');
        row.className = 'agent-field-row';
        var lbl = document.createElement('span');
        lbl.className = 'agent-field-label';
        lbl.textContent = label + ':';
        row.appendChild(lbl);
        row.appendChild(control);
        return row;
    }

    // --- Identity ---
    var idSec = makeSection(_tr('agent_identity'));
    idSec.appendChild(makeField(_tr('agent_name'), _acpText(es.name, function(v){ es.name=v; _acpUpdatePreviewInfo(); _acpAutoSave(); })));
    idSec.appendChild(makeField(_tr('agent_role'), _acpText(es.role, function(v){ es.role=v; _acpUpdatePreviewInfo(); _acpAutoSave(); })));
    idSec.appendChild(makeField(_tr('agent_emoji'), _acpText(es.emoji, function(v){ es.emoji=v; _acpUpdatePreviewInfo(); _acpAutoSave(); })));
    idSec.appendChild(makeField(_tr('agent_gender'), _acpToggle(['M','F'], es.gender, function(v){
        es.gender=v; _acpAutoSave(); _acpBuildEditor(agent);
    })));
    sectionsWrap.appendChild(idSec);

    // --- Colors ---
    var clrSec = makeSection(_tr('agent_colors'));
    clrSec.appendChild(makeField(_tr('agent_shirt'), _acpColor(es.color, function(v){ es.color=v; _acpAutoSave(); })));
    var skinPresets = ['#fddcb5','#ffcc80','#e8b88a','#d4a574','#c68642','#8d5524'];
    clrSec.appendChild(makeField(_tr('agent_skin'), _acpSwatchRow(skinPresets, es.appearance.skinTone, function(v){ es.appearance.skinTone=v; _acpAutoSave(); }, true)));
    sectionsWrap.appendChild(clrSec);

    // --- Hair ---
    var hairSec = makeSection(_tr('agent_hair'));
    var hairStyles = ['bald','buzz','short','medium','long','curly','wavy','spiky','bun','ponytail','mohawk'];
    hairSec.appendChild(makeField(_tr('agent_style'), _acpGridSelect(hairStyles, es.appearance.hairStyle, function(v){ es.appearance.hairStyle=v; _acpAutoSave(); })));
    var hairColorPresets = ['#1a1a1a','#3e2723','#5d4037','#8d6e63','#dcc282','#bf360c','#616161','#e0e0e0'];
    hairSec.appendChild(makeField(_tr('color_field'), _acpSwatchRow(hairColorPresets, es.appearance.hairColor, function(v){ es.appearance.hairColor=v; _acpAutoSave(); }, true)));
    hairSec.appendChild(makeField(_tr('agent_highlight'), _acpColorNullable(es.appearance.hairHighlight, function(v){ es.appearance.hairHighlight=v; _acpAutoSave(); })));
    sectionsWrap.appendChild(hairSec);

    // --- Face ---
    var faceSec = makeSection(_tr('agent_face'));
    var ebStyles = ['thin','thick','angular','arched'];
    faceSec.appendChild(makeField(_tr('agent_eyebrows'), _acpGridSelect(ebStyles, es.appearance.eyebrowStyle, function(v){ es.appearance.eyebrowStyle=v; _acpAutoSave(); })));
    var eyePresets = ['#212121','#1565c0','#2e7d32','#5d4037','#6a1b9a','#37474f'];
    faceSec.appendChild(makeField(_tr('agent_eye_color'), _acpSwatchRow(eyePresets, es.appearance.eyeColor, function(v){ es.appearance.eyeColor=v; _acpAutoSave(); }, true)));
    if (es.gender === 'M') {
        var fhStyles = ['none','stubble','beard','goatee','mustache'];
        faceSec.appendChild(makeField(_tr('agent_facial_hair'), _acpGridSelect(fhStyles, es.appearance.facialHair || 'none', function(v){ es.appearance.facialHair=v==='none'?null:v; _acpAutoSave(); })));
        faceSec.appendChild(makeField(_tr('agent_beard_color'), _acpColorNullable(es.appearance.facialHairColor, function(v){ es.appearance.facialHairColor=v; _acpAutoSave(); })));
    }
    sectionsWrap.appendChild(faceSec);

    // --- Costumes ---
    var costSec = makeSection(_tr('agent_costumes'));
    var costumeTypes = ['none','lobster','chicken'];
    costSec.appendChild(makeField(_tr('agent_costume'), _acpGridSelect(costumeTypes, es.appearance.costume||'none', function(v){ es.appearance.costume=v==='none'?null:v; if(v!=='none') { es.appearance.headwear=null; } _costumeCache={}; _acpAutoSave(); })));
    var costumeNote = document.createElement('div');
    costumeNote.style.cssText = 'font-size:10px;color:#888;margin-top:4px;padding:0 2px;';
    costumeNote.textContent = _tr('costume_note') + ' 🦞 ' + _tr('option_lobster') + '  🐔 ' + _tr('option_chicken');
    costSec.appendChild(costumeNote);
    sectionsWrap.appendChild(costSec);

    // --- Accessories ---
    var accSec = makeSection(_tr('agent_accessories'));
    var hwTypes = ['none','hardhat','cap','crown','tiara','headband','goggles','headset','beanie'];
    accSec.appendChild(makeField(_tr('agent_headwear'), _acpGridSelect(hwTypes, es.appearance.headwear||'none', function(v){ es.appearance.headwear=v==='none'?null:v; _acpAutoSave(); })));
    accSec.appendChild(makeField(_tr('agent_hat_color'), _acpColor(es.appearance.headwearColor||'#888888', function(v){ es.appearance.headwearColor=v; _acpAutoSave(); })));
    var glTypes = ['none','round','square','sunglasses'];
    accSec.appendChild(makeField(_tr('agent_glasses'), _acpGridSelect(glTypes, es.appearance.glasses||'none', function(v){ es.appearance.glasses=v==='none'?null:v; _acpAutoSave(); })));
    accSec.appendChild(makeField(_tr('agent_lens_color'), _acpColor(es.appearance.glassesColor||'#333333', function(v){ es.appearance.glassesColor=v; _acpAutoSave(); })));
    sectionsWrap.appendChild(accSec);

    // --- Items ---
    var itemSec = makeSection(_tr('agent_items'));
    var heldItems = ['none','tablet','wrench','coffee','clipboard','pen','hammer','testTube','book'];
    itemSec.appendChild(makeField(_tr('agent_held_item'), _acpGridSelect(heldItems, es.appearance.heldItem||'none', function(v){ es.appearance.heldItem=v==='none'?null:v; _acpAutoSave(); })));
    var deskItems = ['none','anvil','trophy','calendar','envelope','money','ruler','marker','chart','plans','checklist','microscope','shield','phone','files'];
    itemSec.appendChild(makeField(_tr('agent_desk_item'), _acpGridSelect(deskItems, es.appearance.deskItem||'none', function(v){ es.appearance.deskItem=v==='none'?null:v; _acpAutoSave(); })));
    sectionsWrap.appendChild(itemSec);

    // --- Assignment ---
    var asnSec = makeSection(_tr('agent_assignment'));
    var branchSelect = document.createElement('select');
    branchSelect.style.cssText = 'width:100%;padding:4px 6px;background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;font-size:12px;margin-top:4px;';
    getBranchList().forEach(function(branch) {
        var opt = document.createElement('option');
        opt.value = branch.id;
        opt.textContent = branch.emoji + ' ' + getBranchDisplayName(branch.id);
        branchSelect.appendChild(opt);
    });
    branchSelect.value = es.branch || 'UNASSIGNED';
    branchSelect.addEventListener('change', function() {
        es.branch = this.value;
        _acpUpdatePreviewInfo();
        _acpAutoSave();
    });
    asnSec.appendChild(makeField(_tr('branch_field'), branchSelect));
    var ocSelect = document.createElement('select');
    ocSelect.style.cssText = 'width:100%;padding:4px 6px;background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;font-size:12px;margin-top:4px;';
    // Default option
    var defOpt = document.createElement('option');
    defOpt.value = '';
    defOpt.textContent = _tr('none');
    ocSelect.appendChild(defOpt);
    // Loading placeholder
    var loadOpt = document.createElement('option');
    loadOpt.value = '_loading';
    loadOpt.textContent = _tr('loading_agents');
    loadOpt.disabled = true;
    ocSelect.appendChild(loadOpt);
    ocSelect.value = es.statusKey || '';
    // Fetch agent list from server
    fetch('/agents-list').then(function(res) { return res.json(); }).then(function(data) {
        // Remove loading placeholder
        if (loadOpt.parentNode) loadOpt.remove();
        // Get already-assigned agent IDs (exclude current agent)
        var assignedIds = {};
        agents.forEach(function(a) {
            if (a.statusKey && a.id !== agent.id) assignedIds[a.statusKey] = a.name;
        });
        (data.agents || []).forEach(function(oc) {
            var opt = document.createElement('option');
            opt.value = oc.key;
            var label = (oc.emoji || '') + ' ' + oc.name + ' (' + oc.agentId + ')';
            if (assignedIds[oc.key]) label += ' — ' + _tr('assigned_to_agent', { name: assignedIds[oc.key] });
            opt.textContent = label;
            if (assignedIds[oc.key]) { opt.style.color = '#666'; }
            ocSelect.appendChild(opt);
        });
        ocSelect.value = es.statusKey || '';
    }).catch(function() {
            if (loadOpt.parentNode) { loadOpt.textContent = _tr('failed_to_load'); }
    });
    ocSelect.addEventListener('change', function() {
        es.statusKey = ocSelect.value;
        // Also update the agent's statusKey for status polling
        agent.statusKey = ocSelect.value;
        _acpAutoSave();
    });
    asnSec.appendChild(makeField(_tr('openclaw_agent'), ocSelect));
    sectionsWrap.appendChild(asnSec);

    col.appendChild(sectionsWrap);

    // Delete button (any agent except main)
    if (agent.id !== 'main') {
        var delWrap = document.createElement('div');
        delWrap.className = 'agent-delete-wrap';
        var delBtn = document.createElement('button');
    delBtn.innerHTML = _tr('delete_agent');
        delBtn.className = 'agent-delete-btn';
        delBtn.onclick = function() { _acpDeleteAgent(agent.id); };
        delWrap.appendChild(delBtn);
        col.appendChild(delWrap);
    }

    // Save / Undo bar at the bottom
    col.appendChild(editBar);

    _acpUpdatePreview();
}


function _acpText(value, onChange) {
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.value = value || '';
    inp.style.cssText = 'background:#1a1a3e;border:1px solid #2a2a4e;color:#e8e8f0;padding:4px 6px;font-size:11px;flex:1;border-radius:2px';
    inp.oninput = function(){ onChange(inp.value); };
    return inp;
}

function _acpColor(value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:6px';
    var inp = document.createElement('input');
    inp.type = 'color';
    inp.value = value || '#888888';
    inp.style.cssText = 'width:36px;height:24px;border:1px solid #2a2a4e;background:none;cursor:pointer;padding:1px';
    inp.oninput = function(){ onChange(inp.value); };
    wrap.appendChild(inp);
    return wrap;
}

function _acpColorNullable(value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:6px';
    var chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = !!value;
    chk.style.cssText = 'cursor:pointer';
    var inp = document.createElement('input');
    inp.type = 'color';
    inp.value = value || '#888888';
    inp.disabled = !value;
    inp.style.cssText = 'width:36px;height:24px;border:1px solid #2a2a4e;background:none;cursor:pointer;padding:1px;opacity:' + (value ? '1' : '0.3');
    chk.onchange = function(){
        inp.disabled = !chk.checked;
        inp.style.opacity = chk.checked ? '1' : '0.3';
        onChange(chk.checked ? inp.value : null);
    };
    inp.oninput = function(){ if (chk.checked) onChange(inp.value); };
    wrap.appendChild(chk);
    wrap.appendChild(inp);
    return wrap;
}

function _acpToggle(options, value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;gap:4px';
    options.forEach(function(opt) {
        var btn = document.createElement('button');
        btn.textContent = (opt === 'M' || opt === 'F') ? opt : _tr('option_' + opt);
        var active = opt === value;
        btn.style.cssText = 'padding:3px 10px;border:1px solid ' + (active ? '#ffd600' : '#2a2a4e') + ';background:' + (active ? '#3a3a10' : '#1a1a3e') + ';color:' + (active ? '#ffd600' : '#aaa') + ';cursor:pointer;font-size:11px;border-radius:2px';
        btn.onclick = function(){
            wrap.querySelectorAll('button').forEach(function(b){ b.style.borderColor='#2a2a4e'; b.style.background='#1a1a3e'; b.style.color='#aaa'; });
            btn.style.borderColor='#ffd600'; btn.style.background='#3a3a10'; btn.style.color='#ffd600';
            onChange(opt);
        };
        wrap.appendChild(btn);
    });
    return wrap;
}

function _acpSwatchRow(presets, value, onChange, allowCustom) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:3px;align-items:center';
    presets.forEach(function(c) {
        var sw = document.createElement('div');
        var isSelected = c.toLowerCase() === (value||'').toLowerCase();
        sw.className = 'swatch' + (isSelected ? ' selected' : '');
        sw.style.background = c;
        sw.title = c;
        sw.onclick = function(){
            wrap.querySelectorAll('.swatch').forEach(function(s){ s.classList.remove('selected'); });
            sw.classList.add('selected');
            onChange(c);
        };
        wrap.appendChild(sw);
    });
    if (allowCustom) {
        var inp = document.createElement('input');
        inp.type = 'color';
        inp.value = value || '#888888';
            inp.title = _tr('custom_color');
        inp.style.cssText = 'width:22px;height:22px;border:1px solid #444;background:none;cursor:pointer;padding:1px';
        inp.oninput = function(){
            wrap.querySelectorAll('.swatch').forEach(function(s){ s.classList.remove('selected'); });
            onChange(inp.value);
        };
        wrap.appendChild(inp);
    }
    return wrap;
}

function _acpGridSelect(options, value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:3px';
    options.forEach(function(opt) {
        var btn = document.createElement('button');
        btn.textContent = _tr('option_' + opt);
        btn.className = 'option-btn' + (opt === (value || 'none') ? ' selected' : '');
        btn.onclick = function(){
            wrap.querySelectorAll('.option-btn').forEach(function(b){ b.classList.remove('selected'); });
            btn.classList.add('selected');
            onChange(opt);
        };
        wrap.appendChild(btn);
    });
    return wrap;
}

function _acpUpdatePreviewInfo() {
    var es = _agentPanelEditState;
    if (!es) return;
    var nameEl = document.getElementById('acp-preview-name');
    var roleEl = document.getElementById('acp-preview-role');
    var branchEl = document.getElementById('acp-preview-branch');
    var emojiEl = document.getElementById('acp-preview-emoji');
    if (nameEl) nameEl.textContent = es.name;
    if (roleEl) roleEl.textContent = es.role;
    if (branchEl) branchEl.textContent = _tr('branch_field') + ': ' + getBranchDisplayName(es.branch);
    if (emojiEl) emojiEl.textContent = es.emoji;
    _acpUpdatePreview();
}

function _acpUpdatePreview() {
    var pCtx = _agentPanelPreviewCtx;
    var pCanvas = _agentPanelPreviewCanvas;
    if (!pCtx || !pCanvas) return;
    var es = _agentPanelEditState;
    if (!es) return;

    // Clear
    pCtx.clearRect(0, 0, pCanvas.width, pCanvas.height);
    pCtx.fillStyle = '#1a1a2e';
    pCtx.fillRect(0, 0, pCanvas.width, pCanvas.height);

    // Draw mini agent at center
    pCtx.save();
    pCtx.translate(40, 75);
    pCtx.scale(1.5, 1.5);

    var app = es.appearance;
    var isFem = es.gender === 'F';

    // Shadow
    pCtx.fillStyle = 'rgba(0,0,0,0.2)';
    pCtx.beginPath(); pCtx.ellipse(0, 4, 12, 5, 0, 0, Math.PI * 2); pCtx.fill();

    // Legs
    pCtx.fillStyle = '#1a1a2e';
    pCtx.fillRect(-10, -2, 8, 8); pCtx.fillRect(2, -2, 8, 8);

    // Body
    pCtx.fillStyle = es.color || '#888';
    if (isFem) {
        pCtx.fillRect(-9, -22, 18, 6); pCtx.fillRect(-8, -16, 16, 9);
    } else {
        pCtx.fillRect(-10, -22, 20, 15);
    }

    // Arms
    pCtx.fillRect(isFem ? -11 : -12, -20, 3, 10);
    pCtx.fillRect(9, -20, 3, 10);

    // Head
    pCtx.fillStyle = app.skinTone || '#ffcc80';
    pCtx.fillRect(-12, -38, 24, 18);

    // Hair
    _drawHairByConfig(pCtx, app.hairStyle, app.hairColor, app.hairHighlight);

    // Eyebrows
    var ebStyle = app.eyebrowStyle || (isFem ? 'thin' : 'thick');
    if (ebStyle === 'thin' || ebStyle === 'arched') {
        pCtx.fillStyle = '#5d4037';
        pCtx.fillRect(-5, -33, 4, 1); pCtx.fillRect(4, -33, 4, 1);
        pCtx.fillRect(-6, -34, 2, 1); pCtx.fillRect(7, -34, 2, 1);
    } else {
        pCtx.fillStyle = '#3e2723';
        pCtx.fillRect(-5, -34, 5, 2); pCtx.fillRect(4, -34, 5, 2);
    }

    // Eyes
    pCtx.fillStyle = '#fff';
    pCtx.fillRect(-6, -31, 6, 5); pCtx.fillRect(3, -31, 6, 5);
    pCtx.fillStyle = app.eyeColor || '#212121';
    pCtx.fillRect(-4, -30, 3, 4); pCtx.fillRect(5, -30, 3, 4);
    pCtx.fillStyle = '#fff';
    pCtx.fillRect(-3, -30, 1, 1); pCtx.fillRect(6, -30, 1, 1);
    if (isFem) {
        pCtx.fillStyle = '#212121';
        pCtx.fillRect(-7, -32, 1, 2); pCtx.fillRect(-6, -33, 1, 2);
        pCtx.fillRect(8, -32, 1, 2); pCtx.fillRect(9, -33, 1, 2);
    }

    // Nose
    var skinVal = app.skinTone || '#ffcc80';
    pCtx.fillStyle = darken(skinVal, 0.15);
    pCtx.fillRect(0, -27, 2, 2);

    // Mouth
    if (isFem) {
        pCtx.fillStyle = '#c4626a'; pCtx.fillRect(-2, -24, 5, 2);
        pCtx.fillStyle = '#d47a82'; pCtx.fillRect(-1, -24, 3, 1);
    } else {
        pCtx.fillStyle = darken(skinVal, 0.25); pCtx.fillRect(-2, -24, 4, 1);
    }

    // Facial hair
    if (app.facialHair) {
        pCtx.fillStyle = app.facialHairColor || darken(skinVal, 0.4);
        if (app.facialHair === 'stubble') { pCtx.globalAlpha=0.4; pCtx.fillRect(-8,-26,16,4); pCtx.globalAlpha=1; }
        else if (app.facialHair === 'beard') { pCtx.fillRect(-8,-27,16,8); pCtx.fillStyle=skinVal; pCtx.fillRect(-3,-26,6,3); }
        else if (app.facialHair === 'goatee') { pCtx.fillRect(-4,-25,8,4); }
        else if (app.facialHair === 'mustache') { pCtx.fillRect(-5,-27,10,2); }
    }

    // Headwear
    _drawHeadwear(pCtx, app.headwear, app.headwearColor, false);

    // Glasses
    _drawGlasses(pCtx, app.glasses, app.glassesColor, 0);

    // Held item
    _drawHeldItem(pCtx, app.heldItem, false);

    // Emoji
    pCtx.font = '8px sans-serif';
    pCtx.textAlign = 'center';
    pCtx.fillText(es.emoji || '😊', 0, -12);

    pCtx.restore();
}

function _acpSave() {
    var es = _agentPanelEditState;
    if (!es) return;

    // Ensure agents array in officeConfig
    if (!officeConfig.agents) officeConfig.agents = [];

    // Find or create config entry
    var idx = officeConfig.agents.findIndex(function(a){ return _agentConfigMatches(a, es); });
    if (idx >= 0) {
        officeConfig.agents[idx].appearance = es.appearance;
        officeConfig.agents[idx].name = es.name;
        officeConfig.agents[idx].role = es.role;
        officeConfig.agents[idx].emoji = es.emoji;
        officeConfig.agents[idx].color = es.color;
        officeConfig.agents[idx].gender = es.gender;
        officeConfig.agents[idx].branch = es.branch;
        officeConfig.agents[idx].statusKey = es.statusKey;
        officeConfig.agents[idx].providerKind = es.providerKind;
        officeConfig.agents[idx].providerAgentId = es.providerAgentId;
        officeConfig.agents[idx].profile = es.profile;
    } else {
        officeConfig.agents.push({ id: es.id, name: es.name, role: es.role, emoji: es.emoji, color: es.color, gender: es.gender, branch: es.branch, statusKey: es.statusKey, providerKind: es.providerKind, providerAgentId: es.providerAgentId, profile: es.profile, appearance: es.appearance });
    }

    // Update live agent object
    var agent = agents.find(function(a){ return a.id === es.id; });
    if (agent) {
        agent.name = es.name;
        agent.role = es.role;
        agent.emoji = es.emoji;
        agent.color = es.color;
        agent.gender = es.gender;
        agent.branch = es.branch;
    }

    saveOfficeConfig();
    _acpRefreshList();

    // Show saved toast
    _acpShowToast('✅ Saved!');
}

function _acpAutoSave() {
    var es = _agentPanelEditState;
    if (!es) return;

    // Push undo state before applying
    var agent = agents.find(function(a){ return a.id === es.id; });
    if (agent) {
        _acpUndoStack.push(JSON.stringify({ name: agent.name, role: agent.role, emoji: agent.emoji, color: agent.color, gender: agent.gender, branch: agent.branch, statusKey: agent.statusKey, appearance: JSON.parse(JSON.stringify(agent.appearance || {})) }));
        if (_acpUndoStack.length > 20) _acpUndoStack.shift();
    }

    if (!officeConfig.agents) officeConfig.agents = [];
    var idx = officeConfig.agents.findIndex(function(a){ return _agentConfigMatches(a, es); });
    var agentData = { id: es.id, name: es.name, role: es.role, emoji: es.emoji, color: es.color, gender: es.gender, branch: es.branch, statusKey: es.statusKey, providerKind: es.providerKind, providerAgentId: es.providerAgentId, profile: es.profile, appearance: es.appearance };
    if (idx >= 0) {
        Object.assign(officeConfig.agents[idx], agentData);
    } else {
        officeConfig.agents.push(agentData);
    }
    if (agent) {
        agent.name = es.name;
        agent.role = es.role;
        agent.emoji = es.emoji;
        agent.color = es.color;
        agent.gender = es.gender;
        agent.branch = es.branch;
        agent.appearance = JSON.parse(JSON.stringify(es.appearance));
        if (es.statusKey) agent.statusKey = es.statusKey;
    }

    _acpUnsaved = true;
    // Update Save/Undo button states
    var saveBtn = document.getElementById('acp-save-btn');
    var undoBtn = document.getElementById('acp-undo-btn');
    if (saveBtn) { saveBtn.style.opacity = '1'; saveBtn.disabled = false; }
    if (undoBtn) { undoBtn.style.opacity = '1'; undoBtn.disabled = false; }

    _acpUpdatePreview();
    // Don't auto-save to localStorage — user must click Save
}

function _acpShowToast(msg) {
    var toast = document.createElement('div');
    toast.textContent = msg;
    toast.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#1e3a1e;border:1px solid #4caf50;color:#4caf50;padding:8px 20px;border-radius:4px;font-size:12px;z-index:9999;pointer-events:none';
    document.body.appendChild(toast);
    setTimeout(function(){ if (toast.parentNode) toast.parentNode.removeChild(toast); }, 4000);
}

function _acpLocalizeCreateAgentError(errorText) {
    var msg = String(errorText || '').trim();
    if (/["']?main["']?\s+is\s+reserved/i.test(msg)) return _tr('agent_error_main_reserved');
    return msg || _tr('unknown');
}

function _acpShowMessageDialog(title, message, kind) {
    var existing = document.getElementById('agent-message-dialog');
    if (existing) existing.remove();
    var modal = document.createElement('div');
    modal.id = 'agent-message-dialog';
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-content agent-message-modal agent-message-' + escAttr(kind || 'info') + '">' +
            '<div class="modal-header">' +
                '<span class="modal-emoji">' + (kind === 'error' ? '⚠️' : 'ℹ️') + '</span>' +
                '<h2>' + escHtml(title || _tr('error')) + '</h2>' +
                '<span class="close-btn" data-agent-message-close>&times;</span>' +
            '</div>' +
            '<div class="agent-message-body">' + escHtml(message || '') + '</div>' +
            '<div class="modal-controls">' +
                '<button type="button" class="mtg-btn mtg-btn-end" data-agent-message-close>' + escHtml(_tr('confirm')) + '</button>' +
            '</div>' +
        '</div>';
    modal.addEventListener('click', function(e) {
        if (e.target === modal || e.target.closest('[data-agent-message-close]')) modal.remove();
    });
    modal.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' || e.key === 'Enter') modal.remove();
    });
    document.body.appendChild(modal);
    var close = modal.querySelector('[data-agent-message-close]');
    if (close) close.focus();
}

function _isCustomAgent(agentId) {
    // Built-in agents come from AGENT_DEFS
    return !AGENT_DEFS.find(function(d){ return d.id === agentId; });
}

function _acpPlatformDefaults(platform) {
    var id = platform && platform.id || 'openclaw';
    if (id === 'hermes') return { role: 'Hermes Agent', emoji: '⚕️' };
    if (id === 'codex') return { role: 'Codex Collaborator', emoji: '⚡' };
    if (id === 'claude-code') return { role: 'Claude Code Agent', emoji: '🧠' };
    return { role: _tr('ai_assistant'), emoji: '🤖' };
}

function _acpSlugAgentName(name) {
    var slug = String(name || '').trim().toLowerCase()
        .replace(/[^a-z0-9_.-]+/g, '-')
        .replace(/^[-._]+|[-._]+$/g, '')
        .slice(0, 64);
    return slug || 'agent';
}

function _acpShowCreateAgentDialog(platformsSource) {
    return new Promise(function(resolve) {
        var existing = document.getElementById('agent-create-dialog');
        if (existing) existing.remove();

        var platforms = [];
        var selectedPlatform = null;
        var defaults = _acpPlatformDefaults(null);
        var modal = document.createElement('div');
        modal.id = 'agent-create-dialog';
        modal.className = 'modal';
        modal.innerHTML =
            '<div class="modal-content agent-create-modal">' +
                '<div class="modal-header">' +
                    '<span class="modal-emoji">➕</span>' +
                    '<h2>' + escHtml(_tr('agent_create_title')) + '</h2>' +
                    '<span class="close-btn" data-acp-create-cancel>&times;</span>' +
                '</div>' +
                '<div class="agent-create-form">' +
                    '<div class="agent-create-label">' + escHtml(_tr('agent_platform_prompt')) + '</div>' +
                    '<div class="agent-platform-grid agent-platform-grid-loading">' + escHtml(_tr('loading')) + '</div>' +
                    '<label class="agent-create-field"><span>' + escHtml(_tr('agent_name_prompt')) + '</span><input id="agent-create-name" value="' + escAttr(_tr('new_agent_default')) + '"></label>' +
                    '<label class="agent-create-field"><span>' + escHtml(_tr('agent_role_prompt')) + '</span><input id="agent-create-role" value="' + escAttr(defaults.role) + '"></label>' +
                    '<label class="agent-create-field agent-create-emoji-field"><span>' + escHtml(_tr('emoji_prompt')) + '</span><input id="agent-create-emoji" value="' + escAttr(defaults.emoji) + '" maxlength="8"></label>' +
                '</div>' +
                '<div class="modal-controls">' +
                    '<button type="button" class="mtg-btn" data-acp-create-cancel>' + escHtml(_tr('cancel')) + '</button>' +
                    '<button type="button" class="mtg-btn mtg-btn-end" data-acp-create-submit disabled>' + escHtml(_tr('agent_create_submit')) + '</button>' +
                '</div>' +
            '</div>';

        function close(value) {
            modal.remove();
            resolve(value || null);
        }
        function renderPlatforms(nextPlatforms, errorText) {
            platforms = (nextPlatforms || []).filter(function(p){ return p && p.available && p.create; });
            var grid = modal.querySelector('.agent-platform-grid');
            var submit = modal.querySelector('[data-acp-create-submit]');
            if (!grid) return;
            grid.classList.remove('agent-platform-grid-loading');
            if (!platforms.length) {
                grid.classList.add('agent-platform-grid-loading');
                grid.textContent = errorText || _tr('no_agent_platforms');
                if (submit) submit.disabled = true;
                return;
            }
            selectedPlatform = platforms[0];
            grid.innerHTML = platforms.map(function(p, i) {
                return '<button type="button" class="agent-platform-card' + (i === 0 ? ' selected' : '') + '" data-platform-id="' + escAttr(p.id) + '">' +
                    '<span class="agent-platform-name">' + escHtml(p.label || p.id) + '</span>' +
                    '<span class="agent-platform-id">' + escHtml(p.id) + '</span>' +
                '</button>';
            }).join('');
            if (submit) submit.disabled = false;
            syncDefaults(selectedPlatform);
        }
        function syncDefaults(platform) {
            var d = _acpPlatformDefaults(platform);
            var role = document.getElementById('agent-create-role');
            var emoji = document.getElementById('agent-create-emoji');
            if (role && (!role.value.trim() || role.dataset.autofill === '1')) {
                role.value = d.role;
                role.dataset.autofill = '1';
            }
            if (emoji && (!emoji.value.trim() || emoji.dataset.autofill === '1')) {
                emoji.value = d.emoji;
                emoji.dataset.autofill = '1';
            }
        }

        modal.addEventListener('input', function(e) {
            if (e.target && (e.target.id === 'agent-create-role' || e.target.id === 'agent-create-emoji')) {
                e.target.dataset.autofill = '0';
            }
        });
        modal.addEventListener('click', function(e) {
            if (e.target === modal || e.target.closest('[data-acp-create-cancel]')) {
                close(null);
                return;
            }
            var platformBtn = e.target.closest('.agent-platform-card');
            if (platformBtn) {
                selectedPlatform = platforms.find(function(p) { return p.id === platformBtn.dataset.platformId; }) || selectedPlatform;
                modal.querySelectorAll('.agent-platform-card').forEach(function(btn) { btn.classList.toggle('selected', btn === platformBtn); });
                syncDefaults(selectedPlatform);
                return;
            }
            if (e.target.closest('[data-acp-create-submit]')) {
                if (!selectedPlatform) return;
                var name = (document.getElementById('agent-create-name').value || '').trim();
                var role = (document.getElementById('agent-create-role').value || '').trim();
                var emoji = (document.getElementById('agent-create-emoji').value || '').trim();
                var d = _acpPlatformDefaults(selectedPlatform);
                if (!name) {
                    var nameInput = document.getElementById('agent-create-name');
                    if (nameInput) nameInput.focus();
                    return;
                }
                close({ platform: selectedPlatform, name: name, role: role || d.role, emoji: emoji || d.emoji });
            }
        });
        modal.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') close(null);
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                var submit = modal.querySelector('[data-acp-create-submit]');
                if (submit) submit.click();
            }
        });
        document.body.appendChild(modal);
        var nameInput = document.getElementById('agent-create-name');
        var roleInput = document.getElementById('agent-create-role');
        var emojiInput = document.getElementById('agent-create-emoji');
        if (roleInput) roleInput.dataset.autofill = '1';
        if (emojiInput) emojiInput.dataset.autofill = '1';
        if (nameInput) {
            nameInput.focus();
            nameInput.select();
        }
        Promise.resolve(platformsSource).then(function(platformData) {
            var loaded = Array.isArray(platformData) ? platformData : (platformData && platformData.platforms) || [];
            renderPlatforms(loaded);
        }).catch(function() {
            renderPlatforms([{ id: 'openclaw', label: 'OpenClaw', available: true, create: true }]);
        });
    });
}

function _acpCreateNewAgent() {
    var platformsPromise = fetch('/api/agent-platforms').then(function(res) {
        return res.json();
    }).catch(function() {
        return { platforms: [{ id: 'openclaw', label: 'OpenClaw', available: true, create: true }] };
    });
    _acpShowCreateAgentDialog(platformsPromise).then(function(selection) {
        if (!selection) return null;
        var selectedPlatform = selection.platform;
        var agentName = selection.name;
        var agentRole = selection.role;
        var agentEmoji = selection.emoji;
        var agentProfile = _acpSlugAgentName(agentName);

        _acpShowToast(_tr('creating_agent_platform', { platform: selectedPlatform.label }));
        return fetch('/api/agent/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform: selectedPlatform.id, id: agentProfile, profile: agentProfile, name: agentName, role: agentRole, emoji: agentEmoji })
        }).then(function(res) { return res.json(); }).then(function(data) {
            return { data: data, platform: selectedPlatform, name: agentName, role: agentRole, emoji: agentEmoji, prompt: agentPrompt };
        });
    }).then(function(result) {
        if (!result) return;
        var data = result.data;
        if (data.error) {
            _acpShowMessageDialog(_tr('failed_create_agent'), _acpLocalizeCreateAgentError(data.error), 'error');
            return;
        }
        var newId = data.agentId;
        var newAgent = {
            id: newId,
            name: result.name,
            role: result.role,
            emoji: result.emoji,
            gender: 'M',
            color: '#607d8b',
            statusKey: newId,
            providerKind: data.providerKind || result.platform.id || 'openclaw',
            providerType: data.providerType || result.platform.providerType || 'runtime',
            providerAgentId: data.providerAgentId || data.profile || newId,
            profile: data.profile || data.providerAgentId || '',
            branch: 'UNASSIGNED',
            deskType: 'center',
        };

        var appearance = getDefaultAppearance(newId, 'M');
        if (!officeConfig.agents) officeConfig.agents = [];
        var savedAgent = Object.assign({}, newAgent, { appearance: appearance });
        var existingIdx = officeConfig.agents.findIndex(function(a) {
            return _agentConfigMatches(a, savedAgent);
        });
        if (existingIdx >= 0) officeConfig.agents[existingIdx] = Object.assign({}, officeConfig.agents[existingIdx], savedAgent);
        else officeConfig.agents.push(savedAgent);

        var startX = 500 + (agents.length * 20) % 100;
        var startY = 350;
        var agentInst = new Agent(newAgent);
        agentInst.desk = { x: startX, y: startY };
        agentInst.x = startX;
        agentInst.y = startY;
        agentInst.targetX = startX;
        agentInst.targetY = startY;
        agents.push(agentInst);
        agentMap[newId] = agentInst;

        saveOfficeConfig();
        _acpRefreshList();
        _acpSelectAgent(newId);
        _acpShowToast('✅ ' + _tr('agent_created_platform', { name: result.name, platform: result.platform.label }));
    }).catch(function(e) {
        _acpShowMessageDialog(_tr('error_create_agent'), _acpLocalizeCreateAgentError(e.message), 'error');
    });
}

function _acpDeleteAgent(agentId) {
    var agentName = agentId;
    var agentCfg = (officeConfig.agents || []).find(function(a) { return a.id === agentId; });
    if (agentCfg) agentName = agentCfg.name || agentId;

    var providerKind = (agentCfg && agentCfg.providerKind) || (agentId.indexOf('hermes-') === 0 ? 'Hermes' : (agentId.indexOf('codex-') === 0 ? 'Codex' : 'OpenClaw'));
    if (!confirm(_tr('delete_agent_confirm', { name: agentName, provider: providerKind }))) return;

    // Call server to delete from the backing agent platform.
    fetch('/api/agent/delete', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: agentId })
    }).then(function(res) { return res.json(); }).then(function(data) {
        if (data.error) {
        alert(_tr('failed_delete_agent') + ': ' + data.error);
            return;
        }

        // Remove from local state
        var idx = agents.findIndex(function(a){ return a.id === agentId; });
        if (idx >= 0) agents.splice(idx, 1);
        delete agentMap[agentId];

        if (officeConfig.agents) {
            var cidx = officeConfig.agents.findIndex(function(a){ return a.id === agentId; });
            if (cidx >= 0) officeConfig.agents.splice(cidx, 1);
        }

        saveOfficeConfig();
        _acpRefreshList();

        if (agents.length > 0) {
            _acpSelectAgent(agents[0].id);
        } else {
            var col = document.getElementById('acp-editor-col');
        if (col) col.innerHTML = '<div style="padding:20px;color:#666;font-size:11px">' + escHtml(_tr('no_agents_create')) + '</div>';
        }

        _acpShowToast('🗑️ ' + _tr('agent_deleted', { name: agentName }));
    }).catch(function(e) {
        alert(_tr('error_delete_agent') + ': ' + e.message);
    });
}

// --- INTERCEPT CLICKS IN EDIT MODE ---
// Patch into existing mouseup/touchend handlers
var _origHandleClick = typeof handleCanvasClick === 'function' ? handleCanvasClick : null;

canvas.addEventListener('click', function(e) {
    if (!editMode) return;
    if (_isPanning) return;
    if (_skipNextEditClick) { _skipNextEditClick = false; return; }
    var world = screenToWorld(e.clientX, e.clientY);
    handleEditClick(world.x, world.y, e.clientX, e.clientY, e);
});

// --- EDIT MODE DRAG: mousedown to start dragging selected item or multi-drag ---
var _editMouseDownPos = null; // track start position to detect drag vs click
var _editMouseMoved = false;
var _editDragTileHighlight = null; // {tx, ty} for glowing tile during drag

canvas.addEventListener('mousedown', function(e) {
    if (!editMode || e.button !== 0 || placingType) return;
    var world = screenToWorld(e.clientX, e.clientY);
    var hit = _findFurnitureAt(world.x, world.y);
    var isCtrl = e.ctrlKey || e.metaKey;
    _editMouseDownPos = { x: world.x, y: world.y, sx: e.clientX, sy: e.clientY };
    _editMouseMoved = false;
    _editDragTileHighlight = null;

    if (hit) {
        _isPanning = false;
        e.stopPropagation();

        if (isCtrl) {
            // Ctrl+click: toggle item in multi-selection
            var _mIdx = _multiSelected.indexOf(hit.id);
            if (_mIdx >= 0) {
                _multiSelected.splice(_mIdx, 1);
            } else {
                _multiSelected.push(hit.id);
            }
            selectedItemId = null;
            return;
        }

        // If hit is in multi-selection → start multi-drag
        if (_multiSelected.length > 0 && _multiSelected.indexOf(hit.id) >= 0) {
            _multiDragging = true;
            _multiDragStart = { x: world.x, y: world.y };
            _pushUndo();
            return;
        }

        // Hit is NOT in multi-selection → clear multi, single-select + start drag
        _multiSelected = [];
        selectedItemId = hit.id;
        isDragging = true;
        _pushUndo();
        dragOffset = { x: world.x - hit.x, y: world.y - hit.y };
    } else {
        // Click on empty space
        if (_marqueeMode) {
            // In marquee mode: start drawing the selection box
            _marqueeStart = { x: world.x, y: world.y };
            _marqueeEnd = null;
            _isPanning = false;
            e.stopPropagation();
            return;
        }
        if (!isCtrl) {
            // Normal click on empty: clear selections
            selectedItemId = null;
            selectedWallIdx = null;
            _multiSelected = [];
            if (_floatingToolbar) _floatingToolbar.style.display = 'none';
            _hideColorPicker();
        }
    }
});

// Double-click on empty space → activate marquee mode (click+drag to select area)
var _marqueeMode = false; // true = next mousedown starts marquee drawing
canvas.addEventListener('dblclick', function(e) {
    if (!editMode || placingType) return;
    var world = screenToWorld(e.clientX, e.clientY);
    var hit = _findFurnitureAt(world.x, world.y);
    if (!hit) {
        _marqueeMode = true;
        _isPanning = false;
        selectedItemId = null;
        selectedWallIdx = null;
        _multiSelected = [];
        // Show visual hint
        canvas.style.cursor = 'crosshair';
    }
});

// Stop dragging on mouseup (window-level to catch releases outside canvas)
window.addEventListener('mouseup', function() {
    _editDragTileHighlight = null;
    if (isDragging) {
        isDragging = false;
        _skipNextEditClick = true;
        saveOfficeConfig();
        getInteractionSpots();
        _syncAllDeskAssignments();
    }
    // Finalize marquee selection
    if (_marqueeStart) {
        if (_marqueeEnd) {
            var mx1 = Math.min(_marqueeStart.x, _marqueeEnd.x);
            var my1 = Math.min(_marqueeStart.y, _marqueeEnd.y);
            var mx2 = Math.max(_marqueeStart.x, _marqueeEnd.x);
            var my2 = Math.max(_marqueeStart.y, _marqueeEnd.y);
            // Only select if marquee is bigger than 10px world (not just a click)
            if (mx2 - mx1 > 10 && my2 - my1 > 10) {
                _multiSelected = [];
                officeConfig.furniture.forEach(function(f) {
                    var fb = FURNITURE_BOUNDS[f.type] || { w: TILE, h: TILE, ox: 0, oy: 0 };
                    var fox = fb.ox || 0, foy = fb.oy || 0;
                    var fx1 = f.x - fox * fb.w, fy1 = f.y - foy * fb.h;
                    var fx2 = fx1 + fb.w, fy2 = fy1 + fb.h;
                    if (fx1 < mx2 && fx2 > mx1 && fy1 < my2 && fy2 > my1) {
                        _multiSelected.push(f.id);
                    }
                });
            }
        }
        _marqueeStart = null;
        _marqueeEnd = null;
        _marqueeMode = false;
        canvas.style.cursor = '';
    }
    // End multi-drag
    if (_multiDragging) {
        _multiDragging = false;
        _multiDragStart = null;
        saveOfficeConfig();
        getInteractionSpots();
        _syncAllDeskAssignments();
    }
    _editMouseDownPos = null;
    _editMouseMoved = false;
});

// Right-click in edit mode → cancel placement
canvas.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    if (editMode) {
        _cancelPlacement();
        return;
    }
    var desk = _findDeskAtScreen(e.clientX, e.clientY);
    if (desk) _showAgentWorkspaceMenu(desk, e.clientX, e.clientY);
});

// Mobile equivalent: long-press a desk to reveal the same workspace affordance.
var _agentWorkspaceLongPressTimer = null;
canvas.addEventListener('touchstart', function(e) {
    if (editMode || e.touches.length !== 1) return;
    var t = e.touches[0];
    var desk = _findDeskAtScreen(t.clientX, t.clientY);
    if (!desk) return;
    clearTimeout(_agentWorkspaceLongPressTimer);
    _agentWorkspaceLongPressTimer = setTimeout(function() {
        _showAgentWorkspaceMenu(desk, t.clientX, t.clientY);
    }, 520);
}, { passive: true });
canvas.addEventListener('touchmove', function() {
    clearTimeout(_agentWorkspaceLongPressTimer);
}, { passive: true });
canvas.addEventListener('touchend', function() {
    clearTimeout(_agentWorkspaceLongPressTimer);
}, { passive: true });

// Keyboard shortcuts in edit mode
document.addEventListener('keydown', function(e) {
    if (!editMode) return;
    if (e.key === 'Escape') {
        if (_marqueeMode) {
            _marqueeMode = false;
            _marqueeStart = null;
            _marqueeEnd = null;
            canvas.style.cursor = '';
        } else if (placingType) {
            _cancelPlacement();
        } else if (selectedItemId) {
            _deselectItem();
        } else {
            toggleEditMode();
        }
    }
    if (e.key === 'Delete' || e.key === 'Backspace') {
        if (document.activeElement === document.body || document.activeElement === canvas) {
            if (selectedItemId) _deleteSelectedItem();
            else if (selectedWallIdx !== null) _deleteSelectedWall();
        }
    }
});

window.addEventListener('i18n:changed', function() {
    if (_catalogPanel) {
        _catalogPanel.remove();
        _catalogPanel = null;
        if (editMode) _showCatalogPanel();
    }
    if (_colorPickerEl) {
        _colorPickerEl.remove();
        _colorPickerEl = null;
        _colorPickerTarget = null;
    }
    if (_agentPanel) {
        var wasAgentPanelOpen = _agentPanel.classList.contains('visible');
        _agentPanel.remove();
        _agentPanel = null;
        if (wasAgentPanelOpen) toggleAgentPanel();
    }
    if (typeof _mtgRender === 'function' && !document.getElementById('meetingsModal').classList.contains('hidden')) {
        _mtgRender();
    }
    if (typeof renderSkillCards === 'function' && !document.getElementById('skillsLibraryModal').classList.contains('hidden')) {
        renderSkillCards();
    }
});

// ─── CATALOG PANEL ────────────────────────────────────────────

function _createCatalogPanel() {
    if (_catalogPanel) return;

    var panel = document.createElement('div');
    panel.id = 'furniture-catalog';
    panel.className = 'furniture-catalog';

    // Header
    var header = document.createElement('div');
    header.className = 'catalog-header';
    var titleSpan = document.createElement('span');
    titleSpan.textContent = _tr('furniture');
    var closeBtn = document.createElement('button');
    closeBtn.className = 'catalog-close-btn';
    closeBtn.textContent = '✕';
    closeBtn.title = _tr('close_panel');
    closeBtn.addEventListener('click', function(e) { e.stopPropagation(); toggleEditMode(); });
    header.appendChild(titleSpan);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    // Body
    var body = document.createElement('div');
    body.className = 'catalog-body';

    CATALOG_CATEGORIES.forEach(function(cat) {
        var section = document.createElement('div');
        section.className = 'catalog-section';

        var catHeader = document.createElement('div');
        catHeader.className = 'catalog-cat-header';
        var arrow = document.createElement('span');
        arrow.className = 'cat-arrow';
        arrow.textContent = '▼';
        catHeader.appendChild(arrow);
        catHeader.appendChild(document.createTextNode(' ' + _tr(cat.key)));
        catHeader.addEventListener('click', function() {
            var itemsDiv = section.querySelector('.catalog-items');
            var collapsed = itemsDiv.style.display === 'none';
            itemsDiv.style.display = collapsed ? '' : 'none';
            arrow.textContent = collapsed ? '▼' : '▶';
        });
        section.appendChild(catHeader);

        var itemsDiv = document.createElement('div');
        itemsDiv.className = 'catalog-items';

        cat.items.forEach(function(item) {
            var btn = document.createElement('div');
            btn.className = 'catalog-item';
            btn.dataset.type = item.type;

            var iconSpan = document.createElement('span');
            iconSpan.className = 'catalog-icon';
            iconSpan.textContent = item.icon;

            var labelSpan = document.createElement('span');
            labelSpan.className = 'catalog-label';
            labelSpan.textContent = _tr(item.key);

            btn.appendChild(iconSpan);
            btn.appendChild(labelSpan);
            btn.addEventListener('click', function() { _selectCatalogItem(item.type); });
            itemsDiv.appendChild(btn);
        });

        section.appendChild(itemsDiv);
        body.appendChild(section);
    });

    panel.appendChild(body);

    // Snap zone selector
    var snapSection = document.createElement('div');
    snapSection.className = 'catalog-snap-section';
    var snapLabel = document.createElement('div');
    snapLabel.className = 'catalog-cat-header';
    snapLabel.textContent = _tr('snap_zone');
    snapSection.appendChild(snapLabel);
    var snapSelect = document.createElement('select');
    snapSelect.id = 'snap-zone-select';
    snapSelect.className = 'snap-zone-select';
    for (var _zKey in SNAP_ZONES) {
        var opt = document.createElement('option');
        opt.value = _zKey;
        opt.textContent = _tr(SNAP_ZONES[_zKey].key);
        if (_zKey === activeSnapZone) opt.selected = true;
        snapSelect.appendChild(opt);
    }
    snapSelect.addEventListener('change', function() { activeSnapZone = this.value; });
    snapSection.appendChild(snapSelect);
    panel.appendChild(snapSection);

    // Floor edit toggle
    var floorSection = document.createElement('div');
    floorSection.className = 'catalog-snap-section';
    var floorBtn = document.createElement('button');
    floorBtn.id = 'floor-edit-btn';
    floorBtn.style.cssText = 'width:100%;padding:6px 8px;background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:7px;font-family:"Press Start 2P",cursive;';
    floorBtn.textContent = _tr('edit_floor_tiles');
    floorBtn.addEventListener('click', function() {
        _floorEditMode = !_floorEditMode;
        floorBtn.style.borderColor = _floorEditMode ? '#ffd700' : '#3a3a5e';
        floorBtn.style.color = _floorEditMode ? '#ffd700' : '#ccc';
        floorBtn.textContent = _floorEditMode ? _tr('done_floor_edit') : _tr('edit_floor_tiles');
    });
    floorSection.appendChild(floorBtn);
    panel.appendChild(floorSection);

    // === PET SECTION ===
    var petSection = document.createElement('div');
    petSection.className = 'catalog-snap-section';
    var petHeader = document.createElement('div');
    petHeader.className = 'catalog-cat-header';
    petHeader.textContent = _tr('office_pet');
    petSection.appendChild(petHeader);

    var petCfg = officeConfig.pet || { enabled: false, species: 'cat', name: '' };

    // Enable toggle
    var petEnableRow = document.createElement('div');
    petEnableRow.style.cssText = 'display:flex;align-items:center;gap:6px;margin:4px 0;';
    var petCheck = document.createElement('input');
    petCheck.type = 'checkbox';
    petCheck.checked = petCfg.enabled || false;
    petCheck.id = 'pet-enable-check';
    var petCheckLabel = document.createElement('label');
    petCheckLabel.htmlFor = 'pet-enable-check';
    petCheckLabel.textContent = _tr('enable_pet');
    petCheckLabel.style.cssText = 'color:#ccc;font-size:11px;cursor:pointer;';
    petEnableRow.appendChild(petCheck);
    petEnableRow.appendChild(petCheckLabel);
    petSection.appendChild(petEnableRow);

    // Species selector
    var petSpeciesRow = document.createElement('div');
    petSpeciesRow.style.cssText = 'display:flex;align-items:center;gap:6px;margin:4px 0;';
    var petSpeciesLabel = document.createElement('span');
    petSpeciesLabel.textContent = _tr('type_label');
    petSpeciesLabel.style.cssText = 'color:#aaa;font-size:11px;';
    var petSpeciesSelect = document.createElement('select');
    petSpeciesSelect.style.cssText = 'background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;padding:2px 4px;font-size:11px;';
    [{ v: 'cat', l: _tr('pet_cat') }, { v: 'pug', l: _tr('pet_pug') }, { v: 'lobster', l: _tr('pet_lobster') }].forEach(function(opt) {
        var o = document.createElement('option');
        o.value = opt.v; o.textContent = opt.l;
        if (petCfg.species === opt.v) o.selected = true;
        petSpeciesSelect.appendChild(o);
    });
    petSpeciesRow.appendChild(petSpeciesLabel);
    petSpeciesRow.appendChild(petSpeciesSelect);
    petSection.appendChild(petSpeciesRow);

    // Name input
    var petNameRow = document.createElement('div');
    petNameRow.style.cssText = 'display:flex;align-items:center;gap:6px;margin:4px 0;';
    var petNameLabel = document.createElement('span');
    petNameLabel.textContent = _tr('name_label');
    petNameLabel.style.cssText = 'color:#aaa;font-size:11px;';
    var petNameInput = document.createElement('input');
    petNameInput.type = 'text';
    petNameInput.value = petCfg.name || '';
    petNameInput.placeholder = 'Clawy';
    petNameInput.maxLength = 20;
    petNameInput.style.cssText = 'background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;padding:2px 6px;font-size:11px;width:80px;';
    petNameRow.appendChild(petNameLabel);
    petNameRow.appendChild(petNameInput);
    petSection.appendChild(petNameRow);

    // Apply changes
    function _applyPetConfig() {
        officeConfig.pet = {
            enabled: petCheck.checked,
            species: petSpeciesSelect.value,
            name: petNameInput.value || 'Clawy',
            x: (officeConfig.pet && officeConfig.pet.x) || Math.floor(W / 2),
            y: (officeConfig.pet && officeConfig.pet.y) || Math.floor(H / 2),
        };
        initPets();
        saveOfficeConfig();
    }
    petCheck.addEventListener('change', _applyPetConfig);
    petSpeciesSelect.addEventListener('change', _applyPetConfig);
    petNameInput.addEventListener('change', _applyPetConfig);

    panel.appendChild(petSection);

    // Instructions
    var instr = document.createElement('div');
    instr.className = 'catalog-instructions';
    instr.id = 'catalog-instr';
    instr.innerHTML = _tr('place_item_hint');
    panel.appendChild(instr);

    var wrapper = document.querySelector('.game-wrapper');
    wrapper.appendChild(panel);
    _catalogPanel = panel;

    // Create floating toolbar
    _createFloatingToolbar();
}

function _createFloatingToolbar() {
    if (_floatingToolbar) return;
    var tb = document.createElement('div');
    tb.id = 'furniture-toolbar';
    tb.className = 'furniture-floating-toolbar';
    tb.style.display = 'none';

    var delBtn = document.createElement('button');
    delBtn.className = 'ftb-btn delete-btn';
    delBtn.title = _tr('delete_shortcut');
    delBtn.textContent = '🗑️';
    delBtn.addEventListener('click', function() {
        if (selectedWallIdx !== null) _deleteSelectedWall();
        else _deleteSelectedItem();
    });

    var deselectBtn = document.createElement('button');
    deselectBtn.className = 'ftb-btn';
    deselectBtn.title = _tr('deselect_shortcut');
    deselectBtn.textContent = '✕';
    deselectBtn.addEventListener('click', function() { _deselectItem(); });

    var colorBtn = document.createElement('button');
    colorBtn.className = 'ftb-btn';
    colorBtn.id = 'ftb-color-btn';
    colorBtn.title = _tr('edit_wall_color');
    colorBtn.textContent = '🎨';
    colorBtn.style.display = 'none';
    colorBtn.addEventListener('click', function() {
        if (selectedWallIdx === null) return;
        var rect = _floatingToolbar ? _floatingToolbar.getBoundingClientRect() : { left: 200, bottom: 60 };
        _showWallColorPicker(selectedWallIdx, rect.left, rect.bottom);
    });

    var assignBtn = document.createElement('button');
    assignBtn.className = 'ftb-btn assign-btn';
    assignBtn.id = 'ftb-assign-btn';
    assignBtn.title = _tr('assign_agent');
    assignBtn.textContent = '👤';
    assignBtn.addEventListener('click', function() { _showDeskAssignMenu(); });

    var branchBtn = document.createElement('button');
    branchBtn.className = 'ftb-btn';
    branchBtn.id = 'ftb-branch-btn';
    branchBtn.title = _tr('assign_branch');
    branchBtn.textContent = '🏷️';
    branchBtn.style.display = 'none';
    branchBtn.addEventListener('click', function() { _showBranchAssignMenu(); });

    tb.appendChild(delBtn);
    tb.appendChild(colorBtn);
    tb.appendChild(assignBtn);
    tb.appendChild(branchBtn);
    tb.appendChild(deselectBtn);
    document.querySelector('.game-wrapper').appendChild(tb);
    _floatingToolbar = tb;
}

function _showCatalogPanel() {
    if (!_catalogPanel) _createCatalogPanel();
    _catalogPanel.classList.add('visible');
}

function _hideCatalogPanel() {
    if (_catalogPanel) _catalogPanel.classList.remove('visible');
    if (_floatingToolbar) _floatingToolbar.style.display = 'none';
    placingType = null;
    selectedItemId = null;
    isDragging = false;
    _ghostPos = null;
    _updateCatalogSelection();
}

function _selectCatalogItem(type) {
    placingType = type;
    wallPlacingPhase = 0;
    wallPlacingStart = null;
    selectedWallIdx = null;
    selectedItemId = null;
    isDragging = false;
    if (_floatingToolbar) _floatingToolbar.style.display = 'none';
    _updateCatalogSelection();
    var instr = document.getElementById('catalog-instr');
    if (instr) instr.innerHTML = _tr('place_canvas_hint');
}

function _cancelPlacement() {
    placingType = null;
    wallPlacingPhase = 0;
    wallPlacingStart = null;
    _ghostPos = null;
    _updateCatalogSelection();
    var instr = document.getElementById('catalog-instr');
    if (instr) instr.innerHTML = _tr('place_item_hint');
}

function _deselectItem() {
    selectedItemId = null;
    isDragging = false;
    if (_floatingToolbar) _floatingToolbar.style.display = 'none';
}

function _showBranchAssignMenu() {
    if (!selectedItemId) return;
    var selItem = null;
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        if (officeConfig.furniture[i].id === selectedItemId) { selItem = officeConfig.furniture[i]; break; }
    }
    if (!selItem || selItem.type !== 'branchSign') return;

    var existing = document.getElementById('branch-assign-menu');
    if (existing) existing.remove();

    var menu = document.createElement('div');
    menu.id = 'branch-assign-menu';
    menu.style.cssText = 'position:fixed;z-index:10001;background:#1a1a2e;border:2px solid #ffd600;border-radius:8px;padding:8px;min-width:180px;box-shadow:0 4px 16px rgba(0,0,0,0.5);';

    // Position near toolbar, clamped to viewport
    document.body.appendChild(menu);
    var tb = _floatingToolbar;
    if (tb) {
        var tbRect = tb.getBoundingClientRect();
        var menuH = menu.offsetHeight || 200;
        var left = tbRect.left;
        var top = tbRect.top - menuH - 10;
        if (top < 8) top = tbRect.bottom + 8;
        if (left + 200 > window.innerWidth - 8) left = window.innerWidth - 208;
        if (left < 8) left = 8;
        menu.style.left = left + 'px';
        menu.style.top = top + 'px';
    }

    var title = document.createElement('div');
    title.style.cssText = 'color:#ffd600;font-size:10px;font-family:"Press Start 2P",monospace;margin-bottom:6px;text-align:center;';
    title.textContent = _tr('assign_branch_title');
    menu.appendChild(title);

    var branches = getBranchList();
    branches.forEach(function(branch) {
        var btn = document.createElement('button');
        var isCurrent = selItem.branchId === branch.id;
        var neonColor = branch.color || _NEON_COLORS[branch.theme] || '#ccc';
        btn.style.cssText = 'display:block;width:100%;padding:5px 8px;margin:2px 0;background:#2a2a4e;color:' + neonColor + ';border:1px solid ' + (isCurrent ? '#ffd600' : '#3a3a5e') + ';border-radius:4px;cursor:pointer;font-size:11px;text-align:left;';
        btn.textContent = branch.emoji + ' ' + branch.name + (isCurrent ? ' ✓' : '');
        btn.addEventListener('mouseenter', function() { if (!isCurrent) btn.style.background = '#3a3a5e'; });
        btn.addEventListener('mouseleave', function() { btn.style.background = '#2a2a4e'; });
        btn.addEventListener('click', function() {
            _pushUndo();
            selItem.branchId = branch.id;
            saveOfficeConfig();
            menu.remove();
        });
        menu.appendChild(btn);
    });

    // Close on click outside
    setTimeout(function() {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', closeMenu); }
        });
    }, 100);
}

function _showDeskAssignMenu() {
    if (!selectedItemId) return;
    var selItem = null;
    for (var i = 0; i < officeConfig.furniture.length; i++) {
        if (officeConfig.furniture[i].id === selectedItemId) { selItem = officeConfig.furniture[i]; break; }
    }
    if (!selItem || (selItem.type !== 'desk' && selItem.type !== 'bossDesk')) return;

    // Get list of agents
    var agentNames = AGENT_DEFS.map(function(a) { return a.name; });
    // Get already-assigned agents (exclude this desk)
    var assigned = {};
    officeConfig.furniture.forEach(function(f) {
        if (f.assignedTo && f.id !== selItem.id) assigned[f.assignedTo] = true;
    });

    // Build dropdown menu
    var existing = document.getElementById('desk-assign-menu');
    if (existing) existing.remove();

    var menu = document.createElement('div');
    menu.id = 'desk-assign-menu';
    menu.style.cssText = 'position:fixed;z-index:10001;background:#1a1a2e;border:2px solid #ffd600;border-radius:8px;padding:8px;min-width:160px;box-shadow:0 4px 16px rgba(0,0,0,0.5);';

    // Position near toolbar, clamped to viewport
    document.body.appendChild(menu);
    var tb = _floatingToolbar;
    if (tb) {
        var tbRect = tb.getBoundingClientRect();
        var menuH = menu.offsetHeight || (agentNames.length * 28 + 50);
        var menuW = menu.offsetWidth || 180;
        var left = tbRect.left;
        var top = tbRect.top - menuH - 10;
        // Clamp to viewport
        if (top < 8) top = tbRect.bottom + 8;
        if (left + menuW > window.innerWidth - 8) left = window.innerWidth - menuW - 8;
        if (left < 8) left = 8;
        if (top + menuH > window.innerHeight - 8) top = window.innerHeight - menuH - 8;
        menu.style.left = left + 'px';
        menu.style.top = top + 'px';
    }

    var title = document.createElement('div');
    title.style.cssText = 'color:#ffd600;font-size:10px;font-family:"Press Start 2P",monospace;margin-bottom:6px;text-align:center;';
    title.textContent = _tr('assign_desk_title');
    menu.appendChild(title);

    // Unassign option
    var unBtn = document.createElement('button');
    unBtn.style.cssText = 'display:block;width:100%;padding:4px 8px;margin:2px 0;background:#2a2a4e;color:#aaa;border:1px solid #3a3a5e;border-radius:4px;cursor:pointer;font-size:11px;text-align:left;';
    unBtn.textContent = _tr('none');
    if (!selItem.assignedTo) { unBtn.style.borderColor = '#ffd600'; unBtn.style.color = '#ffd600'; }
    unBtn.addEventListener('click', function() {
        _pushUndo();
        delete selItem.assignedTo;
        _syncAllDeskAssignments();
        menu.remove();
    });
    menu.appendChild(unBtn);

    agentNames.forEach(function(name) {
        var btn = document.createElement('button');
        var isAssigned = assigned[name];
        var isCurrent = selItem.assignedTo === name;
        btn.style.cssText = 'display:block;width:100%;padding:4px 8px;margin:2px 0;background:#2a2a4e;color:' + (isAssigned ? '#555' : '#ccc') + ';border:1px solid ' + (isCurrent ? '#ffd600' : '#3a3a5e') + ';border-radius:4px;cursor:' + (isAssigned ? 'default' : 'pointer') + ';font-size:11px;text-align:left;';
        var agent = AGENT_DEFS.find(function(a) { return a.name === name; });
        btn.textContent = (agent ? agent.emoji + ' ' : '') + name + (isAssigned ? ' (' + _tr('assigned_suffix') + ')' : '') + (isCurrent ? ' ✓' : '');
        if (!isAssigned) {
            btn.addEventListener('mouseenter', function() { if (!isCurrent) btn.style.background = '#3a3a5e'; });
            btn.addEventListener('mouseleave', function() { btn.style.background = '#2a2a4e'; });
            btn.addEventListener('click', function() {
                _pushUndo();
                selItem.assignedTo = name;
                _syncAgentToDesk(selItem);
                menu.remove();
            });
        }
        menu.appendChild(btn);
    });

    // Close on click outside
    setTimeout(function() {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', closeMenu); }
        });
    }, 100);
}

function _deleteSelectedItem() {
    if (!selectedItemId) return;
    _pushUndo();
    // If deleting a desk, clear the assigned agent's desk reference
    var delItem = officeConfig.furniture.find(function(f) { return f.id === selectedItemId; });
    if (delItem && (delItem.type === 'desk' || delItem.type === 'bossDesk') && delItem.assignedTo) {
        agents.forEach(function(a) {
            if (a.name === delItem.assignedTo) {
                // Move agent to center as fallback
                a.desk = { x: Math.floor(W / 2), y: Math.floor(H / 2) };
                a.targetX = a.desk.x;
                a.targetY = a.desk.y;
            }
        });
    }
    officeConfig.furniture = officeConfig.furniture.filter(function(f) { return f.id !== selectedItemId; });
    selectedItemId = null;
    isDragging = false;
    if (_floatingToolbar) _floatingToolbar.style.display = 'none';
    getInteractionSpots();
    saveOfficeConfig(); // persist deletion + re-derive meeting slots
}

function _updateCatalogSelection() {
    if (!_catalogPanel) return;
    var items = _catalogPanel.querySelectorAll('.catalog-item');
    items.forEach(function(el) {
        if (el.dataset.type === placingType) {
            el.classList.add('selected');
        } else {
            el.classList.remove('selected');
        }
    });
}

// ─── WALL / FLOOR COLOR PICKER ────────────────────────────────

var _colorPickerEl = null;
var _colorPickerTarget = null; // { type: 'wall'|'floor', idx }

function _ensureColorPicker() {
    if (_colorPickerEl) return;
    var el = document.createElement('div');
    el.id = 'edit-color-picker';
    el.style.cssText = [
        'position:fixed; z-index:400; background:#1a1a2e; border:1px solid #ffd600;',
        'border-radius:8px; padding:10px 14px; display:none; flex-direction:column; gap:8px;',
        'box-shadow:0 4px 20px rgba(0,0,0,0.7); font-family:"Press Start 2P",cursive; font-size:7px; color:#ccc;',
        'min-width:200px;'
    ].join('');

    var closeRow = document.createElement('div');
    closeRow.style.cssText = 'display:flex;justify-content:space-between;align-items:center;';
    var titleEl = document.createElement('span');
    titleEl.id = 'edit-cp-title';
    titleEl.style.color = '#ffd600';
    titleEl.textContent = _tr('color_title');
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = 'background:none;border:1px solid #444;color:#aaa;cursor:pointer;padding:2px 6px;border-radius:3px;font-family:inherit;';
    closeBtn.addEventListener('click', _hideColorPicker);
    closeRow.appendChild(titleEl);
    closeRow.appendChild(closeBtn);
    el.appendChild(closeRow);

    // Row 1
    var row1 = document.createElement('div');
    row1.style.cssText = 'display:flex;align-items:center;gap:8px;';
    var lbl1 = document.createElement('span');
    lbl1.id = 'edit-cp-lbl1';
    lbl1.textContent = _tr('main_color');
    var inp1 = document.createElement('input');
    inp1.type = 'color'; inp1.id = 'edit-cp-color1';
    inp1.style.cssText = 'width:40px;height:28px;cursor:pointer;border:none;padding:0;border-radius:3px;';
    inp1.addEventListener('input', function() { _setActiveColorInput('edit-cp-color1'); _applyColorPicker(); });
    inp1.addEventListener('focus', function() { _setActiveColorInput('edit-cp-color1'); });
    inp1.addEventListener('click', function() { _setActiveColorInput('edit-cp-color1'); });
    row1.appendChild(lbl1); row1.appendChild(inp1);
    el.appendChild(row1);

    // Row 2
    var row2 = document.createElement('div');
    row2.style.cssText = 'display:flex;align-items:center;gap:8px;';
    var lbl2 = document.createElement('span');
    lbl2.id = 'edit-cp-lbl2';
    lbl2.textContent = _tr('accent_color');
    var inp2 = document.createElement('input');
    inp2.type = 'color'; inp2.id = 'edit-cp-color2';
    inp2.style.cssText = 'width:40px;height:28px;cursor:pointer;border:none;padding:0;border-radius:3px;';
    inp2.addEventListener('input', function() { _setActiveColorInput('edit-cp-color2'); _applyColorPicker(); });
    inp2.addEventListener('focus', function() { _setActiveColorInput('edit-cp-color2'); });
    inp2.addEventListener('click', function() { _setActiveColorInput('edit-cp-color2'); });
    row2.appendChild(lbl2); row2.appendChild(inp2);
    el.appendChild(row2);

    // Row 3
    var row3 = document.createElement('div');
    row3.id = 'edit-cp-row3';
    row3.style.cssText = 'display:none;align-items:center;gap:8px;';
    var lbl3 = document.createElement('span');
    lbl3.id = 'edit-cp-lbl3';
    lbl3.textContent = _tr('trim_2_color');
    var inp3 = document.createElement('input');
    inp3.type = 'color'; inp3.id = 'edit-cp-color3';
    inp3.style.cssText = 'width:40px;height:28px;cursor:pointer;border:none;padding:0;border-radius:3px;';
    inp3.addEventListener('input', function() { _setActiveColorInput('edit-cp-color3'); _applyColorPicker(); });
    inp3.addEventListener('focus', function() { _setActiveColorInput('edit-cp-color3'); });
    inp3.addEventListener('click', function() { _setActiveColorInput('edit-cp-color3'); });
    row3.appendChild(lbl3); row3.appendChild(inp3);
    el.appendChild(row3);

    // Favorites
    var favHeader = document.createElement('div');
    favHeader.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-top:4px;gap:8px;';
    var favTitle = document.createElement('span');
    favTitle.textContent = _tr('favorites');
    favTitle.style.cssText = 'color:#bbb;font-size:11px;';
    var favSaveBtn = document.createElement('button');
    favSaveBtn.id = 'edit-cp-save-favorite';
    favSaveBtn.textContent = _tr('save_current');
    favSaveBtn.style.cssText = 'background:#2a2a4e;border:1px solid #555;color:#ddd;cursor:pointer;padding:3px 6px;border-radius:3px;font-family:inherit;font-size:10px;';
    favSaveBtn.addEventListener('click', function() { _saveCurrentColorFavorite(); });
    favHeader.appendChild(favTitle);
    favHeader.appendChild(favSaveBtn);
    el.appendChild(favHeader);

    var favWrap = document.createElement('div');
    favWrap.id = 'edit-cp-favorites';
    favWrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;';
    el.appendChild(favWrap);

    document.body.appendChild(el);
    _colorPickerEl = el;
}

function _refreshColorFavoritesUI() {
    var wrap = document.getElementById('edit-cp-favorites');
    if (!wrap) return;
    wrap.innerHTML = '';
    colorFavorites.forEach(function(color, idx) {
        var btn = document.createElement('button');
        btn.className = 'cp-favorite-btn';
        btn.title = color;
        btn.style.cssText = 'width:24px;height:24px;border-radius:4px;border:1px solid rgba(255,255,255,0.35);cursor:pointer;background:' + color + ';';
        btn.addEventListener('click', function() { _applyFavoriteColor(color); });
        btn.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            colorFavorites.splice(idx, 1);
            saveColorFavorites();
            _refreshColorFavoritesUI();
        });
        wrap.appendChild(btn);
    });
}

function _activeColorInput() {
    if (_colorPickerTarget && _colorPickerTarget.activeInputId) {
        var active = document.getElementById(_colorPickerTarget.activeInputId);
        if (active) return active;
    }
    return document.getElementById('edit-cp-color1');
}

function _setActiveColorInput(inputId) {
    if (!_colorPickerTarget) _colorPickerTarget = {};
    _colorPickerTarget.activeInputId = inputId;
}

function _applyFavoriteColor(color) {
    var input = _activeColorInput();
    if (!input) return;
    input.value = color;
    _applyColorPicker();
}

function _saveCurrentColorFavorite() {
    var input = _activeColorInput();
    if (!input || !input.value) return;
    var color = input.value.toLowerCase();
    colorFavorites = colorFavorites.filter(function(c) { return c.toLowerCase() !== color; });
    colorFavorites.unshift(color);
    colorFavorites = colorFavorites.slice(0, 16);
    saveColorFavorites();
    _refreshColorFavoritesUI();
}

function _showWallColorPicker(wallIdx, sx, sy) {
    _ensureColorPicker();
    _colorPickerTarget = { type: 'interior-wall', idx: wallIdx };
    var wall = (officeConfig.walls.interior || [])[wallIdx] || {};
    document.getElementById('edit-cp-title').textContent = _tr('wall_color');
    document.getElementById('edit-cp-lbl1').textContent = _tr('main_color');
    document.getElementById('edit-cp-lbl2').textContent = _tr('trim_color');
    document.getElementById('edit-cp-lbl3').textContent = _tr('trim_2_color');
    document.getElementById('edit-cp-color1').value = _wallMainColor(wall);
    document.getElementById('edit-cp-color2').value = _wallTrimColor(wall);
    document.getElementById('edit-cp-color3').value = _wallTrim2Color(wall);
    _setActiveColorInput('edit-cp-color1');
    _refreshColorFavoritesUI();
    document.getElementById('edit-cp-color2').parentElement.style.display = 'flex';
    document.getElementById('edit-cp-row3').style.display = 'flex';
    _positionColorPicker(sx, sy);
}

function _showTopWallColorPicker(sx, sy) {
    _ensureColorPicker();
    _colorPickerTarget = { type: 'top-wall' };
    var wall = getTopWallConfig();
    document.getElementById('edit-cp-title').textContent = _tr('top_wall_color');
    document.getElementById('edit-cp-lbl1').textContent = _tr('main_color');
    document.getElementById('edit-cp-lbl2').textContent = _tr('trim_color');
    document.getElementById('edit-cp-color1').value = wall.color;
    document.getElementById('edit-cp-color2').value = wall.trimColor || wall.accentColor;
    document.getElementById('edit-cp-color2').parentElement.style.display = 'flex';
    document.getElementById('edit-cp-row3').style.display = 'none';
    _setActiveColorInput('edit-cp-color1');
    _refreshColorFavoritesUI();
    _positionColorPicker(sx, sy);
}

function _showFloorColorPicker(sx, sy) {
    _ensureColorPicker();
    _colorPickerTarget = { type: 'floor' };
    document.getElementById('edit-cp-title').textContent = _tr('floor_color');
    document.getElementById('edit-cp-lbl1').textContent = _tr('tile_a_color');
    document.getElementById('edit-cp-lbl2').textContent = _tr('tile_b_color');
    document.getElementById('edit-cp-color1').value = officeConfig.floor.color1;
    document.getElementById('edit-cp-color2').value = officeConfig.floor.color2;
    document.getElementById('edit-cp-color2').parentElement.style.display = 'flex';
    document.getElementById('edit-cp-row3').style.display = 'none';
    _setActiveColorInput('edit-cp-color1');
    _refreshColorFavoritesUI();
    _positionColorPicker(sx, sy);
}

function _positionColorPicker(sx, sy) {
    var el = _colorPickerEl;
    el.style.display = 'flex';
    // Position below click, clamped to viewport
    var w = 220, h = _colorPickerTarget && _colorPickerTarget.type === 'interior-wall' ? 168 : 130;
    var vw = window.innerWidth, vh = window.innerHeight;
    var left = Math.min(sx, vw - w - 10);
    var top  = Math.min(sy + 10, vh - h - 10);
    el.style.left = left + 'px';
    el.style.top  = top  + 'px';
}

function _applyColorPicker() {
    if (!_colorPickerTarget) return;
    _pushUndo();
    var c1 = document.getElementById('edit-cp-color1').value;
    var c2 = document.getElementById('edit-cp-color2').value;
    var c3 = document.getElementById('edit-cp-color3') ? document.getElementById('edit-cp-color3').value : null;
    if (_colorPickerTarget.type === 'interior-wall') {
        var wall = officeConfig.walls.interior[_colorPickerTarget.idx];
        if (wall) {
            wall.color = c1;
            wall.accentColor = c1;
            wall.trimColor = c2;
            wall.trim2Color = c3 || wall.trim2Color || '#37474f';
        }
    } else if (_colorPickerTarget.type === 'top-wall') {
        if (!officeConfig.walls.topWall) officeConfig.walls.topWall = {};
        officeConfig.walls.topWall.color = c1;
        officeConfig.walls.topWall.accentColor = c2;
        officeConfig.walls.topWall.trimColor = c2;
        officeConfig.walls.trimColor = c2;
        if (officeConfig.walls.sections && officeConfig.walls.sections[0]) {
            officeConfig.walls.sections[0].color = c1;
            officeConfig.walls.sections[0].accentColor = c2;
        }
        officeConfig.walls.trimColor = c2;
    } else if (_colorPickerTarget.type === 'floor') {
        officeConfig.floor.color1 = c1;
        officeConfig.floor.color2 = c2;
    } else if (_colorPickerTarget.type === 'couch') {
        var cItem = officeConfig.furniture.find(function(f){ return f.id === _colorPickerTarget.itemId; });
        if (cItem) {
            cItem.couchColor = c1;
            _saveOfficeConfig();
        }
    }
}

function _showCouchColorEditor(item) {
    _ensureColorPicker();
    _colorPickerTarget = { type: 'couch', itemId: item.id };
    document.getElementById('edit-cp-title').textContent = _tr('couch_color');
    document.getElementById('edit-cp-lbl1').textContent = _tr('color_label');
    document.getElementById('edit-cp-color1').value = item.couchColor || '#3f51b5';
    document.getElementById('edit-cp-color2').parentElement.style.display = 'none';
    document.getElementById('edit-cp-row3').style.display = 'none';
    _setActiveColorInput('edit-cp-color1');
    _refreshColorFavoritesUI();
    // Position near the toolbar
    var tb = _floatingToolbar.getBoundingClientRect();
    _positionColorPicker(tb.left, tb.bottom);
}

function _hideColorPicker() {
    if (_colorPickerEl) _colorPickerEl.style.display = 'none';
    _colorPickerTarget = null;
}

// ─── SKILLS MANAGEMENT ──────────────────────────────────────────────────────
var _currentSkillAgent = null; // statusKey of agent whose skills are shown
var _editingSkillName = null;
var _skillWorkshopProposals = [];
var _skillWorkshopErrors = [];
var _skillWorkshopLoaded = false;
var _skillWorkshopLoading = false;

function _showSkillLibraryVersionDialog(skillName, onUpdate) {
    var existing = document.getElementById('skill-library-version-dialog');
    if (existing) existing.remove();
    var modal = document.createElement('div');
    modal.id = 'skill-library-version-dialog';
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-content" style="max-width:420px;">' +
            '<div class="modal-header">' +
                '<span class="modal-emoji">📚</span>' +
                '<h2>Skill Library</h2>' +
                '<span class="close-btn" data-skl-version-cancel>&times;</span>' +
            '</div>' +
            '<div style="padding:14px;color:#ddd;font-size:13px;line-height:1.45;">' +
                '<p style="margin:0 0 12px 0;">Skill already exists in the Skill Library.</p>' +
                '<p style="margin:0;color:#aaa;">The agent version of <b>' + escHtml(skillName) + '</b> is different from the saved library version.</p>' +
            '</div>' +
            '<div class="skl-editor-actions" style="padding:0 14px 14px 14px;">' +
                '<button class="mtg-btn" data-skl-version-update>Update Skill Library Version</button>' +
                '<button class="mtg-btn" data-skl-version-cancel>Cancel</button>' +
            '</div>' +
        '</div>';
    modal.addEventListener('click', function(e) {
        if (e.target === modal || e.target.closest('[data-skl-version-cancel]')) {
            modal.remove();
            return;
        }
        if (e.target.closest('[data-skl-version-update]')) {
            modal.remove();
            if (typeof onUpdate === 'function') onUpdate();
        }
    });
    document.body.appendChild(modal);
}

async function saveAgentSkillToLibrary(agentId, skillName, onDone) {
    if (!agentId || !skillName) return;
    async function requestSave(overwrite) {
        var res = await fetch('/api/skills-library/save-from-agent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId: agentId, skill: skillName, overwrite: !!overwrite })
        });
        return await res.json();
    }
    try {
        var data = await requestSave(false);
        if (data.ok) {
            if (data.status === 'identical') {
        alert(_tr('skill_exists_library'));
            } else {
                _acpShowToast('✅ ' + (data.status === 'updated' ? 'Updated' : 'Saved') + ' "' + skillName + '" in Skill Library');
            }
            if (typeof refreshSkillsList === 'function') refreshSkillsList();
            if (typeof onDone === 'function') onDone(data);
            return;
        }
        if (data.exists && data.different) {
            _showSkillLibraryVersionDialog(skillName, async function() {
                var updated = await requestSave(true);
                if (updated.ok) {
                    _acpShowToast('✅ Updated Skill Library Version for "' + skillName + '"');
                    if (typeof refreshSkillsList === 'function') refreshSkillsList();
                    if (typeof onDone === 'function') onDone(updated);
                } else {
                    _acpShowToast('❌ ' + (updated.error || 'Could not update Skill Library version'));
                }
            });
            return;
        }
        _acpShowToast('❌ ' + (data.error || 'Could not save skill to library'));
    } catch (e) {
        _acpShowToast('❌ Could not save skill to library: ' + e.message);
    }
}

function _skillWorkshopProposalId(p) {
    return (p && (p.id || p.proposalId || p.proposal_id)) || '';
}

function _skillWorkshopTitle(p) {
    return (p && (p.skillName || p.skill || p.name || p.title || p.description || _skillWorkshopProposalId(p))) || 'Untitled proposal';
}

function _skillWorkshopStatus(p) {
    return (p && (p.status || p.state || p.reviewState || 'pending')) || 'pending';
}

function _skillWorkshopSummary(p) {
    var parts = [];
    if (p.agentName) parts.push((p.agentEmoji ? p.agentEmoji + ' ' : '') + p.agentName);
    if (p.kind || p.action || p.type) parts.push(p.kind || p.action || p.type);
    if (p.updatedAt || p.createdAt) parts.push(_formatAgentWorkspaceTime(p.updatedAt || p.createdAt));
    return parts.join(' · ');
}

async function refreshSkillWorkshopQueue() {
    if (_skillWorkshopLoading) return;
    _skillWorkshopLoading = true;
    var agentParam = '';
    try {
        var res = await fetch('/api/skills-workshop' + agentParam, { cache: 'no-store' });
        var data = await res.json();
        _skillWorkshopProposals = data.proposals || [];
        _skillWorkshopErrors = data.errors || [];
        _skillWorkshopLoaded = true;
    } catch (e) {
        _skillWorkshopProposals = [];
        _skillWorkshopErrors = [{ error: e.message || String(e) }];
        _skillWorkshopLoaded = true;
    } finally {
        _skillWorkshopLoading = false;
    }
    renderSkillWorkshopQueue();
}

function renderSkillWorkshopQueue() {
    var containers = [
        document.getElementById('skill-workshop-list'),
        document.getElementById('agent-workspace-skill-workshop-list')
    ].filter(Boolean);
    if (!containers.length) return;
    var proposals = (_skillWorkshopProposals || []).filter(function(p) {
        return _skillWorkshopStatus(p).toLowerCase() === 'pending';
    });
    var html = '';
    if (_skillWorkshopLoading && !_skillWorkshopLoaded) {
        html = '<span style="color:#666;font-size:11px;">Loading proposals...</span>';
    } else if (!proposals.length) {
        html = '<div class="skill-workshop-empty">No pending skill proposals.</div>';
    } else {
        html = proposals.map(function(p) {
            var proposalId = _skillWorkshopProposalId(p);
            var idx = _skillWorkshopProposals.indexOf(p);
            return '<div class="skill-workshop-row" data-skill-workshop-index="' + idx + '">' +
                '<div class="skill-workshop-main">' +
                    '<b>' + escHtml(_skillWorkshopTitle(p)) + '</b>' +
                    '<div class="skill-workshop-meta">' + escHtml(_skillWorkshopSummary(p)) + '</div>' +
                    '<div class="skill-workshop-status">' + escHtml(_skillWorkshopStatus(p)) + '</div>' +
                '</div>' +
                '<div class="skill-workshop-actions">' +
                    '<button type="button" data-skill-workshop-action="inspect" data-skill-workshop-index="' + idx + '">Review</button>' +
                    '<button type="button" data-skill-workshop-action="apply" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Apply</button>' +
                    '<button type="button" data-skill-workshop-action="revise" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Revise</button>' +
                    '<button type="button" data-skill-workshop-action="reject" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Reject</button>' +
                    '<button type="button" data-skill-workshop-action="quarantine" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Quarantine</button>' +
                '</div>' +
            '</div>';
        }).join('');
    }
    if (_skillWorkshopErrors.length) {
        html += '<div class="skill-workshop-error">Some agent queues could not load.</div>';
    }
    containers.forEach(function(el) { el.innerHTML = html; });
}

function _skillWorkshopProposalContent(detail) {
    if (!detail) return '';
    if (typeof detail.proposalContent === 'string') return detail.proposalContent;
    if (typeof detail.content === 'string') return detail.content;
    if (typeof detail.body === 'string') return detail.body;
    var proposal = detail.proposal || detail;
    if (typeof proposal.proposalContent === 'string') return proposal.proposalContent;
    if (typeof proposal.content === 'string') return proposal.content;
    if (typeof proposal.body === 'string') return proposal.body;
    if (Array.isArray(detail.files)) {
        var primary = detail.files.find(function(f) { return /PROPOSAL\\.md$/i.test(f.path || f.name || ''); }) || detail.files[0];
        if (primary && typeof primary.content === 'string') return primary.content;
    }
    return JSON.stringify(detail, null, 2);
}

async function inspectSkillWorkshopProposal(index, mode) {
    var proposal = _skillWorkshopProposals[index];
    if (!proposal) return;
    var proposalId = _skillWorkshopProposalId(proposal);
    if (!proposalId || !proposal.agentId) {
        _acpShowToast('❌ Proposal is missing agent or id');
        return;
    }
    try {
        var url = '/api/skills-workshop/inspect?agentId=' + encodeURIComponent(proposal.agentId) + '&proposalId=' + encodeURIComponent(proposalId);
        var detail = await fetch(url, { cache: 'no-store' }).then(function(r) { return r.json(); });
        _showSkillWorkshopReviewDialog(proposal, detail, mode === 'revise');
    } catch (e) {
        _acpShowToast('❌ Could not inspect proposal: ' + e.message);
    }
}

function _showSkillWorkshopReviewDialog(proposal, detail, startEditing) {
    var existing = document.getElementById('skill-workshop-review-dialog');
    if (existing) existing.remove();
    var proposalId = _skillWorkshopProposalId(proposal);
    var content = _skillWorkshopProposalContent(detail);
    var isEditing = !!startEditing;
    var modal = document.createElement('div');
    modal.id = 'skill-workshop-review-dialog';
    modal.className = 'modal';
    function renderDialogBody() {
        modal.innerHTML =
            '<div class="modal-content" style="max-width:760px;">' +
                '<div class="modal-header">' +
                    '<span class="modal-emoji">🧪</span>' +
                    '<h2>Skill Workshop</h2>' +
                    '<span class="close-btn" data-skill-workshop-close>&times;</span>' +
                '</div>' +
                '<div class="skill-workshop-review-head">' +
                    '<b>' + escHtml(_skillWorkshopTitle(proposal)) + '</b>' +
                    '<span>' + escHtml((proposal.agentEmoji ? proposal.agentEmoji + ' ' : '') + (proposal.agentName || proposal.agentId || '')) + '</span>' +
                    '<span>' + escHtml(_skillWorkshopStatus(proposal)) + '</span>' +
                    '<span class="skill-workshop-review-mode">' + (isEditing ? 'Editing revision' : 'Review only') + '</span>' +
                '</div>' +
                '<textarea class="skill-workshop-review-textarea' + (isEditing ? ' is-editing' : ' is-readonly') + '" spellcheck="false"' + (isEditing ? '' : ' readonly') + '>' + escTextarea(content) + '</textarea>' +
                '<div class="skl-editor-actions" style="padding:0 14px 14px 14px;">' +
                    (isEditing
                        ? '<button class="mtg-btn" data-skill-workshop-dialog-action="saveRevision">Save revision</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="cancelRevision">Cancel revision</button>'
                        : '<button class="mtg-btn" data-skill-workshop-dialog-action="apply">Apply</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="startRevision">Revise</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="reject">Reject</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="quarantine">Quarantine</button>' +
                            '<button class="mtg-btn" data-skill-workshop-close>Cancel</button>') +
                '</div>' +
            '</div>';
    }
    renderDialogBody();
    modal.addEventListener('click', function(e) {
        if (e.target === modal || e.target.closest('[data-skill-workshop-close]')) {
            modal.remove();
            return;
        }
        var actionBtn = e.target.closest('[data-skill-workshop-dialog-action]');
        if (!actionBtn) return;
        var action = actionBtn.dataset.skillWorkshopDialogAction;
        if (action === 'startRevision') {
            isEditing = true;
            renderDialogBody();
            var editor = modal.querySelector('.skill-workshop-review-textarea');
            if (editor) editor.focus();
            return;
        }
        if (action === 'cancelRevision') {
            isEditing = false;
            renderDialogBody();
            return;
        }
        if (action === 'saveRevision') {
            var revisedContent = modal.querySelector('.skill-workshop-review-textarea').value;
            runSkillWorkshopAction(proposal.agentId, proposalId, 'revise', revisedContent, function() { modal.remove(); });
            return;
        }
        runSkillWorkshopAction(proposal.agentId, proposalId, action, '', function() { modal.remove(); });
    });
    document.body.appendChild(modal);
}

async function runSkillWorkshopAction(agentId, proposalId, action, proposalContent, onDone) {
    var body = { agentId: agentId, proposalId: proposalId, action: action };
    if (action === 'reject' || action === 'quarantine') {
        var reason = prompt((action === 'reject' ? 'Reject' : 'Quarantine') + ' reason:', '');
        if (reason == null) return;
        body.reason = reason;
    }
    if (action === 'revise') {
        body.proposalContent = proposalContent || '';
        if (!body.proposalContent.trim()) {
            _acpShowToast('❌ Revision content is required');
            return;
        }
    }
    try {
        var res = await fetch('/api/skills-workshop/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        var data = await res.json();
        if (!data.ok && data.error) {
            _acpShowToast('❌ ' + data.error);
            return;
        }
        _acpShowToast('✅ Skill Workshop proposal ' + action + ' complete');
        if (typeof onDone === 'function') onDone(data);
        refreshSkillWorkshopQueue();
        if (_agentWorkspace.agent && _agentWorkspace.activeTab === 'skills') _loadAgentWorkspace(_agentWorkspace.agent);
    } catch (e) {
        _acpShowToast('❌ Skill Workshop action failed: ' + e.message);
    }
}

document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-skill-workshop-action]');
    if (!btn) return;
    var idx = Number(btn.dataset.skillWorkshopIndex);
    var action = btn.dataset.skillWorkshopAction;
    var proposal = _skillWorkshopProposals[idx];
    if (!proposal) return;
    var proposalId = _skillWorkshopProposalId(proposal);
    if (action === 'inspect') {
        inspectSkillWorkshopProposal(idx, 'review');
    } else if (action === 'revise') {
        inspectSkillWorkshopProposal(idx, 'revise');
    } else {
        runSkillWorkshopAction(proposal.agentId, proposalId, action, '', null);
    }
});

function loadAgentSkills(agentKey) {
    _currentSkillAgent = agentKey;
    var listEl = document.getElementById('skills-list');
    if (!listEl) return;
    listEl.innerHTML = '<span style="color:#666;font-size:11px;">' + escHtml(_tr('loading_skills')) + '</span>';
    fetch('/api/agent/' + encodeURIComponent(agentKey) + '/skills')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            listEl.innerHTML = '';
            if (!data.skills || data.skills.length === 0) {
            listEl.innerHTML = '<span style="color:#666;font-size:11px;">' + escHtml(_tr('no_skills_configured')) + '</span>';
                return;
            }
            data.skills.forEach(function(skill) {
                var row = document.createElement('div');
                row.className = 'skill-row';
                var info = document.createElement('div');
                info.className = 'skill-row-info';
                info.innerHTML = '<span style="font-weight:bold;">' + escHtml(skill.name) + '</span>' +
                    (skill.description ? '<br><span style="color:#888;font-size:10px;">' + escHtml(skill.description).substring(0, 80) + '</span>' : '');
                var btns = document.createElement('div');
                btns.className = 'skill-row-btns';
                var editBtn = document.createElement('button');
                editBtn.textContent = '✏️';
            editBtn.title = _tr('edit_skill_title');
                editBtn.onclick = (function(sName) { return function() { editSkill(sName); }; })(skill.name);
                var libraryBtn = document.createElement('button');
            libraryBtn.textContent = _tr('save_skill_library');
            libraryBtn.title = _tr('save_skill_library_hint');
                libraryBtn.onclick = (function(sName) {
                    return function() { saveAgentSkillToLibrary(_currentSkillAgent, sName, function() { loadAgentSkills(_currentSkillAgent); }); };
                })(skill.name);
                var delBtn = document.createElement('button');
                delBtn.textContent = '🗑️';
            delBtn.title = _tr('remove_skill');
                delBtn.onclick = (function(sName) { return function() { deleteSkill(sName); }; })(skill.name);
                btns.appendChild(editBtn);
                btns.appendChild(libraryBtn);
                btns.appendChild(delBtn);
                row.appendChild(info);
                row.appendChild(btns);
                listEl.appendChild(row);
            });
        })
        .catch(function(e) {
        listEl.innerHTML = '<span style="color:#f44336;font-size:11px;">' + escHtml(_tr('error_loading_skills')) + '</span>';
        });
    refreshSkillWorkshopQueue();
}

function showAddSkillForm() {
    document.getElementById('skill-add-form').style.display = 'block';
    document.getElementById('skill-edit-form').style.display = 'none';
    document.getElementById('skill-new-name').value = '';
    document.getElementById('skill-new-content').value = '';
    document.getElementById('skill-new-name').focus();
}

function hideAddSkillForm() {
    document.getElementById('skill-add-form').style.display = 'none';
}

async function showLibraryPicker() {
    var picker = document.getElementById('skill-library-picker');
    var select = document.getElementById('skill-library-select');
    document.getElementById('skill-add-form').style.display = 'none';
    document.getElementById('skill-edit-form').style.display = 'none';
    picker.style.display = 'block';
    select.innerHTML = '<option value="">' + escHtml(_tr('loading')) + '</option>';
    try {
        var res = await fetch('/api/skills-library');
        var data = await res.json();
        var skills = Array.isArray(data) ? data : (data.skills || []);
        if (skills.length === 0) {
            select.innerHTML = '<option value="">' + escHtml(_tr('no_skills_in_library')) + '</option>';
            return;
        }
        skills.sort(function(a, b) { return (a.name || '').localeCompare(b.name || ''); });
        select.innerHTML = skills.map(function(s) {
            return '<option value="' + escHtml(s.name) + '">' + escHtml(s.name) + (s.description ? ' — ' + escHtml(s.description).substring(0, 50) : '') + '</option>';
        }).join('');
    } catch (e) {
        select.innerHTML = '<option value="">' + escHtml(_tr('failed_load_library')) + '</option>';
    }
}

function hideLibraryPicker() {
    document.getElementById('skill-library-picker').style.display = 'none';
}

async function applyLibrarySkill() {
    if (!_currentSkillAgent) return;
    var select = document.getElementById('skill-library-select');
    var skillName = select.value;
    if (!skillName) return;
    try {
        var res = await fetch('/api/skills-library/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill: skillName, agentId: _currentSkillAgent, overwrite: false })
        });
        var data = await res.json();
        if (data.ok) {
            if (typeof _acpShowToast === 'function') _acpShowToast('✅ Applied "' + skillName + '" to agent');
            hideLibraryPicker();
            loadAgentSkills(_currentSkillAgent);
        } else if (data.exists) {
        if (confirm(_tr('overwrite_skill_confirm', { name: skillName }))) {
                var res2 = await fetch('/api/skills-library/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ skill: skillName, agentId: _currentSkillAgent, overwrite: true })
                });
                var data2 = await res2.json();
                if (data2.ok) {
                    if (typeof _acpShowToast === 'function') _acpShowToast('✅ Overwrote "' + skillName + '" on agent');
                    hideLibraryPicker();
                    loadAgentSkills(_currentSkillAgent);
                }
            }
        } else {
            if (typeof _acpShowToast === 'function') _acpShowToast('❌ ' + (data.error || 'Failed to apply'));
        }
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast('❌ Error: ' + e.message);
    }
}

function saveNewSkill() {
    if (!_currentSkillAgent) return;
    var name = document.getElementById('skill-new-name').value.trim();
    var content = document.getElementById('skill-new-content').value;
    if (!name) { alert(_tr('skill_name_required')); return; }
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, content: content })
    }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { alert(_tr('error') + ': ' + data.error); return; }
        hideAddSkillForm();
        loadAgentSkills(_currentSkillAgent);
        _acpShowToast('✅ Skill "' + name + '" added');
    }).catch(function(e) { alert(_tr('error_saving_skill') + ': ' + e.message); });
}

function editSkill(skillName) {
    if (!_currentSkillAgent) return;
    _editingSkillName = skillName;
    document.getElementById('skill-add-form').style.display = 'none';
    document.getElementById('skill-edit-form').style.display = 'block';
    document.getElementById('skill-edit-title').textContent = _tr('editing_skill', { name: skillName });
    document.getElementById('skill-edit-content').value = 'Loading...';
    // Fetch skills list which includes content
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var skill = (data.skills || []).find(function(s) { return s.name === skillName; });
            document.getElementById('skill-edit-content').value = (skill && skill.content) || '# ' + skillName + '\n\n_No content yet._';
        })
        .catch(function(e) {
            document.getElementById('skill-edit-content').value = '# ' + skillName + '\n\n_Could not load content. Edit and save to create._';
        });
}

function hideEditSkillForm() {
    document.getElementById('skill-edit-form').style.display = 'none';
    _editingSkillName = null;
}

function saveEditedSkill() {
    if (!_currentSkillAgent || !_editingSkillName) return;
    var content = document.getElementById('skill-edit-content').value;
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: _editingSkillName, content: content })
    }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { alert(_tr('error') + ': ' + data.error); return; }
        hideEditSkillForm();
        loadAgentSkills(_currentSkillAgent);
        _acpShowToast('✅ Skill "' + _editingSkillName + '" updated');
    }).catch(function(e) { alert(_tr('error_saving_skill') + ': ' + e.message); });
}

function deleteSkill(skillName) {
    if (!_currentSkillAgent) return;
    if (!confirm(_tr('remove_agent_skill_confirm', { name: skillName }))) return;
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills/' + encodeURIComponent(skillName), {
        method: 'DELETE'
    }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { alert(_tr('error') + ': ' + data.error); return; }
        loadAgentSkills(_currentSkillAgent);
        _acpShowToast('🗑️ Skill "' + skillName + '" removed');
    }).catch(function(e) { alert(_tr('error_deleting_skill') + ': ' + e.message); });
}

// ─── MEETINGS DASHBOARD ──────────────────────────────────────────
var _mtgAgentMap = {};  // key → {name, emoji, role}
var _mtgAgents = [];
var _mtgCurrentTab = 'active';
var _mtgData = { active: [], history: [], requests: [], projects: [] };
var _mtgOpenCards = {};
var _mtgLiveEvents = {};
var _mtgLivePollTimer = null;
var _mtgHistorySearch = '';
var _mtgDecisionAutoContinuing = {};
var _mtgDetailMeetingId = '';

function openMeetingsDashboard() {
    ['meetingsModal', 'meetingDetailModal', 'meetingRequestDetailModal', 'newMeetingModal'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('modal-above-projects');
    });
    document.getElementById('meetingsModal').classList.remove('hidden');
    updateMeetingLabels();
    _mtgRefresh();
    _mtgEnsureLivePolling();
}

function closeMeetingsModal() {
    document.getElementById('meetingsModal').classList.add('hidden');
    toggleNewMeetingForm(false);
    closeMeetingRequestDetailModal();
    closeMeetingDetailModal();
    _mtgStopLivePolling();
}

function switchMtgTab(tab) {
    _mtgCurrentTab = tab;
    document.querySelectorAll('.mtg-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === tab);
    });
    _mtgRender();
}

function setMeetingHistorySearch(value) {
    _mtgHistorySearch = String(value || '').trim().toLowerCase();
    _mtgRender();
}

function _mtgMeetingTime(m) {
    if (!m) return 0;
    var candidates = [m.endedAt, m.updatedAt, m.createdAt, m.startedAt];
    for (var i = 0; i < candidates.length; i++) {
        var value = candidates[i];
        if (!value) continue;
        if (typeof value === 'number') return value > 1000000000000 ? value : value * 1000;
        var parsed = Date.parse(value);
        if (!isNaN(parsed)) return parsed;
    }
    return 0;
}

function _mtgSortMeetingsByTime(meetings) {
    return (meetings || []).slice().sort(function(a, b) {
        return _mtgMeetingTime(b) - _mtgMeetingTime(a);
    });
}

function _mtgMeetingCompleted(m) {
    if (!m) return false;
    var state = m.stage || m.executionStage || m.status || '';
    return state === 'completed' || state === 'cancelled';
}

function _mtgHistorySearchText(m) {
    var parts = [
        m && m.topic,
        m && m.purpose,
        m && m.summary,
        m && m.resolution,
        m && m.organizer,
        m && m.moderator,
        m && m.contextMode
    ];
    ((m && (m.participants || m.agents)) || []).forEach(function(p) { parts.push(p); });
    ((m && m.actionItems) || []).forEach(function(item) { parts.push(_mtgActionText(item)); });
    var responses = (m && m.responses) || {};
    Object.keys(responses).forEach(function(key) { parts.push(key, responses[key]); });
    if (m && m.result) {
        parts.push(m.result.summary, m.result.decision);
        (m.result.unresolvedQuestions || []).forEach(function(item) { parts.push(item); });
        (m.result.disagreements || []).forEach(function(item) { parts.push(item); });
        Object.keys(m.result.contributions || {}).forEach(function(key) { parts.push(key, m.result.contributions[key]); });
    }
    ((m && m.transcript) || []).forEach(function(turn) {
        parts.push(turn.speaker, turn.text, turn.rawText);
    });
    return parts.filter(Boolean).join(' ').toLowerCase();
}

function _mtgFilterMeetingHistory(meetings) {
    var sorted = _mtgSortMeetingsByTime(meetings);
    if (!_mtgHistorySearch) return sorted;
    return sorted.filter(function(m) {
        return _mtgHistorySearchText(m).indexOf(_mtgHistorySearch) >= 0;
    });
}

function _mtgHistorySnippet(m) {
    var text = m.summary || m.resolution || (m.result && (m.result.summary || m.result.decision)) || m.purpose || '';
    return String(text || '').trim().slice(0, 180);
}

function _mtgRequestProcessed(req) {
    var status = req && req.status;
    if (status === 'confirmed' || status === 'rejected') return true;
    var review = (req && req.review) || {};
    var conversion = (req && req.conversion) || {};
    return !!(review.confirmedAt || review.rejectedAt || conversion.meetingId);
}

function _mtgRequestTime(req) {
    var raw = (req && (req.updatedAt || req.createdAt)) || '';
    var ms = Date.parse(raw);
    return Number.isFinite(ms) ? ms : 0;
}

function _mtgSortRequestsByStatusThenTime(requests) {
    return (requests || []).slice().sort(function(a, b) {
        var statusDelta = Number(_mtgRequestProcessed(a)) - Number(_mtgRequestProcessed(b));
        if (statusDelta) return statusDelta;
        return _mtgRequestTime(b) - _mtgRequestTime(a);
    });
}

async function _mtgRefresh() {
    try {
        var [activeRes, histRes, requestsRes, agentsRes, projectsRes] = await Promise.all([
            fetch('/api/meetings/active').then(function(r) { return r.json(); }),
            fetch('/api/meetings/history').then(function(r) { return r.json(); }),
            fetch('/api/meetings/requests').then(function(r) { return r.json(); }),
            fetch('/agents-list').then(function(r) { return r.json(); }),
            fetch('/api/projects').then(function(r) { return r.json(); }).catch(function() { return { projects: [] }; })
        ]);
        _mtgData.active = activeRes.meetings || [];
        _mtgData.history = _mtgSortMeetingsByTime(histRes.history || []);
        _mtgData.requests = _mtgSortRequestsByStatusThenTime(requestsRes.requests || []);
        _mtgData.projects = projectsRes.projects || [];
        _mtgSeedLiveMeetings(_mtgData.active);
        (_mtgData.active || []).forEach(_mtgMaybeAutoContinueDecisionMeeting);
        _mtgAgentMap = {};
        var agentsList = agentsRes.agents || agentsRes || [];
        _mtgAgents = Array.isArray(agentsList) ? agentsList : [];
        if (Array.isArray(agentsList)) {
            agentsList.forEach(function(a) {
                _mtgAgentMap[a.key || a.agentId || a.id] = {
                    name: a.name || a.key || 'Unknown',
                    emoji: a.emoji || '🤖',
                    role: a.role || ''
                };
            });
        }
        _mtgRender();
        _updateSidebarMeetings();
    } catch (e) {
        console.warn('[meetings] refresh error:', e);
    }
}

async function openMeetingReference(ref) {
    ref = ref || {};
    var requestId = String(ref.requestId || '').trim();
    var meetingId = String(ref.meetingId || '').trim();
    updateMeetingLabels();
    _mtgEnsureLivePolling();
    ['meetingsModal', 'meetingDetailModal', 'meetingRequestDetailModal'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('modal-above-projects');
    });
    await _mtgRefresh();

    var request = requestId ? _mtgFindRequest(requestId) : null;
    if (requestId && !request) request = await _mtgFetchRequestDetail(requestId);
    if (request && !meetingId) meetingId = _mtgMeetingIdFromRequest(request);

    var meeting = meetingId ? _mtgFindMeeting(meetingId) : null;
    if (!meeting && requestId) {
        meeting = _mtgFindMeetingByRequestId(requestId);
        if (meeting && meeting.id) meetingId = meeting.id;
    }
    if (meeting) {
        switchMtgTab(meeting && meeting.status === 'active' ? 'active' : 'completed');
        openMeetingDetailModal(meetingId);
        return;
    }

    if (meetingId) {
        switchMtgTab('completed');
        openMeetingDetailModal(meetingId);
        return;
    }

    if (requestId) {
        var modal = document.getElementById('meetingsModal');
        if (modal) modal.classList.remove('hidden');
        switchMtgTab('requests');
        if (!request) request = await _mtgFetchRequestDetail(requestId);
        if (request) {
            openMeetingRequestDetailModal(requestId);
        } else if (meetingId) {
            switchMtgTab('completed');
        }
    }
}

function _mtgProjectName(projectId) {
    if (!projectId) return '';
    var p = (_mtgData.projects || []).find(function(item) { return item.id === projectId; });
    return (p && p.title) || projectId;
}

function _mtgProjectMetaLabel(m) {
    var name = '';
    if (m && m.projectId) name = m.projectTitle || _mtgProjectName(m.projectId);
    if (!name && m && m.source && m.source.projectId) name = m.source.projectTitle || _mtgProjectName(m.source.projectId);
    if (!name) name = _mtgT('meeting_project_none', 'No project');
    return '📁 ' + _escMtg(_mtgT('meeting_project', 'Project')) + ': ' + _escMtg(name);
}

function _mtgProjectSelectHtml(id, selectedProjectId, allowEmpty) {
    var projects = _mtgData.projects || [];
    var html = '<select id="' + _escMtg(id) + '" class="skl-input">';
    if (allowEmpty !== false) html += '<option value="">' + _escMtg(_mtgT('meeting_project_none', 'No project')) + '</option>';
    projects.forEach(function(p) {
        html += '<option value="' + _escMtg(p.id) + '"' + (p.id === selectedProjectId ? ' selected' : '') + '>' + _escMtg(p.title || p.id) + '</option>';
    });
    html += '</select>';
    return html;
}

function _mtgRender() {
    var container = document.getElementById('mtg-cards');
    var searchTools = document.getElementById('mtg-history-tools');
    if (searchTools) searchTools.classList.toggle('hidden', _mtgCurrentTab !== 'completed');
    if (_mtgCurrentTab === 'requests') {
        _mtgRenderRequests(container);
        return;
    }
    var meetings = [];
    if (_mtgCurrentTab === 'active') meetings = _mtgData.active;
    else if (_mtgCurrentTab === 'completed') meetings = _mtgFilterMeetingHistory(_mtgData.history);
    else meetings = _mtgData.active.concat(_mtgData.history);
    meetings = meetings.map(_mtgMergeLiveMeeting);

    if (!meetings.length) {
        container.innerHTML = '<div class="mtg-empty">' + _escMtg(_tr('meeting_empty', { status: _tr(_mtgCurrentTab === 'completed' ? 'completed' : 'active') })) + '</div>';
        return;
    }

    container.innerHTML = meetings.map(function(m) {
        var isActive = m.status === 'active';
        var participants = m.participants || m.agents || [];

        var isHistory = !isActive;

        // Header (clickable to open detail modal)
        var html = '<div class="mtg-card">';
        html += '<div class="mtg-card-header" onclick="openMeetingDetailModal(\'' + _escMtg(m.id) + '\')">';
        html += '<div><div class="mtg-card-title">' + _escMtg(m.topic || _tr('untitled_meeting')) + '</div>';
        if (m.purpose && m.purpose !== m.topic) {
            html += '<div class="mtg-card-purpose">' + _escMtg(m.purpose) + '</div>';
        }
        html += '</div>';
        html += '<div class="mtg-card-badges">';
        if (isActive && m.executableMeeting && (m.executionStage || '') === 'awaiting_user_decision') {
            var isNoConsensus = m.arbitration && m.arbitration.reason === 'no_consensus';
            if (isNoConsensus) {
                html += '<span id="mtg-decision-countdown-' + _escMtg(m.id) + '" class="mtg-badge mtg-badge-countdown" data-meeting-id="' + _escMtg(m.id) + '" data-auto-continue="0">⏳ ' + _escMtg(_mtgT('meeting_arbitration_waiting', 'Waiting for arbitration')) + '</span>';
            } else {
                html += '<span id="mtg-decision-countdown-' + _escMtg(m.id) + '" class="mtg-badge mtg-badge-countdown mtg-decision-countdown" data-meeting-id="' + _escMtg(m.id) + '" data-deadline="' + _escMtg(m.decisionDeadlineAt || '') + '" data-auto-continue="1">' + _escMtg(_mtgDecisionCountdownText(m)) + '</span>';
            }
        }
        var statusInfo = _mtgMeetingStatusInfo(m);
        html += '<span class="mtg-badge ' + _escMtg(statusInfo.className) + '">' + _escMtg(statusInfo.icon + ' ' + statusInfo.label) + '</span>';
        if (m.kind) html += '<span class="mtg-badge mtg-badge-kind">' + _escMtg(m.kind) + '</span>';
        if (m.executableMeeting) html += '<span class="mtg-badge mtg-badge-kind">' + _escMtg(_mtgT('meeting_executable', 'Executable')) + ' · ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || m.status || '')) + '</span>';
        html += '</div></div>';

        if (isActive) {
            html += '<div class="mtg-card-summary">';
            var activeOrgInfo = _mtgAgentMap[m.organizer] || { emoji: '🤖', name: m.organizer || 'Unknown' };
            var activeLeftMeta = [
                '👑 ' + activeOrgInfo.emoji + ' ' + _escMtg(activeOrgInfo.name),
                '🪪 ' + _escMtg(_mtgCreatedByLabel(m)),
                '👥 ' + _escMtg(_tr('participants_count', { count: participants.length }))
            ];
            var activeRightMeta = [];
            if (m.type) activeRightMeta.push('📋 ' + _escMtg(m.type));
            if (m.executableMeeting) {
                activeRightMeta.push('⚙️ ' + _escMtg(_mtgT('meeting_stage', 'Stage')) + ': ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || '')));
                activeRightMeta.push('🔁 ' + _escMtg(_mtgT('meeting_version', 'Version')) + ': ' + _escMtg(m.executionVersion || 0));
                activeRightMeta.push('🧭 ' + _escMtg(_mtgT('meeting_round', 'Round')) + ': ' + _escMtg((m.currentRound || 0) + '/' + (m.maxRounds || 0)));
                if (m.moderator) activeRightMeta.push('🎙️ ' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + ': ' + _escMtg(m.moderator));
                if (m.agenda && m.agenda !== m.topic) activeRightMeta.push('📝 ' + _escMtg(_mtgT('meeting_current_agenda', 'Current agenda')) + ': ' + _escMtg(m.agenda));
                if (m.contextMode) activeRightMeta.push('🧩 ' + _escMtg(_mtgT('meeting_context_mode', 'Context')) + ': ' + _escMtg(m.contextMode));
                if (m.currentSpeaker) activeRightMeta.push('🗣️ ' + _escMtg(_mtgT('meeting_current_speaker', 'Speaker')) + ': ' + _escMtg(m.currentSpeaker));
                if (m.resolutionPolicy) activeRightMeta.push('⚖️ ' + _escMtg(_mtgResolutionPolicyLabel(m.resolutionPolicy)));
                var activePreparingTimeoutLabel = _mtgPreparingTimeoutLabel(m);
                if (activePreparingTimeoutLabel) activeRightMeta.push('⏱️ ' + _escMtg(activePreparingTimeoutLabel));
                if (m.urgency) activeRightMeta.push('🚦 ' + _escMtg(_mtgUrgencyLabel(m.urgency)));
            }
            activeRightMeta.push(_mtgProjectMetaLabel(m));
            var activeTs = _mtgMeetingTime(m);
            if (activeTs) activeRightMeta.push('🕐 ' + new Date(activeTs).toLocaleString());
            html += _mtgRenderMetaColumns(activeLeftMeta, activeRightMeta);
            var activeSnippet = _mtgHistorySnippet(m);
            if (activeSnippet) {
                html += '<div class="mtg-section-text mtg-history-snippet">' + _escMtg(activeSnippet) + '</div>';
            }
            html += '<div class="mtg-actions-bar">';
            html += '<button class="mtg-btn mtg-btn-end" onclick="event.stopPropagation(); openMeetingDetailModal(\'' + _escMtg(m.id) + '\')">' + _escMtg(_mtgT('meeting_view_detail', 'View detail')) + '</button>';
            html += '</div>';
            html += '</div></div>';
            return html;
        }

        // Body (collapsible)
        html += '<div class="mtg-card-body open" id="mtg-body-' + _escMtg(m.id) + '">';

        // Meta
        var orgInfo = _mtgAgentMap[m.organizer] || { emoji: '🤖', name: m.organizer || 'Unknown' };
        var leftMeta = [
            '👑 ' + orgInfo.emoji + ' ' + _escMtg(orgInfo.name),
            '🪪 ' + _escMtg(_mtgCreatedByLabel(m)),
            '👥 ' + _escMtg(_tr('participants_count', { count: participants.length }))
        ];
        var rightMeta = [];
        if (m.type) rightMeta.push('📋 ' + _escMtg(m.type));
        if (m.executableMeeting) {
            rightMeta.push('⚙️ ' + _escMtg(_mtgT('meeting_stage', 'Stage')) + ': ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || '')));
            rightMeta.push('🔁 ' + _escMtg(_mtgT('meeting_version', 'Version')) + ': ' + _escMtg(m.executionVersion || 0));
            rightMeta.push('🧭 ' + _escMtg(_mtgT('meeting_round', 'Round')) + ': ' + _escMtg((m.currentRound || 0) + '/' + (m.maxRounds || 0)));
            if (m.moderator) rightMeta.push('🎙️ ' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + ': ' + _escMtg(m.moderator));
            if (m.agenda && m.agenda !== m.topic) rightMeta.push('📝 ' + _escMtg(_mtgT('meeting_current_agenda', 'Current agenda')) + ': ' + _escMtg(m.agenda));
            if (m.contextMode) rightMeta.push('🧩 ' + _escMtg(_mtgT('meeting_context_mode', 'Context')) + ': ' + _escMtg(m.contextMode));
            if (m.resolutionPolicy) rightMeta.push('⚖️ ' + _escMtg(_mtgT('meeting_resolution_policy', 'Resolution policy')) + ': ' + _escMtg(_mtgResolutionPolicyLabel(m.resolutionPolicy)));
            var cardPreparingTimeoutLabel = _mtgPreparingTimeoutLabel(m);
            if (cardPreparingTimeoutLabel) rightMeta.push('⏱️ ' + _escMtg(cardPreparingTimeoutLabel));
            if (m.currentSpeaker) rightMeta.push('🗣️ ' + _escMtg(_mtgT('meeting_current_speaker', 'Speaker')) + ': ' + _escMtg(m.currentSpeaker));
            if (m.urgency) rightMeta.push('🚦 ' + _escMtg(_mtgUrgencyLabel(m.urgency)));
        }
        if (m.endedAt) {
            var d = new Date(m.endedAt * 1000);
            rightMeta.push('🕐 ' + d.toLocaleString(typeof i18n !== 'undefined' && i18n.getLanguage() === 'zh' ? 'zh-CN' : 'en-US'));
        }
        rightMeta.push(_mtgProjectMetaLabel(m));
        html += _mtgRenderMetaColumns(leftMeta, rightMeta);

        if (isHistory) {
            var snippet = _mtgHistorySnippet(m);
            if (snippet) {
                html += '<div class="mtg-section-text mtg-history-snippet">' + _escMtg(snippet) + '</div>';
            }
            html += '<div class="mtg-actions-bar">';
            html += '<button class="mtg-btn mtg-btn-end" onclick="event.stopPropagation(); openMeetingDetailModal(\'' + _escMtg(m.id) + '\')">' + _escMtg(_mtgT('meeting_view_detail', 'View detail')) + '</button>';
            html += '<button class="mtg-btn mtg-btn-delete" onclick="event.stopPropagation(); deleteMeetingHistory(\'' + _escMtg(m.id) + '\')">' + _escMtg(_tr('delete')) + '</button>';
            html += '</div>';
            html += '</div>';  // close mtg-card-body
            html += '</div>';  // close mtg-card
            return html;
        }

        // Participants
        html += '<div class="mtg-participants">';
        participants.forEach(function(pKey) {
            var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
            html += '<div class="mtg-participant">';
            html += '<span class="mtg-participant-emoji">' + info.emoji + '</span>';
            html += '<div class="mtg-participant-info">';
            html += '<div class="mtg-participant-name">' + _escMtg(info.name) + '</div>';
            if (info.role) html += '<div class="mtg-participant-role">' + _escMtg(info.role) + '</div>';
            if (!isActive && m.actionItems && m.actionItems.length) {
                var agentActions = m.actionItems.filter(function(item) {
                    var text = _mtgActionText(item).toLowerCase();
                    return text.indexOf(info.name.toLowerCase()) >= 0 ||
                           text.indexOf(pKey.toLowerCase()) >= 0;
                });
                if (agentActions.length) {
                    html += '<div class="mtg-participant-actions">→ ' + agentActions.map(function(item) { return _escMtg(_mtgActionText(item)); }).join('<br>→ ') + '</div>';
                }
            }
            html += '</div></div>';
        });
        html += '</div>';

        if (isActive && m.executableMeeting) {
            if ((m.executionStage || '') === 'awaiting_user_decision') {
                html += _mtgRenderDecisionWindowControls(m);
            }
            if (m.moderatorFailure && m.moderatorFailure.reason === 'moderator_failed') {
                html += _mtgRenderModeratorTakeoverControls(m);
            }
            html += _mtgRenderInterventionForm(m);
        }

        if (m.executableMeeting && ((Array.isArray(m.transcript) && m.transcript.length) || (Array.isArray(m.pendingCalls) && m.pendingCalls.length))) {
            html += _mtgRenderTranscript(m);
        }

        // Per-agent responses
        var responses = m.responses || {};
        if (!isActive && Object.keys(responses).length > 0) {
            html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('agent_responses')) + '</div>';
            html += '<div class="mtg-responses">';
            participants.forEach(function(pKey) {
                var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
                var resp = responses[pKey] || '';
                html += '<div class="mtg-response">';
                html += '<div class="mtg-response-header">';
                html += '<span class="mtg-response-emoji">' + info.emoji + '</span>';
                html += '<span class="mtg-response-name">' + _escMtg(info.name) + '</span>';
                if (info.role) html += '<span class="mtg-response-role">' + _escMtg(info.role) + '</span>';
                html += '</div>';
                if (resp) {
                    var respId = 'mtg-resp-' + _escMtg(m.id) + '-' + _escMtg(pKey);
                    html += '<div class="mtg-response-text" id="' + respId + '">' + _escMtg(resp) + '</div>';
                    html += '<span class="mtg-response-expand" onclick="toggleMtgResponse(\'' + respId + '\', this)">' + _escMtg(_tr('expand')) + '</span>';
                } else {
                    html += '<div class="mtg-response-none">' + _escMtg(_tr('no_response_recorded')) + '</div>';
                }
                html += '</div>';
            });
            html += '</div></div>';
        }

        // Completed details
        if (!isActive) {
            if (m.summary) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('summary')) + '</div>';
                html += '<div class="mtg-section-text">' + _escMtg(m.summary) + '</div></div>';
            }
            if (m.resolution) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('resolution')) + '</div>';
                html += '<div class="mtg-section-text">' + _escMtg(m.resolution) + '</div></div>';
            }
            if (m.actionItems && m.actionItems.length) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('action_items')) + '</div>';
                html += '<div class="mtg-section-text">' + m.actionItems.map(function(a) { return '• ' + _escMtg(_mtgActionText(a)); }).join('\n') + '</div></div>';
            }
            if (m.executableMeeting && m.result && m.result.contributions) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_contributions', 'Contributions')) + '</div>';
                Object.keys(m.result.contributions).forEach(function(agentId) {
                    var info = _mtgAgentMap[agentId] || { emoji: '🤖', name: agentId };
                    html += '<div class="mtg-response"><div class="mtg-response-header"><span class="mtg-response-emoji">' + info.emoji + '</span><span class="mtg-response-name">' + _escMtg(info.name) + '</span></div>';
                    html += '<div class="mtg-response-text">' + _mtgRenderContributionText(m.result.contributions[agentId] || '') + '</div></div>';
                });
                html += '</div>';
            }
            if (m.endedBy) {
                var endInfo = _mtgAgentMap[m.endedBy] || { emoji: '🤖', name: m.endedBy };
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('ended_by')) + '</div>';
                html += '<div class="mtg-section-text">' + endInfo.emoji + ' ' + _escMtg(endInfo.name) + '</div></div>';
            }
        }

        // Actions bar
        html += '<div class="mtg-actions-bar">';
        if (m.executableMeeting) {
            var stage = m.executionStage || '';
            if (stage === 'preparing') {
                html += '<button id="mtg-start-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="startExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_start_existing', 'Start meeting')) + '</button>';
            } else if (stage === 'paused') {
                html += '<button id="mtg-resume-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="resumeExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_resume', 'Resume')) + '</button>';
            } else {
                html += '<button id="mtg-pause-' + _escMtg(m.id) + '" class="mtg-btn" onclick="pauseExecutableMeeting(\'' + _escMtg(m.id) + '\')">⏸ ' + _escMtg(_mtgT('meeting_pause', 'Pause')) + '</button>';
                html += '<button id="mtg-ai-end-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="endExecutableMeetingWithAI(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_mtgT('meeting_ai_end', 'Ask moderator to end')) + '</button>';
            }
            html += '<button id="mtg-cancel-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-delete" onclick="cancelExecutableMeeting(\'' + _escMtg(m.id) + '\')">✕ ' + _escMtg(_mtgT('meeting_cancel', 'Cancel')) + '</button>';
        } else {
            html += '<button class="mtg-btn mtg-btn-end" onclick="openEndMeetingForm(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_tr('end_meeting')) + '</button>';
        }
        html += '</div>';

        html += '</div>';  // close mtg-card-body
        html += '</div>';  // close mtg-card
        return html;
    }).join('');
}

function _mtgRequestStatusLabel(status) {
    if (status === 'confirmed') return _mtgT('meeting_request_status_confirmed', 'Confirmed');
    if (status === 'rejected') return _mtgT('meeting_request_status_rejected', 'Rejected');
    return _mtgT('meeting_request_status_pending', 'Pending');
}

function _mtgRequestStatusClass(status) {
    if (status === 'confirmed') return 'status-confirmed';
    if (status === 'rejected') return 'status-rejected';
    return 'status-pending';
}

function _mtgMeetingStageLabel(stage) {
    var key = String(stage || '').trim();
    var map = {
        active: 'active',
        completed: 'meeting_status_completed',
        cancelled: 'meeting_status_cancelled',
        failed: 'meeting_status_failed',
        preparing: 'meeting_stage_preparing',
        conflict: 'meeting_stage_conflict',
        active_opening: 'meeting_stage_active_opening',
        active_discussion: 'meeting_stage_active_discussion',
        awaiting_user_decision: 'meeting_stage_awaiting_user_decision',
        paused: 'meeting_stage_paused',
        summarizing: 'meeting_stage_summarizing'
    };
    return map[key] ? _mtgT(map[key], key) : key;
}

function _mtgNormalizePreparingTimeoutSec(value) {
    var seconds = parseInt(value, 10);
    if (!isFinite(seconds) || seconds < 30) seconds = 300;
    if (seconds > 86400) seconds = 86400;
    return seconds;
}

function _mtgPreparingRemainingSec(m) {
    if (!m || (m.executionStage || '') !== 'preparing') return null;
    var started = Date.parse(m.preparingStartedAt || m.createdAt || '');
    if (!started) return null;
    var timeout = _mtgNormalizePreparingTimeoutSec(m.preparingTimeoutSec || 300);
    return Math.max(0, Math.ceil((started + timeout * 1000 - Date.now()) / 1000));
}

function _mtgPreparingTimeoutLabel(m) {
    if (!m || !m.executableMeeting) return '';
    if (m.cancelReason === 'preparing_timeout') {
        return _mtgT('meeting_preparing_timeout_released', 'Preparing timeout released');
    }
    var remaining = _mtgPreparingRemainingSec(m);
    if (remaining === null) return '';
    return _mtgT('meeting_preparing_timeout_remaining', 'Auto-release in {seconds}s').replace('{seconds}', String(remaining));
}

function _mtgMeetingStatusInfo(m) {
    var stage = String((m && (m.executionStage || m.status)) || '').trim();
    if ((m && m.status) === 'active' && stage !== 'cancelled' && stage !== 'failed' && stage !== 'completed') {
        return { icon: '●', label: _tr('active'), className: 'mtg-badge-active' };
    }
    if (stage === 'cancelled') {
        var cancelledLabel = (m && m.cancelReason === 'preparing_timeout')
            ? _mtgT('meeting_preparing_timeout_released', 'Preparing timeout released')
            : _mtgT('meeting_status_cancelled', 'Cancelled');
        return { icon: '✕', label: cancelledLabel, className: 'mtg-badge-kind' };
    }
    if (stage === 'failed') {
        return { icon: '!', label: _mtgT('meeting_status_failed', 'Failed'), className: 'mtg-badge-countdown' };
    }
    return { icon: '✓', label: _mtgT('meeting_status_completed', _tr('completed')), className: 'mtg-badge-completed' };
}

function _mtgRequestProposal(req) {
    return (req && req.originalProposal) || {};
}

function _mtgRequestSource(req) {
    return (req && req.source) || {};
}

function _mtgRequestAgentName(agentId) {
    var info = _mtgAgentMap[agentId] || {};
    return ((info.emoji || '🤖') + ' ' + (info.name || agentId || 'AI')).trim();
}

function _mtgUrgencyLabel(value) {
    var score = Math.max(1, Math.min(5, Number(value || 3)));
    return _mtgT('meeting_urgency', 'Urgency') + ': ' + score + '/5';
}

function _mtgCreatedByLabel(m) {
    var source = (m && m.source) || {};
    var agentId = m.createdByAgentId || source.requestingAgentId || '';
    if ((m.createdByType || '') === 'agent' || source.meetingRequestId || agentId) {
        return _mtgT('meeting_created_by_agent', 'Agent started') + ': ' + _mtgRequestAgentName(agentId || m.organizer);
    }
    return _mtgT('meeting_created_by_user', 'User started');
}

function _mtgSourceKindLabel(kind) {
    if (kind === 'project') return _mtgT('meeting_context_source_project', 'Project');
    if (kind === 'task') return _mtgT('meeting_context_source_task', 'Task');
    if (kind === 'related_task') return _mtgT('meeting_context_source_related_task', 'Related task');
    if (kind === 'meeting') return _mtgT('meeting_context_source_meeting', 'Meeting');
    if (kind === 'supplemental') return _mtgT('meeting_context_source_supplemental', 'Supplemental');
    return kind || '';
}

function _mtgDisplayText(text) {
    var raw = String(text || '');
    var normalized = raw.trim().toLowerCase();
    var map = {
        'user requested ai meeting': _mtgT('meeting_fixture_user_requested_ai_meeting', 'User requested AI meeting'),
        'invite gg to urgency 3 ai meeting': _mtgT('meeting_fixture_invite_gg_urgency_3', 'Invite gg to urgency 3 AI meeting'),
        'user requested codex to start an urgency 3 ai meeting and invite gg. this task exists as the required project-task source for the meeting request.': _mtgT('meeting_fixture_invite_gg_urgency_3_summary', 'User requested Codex to start an urgency 3 AI meeting and invite gg. This task exists as the required project-task source for the meeting request.')
    };
    return map[normalized] || raw;
}

function _mtgRenderMetaColumns(itemsLeft, itemsRight) {
    var left = (itemsLeft || []).filter(Boolean);
    var right = (itemsRight || []).filter(Boolean);
    var row1 = left.slice();
    var row2 = [];
    var row3 = [];
    right.forEach(function(item) {
        var text = String(item || '');
        if (text.indexOf('📋') === 0) row1.push(item);
        else if (text.indexOf('⚙️') === 0 || text.indexOf('🔁') === 0 || text.indexOf('🧭') === 0 || text.indexOf('🎙️') === 0 || text.indexOf('🗣️') === 0 || text.indexOf('📝') === 0) row2.push(item);
        else row3.push(item);
    });
    var rows = [row1, row2, row3].filter(function(row) { return row.length; });
    return '<div class="mtg-meta mtg-meta-grid">' + rows.map(function(items) {
        return '<div class="mtg-meta-row">' + items.map(function(item) {
            return '<div class="mtg-meta-item">' + item + '</div>';
        }).join('') + '</div>';
    }).join('') + '</div>';
}

function _mtgRenderRequestContext(req) {
    var candidates = req.contextCandidates || [];
    if (!candidates.length) return '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_request_no_context', 'No context candidates.')) + '</div>';
    return '<div class="mtg-request-context-list">' + candidates.map(function(c) {
        var title = c.title || c.sourceKind || 'Context';
        var summary = c.summary || '';
        return '<label class="mtg-request-context-item">' +
            '<input type="checkbox" class="mtg-request-context" data-request-id="' + _escMtg(req.id) + '" value="' + _escMtg(c.id || '') + '">' +
            '<span><strong>' + _escMtg(_mtgDisplayText(title)) + '</strong><small>' + _escMtg(_mtgSourceKindLabel(c.sourceKind || '')) + '</small><em>' + _escMtg(_mtgDisplayText(summary)) + '</em></span>' +
            '</label>';
    }).join('') + '</div>';
}

function _mtgRenderRequestReview(req) {
    if (req.status !== 'pending') return '';
    var proposal = _mtgRequestProposal(req);
    var participants = proposal.suggestedParticipants || [];
    var participantOptions = _mtgParticipantSelectorHtml({
        selected: participants,
        participantClass: 'mtg-request-participant mtg-request-participant-' + req.id,
        branchClass: 'mtg-request-branch mtg-request-branch-' + req.id,
        participantAttrs: ' data-request-id="' + _escMtg(req.id) + '" onchange="_mtgUpdateRequestModeratorOptions(\'' + _escMtg(req.id) + '\')"',
        branchAttrs: ' data-request-id="' + _escMtg(req.id) + '" onchange="_mtgToggleRequestBranch(\'' + _escMtg(req.id) + '\', this)"'
    });
    return '<div class="mtg-request-review" id="mtg-request-review-' + _escMtg(req.id) + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_topic', 'Topic')) + '</label>' +
        '<input id="mtg-request-topic-' + _escMtg(req.id) + '" class="skl-input" type="text" value="' + _escMtg(proposal.topic || '') + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_purpose', 'Purpose')) + '</label>' +
        '<input id="mtg-request-purpose-' + _escMtg(req.id) + '" class="skl-input" type="text" value="' + _escMtg(proposal.purpose || proposal.goal || '') + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_type', 'Meeting type')) + '</label>' +
        '<select id="mtg-request-type-' + _escMtg(req.id) + '" class="skl-input"><option value="information"' + (proposal.meetingType === 'information' ? ' selected' : '') + '>' + _escMtg(_mtgT('meeting_type_information', 'Information gathering')) + '</option><option value="discussion"' + (proposal.meetingType !== 'information' && proposal.meetingType !== 'task' ? ' selected' : '') + '>' + _escMtg(_mtgT('meeting_type_discussion', 'Decision discussion')) + '</option><option value="task"' + (proposal.meetingType === 'task' ? ' selected' : '') + '>' + _escMtg(_mtgT('meeting_type_task', 'Task collaboration')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_project', 'Project')) + '</label>' +
        _mtgProjectSelectHtml('mtg-request-project-' + req.id, (req.source || {}).projectId || '', true) +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_participants', 'Participants')) + '</label>' +
        '<div>' + participantOptions + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + '</label>' +
        '<select id="mtg-request-moderator-' + _escMtg(req.id) + '" class="skl-input"></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_max_rounds', 'Max discussion rounds')) + '</label>' +
        '<input id="mtg-request-max-rounds-' + _escMtg(req.id) + '" class="skl-input" type="number" min="1" max="5" value="' + _escMtg(proposal.maxRounds || 2) + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_context_candidates', 'Context candidates')) + '</div>' +
        _mtgRenderRequestContext(req) +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_add_context', 'Additional context')) + '</label>' +
        '<textarea id="mtg-request-supplemental-' + _escMtg(req.id) + '" class="mtg-textarea" rows="3"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_request_reject_reason', 'Reject reason')) + '</label>' +
        '<input id="mtg-request-reject-reason-' + _escMtg(req.id) + '" class="skl-input" type="text">' +
        '<div id="mtg-request-error-' + _escMtg(req.id) + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-actions-bar">' +
        '<button id="mtg-request-confirm-' + _escMtg(req.id) + '" class="mtg-btn mtg-btn-end" onclick="_mtgConfirmRequest(\'' + _escMtg(req.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_request_confirm_start', 'Confirm and start')) + '</button>' +
        '<button id="mtg-request-reject-' + _escMtg(req.id) + '" class="mtg-btn mtg-btn-delete" onclick="_mtgRejectRequest(\'' + _escMtg(req.id) + '\')">✕ ' + _escMtg(_mtgT('meeting_request_reject', 'Reject')) + '</button>' +
        '</div>' +
        '</div>';
}

function _mtgRenderRequests(container) {
    if (!container) return;
    var requests = _mtgData.requests || [];
    if (!requests.length) {
        container.innerHTML = '<div class="mtg-empty">' + _escMtg(_mtgT('meeting_request_empty', 'No AI meeting requests')) + '</div>';
        return;
    }
    container.innerHTML = requests.map(function(req) {
        var proposal = _mtgRequestProposal(req);
        var source = _mtgRequestSource(req);
        var status = req.status || 'pending';
        var urgency = req.urgency || proposal.urgency || 3;
        var statusClass = _mtgRequestStatusClass(status);
        var html = '<div class="mtg-card mtg-request-card ' + statusClass + '" data-request-id="' + _escMtg(req.id) + '">';
        html += '<div class="mtg-card-header" onclick="openMeetingRequestDetailModal(\'' + _escMtg(req.id) + '\')"><div><div class="mtg-card-title">' + _escMtg(proposal.topic || proposal.goal || _mtgT('meeting_request_title', 'AI meeting request')) + '</div>';
        html += '<div class="mtg-card-purpose">' + _escMtg(source.projectTitle || '') + (source.taskTitle ? ' · ' + _escMtg(source.taskTitle) : '') + '</div></div>';
        html += '<div class="mtg-card-badges"><span class="mtg-badge mtg-request-status ' + statusClass + '">' + _escMtg(_mtgRequestStatusLabel(status)) + '</span></div></div>';
        html += '<div class="mtg-card-summary mtg-request-summary">';
        html += _mtgRenderMetaColumns([
            '🤖 ' + _escMtg(_mtgT('meeting_requesting_agent', 'Requesting agent')) + ': ' + _escMtg(_mtgRequestAgentName(req.requestingAgentId)),
            '📌 ' + _escMtg(source.taskTitle || '')
        ], [
            '🚦 ' + _escMtg(_mtgUrgencyLabel(urgency)),
            urgency >= 4 ? '⚡ ' + _escMtg(_mtgT('meeting_auto_start_high_urgency', 'High urgency auto-starts')) : ''
        ]);
        html += '<div class="mtg-section-text mtg-request-preview">' + _escMtg(proposal.goal || proposal.cannotCompleteAloneReason || '') + '</div>';
        if (status === 'confirmed' && req.conversion && req.conversion.meetingId) {
            html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_request_created_meeting', 'Created meeting')) + ': ' + _escMtg(req.conversion.meetingId) + '</div>';
        }
        if (req.review && req.review.autoConfirmed) {
            html += '<div class="mtg-section-text">' + _escMtg(req.review.autoConfirmLabel || req.review.autoConfirmReason || _mtgT('meeting_request_auto_confirmed', 'Auto-approved')) + '</div>';
        }
        if (status === 'rejected' && req.review && req.review.rejectionReason) {
            html += '<div class="mtg-inline-error" style="display:block">' + _escMtg(req.review.rejectionReason) + '</div>';
        }
        html += '<div class="mtg-actions-bar"><button class="mtg-btn" onclick="openMeetingRequestDetailModal(\'' + _escMtg(req.id) + '\')">' + _escMtg(_mtgT('meeting_request_view_detail', 'View details')) + '</button></div>';
        html += '</div></div>';
        return html;
    }).join('');
}

function _mtgFindRequest(requestId) {
    return (_mtgData.requests || []).find(function(req) { return req && req.id === requestId; });
}

function _mtgRenderRequestDetail(req) {
    var proposal = _mtgRequestProposal(req);
    var source = _mtgRequestSource(req);
    var status = req.status || 'pending';
    var urgency = req.urgency || proposal.urgency || 3;
    var html = '<div class="mtg-request-detail" data-request-id="' + _escMtg(req.id) + '">';
    html += _mtgRenderMetaColumns([
        '🤖 ' + _escMtg(_mtgT('meeting_requesting_agent', 'Requesting agent')) + ': ' + _escMtg(_mtgRequestAgentName(req.requestingAgentId)),
        '📋 ' + _escMtg(source.projectTitle || ''),
        '📌 ' + _escMtg(source.taskTitle || '')
    ], [
        '🚦 ' + _escMtg(_mtgUrgencyLabel(urgency)),
        '<span class="mtg-badge mtg-request-status ' + _mtgRequestStatusClass(status) + '">' + _escMtg(_mtgRequestStatusLabel(status)) + '</span>'
    ]);
    html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_goal', 'Goal')) + '</div><div class="mtg-section-text">' + _escMtg(proposal.goal || '') + '</div></div>';
    html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_expected', 'Expected outcome')) + '</div><div class="mtg-section-text">' + _escMtg(proposal.expectedOutcome || '') + '</div></div>';
    html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_reason', 'Why meeting is needed')) + '</div><div class="mtg-section-text">' + _escMtg(proposal.cannotCompleteAloneReason || '') + '</div></div>';
    if (status === 'confirmed' && req.conversion && req.conversion.meetingId) {
        html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_request_created_meeting', 'Created meeting')) + ': ' + _escMtg(req.conversion.meetingId) + '</div>';
    }
    if (req.review && req.review.autoConfirmed) {
        html += '<div class="mtg-section-text">' + _escMtg(req.review.autoConfirmLabel || req.review.autoConfirmReason || _mtgT('meeting_request_auto_confirmed', 'Auto-approved')) + '</div>';
    }
    if (status === 'rejected' && req.review && req.review.rejectionReason) {
        html += '<div class="mtg-inline-error" style="display:block">' + _escMtg(req.review.rejectionReason) + '</div>';
    }
    html += _mtgRenderRequestReview(req);
    html += '</div>';
    return html;
}

function openMeetingRequestDetailModal(requestId) {
    var req = _mtgFindRequest(requestId);
    var modal = document.getElementById('meetingRequestDetailModal');
    var body = document.getElementById('meeting-request-detail-body');
    var title = document.getElementById('meeting-request-detail-title');
    if (!req || !modal || !body) return;
    var proposal = _mtgRequestProposal(req);
    if (title) title.textContent = proposal.topic || proposal.goal || _mtgT('meeting_request_title', 'AI meeting request');
    body.innerHTML = _mtgRenderRequestDetail(req);
    modal.classList.remove('hidden');
    setTimeout(function() { _mtgUpdateRequestModeratorOptions(req.id); }, 0);
}

function closeMeetingRequestDetailModal() {
    var modal = document.getElementById('meetingRequestDetailModal');
    var body = document.getElementById('meeting-request-detail-body');
    if (modal) modal.classList.add('hidden');
    if (body) body.innerHTML = '';
}

function _mtgToggleRequestBranch(requestId, branchEl) {
    var branchId = branchEl.getAttribute('data-branch-id') || '';
    _mtgApplyBranchSelection('[data-request-id="' + requestId + '"].mtg-request-branch', '[data-request-id="' + requestId + '"].mtg-request-participant', branchId, branchEl.checked);
    _mtgUpdateRequestModeratorOptions(requestId);
}

function _mtgUpdateRequestModeratorOptions(requestId) {
    var req = (_mtgData.requests || []).find(function(item) { return item.id === requestId; }) || {};
    var proposal = _mtgRequestProposal(req);
    _mtgSyncBranchSelectionState('[data-request-id="' + requestId + '"].mtg-request-branch', '[data-request-id="' + requestId + '"].mtg-request-participant');
    _mtgUpdateModeratorOptions('mtg-request-moderator-' + requestId, '[data-request-id="' + requestId + '"].mtg-request-participant', proposal.suggestedModerator);
}

function _mtgRequestError(requestId, msg) {
    var err = document.getElementById('mtg-request-error-' + requestId);
    if (err) {
        err.textContent = msg || '';
        err.style.display = msg ? 'block' : 'none';
    }
}

async function _mtgConfirmRequest(requestId) {
    _mtgRequestError(requestId, '');
    var participants = _mtgFilterAssignableParticipants(Array.prototype.slice.call(document.querySelectorAll('[data-request-id="' + requestId + '"].mtg-request-participant:checked')).map(function(el) { return el.value; }));
    var selectedContextIds = Array.prototype.slice.call(document.querySelectorAll('[data-request-id="' + requestId + '"].mtg-request-context:checked')).map(function(el) { return el.value; });
    var body = {
        topic: ((document.getElementById('mtg-request-topic-' + requestId) || {}).value || '').trim(),
        purpose: ((document.getElementById('mtg-request-purpose-' + requestId) || {}).value || '').trim(),
        meetingType: (document.getElementById('mtg-request-type-' + requestId) || {}).value || 'discussion',
        participants: participants,
        moderator: (document.getElementById('mtg-request-moderator-' + requestId) || {}).value || '',
        projectId: (document.getElementById('mtg-request-project-' + requestId) || {}).value || '',
        maxRounds: Number((document.getElementById('mtg-request-max-rounds-' + requestId) || {}).value || 2),
        selectedContextIds: selectedContextIds,
        supplementalContext: ((document.getElementById('mtg-request-supplemental-' + requestId) || {}).value || '').trim(),
        idempotencyKey: 'ui-confirm-' + requestId
    };
    if (participants.length < 2) return _mtgRequestError(requestId, _mtgT('meeting_error_participants_required', 'Select at least two participants.'));
    try {
        var res = await fetch('/api/meetings/requests/' + encodeURIComponent(requestId) + '/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to confirm request');
        var meetingId = data.meetingId || (data.meeting && data.meeting.id) || (data.request && data.request.conversion && data.request.conversion.meetingId) || '';
        var ran = null;
        if (meetingId) {
            ran = await _mtgRunMeeting(meetingId, { action: 'confirmed_start' });
        }
        closeMeetingRequestDetailModal();
        await _mtgRefresh();
        var latest = meetingId ? _mtgFindMeeting(meetingId) : null;
        var current = latest || (ran && ran.meeting) || data.meeting || null;
        switchMtgTab(_mtgMeetingCompleted(current) ? 'completed' : 'active');
        if (current) openMeetingDetailRecord(current);
        else if (meetingId) openMeetingDetailModal(meetingId);
    } catch (e) {
        _mtgRequestError(requestId, e.message || String(e));
    }
}

async function _mtgRejectRequest(requestId) {
    _mtgRequestError(requestId, '');
    var reason = ((document.getElementById('mtg-request-reject-reason-' + requestId) || {}).value || '').trim();
    if (!reason) return _mtgRequestError(requestId, _mtgT('meeting_request_reject_reason_required', 'Enter a rejection reason.'));
    try {
        var res = await fetch('/api/meetings/requests/' + encodeURIComponent(requestId) + '/reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to reject request');
        closeMeetingRequestDetailModal();
        await _mtgRefresh();
        switchMtgTab('requests');
    } catch (e) {
        _mtgRequestError(requestId, e.message || String(e));
    }
}

function _mtgDecisionSecondsRemaining(deadlineAt) {
    if (!deadlineAt) return null;
    var deadline = new Date(deadlineAt).getTime();
    if (!Number.isFinite(deadline)) return null;
    return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
}

function _mtgResolutionPolicyLabel(policy) {
    if (policy === 'moderator_decision') return _mtgT('meeting_resolution_moderator_decision', 'Moderator decides and closes');
    return _mtgT('meeting_resolution_user_decision', 'User decides disagreements');
}

function _mtgOutcomeLabel(outcome) {
    if (outcome === 'approved') return _mtgT('meeting_outcome_approved', 'Approved');
    if (outcome === 'rejected') return _mtgT('meeting_outcome_rejected', 'Rejected');
    if (outcome === 'no_consensus') return _mtgT('meeting_outcome_no_consensus', 'No consensus');
    if (outcome === 'needs_user_decision') return _mtgT('meeting_outcome_needs_user_decision', 'Needs user decision');
    return outcome || '';
}

function _mtgRenderResultSummary(m) {
    var result = (m && m.result) || {};
    var hasStructured = !!(result.outcome || result.rationale || (result.unresolvedQuestions || []).length || (result.disagreements || []).length || (result.actionItems || []).length);
    if (!m || (!m.summary && !m.resolution && !hasStructured)) return '';
    var html = '<div class="mtg-section mtg-result-summary">';
    html += '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_result_summary', 'Meeting result')) + '</div>';
    if (result.outcome) {
        html += '<div class="mtg-result-outcome mtg-result-outcome-' + _escMtg(result.outcome) + '">' + _escMtg(_mtgOutcomeLabel(result.outcome)) + '</div>';
    }
    if (m.summary) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_tr('summary')) + '</div><div class="mtg-section-text">' + _escMtg(m.summary) + '</div></div>';
    }
    if (m.resolution) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_tr('resolution')) + '</div><div class="mtg-section-text">' + _escMtg(m.resolution) + '</div></div>';
    }
    if (result.rationale) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_mtgT('meeting_rationale', 'Rationale')) + '</div><div class="mtg-section-text">' + _escMtg(result.rationale) + '</div></div>';
    }
    if (result.unresolvedQuestions && result.unresolvedQuestions.length) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_mtgT('meeting_unresolved_questions', 'Unresolved questions')) + '</div><div class="mtg-section-text">' + result.unresolvedQuestions.map(function(item) { return '• ' + _escMtg(item); }).join('\n') + '</div></div>';
    }
    if (result.disagreements && result.disagreements.length) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_mtgT('meeting_disagreements', 'Disagreements')) + '</div><div class="mtg-section-text">' + result.disagreements.map(function(item) { return '• ' + _escMtg(item); }).join('\n') + '</div></div>';
    }
    if (m.actionItems && m.actionItems.length) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_tr('action_items')) + '</div><div class="mtg-section-text">' + m.actionItems.map(function(a) { return '• ' + _escMtg(_mtgActionText(a)); }).join('\n') + '</div></div>';
    }
    html += '</div>';
    return html;
}

function _mtgDecisionCountdownText(m) {
    var seconds = _mtgDecisionSecondsRemaining(m && m.decisionDeadlineAt);
    if (seconds == null) return '⏳ ' + _mtgT('meeting_decision_waiting', 'Waiting');
    if (seconds <= 0) return '⏳ 0s';
    return '⏳ ' + seconds + 's';
}

function _mtgUpdateDecisionCountdowns() {
    document.querySelectorAll('.mtg-decision-countdown').forEach(function(el) {
        var seconds = _mtgDecisionSecondsRemaining(el.dataset.deadline || '');
        if (seconds == null) {
            el.textContent = '⏳ ' + _mtgT('meeting_decision_waiting', 'Waiting');
        } else {
            el.textContent = '⏳ ' + Math.max(0, seconds) + 's';
        }
        el.classList.toggle('mtg-badge-countdown-expired', seconds === 0);
        if (seconds === 0 && el.dataset.autoContinue === '1') {
            _mtgAutoContinueDecisionWindow(el.dataset.meetingId || '');
        }
    });
}

function _mtgMaybeAutoContinueDecisionMeeting(m) {
    if (!m || !m.executableMeeting || (m.executionStage || '') !== 'awaiting_user_decision') return;
    if (m.arbitration && m.arbitration.reason === 'no_consensus') return;
    if (_mtgDecisionSecondsRemaining(m.decisionDeadlineAt || '') === 0) {
        _mtgAutoContinueDecisionWindow(m.id || '');
    }
}

async function _mtgAutoContinueDecisionWindow(meetingId) {
    if (!meetingId || _mtgDecisionAutoContinuing[meetingId]) return;
    _mtgDecisionAutoContinuing[meetingId] = true;
    var badge = document.getElementById('mtg-decision-countdown-' + meetingId);
    if (badge) {
        badge.textContent = '⏳ ' + _mtgT('meeting_decision_continuing', 'Continuing');
        badge.dataset.autoContinue = '0';
    }
    _mtgSetDecisionControlsDisabled(meetingId, true);
    try {
        var ran = await _mtgRunMeeting(meetingId, { action: 'timeout' });
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(ran && ran.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        console.warn('[meetings] decision window auto-continue failed:', e);
        if (badge) {
            badge.textContent = '⏳ 0s';
            badge.dataset.autoContinue = '1';
        }
        _mtgSetDecisionControlsDisabled(meetingId, false);
    } finally {
        delete _mtgDecisionAutoContinuing[meetingId];
    }
}

function _mtgSetDecisionControlsDisabled(meetingId, disabled) {
    ['mtg-target-submit-', 'mtg-continue-', 'mtg-target-participant-', 'mtg-target-question-', 'mtg-agenda-submit-', 'mtg-agenda-text-', 'mtg-agenda-reason-', 'mtg-arb-decision-', 'mtg-arb-rationale-', 'mtg-arb-consensus-', 'mtg-arb-decide-', 'mtg-arb-end-', 'mtg-arb-continue-', 'mtg-takeover-submit-', 'mtg-replacement-submit-', 'mtg-takeover-summary-', 'mtg-takeover-decision-', 'mtg-replacement-moderator-'].forEach(function(prefix) {
        var el = document.getElementById(prefix + meetingId);
        if (el) el.disabled = !!disabled;
    });
}

function _mtgRenderInterventionForm(m) {
    var id = _escMtg(m.id);
    var agendaValue = _escMtg(m.agenda || m.topic || '');
    return '<div class="mtg-section mtg-intervention" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_user_intervention', 'User intervention')) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_user_message', 'Message')) + '</label>' +
        '<textarea id="mtg-intervention-text-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_user_message_placeholder', 'Add a live comment for the agents.')) + '"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_add_context', 'Additional context')) + '</label>' +
        '<textarea id="mtg-intervention-context-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_add_context_placeholder', 'Add facts or constraints for later turns.')) + '"></textarea>' +
        '<div id="mtg-intervention-error-' + id + '" class="mtg-inline-error"></div>' +
        '<button id="mtg-intervention-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingIntervention(\'' + id + '\')">' + _escMtg(_mtgT('meeting_send_intervention', 'Send')) + '</button>' +
        '<div class="mtg-subsection">' +
        '<div class="mtg-section-title mtg-section-title-small">' + _escMtg(_mtgT('meeting_adjust_agenda', 'Adjust agenda')) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_new_agenda', 'New agenda')) + '</label>' +
        '<textarea id="mtg-agenda-text-' + id + '" class="mtg-textarea" rows="2" placeholder="' + _escMtg(_mtgT('meeting_new_agenda_placeholder', 'Set the agenda for upcoming turns.')) + '">' + agendaValue + '</textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_agenda_reason', 'Reason')) + '</label>' +
        '<input id="mtg-agenda-reason-' + id + '" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_agenda_reason_placeholder', 'Optional reason for the change.')) + '">' +
        '<div id="mtg-agenda-error-' + id + '" class="mtg-inline-error"></div>' +
        '<button id="mtg-agenda-submit-' + id + '" class="mtg-btn" onclick="submitMeetingAgendaChange(\'' + id + '\')">' + _escMtg(_mtgT('meeting_save_agenda', 'Save agenda')) + '</button>' +
        '</div>' +
        '</div>';
}

function _mtgRenderDecisionWindowControls(m) {
    var id = _escMtg(m.id);
    var participants = m.participants || m.agents || [];
    var options = participants.map(function(p) {
        var info = _mtgAgentMap[p] || { emoji: '🤖', name: p };
        return '<option value="' + _escMtg(p) + '">' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || p)) + '</option>';
    }).join('');
    var deadline = m.decisionDeadlineAt ? new Date(m.decisionDeadlineAt).toLocaleTimeString() : '';
    var isNoConsensus = m.arbitration && m.arbitration.reason === 'no_consensus';
    var willSummarize = !isNoConsensus && (m.decisionNextStage === 'summarizing');
    var hint = isNoConsensus
        ? _mtgT('meeting_arbitration_waiting_hint', 'The meeting found unresolved disagreement. Choose a decision, continue discussion, or end with no consensus.')
        : (willSummarize
            ? _mtgT('meeting_decision_summary_hint', 'The final formal round is complete. Ask one participant, add context, or wait for the moderator to summarize and end.')
            : _mtgT('meeting_decision_window_hint', 'A formal round is complete. Ask one participant, add context, or continue the agenda.'));
    if (!isNoConsensus && m.decisionWindowSec) hint += ' ' + _mtgT('meeting_decision_window_timeout', 'Timeout') + ': ' + m.decisionWindowSec + 's';
    if (!isNoConsensus && deadline) hint += ' · ' + _mtgT('meeting_decision_deadline', 'Deadline') + ': ' + deadline;
    var html = '<div class="mtg-section mtg-decision-window" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_decision_window', 'Round decision window')) + '</div>' +
        (!isNoConsensus ? '<div class="mtg-section-text mtg-decision-countdown" data-meeting-id="' + id + '" data-deadline="' + _escMtg(m.decisionDeadlineAt || '') + '" data-auto-continue="1">' + _escMtg(_mtgDecisionCountdownText(m)) + '</div>' : '') +
        '<div class="mtg-section-text">' + _escMtg(hint) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_target_participant', 'Target participant')) + '</label>' +
        '<select id="mtg-target-participant-' + id + '" class="skl-input">' + options + '</select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_target_question', 'Targeted question')) + '</label>' +
        '<textarea id="mtg-target-question-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_target_question_placeholder', 'Ask this participant to respond before the next round.')) + '"></textarea>' +
        '<div id="mtg-target-error-' + id + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-decision-actions">' +
        '<button id="mtg-target-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingTargetedQuestion(\'' + id + '\')">' + _escMtg(_mtgT('meeting_send_targeted_question', 'Ask participant')) + '</button>' +
        '<button id="mtg-continue-' + id + '" class="mtg-btn" onclick="continueMeetingDecisionWindow(\'' + id + '\')">▶ ' + _escMtg(_mtgT('meeting_continue', 'Continue')) + '</button>' +
        '</div>' +
        '</div>';
    if (isNoConsensus) {
        html += _mtgRenderArbitrationControls(m);
    }
    return html;
}

function _mtgRenderArbitrationControls(m) {
    var id = _escMtg(m.id);
    var arb = m.arbitration || {};
    var positions = (arb.positions || []).map(function(item) {
        var info = _mtgAgentMap[item.speaker] || { emoji: '🤖', name: item.speaker || '' };
        return '<div class="mtg-arb-position"><strong>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || item.speaker || '')) + '</strong><span>' + _escMtg(item.position || '') + '</span></div>';
    }).join('');
    var disagreements = (arb.disagreements || []).map(function(item) { return '• ' + _escMtg(item); }).join('\n');
    return '<div class="mtg-section mtg-arbitration" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_arbitration_title', 'No consensus arbitration')) + '</div>' +
        '<div class="mtg-section-text">' + _escMtg(arb.moderatorSuggestion || _mtgT('meeting_arbitration_hint', 'Choose a decision, continue discussion, or end with no consensus.')) + '</div>' +
        (positions ? '<div class="mtg-arb-positions">' + positions + '</div>' : '') +
        (disagreements ? '<div class="mtg-section-text mtg-arb-disagreements">' + disagreements + '</div>' : '') +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_arbitration_decision', 'Decision')) + '</label>' +
        '<textarea id="mtg-arb-decision-' + id + '" class="mtg-textarea" rows="2" placeholder="' + _escMtg(_mtgT('meeting_arbitration_decision_placeholder', 'Write the user decision to finalize.')) + '"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_arbitration_rationale', 'Rationale')) + '</label>' +
        '<input id="mtg-arb-rationale-' + id + '" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_arbitration_rationale_placeholder', 'Optional rationale.')) + '">' +
        '<div id="mtg-arb-error-' + id + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-decision-actions">' +
        '<button id="mtg-arb-consensus-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingArbitration(\'' + id + '\', \'consensus_summary\')">' + _escMtg(_mtgT('meeting_arbitration_consensus_summary', 'Consensus reached, summarize')) + '</button>' +
        '<button id="mtg-arb-decide-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingArbitration(\'' + id + '\', \'decide\')">' + _escMtg(_mtgT('meeting_arbitration_decide', 'Finalize decision')) + '</button>' +
        '<button id="mtg-arb-continue-' + id + '" class="mtg-btn" onclick="submitMeetingArbitration(\'' + id + '\', \'continue_discussion\')">' + _escMtg(_mtgT('meeting_arbitration_continue', 'Continue one round')) + '</button>' +
        '<button id="mtg-arb-end-' + id + '" class="mtg-btn mtg-btn-delete" onclick="submitMeetingArbitration(\'' + id + '\', \'end_no_consensus\')">' + _escMtg(_mtgT('meeting_arbitration_end', 'End no consensus')) + '</button>' +
        '</div>' +
        '</div>';
}

function _mtgRenderModeratorTakeoverControls(m) {
    var id = _escMtg(m.id);
    var failure = m.moderatorFailure || {};
    var participants = m.participants || m.agents || [];
    var currentModerator = m.moderator || failure.moderator || '';
    var options = participants.map(function(p) {
        var info = _mtgAgentMap[p] || { emoji: '🤖', name: p };
        return '<option value="' + _escMtg(p) + '"' + (p === currentModerator ? ' disabled' : '') + '>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || p)) + (p === currentModerator ? ' (' + _escMtg(_mtgT('meeting_current_moderator', 'current')) + ')' : '') + '</option>';
    }).join('');
    return '<div class="mtg-section mtg-moderator-takeover" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_moderator_takeover_title', 'Moderator takeover')) + '</div>' +
        '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_moderator_takeover_hint', 'The moderator failed while summarizing. Take over manually or choose another moderator to retry.')) + '</div>' +
        '<div class="mtg-inline-error" style="display:block">' + _escMtg(failure.error || '') + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_takeover_summary', 'User summary')) + '</label>' +
        '<textarea id="mtg-takeover-summary-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_takeover_summary_placeholder', 'Write the final summary to close the meeting.')) + '"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_takeover_decision', 'Decision')) + '</label>' +
        '<input id="mtg-takeover-decision-' + id + '" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_takeover_decision_placeholder', 'Optional final decision.')) + '">' +
        '<div id="mtg-takeover-error-' + id + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-decision-actions">' +
        '<button id="mtg-takeover-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitModeratorTakeover(\'' + id + '\', \'user_takeover\')">' + _escMtg(_mtgT('meeting_takeover_submit', 'Take over and close')) + '</button>' +
        '</div>' +
        '<div class="mtg-subsection">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_replacement_moderator', 'Replacement moderator')) + '</label>' +
        '<select id="mtg-replacement-moderator-' + id + '" class="skl-input">' + options + '</select>' +
        '<button id="mtg-replacement-submit-' + id + '" class="mtg-btn" onclick="submitModeratorTakeover(\'' + id + '\', \'replace_moderator\')">' + _escMtg(_mtgT('meeting_replace_moderator_submit', 'Retry with moderator')) + '</button>' +
        '</div>' +
        '</div>';
}

function _escMtg(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _mtgJsArg(value) {
    return JSON.stringify(value == null ? '' : String(value)).replace(/</g, '\\u003c');
}

function _mtgT(key, fallback) {
    if (typeof i18n !== 'undefined' && i18n && typeof i18n.t === 'function') {
        var translated = i18n.t(key);
        if (translated && translated !== key) return translated;
    }
    var lang = 'en';
    try { lang = (typeof i18n !== 'undefined' && i18n.getLanguage && i18n.getLanguage()) || document.documentElement.lang || 'en'; } catch (e) {}
    var zhFallback = {
        new_meeting: '新建会议',
        meeting_executable: '可执行会议',
        meeting_stage: '阶段',
        meeting_preparing_timeout_remaining: '{seconds} 秒后自动释放',
        meeting_preparing_timeout_released: '准备超时已释放',
        meeting_version: '版本',
        meeting_round: '轮次',
        meeting_moderator: '主持人',
        meeting_context_mode: '上下文模式',
        meeting_current_speaker: '当前发言者',
        meeting_contributions: '主要贡献',
        meeting_transcript: '逐轮发言',
        meeting_opening_round: '开场轮',
        meeting_discussion_round: '讨论轮',
        meeting_turn_failed: '调用失败',
        meeting_provider_calling: '正在调用',
        meeting_live_discussion: '实时讨论',
        meeting_user_intervention: '用户插话',
        meeting_user_message: '发言',
        meeting_user_message_placeholder: '给正在讨论的 Agent 补充一段发言',
        meeting_add_context: '补充上下文',
        meeting_add_context_placeholder: '补充事实、约束或用户确认信息，后续发言会看到',
        meeting_send_intervention: '发送',
        meeting_intervention_required: '请输入发言或补充上下文。',
        meeting_user: '用户',
        meeting_turn_position: '立场',
        meeting_turn_reasoning: '理由',
        meeting_turn_disagreements: '分歧',
        meeting_turn_questions: '问题',
        meeting_turn_next_step: '下一步',
        meeting_turn_confidence: '信心',
        meeting_parse_fallback: '已保留原文',
        meeting_ai_end: '请主持人总结并结束',
        meeting_ai_ending: '主持人总结中...',
        meeting_start_existing: '开始会议',
        meeting_starting: '启动中...',
        meeting_start_failed: '开始会议失败',
        meeting_decision_window: '轮末决策窗口',
        meeting_decision_window_hint: '本轮正式发言已结束。可以点名、补充上下文，或继续原议程。',
        meeting_decision_summary_hint: '最后一轮正式发言已结束。可以点名、补充上下文，或等待主持人总结并结束。',
        meeting_decision_window_timeout: '等待',
        meeting_decision_deadline: '截止',
        meeting_decision_waiting: '等待中',
        meeting_decision_continuing: '继续中',
        meeting_target_participant: '点名对象',
        meeting_target_question: '点名问题',
        meeting_target_question_placeholder: '请指定参会 Agent 在进入下一轮前补充回答',
        meeting_send_targeted_question: '点名提问',
        meeting_continue: '继续',
        meeting_targeted_question: '点名提问',
        meeting_targeted_response: '点名回答',
        meeting_target_required: '请选择点名对象。',
        meeting_target_question_required: '请输入点名问题。',
        meeting_targeted_calling: '正在回答点名',
        meeting_current_agenda: '当前议题',
        meeting_adjust_agenda: '调整议题',
        meeting_new_agenda: '新议题',
        meeting_new_agenda_placeholder: '设置后续轮次要讨论的议题',
        meeting_agenda_reason: '调整原因',
        meeting_agenda_reason_placeholder: '可选，说明为什么调整',
        meeting_save_agenda: '保存议题',
        meeting_agenda_required: '请填写新议题。',
        meeting_agenda_changed: '议题调整',
        meeting_previous_agenda: '原议题',
        meeting_arbitration_title: '无共识裁决',
        meeting_arbitration_hint: '请选择裁决、继续讨论或以无共识结束。',
        meeting_arbitration_waiting: '等待裁决',
        meeting_arbitration_waiting_hint: '会议存在未解决分歧。请选择裁决、继续讨论或以无共识结束。',
        meeting_arbitration_decision: '裁决',
        meeting_arbitration_decision_placeholder: '填写最终采纳的用户裁决',
        meeting_arbitration_rationale: '裁决理由',
        meeting_arbitration_rationale_placeholder: '可选，说明裁决依据',
        meeting_arbitration_consensus_summary: '达成共识并总结',
        meeting_arbitration_decide: '采纳裁决并结束',
        meeting_arbitration_continue: '继续一轮',
        meeting_arbitration_end: '无共识结束',
        meeting_arbitration_decision_required: '请填写裁决内容。',
        meeting_arbitration_marker: '用户裁决',
        meeting_arbitration_action: '动作',
        meeting_moderator_takeover_title: '主持接管',
        meeting_moderator_takeover_hint: '主持人在总结时失败。你可以手动接管结束，或选择另一位主持人重试。',
        meeting_takeover_summary: '用户总结',
        meeting_takeover_summary_placeholder: '填写最终总结以结束会议',
        meeting_takeover_decision: '决议',
        meeting_takeover_decision_placeholder: '可选，填写最终决议',
        meeting_takeover_summary_required: '请填写用户总结。',
        meeting_takeover_submit: '接管并结束',
        meeting_replacement_moderator: '替换主持人',
        meeting_replace_moderator_submit: '用新主持重试',
        meeting_current_moderator: '当前',
        meeting_view_detail: '查看详情',
        meeting_detail_title: '会议详情',
        meeting_history_search_placeholder: '搜索历史会议',
        meeting_topic: '主题',
        meeting_topic_placeholder: '这场会议要讨论什么？',
        meeting_purpose: '目的',
        meeting_purpose_placeholder: '这场会议需要产出什么结果？',
        meeting_type: '会议类型',
        meeting_project: '项目',
        meeting_project_none: '不绑定项目',
        meeting_type_information: '信息收集',
        meeting_type_discussion: '讨论决策',
        meeting_type_task: '任务协作',
        meeting_participants: '参会者',
        meeting_branch_quick_select: '按部门快捷选择',
        meeting_branch_quick_select_hint: '先选择部门，再手动调整单个 Agent。',
        meeting_context_incremental: '增量',
        meeting_context_summary: '摘要',
        meeting_context_full: '完整',
        meeting_resolution_policy: '裁决策略',
        meeting_resolution_user_decision: '用户裁决分歧',
        meeting_resolution_moderator_decision: '主持裁决并关闭',
        meeting_result_summary: '会议结论',
        meeting_outcome: '结果',
        meeting_outcome_approved: '通过',
        meeting_outcome_rejected: '不通过',
        meeting_outcome_no_consensus: '无共识',
        meeting_outcome_needs_user_decision: '需要用户裁决',
        meeting_rationale: '理由',
        meeting_unresolved_questions: '未解决问题',
        meeting_disagreements: '分歧',
        meeting_max_rounds: '最大讨论轮次',
        meeting_initial_context: '初始上下文',
        meeting_initial_context_placeholder: '用户确认后提供给所有 Agent 的上下文',
        meeting_start: '开始会议',
        meeting_running: '会议运行中...',
        meeting_error_topic_required: '请填写会议主题。',
        meeting_error_participants_required: '至少选择两名参会者。',
        meeting_error_moderator_required: '请选择主持人。',
        meeting_action_drafts: '行动项草稿',
        meeting_action_drafts_hint: '确认后会加入来源任务的会议行动项，草稿不会自动执行。',
        meeting_action_untitled: '未命名行动项',
        meeting_action_status_draft: '待确认',
        meeting_action_status_confirmed: '已加入当前任务',
        meeting_action_status_rejected: '已拒绝',
        meeting_action_status_kept: '仅保存',
        meeting_action_edit: '编辑',
        meeting_action_owner: '负责人',
        meeting_action_title: '任务标题',
        meeting_action_description: '说明',
        meeting_action_save_draft: '保存草稿',
        meeting_action_confirm_task: '加入当前任务',
        meeting_action_keep: '仅保存',
        meeting_action_reject: '拒绝',
        meeting_action_open_task: '打开来源任务',
        meeting_action_task_created: '已加入来源任务',
        meeting_action_rejected_by_user: '用户拒绝'
    };
    if (String(lang).toLowerCase().indexOf('zh') === 0 && zhFallback[key]) return zhFallback[key];
    return fallback || key;
}

function _mtgLiveStateFromMeeting(m) {
    var state = {
        lastSeq: Number(m.lastEventSequence || 0),
        transcript: [],
        pendingBySeq: {},
        turnBySeq: {},
        timeoutRunBySeq: {}
    };
    (m.transcript || []).forEach(function(turn) {
        var seq = Number(turn.sequence || 0);
        if (seq) state.turnBySeq[seq] = true;
        state.transcript.push(turn);
    });
    (m.pendingCalls || []).forEach(function(call) {
        var seq = Number(call.sequence || 0);
        if (seq) state.pendingBySeq[seq] = call;
    });
    return state;
}

function _mtgSeedLiveMeetings(meetings) {
    (meetings || []).forEach(function(m) {
        if (!m.executableMeeting || m.status !== 'active') return;
        _mtgLiveEvents[m.id] = _mtgLiveStateFromMeeting(m);
    });
}

function _mtgMergeLiveMeeting(m) {
    if (!m || !m.executableMeeting || m.status !== 'active') return m;
    var state = _mtgLiveEvents[m.id];
    if (!state) return m;
    var copy = Object.assign({}, m);
    copy.transcript = state.transcript.slice();
    copy.pendingCalls = Object.keys(state.pendingBySeq).map(function(key) { return state.pendingBySeq[key]; });
    copy.lastEventSequence = Math.max(Number(copy.lastEventSequence || 0), Number(state.lastSeq || 0));
    return copy;
}

function _mtgTurnFromParticipantEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'participant_turn',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.speaker || (event.actor || {}).id || '',
        text: payload.text || '',
        rawText: payload.rawText || payload.text || '',
        structured: payload.structured || {},
        parseError: payload.parseError || '',
        ok: !!payload.ok,
        durationMs: Number(payload.durationMs || 0),
        providerRef: payload.providerRef || {},
        kind: payload.kind || '',
        targetQuestion: payload.targetQuestion || '',
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromUserInterventionEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'user_intervention',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        text: payload.text || '',
        context: payload.context || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromTargetedQuestionEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'targeted_question',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        target: payload.target || '',
        text: payload.question || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromAgendaChangeEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'agenda_change',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        text: payload.agenda || '',
        previousAgenda: payload.previousAgenda || '',
        reason: payload.reason || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromArbitrationEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'arbitration_decision',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        text: payload.decision || payload.action || '',
        action: payload.action || '',
        rationale: payload.rationale || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgPendingFromProviderEvent(event) {
    var payload = event.payload || {};
    return {
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.speaker || (event.actor || {}).id || '',
        purpose: payload.purpose || '',
        promptChars: Number(payload.promptChars || 0),
        contextMode: payload.contextMode || '',
        createdAt: event.createdAt || '',
        elapsedSec: Number(payload.elapsedSec || 0),
        timeoutSec: Number(payload.timeoutSec || 0),
        timedOut: !!payload.timedOut
    };
}

function _mtgProviderTimeoutSec() {
    return 120;
}

function _mtgCallElapsedSec(call) {
    if (!call) return 0;
    if (Number(call.elapsedSec || 0) > 0) return Number(call.elapsedSec || 0);
    if (!call.createdAt) return 0;
    var ts = Date.parse(call.createdAt);
    if (!isFinite(ts)) return 0;
    return Math.max(0, Math.floor((Date.now() - ts) / 1000));
}

function _mtgHydratePendingCall(call) {
    if (!call) return call;
    var copy = Object.assign({}, call);
    copy.elapsedSec = _mtgCallElapsedSec(copy);
    copy.timeoutSec = Number(copy.timeoutSec || _mtgProviderTimeoutSec());
    copy.timedOut = !!copy.timedOut || (copy.timeoutSec > 0 && copy.elapsedSec >= copy.timeoutSec);
    return copy;
}

function _mtgApplyLiveEvent(meetingId, event) {
    var state = _mtgLiveEvents[meetingId] || { lastSeq: 0, transcript: [], pendingBySeq: {}, turnBySeq: {}, timeoutRunBySeq: {} };
    var seq = Number(event.sequence || 0);
    if (seq) state.lastSeq = Math.max(Number(state.lastSeq || 0), seq);
    if (event.type === 'provider_call_started') {
        state.pendingBySeq[seq] = _mtgPendingFromProviderEvent(event);
    } else if (event.type === 'participant_turn') {
        var turn = _mtgTurnFromParticipantEvent(event);
        if (turn.sequence && !state.turnBySeq[turn.sequence]) {
            state.turnBySeq[turn.sequence] = true;
            state.transcript.push(turn);
        }
        var inReplyTo = (event.payload || {}).inReplyToSequence;
        if (inReplyTo != null) delete state.pendingBySeq[inReplyTo];
    } else if (event.type === 'user_intervention') {
        var intervention = _mtgTurnFromUserInterventionEvent(event);
        if (intervention.sequence && !state.turnBySeq[intervention.sequence]) {
            state.turnBySeq[intervention.sequence] = true;
            state.transcript.push(intervention);
        }
    } else if (event.type === 'targeted_question') {
        var targeted = _mtgTurnFromTargetedQuestionEvent(event);
        if (targeted.sequence && !state.turnBySeq[targeted.sequence]) {
            state.turnBySeq[targeted.sequence] = true;
            state.transcript.push(targeted);
        }
    } else if (event.type === 'agenda_change') {
        var agendaChange = _mtgTurnFromAgendaChangeEvent(event);
        if (agendaChange.sequence && !state.turnBySeq[agendaChange.sequence]) {
            state.turnBySeq[agendaChange.sequence] = true;
            state.transcript.push(agendaChange);
        }
    } else if (event.type === 'arbitration_decision') {
        var arbitration = _mtgTurnFromArbitrationEvent(event);
        if (arbitration.sequence && !state.turnBySeq[arbitration.sequence]) {
            state.turnBySeq[arbitration.sequence] = true;
            state.transcript.push(arbitration);
        }
    }
    _mtgLiveEvents[meetingId] = state;
}

function _mtgEnsureLivePolling() {
    if (_mtgLivePollTimer) return;
    _mtgLivePollTimer = setInterval(_mtgPollLiveMeetings, 2000);
}

function _mtgStopLivePolling() {
    if (_mtgLivePollTimer) clearInterval(_mtgLivePollTimer);
    _mtgLivePollTimer = null;
}

async function _mtgPollLiveMeetings() {
    var modal = document.getElementById('meetingsModal');
    if (!modal || modal.classList.contains('hidden')) {
        _mtgStopLivePolling();
        return;
    }
    var meetings = (_mtgData.active || []).filter(function(m) { return m.executableMeeting && m.status === 'active'; });
    if (!meetings.length) return;
    var changed = false;
    var shouldRefresh = false;
    await Promise.all(meetings.map(async function(m) {
        var state = _mtgLiveEvents[m.id] || _mtgLiveStateFromMeeting(m);
        _mtgLiveEvents[m.id] = state;
        try {
            var res = await fetch('/api/meetings/executable/' + encodeURIComponent(m.id) + '/events?after=' + encodeURIComponent(state.lastSeq || 0));
            var data = await res.json();
            if (!res.ok || data.error) return;
            _mtgMaybeAutoContinueDecisionMeeting(m);
            (data.events || []).forEach(function(event) {
                _mtgApplyLiveEvent(m.id, event);
                changed = true;
                if (event.type === 'meeting_result' || (event.type === 'meeting_transitioned' && (event.payload || {}).to === 'completed')) {
                    shouldRefresh = true;
                }
            });
            var hydratedPending = Object.keys(state.pendingBySeq || {}).map(function(key) {
                var call = _mtgHydratePendingCall(state.pendingBySeq[key]);
                state.pendingBySeq[key] = call;
                return call;
            });
            if (hydratedPending.some(function(call) { return call.timedOut; })) changed = true;
            hydratedPending.forEach(function(call) {
                if (!call.timedOut || !call.sequence || state.timeoutRunBySeq[call.sequence]) return;
                state.timeoutRunBySeq[call.sequence] = Date.now();
                fetch('/api/meetings/executable/' + encodeURIComponent(m.id) + '/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'provider_timeout_skip', pendingSequence: call.sequence })
                }).catch(function(e) {
                    console.warn('[meetings] provider timeout skip failed:', e);
                });
            });
        } catch (e) {
            console.warn('[meetings] live poll error:', e);
        }
    }));
    if (shouldRefresh) {
        await _mtgAfterMeetingRefresh();
        switchMtgTab('completed');
    } else if (changed && !modal.classList.contains('hidden')) {
        _mtgRender();
        _mtgRefreshDetailModal();
    }
}

function _mtgTranscriptGroupLabel(turn) {
    var stage = turn.stage || '';
    var round = Number(turn.round || 0);
    if (stage === 'active_opening') return _mtgT('meeting_opening_round', 'Opening round');
    if (stage === 'active_discussion') return _mtgT('meeting_discussion_round', 'Discussion round') + ' ' + (round || 1);
    return (stage || 'round') + ' ' + (round || 0);
}

function _mtgRenderTranscript(m) {
    var groups = [];
    var indexByKey = {};
    var rows = (m.transcript || []).map(function(turn) {
        return Object.assign({ pending: false }, turn);
    });
    (m.pendingCalls || []).forEach(function(call) {
        rows.push(Object.assign({ pending: true }, _mtgHydratePendingCall(call)));
    });
    rows.sort(function(a, b) { return Number(a.sequence || 0) - Number(b.sequence || 0); });
    rows.forEach(function(turn) {
        var key = (turn.stage || '') + ':' + (turn.round || 0);
        if (indexByKey[key] == null) {
            indexByKey[key] = groups.length;
            groups.push({ label: _mtgTranscriptGroupLabel(turn), turns: [] });
        }
        groups[indexByKey[key]].turns.push(turn);
    });
    var titleKey = m.status === 'active' ? 'meeting_live_discussion' : 'meeting_transcript';
    var titleFallback = m.status === 'active' ? 'Live discussion' : 'Round transcript';
    var html = '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT(titleKey, titleFallback)) + '</div>';
    groups.forEach(function(group) {
        html += '<div class="mtg-round">';
        html += '<div class="mtg-round-title">' + _escMtg(group.label) + '</div>';
        group.turns.forEach(function(turn) {
            var isTargetedQuestion = turn.type === 'targeted_question';
            var isTargetedResponse = turn.kind === 'targeted_response';
            var isTargetedPending = turn.pending && turn.purpose === 'targeted_response';
            var isAgendaChange = turn.type === 'agenda_change';
            var isArbitration = turn.type === 'arbitration_decision';
            var isUserTurn = turn.type === 'user_intervention' || turn.actorType === 'user';
            var info = isUserTurn ? { emoji: '👤', name: _mtgT('meeting_user', 'User') } : (_mtgAgentMap[turn.speaker] || { emoji: '🤖', name: turn.speaker || 'Unknown' });
            var providerKind = ((turn.providerRef || {}).providerKind || '').trim();
            var pendingStatus = turn.timedOut ? _mtgT('meeting_provider_call_timeout', 'call timed out') : _mtgT('meeting_provider_calling', 'calling');
            var status = isUserTurn ? '' : (turn.pending ? ' · ' + pendingStatus : (turn.ok ? '' : ' · ' + _mtgT('meeting_turn_failed', 'failed')));
            var duration = turn.durationMs ? ' · ' + Math.round(turn.durationMs / 1000) + 's' : '';
            var pendingText = isTargetedPending ? _mtgT('meeting_targeted_calling', 'Answering targeted question...') : _mtgT('meeting_provider_calling', 'Calling provider...');
            if (turn.pending && turn.timedOut) {
                pendingText = _mtgT('meeting_provider_timeout_monitor', 'Provider call has exceeded the timeout and will be skipped so the meeting can continue.');
            } else if (turn.pending && turn.elapsedSec) {
                pendingText += ' · ' + _mtgT('meeting_provider_waited', 'waited') + ' ' + Math.round(turn.elapsedSec) + 's';
            }
            var text = turn.pending ? pendingText : (turn.text || '');
            var marker = '';
            if (isTargetedQuestion) {
                var targetInfo = _mtgAgentMap[turn.target] || { emoji: '🤖', name: turn.target || '' };
                marker = _mtgT('meeting_targeted_question', 'Targeted question') + (turn.target ? ' → ' + (targetInfo.name || turn.target) : '');
            } else if (isTargetedResponse) {
                marker = _mtgT('meeting_targeted_response', 'Targeted response');
            } else if (isAgendaChange) {
                marker = _mtgT('meeting_agenda_changed', 'Agenda changed');
            } else if (isArbitration) {
                marker = _mtgT('meeting_arbitration_marker', 'Arbitration');
            }
            if (isUserTurn && turn.context) {
                text += (text ? '\n\n' : '') + _mtgT('meeting_add_context', 'Additional context') + ': ' + turn.context;
            }
            if (isAgendaChange) {
                text = _mtgT('meeting_new_agenda', 'New agenda') + ': ' + (turn.text || '');
                if (turn.previousAgenda) text += '\n' + _mtgT('meeting_previous_agenda', 'Previous agenda') + ': ' + turn.previousAgenda;
                if (turn.reason) text += '\n' + _mtgT('meeting_agenda_reason', 'Reason') + ': ' + turn.reason;
            }
            if (isArbitration) {
                text = _mtgT('meeting_arbitration_action', 'Action') + ': ' + (turn.action || '') + (turn.text ? '\n' + _mtgT('meeting_arbitration_decision', 'Decision') + ': ' + turn.text : '');
                if (turn.rationale) text += '\n' + _mtgT('meeting_arbitration_rationale', 'Rationale') + ': ' + turn.rationale;
            }
            if (isTargetedResponse && turn.targetQuestion) {
                text = _mtgT('meeting_targeted_question', 'Targeted question') + ': ' + turn.targetQuestion + '\n\n' + text;
            }
            html += '<div class="mtg-turn' + (turn.pending ? ' mtg-turn-pending' : '') + (turn.timedOut ? ' mtg-turn-timeout' : '') + (isUserTurn ? ' mtg-turn-user' : '') + '">';
            html += '<div class="mtg-turn-header"><span class="mtg-response-emoji">' + _escMtg(info.emoji || '🤖') + '</span><span class="mtg-response-name">' + _escMtg(info.name || turn.speaker || 'Unknown') + '</span>';
            html += '<span class="mtg-turn-meta">' + _escMtg([marker, providerKind + status + duration].filter(Boolean).join(' · ')) + '</span></div>';
            if (!turn.pending && !isUserTurn && _mtgHasStructuredTurn(turn.structured)) {
                html += _mtgRenderStructuredTurn(turn.structured);
                if (turn.parseError) html += '<div class="mtg-turn-parse">' + _escMtg(_mtgT('meeting_parse_fallback', 'Fallback text retained')) + '</div>';
            } else {
                html += '<div class="mtg-turn-text">' + _escMtg(text) + '</div>';
                if (!turn.pending && !isUserTurn && turn.parseError) {
                    html += '<div class="mtg-turn-parse">' + _escMtg(_mtgT('meeting_parse_fallback', 'Fallback text retained')) + '</div>';
                }
            }
            html += '</div>';
        });
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function _mtgHasStructuredTurn(structured) {
    if (!structured || typeof structured !== 'object') return false;
    return ['position', 'reasoning', 'suggestedNextStep', 'confidence'].some(function(key) {
        return !!String(structured[key] || '').trim();
    }) || ['disagreements', 'questions'].some(function(key) {
        return Array.isArray(structured[key]) && structured[key].length > 0;
    });
}

function _mtgStructuredValue(value) {
    if (Array.isArray(value)) return value.filter(function(item) { return String(item || '').trim(); }).join('\n');
    return String(value || '').trim();
}

function _mtgStripJsonFence(text) {
    var raw = String(text || '').trim();
    if (raw.indexOf('```') === 0) {
        var lines = raw.split(/\r?\n/);
        if (lines.length && lines[0].trim().indexOf('```') === 0) lines.shift();
        if (lines.length && lines[lines.length - 1].trim().indexOf('```') === 0) lines.pop();
        raw = lines.join('\n').trim();
    }
    return raw;
}

function _mtgParseJsonObject(text) {
    var raw = _mtgStripJsonFence(text);
    if (!raw) return null;
    try {
        var parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
    } catch (e) {}
    var idx = raw.indexOf('{');
    while (idx >= 0) {
        var end = raw.lastIndexOf('}');
        while (end > idx) {
            try {
                var obj = JSON.parse(raw.slice(idx, end + 1));
                return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : null;
            } catch (e2) {
                end = raw.lastIndexOf('}', end - 1);
            }
        }
        idx = raw.indexOf('{', idx + 1);
    }
    return null;
}

function _mtgNormalizeStructuredContribution(obj) {
    var keyMap = {
        position: 'position',
        reasoning: 'reasoning',
        disagreements: 'disagreements',
        questions: 'questions',
        suggestednextstep: 'suggestedNextStep',
        suggested_next_step: 'suggestedNextStep',
        confidence: 'confidence'
    };
    var structured = {};
    Object.keys(obj || {}).forEach(function(rawKey) {
        var normalized = String(rawKey || '').replace(/[^A-Za-z_]/g, '').toLowerCase();
        var key = keyMap[normalized];
        if (!key) return;
        if (key === 'disagreements' || key === 'questions') {
            var value = obj[rawKey];
            structured[key] = Array.isArray(value) ? value.map(function(item) { return String(item || '').trim(); }).filter(Boolean) : [String(value || '').trim()].filter(Boolean);
        } else {
            structured[key] = String(obj[rawKey] || '').trim();
        }
    });
    if (structured.position || structured.reasoning || structured.suggestedNextStep || structured.confidence || (structured.disagreements || []).length || (structured.questions || []).length) {
        structured.disagreements = structured.disagreements || [];
        structured.questions = structured.questions || [];
        return structured;
    }
    return null;
}

function _mtgParseLabeledContribution(text) {
    var labelMap = {
        position: 'position',
        reasoning: 'reasoning',
        disagreements: 'disagreements',
        questions: 'questions',
        suggestednextstep: 'suggestedNextStep',
        confidence: 'confidence'
    };
    var structured = {};
    var currentKey = '';
    String(text || '').split(/\r?\n/).forEach(function(line) {
        var match = line.match(/^\s*([A-Za-z][A-Za-z ]{1,40}):\s*(.*)$/);
        var mapped = match ? labelMap[String(match[1] || '').replace(/[^A-Za-z]/g, '').toLowerCase()] : '';
        if (mapped) {
            currentKey = mapped;
            if (mapped === 'disagreements' || mapped === 'questions') {
                structured[mapped] = structured[mapped] || [];
                if (String(match[2] || '').trim()) structured[mapped].push(String(match[2] || '').trim());
            } else {
                structured[mapped] = [structured[mapped], String(match[2] || '').trim()].filter(Boolean).join('\n\n');
            }
            return;
        }
        if (!currentKey || !line.trim()) return;
        if (currentKey === 'disagreements' || currentKey === 'questions') {
            structured[currentKey] = structured[currentKey] || [];
            structured[currentKey].push(line.trim().replace(/^[-*]\s*/, ''));
        } else {
            structured[currentKey] = [structured[currentKey], line.trim()].filter(Boolean).join('\n');
        }
    });
    return _mtgNormalizeStructuredContribution(structured);
}

function _mtgRenderContributionText(text) {
    var raw = String(text || '').trim();
    var structured = _mtgNormalizeStructuredContribution(_mtgParseJsonObject(raw)) || _mtgParseLabeledContribution(raw);
    if (structured && _mtgHasStructuredTurn(structured)) return _mtgRenderStructuredTurn(structured);
    return _escMtg(raw);
}

function _mtgRenderStructuredTurn(structured) {
    var fields = [
        ['position', 'meeting_turn_position', 'Position'],
        ['reasoning', 'meeting_turn_reasoning', 'Reasoning'],
        ['disagreements', 'meeting_turn_disagreements', 'Disagreements'],
        ['questions', 'meeting_turn_questions', 'Questions'],
        ['suggestedNextStep', 'meeting_turn_next_step', 'Suggested next step'],
        ['confidence', 'meeting_turn_confidence', 'Confidence']
    ];
    var html = '<div class="mtg-structured-turn">';
    fields.forEach(function(field) {
        var value = _mtgStructuredValue(structured[field[0]]);
        if (!value) return;
        html += '<div class="mtg-structured-field">';
        html += '<div class="mtg-structured-label">' + _escMtg(_mtgT(field[1], field[2])) + '</div>';
        html += '<div class="mtg-structured-value">' + _escMtg(value) + '</div>';
        html += '</div>';
    });
    html += '</div>';
    return html;
}

async function submitMeetingIntervention(meetingId) {
    var textEl = document.getElementById('mtg-intervention-text-' + meetingId);
    var contextEl = document.getElementById('mtg-intervention-context-' + meetingId);
    var err = document.getElementById('mtg-intervention-error-' + meetingId);
    var btn = document.getElementById('mtg-intervention-submit-' + meetingId);
    var text = (textEl && textEl.value || '').trim();
    var context = (contextEl && contextEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (!text && !context) return fail(_mtgT('meeting_intervention_required', 'Enter a message or additional context.'));
    if (err) err.style.display = 'none';
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/intervention', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                context: context,
                actorId: 'user',
                idempotencyKey: 'ui-intervention-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to send intervention');
        if (textEl) textEl.value = '';
        if (contextEl) contextEl.value = '';
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        await _mtgAfterMeetingRefresh();
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitMeetingAgendaChange(meetingId) {
    var agendaEl = document.getElementById('mtg-agenda-text-' + meetingId);
    var reasonEl = document.getElementById('mtg-agenda-reason-' + meetingId);
    var err = document.getElementById('mtg-agenda-error-' + meetingId);
    var btn = document.getElementById('mtg-agenda-submit-' + meetingId);
    var agenda = (agendaEl && agendaEl.value || '').trim();
    var reason = (reasonEl && reasonEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (!agenda) return fail(_mtgT('meeting_agenda_required', 'Enter a new agenda.'));
    if (err) err.style.display = 'none';
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/agenda-change', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agenda: agenda,
                reason: reason,
                actorId: 'user',
                idempotencyKey: 'ui-agenda-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to save agenda');
        if (reasonEl) reasonEl.value = '';
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        await _mtgAfterMeetingRefresh();
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitMeetingTargetedQuestion(meetingId) {
    var targetEl = document.getElementById('mtg-target-participant-' + meetingId);
    var questionEl = document.getElementById('mtg-target-question-' + meetingId);
    var err = document.getElementById('mtg-target-error-' + meetingId);
    var btn = document.getElementById('mtg-target-submit-' + meetingId);
    var target = (targetEl && targetEl.value || '').trim();
    var question = (questionEl && questionEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (!target) return fail(_mtgT('meeting_target_required', 'Select a target participant.'));
    if (!question) return fail(_mtgT('meeting_target_question_required', 'Enter a targeted question.'));
    if (err) err.style.display = 'none';
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/targeted-question', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target: target,
                question: question,
                actorId: 'user',
                idempotencyKey: 'ui-targeted-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to ask targeted question');
        if (questionEl) questionEl.value = '';
        if (data.questionEvent) _mtgApplyLiveEvent(meetingId, data.questionEvent);
        if (data.pending) _mtgApplyLiveEvent(meetingId, data.pending);
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        await _mtgAfterMeetingRefresh();
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitMeetingArbitration(meetingId, action) {
    var decisionEl = document.getElementById('mtg-arb-decision-' + meetingId);
    var rationaleEl = document.getElementById('mtg-arb-rationale-' + meetingId);
    var err = document.getElementById('mtg-arb-error-' + meetingId);
    var decision = (decisionEl && decisionEl.value || '').trim();
    var rationale = (rationaleEl && rationaleEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (action === 'decide' && !decision) return fail(_mtgT('meeting_arbitration_decision_required', 'Enter a decision.'));
    if (err) err.style.display = 'none';
    _mtgSetDecisionControlsDisabled(meetingId, true);
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/arbitration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: action,
                decision: decision,
                rationale: rationale,
                actorId: 'user',
                idempotencyKey: 'ui-arbitration-' + action + '-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to submit arbitration');
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        var latest = data;
        if (action === 'continue_discussion' && data.meeting && data.meeting.stage !== 'completed') {
            latest = await _mtgRunMeeting(meetingId, { action: 'continue' });
        }
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(latest && latest.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        fail(e.message || String(e));
        await _mtgAfterMeetingRefresh();
        _mtgSetDecisionControlsDisabled(meetingId, false);
    }
}

async function submitModeratorTakeover(meetingId, action) {
    var summaryEl = document.getElementById('mtg-takeover-summary-' + meetingId);
    var decisionEl = document.getElementById('mtg-takeover-decision-' + meetingId);
    var replacementEl = document.getElementById('mtg-replacement-moderator-' + meetingId);
    var err = document.getElementById('mtg-takeover-error-' + meetingId);
    var summary = (summaryEl && summaryEl.value || '').trim();
    var decision = (decisionEl && decisionEl.value || '').trim();
    var replacement = (replacementEl && replacementEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (action === 'user_takeover' && !summary) return fail(_mtgT('meeting_takeover_summary_required', 'Enter a user summary.'));
    if (err) err.style.display = 'none';
    _mtgSetDecisionControlsDisabled(meetingId, true);
    ['mtg-takeover-submit-', 'mtg-replacement-submit-', 'mtg-takeover-summary-', 'mtg-takeover-decision-', 'mtg-replacement-moderator-'].forEach(function(prefix) {
        var el = document.getElementById(prefix + meetingId);
        if (el) el.disabled = true;
    });
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/moderator-takeover', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: action,
                summary: summary,
                decision: decision,
                moderator: replacement,
                actorId: 'user',
                idempotencyKey: 'ui-moderator-takeover-' + action + '-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to submit moderator takeover');
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        if (data.takeoverEvent) _mtgApplyLiveEvent(meetingId, data.takeoverEvent);
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(data.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        fail(e.message || String(e));
        _mtgSetDecisionControlsDisabled(meetingId, false);
        ['mtg-takeover-submit-', 'mtg-replacement-submit-', 'mtg-takeover-summary-', 'mtg-takeover-decision-', 'mtg-replacement-moderator-'].forEach(function(prefix) {
            var el = document.getElementById(prefix + meetingId);
            if (el) el.disabled = false;
        });
    }
}

async function continueMeetingDecisionWindow(meetingId) {
    var btn = document.getElementById('mtg-continue-' + meetingId);
    _mtgSetDecisionControlsDisabled(meetingId, true);
    try {
        var ran = await _mtgRunMeeting(meetingId, { action: 'continue' });
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(ran && ran.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
        _mtgSetDecisionControlsDisabled(meetingId, false);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function _mtgRunMeeting(meetingId, body) {
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Failed to run meeting');
    return data;
}

async function startExecutableMeeting(meetingId) {
    var btn = document.getElementById('mtg-start-' + meetingId);
    if (btn) {
        btn.disabled = true;
        btn.textContent = _mtgT('meeting_starting', 'Starting...');
    }
    try {
        var ran = await _mtgRunMeeting(meetingId, { action: 'start' });
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(ran && ran.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        alert(_mtgT('meeting_start_failed', 'Failed to start meeting') + ': ' + (e.message || String(e)));
        if (btn) {
            btn.disabled = false;
            btn.textContent = '▶ ' + _mtgT('meeting_start_existing', 'Start meeting');
        }
    }
}

function updateMeetingLabels() {
    var btn = document.getElementById('new-mtg-btn-label');
    if (btn) btn.textContent = _mtgT('new_meeting', 'New Meeting');
    var search = document.getElementById('mtg-history-search');
    if (search) search.placeholder = _mtgT('meeting_history_search_placeholder', 'Search meeting history');
}

function _mtgAgentKey(agent) {
    return agent.key || agent.statusKey || agent.agentId || agent.id || '';
}

function _mtgNormalizeBranchToken(value) {
    return String(value || '').trim().toLowerCase();
}

function _mtgParticipantBranchId(agent) {
    var rawBranch = (agent && agent.branch) || '';
    var normalized = _mtgNormalizeBranchToken(rawBranch);
    var branches = getBranchList();
    var matched = branches.find(function(b) {
        return b.id === rawBranch ||
            _mtgNormalizeBranchToken(b.id) === normalized ||
            _mtgNormalizeBranchToken(b.name) === normalized;
    });
    if (matched) return matched.id;
    var unassignedNames = [
        'unassigned',
        _mtgT('branch_unassigned', 'Unassigned')
    ].map(_mtgNormalizeBranchToken);
    if (!normalized || unassignedNames.indexOf(normalized) >= 0) return 'UNASSIGNED';
    if (agent && agent.providerKind) {
        var providerMatched = branches.find(function(b) {
            return _mtgNormalizeBranchToken(b.name) === _mtgNormalizeBranchToken(agent.providerKind) ||
                _mtgNormalizeBranchToken(b.id) === _mtgNormalizeBranchToken(agent.providerKind);
        });
        if (providerMatched) return providerMatched.id;
    }
    return 'UNASSIGNED';
}

function _mtgBranchDisplayLabel(branch) {
    if (!branch) return _mtgT('branch_unassigned', 'Unassigned');
    var name = branch.id === 'UNASSIGNED' ? _mtgT('branch_unassigned', 'Unassigned') : (branch.name || branch.id);
    if (typeof name === 'string' && name.indexOf('branch_') === 0) name = _mtgT(name, branch.id || name);
    return (branch.emoji || '🏢') + ' ' + name;
}

function _mtgIsAssignableMeetingAgent(agent) {
    return !!(agent && agent.assignable !== false && agent.systemRole !== 'archive_manager' && !agent.archiveManager);
}

function _mtgMeetingAgents() {
    return (_mtgAgents || []).filter(_mtgIsAssignableMeetingAgent);
}

function _mtgAssignableParticipantSet() {
    return new Set(_mtgMeetingAgents().map(function(agent) { return _mtgAgentKey(agent); }));
}

function _mtgFilterAssignableParticipants(participants) {
    var allowed = _mtgAssignableParticipantSet();
    return (participants || []).filter(function(key) { return allowed.has(key); });
}

function _mtgParticipantSelectorHtml(opts) {
    opts = opts || {};
    var participantClass = opts.participantClass || '';
    var branchClass = opts.branchClass || '';
    var branchAttrs = opts.branchAttrs || '';
    var participantAttrs = opts.participantAttrs || '';
    var allowed = _mtgAssignableParticipantSet();
    var selected = new Set((opts.selected || []).map(function(item) { return String(item); }).filter(function(key) { return allowed.has(key); }));
    var byBranch = {};
    getBranchList().forEach(function(branch) { byBranch[branch.id] = []; });
    _mtgMeetingAgents().forEach(function(agent) {
        var branchId = _mtgParticipantBranchId(agent);
        if (!byBranch[branchId]) byBranch[branchId] = [];
        byBranch[branchId].push(agent);
    });
    var branchHtml = getBranchList().map(function(branch) {
        var branchAgents = byBranch[branch.id] || [];
        if (!branchAgents.length) return '';
        return '<label class="mtg-label" style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;margin-top:4px;">' +
            '<input type="checkbox" class="' + _escMtg(branchClass) + '" data-branch-id="' + _escMtg(branch.id) + '"' + branchAttrs + '> ' +
            _escMtg(_mtgBranchDisplayLabel(branch)) +
            '</label>';
    }).join('');
    var agentHtml = getBranchList().map(function(branch) {
        var branchAgents = byBranch[branch.id] || [];
        if (!branchAgents.length) return '';
        var items = branchAgents.map(function(agent) {
            var key = _mtgAgentKey(agent);
            var checked = selected.has(key) ? ' checked' : '';
            return '<label class="mtg-label" style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;margin-top:4px;">' +
                '<input type="checkbox" class="' + _escMtg(participantClass) + '" data-branch-id="' + _escMtg(branch.id) + '" value="' + _escMtg(key) + '"' + checked + participantAttrs + '> ' +
                _escMtg((agent.emoji || '🤖') + ' ' + (agent.name || key)) +
                '</label>';
        }).join('');
        return '<div class="mtg-participant-branch-group" data-branch-id="' + _escMtg(branch.id) + '" style="margin-top:6px;">' +
            '<div class="mtg-section-text" style="font-size:10px;color:#aaa;">' + _escMtg(_mtgBranchDisplayLabel(branch)) + '</div>' +
            '<div>' + items + '</div>' +
            '</div>';
    }).join('');
    return '<div class="mtg-participant-selector">' +
        '<div class="mtg-section-text" style="font-size:10px;color:#aaa;margin:2px 0 4px;">' + _escMtg(_mtgT('meeting_branch_quick_select', 'Quick select by branch')) + '</div>' +
        '<div class="mtg-branch-selectors">' + branchHtml + '</div>' +
        '<div class="mtg-section-text" style="font-size:10px;color:#777;margin-top:4px;">' + _escMtg(_mtgT('meeting_branch_quick_select_hint', 'Choose a branch, then manually adjust individual agents.')) + '</div>' +
        '<div class="mtg-agent-selectors" style="margin-top:6px;">' + agentHtml + '</div>' +
        '</div>';
}

function _mtgSelectedParticipantValues(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector + ':checked')).map(function(el) { return el.value; });
}

function _mtgApplyBranchSelection(branchSelector, participantSelector, branchId, checked) {
    Array.prototype.slice.call(document.querySelectorAll(participantSelector + '[data-branch-id="' + branchId + '"]')).forEach(function(el) {
        el.checked = checked;
    });
}

function _mtgSyncBranchSelectionState(branchSelector, participantSelector) {
    Array.prototype.slice.call(document.querySelectorAll(branchSelector)).forEach(function(branchEl) {
        var branchId = branchEl.getAttribute('data-branch-id') || '';
        var items = Array.prototype.slice.call(document.querySelectorAll(participantSelector + '[data-branch-id="' + branchId + '"]'));
        var checkedCount = items.filter(function(el) { return el.checked; }).length;
        branchEl.checked = items.length > 0 && checkedCount === items.length;
        branchEl.indeterminate = checkedCount > 0 && checkedCount < items.length;
    });
}

function _mtgUpdateModeratorOptions(selectId, participantSelector, preferredModerator) {
    var select = document.getElementById(selectId);
    if (!select) return;
    var previous = select.value || preferredModerator || '';
    var selected = _mtgSelectedParticipantValues(participantSelector);
    var selectedSet = new Set(selected);
    var target = selectedSet.has(previous) ? previous : (selected[0] || '');
    select.innerHTML = selected.map(function(key) {
        var info = _mtgAgentMap[key] || { name: key, emoji: '🤖' };
        return '<option value="' + _escMtg(key) + '"' + (key === target ? ' selected' : '') + '>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || key)) + '</option>';
    }).join('');
    if (target) select.value = target;
}

function toggleNewMeetingForm(forceOpen) {
    var modal = document.getElementById('newMeetingModal');
    var panel = document.getElementById('new-meeting-panel');
    if (!modal || !panel) return;
    var shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : modal.classList.contains('hidden');
    modal.classList.toggle('modal-above-projects', shouldOpen);
    modal.classList.toggle('hidden', !shouldOpen);
    if (shouldOpen) {
        renderNewMeetingForm();
        var title = document.getElementById('new-meeting-modal-title');
        if (title) title.textContent = _mtgT('new_meeting', 'New Meeting');
        setTimeout(function() {
            var topic = document.getElementById('new-mtg-topic');
            if (topic) topic.focus();
        }, 0);
    } else {
        panel.innerHTML = '';
        modal.classList.remove('modal-above-projects');
    }
}

function renderNewMeetingForm() {
    var panel = document.getElementById('new-meeting-panel');
    if (!panel) return;
    var agentOptions = _mtgParticipantSelectorHtml({
        selected: [],
        participantClass: 'new-mtg-participant',
        branchClass: 'new-mtg-branch',
        participantAttrs: ' onchange="updateNewMeetingModeratorOptions()"',
        branchAttrs: ' onchange="toggleNewMeetingBranch(this)"'
    });
    panel.innerHTML =
        '<div class="mtg-section-title">' + _escMtg(_mtgT('new_meeting', 'New Meeting')) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_topic', 'Topic')) + '</label>' +
        '<input id="new-mtg-topic" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_topic_placeholder', 'What should the agents discuss?')) + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_purpose', 'Purpose')) + '</label>' +
        '<input id="new-mtg-purpose" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_purpose_placeholder', 'What result should this meeting produce?')) + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_type', 'Meeting type')) + '</label>' +
        '<select id="new-mtg-type" class="skl-input"><option value="information">' + _escMtg(_mtgT('meeting_type_information', 'Information gathering')) + '</option><option value="discussion" selected>' + _escMtg(_mtgT('meeting_type_discussion', 'Decision discussion')) + '</option><option value="task">' + _escMtg(_mtgT('meeting_type_task', 'Task collaboration')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_project', 'Project')) + '</label>' +
        _mtgProjectSelectHtml('new-mtg-project', '', true) +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_participants', 'Participants')) + '</label>' +
        '<div id="new-mtg-participants">' + agentOptions + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + '</label>' +
        '<select id="new-mtg-moderator" class="skl-input"></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_context_mode', 'Context mode')) + '</label>' +
        '<select id="new-mtg-context-mode" class="skl-input"><option value="incremental" selected>' + _escMtg(_mtgT('meeting_context_incremental', 'Incremental')) + '</option><option value="summary">' + _escMtg(_mtgT('meeting_context_summary', 'Summary')) + '</option><option value="full">' + _escMtg(_mtgT('meeting_context_full', 'Full')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_resolution_policy', 'Resolution policy')) + '</label>' +
        '<select id="new-mtg-resolution-policy" class="skl-input"><option value="user_decision" selected>' + _escMtg(_mtgT('meeting_resolution_user_decision', 'User decides disagreements')) + '</option><option value="moderator_decision">' + _escMtg(_mtgT('meeting_resolution_moderator_decision', 'Moderator decides and closes')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_max_rounds', 'Max discussion rounds')) + '</label>' +
        '<input id="new-mtg-max-rounds" class="skl-input" type="number" min="1" max="5" value="1">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_initial_context', 'Initial context')) + '</label>' +
        '<textarea id="new-mtg-context" class="mtg-textarea" rows="4" placeholder="' + _escMtg(_mtgT('meeting_initial_context_placeholder', 'User-confirmed context for all agents')) + '"></textarea>' +
        '<div id="new-mtg-error" style="color:#e74c3c;font-size:10px;margin:6px 0;display:none;"></div>' +
        '<button id="new-mtg-submit" class="mtg-btn mtg-btn-end" onclick="submitNewMeeting()">▶ ' + _escMtg(_mtgT('meeting_start', 'Start meeting')) + '</button>' +
        '<button class="mtg-btn" onclick="toggleNewMeetingForm(false)">' + _escMtg(_mtgT('cancel', 'Cancel')) + '</button>';
    updateNewMeetingModeratorOptions();
}

function toggleNewMeetingBranch(branchEl) {
    var branchId = branchEl.getAttribute('data-branch-id') || '';
    _mtgApplyBranchSelection('.new-mtg-branch', '.new-mtg-participant', branchId, branchEl.checked);
    updateNewMeetingModeratorOptions();
}

function updateNewMeetingModeratorOptions() {
    _mtgSyncBranchSelectionState('.new-mtg-branch', '.new-mtg-participant');
    _mtgUpdateModeratorOptions('new-mtg-moderator', '.new-mtg-participant', '');
}

async function submitNewMeeting() {
    var err = document.getElementById('new-mtg-error');
    var btn = document.getElementById('new-mtg-submit');
    function fail(msg) {
        if (err) { err.textContent = msg; err.style.display = 'block'; }
    }
    var participants = _mtgFilterAssignableParticipants(Array.prototype.slice.call(document.querySelectorAll('.new-mtg-participant:checked')).map(function(el) { return el.value; }));
    var topic = (document.getElementById('new-mtg-topic') || {}).value || '';
    var moderator = (document.getElementById('new-mtg-moderator') || {}).value || '';
    if (!topic.trim()) return fail(_mtgT('meeting_error_topic_required', 'Topic is required.'));
    if (participants.length < 2) return fail(_mtgT('meeting_error_participants_required', 'Select at least two participants.'));
    if (!moderator) return fail(_mtgT('meeting_error_moderator_required', 'Select a moderator.'));
    if (btn) { btn.disabled = true; btn.textContent = _mtgT('meeting_running', 'Running...'); }
    if (err) err.style.display = 'none';
    try {
        var createRes = await fetch('/api/meetings/executable/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: topic.trim(),
                purpose: ((document.getElementById('new-mtg-purpose') || {}).value || '').trim(),
                meetingType: (document.getElementById('new-mtg-type') || {}).value || 'discussion',
                projectId: (document.getElementById('new-mtg-project') || {}).value || '',
                participants: participants,
                moderator: moderator,
                contextMode: (document.getElementById('new-mtg-context-mode') || {}).value || 'incremental',
                resolutionPolicy: (document.getElementById('new-mtg-resolution-policy') || {}).value || 'user_decision',
                maxRounds: Number((document.getElementById('new-mtg-max-rounds') || {}).value || 1),
                context: ((document.getElementById('new-mtg-context') || {}).value || '').trim(),
                allowConflicts: true,
                idempotencyKey: 'ui-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var created = await createRes.json();
        if (!createRes.ok || created.error) throw new Error(created.error || 'Failed to create meeting');
        if (created.meeting && created.meeting.stage === 'conflict') {
            toggleNewMeetingForm(false);
            await _mtgAfterMeetingRefresh();
            switchMtgTab('active');
            openMeetingDetailModal(created.meeting.id);
            return;
        }
        var ran = await _mtgRunMeeting(created.meeting.id);
        toggleNewMeetingForm(false);
        await _mtgAfterMeetingRefresh();
        switchMtgTab(_mtgMeetingCompleted(ran && ran.meeting) ? 'completed' : 'active');
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '▶ ' + _mtgT('meeting_start', 'Start meeting'); }
    }
}

function _mtgActionText(action) {
    if (!action) return '';
    if (typeof action === 'string') return action;
    if (typeof action === 'object') {
        var owner = action.owner || action.agent || action.assignee || '';
        var item = action.item || action.text || action.task || action.action || action.summary || '';
        if (owner && item) return owner + ': ' + item;
        if (item) return item;
        if (owner) return owner;
        try { return JSON.stringify(action); } catch (e) { return String(action); }
    }
    return String(action);
}

function mtgExpandAll() {
    (_mtgData.active || []).concat(_mtgData.history || []).forEach(function(m) { if (m.id) _mtgOpenCards[m.id] = true; });
    document.querySelectorAll('.mtg-card-body').forEach(function(el) { el.classList.add('open'); });
    document.querySelectorAll('.mtg-card-toggle').forEach(function(el) { el.classList.add('open'); });
}

function mtgCollapseAll() {
    (_mtgData.active || []).concat(_mtgData.history || []).forEach(function(m) { if (m.id) delete _mtgOpenCards[m.id]; });
    document.querySelectorAll('.mtg-card-body').forEach(function(el) { el.classList.remove('open'); });
    document.querySelectorAll('.mtg-card-toggle').forEach(function(el) { el.classList.remove('open'); });
}

function toggleMtgCard(meetingId) {
    var body = document.getElementById('mtg-body-' + meetingId);
    var toggle = document.getElementById('mtg-toggle-' + meetingId);
    if (body) {
        body.classList.toggle('open');
        _mtgOpenCards[meetingId] = body.classList.contains('open');
        if (toggle) toggle.classList.toggle('open');
    }
}

function toggleMtgResponse(respId, btn) {
    var el = document.getElementById(respId);
    if (!el) return;
    el.classList.toggle('expanded');
    if (el.classList.contains('expanded')) {
        btn.textContent = _tr('collapse');
    } else {
        btn.textContent = _tr('expand');
    }
}

function _mtgFindMeeting(meetingId) {
    return (_mtgData.active || []).concat(_mtgData.history || []).find(function(m) {
        return m && m.id === meetingId;
    });
}

function _mtgFindMeetingByRequestId(requestId) {
    if (!requestId) return null;
    return (_mtgData.active || []).concat(_mtgData.history || []).find(function(m) {
        var source = (m && m.source) || {};
        return source.meetingRequestId === requestId;
    }) || null;
}

function _mtgMeetingIdFromRequest(req) {
    if (!req) return '';
    var conversion = req.conversion && typeof req.conversion === 'object' ? req.conversion : {};
    var taskBlocker = req.taskBlocker && typeof req.taskBlocker === 'object' ? req.taskBlocker : {};
    return String(conversion.meetingId || taskBlocker.meetingId || '').trim();
}

function _mtgUpsertRequest(req) {
    if (!req || !req.id) return null;
    var requests = Array.isArray(_mtgData.requests) ? _mtgData.requests : [];
    var idx = requests.findIndex(function(item) { return item && item.id === req.id; });
    if (idx >= 0) requests[idx] = req;
    else requests.unshift(req);
    _mtgData.requests = _mtgSortRequestsByStatusThenTime(requests);
    return req;
}

async function _mtgFetchRequestDetail(requestId) {
    if (!requestId) return null;
    try {
        var res = await fetch('/api/meetings/requests/' + encodeURIComponent(requestId));
        var data = await res.json();
        if (!res.ok || data.error || !data.request) return null;
        return _mtgUpsertRequest(data.request);
    } catch (e) {
        console.warn('[meetings] request detail fetch error:', e);
        return null;
    }
}

function openMeetingDetailModal(meetingId) {
    var meeting = _mtgFindMeeting(meetingId);
    if (meeting) {
        openMeetingDetailRecord(meeting, meetingId);
        return;
    }
    openMeetingDetailPlaceholder(meetingId, _mtgT('loading', 'Loading...'));
    _mtgFetchMeetingDetail(meetingId);
}

function openMeetingDetailRecord(meeting, fallbackMeetingId) {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    var title = document.getElementById('meeting-detail-title');
    if (!meeting || !modal || !body) return;
    _mtgDetailMeetingId = meeting.id || fallbackMeetingId || '';
    if (title) title.textContent = meeting.topic || _tr('untitled_meeting');
    body.innerHTML = _mtgRenderMeetingDetail(_mtgMergeLiveMeeting(meeting));
    modal.classList.remove('hidden');
}

function openMeetingDetailPlaceholder(meetingId, message) {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    var title = document.getElementById('meeting-detail-title');
    if (!meetingId || !modal || !body) return;
    _mtgDetailMeetingId = meetingId;
    if (title) title.textContent = _mtgT('meeting_detail_title', 'Meeting Detail');
    body.innerHTML = '<div class="mtg-empty">' + _escMtg(message || '') + '</div>';
    modal.classList.remove('hidden');
}

async function _mtgFetchMeetingDetail(meetingId) {
    if (!meetingId) return;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId));
        var data = await res.json();
        if (!res.ok || data.error || !data.meeting) {
            throw new Error(data.error || _mtgT('meeting_not_found', 'Meeting not found'));
        }
        if (Array.isArray(data.events)) {
            _mtgLiveEvents[meetingId] = _mtgLiveStateFromMeeting(data.meeting);
            data.events.forEach(function(event) { _mtgApplyLiveEvent(meetingId, event); });
        }
        openMeetingDetailRecord(data.meeting, meetingId);
    } catch (e) {
        var body = document.getElementById('meeting-detail-body');
        if (_mtgDetailMeetingId === meetingId && body) {
            body.innerHTML = '<div class="mtg-inline-error" style="display:block">' + _escMtg(e.message || String(e)) + '</div>';
        }
    }
}

function closeMeetingDetailModal() {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    _mtgDetailMeetingId = '';
    if (modal) modal.classList.add('hidden');
    if (body) body.innerHTML = '';
}

function _mtgRefreshDetailModal() {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    var title = document.getElementById('meeting-detail-title');
    if (!modal || modal.classList.contains('hidden') || !body || !_mtgDetailMeetingId) return;
    var meeting = _mtgFindMeeting(_mtgDetailMeetingId);
    if (!meeting) {
        closeMeetingDetailModal();
        return;
    }
    meeting = _mtgMergeLiveMeeting(meeting);
    if (title) title.textContent = meeting.topic || _tr('untitled_meeting');
    body.innerHTML = _mtgRenderMeetingDetail(meeting);
}

async function _mtgAfterMeetingRefresh() {
    await _mtgRefresh();
    _mtgRefreshDetailModal();
}

function _mtgRenderMeetingDetail(m) {
    var participants = m.participants || m.agents || [];
    var isActive = m.status === 'active';
    var html = '';
    if (m.purpose && m.purpose !== m.topic) {
        html += '<div class="mtg-card-purpose mtg-detail-purpose">' + _escMtg(m.purpose) + '</div>';
    }
    var orgInfo = _mtgAgentMap[m.organizer] || { emoji: '🤖', name: m.organizer || 'Unknown' };
    var leftMeta = [
        '👑 ' + orgInfo.emoji + ' ' + _escMtg(orgInfo.name),
        '🪪 ' + _escMtg(_mtgCreatedByLabel(m)),
        '👥 ' + _escMtg(_tr('participants_count', { count: participants.length }))
    ];
    var rightMeta = [];
    if (m.executableMeeting) {
        rightMeta.push('⚙️ ' + _escMtg(_mtgT('meeting_stage', 'Stage')) + ': ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || m.status || '')));
        if (m.moderator) rightMeta.push('🎙️ ' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + ': ' + _escMtg(m.moderator));
        if (m.contextMode) rightMeta.push('🧩 ' + _escMtg(_mtgT('meeting_context_mode', 'Context')) + ': ' + _escMtg(m.contextMode));
        if (m.resolutionPolicy) rightMeta.push('⚖️ ' + _escMtg(_mtgT('meeting_resolution_policy', 'Resolution policy')) + ': ' + _escMtg(_mtgResolutionPolicyLabel(m.resolutionPolicy)));
        var preparingTimeoutLabel = _mtgPreparingTimeoutLabel(m);
        if (preparingTimeoutLabel) rightMeta.push('⏱️ ' + _escMtg(preparingTimeoutLabel));
        if (m.urgency) rightMeta.push('🚦 ' + _escMtg(_mtgUrgencyLabel(m.urgency)));
        rightMeta.push(_mtgProjectMetaLabel(m));
    }
    var ts = _mtgMeetingTime(m);
    if (ts) rightMeta.push('🕐 ' + new Date(ts).toLocaleString());
    html += _mtgRenderMetaColumns(leftMeta, rightMeta);

    html += '<div class="mtg-participants">';
    participants.forEach(function(pKey) {
        var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
        html += '<div class="mtg-participant"><span class="mtg-participant-emoji">' + info.emoji + '</span><div class="mtg-participant-info">';
        html += '<div class="mtg-participant-name">' + _escMtg(info.name) + '</div>';
        if (info.role) html += '<div class="mtg-participant-role">' + _escMtg(info.role) + '</div>';
        html += '</div></div>';
    });
    html += '</div>';

    html += _mtgRenderResultSummary(m);
    html += _mtgRenderActionItemDrafts(m);

    if (isActive && m.executableMeeting) {
        if ((m.executionStage || '') === 'conflict' || (Array.isArray(m.conflicts) && m.conflicts.length)) {
            html += _mtgRenderConflictPanel(m);
        }
        if ((m.executionStage || '') === 'awaiting_user_decision') {
            html += _mtgRenderDecisionWindowControls(m);
        }
        if (m.moderatorFailure && m.moderatorFailure.reason === 'moderator_failed') {
            html += _mtgRenderModeratorTakeoverControls(m);
        }
        html += _mtgRenderInterventionForm(m);
    }

    if (m.executableMeeting && ((Array.isArray(m.transcript) && m.transcript.length) || (Array.isArray(m.pendingCalls) && m.pendingCalls.length))) {
        html += _mtgRenderTranscript(m);
    }

    var responses = m.responses || {};
    if (Object.keys(responses).length > 0) {
        html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('agent_responses')) + '</div><div class="mtg-responses">';
        participants.forEach(function(pKey) {
            var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
            var resp = responses[pKey] || '';
            html += '<div class="mtg-response"><div class="mtg-response-header"><span class="mtg-response-emoji">' + info.emoji + '</span><span class="mtg-response-name">' + _escMtg(info.name) + '</span></div>';
            html += '<div class="mtg-response-text expanded">' + _escMtg(resp || _tr('no_response_recorded')) + '</div></div>';
        });
        html += '</div></div>';
    }

    if (m.executableMeeting && m.result && m.result.contributions) {
        html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_contributions', 'Contributions')) + '</div>';
        Object.keys(m.result.contributions).forEach(function(agentId) {
            var info = _mtgAgentMap[agentId] || { emoji: '🤖', name: agentId };
            html += '<div class="mtg-response"><div class="mtg-response-header"><span class="mtg-response-emoji">' + info.emoji + '</span><span class="mtg-response-name">' + _escMtg(info.name) + '</span></div>';
            html += '<div class="mtg-response-text expanded">' + _mtgRenderContributionText(m.result.contributions[agentId] || '') + '</div></div>';
        });
        html += '</div>';
    }

    if (m.endedBy) {
        var endInfo = _mtgAgentMap[m.endedBy] || { emoji: '🤖', name: m.endedBy };
        html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('ended_by')) + '</div><div class="mtg-section-text">' + endInfo.emoji + ' ' + _escMtg(endInfo.name) + '</div></div>';
    }
    if (isActive) {
        html += '<div class="mtg-actions-bar mtg-detail-actions">';
        if (m.executableMeeting) {
            var stage = m.executionStage || '';
            if (stage === 'preparing') {
                html += '<button id="mtg-start-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="startExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_start_existing', 'Start meeting')) + '</button>';
            } else if (stage === 'conflict') {
                html += '<button id="mtg-refresh-conflict-' + _escMtg(m.id) + '" class="mtg-btn" onclick="refreshMeetingConflicts(\'' + _escMtg(m.id) + '\')">' + _escMtg(_mtgT('meeting_conflict_refresh', 'Recheck conflicts')) + '</button>';
            } else if (stage === 'paused') {
                html += '<button id="mtg-resume-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="resumeExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_resume', 'Resume')) + '</button>';
            } else {
                html += '<button id="mtg-pause-' + _escMtg(m.id) + '" class="mtg-btn" onclick="pauseExecutableMeeting(\'' + _escMtg(m.id) + '\')">⏸ ' + _escMtg(_mtgT('meeting_pause', 'Pause')) + '</button>';
                html += '<button id="mtg-ai-end-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="endExecutableMeetingWithAI(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_mtgT('meeting_ai_end', 'Ask moderator to end')) + '</button>';
            }
            html += '<button id="mtg-cancel-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-delete" onclick="cancelExecutableMeeting(\'' + _escMtg(m.id) + '\')">✕ ' + _escMtg(_mtgT('meeting_cancel', 'Cancel')) + '</button>';
        } else {
            html += '<button class="mtg-btn mtg-btn-end" onclick="openEndMeetingForm(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_tr('end_meeting')) + '</button>';
        }
        html += '</div>';
    }
    return html;
}

function _mtgActionStatusLabel(status) {
    var map = {
        draft: 'meeting_action_status_draft',
        confirmed: 'meeting_action_status_confirmed',
        rejected: 'meeting_action_status_rejected',
        kept_as_meeting_item: 'meeting_action_status_kept'
    };
    return _mtgT(map[status] || 'meeting_action_status_draft', status || 'draft');
}

function _mtgRenderActionItemDrafts(m) {
    var drafts = Array.isArray(m.actionItemDrafts) ? m.actionItemDrafts : [];
    if (!drafts.length && m.result && Array.isArray(m.result.actionItems) && m.result.actionItems.length) {
        drafts = m.result.actionItems.map(function(item, idx) {
            return { id: 'ai-' + (idx + 1), title: _mtgActionText(item), status: 'draft', targetProjectId: m.projectId || '' };
        });
    }
    if (!drafts.length) return '';
    var html = '<div class="mtg-section mtg-action-drafts"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_action_drafts', 'Action item drafts')) + '</div>';
    html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_action_drafts_hint', 'Confirming adds the item to the source task. Drafts do not execute automatically.')) + '</div>';
    drafts.forEach(function(d) {
        var id = _escMtg(d.id || '');
        var formId = 'mtg-action-form-' + _escMtg(m.id) + '-' + id;
        var projectSelectId = 'mtg-action-project-' + _escMtg(m.id) + '-' + id;
        html += '<div class="mtg-action-draft" data-action-item-id="' + id + '">';
        html += '<div class="mtg-action-draft-title">' + _escMtg(d.title || _mtgT('meeting_action_untitled', 'Untitled action item')) + '</div>';
        if (d.description || d.sourceText) html += '<div class="mtg-section-text">' + _escMtg(d.description || d.sourceText || '') + '</div>';
        html += '<div class="mtg-action-draft-row">';
        html += '<span class="mtg-badge mtg-badge-kind">' + _escMtg(_mtgActionStatusLabel(d.status)) + '</span>';
        html += '<span class="mtg-action-draft-meta">' + _escMtg(_mtgT('meeting_action_owner', 'Owner')) + ': ' + _escMtg(d.assignee || d.suggestedOwner || _mtgT('meeting_unknown', 'unknown')) + ' · ' + _escMtg(_mtgT('meeting_project', 'Project')) + ': ' + _escMtg(_mtgProjectName(d.targetProjectId || m.projectId) || _mtgT('meeting_project_none', 'No project')) + '</span>';
        if (d.status === 'confirmed' && d.taskId) {
            html += '<div class="mtg-action-draft-actions"><button class="mtg-btn mtg-btn-end" onclick="openMeetingTaskLink(\'' + _escMtg(d.targetProjectId || m.projectId) + '\',\'' + _escMtg(d.sourceTaskId || d.taskId) + '\')">' + _escMtg(_mtgT('meeting_action_open_task', 'Open source task')) + '</button></div>';
        } else if (d.status !== 'rejected' && d.status !== 'kept_as_meeting_item') {
            html += '<div class="mtg-action-draft-actions">';
            html += '<button class="mtg-btn" onclick="toggleMeetingActionItemEditor(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_edit', 'Edit')) + '</button>';
            html += '<button class="mtg-btn mtg-btn-end" onclick="confirmMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_confirm_task', 'Add to source task')) + '</button>';
            html += '<button class="mtg-btn" onclick="keepMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_keep', 'Keep only')) + '</button>';
            html += '<button class="mtg-btn mtg-btn-delete" onclick="rejectMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_reject', 'Reject')) + '</button>';
            html += '</div>';
            html += '<div id="' + formId + '" class="mtg-action-form hidden">';
            html += '<div class="mtg-field"><label class="mtg-label">' + _escMtg(_mtgT('meeting_action_title', 'Task title')) + '</label>';
            html += '<input id="mtg-action-title-' + _escMtg(m.id) + '-' + id + '" class="skl-input" type="text" value="' + _escMtg(d.title || '') + '">';
            html += '</div>';
            html += '<div class="mtg-field"><label class="mtg-label">' + _escMtg(_mtgT('meeting_action_description', 'Description')) + '</label>';
            html += '<textarea id="mtg-action-desc-' + _escMtg(m.id) + '-' + id + '" class="mtg-textarea" rows="3">' + _escMtg(d.description || '') + '</textarea>';
            html += '</div>';
            html += '<div class="mtg-field"><label class="mtg-label">' + _escMtg(_mtgT('meeting_project', 'Project')) + '</label>';
            html += _mtgProjectSelectHtml(projectSelectId, d.targetProjectId || m.projectId || '', true);
            html += '</div>';
            html += '<div id="mtg-action-error-' + _escMtg(m.id) + '-' + id + '" class="mtg-inline-error"></div>';
            html += '<div class="mtg-actions-bar">';
            html += '<button class="mtg-btn" onclick="updateMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_save_draft', 'Save draft')) + '</button>';
            html += '</div>';
            html += '</div>';
        }
        html += '</div></div>';
    });
    html += '</div>';
    return html;
}

function toggleMeetingActionItemEditor(meetingId, actionItemId) {
    var form = document.getElementById('mtg-action-form-' + meetingId + '-' + actionItemId);
    if (form) form.classList.toggle('hidden');
}

function _mtgActionInput(meetingId, actionItemId, suffix) {
    return document.getElementById('mtg-action-' + suffix + '-' + meetingId + '-' + actionItemId);
}

function _mtgActionError(meetingId, actionItemId, msg) {
    var el = document.getElementById('mtg-action-error-' + meetingId + '-' + actionItemId);
    if (el) {
        el.textContent = msg || '';
        el.style.display = msg ? 'block' : 'none';
    }
}

async function _mtgActionItemRequest(meetingId, actionItemId, body) {
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/action-items/' + encodeURIComponent(actionItemId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ idempotencyKey: body.action + '-' + Date.now() + '-' + Math.random().toString(16).slice(2) }, body))
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Action item update failed');
    await _mtgAfterMeetingRefresh();
    return data;
}

async function updateMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, {
            action: 'update',
            title: (_mtgActionInput(meetingId, actionItemId, 'title') || {}).value || '',
            description: (_mtgActionInput(meetingId, actionItemId, 'desc') || {}).value || '',
            targetProjectId: (_mtgActionInput(meetingId, actionItemId, 'project') || {}).value || ''
        });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

async function confirmMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, {
            action: 'confirm',
            title: (_mtgActionInput(meetingId, actionItemId, 'title') || {}).value || '',
            description: (_mtgActionInput(meetingId, actionItemId, 'desc') || {}).value || '',
            targetProjectId: (_mtgActionInput(meetingId, actionItemId, 'project') || {}).value || ''
        });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

async function keepMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, { action: 'keep' });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

async function rejectMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, { action: 'reject', reason: _mtgT('meeting_action_rejected_by_user', 'Rejected by user') });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

function openMeetingTaskLink(projectId, taskId) {
    if (!projectId || !taskId) return;
    window.location.hash = '#projects';
    window.dispatchEvent(new CustomEvent('vo-open-project-task', { detail: { projectId: projectId, taskId: taskId } }));
    alert(_mtgT('meeting_action_task_created', 'Task created') + ': ' + taskId);
}

function _mtgRenderConflictPanel(m) {
    var conflicts = Array.isArray(m.conflicts) ? m.conflicts.filter(function(c) { return c && ['open', 'waiting', 'reserved'].indexOf(c.status || 'open') >= 0; }) : [];
    if (!conflicts.length && !(m.reservation && Object.keys(m.reservation).length)) return '';
    var html = '<div class="mtg-section mtg-conflict-panel"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_conflicts', 'Participant conflicts')) + '</div>';
    conflicts.forEach(function(c) {
        var info = _mtgAgentMap[c.agentId] || { emoji: '🤖', name: c.agentId || 'Agent' };
        var advisory = c.advisory || {};
        html += '<div class="mtg-conflict-card">';
        html += '<div class="mtg-conflict-head"><strong>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || c.agentId)) + '</strong><span class="mtg-badge mtg-badge-countdown">' + _escMtg(_mtgConflictLabel('risk', c.riskLevel || 'busy')) + '</span></div>';
        html += '<div class="mtg-section-text">' + _escMtg(_mtgConflictText(c.summary || c.reason || '')) + '</div>';
        html += '<div class="mtg-meta"><span>' + _escMtg(_mtgT('meeting_conflict_estimated', 'Availability')) + ': ' + _escMtg(_mtgConflictText(c.estimatedAvailability || 'unknown')) + '</span><span>' + _escMtg(_mtgT('meeting_pause_capability', 'Pause')) + ': ' + _escMtg(_mtgConflictLabel('pause', c.pauseCapability || 'logical')) + '</span></div>';
        if (advisory && advisory.status) {
            html += '<div class="mtg-result-summary mtg-conflict-advisory">';
            html += '<div class="mtg-result-label">' + _escMtg(_mtgT('meeting_advisory', 'Advisory recommendation')) + ': ' + _escMtg(_mtgConflictLabel('recommendation', advisory.recommendation || '')) + '</div>';
            if (advisory.interruptionRisk) html += '<div class="mtg-section-text">' + _escMtg(_mtgConflictText(advisory.interruptionRisk)) + '</div>';
            if (advisory.resumeNotes) html += '<div class="mtg-section-text">' + _escMtg(_mtgConflictText(advisory.resumeNotes)) + '</div>';
            if (advisory.source) html += '<div class="mtg-meta"><span>' + _escMtg(_mtgT('meeting_advisory_source', 'Source')) + ': ' + _escMtg(_mtgConflictLabel('advisory_source', advisory.source)) + '</span></div>';
            html += '</div>';
        }
        html += '<div class="mtg-actions-bar">';
        html += '<button class="mtg-btn" onclick="resolveMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\',\'wait\')">' + _escMtg(_mtgT('meeting_conflict_wait', 'Wait')) + '</button>';
        html += '<button class="mtg-btn" onclick="reserveMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\')">' + _escMtg(_mtgT('meeting_conflict_reserve', 'Try later')) + '</button>';
        html += '<button class="mtg-btn" onclick="replaceMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\')">' + _escMtg(_mtgT('meeting_conflict_replace', 'Replace')) + '</button>';
        html += '<button class="mtg-btn mtg-btn-delete" onclick="forceJoinMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\')">' + _escMtg(_mtgT('meeting_conflict_force', 'Force join')) + '</button>';
        html += '</div></div>';
    });
    if (m.reservation && Object.keys(m.reservation).length) {
        html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_reservation_notice', 'Reservations are reminders only; conflicts are rechecked before the meeting starts.')) + '</div>';
    }
    html += '</div>';
    return html;
}

function _mtgConflictLabel(kind, value) {
    var key = String(value || '').trim();
    if (!key) return '';
    var map = {
        risk: {
            high: 'meeting_conflict_risk_high',
            medium: 'meeting_conflict_risk_medium',
            low: 'meeting_conflict_risk_low',
            busy: 'meeting_conflict_risk_busy',
            idle: 'meeting_conflict_risk_idle'
        },
        pause: {
            unavailable: 'meeting_pause_unavailable',
            logical: 'meeting_pause_logical',
            none: 'meeting_pause_none',
            unknown: 'meeting_unknown'
        },
        recommendation: {
            wait: 'meeting_recommend_wait',
            reserve: 'meeting_recommend_reserve',
            replace: 'meeting_recommend_replace',
            force_join: 'meeting_recommend_force_join'
        },
        advisory_source: {
            agent_advisory_turn: 'meeting_advisory_source_agent',
            local_fallback: 'meeting_advisory_source_local',
            local_fallback_after_provider_failure: 'meeting_advisory_source_local_failed'
        }
    };
    var dict = map[kind] || {};
    return dict[key] ? _mtgT(dict[key], key) : key;
}

function _mtgConflictText(value) {
    var text = String(value || '').trim();
    if (!text) return '';
    var exact = {
        'unknown': 'meeting_unknown',
        'Idle': 'meeting_conflict_idle',
        'Provider call in progress': 'meeting_conflict_provider_call',
        'Agent is already in another active meeting. Do not force join unless the existing meeting is cancelled.': 'meeting_conflict_risk_meeting_occupied',
        'No original task can be resumed from this meeting conflict.': 'meeting_conflict_resume_none',
        'A provider call is in progress. Interrupting can lose an in-flight response.': 'meeting_conflict_risk_provider_call',
        'Wait for the provider call to finish, then retry conflict handling.': 'meeting_conflict_resume_provider_call',
        'The current task can only be logically paused; the provider process may not stop immediately.': 'meeting_conflict_risk_logical_pause',
        'Save current task context and resume from the recorded task state after the meeting.': 'meeting_conflict_resume_logical_pause',
        'Pause safety is uncertain.': 'meeting_conflict_risk_uncertain',
        'Recheck the agent state before forcing a meeting.': 'meeting_conflict_resume_recheck'
    };
    if (exact[text]) return _mtgT(exact[text], text);
    var prefix = 'Already in meeting: ';
    if (text.indexOf(prefix) === 0) {
        return _mtgT('meeting_conflict_already_in_meeting', 'Already in meeting: {topic}', { topic: text.slice(prefix.length) });
    }
    return text;
}

function openEndMeetingForm(meetingId) {
    document.getElementById('end-mtg-id').value = meetingId;
    document.getElementById('end-mtg-summary').value = '';
    document.getElementById('end-mtg-resolution').value = '';
    document.getElementById('end-mtg-actions').value = '';
    document.getElementById('end-mtg-error').style.display = 'none';

    // Build per-agent response fields
    var respSection = document.getElementById('end-mtg-responses-section');
    respSection.innerHTML = '';
    var meeting = _mtgData.active.find(function(m) { return m.id === meetingId; });
    if (meeting) {
        var participants = meeting.participants || meeting.agents || [];
        if (participants.length) {
            respSection.innerHTML = '<label class="mtg-label" style="margin-top:6px">' + _escMtg(_tr('agent_responses')) + '</label>';
            participants.forEach(function(pKey) {
                var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey };
                var div = document.createElement('div');
                div.style.cssText = 'margin-bottom:6px;';
                div.innerHTML = '<div style="font-size:9px;color:#ccc;margin-bottom:2px;">' + info.emoji + ' ' + _escMtg(info.name) + '</div>' +
                    '<textarea class="mtg-textarea end-mtg-resp" data-agent="' + _escMtg(pKey) + '" rows="2" placeholder="' + _escMtg(_tr('contribution_placeholder', { name: info.name })) + '"></textarea>';
                respSection.appendChild(div);
            });
        }
    }

    document.getElementById('endMeetingModal').classList.remove('hidden');
}

function closeEndMeetingModal() {
    document.getElementById('endMeetingModal').classList.add('hidden');
}

async function endExecutableMeetingWithAI(meetingId) {
    var btn = document.getElementById('mtg-ai-end-' + meetingId);
    if (btn) {
        btn.disabled = true;
        btn.textContent = _mtgT('meeting_ai_ending', 'Moderator summarizing...');
    }
    try {
        var res = await fetch('/api/meetings/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: meetingId, endedBy: 'user' })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to end meeting');
        await _mtgAfterMeetingRefresh();
        switchMtgTab('completed');
    } catch (e) {
        alert((_tr('failed_end_meeting') || 'Failed to end meeting') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '✅ ' + _mtgT('meeting_ai_end', 'Ask moderator to end');
        }
    }
}

function _mtgFindActiveMeeting(meetingId) {
    return (_mtgData.active || []).find(function(m) { return m && m.id === meetingId; }) || null;
}

async function _mtgTransitionMeeting(meetingId, action, reason) {
    var meeting = _mtgFindActiveMeeting(meetingId);
    var body = {
        action: action,
        actorType: 'user',
        actorId: 'user',
        idempotencyKey: action + '-' + Date.now()
    };
    if (meeting && meeting.executionVersion !== undefined) body.expectedVersion = meeting.executionVersion;
    if (reason) body.reason = reason;
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/transition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Meeting control failed');
    await _mtgAfterMeetingRefresh();
    if (action === 'cancel') switchMtgTab('completed');
    return data;
}

async function _mtgConflictAction(meetingId, body) {
    body = body || {};
    body.actorType = body.actorType || 'user';
    body.actorId = body.actorId || 'user';
    body.idempotencyKey = body.idempotencyKey || ((body.action || 'conflict') + '-' + Date.now() + '-' + Math.random().toString(16).slice(2));
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Conflict handling failed');
    await _mtgAfterMeetingRefresh();
    return data;
}

async function resolveMeetingConflict(meetingId, agentId, action) {
    try {
        await _mtgConflictAction(meetingId, { action: action || 'wait', agentId: agentId });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function reserveMeetingConflict(meetingId, agentId) {
    try {
        await _mtgConflictAction(meetingId, { action: 'reserve', agentId: agentId });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function replaceMeetingConflict(meetingId, agentId) {
    var replacement = prompt(_mtgT('meeting_conflict_replace_prompt', 'Replacement agent ID'), '');
    if (!replacement) return;
    try {
        await _mtgConflictAction(meetingId, { action: 'replace', agentId: agentId, replacement: replacement.trim() });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function forceJoinMeetingConflict(meetingId, agentId) {
    if (!confirm(_mtgT('meeting_conflict_force_confirm', 'Force join can interrupt current work. Continue?'))) return;
    try {
        await _mtgConflictAction(meetingId, { action: 'force_join', agentId: agentId, confirmForce: true });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function refreshMeetingConflicts(meetingId) {
    try {
        await _mtgConflictAction(meetingId, { action: 'refresh' });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function pauseExecutableMeeting(meetingId) {
    var btn = document.getElementById('mtg-pause-' + meetingId);
    if (btn) btn.disabled = true;
    try {
        await _mtgTransitionMeeting(meetingId, 'pause', 'Paused by user');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function resumeExecutableMeeting(meetingId) {
    var btn = document.getElementById('mtg-resume-' + meetingId);
    if (btn) btn.disabled = true;
    var meeting = _mtgFindActiveMeeting(meetingId);
    var previous = meeting && meeting.executionPreviousStage;
    var action = previous === 'active_discussion' ? 'resume_discussion' : previous === 'preparing' ? 'resume_preparing' : 'resume_opening';
    try {
        await _mtgTransitionMeeting(meetingId, action, 'Resumed by user');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function cancelExecutableMeeting(meetingId) {
    if (!confirm(_mtgT('meeting_cancel_confirm', 'Cancel this meeting?'))) return;
    var btn = document.getElementById('mtg-cancel-' + meetingId);
    if (btn) btn.disabled = true;
    try {
        await _mtgTransitionMeeting(meetingId, 'cancel', 'Cancelled by user');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitEndMeeting() {
    var meetId = document.getElementById('end-mtg-id').value;
    var summary = document.getElementById('end-mtg-summary').value.trim();
    var resolution = document.getElementById('end-mtg-resolution').value.trim();
    var actionsRaw = document.getElementById('end-mtg-actions').value.trim();
    var actionItems = actionsRaw ? actionsRaw.split('\n').map(function(l) { return l.trim(); }).filter(Boolean) : [];

    // Collect per-agent responses
    var responses = {};
    document.querySelectorAll('.end-mtg-resp').forEach(function(el) {
        var key = el.dataset.agent;
        var val = el.value.trim();
        if (key && val) responses[key] = val;
    });

    if (!summary) {
        var errEl = document.getElementById('end-mtg-error');
        errEl.textContent = _tr('summary_required');
        errEl.style.display = 'block';
        return;
    }

    try {
        var res = await fetch('/api/meetings/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: meetId, summary: summary, resolution: resolution, actionItems: actionItems, responses: responses, endedBy: 'user' })
        });
        var data = await res.json();
        if (data.ok) {
            closeEndMeetingModal();
            _mtgRefresh();
        } else {
            var errEl = document.getElementById('end-mtg-error');
            errEl.textContent = data.error || _tr('failed_end_meeting');
            errEl.style.display = 'block';
        }
    } catch (e) {
        var errEl = document.getElementById('end-mtg-error');
        errEl.textContent = _tr('error') + ': ' + e.message;
        errEl.style.display = 'block';
    }
}

async function deleteMeetingHistory(meetingId) {
    if (!confirm(_tr('delete_meeting_confirm'))) return;
    try {
        var res = await fetch('/api/meetings/history/' + meetingId, { method: 'DELETE' });
        var data = await res.json();
        if (data.ok) _mtgRefresh();
        else alert(data.error || _tr('failed_delete'));
    } catch (e) {
        alert(_tr('error') + ': ' + e.message);
    }
}

// --- Sidebar meetings widget ---
function _updateSidebarMeetings() {
    var container = document.getElementById('sidebar-mtg-active');
    if (!container) return;
    var active = _mtgData.active || [];
    var pendingRequests = (_mtgData.requests || []).filter(function(r) { return r && r.status === 'pending'; });
    var requestHtml = '';
    if (pendingRequests.length) {
        requestHtml = '<div class="sidebar-mtg-request" onclick="openMeetingsDashboard();switchMtgTab(\'requests\')">' +
            '<div class="sidebar-mtg-item-title sidebar-mtg-request-title"><span><span class="sidebar-mtg-request-dot"></span>' + _escMtg(_mtgT('meeting_request_pending_prompt', 'AI meeting requests need confirmation')) + '</span><span class="sidebar-mtg-request-count">' + _escMtg(String(pendingRequests.length)) + '</span></div>' +
            '</div>';
    }
    if (!active.length) {
        container.innerHTML = requestHtml + '<div class="sidebar-mtg-none">' + _escMtg(_tr('no_active_meetings')) + '</div>';
        return;
    }
    container.innerHTML = requestHtml + active.map(function(m) {
        var participants = m.participants || m.agents || [];
        var pNames = participants.map(function(k) {
            var info = _mtgAgentMap[k];
            return info ? info.emoji + ' ' + info.name : k;
        }).join(', ');
        return '<div class="sidebar-mtg-item" onclick="openMeetingReference({ meetingId: ' + _escMtg(_mtgJsArg(m.id || '')) + ' })">' +
            '<div class="sidebar-mtg-item-title"><span class="sidebar-mtg-item-dot"></span>' + _escMtg(m.topic || _tr('untitled_meeting')) + '</div>' +
            '<div class="sidebar-mtg-item-meta">' + pNames + '</div>' +
            '</div>';
    }).join('');
}

// Refresh sidebar meetings periodically
setInterval(function() {
    Promise.all([
        fetch('/api/meetings/active').then(function(r) { return r.json(); }),
        fetch('/api/meetings/requests?status=pending').then(function(r) { return r.json(); })
    ]).then(function(results) {
        var data = results[0] || {};
        var requests = results[1] || {};
        _mtgData.active = data.meetings || [];
        _mtgSeedLiveMeetings(_mtgData.active);
        (_mtgData.active || []).forEach(_mtgMaybeAutoContinueDecisionMeeting);
        _mtgData.requests = _mtgSortRequestsByStatusThenTime(requests.requests || []);
        // Also refresh agent map if empty
        if (Object.keys(_mtgAgentMap).length === 0) {
            fetch('/agents-list').then(function(r) { return r.json(); }).then(function(d) {
                var list = d.agents || d || [];
                if (Array.isArray(list)) {
                    list.forEach(function(a) {
                        _mtgAgentMap[a.key || a.agentId || a.id] = { name: a.name || a.key, emoji: a.emoji || '🤖', role: a.role || '' };
                    });
                }
                _updateSidebarMeetings();
            }).catch(function() { _updateSidebarMeetings(); });
        } else {
            _updateSidebarMeetings();
        }
    }).catch(function() {});
}, 10000);

setInterval(_mtgUpdateDecisionCountdowns, 1000);

// Initial load
setTimeout(function() {
    fetch('/api/meetings/active').then(function(r) { return r.json(); }).then(function(data) {
        _mtgData.active = data.meetings || [];
        _mtgSeedLiveMeetings(_mtgData.active);
        fetch('/agents-list').then(function(r) { return r.json(); }).then(function(d) {
            var list = d.agents || d || [];
            if (Array.isArray(list)) {
                list.forEach(function(a) {
                    _mtgAgentMap[a.key || a.agentId || a.id] = { name: a.name || a.key, emoji: a.emoji || '🤖', role: a.role || '' };
                });
            }
            _updateSidebarMeetings();
        }).catch(function() { _updateSidebarMeetings(); });
    }).catch(function() {});
}, 2000);

// --- Meeting table click handler ---
// Override the existing furniture click to detect meetingTable clicks
var _origHandleFurnitureClick = typeof handleFurnitureClick === 'function' ? handleFurnitureClick : null;
function _meetingTableClickCheck(item) {
    if (item && item.type === 'meetingTable' && !editMode) {
        openMeetingsDashboard();
        return true;
    }
    return false;
}

// Close meetings modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (!document.getElementById('meetingRequestDetailModal').classList.contains('hidden')) {
            closeMeetingRequestDetailModal();
        } else if (!document.getElementById('meetingDetailModal').classList.contains('hidden')) {
            closeMeetingDetailModal();
        } else if (!document.getElementById('endMeetingModal').classList.contains('hidden')) {
            closeEndMeetingModal();
        } else if (!document.getElementById('meetingsModal').classList.contains('hidden')) {
            closeMeetingsModal();
        }
    }
});

// Close meetings modal on backdrop click
document.getElementById('meetingsModal').addEventListener('click', function(e) {
    if (e.target === this) closeMeetingsModal();
});
document.getElementById('endMeetingModal').addEventListener('click', function(e) {
    if (e.target === this) closeEndMeetingModal();
});
document.getElementById('meetingDetailModal').addEventListener('click', function(e) {
    if (e.target === this) closeMeetingDetailModal();
});
document.getElementById('meetingRequestDetailModal').addEventListener('click', function(e) {
    if (e.target === this) closeMeetingRequestDetailModal();
});

// ============================================================
// SKILLS LIBRARY
// ============================================================

var _sklSkills = [];
var _sklEditingName = null; // null = new, string = editing existing

function openSkillsLibrary() {
    document.getElementById('skillsLibraryModal').classList.remove('hidden');
    refreshSkillsList();
}

function closeSkillsLibrary() {
    document.getElementById('skillsLibraryModal').classList.add('hidden');
}

async function refreshSkillsList() {
    try {
        var res = await fetch('/api/skills-library');
        var data = await res.json();
        _sklSkills = Array.isArray(data) ? data : (data.skills || []);
    } catch (e) {
        _sklSkills = [];
    }
    renderSkillCards();
}

function renderSkillCards() {
    var container = document.getElementById('skl-cards');
    if (!container) return;

    if (!_sklSkills.length) {
        container.innerHTML = '<div style="color:#666;font-size:11px;padding:20px;text-align:center;">' + _sklEsc(_tr('no_skills_library')) + '</div>';
        return;
    }

    var sorted = _sklSkills.slice().sort(function(a, b) { return (a.name || '').localeCompare(b.name || ''); });

    container.innerHTML = sorted.map(function(skill) {
        var safeName = _sklEsc(skill.name);
        return '<div class="skl-card" id="skl-card-' + safeName + '">' +
            '<div class="skl-card-top">' +
                '<div class="skl-card-name">' + safeName + '</div>' +
                '<div class="skl-card-actions">' +
                    '<button onclick="toggleSkillApply(\'' + safeName + '\')" title="' + _sklEsc(_tr('apply_to_agent')) + '">📋</button>' +
                    '<button onclick="openSkillEditor(\'' + safeName + '\')" title="' + _sklEsc(_tr('edit')) + '">✏️</button>' +
                    '<button onclick="deleteLibrarySkill(\'' + safeName + '\')" title="' + _sklEsc(_tr('delete')) + '">🗑️</button>' +
                '</div>' +
            '</div>' +
            '<div class="skl-apply-dropdown" id="skl-apply-' + safeName + '" style="display:none"></div>' +
        '</div>';
    }).join('');
}

function _sklEsc(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

async function toggleSkillApply(skillName) {
    var dropdown = document.getElementById('skl-apply-' + skillName);
    if (!dropdown) return;

    if (dropdown.style.display !== 'none') {
        dropdown.style.display = 'none';
        return;
    }

    // Fetch agent list
    try {
        var res = await fetch('/agents-list');
        var data = await res.json();
        var agentList = Array.isArray(data) ? data : (data.agents || []);

        var options = agentList.map(function(a) {
            var id = a.id || a.agentId || a.name;
            var name = a.name || id;
            return '<option value="' + _sklEsc(id) + '">' + _sklEsc(name) + '</option>';
        }).join('');

        dropdown.innerHTML =
            '<select id="skl-agent-select-' + skillName + '">' + options + '</select>' +
            '<button onclick="applySkillToAgent(\'' + _sklEsc(skillName) + '\')">' + _sklEsc(_tr('apply')) + '</button>';
        dropdown.style.display = 'flex';
    } catch (e) {
        _acpShowToast('❌ ' + _tr('failed_to_load'));
    }
}

async function applySkillToAgent(skillName) {
    var select = document.getElementById('skl-agent-select-' + skillName);
    if (!select) return;
    var agentId = select.value;
    if (!agentId) return;

    try {
        var res = await fetch('/api/skills-library/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill: skillName, agentId: agentId })
        });
        var data = await res.json();
        if (res.ok) {
            if (data.warning) {
                _acpShowToast('⚠️ ' + data.warning);
            } else {
                _acpShowToast('✅ ' + _tr('skill_applied', { skill: skillName, agent: agentId }));
            }
        } else {
            _acpShowToast('❌ ' + _tr('apply_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('apply_failed') + ': ' + e.message);
    }

    // Hide dropdown after apply
    var dropdown = document.getElementById('skl-apply-' + skillName);
    if (dropdown) dropdown.style.display = 'none';
}

async function openSkillEditor(skillName) {
    _sklEditingName = skillName;
    var titleEl = document.getElementById('skl-editor-title');
    var nameInput = document.getElementById('skl-editor-name');
    var contentArea = document.getElementById('skl-editor-content');

    if (skillName) {
        // Edit existing: fetch content
        titleEl.textContent = _tr('edit_skill');
        nameInput.value = skillName;
        nameInput.disabled = true;
        try {
            var res = await fetch('/api/skills-library/' + encodeURIComponent(skillName));
            var data = await res.json();
            contentArea.value = data.content || '';
        } catch (e) {
            contentArea.value = '';
            _acpShowToast('❌ ' + _tr('failed_load_skill') + ': ' + e.message);
        }
    } else {
        // New skill
        titleEl.textContent = _tr('add_skill_title');
        nameInput.value = '';
        nameInput.disabled = false;
        contentArea.value = '---\nname: \ndescription: \n---\n\n# Skill Title\n\nInstructions here...\n';
    }

    document.getElementById('skillEditorModal').classList.remove('hidden');
}

function closeSkillEditor() {
    document.getElementById('skillEditorModal').classList.add('hidden');
    _sklEditingName = null;
}

async function saveSkill() {
    var nameInput = document.getElementById('skl-editor-name');
    var contentArea = document.getElementById('skl-editor-content');
    var name = (nameInput.value || '').trim();
    var content = contentArea.value || '';

    if (!name) {
        _acpShowToast('❌ ' + _tr('skill_name_required'));
        return;
    }

    try {
        var res = await fetch('/api/skills-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: content })
        });
        var data = await res.json();
        if (res.ok) {
            _acpShowToast('✅ ' + _tr('skill_saved', { name: name }));
            closeSkillEditor();
            refreshSkillsList();
        } else {
            _acpShowToast('❌ ' + _tr('save_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('save_failed') + ': ' + e.message);
    }
}

async function deleteLibrarySkill(skillName) {
    if (!confirm(_tr('delete_library_skill_confirm', { name: skillName }))) return;

    try {
        var res = await fetch('/api/skills-library/' + encodeURIComponent(skillName), { method: 'DELETE' });
        if (res.ok) {
            _acpShowToast('🗑️ ' + _tr('skill_deleted', { name: skillName }));
            refreshSkillsList();
        } else {
            var data = await res.json().catch(function() { return {}; });
            _acpShowToast('❌ ' + _tr('failed_delete') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('failed_delete') + ': ' + e.message);
    }
}

async function handleSkillUpload(input) {
    if (!input.files || !input.files.length) return;
    var file = input.files[0];
    var name = file.name.replace(/\.md$/i, '').replace(/[^a-zA-Z0-9_-]/g, '-');

    try {
        var text = await file.text();
        var res = await fetch('/api/skills-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: text })
        });
        if (res.ok) {
            _acpShowToast('✅ ' + _tr('uploaded', { name: name }));
            refreshSkillsList();
        } else {
            var data = await res.json().catch(function() { return {}; });
            _acpShowToast('❌ ' + _tr('upload_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('upload_failed') + ': ' + e.message);
    }

    // Reset input so same file can be re-uploaded
    input.value = '';
}

// Close skills modals on backdrop click
document.getElementById('skillsLibraryModal').addEventListener('click', function(e) {
    if (e.target === this) closeSkillsLibrary();
});
document.getElementById('skillEditorModal').addEventListener('click', function(e) {
    if (e.target === this) closeSkillEditor();
});

// Close skills modals on Escape (extend existing keydown)
var _origKeydownHandler = document.onkeydown;
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (!document.getElementById('skillEditorModal').classList.contains('hidden')) {
            closeSkillEditor();
            e.stopPropagation();
        } else if (!document.getElementById('skillsLibraryModal').classList.contains('hidden')) {
            closeSkillsLibrary();
            e.stopPropagation();
        }
    }
});

loop();
