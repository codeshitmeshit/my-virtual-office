# Checklist: Meeting Role Motion UI

确认状态：已确认

## Items

### CHK-001: Current speaker is visually identifiable

- Requirement: A meeting participant identified as the current speaker should visibly indicate speaking in the office canvas.
- Verification method: Start or simulate an active meeting with a known current speaker and observe that participant in the canvas.
- Expected result: The current speaker has a subtle vertical speaking bob and mouth motion while the speaker state is active.

### CHK-002: Speaker mouth animation stops when speaking state disappears

- Requirement: Mouth animation should start when the participant is speaking and stop when no longer speaking.
- Verification method: Transition a meeting from a known current speaker to no current speaker, or clear the speaker state in a simulated active meeting.
- Expected result: The former speaker's mouth returns to the normal closed/idle rendering and does not continue talking from random meeting animation.

### CHK-003: Listener participants occasionally nod

- Requirement: Non-speaking meeting participants should not remain completely still; they should occasionally show a listening nod.
- Verification method: Observe a meeting while one participant is speaking for several seconds.
- Expected result: Other participants occasionally nod in a restrained way, without all listeners moving in perfect sync.

### CHK-004: Listener nods do not imply agreement

- Requirement: Listener nodding is ordinary listening feedback, not agreement, voting, or acceptance.
- Verification method: Inspect UI copy and behavior around meeting transcripts, decisions, and action items.
- Expected result: No text, badge, state, or decision logic treats nodding as approval or consensus.

### CHK-005: Participants face the current speaker naturally

- Requirement: When one participant is speaking, other participants should usually face that speaker.
- Verification method: Run or simulate a meeting with participants on both sides of a speaker.
- Expected result: Listener `facing` direction turns toward the current speaker with natural behavior; no speaker or unresolvable speaker leaves facing unforced.

### CHK-006: No forced meeting motion when no speaker is known

- Requirement: Meetings without current-speaker metadata should degrade gracefully.
- Verification method: Start or simulate an active meeting without `currentSpeaker` or pending speaker data.
- Expected result: Participants remain placed in the meeting normally, with no incorrect speaker bob/mouth animation forced onto an arbitrary participant.

### CHK-007: Existing meeting placement still works

- Requirement: Group and 1:1 meetings should keep their existing participant placement behavior.
- Verification method: Start or simulate a group meeting at the meeting table and a 1:1 visiting meeting.
- Expected result: Participants still move to expected slots or visit positions, and leave meetings correctly when the meeting ends.

### CHK-008: Non-meeting character behavior is not regressed

- Requirement: Work, idle, break, lounge, and social character animations outside meetings should keep existing behavior.
- Verification method: Observe or test agents outside active meetings after the change.
- Expected result: Existing idle/social mouth animation, facing, walking, and desk behavior continue normally for non-meeting agents.

### CHK-009: Motion remains restrained and readable

- Requirement: The animation should combine low-key office behavior with light game-like liveliness, without distracting from meeting content.
- Verification method: Manual visual review during an active meeting.
- Expected result: Bob and nod amplitudes are small, readable, and do not cause jitter, overlap, or excessive visual noise.

### CHK-010: Meeting dashboard and live meeting rendering remain intact

- Requirement: Adding canvas motion should not break meeting dashboard active cards, detail modal, transcript rendering, or live event polling.
- Verification method: Open the meetings dashboard during an active executable meeting and inspect cards, detail modal, pending calls, and transcript updates.
- Expected result: Dashboard rendering and live updates continue to work as before.

### CHK-011: Regression tests pass where applicable

- Requirement: Existing automated meeting-related behavior should not regress.
- Verification method: Run the relevant existing meeting tests or the nearest available project test subset.
- Expected result: Existing meeting tests pass, or any unrelated failures are documented with reason and scope.

### CHK-012: Manual canvas verification is documented

- Requirement: Because the main behavior is visual canvas animation, manual verification should be recorded.
- Verification method: After implementation, document the meeting scenario used, speaker transitions observed, and pass/fail result.
- Expected result: Checklist or delivery notes include manual verification covering speaker bob, mouth stop, listener nod, and facing behavior.

## 人工确认记录

- 确认项：checklist 初次确认
- 确认时间：2026-06-20T17:30:33+08:00
- 用户确认摘要：用户回复 `continue`，确认继续到下一阶段。

## 实施验证记录

- 验证时间：2026-06-20T17:42:17+08:00
- 验证命令：`node --check app/game.js`
- 验证结果：通过。覆盖前端语法检查。

