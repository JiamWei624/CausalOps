
# CausalOps 自动化 V2 第二阶段：持久化恢复、预算与执行控制

日期：2026-11-06。定位：单用户、本地、固定 Hillstrom 五步链的受限执行基础；不是通用自主规划或完整工作台。

## 1. 基线、修改范围与结论

本轮产品冻结提交：`a9f02ce5fc22e87ff8b07e65d8cb32a0b5d283a0`，源码指纹：`32a9fd12628291018a1ccace740b4c231f06688126e50e04fb423b3d3ee9e11d`。

从干净的第一阶段交付 `461a4b7` 创建 `feat/automation-v2-stage2`。此前产品提交为 `2d0efb2`。保留原分支、提交、所有研究与评测证据，未推送、合并 main 或创建 Release。本轮没有重新运行 V2.3 研究题集。

真实源码核查发现：第一阶段已有步骤、assistant_tasks、TaskRuntime 检查点、统计 Run 与文件；但没有恢复协调器对这些记录的调和。原暂停接口持有同一执行锁，不能及时记录在途停止请求；物理 HTTP 观察器只记录、不能阻止超额发出。第二阶段因此只扩展协调器、资源账本、传输前检查及薄 CLI，没有修改统计估计器、RAG、LangGraph 或既有人工审批门禁。

**最终产品提交、完整工程成绩及机器证据见 [STAGE_TWO_EVIDENCE.json](STAGE_TWO_EVIDENCE.json)。** 全部日志、隔离工作区和故障注入输出保存在本地独立证据目录；该目录不进入源码仓库。下面记录实现语义与实测范围，不宣称生产级高可用或物理恰好执行一次。

## 2. 实际修改的模块与调用关系

| 文件 | 类／函数 | 实际变化 |
|---|---|---|
| automation_coordinator.py | BoundedCoordinator._init_control / _claim_owner / _release_owner | 加任务层进程出生身份和令牌；复用 OS flow_lock；活所有者或无法判定退出时拒绝接管 |
| 同上 | advance / _advance_once / _inputs / _publish | 固定链、逐步批准和依赖复核；逻辑步骤单次发布；静态计划与尝试分离；在途控制请求在安全边界生效 |
| 同上 | _reconcile_stat / resume | 原 tools.reconcile 之前检查文件与 SQLite、原检查点和所有者；唯一可信 Run 恢复关联；不确定则暂停并记录接管原因 |
| 同上 | pause / cancel / _control | 短事务记录请求，不等待工具执行锁；取消终态；不删除历史 Run |
| 同上 | budget / model_context | 资源状态读取；当前固定计划 model_requests=0，拒绝开放自主模型规划 |
| automation_budget.py | BudgetLedger | 持久请求预留、回执、语义修订、价格快照、资源停止原因；物理请求12次、载荷128 KiB、修订2次 |
| llm/providers.py | StructuredModelClient.complete_json | 每次实际 HTTP 前原子预留，包括底层重试与上层另发的 JSON 修复；保存用量或未知状态 |
| llm/deepseek.py | DeepSeekStructuredModelClient.complete_json | 在 V2 资源上下文中拒绝旧 SDK 路径，防止其内层请求逃逸计数；普通旧流程保持原行为 |
| research_service.py | ResearchService.automation_v2 | 继续作为唯一服务工厂；更新入口说明 |
| scripts/automation_v2_stage1.py | main | 在原薄入口增加 advance、pause、cancel、resume、budget；没有建设新工作台 |
| tests/test_automation_v2_stage2.py | 32项参数化实例 | 真实工具、子进程崩溃、并发控制、资源与反例测试 |

调用链：

