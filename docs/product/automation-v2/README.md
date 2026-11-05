# CausalOps 自动化 V2 · 专项设计候选

实施记录：[第一阶段真实依赖闭环](STAGE_ONE.md) · [第二阶段持久化恢复与预算控制](STAGE_TWO.md) · [第二阶段机器证据](STAGE_TWO_EVIDENCE.json) · [第三阶段真实工作台与交付](STAGE_THREE.md) · [第三阶段机器证据](STAGE_THREE_EVIDENCE.json)。以下原专项设计保留其制定时点，不能据设计内容推断全部工作台已实现。

**2026-11-05｜基线5ac788f｜仅设计，不含功能实现**

先读[完整阅读版](index.html)，再打开[低保真交互原型](prototype.html)。原型、图示和JSON都是未来设计，不能作为已实现或实测证明。

| 交付 | 内容 |
|---|---|
| [正式专项PRD](PRD.md) | 17节：场景、规则、真实依赖、审批、恢复、预算及三个验收场景 |
| [源码可行性核查](FEASIBILITY.md) | 七项能力结论、关键函数、输入输出、调用链、最小新增接口 |
| [步骤合同示例](plan-example.json) | 5步逻辑链、两次统计调用、上游证据引用；不可直接交现有执行器 |
| [负责人确认事项](DECISIONS.md) | 已确认方向与少量待确认实现取舍 |
| [源码指纹和符号行号](SOURCE_MANIFEST.json) | 本轮实际阅读的产品文件清单 |
| [文档校验记录](DOCUMENT_CHECKS.json) | 本轮文档/原型检查，非产品工程回归 |

## 可编辑图示
- [用户流程SVG](diagrams/user-flow.svg) / [Mermaid源文件](diagrams/user-flow.mmd)。
- [状态图SVG](diagrams/state.svg) / [完整状态转移源文件](diagrams/state.mmd)。
- [架构SVG](diagrams/architecture.svg) / [Mermaid源文件](diagrams/architecture.mmd)。

SVG为适合阅读的布局，Mermaid为可编辑逻辑；状态SVG突出关键状态族，完整转移以PRD和.mmd为准。build_assets.py可重建SVG与源码清单；build.mjs从Markdown生成阅读版。两者仅写本设计目录，不导入或执行产品模块。

## 核查范围
Git工作树在开始时干净；从docs/product-prd-draft-20261105的5ac788f建立docs/automation-v2-prd-20261105。没有改动统计估计器、服务、编排、UI或历史评测。没有新模型调用、工程回归或研究验收成绩。

可行性结论：已有多统计步骤、批准、检查点和恢复底座；缺少显式依赖、每步授权、全任务预算与整体证据交付。建议固定五步链，直接复用descriptive与ab_test，首版不开放通用任务图或额外方法。

现状来源：[Beta总体PRD](../draft-v1/02_Beta总体PRD.md)、[N06专项](../draft-v1/03_N06指标变更专项方案.md)、[历史评测账本](../draft-v1/04_产品指标体系与版本路线图.md)、[营销教程](../../current/PUBLIC_TUTORIAL.md)。

本次完成后等待审阅，不自动开发、推送或创建Release。
