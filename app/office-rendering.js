// Office furniture data, environment rendering, collision grid, and functional furniture menus.
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

Object.assign(window, {
    getDefaultFurniture,
    getInteractionSpots,
    drawEnvironment,
    drawInteriorWallShadows,
    drawInteriorWalls,
    drawInteriorWallOccluders,
    buildCollisionGrid,
    drawFurnitureItem,
    drawWhiteboard,
    drawWindow,
    drawClock,
    drawDesk,
    drawBossDesk,
    drawCouch,
    drawCoffeeTable,
    drawEndTable,
    drawTV,
    drawFloorLamp,
    drawBranchSign,
    drawInteractiveWindow,
    drawFloorWindow,
    drawTextLabel,
    drawKitchenCounter,
    drawCoffeeMakerStandalone,
    drawMicrowaveStandalone,
    drawToasterStandalone,
    drawLoungeArea,
    drawDartBoard,
    drawEngLounge,
    drawPingPongTable,
    drawPongGames,
    drawBreakArea,
    drawWaterCooler,
    drawVendingMachine,
    drawTallPlant,
    drawPlant,
    drawBookshelf,
    drawFunctionalBookshelf,
    _handleFunctionalFurnitureClick,
    _closeBookshelfActionMenu,
    _deleteSelectedWall
});
