# 主动研究诊断与证据质量评估

当前本地工程状态：P1 第三阶段已完成现有诊断事实层与三层报告的真实 Streamlit 集成。用户显式发起研究条件／研究证据检查，查看风险和依据，保存无执行权限需求草案及重新打开历史版本。六项规则已实现，其余八项未实现；模型解释与自动执行建议继续关闭。尚未公开发布。

**当前能力与实测以[第三阶段报告](STAGE_THREE.md)及[浏览器证据](stage3-evidence/browser-results.json)为准。** 下列完整设计范围不全部代表已实现能力。

## 已完成阶段与保留证据

1. [第一阶段：只读诊断事实层](STAGE_ONE.md) · [A/B/C 服务验收](stage1-evidence/summary.json) · [工程测试](stage1-evidence/engineering-results.json)。
2. [第二阶段：同源三层报告与受控建议](STAGE_TWO.md) · [实际报告 Schema](stage2-evidence/report-v1.schema.json)。
3. [第三阶段：诊断工作台与交互验收](STAGE_THREE.md) · [报告与草案](stage3-evidence/reports.json) · [测试记录](stage3-evidence/engineering-results.json)。
4. [第三阶段真实页面截图](stage3-evidence/README.md)，与下方低保真设计稿明确分开。
5. 既有统计执行、安全门禁、人工审核及历史结果继续使用原服务；诊断和需求草案不授予执行权限。

## 设计基线（历史候选保留）

公开 Beta 0.17.0b1 / f9e876a；专项设计提交 f150ef8。以下文件保留先前设计与原始 Schema，包含尚未实现功能。

1. [完整专项 PRD](PRD.md)。
2. [源码可行性与能力对照](FEASIBILITY.md)。
3. [14 项设计规则](RULES.md)。
4. [设计合同](CONTRACTS.md)；第一阶段实际合同为 [Finding v1.1](stage1-evidence/finding-v1.1.schema.json) 和 [Assessment v1.1](stage1-evidence/assessment-v1.1.schema.json)。
5. [低保真交互原型](prototypes/index.html)与[设计预览](previews/README.md)：仍为历史设计稿，不能代替第三阶段真实页面证据。
6. [完整验收场景设计](ACCEPTANCE.md) · [设计取舍](DECISIONS.md)。
7. [先期源码位置](SOURCE_MAP.md)、[历史哈希](SOURCE_AUDIT.json)、[先期文档检查](REVIEW_NOTES.md)。

不修改历史评测、正式研究数据及原评分。不把工程、服务或固定浏览器结果称为真人使用成绩。
