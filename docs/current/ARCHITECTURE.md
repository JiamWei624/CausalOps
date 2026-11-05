# 系统架构 · CausalOps 阶段性公开测试版

应用包0.17.0b1。当前候选来自第三阶段f568f3e；新增受限固定自动化，旧单次LangGraph路径保留。软件不是通用自主规划系统。

## 受限自动化执行路径（当前实现）

Streamlit automation_app → ResearchService.automation_v2 → BoundedCoordinator。PlanV2静态计划与动态步骤记录分开；整体人工批准绑定数据、DataContract、完整步骤、配置与哈希。AutomationJobs复用后台线程，逐步授权后调用原注册工具与研究域门禁。

固定链：S01审计→S02描述Run→S03持久结果/哈希核验→S04 A/B Run→S05事实报告。正式计算只有两次，不把审计或页面状态当统计步骤。automation_results.snapshot有界重读，report_html在同一HTML内绑定任务、指标、计划与两个Run。SQLite/Parquet及原结果文件仍为统计事实来源，没有第二套统计数据库。

automation_budget记录实际模型请求、工具尝试与预算事件；固定计划模型授权为0。暂停在安全边界生效，取消终态，恢复核对所有权、批准、输入、已有Run和预算。无法证明安全时暂停人工核查，不盲目重算。

核心文件：application/automation_contracts.py、automation_coordinator.py、automation_budget.py、automation_results.py、background.py；ui/automation_app.py。完整设计与三个阶段见[自动化文档](../product/automation-v2/README.md)，实际安装与浏览器结果见[本次验收](../releases/automation-v2-beta/ACCEPTANCE.md)。

以下组件图及单次路径继续适用；图中LangGraph不是固定自动化的必经路线。可选DeepSeek不等于每次研究必须调用模型。

[查看研究质量、权限、恢复和运行证据图](FIGURES.md)

## 组件与调用关系

下图展示本地工作台的主要调用关系。研究服务接收界面请求，编排模块组织方法检索与计划审核，统计内核承担已批准的计算。部署约束、源码入口与扩展接口分别列于下文。

![本地组件与外部模型服务的调用关系](../assets/architecture-current.svg)

## 交互入口

首页提供导入与三级案例入口。营销实验通过公开文件指纹与组内计数核验后，复用研究服务建立口径与待审方案，只有收到人工批准后才能执行组间比较。[数据与验收](PHASE2_ACCEPTANCE.md)

首页可配置模型，完整连接默认收起；导入后自动显示本地概览与建议。上传后分为字段概况、问题发现（explore）、待审计划和运行解释四种不同产出。基础报告复用 ResearchService，但入口严格限制为描述统计，显式按钮触发批准；模型不获得批准接口。连接与密钥放在非 widget 的内存状态中，数据任务仍独立授权。

## 从输入到结果

Streamlit → ResearchService → 安全字段与冻结DataContract → 结构化路由 → LangGraph方法研究子图 → 待审Plan与就绪检查 → interrupt → 使用者批准 → TaskRuntime与原统计执行器 → ToolResult → 主要运行结论、证据问答和报告。

结构化路由可读取数据类型及已登记口径，选择最少必要的主要分析。它不接收方法键名形式的测试答案，不确认人工事实。计划若更换已登记的结果或变量集合，进入有限修复或要求使用者先更新字典。

方法子图使用LangChain Core检索适配。通用检索不足时，以注册方法名称和原问题定向补检；最多三轮，停止条件包括依据齐备、没有新依据、达到预算或方法尚不支持。规则卡与实证案例分开。

## 发布入口与公共示例

统一启动器默认使用 8513，输出含 release/build 的地址；页面显示实际版本和源码构建指纹。重启核对进程归属与活动任务，不关闭其他程序。葡萄酒示例通过包资源读取并校验 SHA-256，载入后建立常规任务，不继承模型外发许可、研究事实或执行批准。作者历史示例默认隐藏，需显式本地开关启用。结果页的快捷追问只查询选定运行，不建立新估计。

营销案例页由 `ui/marketing_case.py` 收集来源确认，`sample_data/hillstrom.py` 校验指定原始压缩包、筛选两组并生成分析字段，再使用既有研究服务保存口径与待审计划。政策示例使用固定种子的合成面板，分别演示不同处理前趋势下的诊断与解释边界。