```text
ResearchService.automation_v2()
  → advance → 有模型关闭约束的任务上下文
  → OS flow_lock + 持久 owner token / PID birth
  → _inputs：批准 + 数据/合同/计划/上游证据 + 资源政策
  → 逻辑步骤 running / attempt
  → _stat：TaskRuntime.claim(max_attempts=2)
      → prepare → 持久 checkpoint → 再次核验
      → 原工具 execute → 原研究域门禁 → 原 Run
      → TaskRuntime.finish
  → _publish：一份逻辑步骤证据
  → 正常推进 / 暂停 / 取消

重启 → resume → 证明旧所有者失效
  → 批准、数据、合同及所有成功上游复核
  → 文件集合与数据库对照 → tools.reconcile
  → 唯一可信 Run：校验并修复原关联，不统计
  → 无 Run 且确定安全的临时失败：原工具总尝试额度内恢复
  → 多个 Run / 孤立文件 / 损坏 / 身份冲突：暂停及人工核查
```

## 3. 逻辑身份、状态与调和

逻辑身份为 task_id + plan_sha + step_id，input_sha 绑定实际步骤配置与上游内容哈希。每次尝试有独立 ID；统计工具沿用同一个 assistant_task_id 和 TaskRuntime attempts。协调器的尝试表用于记录步骤时序，并不额外提供一份统计重试额度。

复用原 pending、running、succeeded、blocked、interrupted 状态；准备完成记录 step_prepared 事件与持久 checkpoint，不为了术语新增第二套准备状态。任务另有 pause_requested、paused、cancel_requested、cancelled。interrupted 表示结果尚需调和，不等于没有 Run。

调和前核对旧进程 PID 与出生身份；活进程或未知身份不会按心跳过期强行抢占。OS 锁仍阻止同进程其他线程同时进入。统计检查点的旧令牌也必须失效，才能修复任务关联。

探索统计核对独立 study 下全部结果文件和 Run ID；A/B 核对原 session 下记录、evidence/run-*.json 和未完成临时文件。多个候选、孤立文件、损坏、未完成记录或来源不匹配均停止，不挑选结果。可信 Run 必须通过原 envelope、配置、数据、计划、批准、样本与上游门禁复核后才发布逻辑成功。

本地可信操作者仍可直接修改磁盘和 SQLite；哈希不是防管理员篡改的数字签名。跨 SQLite 与结果文件不是物理原子事务。明确无法判断时采用人工接管，没有实现或宣称任意故障下的物理“恰好执行一次”。

## 4. 暂停、取消和接管规则

- pause/cancel 先用短事务登记，正在运行的工具可正常完成并保存结果；不启动下一步骤。
- 暂停保留原批准、步骤、Run、证据和原因；resume 重新核查，不能仅靠状态文字放行。
- 取消是终态。旧 resume/advance 不会恢复执行权限；已成功步骤允许只读查阅。若进程在取消请求后退出，再次取消可确认死亡后终结该任务，未核清 Run 保留供只读核查。
- 对多候选、文件冲突、批准失效、数据或计划变化，写 takeover_required 事件和具体任务原因；下一步是核查原 Run，或新建候选并重新审核，不提供管理员绕过执行门禁的接口。
- 重复批准、完成步骤、恢复已完成任务只读取原证据。重复暂停/取消不会创建新统计结果。

## 5. 资源账本与预算边界

在同一工作区 SQLite 添加以下任务侧表，统计事实仍保留在原 Run 中：

| 表 | 内容 |
|---|---|
| automation_v2_owners | 任务所有权令牌、PID和出生身份 |
| automation_v2_step_attempts | 逻辑步骤尝试、输入哈希、开始/结束、异常类型 |
| automation_v2_budget | 固定资源政策版本 |
| automation_v2_model_requests | 每个物理请求的原子预留、用途、非敏感配置、时间、字节数、状态和回执 |
| automation_v2_revisions | 语义修订内容键，幂等计数，上限2 |
| automation_v2_prices | 不可原地改写的模型价格、HTTPS来源及版本 |
| automation_v2_budget_stops | 超额或不允许继续时的停止原因 |

整体人工批准新增绑定资源政策。旧源码批准因代码及政策不符不能用于新执行；未迁移或重写历史收据。PlanV2 固定链和 model_requests=0 保持原合同。当前五步服务不会发模型请求；意外嵌套模型请求在 HTTP 前阻断。

