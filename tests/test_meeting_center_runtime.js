const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

function element() {
    return {
        innerHTML: '',
        textContent: '',
        lastQueryNodes: [],
        querySelectorAll(selector) {
            if (selector !== '.meeting-center-item') return [];
            const nodes = [];
            const pattern = /<button class="meeting-center-item[^"]*"[^>]+data-record-id="([^"]+)"/g;
            let match;
            while ((match = pattern.exec(this.innerHTML))) {
                const node = {
                    dataset: { recordId: match[1] },
                    addEventListener(type, callback) {
                        if (type === 'click') this.click = callback;
                    }
                };
                nodes.push(node);
            }
            this.lastQueryNodes = nodes;
            return nodes;
        },
        classList: {
            values: new Set(),
            toggle(name, enabled) {
                if (enabled) this.values.add(name);
                else this.values.delete(name);
            }
        }
    };
}

const elements = {
    'meeting-center-status': element(),
    'mtg-history-tools': element(),
    'meeting-center-list': element(),
    'meeting-center-main': element(),
    'meeting-center-controls': element()
};

const context = {
    console,
    setTimeout(callback) {
        callback();
        return 1;
    },
    document: {
        documentElement: { lang: 'zh' },
        getElementById(id) {
            return elements[id] || null;
        }
    }
};
context.window = context;

vm.createContext(context);
vm.runInContext(
    fs.readFileSync('app/meeting-center.js', 'utf8'),
    context,
    { filename: 'app/meeting-center.js' }
);

const history = [
    { id: 'meeting-a', topic: '第一场会议', status: 'completed', participants: ['a'], context: '启动资料：先看项目背景。' },
    { id: 'meeting-b', topic: '第二场会议', status: 'cancelled', participants: ['b'] }
];
const active = [
    { id: 'meeting-live', topic: '进行中会议', status: 'active', participants: ['a', 'b'], context: '实时会议原始上下文', currentRound: 1, maxRounds: 2 }
];
const requests = [
    { id: 'request-a', status: 'pending', proposal: { topic: '第一条申请' } },
    { id: 'request-b', status: 'confirmed', proposal: { topic: '第二条申请' } }
];

let currentTab = 'completed';
let renderCount = 0;

function runtime() {
    return {
        currentTab,
        data: { active, history, requests },
        agentMap: {
            a: { emoji: '🅰️', name: 'Agent A' },
            b: { emoji: '🅱️', name: 'Agent B' }
        },
        mergeLiveMeeting: value => value,
        filterMeetingHistory: values => values,
        sortRequests: values => values,
        requestProposal: request => request.proposal || {},
        renderRequestDetail: request => `<div data-request="${request.id}">request detail</div>`,
        updateRequestModeratorOptions() {},
        renderMeetingDetail: meeting => `<div data-meeting="${meeting.id}">meeting detail</div>`,
        renderMeetingTranscript: meeting => `<div data-transcript="${meeting.id}">meeting transcript</div>`,
        meetingStageLabel: stage => stage,
        structuredValue: value => String(value || ''),
        hydratePendingCall: call => call,
        requestRender() {
            renderCount += 1;
            context.MeetingCenterUI.render(runtime());
        }
    };
}

context.MeetingCenterUI.render(runtime());
assert.match(elements['meeting-center-list'].innerHTML, /meeting-a/);
assert.match(elements['meeting-center-list'].innerHTML, /data-record-id="meeting-a"/);
assert.doesNotMatch(elements['meeting-center-list'].innerHTML, /onclick=/);
assert.match(elements['meeting-center-main'].innerHTML, /第一场会议/);
assert.match(elements['meeting-center-main'].innerHTML, /原始上下文/);
assert.match(elements['meeting-center-main'].innerHTML, /启动资料：先看项目背景。/);
assert.ok(
    elements['meeting-center-main'].innerHTML.indexOf('启动资料：先看项目背景。') <
    elements['meeting-center-main'].innerHTML.indexOf('data-transcript="meeting-a"')
);
assert.match(elements['meeting-center-main'].innerHTML, /data-transcript="meeting-a"/);
assert.doesNotMatch(elements['meeting-center-main'].innerHTML, /data-meeting=/);
assert.match(elements['meeting-center-controls'].innerHTML, /第一场会议/);
assert.match(elements['meeting-center-controls'].innerHTML, /data-meeting="meeting-a"/);
assert.doesNotMatch(elements['meeting-center-controls'].innerHTML, /打开完整详情/);

elements['meeting-center-list'].lastQueryNodes[1].click();
assert.strictEqual(renderCount, 1);
assert.match(elements['meeting-center-list'].innerHTML, /meeting-center-item is-selected[^>]+meeting-b/);
assert.match(elements['meeting-center-main'].innerHTML, /第二场会议/);
assert.match(elements['meeting-center-main'].innerHTML, /原始上下文为空/);
assert.match(elements['meeting-center-main'].innerHTML, /data-transcript="meeting-b"/);
assert.doesNotMatch(elements['meeting-center-main'].innerHTML, /data-meeting=/);
assert.match(elements['meeting-center-controls'].innerHTML, /第二场会议/);
assert.match(elements['meeting-center-controls'].innerHTML, /data-meeting="meeting-b"/);
assert.doesNotMatch(elements['meeting-center-main'].innerHTML, /第一场会议/);

currentTab = 'requests';
context.MeetingCenterUI.render(runtime());
assert.match(elements['meeting-center-main'].innerHTML, /第一条申请/);
assert.match(elements['meeting-center-main'].innerHTML, /data-request="request-a"/);

elements['meeting-center-list'].lastQueryNodes[1].click();
assert.strictEqual(renderCount, 2);
assert.match(elements['meeting-center-list'].innerHTML, /meeting-center-item is-selected[^>]+request-b/);
assert.match(elements['meeting-center-main'].innerHTML, /第二条申请/);
assert.match(elements['meeting-center-main'].innerHTML, /data-request="request-b"/);
assert.match(elements['meeting-center-controls'].innerHTML, /第二条申请/);
assert.doesNotMatch(elements['meeting-center-main'].innerHTML, /第一条申请/);

currentTab = 'active';
context.MeetingCenterUI.render(runtime());
assert.match(elements['meeting-center-main'].innerHTML, /进行中会议/);
assert.match(elements['meeting-center-main'].innerHTML, /实时会议原始上下文/);
assert.ok(
    elements['meeting-center-main'].innerHTML.indexOf('实时会议原始上下文') <
    elements['meeting-center-main'].innerHTML.indexOf('meeting-center-timeline')
);

console.log('meeting center runtime interaction tests passed');
