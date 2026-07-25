// Office pet system and frame loop.
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

Object.assign(window, {
    initPets,
    OfficePet,
    _maybePetInteraction,
    updatePets,
    drawPets,
    loop
});
