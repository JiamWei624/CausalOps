# CausalOps 研究界面、统计展示与执行边界复核
2026-11-03 · 0.16.0 源码修订 · 基线提交 aea7bbc · 本记录对应源码与界面复核

## 复核范围与设计取舍

审计开始时发布工作树清洁。设计包的 30 个编号覆盖界面、文档和研究流程。实施依据为实际入口、字段合同、审批与执行路径、已保存证据和公开数据运行。原始设计稿留在审阅目录。本文图片来自本轮运行或按代码绘制。

| 设计编号 | 核实结果 | 实际处理 |
|---|---|---|
| 01、02、10–12 | 首页已有真实的示例与可选模型连接；仓库首页原先先列安装命令 | 先展示产品、核心任务、公开示例和截图，再给出流程、架构、安装与限制。应用首页并列导入和查看已有任务，保留可选模型设置 |
| 03、04、24 | 陌生表不能根据列顺序判定处理、结果和分析单位。缺少编排依赖的导入回退路径曾主动批准描述分析 | 移除旧上传入口的列序推断。未指定角色时不创建初始草案；专业分析的方法、指标类型由使用者选择。导入阶段只登记并检查数据，展示实际文件名 |
| 05、06、17、21、25 | 版本差异、人工中断、版本绑定、历史运行已经实现 | 保留服务端门禁。任务摘要显示相应计划版本；结果区注明报告对应的计划与运行。演示页用真实状态替代固定进度百分比 |
| 07–09、18、29 | 两个字段仍绘制含重复信息的四格矩阵，专业入口把图排在明细表之后 | 两变量展示 Pearson、Spearman 和成对有效数；多变量保留矩阵。主图移至结论之后。无估计区间时不标为区间图。历史汇总未保存散点坐标，不从相关系数生成模拟点 |
| 13–16、19、20、22、26、27 | 权限、方法检索与运行证据已有分工 | 在[图集](FIGURES.md)中分开呈现。复杂度较高的图保留在技术说明，首屏不堆叠方法和协议名 |
| 23、28、30 | 后台停止、恢复与重试已有状态机制 | 保留现有实现，运行回归套件并实测双标签读取与刷新。未把模拟或自动化操作计为独立用户研究 |

**未采用的设计。** 不把模拟数值当作结果卡片，不预填研究者未确认的分配机制，不新增无后端处理的按钮。窄屏保留单列的审核与阅读顺序。旧运行保留其原始设置；本次不会回填或重新批准既有历史设计。

## 实际操作与截图

| 页面 | 实际操作 | 核对点 |
|---|---|---|
| [首页](../assets/review-home.png) | 本机打开公开预览 | 导入、继续任务、示例与可选模型连接 |
| [数据导入和工作台](../assets/review-workspace.png) | 载入 UCI 红葡萄酒数据 | 原表 1,599 行、12 列，保留数据来源与统计口径 |
| [待审计划](../assets/review-approval.png) | 选择已有明确问题、使用公开示例说明生成计划 | 确认框未勾选时批准按钮禁用；勾选并提交后才生成对应报告 |
| [分析结果](../assets/review-result.png) | 显式生成描述统计并定位到结果 | 研究问题、指标、范围、主图与报告操作 |
| [离线报告](../assets/review-report.png) | 点击导出并在浏览器中打开下载文件 | 结论、样本限制和图表使用已保存的运行 |

## 本轮验证

- 在独立工作区启动修改后的源码，使用本地模式。运行完整 pytest 套件，630 项通过。覆盖估计器、权限、报告、历史绑定、拒绝旧批准、恢复与重复请求等路径。
- 新增三项回归样例。常量与部分缺失、无穷值的数据检查系数和图文一致性；任意上传表检查空角色、同一字段冲突和显式确认后的草案。
- Edge 实际操作涵盖载入示例、首份报告、方案人工审核、下载、同一任务的第二个浏览器标签及页面刷新。390 CSS 像素宽首页的文档宽度为 390 像素。此项限于首页。
- 合成政策示例每组场景各有 3,240 条实际估计记录。正常趋势场景估计约 1.783，解释等级为受限准实验；异常趋势场景仍可得到约 3.583，但结果限于关联。该数据来自教学生成器，不能外推为真实政策效果。
- 11 张技术图由浏览器实际渲染为 PNG，核对 SVG 文字视口边界。可编辑关系定义随文提供，其中操作图及架构图沿用本轮开始时已核对的图源。
- 固定种子脚本重跑 90 次拟合，独立公式复算 A/B 均值差和标准误。下表分母是每种方法本次的模拟次数。与旧记录使用同一组种子，不合并为更大的样本。

