## 评审结论

通过，等待技术方案确认。

本 change 的目标、范围和验收边界已经能支撑后续任务拆分与实现：先证明并移除 routed chat path 不使用的旧 Provider run authority，再对当前 Codex chat fast path 做低风险的二阶段性能优化。评审中发现的 OpenSpec 能力声明问题已修订：`codex-chat-fast-path` 不作为 Modified capability 声明，当前行为契约由新增 capability `chat-bridge-cleanup-and-performance` 承载。任务清单也已补充 strict OpenSpec validation 证据要求。

## 阻塞问题

无。

## 主要风险

- **稳定性**：删除 `server_services/agent_bridges.py` 中旧 run bridge 残留时，可能误伤仍被测试或罕见 direct import 使用的兼容函数。方案已要求先做 route hydration identity proof 和 direct import inventory，再删除或改为无状态薄代理。
- **数据一致性**：内部 optimized event publication 如果绕过 sanitize/copy 边界，可能造成 replay index、terminal dedupe 或 payload redaction 漏洞。方案已限定为 trusted server-side path，并要求 redaction、payload-bound、terminal-dedupe、run/conversation index、SSE replay 测试。
- **性能**：剩余优化收益预期较小，可能被 fixture 噪声淹没。方案已要求同一 deterministic fixture identity 的 before/after 证据，无法区分改善时不得声称性能验证通过。
- **兼容性**：静态 module-split tests 当前可能仍锚定旧 `ProviderRunBridge` marker。方案已要求同步替换为当前 repository/journal/coordinator/SSE transport 边界检查。
- **可回滚性**：清理废弃代码本身没有运行时开关；回滚方式主要是代码回滚。方案通过先测试证明未使用、保持 public route contracts、分离性能优化任务来降低回滚范围。
- **可观测性**：优化 telemetry 锁开销可能减少粒度。方案要求保留 first-event、first-fragment、terminal、busy、bypass、forced-flush 等关键 counters，并保持 content-free diagnostics。

## 关键追问

**Q: 为什么不把旧 `ProviderRunBridge` 直接删掉？**  
A: 删除前必须先把 routed path 的实际 handler identity 固化成测试，并盘点 direct import。这样可以区分“确实废弃”与“被非正常入口依赖”的历史残留。

**Q: 为什么不把这次 change 设成 `skip_specs: true`？**  
A: 这不是纯内部整理。它改变了 bridge 边界约束、静态检查要求和性能验收口径，需要 requirements/scenarios 作为验收事实源。

**Q: 优化 event publication 会不会绕开安全清洗？**  
A: 方案要求 public publish API 保持完全防御式 sanitize，optimized path 只接受 Codex fast path 已 bounded/sanitized 的内部 payload，并用敏感内容 canary 测试验证。

**Q: 性能成功标准是什么？**  
A: 首要标准是无兼容回归；性能标准是同一 deterministic fixture 下有 before/after 证据，报告 p50/p95/max/errors/operation counts。无法复现可区分改善时，不把优化声明为已验证。

**Q: 如果发现 direct import 依赖旧 service-local 行为怎么办？**  
A: 优先迁移到 routed/hydrated contract 或当前 Provider services。只有必要的兼容函数名可以保留，但必须是无状态薄代理，不能保留第二套 run authority。

## 测试与上线建议

- 将 route hydration identity proof 作为第一个实现任务的准入测试。
- 在删除旧 authority 前后分别运行 Provider service boundary、Codex runs bridge、Claude Code runs SSE、Provider chat SSE、server/frontend module split 静态检查。
- 对 optimized publication path 增加 redaction canary、payload bound、terminal dedupe、run/conversation replay index、SSE reconnect 测试。
- 运行 deterministic Codex chat fast-path performance harness，保存同 fixture 的 before/after 证据。
- 最终证据必须包含 `openspec validate optimize-chat-performance-cleanup --strict`。
- 对 real Provider、browser CDP 或外部环境依赖项，只能记录为已验证或未验证，不得用 deterministic fixture 代替真实环境结论。
