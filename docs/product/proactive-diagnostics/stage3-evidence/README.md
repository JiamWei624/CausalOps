# 第三阶段实际运行证据

本目录只归档公开 Hillstrom 与合成研究的必要机器记录、真实页面截图和可见文本。不包含数据库、私人研究资料、API 密钥或原始私有评测会话。

- [阶段报告](../STAGE_THREE.md)：版本、实际功能、首次失败、最终复验和限制。
- [浏览器逐次事件](browser-results.json)：三类场景展开为八条固定流程，不是自由探索或真人测试。
- [页面状态采样](state-samples.json)：实际时间戳、所选与已渲染身份、可见性；不能视为连续视频。
- [各批首次与最终摘要](browser-attempt-history.json)：保留失败，不只记录最终通过。
- [报告与草案](reports.json)：最终浏览器实际读取的结构化报告、草案及旧门禁拒绝核对。
- [原生步骤证据](A-native-evidence.json)：当前成功案例 S02、S03、S04、S05 的实际持久化证据。
- [历史与保护指纹](history-and-preservation.json)：原生统计、任务、计划及审批前后一致；原成功报告版本保留。
- [原流程浏览器回归](original-workflows.json)。
- [工程逐测试结果](engineering-results.json)：定向、受影响及完整运行范围重叠，不相加。
- [源码与环境](source-and-environment.json)。
- [原始失败日志收据](initial-failure-receipts.json)与[本轮文件及保护范围检查](review-checks.json)。

## 实际页面

|页面|截图及同时保存的可见文本|
|---|---|
|风险与来源|[截图](screenshots/A-risk.png) · [文本](screenshots/A-risk.txt)|
|研究结果|[截图](screenshots/A-results.png) · [文本](screenshots/A-results.txt)|
|证据质量|[截图](screenshots/A-quality.png) · [文本](screenshots/A-quality.txt)|
|建议层：未生成建议|[截图](screenshots/A-suggestions.png) · [文本](screenshots/A-suggestions.txt)|
|原始运行证据|[截图](screenshots/A-original-evidence.png) · [文本](screenshots/A-original-evidence.txt)|
|无 Run 的预诊断|[截图](screenshots/B-preflight.png) · [文本](screenshots/B-preflight.txt)|
|显式保存需求草案|[截图](screenshots/B-draft.png) · [文本](screenshots/B-draft.txt)|
|建议来源过期|[截图](screenshots/B-stale-source.png) · [文本](screenshots/B-stale-source.txt)|
|窗口冲突|[截图](screenshots/C-window-risk.png) · [文本](screenshots/C-window-risk.txt)|
|跨任务证据|[截图](screenshots/C-foreign-evidence.png) · [文本](screenshots/C-foreign-evidence.txt)|
|哈希损坏|[截图](screenshots/C-hash-evidence.png) · [文本](screenshots/C-hash-evidence.txt)|
|历史任务切换后|[截图](screenshots/history-switch.png) · [文本](screenshots/history-switch.txt)|

截图来自当前实际 Streamlit 页面，没有以原型或设计稿代替。完整失败日志、DOM、独立工作区及原始 JUnit 保留在本地 QA 归档；此目录的哈希用于对照原始文件，不含开发机绝对路径。
