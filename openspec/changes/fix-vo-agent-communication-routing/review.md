## 评审结论

带条件通过。方案能够修复 VO skill 来源分裂、Codex 普通聊天规则分叉、未安装到 agent workspace、OpenClaw 检测误报和通信不可追踪问题。进入实现的条件是 tasks 必须包含 managed-copy 冲突保护、非递归 legacy 迁移、symlink 边界、结构化配置异常、readiness 发送门禁、创建失败语义、兼容性测试，以及至少一次真实 OpenClaw 委派验收。

## 阻塞问题

无阻塞问题。

## 主要风险

- 稳定性：discovery 从纯读取增加为受控的 managed-skill 修复写入。必须限制在启动、定时刷新和显式创建边界，并保证单 agent 失败不破坏整个 roster。
- 数据一致性：创建与 discovery 可能同时同步同一 workspace。必须使用进程锁、内容 hash 和原子替换保证重复执行安全。
- 安全：workspace 路径来自 agent 配置。同步前必须检查 realpath 和内部 symlink，仅允许写入已确认 OpenClaw workspace 下的保留 skill 路径。
- 性能：每次 discovery 对所有 OpenClaw agents 做检查。稳态必须只读固定大小 skill/marker 并在 hash 相同时零写入。
- 兼容性：`detected` 在残留目录场景会从 `true` 变为 `false`。保留字段类型并补充 reason，不移除现有响应字段。
- 可回滚性：旧 skill 名可能仍被部分 agent 记忆。迁移顺序必须先安装 canonical，再精确删除已知 managed 文件；禁止递归删除，冲突或附加内容必须保留。
- 可观测性：同步失败若只打印日志会再次形成隐性故障。roster/workspace payload 应携带不含敏感路径的 readiness 状态，并有聚合日志。

## 关键追问

### Q: 为什么不在 VO 服务端直接禁止 `sessions_list` 和 `sessions_send`？

A: 这些工具由 OpenClaw 内部运行时执行，VO 目前只读取其活动并展示，缺少可用的 provider-neutral 拦截钩子。本方案在 VO 可控边界内确保 agent 获得 canonical skill 和明确基础规则，并通过真实 agent 验收验证行为。绝对工具禁用需要后续 OpenClaw policy 能力。

### Q: 为什么 canonical 内容直接读取仓库 skill，而不是继续在 Python 中生成？

A: 直接读取消除双写和版本漂移，保证 HTTP 暴露、Library 和 workspace 安装内容一致。代价是 canonical 文件缺失或 frontmatter 错误时必须 fail closed 并报告 readiness 错误。

### Q: 为什么 discovery 可以写 workspace？

A: 已存在的 agent 需要自动修复，单靠创建路径无法覆盖。写入被限制为低频 refresh 边界、VO 保留路径和 hash 不一致场景，并通过原子/幂等机制控制风险。

### Q: 用户修改了同名 skill 怎么处理？

A: 只有带 VO managed marker 的 canonical copy允许自动升级。未标记冲突不覆盖，返回 conflict；其他 skill 和文件完全不触碰。

### Q: Codex 是否仍需要单独的聊天 skill？

A: 不需要。`vo-agent-communication` 是普通跨 agent 聊天的统一法则，目标为 Codex 时仍查询 VO roster 并调用同一通信 endpoint。`vo-codex-communication` 不再是该普通聊天链路的运行时依赖。

### Q: 为什么 malformed `openclaw.json` 不继续扫描目录？

A: 配置存在但损坏时继续猜测身份可能把消息发给错误 agent。按“宁可不可用，也不做错”的原则返回明确 unavailable，更符合通信身份安全要求。

### Q: 对外协议是否变化？

A: send/history 协议不变；`/vo-config` 和 roster 仅增加可选诊断字段，并修正 `detected` 的语义。

## 测试与上线建议

- 为 canonical loader 验证缺失文件、错误 frontmatter、内容 hash 和 Library 精确一致性。
- 为 managed sync 验证首次安装、重复同步零写、版本升级、并发调用、未标记冲突、路径越界和保留无关 skill。
- 为 legacy migration 验证已知纯 managed 目录的精确迁移，以及未知内容、修改内容、辅助文件和 read-only list 请求均不会触发递归删除。
- 为路径安全验证 `skills` 和 canonical skill 目录的 symlink escape 均被拒绝。
- 为配置检查验证 `agents` 为字符串、数组、空值和错误嵌套结构时均返回 `malformed_config`。
- 为通信门禁验证 non-ready OpenClaw sender 被拒绝，并验证 OpenClaw 到 Codex 仍使用 canonical endpoint。
- 为 agent 创建验证 skill 成功安装和“agent 已创建但 skill 失败”的部分成功语义。
- 为 discovery 验证有效配置、无配置目录回退、skills-only 残留目录、malformed JSON 和空 agent list。
- 为通信 API 验证 roster 身份、稳定 `conversationId`、request/reply history、busy/timeout/空回复和无私有重试。
- 上线后先观察 canonical Library/agent readiness，无冲突后执行真实 OpenClaw 委派；若出现异常，回滚代码并保留已安装 canonical skill。
- 真实验收必须检查活动记录中不存在用于该委派的 `sessions_list`、`sessions_send` 或 `openclaw agents`，同时 history 能按 `conversationId` 查询完整请求与回复。