| 方法 | 重复次数 | 平均偏差 | 区间覆盖次数 |
|---|---:|---:|---:|
| ab_test | 30 | 0.0097 | 29/30 |
| cuped | 30 | 0.0158 | 29/30 |
| did | 12 | 0.0016 | 12/12 |
| double_ml | 6 | -0.0518 | 6/6 |
| psm | 6 | -0.0850 | 4/6 |
| ipw | 6 | -0.0238 | 6/6 |

### 复现命令

在仓库根目录及已安装依赖的 Python 3.11 环境运行。临时目录与统计输出目录应使用空的测试专用目录。

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m pytest -o addopts= -q -p no:cacheprovider --basetemp E:/causalops-review-tests
python tests/test_statistical_benchmark_v016.py E:/causalops-review-benchmark
```

## 边界与后续优先级

1. 当前 PSM 的配对差标准误以匹配结果为条件。本轮 4/6 的覆盖结果仅构成复查信号，尚不支持对长期覆盖率作精确判断。[估计、卡尺及推断说明](STATISTICAL_AUDIT.md)
2. 双标签只实际操作了同一报告的读取；双人同时批准、操作系统强杀时的前端交互、不同浏览器的完整窄屏流程还未做真实使用者验收。服务端的重复提交和旧版本门禁另有回归测试。
3. 本轮不使用第三方模型密钥，没有重新开展付费模型任务评测。历史结果复核、模型权限和公共示例本地运行属于不同的验收项。
4. 完整独立统计复核与首次使用者评测另行开展。优先用不同种子和不同重叠条件验证 PSM，再安排用户独立完成导入、审核、解读和导出。源码修订未打包为新发行版。

## 文件清单

- `README.md`
- `docs/HISTORY.md`
- `docs/assets/README.md`
- `docs/assets/rag-evidence-current.svg`
- `docs/current/ARCHITECTURE.md`
- `docs/current/COMPLETE_MANUAL.html`
- `docs/current/COMPLETE_MANUAL.md`
- `docs/current/PUBLIC_TUTORIAL.md`
- `docs/current/REAL_DATA_EXPERIENCE.md`
- `docs/current/STATISTICAL_AUDIT.md`
- `docs/current/TUTORIAL.html`
- `docs/diagrams/README.md`
- `src/causalops/application/research_report.py`
- `src/causalops/application/task_conclusions.py`
- `src/causalops/general/exploration.py`
- `src/causalops/general/exploration_report.py`
- `src/causalops/help/manual.html`
- `src/causalops/ui/app.py`
- `src/causalops/ui/assistant_app.py`
- `src/causalops/ui/exploration_app.py`
- `src/causalops/ui/general_app.py`
- `src/causalops/ui/graph_app.py`
- `src/causalops/ui/portfolio_demo.py`
- `src/causalops/ui/research_quality.py`
- `src/causalops/ui/showcase_support.py`
- `src/causalops/ui/showcase_widgets.py`
- `src/causalops/ui/workbench.py`
- `tests/test_ui.py`
- `docs/assets/architecture-current.png`
- `docs/assets/review-acceptance.png`
- `docs/assets/review-acceptance.svg`
- `docs/assets/review-approval.png`
- `docs/assets/review-charts.png`
- `docs/assets/review-charts.svg`
- `docs/assets/review-design.png`
- `docs/assets/review-design.svg`
- `docs/assets/review-evidence.png`
- `docs/assets/review-evidence.svg`
- `docs/assets/review-home.png`
- `docs/assets/review-lineage.png`
- `docs/assets/review-lineage.svg`
- `docs/assets/review-permissions.png`
- `docs/assets/review-permissions.svg`
- `docs/assets/review-quality.png`
- `docs/assets/review-quality.svg`
- `docs/assets/review-recovery.png`
- `docs/assets/review-recovery.svg`
- `docs/assets/review-report.png`
- `docs/assets/review-result.png`
- `docs/assets/review-versions.png`
- `docs/assets/review-versions.svg`
- `docs/assets/review-workspace.png`
- `docs/assets/task-workflow-current.png`
- `docs/current/DESIGN_REVIEW.md`
- `docs/current/FIGURES.md`
- `docs/diagrams/review-acceptance.mmd`
- `docs/diagrams/review-charts.mmd`
- `docs/diagrams/review-design.mmd`
- `docs/diagrams/review-evidence.mmd`
- `docs/diagrams/review-lineage.mmd`
- `docs/diagrams/review-permissions.mmd`
- `docs/diagrams/review-quality.mmd`
- `docs/diagrams/review-recovery.mmd`
- `docs/diagrams/review-versions.mmd`
- `tests/test_design_review.py`
