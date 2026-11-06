# 主动研究诊断 P1 第一阶段交付报告

日期：2026-11-06。范围：诊断事实层与结构化证据引擎；**未开发完整工作台或三层报告**。

## 1. 版本与真实修改范围

- 开发分支：feat/proactive-diagnostics-stage1，从设计提交f150ef8创建，完整包含公开Beta f9e876a。
- 冻结产品提交：cf02474ceaddccaee9057b37047130434b3399d5。
- 源码指纹：d7b4e1bb2d9ed2d6510f6c2101a3db2f9ccca5560fce2efcb6493806da455793。
- 原业务源码、统计估计器、LangGraph、RAG、审批/预算、UI和原历史评测均未改动；只新增诊断包、测试与有限验收运行器。没有新增依赖、收费模型调用或远程操作。
- 保留Beta产品版本0.17.0b1；本分支为未发布的P1工程候选，不把新增能力写成已发布功能。

## 2. 规则选择与现有输入核查

本轮严格从原14项中选择6项，未新造规则ID。规则包hillstrom-diagnostics-stage1:1；每条规则版本1。未实现项明确列入coverage.not_implemented，不生成“通过”结果。

|规则|本轮状态|真实输入、复用或缺口|
|---|---|---|
|PD-01 身份与完整性|已实现|原数据/合同、PlanV2、整体批准、assistant任务、co.evidence与_load_stat；新增原生引用适配和验证回执|
|PD-02 分配设计依据|已实现|固定公开源身份、合同及来源确认、S01结构化声明；只核对记录，不证明随机分配过程。原生表不借用Hillstrom声明|
|PD-03 实体与单位|未实现新适配|S01和audit_research已有实体检查，可后续适配；本轮不输出PD-03通过|
|PD-04 组别/纳入|未实现新适配|原固定范围和审计已有产物；预诊断只观察分组字段存在及非空组数，不宣称完整纳入检查|
|PD-05 指标缺失/有限值|未实现新适配|原严格审计/统计已有输出，不新增独立缺失处理或估计|
|PD-06 观察窗口|已实现|合同、计划、工具配置、真实Run指标定义、S05及可选明确请求；精确匹配，不靠相似名称改语义|
|PD-07 双Run与门禁|已实现|原S02/S03/S04；调用只读_gate核对实际样本/门禁，再对两组有效数、均值、总样本交叉核对，不以显著性决定|
|PD-08 区间可引用性|未实现完整适配|原Run有区间，本轮PD-09仅沿用原函数核对单位链，不宣称完成独立的区间质量审核|
|PD-09 指标与单位链|已实现|合同/配置/比较组、真实Bundle与原rate_contrast、S05.effect；不让报告自由文本充当事实|
|PD-10 最低工具条件|未实现独立适配|原_gate已有最低样本与变异条件，作为PD-07上游一致性的一部分读取；不称功效或样本充分|
|PD-11 基线检查|未实现|原工具已记录baseline_balance_not_assessed；本轮不将其映射为新Finding，更不补算SMD|
|PD-12 未证假设|未实现规则适配|无干扰/外推/长期利润没有实证产物，保留统一限制，不显示为通过|
|PD-13 目标决策边界|未实现|没有泛化研究目标解析或ROI/长期结果数据，不新增相关判断|
|PD-14 步骤/报告来源|已实现|实际步骤、两个Run、S05结构化来源/范围/批准版本/样本与目标；没有S05则未检查|

新增计算限于原生预诊断的分组字段存在性、非空组数等结构观察，以及已保存证据的哈希、相等性与单位链核对；**没有调用估计器产生新诊断统计量**。

## 3. 实际源码模块与调用链

