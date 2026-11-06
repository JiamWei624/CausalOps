# 结构化合同与语义不变量 · 设计候选

本目录JSON Schema是**拟实现合同**，不是当前Python类；examples为虚构对象引用的设计夹具，不是本轮新诊断或真实运行。结构校验通过不代表引用存在、得到授权或研究结论正确。生产服务只接受原生对象引用，不接受调用者提交“已通过”的Finding来覆盖检查。

## DiagnosticFinding

|字段|用途与约束|
|---|---|
|finding_id、assessment_id|稳定诊断ID与评估快照；不可跨上下文复用|
|context|task/session、Plan及hash、数据/合同版本、明确Run/结果指纹、目标指标/统计量/单位/组别/窗口；不能只存运行标题|
|rule|规则ID、版本、规则包及检查方法；必须在服务端注册|
|diagnostic_type|身份、设计依据、样本、指标、推断、执行完整性或解释边界|
|applicability、check_performed|适用性与该项实质检查是否发生，独立于五态|
|status|verified / issue / unknown / not_applicable / not_checked，中文分别对应五态|
|result|可核对观察、期望和原因码；缺值为null或明确缺项，不填0；计数不代替估计器事实真源|
|evidence_refs|原生工件ID、内容hash、JSON Pointer、可用性；不用任意文件路径或模型文本URI|
|impact|对结论的允许/限制、报告是否可整合、解释原因；不授予统计权限|
|severity|critical / major / moderate / information与政策/原因码；来自规则表，不由模型决定|
|human_confirmation_required|还需什么人工材料；确认不等于放宽结构冲突|
|eligible_action_ids|0—3个行动引用，不能是可执行Python/SQL/任意条件表达式|
|generated_at、source|实际生成时间和程序/旧引擎适配/人工声明核对来源；模型没有写Finding的权限|

### 五态的机械与语义约束

|状态|check_performed|必须表达|
|---|---|---|
|已核验满足|true|本规则检查对象有当前上下文内有效引用；人工来源只证明记录完整性，另标origin|
|已发现问题|true|具体冲突或不满足值，受影响主张与规则依据|
|条件未知或证据不足|true|已检查记录/条件可用性，但缺少必要证据；逐项列缺什么|
|不适用|false|已判断方法/目的不需要本项；记录原因，不统计成通过|
|尚未检查|false|本项相关但未运行，或数据/范围不允许；不得读取默认0解释成满足|

`status`不承担生命周期。评估还具有freshness=current/superseded/stale_input与执行状态pending/assessing/ready/partial/unavailable。新数据/Plan/规则生成新快照；旧Finding保持原文和历史时间。

## 对应运行和无Run情形

- 执行后评估必须绑定真实Plan/合同及明确Run引用，并通过原envelope/evidence校验。
- B预诊断可以plan_ref=null、run_refs=[]；同时填写“尚未生成正式计划/未执行”原因。字段仍存在，不能虚构编号补齐。
- 无法验证的工件不能提供数值作为证据。对损坏/跨会话输入，引用本任务的验证观察回执，展示概括失败原因，不公开对方研究信息。
- 记录级均值、中位数和总量不机械要求分母；概率/比例才核对相应人群与分母。固定场景遵守原分配组客户数定义。

## 历史代码版本

Context.provenance区分原运行代码、当前诊断代码和读取模式。历史模式核验原保存的批准与工件，不用当前代码许可替代历史来源；同时明确不能恢复旧执行。preflight没有原运行代码，字段为null。模式只能由服务决定，不能由调用者勾选绕过所有权/数据完整性。

## Assessment与报告合同

Assessment的context_fingerprint由任务/Plan/数据/合同/Run结果指纹、规则包、知识版本构成。保存Finding ID+hash，摘要计数可从Finding重算，不能有整体quality_score。pending/assessing表示尚在排队或评估；ready只表示评估产物完整，不等于所有检查通过。重复请求同一有效上下文返回原完成记录；结果处理中允许只读pending，不新增统计。

新增DiagnosticReportManifest关联原S05内容hash与Assessment，不修改原ReportManifest。第一层数值只能从有效原Run读取；source证据异常时不能从历史HTML补数字。模型解释（若获授权）有独立manifest和事实包hash，失败不改变Finding或Plan。