- 验证命令：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`
- 验证结果：通过。输出 `ok`。

- 验证命令：`.venv/bin/python tests/test_meeting_for_ai_phase4.py`
- 验证结果：通过。测试输出 `test_meeting_for_ai_phase4.py passed`，过程中出现 Gateway WS 权限警告，但未导致测试失败。

- 验证命令：`.venv/bin/python tests/test_meeting_for_ai_phase5.py`
- 验证结果：未通过。失败点为本地 gateway advisory 状态，日志显示连接 `127.0.0.1:18789` 失败，判断为当前验证环境缺少 gateway 依赖，不是本次前端 canvas 动效代码路径直接失败。

- 验证命令：`google-chrome --headless=new --disable-gpu --no-sandbox --window-size=1280,800 --screenshot=/tmp/meeting-role-motion-ui-8100.png http://127.0.0.1:8100/`
- 验证结果：通过。8100 服务健康检查通过，生成 1280x800 PNG 截图 `/tmp/meeting-role-motion-ui-8100.png`，页面可加载且非空。

- 验证说明：已按用户要求使用 `8100` 启动服务验证。当前 headless 环境无法直接人工观察动态 speaker/nod 转场，只完成页面加载和 canvas 基础可视验证；最终动效体验仍需用户在浏览器中人工确认。

- 补充验证时间：2026-06-20T17:52:38+08:00
- 补充内容：根据用户反馈补充了可感知的转头 cue。听众 `facing` 方向变化时会触发短暂横向偏移动作，避免只是瞬间切换朝向。
- 验证命令：`node --check app/game.js`
- 验证结果：通过。
- 服务验证：已使用 `start.sh` 以真实数据目录启动 `8100/8101`，命令为 `env VO_PORT=8100 VO_WS_PORT=8101 VO_STATUS_DIR=/home/wo/code/my-virtual-office/data ./start.sh`，`/health` 返回正常。

- 补充验证时间：2026-06-20T18:00:53+08:00
- 用户反馈：会议动作看不出变化，要求调用 chrome MCP 测试。
- 验证结果：chrome MCP 当前不可用，返回 `Missing X server to start the headful browser`，无法启动 headful DevTools 页面。
- 调整内容：提高动效可见性。说话者上下浮动从约 1.5px 提高到约 2px；听众 nod 从约 2px 提高到约 3px；转头 cue 从 14 帧/约 2px 提高到 24 帧/约 5px；并且当 speaker 变化时也触发转头 cue，不再只依赖左右朝向变化。
- 验证命令：`node --check app/game.js`
- 验证结果：通过。
- 服务验证：已重新用 `start.sh` 启动真实数据 8100 服务，`app/index.html` cache-busting 已更新到 `game.js?v=1781949627-meeting-auto-continue`。

- 补充验证时间：2026-06-20T18:05:10+08:00
- 用户反馈：说话者上下浮动频率不需要太高，保持原来的浮动频率。
- 调整内容：仅将说话者上下浮动频率恢复到原来的 `agent.tick * 0.22`，保留较明显的浮动幅度、听众 nod、speaker 变化转头 cue 和 24 帧/约 5px 转头幅度。
- 验证命令：`node --check app/game.js`
- 验证结果：通过。
- 服务验证：已重新用 `start.sh` 启动真实数据 8100 服务，`app/index.html` cache-busting 已更新到 `game.js?v=1781949873-meeting-auto-continue`。

- 补充验证时间：2026-06-20T18:15:09+08:00
- 用户反馈：上下的浮动可以再小一点。
- 调整内容：将当前说话者上下浮动幅度从 `1.2px` 收小到 `0.8px`，频率继续保持 `agent.tick * 0.22`。
- 验证命令：`node --check app/game.js`
- 验证结果：通过。
- 服务验证：已重新用 `start.sh` 启动真实数据 8100 服务，`/health` 返回正常；8100 返回的 `game.js` 已确认包含 `offsetY: -0.8 + Math.sin(agent.tick * 0.22) * 0.8`。

## 最终验收记录

- 确认项：checklist 测试通过确认
- 确认时间：2026-06-20T18:15:09+08:00
- 用户确认摘要：用户回复“可以了，我验收通过了，关闭吧”，确认当前会议角色动效已通过验收。

- 确认项：最终 done 确认
- 确认时间：2026-06-20T18:15:09+08:00
- 用户确认摘要：用户要求关闭需求，确认该需求闭环完成。