|源码|主要类/函数|实际职责|
|---|---|---|
|[contracts.py](../../../src/causalops/application/diagnostics/contracts.py)|DiagnosticContext、DiagnosticFinding、DiagnosticAssessment|严格五态、类型化原生身份、规则/来源、证据与影响合同|
|[evidence.py](../../../src/causalops/application/diagnostics/evidence.py)|NativeEvidenceReader.preflight/post_run/_run_marks|核对所属会话，读取合同和已存工件；在打开统计内容前比对原assistant执行记录；记录文件字节指纹|
|[rules.py](../../../src/causalops/application/diagnostics/rules.py)|evaluate及六个登记检查|确定性条件、原因码、严重度和结论影响；身份失败后下游未检查，不拼接其他Run|
|[repository.py](../../../src/causalops/application/diagnostics/repository.py)|DiagnosticRepository.save/get/observation|同SQLite内追加不可覆盖快照/回执；内容哈希、归属和幂等核对|
|[service.py](../../../src/causalops/application/diagnostics/service.py)|DiagnosticService.preflight/assess/get/evidence/capabilities|显式只读入口、有界稳定重读、规则调度与快照返回|
|[验收运行器](../../../scripts/diagnostics_stage1_acceptance.py)|main|隔离数据、原正式审批与真实工具，保存A/B/C的结构化输入和输出|

调用链为：显式只读请求 → NativeEvidenceReader → 原持久化合同/原co.evidence/_load_stat → 六项确定性检查 → DiagnosticRepository → 不可变Assessment。只有诊断自有表发生写入；不调用approve、execute、advance或模型。没有加入第六个统计步骤，也没有改写原审批格式。

## 4. 结构化合同、状态与证据

实际合同版本diagnostic-finding-v1.1 / diagnostic-assessment-v1.1，见[实际Schema](stage1-evidence/finding-v1.1.schema.json)与[评估Schema](stage1-evidence/assessment-v1.1.schema.json)。

相对先前设计示例的最小调整：支持缺失合同的预诊断（contract_ref可为空）；增加已实现/未实现覆盖范围、输入清单、零模型请求和无执行授权；使用“评估时点的不可变快照”语义，避免把历史读取标成实时当前状态。旧设计Schema与原示例保留，不覆盖历史文档。

五态严格为verified、issue、unknown、not_applicable、not_checked。unknown必须列缺项；not_applicable有目的/方法范围依据；not_checked不标实质检查发生；verified必须有真实检查回执。状态与严重度分开，不输出总体可信度分数。human_confirmation_required表示记录的补充/核查事项，不是解除阻断的许可；即使该字段为false，关键冲突仍受conclusion_policy限制。

每条Finding保留稳定ID、上下文、规则版本、原因码、实际结果、待补充事项、结论影响、来源与时间。证据引用包括原合同/步骤/Run的ID及hash，并关联本次不可变validation_observation。后续报告可通过evidence入口查看当时的检查和原生引用；原Run仍是统计事实真源。

## 5. 只读与幂等

- preflight(session_id)：不要求先创建Plan或Run。独立读取当前原生数据合同，观察分组字段和组数；无设计依据标未知。普通表上的randomized声明或URL文字不足以自动获得已核验设计状态。
- assess(task_id, session_id=...)：强制明确会话，读取固定五步已存结果；允许部分完成记录。调用者不能提交自己的“通过JSON”来替代原生验证。
- 原生证据输入、实际文件内容、上下文、诊断源码、规则包与Schema进入快照指纹。两次有界读取不稳定则拒绝组装混合快照。
- 相同输入返回同一ID和原时间；数据/合同/工件/规则变化形成新快照；原记录不覆盖。SQLite事务和唯一主键保护并发提交，诊断表有禁止UPDATE/DELETE的触发器。
- get只读取当时快照，不表示工件此刻未变化。展示当前状态应重新调用assess/preflight；读取旧结果不自动重算、恢复或批准。
- 原证据缺失为unknown，存在冲突为issue；身份/内容不可靠后其他规则为not_checked，不重复制造多个独立风险。

## 6. 三类实际验收输出

本轮为**服务层验收**，不是浏览器、模拟用户或真人使用测试。完整记录见[汇总](stage1-evidence/summary.json)，整批墙钟耗时15.875秒，模型请求0。

