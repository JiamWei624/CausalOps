# P1 第二阶段 三层研究报告与受控建议

本阶段从 c7cd5ac 建立独立分支 feat/proactive-diagnostics-stage2，工作目录为 [本地独立工作区]。产品源码、公开数据验收和工程回归对应本阶段实际运行；最终数量及版本见文末机器记录。

## 修改范围

|文件|实际职责|
|---|---|
|diagnostics/report_contracts.py|ResearchResults、EvidenceQuality、ResearchSuggestion、DiagnosticReportManifest、ResearchRequestDraft。冻结字段，禁止额外字段，无执行权限|
|diagnostics/suggestions.py|六项已实现规则的确定性建议目录，最多三项|
|diagnostics/report_repository.py|同一研究 SQLite 中追加报告和需求草案，事务与不可变触发器|
|diagnostics/reports.py|DiagnosticReportService，核验评估快照和原生来源，再生成报告或显式保存需求|
|tests/test_diagnostics_stage2.py|三层同源、五态、未知来源、冲突限制、显式草案、并发、历史版本与损坏回执反例|
|scripts/diagnostics_stage2_acceptance.py|公开真实双 Run 与隔离反例的机器验收|

沿用原 DiagnosticService、NativeEvidenceReader、原审批和执行入口。第一阶段六项检查、其余八项未实现状态以及原统计估计器均保持各自合同。这里新增报告投影，不是追加统计检验。

## 报告合同

[实际 JSON Schema](stage2-evidence/report-v1.schema.json)由本阶段 Pydantic 类生成。Schema 只验证结构；运行身份、实际工件和读取稳定性由服务检查。

报告顶层绑定 task/session、数据和 DataContract 版本、Plan 版本、明确 Run、Assessment ID/hash、规则包版本、建议目录版本、生成器源码指纹和生成时间。原批准 ID、sha、计划版本放在 results.approval；原 S05 ReportManifest 的 ID/hash 放在 results.original_manifest。

三层分别如下。

1. results 读取当前所选任务的原生 Run 和 S05。available 时包含原 estimate、标准误、区间、分组样本与访问率、单位和窗口。统计工具保存的估计是事实来源，原 S05 的单位转换链经第一阶段规则核验后复制。没有语言模型生成的统计数值。
2. quality 保留原六项 Finding、各自证据与结论影响，提供五态中文标签，并明确列出八项 unimplemented_rules。此层 limitations 是原 Assessment 的事实引擎范围说明，保留其快照原文，其中关于“不生成完整报告/建议”的语句描述第一阶段事实引擎职责，不能当成整个第二阶段产品的功能清单。当前报告能力以本文件和 capabilities 为准。
3. suggestions 只映射本快照 issue/unknown。verified、not_applicable、not_checked 不自动产生建议。全部 Finding 始终保留；若候选超过三项，优先已发现问题，再按规则 ID 取三项。

results.status 区分 not_run、partial、available、restricted。完整联合结果要求原生双 Run、原报告来源和相关一致性检查满足。存在限制联合结论的冲突时，estimate/effect/sample_size 不交付数值；任务和诊断原因仍可读取。预诊断不补造计划、批准或效应。partial 记录已保存的合法 Run 引用，不将部分完成称为完整研究。

quality 不产生总体可信度分数。来源记录核对通过不能证明随机化真实发生、无干扰或全部因果识别条件。原 Run 自带诊断保持原生记录，不将未适配的八项规则包装为新 Finding。

## 受控建议目录

|规则|出现实际 issue/unknown 时的行动|
|---|---|
|PD-01|核对数据、合同、批准与工件归属和指纹|
|PD-02|补充分配设计来源、适用人群和期间，并由用户核对|
|PD-06|核对请求与指标窗口，目标变化时先补对应数据|
|PD-07|核对两个 Run 的样本、分组和上游门禁|
|PD-09|核对指标、单位及概率差/百分点转换|
|PD-14|核对报告运行引用和版本，暂停使用冲突联合结论|

每项具有稳定 suggestion_id、实际 diagnostic_id、assessment_id、规则版本、上下文指纹、原生引用、行动、实际原因码、缺少材料、状态和权限限制。完整无问题案例建议为零。没有关键词触发的新方法、显著性筛选或剩余八项规则的建议。

new_scope=requires_separate_request 表示建议没有实际修改范围，后续若改变研究范围需要另行请求。status=needs_information、human_review_required=true、execution_authorized=false。草案只保存用户意图和证据缺口，不携带可调用统计参数，也没有 Plan/Approval 身份。

## 服务接口

    from causalops.application.diagnostics.reports import DiagnosticReportService

    reports = DiagnosticReportService(model_free_research_service)
    pre = reports.preflight(session_id)
    post = reports.post_run(task_id, session_id=session_id)
    exact = reports.generate(assessment_id, session_id=session_id)
    historical = reports.get(report_id, session_id=session_id)

