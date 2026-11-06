# 现有能力、源码可行性与最小增量

审查基线为已发布`f9e876a / 0.17.0b1`。本目录不修改源码；哈希与函数位置见[SOURCE_AUDIT.json](SOURCE_AUDIT.json)。没有运行评测或模型。文中路径相对仓库根目录。

## 1. 当前真实能力与增量对照

|模块/接口|当前实际实现与证据|归类|本P1如何处理|
|---|---|---|---|
|application/data_contracts.py: DataContract、ContractRepository.ref/save/verify_current|指标、单位、窗口、实体、测量时点、method_facts与research来源声明；版本/哈希；事件写明human_declared_not_empirically_verified|直接复用|冻结引用，不把声明提升为实证识别|
|assistant/service.py: Plan/Step；research_service.review/verify_approval|单次方案版本与具体范围审核；读取run_ids解释而非授权执行|直接复用|后续需求只有支持时才转入待审；解释/采纳不授予执行权|
|automation_contracts.py: PlanV2/fixed_steps|固定5步；配置、范围与依赖必须完全相同；model_requests=0|直接复用边界|不向旧Plan增加诊断工具或模型步骤；新诊断为旁路只读派生对象|
|automation_coordinator.create_hillstrom/_binding|压缩包指纹、两组纳入与计数，来源确认；合同必须等于固定模板|直接复用|场景B不能从该入口构造，需原生数据任务上的只读预诊断适配|
|同模块 _audit|必要字段/缺失、实体重复、两组与0/1、结构化审计；来源+人确认的randomized声明|直接复用+规范化|程序可核验结构；随机化仍是资料与人声明，不是由均衡推断|
|同模块 _gate|真实S02、两组/有效数/样本、有限均值/变异、总样本>=10与各组>=2；不以显著性放行|直接复用|最低执行支持不称功效或充分样本量评估|
|同模块 evidence/_load_stat/_report|内容哈希、批准/Plan/指标/窗口/依赖；两个Run样本和均值一致；原区间|直接复用|授权/完整性仍由原服务决定；诊断只读引用，不重做估计|
|assistant/contracts.py: ToolResult/AnalysisTools.envelope|Run、数据/结果指纹、Plan/ordinal绑定及所有权核对|直接复用|作为EvidenceResolver事实入口，不把模型输出当ToolResult|
|schemas/core.py: DiagnosticResult|name/passed/value/threshold/message/claim_blocking，只有布尔状态|需适配|保留原记录；用方法专属适配映射到五态，不能直接把false都映射为发现问题|
|estimators/randomized.py: estimate_ab_test/_covariate_balance|组均值差、样本方差标准误与1.96区间；现有基线SMD诊断|直接复用+适用性核对|完整函数已把空协变量替换为baseline_balance_not_assessed，value=None、claim_blocking=False；没有当前“空SMD通过”缺陷|
|application/research_quality.py: audit_research/research_brief|缺失、重复、非有限、实体/时间、变量时序及因果限制；返回assumptions_verified=False|复用观察项|旧pass/review/block按规则语义映射，review不能一律当已发现统计问题|
|同模块 method_contract/next_research_steps|方法说明与按合同/审计返回有限建议，非执行|概念相似，不能等同新能力|尚非绑定Run+Finding的建议合同；可重用文字/方法卡但要新增来源约束与候选状态|
|application/automation_results.py: snapshot/report_html|有界重读、风险数组、固定解释限制、同块HTML、原S05事实报告|需扩展投影|风险数组没有Finding ID、五态和逐项引用；保留原数值真源，增加独立诊断评估与三层投影|
|ui/automation_app.py: _live/render|真实步骤、风险/预算、导出；stale报告隐藏|需最小UI改动|替换风险摘要投影而不重做工作台；当前任务选择和正文原子绑定继续保持|
|integrations/method_retriever.py / knowledge/retrieval.py|LangChain接口、既有字符TF-IDF方法卡、精确来源与引用校验|直接复用|文献支撑方法解释，不能证明当前实验确实随机化；不重构RAG|
|orchestration/research_graph.py / ResearchService|单次流程路由、检索、方案审核、结果/方法解释|复用入口，非必经步骤|固定V2走BoundedCoordinator，不虚称所有诊断必经LangGraph或模型|
|AssistantWorkspace.facts/ask|按Run读取事实、部分确定性回答、可选有引用的模型回复|部分复用|facts当前从旧assistant_plans取运行，V2 Plan不在该表；不可假设直接支持自动化两个Run，需要自动化证据适配|
|automation_budget.py: BudgetLedger；co.model_context|任务账本/物理请求/回执；0模型授权拒绝；completed无法预约|部分复用，模型路径有硬缺口|首版默认零调用；后续新建只读解释Grant与预算适配，不能重新激活完成任务|

## 2. 已计算、人工声明、模型解释分别是什么

程序事实：数据包/派生表指纹、必要字段、记录/有效样本、实体唯一、分组/二元值、工具结果、原SE/区间、运行来源和哈希。它们也不能自动证明抽样代表性或因果假设。

人工声明：来源核查、随机分配依据、客户单位与两周指标含义。固定场景由已登记公开资料与用户确认进入合同，程序核验“记录一致”，不是亲自观察实验分配过程。

模型解释：普通问答可选，经事实ID和知识卡引用校验，但不成为新的统计证据。自动化V2当前确定性报告不调用模型。本P1不沿用模型自由文本作为诊断事实。

尚未检查：固定三列表没有基线协变量；没有功效/最小可检测效应计算、无干扰的实证验证、长期利润/外推验证。不得在原型或报告中改写为通过。现有IPW、PSM、DID等各自有诊断，首版不把它们包装成全方法主动评估。

