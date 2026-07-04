// Agent roster, appearance helpers, Agent class, and dynamic agent initialization.
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

let selectedAgent = null;
const dismissedNotify = new Set();  // track dismissed notifications to prevent poll re-enabling

Object.assign(window, {
    Agent,
    _fetchRoster,
    _initAgentsFromDefs,
    getDefaultAppearance,
    _findOfficeAgentConfig,
    _agentConfigMatches,
    _syncAgentToDesk,
    ensureValidAgentBranches,
    getBranchList,
    _invalidateBranchCache,
    timeStr,
    darken,
    drawRoundRect
});
