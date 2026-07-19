const assert = require('assert');
const fs = require('fs');

const cdpURL = (process.env.VO_CDP_URL || 'http://127.0.0.1:9224').replace(/\/$/, '');
const appURL = process.env.VO_APP_URL || 'http://localhost:8090/';

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
function send(ws, method, params = {}, timeoutMs = 30000) {
    const id = ++seq;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            ws.removeEventListener('message', onMessage);
            reject(new Error(`Timed out waiting for CDP response: ${method}`));
        }, timeoutMs);
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

function eventOnce(ws, method, predicate = () => true, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            ws.removeEventListener('message', onMessage);
            reject(new Error(`Timed out waiting for ${method}`));
        }, timeoutMs);
        const onMessage = (event) => {
            const msg = JSON.parse(event.data.toString());
            if (msg.method === method && predicate(msg.params || {})) {
                clearTimeout(timer);
                ws.removeEventListener('message', onMessage);
                resolve(msg.params || {});
            }
        };
        ws.addEventListener('message', onMessage);
    });
}

async function evalJson(ws, expression, timeoutMs = 30000) {
    const res = await send(ws, 'Runtime.evaluate', {
        expression,
        awaitPromise: true,
        returnByValue: true,
    }, timeoutMs);
    if (res.exceptionDetails) {
        throw new Error(res.exceptionDetails.text || JSON.stringify(res.exceptionDetails));
    }
    return res.result && res.result.value;
}

async function waitForRuntime(ws, expression, timeoutMs = 30000) {
    const start = Date.now();
    let last = '';
    while (Date.now() - start < timeoutMs) {
        const res = await send(ws, 'Runtime.evaluate', {
            expression,
            awaitPromise: true,
            returnByValue: true,
        });
        if (res.exceptionDetails) last = res.exceptionDetails.text || JSON.stringify(res.exceptionDetails);
        else if (res.result && res.result.value) return res.result.value;
        await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(`Timed out waiting for expression: ${expression}\n${last}`);
}

async function setViewport(ws, width, height, deviceScaleFactor = 1) {
    await send(ws, 'Emulation.setDeviceMetricsOverride', {
        width,
        height,
        deviceScaleFactor,
        mobile: width < 600,
    });
}

async function screenshot(ws, path) {
    const shot = await send(ws, 'Page.captureScreenshot', { format: 'png', fromSurface: true }, 30000);
    fs.writeFileSync(path, Buffer.from(shot.data || '', 'base64'));
}

async function createCdpPage(url) {
    try {
        const res = await fetch(`${cdpURL}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' });
        return await res.json();
    } catch (error) {
        throw new Error(`CDP is unavailable at ${cdpURL}. Run ./start.sh --browser, start local Chrome with remote debugging enabled, or set VO_CDP_URL to another reachable Chrome DevTools endpoint. ${error.message || error}`);
    }
}

(async () => {
    const pageInfo = await createCdpPage(appURL);
    const errors = [];
    const ws = await openWs(pageInfo.webSocketDebuggerUrl);
    ws.addEventListener('message', (event) => {
        const msg = JSON.parse(event.data.toString());
        if (msg.method === 'Runtime.exceptionThrown') {
            errors.push((msg.params.exceptionDetails || {}).text || 'Runtime exception');
        }
    });

    try {
        await send(ws, 'Runtime.enable');
        await send(ws, 'Page.enable');
        await setViewport(ws, 1440, 900);
        const loaded = eventOnce(ws, 'Page.loadEventFired').catch(() => null);
        await send(ws, 'Page.navigate', { url: appURL });
        await loaded;
        await waitForRuntime(ws, 'Boolean(document.querySelector("#officeCanvas"))');

        await evalJson(ws, `(() => {
            const prefs = JSON.parse(localStorage.getItem('vo-display-prefs') || '{}');
            prefs.internalBubbleTimeoutSec = 2;
            localStorage.setItem('vo-display-prefs', JSON.stringify(prefs));
            window._displayPrefs.internalBubbleTimeoutSec = 2;

            const agent = window.agents[0];
            const text = 'Reviewing a deliberately long Internal status 中文无空格文本用于验证紧凑换行';
            agent.thought = text;
            agent.lastThought = text;
            agent.thoughtChars = text.length;
            agent.thoughtUpdatedAt = Date.now();
            window.getBubbleMinState(agent).thought = false;
            return true;
        })()`);

        await new Promise((resolve) => setTimeout(resolve, 500));
        const expanded = await evalJson(ws, `(() => {
            const bubble = window.lastCollectedBubbles.find(item => item.type === 'thought');
            const agent = window.agents[0];
            return {
                width: bubble && bubble.w,
                height: bubble && bubble.h,
                minimized: window.getBubbleMinState(agent).thought,
                timeout: window._displayPrefs.internalBubbleTimeoutSec
            };
        })()`);
        assert.strictEqual(expanded.width, 132);
        assert.ok(expanded.height > 0 && expanded.height < 100);
        assert.strictEqual(expanded.minimized, false);
        assert.strictEqual(expanded.timeout, 2);
        await screenshot(ws, '/tmp/internal-bubble-desktop.png');

        await new Promise((resolve) => setTimeout(resolve, 2300));
        const collapsed = await evalJson(ws, `(() => {
            const agent = window.agents[0];
            const icon = window.renderedIcons.find(item => item.type === 'thought' && item.agent === agent);
            return {
                minimized: window.getBubbleMinState(agent).thought,
                hasIcon: Boolean(icon)
            };
        })()`);
        assert.strictEqual(collapsed.minimized, true);
        assert.strictEqual(collapsed.hasIcon, true);

        const restored = await evalJson(ws, `(() => {
            const agent = window.agents[0];
            const icon = window.renderedIcons.find(item => item.type === 'thought' && item.agent === agent);
            const before = agent.thoughtUpdatedAt;
            const handled = window.handleBubbleClick(icon.x + icon.w / 2, icon.y + icon.h / 2);
            return {
                handled,
                minimized: window.getBubbleMinState(agent).thought,
                restarted: agent.thoughtUpdatedAt > before
            };
        })()`);
        assert.strictEqual(restored.handled, true);
        assert.strictEqual(restored.minimized, false);
        assert.strictEqual(restored.restarted, true);

        await setViewport(ws, 390, 844);
        await new Promise((resolve) => setTimeout(resolve, 500));
        await screenshot(ws, '/tmp/internal-bubble-mobile.png');
        const mobile = await evalJson(ws, `(() => {
            const bubble = window.lastCollectedBubbles.find(item => item.type === 'thought');
            return bubble ? { x: bubble.x, y: bubble.y, w: bubble.w, h: bubble.h } : null;
        })()`);
        assert.ok(mobile);
        assert.ok(mobile.x >= 0 && mobile.y >= 0);
        assert.strictEqual(mobile.w, 132);
        assert.deepStrictEqual(errors, []);

        console.log(JSON.stringify({
            expanded,
            collapsed,
            restored,
            mobile,
            screenshots: ['/tmp/internal-bubble-desktop.png', '/tmp/internal-bubble-mobile.png'],
        }, null, 2));
    } finally {
        fetch(`${cdpURL}/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
        ws.close();
    }
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