## 3. 四个关键可行性缺口

### 设计依据不足不属于现固定入口的合法执行状态
create_hillstrom先要求来源确认，再保存固定randomized合同；_binding还核对原包和完全相同合同。建议新增`DiagnosticService.preflight(native_session_ref)`，只读现有DataContract未知分配机制，不创建AB计划或Run。补来源是附加研究材料，不等于批准；正式合同变化通过原版本接口，旧批准照常失效。

### 原有facts不能直接覆盖V2两个统计运行
AssistantWorkspace.facts从旧Plan关联查找，V2不使用assistant_plans。新增AutomationEvidenceAdapter从co.evidence、_load_stat验证后的ToolResult/Run及原S05读事实。统一EvidenceContext只是类型化引用集合，不复制一套估计值库。非法引用只能记录检查失败观察，不读其数值当事实。

### 统计任务的模型授权不能借用给完成后的解释
model_requests=0，co.model_context明确拒绝；BudgetLedger预约仅接受candidate/approved/running。默认确定性解释可完成本P1。首版可选模型仅对当前完整的自动化post_run评估开放，B原生任务无自动化父预算、C有冲突，两者均不开放。可选模型需要独立、限用途的InterpretationGrant：绑定Assessment/事实包/模型服务、外发许可、最多2请求，并受原父任务12次累计上限及未知用量规则限制。

未来适配建议为新增预算“只读解释域”，使用同SQLite预约/回执原子计数，不修改旧POLICY或批准收据；原co.model_context仍拒绝0授权计划。禁止把completed改回running，禁止在预算之外直接调用客户端。此路径需要额外工程与负责人确认，不是当前已可接入能力。

### 全包源码指纹与历史只读兼容

assistant/runtime.py的execution_source_sha遍历整个包的Python文件；新增诊断模块也会改变指纹。_binding/_verify把当前代码与原批准绑定，这是未来执行保护，不应放宽。

历史读取应验证原保存的任务/Plan/合同/批准、数据与工件hash，保留recorded_execution_source_sha；不能把“当前执行授权不可复用”误报为“原统计事实不存在”。现有evidence/_load_stat提供独立的已保存产物核验，snapshot也分别处理binding_error和工件错误；新适配必须保留这种区分，不仅调用当前_verify就拒绝全部历史查看。

已完成旧任务可进入historical_read_only诊断，明确当时版本与当前诊断规则；不重新签收据或把source_sha改为当前值。旧未完成任务切换代码版本后按原门禁停止，需在原冻结版本处理或人工核查；不承诺自动迁移。此为新增P1时的兼容性风险，非本轮确认的Beta损坏问题。

ReportManifest当前是步骤输出标签及保存的dict，不是已存在的独立类型化诊断合同；新增DiagnosticReportManifest需要明确校验其引用，不能凭名称认定已实现。

## 4. 最小新增模块建议（均未实现）

|建议职责/接口|输入→输出|复用点与限制|
|---|---|---|
|DiagnosticService.assess(context_ref)|已授权原生引用→稳定Assessment|只读、幂等；不持有approve/execute工具；与原ResearchService接口相连|
|AutomationEvidenceAdapter / NativeContractAdapter|S01—S05或原生合同→EvidenceContext|先所有权/哈希核对，未知/损坏保留原因；不解析任意文件路径|
|DiagnosticRuleRegistry.evaluate|适用证据→Finding集合|登记的规则ID/版本，无任意代码/表达式；复用原验证器而非授权副本|
|ClaimPolicy.apply|Finding→可展示/需限制的结论类型|只约束新报告投影，不写原Run/Approval或放宽统计入口|
|ResearchActionBuilder.build|Finding+目标+可用方法卡→0—3项Action|模板优先；支持性检查不通过仅登记/导出草案|
|DiagnosticReportManifest / UI投影|原报告引用+Assessment→三层报告|同一上下文，原HTML/Run不覆盖；风险和建议按来源可折叠|
|DecisionEventRepository.append|用户操作+诊断/建议引用→事件|仅本任务追加，不做跨研究长期记忆或推断用户偏好|

建议文件名可在开发时调整；核心是调用职责，不能把目录设计写成现有类。

## 5. 数据与状态设计

当前background.py使用max_workers=1。未来完成回调只能排入新的只读诊断作业，不能在同一工作线程内提交后同步等待，否则可能死锁。事件/请求先持久化，后台只消费原生引用；首版复用原队列与线程池，不新建调度平台。进程重启后的诊断可依据稳定输入幂等重做规则读取，但不得以此重跑任何统计步骤。UI刷新只获取已有快照，不重复派发任务。



同一原SQLite新增`diagnostic_assessments`、`diagnostic_findings`、`research_decision_events`，以及小型报告/建议JSON。保留原SQLite/Parquet/结果文件作为事实真源。上下文幂等键唯一；新规则/来源/合同/Run指纹产生新Assessment，不原地改旧Finding。

固定五步执行状态与诊断状态并行：研究completed不等于诊断全部满足；诊断失败也不触发五步重跑。报告冲突时只读暂停整合，原服务决定是否能继续执行。权限冲突不自动撤销、签发或修复收据。

## 6. 本轮审查结论

**可在当前架构上实现，无需新统计引擎、通用DAG或新事实数据库。** 但统一合同、证据适配、状态规则、建议/决策事件和三层投影均需新增工程；模型后置解释也有明确授权与预算缺口，不能仅挂一段提示词上线。

本结论是源码设计可行性判断，不是新功能已运行或可靠性实测。本轮只做文档校验和原型布局检查，不运行V2.3、974项工程回归或真实模型。
