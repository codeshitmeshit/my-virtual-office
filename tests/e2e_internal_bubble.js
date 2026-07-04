const assert = require('assert');
const fs = require('fs');

function openWs(url) {
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(url);
        const timer = setTimeout(() => reject(new Error('Timed out opening websocket')), 10000);
        ws.addEventListener('open', () => {
            clearTimeout(timer);
            resolve(ws);
        }, { once: true });
        ws.addEventListener('error', reject, { once: true });
    });
}

let seq = 0;
function send(ws, method, params = {}) {
    const id = ++seq;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`Timed out ${method}`)), 45000);
        const onMessage = (event) => {
            const msg = JSON.parse(event.data.toString());
            if (msg.id !== id) return;
            clearTimeout(timer);
            ws.removeEventListener('message', onMessage);
            if (msg.error) reject(new Error(`${method}: ${JSON.stringify(msg.error)}`));
            else resolve(msg.result || {});
        };
        ws.addEventListener('message', onMessage);
    });
}

async function evalJson(ws, expression) {
    const res = await send(ws, 'Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (res.exceptionDetails) throw new Error(res.exceptionDetails.text || JSON.stringify(res.exceptionDetails));
    return res.result.value;
}

async function waitFor(ws, expression, timeoutMs = 30000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        const ok = await evalJson(ws, expression).catch(() => false);
        if (ok) return true;
        await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw new Error(`Timed out waiting for ${expression}`);
}

(async () => {
    const pageInfo = await (await fetch('http://127.0.0.1:9224/json/new?about:blank', { method: 'PUT' })).json();
    const ws = await openWs(pageInfo.webSocketDebuggerUrl);
    const errors = [];
    ws.addEventListener('message', (event) => {
        const msg = JSON.parse(event.data.toString());
        if (msg.method === 'Runtime.exceptionThrown') {
            errors.push((msg.params && msg.params.exceptionDetails && msg.params.exceptionDetails.text) || 'page exception');
        }
    });

    try {
        await send(ws, 'Runtime.enable');
        await send(ws, 'Page.enable').catch(() => {});
        await send(ws, 'Runtime.addBinding', { name: '__voBubblePageError' }).catch(() => {});
        await send(ws, 'Page.addScriptToEvaluateOnNewDocument', {
            source: `window.addEventListener('error', function(e) { try { window.__voBubblePageError(String(e.error && e.error.stack || e.message || e)); } catch (_) {} });`
        }).catch(() => {});
        await send(ws, 'Emulation.setDeviceMetricsOverride', {
            width: 1440,
            height: 900,
            deviceScaleFactor: 1,
            mobile: false
        });
        const liveUrl = process.env.VO_LIVE_URL || 'http://host.docker.internal:8090/';
        await send(ws, 'Page.navigate', { url: liveUrl + '?internal-bubble=' + Date.now() });
        await waitFor(ws, `Boolean(window.agents && window.getBubbleMinState && window.handleBubbleClick && typeof Agent !== 'undefined')`);

        await evalJson(ws, `(() => {
            if (!agents[0]) {
                const testAgent = new Agent({
                    id: 'bubble-test-agent',
                    statusKey: 'bubble-test-agent',
                    name: 'Bubble Test',
                    role: 'Internal bubble test',
                    color: '#4f46e5',
                    branch: 'ENG',
                    deskIdx: 0
                });
                agents.push(testAgent);
                if (typeof agentMap !== 'undefined') {
                    agentMap[testAgent.id] = testAgent;
                    agentMap[testAgent.statusKey] = testAgent;
                }
            }
            const prefs = JSON.parse(localStorage.getItem('vo-display-prefs') || '{}');
            prefs.internalBubbleTimeoutSec = 2;
            localStorage.setItem('vo-display-prefs', JSON.stringify(prefs));
            _displayPrefs.internalBubbleTimeoutSec = 2;

            const agent = agents[0];
            const text = 'Reviewing a deliberately long Internal status 中文无空格文本用于验证紧凑换行';
            agent.thought = text;
            agent.lastThought = text;
            agent.thoughtChars = text.length;
            agent.thoughtUpdatedAt = Date.now();
            getBubbleMinState(agent).thought = false;
            return true;
        })()`);

        await evalJson(ws, `(() => { collectBubbles(); if (typeof drawAllBubbles === 'function') drawAllBubbles(); return true; })()`);
        const expanded = await evalJson(ws, `(() => {
            const bubble = (typeof lastCollectedBubbles !== 'undefined' ? lastCollectedBubbles : []).find(item => item.type === 'thought');
            const agent = agents[0];
            return {
                width: bubble && bubble.w,
                height: bubble && bubble.h,
                minimized: getBubbleMinState(agent).thought,
                timeout: _displayPrefs.internalBubbleTimeoutSec
            };
        })()`);
        assert.strictEqual(expanded.width, 132);
        assert.ok(expanded.height > 0 && expanded.height < 100);
        assert.strictEqual(expanded.minimized, false);
        assert.strictEqual(expanded.timeout, 2);

        const desktopShot = await send(ws, 'Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
        fs.writeFileSync('/tmp/internal-bubble-desktop.png', Buffer.from(desktopShot.data, 'base64'));

        await new Promise(resolve => setTimeout(resolve, 2300));
        const collapsed = await evalJson(ws, `(() => {
            collectBubbles();
            const agent = agents[0];
            const icon = (typeof renderedIcons !== 'undefined' ? renderedIcons : []).find(item => item.type === 'thought' && item.agent === agent);
            return {
                minimized: getBubbleMinState(agent).thought,
                hasIcon: Boolean(icon)
            };
        })()`);
        assert.strictEqual(collapsed.minimized, true);
        assert.strictEqual(collapsed.hasIcon, true);

        const restored = await evalJson(ws, `(() => {
            const agent = agents[0];
            const icon = (typeof renderedIcons !== 'undefined' ? renderedIcons : []).find(item => item.type === 'thought' && item.agent === agent);
            const before = agent.thoughtUpdatedAt;
            const handled = handleBubbleClick(icon.x + icon.w / 2, icon.y + icon.h / 2);
            return {
                handled,
                minimized: getBubbleMinState(agent).thought,
                restarted: agent.thoughtUpdatedAt > before
            };
        })()`);
        assert.strictEqual(restored.handled, true);
        assert.strictEqual(restored.minimized, false);
        assert.strictEqual(restored.restarted, true);

        await send(ws, 'Emulation.setDeviceMetricsOverride', {
            width: 390,
            height: 844,
            deviceScaleFactor: 1,
            mobile: true
        });
        await evalJson(ws, `(() => {
            if (typeof resizeCanvas === 'function') resizeCanvas();
            window.dispatchEvent(new Event('resize'));
            return true;
        })()`);
        await evalJson(ws, `(() => {
            const agent = agents[0];
            agent.thought = agent.thought || agent.lastThought || 'Mobile internal bubble check';
            agent.lastThought = agent.thought;
            agent.thoughtChars = agent.thought.length;
            agent.thoughtUpdatedAt = Date.now();
            getBubbleMinState(agent).thought = false;
            return true;
        })()`);
        await new Promise(resolve => setTimeout(resolve, 500));
        await evalJson(ws, `(() => { collectBubbles(); if (typeof drawAllBubbles === 'function') drawAllBubbles(); return true; })()`);
        const mobileShot = await send(ws, 'Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
        fs.writeFileSync('/tmp/internal-bubble-mobile.png', Buffer.from(mobileShot.data, 'base64'));
        const mobile = await evalJson(ws, `(() => {
            const bubble = (typeof lastCollectedBubbles !== 'undefined' ? lastCollectedBubbles : []).find(item => item.type === 'thought');
            return bubble ? { x: bubble.x, y: bubble.y, w: bubble.w, h: bubble.h } : null;
        })()`);
        assert.ok(mobile);
        assert.ok(mobile.x >= 0 && mobile.y >= 0);
        assert.strictEqual(mobile.w, 132);
        assert.deepStrictEqual(errors, []);

        console.log(JSON.stringify({ expanded, collapsed, restored, mobile, screenshots: [
            '/tmp/internal-bubble-desktop.png',
            '/tmp/internal-bubble-mobile.png'
        ] }, null, 2));
    } finally {
        fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
        ws.close();
    }
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