BudgetLedger 的任务上下文供后续获批的模型步骤复用，统一 Provider 在**物理请求之前**预留。HTTP重试和独立 JSON 修复均消耗同一任务12次额度；无回执也不退还。上下文内服务绑定冲突拒绝发送；旧 SDK 在该上下文内直接拒绝。它不为普通旧工作流凭空建立 V2 任务，也不声称已经接入不存在的自主规划 UI。

语义修订账本已实现两次限制、稳定内容键去重和重启保持；当前固定计划不开放修改研究目标的 API，不能把账本测试称为已经实现通用计划修订。未来新增候选生成器必须在语义修改前调用此接口；纯 JSON 修复只消耗物理请求，不占语义修订。

工具临时故障仅 TimeoutError、BlockingIOError、ConnectionError 在核实无持久结果后可自动恢复一次。参数、研究条件、批准错误不自动重试；通用 OSError 默认不够证明可安全重试。任务层循环不增加工具额度，TaskRuntime 的同输入总次数最多2。取消、数据变化和不确定结果不会因重试获得新权限。

费用：
- 已知输入/输出用量单独记录，缺失回执为 usage_unknown，不视为免费。
- 配置带模型、来源和版本的价格快照后，按回执估算；达到1元预警阻止后续模型外发并登记停止原因。
- 本轮固定链无需模型，未配置或宣称当前官方实时价格，也没有实际收费模型请求。费用预警通过明确标注的合成价格与 HTTP Mock 验证，不能冒充官方账单。
- 无可靠对应分词器，不声称精确总 token 硬限。确定性边界是物理请求12次、序列化请求体128 KiB及原 Provider 输出上限。
- 请求可能已计入预留而进程尚未真正发送，此保守记账不会释放额度；并不承诺预留数恰等于服务商收到数。
- 预算耗尽不能通过恢复重置。已保存证据仍可读取；无需模型的本地步骤不增加模型请求，不能据此再发第13次。

## 6. 实际验收

正常流程和 S04 提交后崩溃两份独立公开数据工作区均完成固定五步链。每份整体批准1、描述Run1、A/B Run1。后者用真实子进程 os._exit 在统计持久化后、逻辑步骤发布前退出；新进程调和原 A/B Run，没有重算，原统计结果与报告文件哈希不变。

| 结果 | 实测 |
|---|---|
| 未发邮件组 | 21,306客户；0.10616727682343002 |
| 男装邮件组 | 21,307客户；0.18275684047496127 |
| 绝对差 | 7.6589563651531245个百分点 |
| 原A/B工具95%区间 | [6.995322354054364, 8.322590376251885]个百分点 |
| 总样本 | 42,613；严格缺失策略 |
| 方法注册 | 17；没有新增估计器 |
| 本轮官方模型请求 | 0；不需要模型才能交付事实报告 |

正常验收及恢复工作区的机器清单、两个 Run ID、S03 的 S02 证据哈希、批准与事件见配套 JSON。批准是测试控制器按完整计划显式提交，不是独立真人审核测试。

故障覆盖：
1. S02、S04 工具真实落盘后子进程退出，恢复原 Run。
2. 步骤领取后、工具开始前进程退出，可核查恢复。
3. Run文件损坏、数据库记录删除后文件仍在、同一步多个结果、检查点跨任务：安全停止，未调用下游A/B。
4. 活任务所有者、活统计所有者：拒绝重复恢复。
5. 步骤中暂停/取消：当前真实 Run 保留，后继不派发。
6. 暂停期间数据、计划、批准变化：恢复阻断。
7. 一次临时故障后完成；两次达到上限；参数错误一次停止。
8. 12次预留成功、第13次被阻断；并发18次预留仅12次成功；HTTP重试与JSON修复共用额度；持久账本重启不归零。
9. 预算不足时已有描述证据仍可读取；恢复不能增加模型额度。
10. 完成后重复运行/恢复，报告与原结果文件哈希保持。

## 7. 测试记录