generate 从服务端保存的评估读取，不接受调用者提交的“已通过”Finding。它重新核对原生输入和观察回执。输入发生变化时要求新评估，旧报告仍由 get 读取，不自动改写旧内容。post_run/preflight 是明确生成新评估和新报告的入口，不能放进普通页面刷新路径。

    draft = reports.save_draft(
        report_id, suggestion_id,
        session_id=session_id,
        user_intent="补充随机分配设计来源",
        request_id="本次显式保存的唯一请求标识",
        human_confirmed=True,
    )
    saved = reports.get_draft(draft.draft_id, session_id=session_id)

保存草案必须显式操作。重复同一请求返回原草案；同一请求改意图会拒绝。来源已变化时拒绝用旧报告新建草案。读取已保存草案保持历史语义。草案没有自动生成后继计划或统计执行接口。

第三阶段 UI 可直接 model_dump(mode="json") 展示三个部分，并利用 assessment_id、diagnostic_id 调用原 DiagnosticService.evidence 查看检查回执。报告原生 Run 引用和 ReportManifest 引用均在结构内。此处尚无新 Streamlit 页面或 HTML 渲染组件。

## 版本和失败行为

相同评估与生成器内容返回同一 report_id、版本和原时间。输入、规则或报告实现变化产生新的内容身份；同任务版本号在 BEGIN IMMEDIATE 事务内递增。报告与草案表都有禁止 UPDATE/DELETE 的触发器。跨会话读取拒绝，内容摘要不符拒绝。

报告历史读取核对保存时的 Assessment/hash 与各层绑定，不按当前建议模板重新生成旧建议。调用原生读取或报告构造失败，只影响本次报告请求，不改变已成功统计 Run。若证据冲突已由第一阶段形成 Finding，则保存 restricted 报告和具体原因。

范围仍是本地单用户研究工作区，继承原会话归属核验，不宣称防本机管理员篡改的多租户系统。

## 触发取舍与外部模型

本轮采用显式只读生成入口。现有统计执行与后台任务拥有各自的停止、恢复、预算及执行源码绑定；本阶段没有新增诊断作业状态、失败隔离或完成事件队列。不把报告生成同步塞进统计完成事务，避免报告异常影响“已成功统计”的状态与恢复。第三阶段可在受控的明确操作中调用 post_run，然后用 get 刷新。

未建立任务完成后的自动订阅、定时任务或周期监测。没有为此改变已有执行保护。事实与报告默认无模型，接口拒绝带模型的 ResearchService，未启用 DeepSeek 或其他收费接口。

## 真实验收与复现

先按原安装文档准备 Python 3.11 和现有依赖，将公开 Hillstrom 压缩包路径写入 CAUSALOPS_HILLSTROM_ARCHIVE。pytest 临时目录、环境 TEMP/TMP 与绘图库缓存均应设在 E 盘。

    python scripts/diagnostics_stage2_acceptance.py --archive <公开压缩包> --output <新的E盘验收目录>
    python -m pytest tests/test_diagnostics_stage2.py tests/test_diagnostics_stage1.py
    python -m pytest

验收器创建全新的隔离工作区，拒绝覆盖旧目录。A 从公开数据通过原五步链产生两个真实 Run；B 使用独立合成两组数据，无设计来源，检查无自动草案后才显式保存需求；C 在隔离副本注入其他任务 Run、指标、单位、窗口和哈希冲突。原 A 保留，C 保留可读旧报告。

[验收汇总](stage2-evidence/summary.json) · [A 完整双 Run 报告](stage2-evidence/A-report.json) · [B 预诊断](stage2-evidence/B-report.json) · [B 显式草案](stage2-evidence/B-draft.json) · [工程回归](stage2-evidence/engineering-results.json)

这是服务层验收。未运行新的浏览器、真人或 V2.3 50 题评测，没有模型提效或真人完成率主张。完整工程成绩以实际 JUnit 为准。

## 停止范围

第二阶段交付后停止。完整 UI、完成事件自动诊断、剩余八项规则、模型解释授权、后继计划自动生成、长期决策记忆及多用户服务仍待后续独立开发。本分支只在本地交付。


## 本轮实际工程结果

|批次|通过|失败/错误|跳过|耗时（秒）|
|---|---:|---:|---:|---:|
|targeted02|16|0|0|36.509|
|affected01|129|0|0|237.433|
|full01|1024|0|0|566.719|

各批次包含重叠用例，不相加为独立样本。完整批次覆盖最终新增的全部16项测试。原五步链、审核、取消、恢复、预算和旧诊断用例纳入回归。