|情形|实际结果|证据|
|---|---|---|
|A 公开Hillstrom真实固定链|6项已实现规则均verified；明确8项未实现；两个原生Run及原审批不变；重复评估/读取一致|[输入](stage1-evidence/A-input.json)、[输出](stage1-evidence/A-output.json)、[检查](stage1-evidence/A-checks.json)|
|B 独立合成两组数据，无随机化来源|PD-02 unknown/major，缺少具体设计来源；两组字段存在不等于随机化；不产生Plan、Approval或统计Run|[输入](stage1-evidence/B-input.json)、[输出](stage1-evidence/B-output.json)、[前后计数](stage1-evidence/B-checks.json)|
|C 其他任务Run、报告指标、窗口、内容hash四种冲突|四个受控副本均hide_integrated_estimate；错误关联未被完整性认可；原A的运行和证据保持不变|[其他任务Run](stage1-evidence/C-foreign_run-output.json)、[指标](stage1-evidence/C-report_metric-output.json)、[窗口](stage1-evidence/C-report_window-output.json)、[哈希](stage1-evidence/C-content_hash-output.json)|

A描述统计Run：10fb40e7b9b2476792bec2ab7adbd74e。A/B Run：9767111e9d5340aca06cdc186f3abe87。它们来自本次原注册工具的真实运行，不是模型输出或历史数字代入。

实际对照访问率10.6167276823%、男装邮件组18.2756840475%；绝对差7.6589563652个百分点，原工具95%区间[6.9953223541, 8.3225903763]个百分点。合计42,613名客户。诊断核对的是既有统计来源和一致性，不代表原方法已经完成所有统计性能验证。

## 7. 历史版本与执行安全

另用未修改的已公开Beta源码实际生成旧任务，再由新引擎读取，六项历史证据检查通过；同时当前原执行校验拒绝沿用旧批准。旧执行指纹b6aa23b24f20e8b1d2c58b7dc0509bc0dc1def807a0583c1e24a03e7d8e23f9a，新诊断指纹d7b4e1bb2d9ed2d6510f6c2101a3db2f9ccca5560fce2efcb6493806da455793。

[历史兼容检查](stage1-evidence/historical-checks.json)保留实际结果。旧版的原Plan、审批、统计事实没有被重签或修改；当前性和执行许可不由诊断授予。原五步链的未批准、暂停、取消、调和、预算和重复提交测试继续运行，见下节。

## 8. 测试与工程回归

冻结产品提交cf02474c；Windows、Python 3.11.5。完整环境及机器结果见[engineering-results.json](stage1-evidence/engineering-results.json)，逐项名称、耗时及状态见[test-cases.json](stage1-evidence/test-cases.json)。

|批次|实测数量|失败/错误|跳过|用途|
|---|---:|---:|---:|---|
|新增定向用例|34|0|0|五态、缺失/损坏、各规则反例、跨任务隔离、并发幂等、无统计副作用及历史保持|
|受影响模块回归|117|0|0|新诊断+原五步、审批、安全、持久恢复及原工作台测试|
|完整工程回归|1008|0|0|本版本实际重跑，非沿用974项历史成绩|

受影响模块JUnit耗时220.230秒，完整工程JUnit耗时569.447秒；不同批次包含重叠用例，不相加为独立样本。工程通过率不是Agent研究任务正确率，更不是真人成功率。本轮没有运行V2.3题集。

首次失败及评测器问题未删除：
1. 实现前反例收集因诊断模块不存在而失败。
2. 初期复制原生工作区未迁移AnalysisRunRecord的绝对工件路径，导致部分反例命中非目标完整性问题；相关初步绿色结果不作为最终规则验收。后续受控副本先迁移路径并证明六项规则正常，再注入问题。
3. 修改S03后原哈希依赖先被PD-01阻断。为单独验证PD-07，在隔离副本同步更新依赖hash但保留错误样本事实；原统计不重算，语义规则仍阻断。
4. 最终34项与上述两类实际验收均在修正后的基础设施上完成。详细日志指纹与结论见[test-history.json](stage1-evidence/test-history.json)，原始日志/数据库留在本地隔离验收目录，不提交工作区或私人材料。