## ResearchAction与需求草案

Action记录：依据Finding和证据、原因、目标问题、所需数据、是否变更范围/需要新审批、支持性（supported_read_only / draft_only / unsupported）、候选方法ID及用户操作要求。方法必须来自注册表，未支持的约束必须保持草案或不支持状态。Action另标rule_template/model_candidate来源；模型候选必须保留needs_human_review，不能把格式/引用检查成功称为语义已完全正确。补充材料本身可不改Plan，但若后续改变正式合同/研究范围，则必须重新审批。

采纳形成FollowupResearchDraft或补充材料请求，不直接等同现有Plan。草案包含来源assessment/finding/action、用户意图、数据缺口、计划变更点及状态draft/needs_information/unsupported/ready_for_explicit_plan_request。只有用户另行明确请求，才通过实际支持的研究服务生成待审Plan，再审核。字段、样本、组别、窗口、方法变化均需新批准；不能改写已批准PlanV2。

## 研究决策记忆最小接口

ResearchDecisionEvent采用追加事件：event_id、actor、decision、目标Finding/Action、原上下文hash、原因、before/after条件引用、候选Plan引用（如有）、supersedes_event_id与实际时间。

- accepted/deferred/rejected只代表对建议的决定，不代表批准执行。
- 问题是否解决必须由新Assessment及相同规则/范围的可比结果判定；仅接受建议不能写resolved=true。
- 过期或被取代通过新的失效/替代事件表达，不修改原记录。合同/Plan/数据/规则变更自动使原决定的适用性需重核。
- 本轮只预留当前研究内接口，不做跨研究召回、偏好学习、向量记忆、图数据库或多用户权限。

## 来源补充的最小记录

建议DiagnosticSourceReview包含review_id、任务/合同引用、支持的主张（分配机制/窗口定义等）、来源ID/URL、可用的版本/内容指纹、段落定位或简短支持说明、适用人群/期间、明确人确认、实际审阅时间及被取代记录。缺少的时间/文档指纹为null，不从数据文件hash推断设计文档内容已验证。

旧Beta只存固定来源、数据包指纹及human_source_confirmed，导入时保留为legacy_source_attestation，不合成新版人签/查阅时间。新增记录只能补充依据，不能覆盖已知冲突或直接修改DataContract、批准。若登记的业务事实变化，仍走原合同版本接口和新计划审核。

## 模型解释Grant（可选后续，不在当前Beta中）

拟新增ModelInterpretationGrant，首版仅允许当前完整的自动化post_run评估；B原生预诊断和C冲突没有可用解释授权，保持零调用。字段包括：grant_id、Assessment/事实包hash、父任务、允许模型服务与配置、显式外发许可、允许动作类型、物理请求上限2（含重试）、父任务总请求上限12、创建/失效时间及撤销记录。它只允许解释，不能复用原固定Plan的执行权限，也不能把model_requests=0改为2。

需要预算适配在同一原子账本中同时检查Grant与父级总额，completed父任务仅允许该只读用途，不改变父任务状态。旧BudgetLedger.POLICY与原批准核验不得放宽；取消/无同意/预算不足均拒绝。尚未实现前模型保持关闭。

## Schema以外必须执行的校验

1. 所有权、引用存在、hash和Pointer一致；受损引用不能因为JSON格式正确就通过。
2. Context、规则与状态/严重度/结论影响组合必须匹配规则注册表。
3. status unknown必须有缺项，not_checked/not_applicable必须有原因，verified不能引用不存在的默认结果。
4. 同ID/幂等键不得绑定不同内容；不使用模型产生的severity或自动接受事件。
5. 任何新Plan与执行仍走原服务；模型与诊断模块没有审批/执行函数权限。

[Finding Schema](schemas/diagnostic-finding.schema.json) · [Assessment](schemas/diagnostic-assessment.schema.json) · [Action](schemas/research-action.schema.json) · [DecisionEvent](schemas/research-decision-event.schema.json) · [共享引用](schemas/common.schema.json)
