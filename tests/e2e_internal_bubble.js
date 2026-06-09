const assert = require('assert');
const puppeteer = require('puppeteer-core');

(async () => {
    const browser = await puppeteer.connect({
        browserURL: 'http://127.0.0.1:9223',
        defaultViewport: { width: 1440, height: 900 }
    });
    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));

    await page.goto('http://localhost:7243/', { waitUntil: 'networkidle0', timeout: 30000 });
    await page.waitForSelector('#officeCanvas');

    await page.evaluate(() => {
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
    });

    await new Promise(resolve => setTimeout(resolve, 500));
    const expanded = await page.evaluate(() => {
        const bubble = lastCollectedBubbles.find(item => item.type === 'thought');
        const agent = agents[0];
        return {
            width: bubble && bubble.w,
            height: bubble && bubble.h,
            minimized: getBubbleMinState(agent).thought,
            timeout: _displayPrefs.internalBubbleTimeoutSec
        };
    });
    assert.strictEqual(expanded.width, 132);
    assert.ok(expanded.height > 0 && expanded.height < 100);
    assert.strictEqual(expanded.minimized, false);
    assert.strictEqual(expanded.timeout, 2);
    await page.screenshot({ path: '/tmp/internal-bubble-desktop.png', fullPage: true });

    await new Promise(resolve => setTimeout(resolve, 2300));
    const collapsed = await page.evaluate(() => {
        const agent = agents[0];
        const icon = renderedIcons.find(item => item.type === 'thought' && item.agent === agent);
        return {
            minimized: getBubbleMinState(agent).thought,
            hasIcon: Boolean(icon)
        };
    });
    assert.strictEqual(collapsed.minimized, true);
    assert.strictEqual(collapsed.hasIcon, true);

    const restored = await page.evaluate(() => {
        const agent = agents[0];
        const icon = renderedIcons.find(item => item.type === 'thought' && item.agent === agent);
        const before = agent.thoughtUpdatedAt;
        const handled = handleBubbleClick(icon.x + icon.w / 2, icon.y + icon.h / 2);
        return {
            handled,
            minimized: getBubbleMinState(agent).thought,
            restarted: agent.thoughtUpdatedAt > before
        };
    });
    assert.strictEqual(restored.handled, true);
    assert.strictEqual(restored.minimized, false);
    assert.strictEqual(restored.restarted, true);

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await new Promise(resolve => setTimeout(resolve, 500));
    await page.screenshot({ path: '/tmp/internal-bubble-mobile.png', fullPage: true });
    const mobile = await page.evaluate(() => {
        const bubble = lastCollectedBubbles.find(item => item.type === 'thought');
        return bubble ? { x: bubble.x, y: bubble.y, w: bubble.w, h: bubble.h } : null;
    });
    assert.ok(mobile);
    assert.ok(mobile.x >= 0 && mobile.y >= 0);
    assert.strictEqual(mobile.w, 132);
    assert.deepStrictEqual(errors, []);

    await browser.disconnect();
    console.log(JSON.stringify({ expanded, collapsed, restored, mobile, screenshots: [
        '/tmp/internal-bubble-desktop.png',
        '/tmp/internal-bubble-mobile.png'
    ] }, null, 2));
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