## 9. 可复现运行

使用项目原安装流程准备Python3.11与现有app/workflow/dev依赖。没有新增模型服务或外部收费依赖。先按现有公开教程取得并核对Hillstrom压缩包，再运行：

    python -m pip install -e ".[app,workflow,dev]"
    python -m pytest tests/test_diagnostics_stage1.py tests/test_automation_v2.py tests/test_automation_v2_safety.py tests/test_automation_v2_stage2.py tests/test_automation_v2_workbench.py
    python -m pytest
    python scripts/diagnostics_stage1_acceptance.py --archive <已核验公开压缩包> --output <全新的隔离输出目录>

真实数据验收与全项目测试应设置CAUSALOPS_HILLSTROM_ARCHIVE；临时目录也可通过pytest --basetemp指定。验收运行器拒绝覆盖已存在输出目录，失败后用新目录，旧记录保留。工作区SQLite、统计工件和公开原表不提交Git。

服务使用：

    from causalops.application.diagnostics import DiagnosticService
    diagnostics = DiagnosticService(model_free_research_service)
    preflight = diagnostics.preflight(native_session_id)
    assessment = diagnostics.assess(automation_task_id, session_id=native_session_id)
    same_snapshot = diagnostics.get(assessment.assessment_id, session_id=native_session_id)
    receipt = diagnostics.evidence(
        assessment.assessment_id, assessment.findings[0].finding_id,
        session_id=native_session_id)

## 10. 当前限制与第二阶段复用

- 当前入口是显式Python服务，未接入自动完成事件、UI或完整三层报告。不能称为已上线的主动诊断工作台。
- 事实层只接受无模型的ResearchService，现有带模型会话需另建共享原工作区的无模型服务实例，不能借其配置发出解释请求。
- 原生任务本身不存在或无法解析时入口拒绝，不伪造任务身份创建快照；可识别任务中的工件缺失/损坏则保存明确Finding。
- 运行后仅支持已登记Hillstrom固定五步；原生预诊断支持合同/分组结构观察与设计来源未知提示，不是任意表的通用因果诊断。
- 已登记随机化事实仍属资料与人工声明核对；不能实证证明分配过程、无干扰、功效、外推或长期收益。
- 8项规则未实现。本阶段不把“未适配”混成统计假设失败，也不将它们算通过。
- 请求窗口须明确匹配登记定义，不提供自然语言窗口同义词推断；未知口径要求用户确认。
- 原生RunRecord部分工件路径为绝对路径；本轮仅在隔离测试副本重定位，未实现正式工作区迁移工具。
- 当前权限边界仍是本地单用户和研究会话归属，不宣称生产级多用户隔离；SQLite触发器也不是防恶意本机管理员篡改的安全机制。
- schema版本1.1与先期设计示例存在以上明确差异，未来页面应使用本阶段实际Schema。
- 代码升级后的未完成旧任务仍服从原执行指纹保护，没有自动迁移或恢复授权。历史读取不改变此边界。
- 没有完整建议生成、模型解释、用户采纳事件、长期决策记忆或额外诊断统计工具。

第二阶段可直接复用DiagnosticService、不可变Finding/Assessment、evidence检查回执、context_fingerprint及coverage，并在同一上下文上投影三层报告。不得从报告文字反取数字；统计事实继续由原Run读取。采纳/暂缓和后继草案仍需另行设计授权，不能以已有诊断ID直接执行统计。

## 11. 结论与停止点

**本阶段的最小事实引擎已达到限定验收目标**：真实证据可读、六项规则状态可复核、未知与未检查明确区分、冲突限制结论、快照可追溯且不改变原统计或批准。支持进入第二阶段的报告与建议机制设计/开发评审；不代表其已获得开发授权。

本轮已停止：不推送GitHub、不合并main、不创建Release、不调用收费模型，也不自动进入第二阶段。
