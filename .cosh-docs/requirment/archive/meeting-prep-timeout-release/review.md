# 方案评审

## 产品澄清结论

需求目标清楚：准备中的会议如果超过配置时长仍未开始，应自动释放，默认 5 分钟，配置单位秒。当前不需要继续产品澄清。

采用以下产品假设：

- “释放”定义为：会议不再占用参会 Agent，不再出现在活动会议中阻塞新会议；会议状态转为可解释的终态，推荐使用 `cancelled` 并记录 reason 为 `preparing_timeout`。
- 配置默认值为 300 秒。
- 设置项允许用户修改秒数；为避免误操作，建议最小值不低于 30 秒。若需要支持 0 表示关闭自动释放，需在 checklist 确认前明确，否则默认不支持关闭。
- 释放后用户可以从历史或详情中看到会议被系统因准备超时取消。

## 技术评审

### 架构

现有可执行会议状态集中在 `app/server.py`，前端会议中心由 `/api/meetings/active`、`/api/meetings/executable/<id>` 和 transition/run API 驱动。准备态超时属于会议生命周期规则，应优先放在后端，前端只负责配置和展示。

推荐增加后端 helper：

- 读取配置：`_meeting_preparing_timeout_sec()`。
- 判定超时：`_meeting_preparing_timed_out(meeting, now, timeout_sec)`。
- 执行释放：`_release_timed_out_preparing_meetings(store, now=None)`。

惰性执行入口建议覆盖：

- `_meeting_active_projection()`：刷新会议列表时自动清理。
- `_handle_executable_meeting_detail()`：打开详情时自动清理。
- `_handle_executable_meeting_run()`：启动会议前先清理并重新读取，避免过期会议被启动。
- `_handle_executable_meeting_reconcile()`：保留显式修复能力。

### 数据和状态流

会议创建时已有 `createdAt` 和 `updatedAt`。准备态超时建议以 `createdAt` 或进入 `preparing` 的时间为基准。为了兼容从 conflict 解决后进入 `preparing` 的会议，推荐新增或维护 `preparingStartedAt`：

- 创建无冲突会议时设置 `preparingStartedAt = now`。
- 冲突被解决并进入 `preparing` 时设置 `preparingStartedAt = now`。
- 从 paused 恢复到 preparing 时设置 `preparingStartedAt = now`。
- 旧数据缺少该字段时回退 `createdAt`。

超时后：

- 将 `stage` 置为 `cancelled`。
- 设置 `cancelReason` 或 `timeoutReason = "preparing_timeout"`。
- 设置 `timedOutAt` 和 `preparingTimeoutSec`。
- 从 `occupancy` 移除该会议的所有参会者占用。
- 追加 `meeting_transitioned` 或专用 `meeting_preparing_timed_out` 事件。

### 配置

设置项可保存到现有 `vo-config.json`。建议结构为：

```json
{
  "meetings": {
    "preparingTimeoutSec": 300
  }
}
```

配置读取需要支持缺省值和非法值兜底：

- 缺省：300。
- 非数字、负数：回退 300。
- 小于最小值：夹到最小值或回退 300。
- 最大值建议限制，例如 86400 秒，避免极端配置。

### 权限和安全

该设置属于本地办公室配置，沿用现有设置保存权限即可。超时释放是系统行为，不应由未授权外部请求绕过；API 层维持现有访问模型。

### 异常处理

- 如果清理过程中会议已经处于终态，跳过。
- 如果 occupancy 中某个 Agent 已被其他会议占用，不能误删其他会议占用；只在 `occupancy[agent] == meeting_id` 时移除。
- 如果会议缺少 `createdAt`、`preparingStartedAt` 或时间格式异常，应保守跳过或使用 `updatedAt`，不能抛出导致列表 API 失败。
- 重复执行释放应幂等，不重复添加多条超时事件。

### 兼容性

旧会议缺少 `preparingStartedAt`、`preparingTimeoutSec`、`cancelReason` 等字段时仍可读取。前端 i18n 需要补充中英文文案。

### 可观测性

建议在事件中记录：

- 超时时间。
- 配置秒数。
- 基准时间。
- 释放的参与者。
- actor 为 `system`。

前端可展示“准备超时已释放”或历史状态说明，便于用户理解。

### 测试可行性

可以通过构造测试 store 中的会议时间戳来稳定验证，无需真实等待 300 秒。前端设置可通过 DOM/API 测试或手工浏览器验证。

## 阻塞问题

无阻塞问题。需求可以进入 checklist 确认阶段。

## 建议决策

1. 默认 `preparingTimeoutSec = 300`。
2. 以 `preparingStartedAt` 为主、`createdAt` 为兼容回退。
3. 超时释放使用 `cancelled` 终态，并记录 `cancelReason = "preparing_timeout"`。
4. 不支持 0 关闭，除非用户明确要求；若后续要求支持关闭，需要更新 checklist 后重新确认。