## 代码职责

| 模块 | 职责 |
|---|---|
| ui/model_setup.py | 首页连接、内存密钥与任务级外发许可 |
| application/onboarding.py | 显式限权的基础报告，版本核对与复用 |
| application/question_discovery.py | 安全字段问题建议、字段校验与明确本地兜底 |
| application/conversation.py | 同任务冻结上文、建议序号解析与安全历史上下文，不继承审批 |
| application/research_service.py | 统一服务、数据/计划/字典绑定和审批验证 |
| orchestration/research_graph.py | 持久主图、审核中断、主要结果选择 |
| orchestration/method_research.py | 有限补检与方法条件检查 |
| integrations/method_retriever.py | 实际LangChain Core Retriever适配与方法过滤 |
| application/data_contracts.py | 不可变人工数据口径版本 |
| application/task_readiness.py | 安全口径投影、字段一致性和具体缺项 |
| application/background.py | 本地后台排队、停止与恢复 |
| assistant/contracts.py | 17项方法注册表与三类工具适配 |
| application/task_conclusions.py | 由保存运行和来源字典生成量化结论 |
| application/answer_evidence.py | 有界事实选择和保守解释检查 |
| assistant/service.py | 候选与运行事实、模型合同及引用校验 |

## 数据、状态与权限

SQLite保存任务、字典、候选、审批、后台状态和图检查点；Parquet保存本地数据副本。图状态保存引用，不保存原始行或密钥。候选配置、人工声明、检索依据与统计结果分别保存。

审批绑定具体数据、字典、计划、知识库和代码指纹。LangGraph恢复信号不是批准；ToolGateway仍验证领域批准。新字典不能静默改变旧运行，模型不能自行接受、批准或执行。

后台是单线程本地队列，并非分布式执行或任意代码沙箱；数值程序来自原已验证内核。MCP保留只读导出工具，A2A是本地规则审阅服务，均不等于多模型自主研究。

## 冻结版本的研究请求调用路径

以下以营销邮件研究为例。表中源码均位于 `src/causalops/` 下。[隔离安装实测和已知风险](../stage/验收与整合.md)

| 顺序与源码入口 | 输入与输出 | 设计理由与边界 |
|---|---|---|
| 1. Streamlit 的 `ui/workbench.py` 进入 `ui/marketing_case.py:render` | 原始 gzip → `sample_data/hillstrom.py:cohort` 校验指纹及两臂样本 → `ResearchService.create_task` | 案例预览可以直接阅读，实际报告需由新的任务生成。用户自有表另走普通上传。 |
| 2. `application/data_contracts.py:DataContract、ContractRepository.save` | 分组、结果、指标窗口、分析单位及来源声明 → 有版本的数据字典 | 字段类型本身不足以证明随机化。更新字典需要重新核对依赖的计划。 |
| 3. `application/research_service.py:ResearchService.start、decide_route` → `orchestration/research_graph.py:build_graph` | 问题、数据绑定、可选历史运行 → 新的流程编号、路由和引用 | 图的状态记录引用和步骤。区分计划与结果追问仍有误路由案例。 |
| 4. `orchestration/method_research.py:build_method_graph` → `integrations/method_retriever.py:MethodRetriever` | 问题、候选方法 → 本地知识目录的方法卡及来源 | 采用有界检索，以便限制缺证时的补检次数。未做全领域文献召回率验证。 |
| 5. `llm/providers.py:ProviderConfig、StructuredModelClient`、`llm/deepseek.py:DeepSeekStructuredModelClient` 与 `ui/model_setup.py` | 授权的字段和研究上下文 → 模型建议或解释 | 密钥和任务外发许可分开。选择本地模式即可完成本教程。结构有效不能保证研究结论正确。 |
| 6. `application/task_readiness.py:plan_readiness、check_declared_roles` → `ResearchService.review` | 待审步骤、绑定的数据与计划指纹、用户确认 → 批准、阻断或修订 | 审核中断让使用者确认真实业务条件。旧研究仍绑定原版本。 |
| 7. `ToolGateway.execute` → `assistant/contracts.py:AnalysisTools.method、REGISTRY` → 探索、研究或进阶工具 | 批准版本、方法、字段 → 运行和统计证据 | 白名单按工具核对方法。描述、因果与局部推断的必要条件不同。 |
| 8. `general/service.py:GeneralWorkspace` 与 `assistant/service.py:AssistantWorkspace` | SQLite 保存研究/审批等记录，工作区文件保存表格与运行产物；`completed_runs` 查成功运行，`bundle` 读证据 | SQLite、Parquet 等本地持久化便于复核；共享或并发多租户部署不在验证范围。 |
| 9. `application/report_scope.py:match_requested_report`、`application/metric_semantics.py:semantic_answer`、`application/aggregation_evidence.py` | 用户所指运行、统计量、单位与窗口 → 有出处的回答或缺项说明；`ui/assistant_app.py:make_report` 生成报告 | 检查分母含义与分组证据；复杂自然语言仍可能漏答。历史查询先确认所选运行。 |
| 10. `evaluation/v1、v12、v13` 与 `scripts/eval_v20/` | 隔离任务、公开或合成输入 → 各层记录、独立评分与失败原因 | 服务评分、浏览器行为和官方模型回执分别报告。真实用户试用另行开展。 |

