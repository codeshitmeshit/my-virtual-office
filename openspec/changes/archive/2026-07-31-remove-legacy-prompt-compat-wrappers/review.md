## 评审结论

通过。该 change 是前序 prompt bridge 迁移后的边界收敛：把运行时和测试从 `server.py` 私有兼容 wrapper 迁到主函数/服务模块，方向符合降低耦合和防止旧入口回潮的目标。

用户补充“必要时拆 `server.py`”后，方案仍可通过：拆分范围应限定在 prompt-wrapper-adjacent runtime ownership，避免把本 change 扩张成无边界的 monolith 重构。

## 阻塞问题

无当前阻塞问题。

## 主要风险

### 稳定性

- `server.py` 与 `server_services.*` 存在 hydration 机制，若只删除 wrapper 而未处理 hydration 覆盖，可能让 split service 的主函数被旧全局覆盖。
  - 建议：每个 wrapper group 迁移后用静态搜索和 focused test 验证实际 runtime owner。

### 兼容性

- 部分测试可能混合“prompt 文本断言”和“server 集成行为”，直接搬到 service 层可能丢失集成覆盖。
  - 建议：prompt-only 断言迁 service；真正验证 provider dispatch / public route 的测试保留 server 集成路径。
- 从 `server.py` 抽出 runtime ownership 时，可能改变全局依赖注入和 hydration 行为。
  - 建议：优先复用现有 `server_services.*` 模式；抽取前后用 focused tests 覆盖 provider/project/workflow/archive 相关路径。

### 数据一致性

- 本 change 不应修改持久化数据；主要风险来自误触碰项目/工作流执行代码。
  - 建议：只改调用点和测试入口，不改状态流、项目记录结构或 provider reply parser。

### 安全

- 删除 wrapper 不应削弱 untrusted boundary。
  - 建议：迁移后继续跑 low-level formatter direct-use 静态测试和 prompt escaping tests。

### 可观测性

- wrapper 删除本身没有新监控需求，但需要清晰 evidence 说明哪些 wrapper 删除、哪些保留。
  - 建议：任务证据里记录 wrapper inventory diff。

## 关键追问

### Q: 为什么不直接删除所有 `server.py` 私有 prompt wrapper？

A: 部分运行时路径和 split-service hydration 仍可能按历史名称查找函数。规格要求先迁调用点和测试，再删除无调用 wrapper；仍必要的 wrapper 必须是薄 delegate 并记录移除条件。

### Q: “必要时拆 `server.py`”的边界在哪里？

A: 只拆 wrapper 清理直接触达的 prompt/provider/project/workflow/archive 小片段。若牵涉大规模路由、状态存储、provider lifecycle 或 UI/API 改造，应保留薄 delegate 并单独开后续 change。

### Q: 为什么测试也必须迁到主函数？

A: 如果测试继续直接调用 `server._*` wrapper，wrapper 就会因为测试依赖长期存在，主函数所有权无法落实。prompt-only 测试迁到主函数后，server-level 测试只保留真正的集成覆盖。

### Q: 如何避免误删仍有动态调用的函数？

A: 通过 `rg` 静态搜索、focused regression、以及按 wrapper group 分步删除。发现无法证明无 runtime caller 的 wrapper 时保留薄 delegate，并记录原因和移除条件。

## 测试与上线建议

- 增加/更新静态测试，禁止 prompt-only tests 继续调用已迁移的 `server._*` private prompt wrappers。
- Provider/platform delivery：验证 Feishu group prompt、VO guidance、agent platform message prompt 仍保留安全边界和 provider dispatch 行为。
- Archive：验证 archive context/refine prompt helper 由 archive prompt module 负责。
- Project/workflow：验证 execution/review/task/rework prompt helper 由 prompt formatting modules 负责，hydration 不回退到 server wrapper。
- `server.py` extraction：对被抽出的 wrapper-adjacent runtime owner 增加或迁移 focused tests，证明公共行为保持兼容。
- 运行 strict OpenSpec validation 和 focused pytest；不声明 prompt 行为改善，只声明所有权边界收敛与兼容通过。
