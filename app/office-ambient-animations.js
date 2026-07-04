// Idle ambient animations and lightweight office games.
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

Object.assign(window, {
    launchAirplane,
    maybeThrowAirplane,
    updateAirplanes,
    drawAirplanes,
    startRPS,
    updateRPS,
    drawRPS,
    maybeStartRPS,
    maybeStartSocial,
    updateSocialInteractions,
    drawSocialInteractions,
    maybeStartGathering,
    updateGatherings,
    drawGatherings,
    startDartGame,
    updateDartGames,
    drawDartGames,
    maybeStartDarts
});
