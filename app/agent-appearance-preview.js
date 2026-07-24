(function (root) {
    'use strict';

    function color(value, fallback) {
        return /^#[0-9a-f]{6}$/i.test(String(value || '')) ? value : fallback;
    }

    function drawHair(ctx, style, hairColor) {
        ctx.fillStyle = hairColor;
        if (style === 'bald') return;
        if (style === 'buzz') {
            ctx.fillRect(27, 14, 26, 5);
            return;
        }
        ctx.fillRect(26, 10, 28, 8);
        ctx.fillRect(24, 16, 5, style === 'long' ? 24 : 11);
        ctx.fillRect(51, 16, 5, style === 'long' ? 24 : 11);
        if (style === 'curly' || style === 'wavy') {
            ctx.fillRect(23, 9, 7, 7);
            ctx.fillRect(36, 7, 8, 6);
            ctx.fillRect(50, 9, 7, 7);
        } else if (style === 'spiky') {
            ctx.fillRect(28, 5, 6, 7);
            ctx.fillRect(38, 2, 6, 10);
            ctx.fillRect(48, 5, 6, 7);
        } else if (style === 'bun') {
            ctx.fillRect(35, 3, 11, 8);
        } else if (style === 'ponytail') {
            ctx.fillRect(54, 16, 7, 24);
        } else if (style === 'mohawk') {
            ctx.clearRect(26, 8, 28, 10);
            ctx.fillRect(37, 0, 7, 18);
        }
    }

    function drawHeadwear(ctx, type, headwearColor) {
        if (!type || type === 'none') return;
        ctx.fillStyle = headwearColor;
        if (type === 'headset' || type === 'goggles') {
            ctx.fillRect(22, 17, 4, 19);
            ctx.fillRect(54, 17, 4, 19);
            ctx.fillRect(26, 10, 28, 3);
            if (type === 'headset') ctx.fillRect(54, 34, 10, 3);
            return;
        }
        if (type === 'crown' || type === 'tiara') {
            ctx.fillRect(29, 7, 22, 5);
            ctx.fillRect(31, 2, 5, 6);
            ctx.fillRect(38, 0, 5, 8);
            ctx.fillRect(46, 2, 5, 6);
            return;
        }
        if (type === 'hardhat') {
            ctx.fillRect(25, 8, 30, 8);
            ctx.fillRect(22, 15, 36, 4);
            return;
        }
        ctx.fillRect(25, 8, 30, 8);
        if (type === 'cap') ctx.fillRect(48, 15, 13, 4);
    }

    function drawGlasses(ctx, type, glassesColor) {
        if (!type || type === 'none') return;
        ctx.fillStyle = glassesColor;
        ctx.fillRect(28, 25, 10, 3);
        ctx.fillRect(43, 25, 10, 3);
        ctx.fillRect(38, 26, 5, 2);
        if (type === 'sunglasses') {
            ctx.fillRect(29, 28, 9, 5);
            ctx.fillRect(43, 28, 9, 5);
        }
    }

    function drawHeldItem(ctx, type) {
        if (!type || type === 'none') return;
        const palette = {
            tablet: '#2e73a6',
            wrench: '#94a3b8',
            coffee: '#f5f5f5',
            clipboard: '#c58b45',
            pen: '#38bdf8',
            hammer: '#a8a29e',
            testTube: '#a78bfa',
            book: '#ef4444',
        };
        ctx.fillStyle = palette[type] || '#38bdf8';
        ctx.fillRect(61, 56, type === 'pen' ? 4 : 12, type === 'pen' ? 20 : 17);
        if (type === 'tablet' || type === 'clipboard' || type === 'book') {
            ctx.fillStyle = '#dbeafe';
            ctx.fillRect(64, 59, 6, 9);
        }
    }

    function render(canvas, appearance, agent) {
        if (!canvas || typeof canvas.getContext !== 'function') return false;
        appearance = appearance || {};
        agent = agent || {};
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.imageSmoothingEnabled = false;

        const skin = color(appearance.skinTone, '#e8b88a');
        const shirt = color(appearance.color || agent.color, '#ffd600');
        const hair = color(appearance.hairColor, '#1a1a1a');
        const eyes = color(appearance.eyeColor, '#38bdf8');
        const hat = color(appearance.headwearColor, '#a78bfa');
        const glasses = color(appearance.glassesColor, '#333333');

        ctx.fillStyle = '#13131c';
        ctx.fillRect(20, 96, 18, 5);
        ctx.fillRect(44, 96, 18, 5);
        ctx.fillStyle = '#203a6b';
        ctx.fillRect(24, 78, 14, 19);
        ctx.fillRect(44, 78, 14, 19);
        ctx.fillRect(22, 72, 38, 10);

        ctx.fillStyle = shirt;
        ctx.fillRect(21, 46, 38, 29);
        ctx.fillStyle = skin;
        ctx.fillRect(14, 49, 7, 27);
        ctx.fillRect(59, 49, 7, 27);
        ctx.fillRect(26, 16, 28, 29);

        drawHair(ctx, appearance.hairStyle || 'short', hair);

        ctx.fillStyle = '#ffffff';
        ctx.fillRect(30, 27, 8, 7);
        ctx.fillRect(43, 27, 8, 7);
        ctx.fillStyle = eyes;
        ctx.fillRect(33, 29, 4, 5);
        ctx.fillRect(46, 29, 4, 5);
        ctx.fillStyle = '#7c3f2c';
        ctx.fillRect(36, 39, 9, 2);

        if (appearance.facialHair && appearance.facialHair !== 'none') {
            ctx.fillStyle = hair;
            if (appearance.facialHair === 'mustache') ctx.fillRect(34, 37, 13, 3);
            else if (appearance.facialHair === 'goatee') ctx.fillRect(37, 39, 7, 7);
            else ctx.fillRect(30, 38, 21, appearance.facialHair === 'beard' ? 9 : 4);
        }

        if (appearance.costume === 'lobster') {
            ctx.fillStyle = '#d32f2f';
            ctx.fillRect(18, 43, 44, 34);
        } else if (appearance.costume === 'chicken') {
            ctx.fillStyle = '#ffd54f';
            ctx.fillRect(18, 43, 44, 34);
        }

        drawHeadwear(ctx, appearance.headwear, hat);
        drawGlasses(ctx, appearance.glasses, glasses);
        drawHeldItem(ctx, appearance.heldItem);
        return true;
    }

    root.AgentAppearancePreview = { render: render };
    if (typeof module !== 'undefined' && module.exports) module.exports = root.AgentAppearancePreview;
})(typeof window !== 'undefined' ? window : globalThis);