实际命令（在项目根目录，Python 3.11依赖环境；公开包通过环境变量指定）：

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:CAUSALOPS_HILLSTROM_ARCHIVE = "<已核验公开压缩包位置>"
python -m pytest tests/test_automation_v2_stage2.py tests/test_automation_v2.py tests/test_automation_v2_safety.py tests/test_v13_transport.py
python -m pytest
```

未提供公开包时相关真实数据测试明确跳过；本轮实测提供了正确指纹的公开包。初始 red、全部中间日志及最终 JUnit 保留，不覆盖原阶段证据。确切数量、耗时与最终代码指纹见配套机器清单；工程通过不代表所有统计方法全面认证，也不是 Agent 研究任务准确率或真人使用成功率。

### 最终实际成绩

| 批次 | 通过／失败／跳过 | 实际耗时 |
|---|---|---|
| 初始 red | 3项失败；预算模块缺失、在途暂停被锁、未提供调和恢复 | 原始失败保留 |
| green01 | 45／0／0 | 71.023秒 |
| green02 | 26／0／0 | 85.435秒 |
| affected01 | 79／0／0 | 134.474秒 |
| affected02 最终受影响模块 | **81／0／0** | **152.902秒** |
| full01 最终完整工程回归 | **962／0／0** | **621.079秒** |
| 独立证据工作区正常＋真实子进程恢复 | 两份工作区均完整，真实工具与文件核对通过 | 16.641秒 |

完整工程回归相比第一阶段增加32项测试。两个新增实际验收工作区的统计方法注册均为17。全回归与独立运行的源码指纹相同；没有利用测试期修改模型提示词、估计器或冻结评测答案。完整日志和JUnit不含新模型真实调用成绩，本轮没有收费API请求。

## 8. 薄入口与第三阶段接入

```powershell
python scripts/automation_v2_stage1.py --workspace "<独立工作区>" pause --task "<任务ID>" --confirm-control
python scripts/automation_v2_stage1.py --workspace "<独立工作区>" cancel --task "<任务ID>" --confirm-control
python scripts/automation_v2_stage1.py --workspace "<独立工作区>" resume --task "<任务ID>" --confirm-control
python scripts/automation_v2_stage1.py --workspace "<独立工作区>" budget --task "<任务ID>"
python scripts/automation_v2_stage1.py --workspace "<独立工作区>" show --task "<任务ID>"
```

第三阶段页面只需调用 create_hillstrom、approve、run/advance、pause、cancel、resume、task/steps/events/budget、report 及既有 export。页面刷新读取状态，不派发统计。需展示请求暂停与已经暂停的区别、接管原因、实际 Run 以及费用未知，不能靠界面状态代替域授权。后台线程若未来承载获批模型步骤，必须显式传递同一任务预算上下文；当前完整 UI 与模型规划入口仍未实现。

## 9. 剩余边界与阶段判断

- 只支持固定公开 Hillstrom 计划；不支持通用研究图、动态方法、任意目标或多表。
- 不做在途统计强杀；SQLite/文件冲突和未知进程身份安全停止。
- 历史中断在旧源码指纹下不能直接授权新源码执行；保留只读证据，需要新审核或单独迁移设计。
- 文件与SQLite间没有物理事务保证；可能产生待人工核查的孤立文件，不会自动“清理”或重算。
- 当前策略不尝试自动选择多个匹配Run，不提供覆盖冲突事实的人工特权。
- 模型预算传输基础已验证；真实自主规划与完整工作台未开放，本轮未进行官方模型收费调用。
- 语义修订预算是后续生成器必须复用的基础，当前固定计划仍不可原地修改。
- 没有多人、远程队列、云端恢复、主动诊断或新方法；未开始第三阶段UI。

**阶段判断：第二阶段满足本轮结束条件，可以在另行授权后进入第三阶段 UI 集成。** 实际依据为962项完整工程回归、81项受影响模块回归、两个真实统计Run，以及真实子进程退出后的运行调和与历史哈希保持。 本报告不代表通用模型研究能力或生产级发布验收。本轮完成后停止。
