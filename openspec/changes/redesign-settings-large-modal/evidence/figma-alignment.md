# Figma 行为校准证据

## 节点

- 大弹窗主视觉：[系统设置 · 大弹窗](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=334-240)
- 点击与交互：[系统设置 · 交互全景](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=338-240)
- 数据与保存：[系统设置 · 存储与提交](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=338-249)

## 2026-08-09 校准结果

- 主视觉保留 960 × 680 弹窗、稳定 header/nav/content/footer 与原有深色视觉体系；七分类修正为 Connections & Agents、Office、Display、Tools & Browser、Notifications、Storage、Advanced。
- Footer 中删除额外 Cancel 控件，只保留原关闭入口和全局 Save Settings；导航说明改为“分类切换只改变展示，各按钮仍按当前保存边界执行”。
- 交互板删除 dirty-close、backdrop close、Escape close、save-and-close、discard、continue editing、restore defaults 与 view changes 等本期不存在的动作。
- 点击清单改为当前 handler 的真实行为：OpenClaw、Hermes、Codex、Claude Code、PC Metrics、CDP、Viewer 保留先保存再测试；天气与 SSE 保持纯测试；飞书通知、飞书 Chat、OSS 保留独立 action。
- 状态图改为 Closed → Open → Editing → Saving/Testing → Success/Error，明确不引入统一 dirty state。
- 存储板删除 SettingsDraftStore、Coordinator 和原子提交设想，改为现有原 DOM、稳定 ID 与 action handler 权威。
- 全局保存顺序改为当前实现：收集 → 先写 localStorage 并应用字号 → 构造配置 → POST `/setup/save` → 成功反馈；服务端失败不回滚已经写入的本地偏好。
- 关闭行为明确为不自动关闭，由 `toggleMainMenu()` 保持现有生命周期。

## 视觉复核

- 三个节点均以原始画布尺寸重新渲染检查。
- Noto Sans SC 字体族保持不变，未出现缺字、文字裁切、卡片溢出或重叠。
- 主弹窗七个导航项均可读，Tools & Browser 未挤压边界；隐藏 Cancel 后 Save Settings 仍保持右对齐。
- 两张说明板的长文仍位于各自卡片内，状态流与保存顺序从左到右可读。

