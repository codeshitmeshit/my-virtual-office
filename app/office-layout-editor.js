// Office layout editor and edit-mode interactions.
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

Object.assign(window, {
    toggleEditMode,
    undoEdit,
    saveEdits,
    drawEditOverlay,
    drawEditHUD,
    handleEditClick,
    _pushUndo,
    _showCatalogPanel,
    _hideCatalogPanel,
    _selectCatalogItem,
    _cancelPlacement,
    _deselectItem,
    _syncAllDeskAssignments,
    _findFurnitureAt,
    _findWallAt,
    _deleteSelectedItem
});