## 官方技术依据

- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)：持久暂停和恢复机制。
- [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)：编译子图与共享状态通道。
- [Streamlit fragment](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)：局部刷新。
- [Python 3.11 futures](https://docs.python.org/3.11/library/concurrent.futures.html)：线程任务与取消边界。
- [Statsmodels GLM](https://www.statsmodels.org/stable/generated/statsmodels.genmod.generalized_linear_model.GLM.html)：二元/计数关联拟合。
- [Scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)：信息泄漏与不当评估的基本边界。

## 结果解释的两项约束

模型问答只读取当前运行事实；候选阶段的旧数字与旧引用不作为本轮数值依据。短引用在渲染与保存前恢复完整证据ID。当前已执行诊断、来源口径及实际人工声明优先于候选阶段的待确认问题清单，失败诊断不能被写成已通过。

结构返回不合格时只做一次改变输入的有限修复，HTTP错误不按此重试；记录被拒绝输出的使用量，保留显式本地兜底。


## 首次使用与目标结论绑定

`ui/guided_intake.py` 逐步收集分析单位、目标字段及单位、分析意图；`application/guided_intake.py` 按数据哈希保存 SQLite 状态，并使用乐观版本检查登记新的数据口径。它不创建执行批准，也不授予模型发送许可。未知事实保持未知。

分析意图经 ResearchService/LangGraph 进入问题探索、方法说明或待审计划。`application/conversation.py` 保留同数据的有限历史关联与实际方案差异。普通文本的同意没有执行权；方法咨询可以返回原待审计划。

`application/task_conclusions.py` 从运行对应流程绑定的 DataContract 读取目标，不读取最新可变口径。描述统计的主结论、首要图表、问答事实排序和导出报告使用这一运行目标；没有已计算目标则明确提示，不替换成其他字段。用户明确询问其他字段时可引用其已有证据；新估计仍需新计划。

候选校验提前检查数值/分类重复角色，失败时把被拒绝候选与错误原因交给最多一次有限模型修复。它不是自动接受计划，更不构成识别假设确认。

## 0.16.0 故障恢复

模型测试失败会撤销旧连接成功状态；本地模式只影响后续请求，不改写密钥、任务许可或批准。失败、阻断或待补充流程保留原记录，提供口径设置入口和带前序引用的新待审计划。新计划不能继承批准，运行中的任务仍需单独停止。完整[项目与功能手册](COMPLETE_MANUAL.md)内置于安装包，页面可下载。


## 0.16.0 研究质量与解释路径

![研究质量路径](../assets/research-quality-current.svg)

`DataContract.research` 保存范围、比较、目标、来源与限制，字段说明支持来源及派生逻辑。`research_quality` 在研究流程开始时产生只读审计与摘要，并绑定数据、口径版本。`method_contract` 为注册方法提供同一套解释字段和来源，不替代估计器。

执行后 `research_report.run_quality` 从保存的运行、计划和原口径读取事实；界面及HTML导出共用这些信息。当前口径编辑不会改写历史运行。新增自由文本不自动进入模型外发上下文。`next_research_steps` 与结果建议只能提出新的待审计划或方法咨询；审批和数值计算继续由既有受控服务执行。
