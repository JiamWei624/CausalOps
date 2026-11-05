# CausalOps 源码阅读指南：一次批准如何变成一份可引用的结果

阅读基线为公开 Beta 的 5f350ab；本分支仅增加评测材料。先在纸上写下四个不同的标识。**sid** 指一个长期研究任务，**fid** 指一次请求对应的流程，**plan_id / plan_sha** 指某个计划及内容，**run_id** 指一次实际计算。打开同一个任务可以提出多个请求。一份计划可以有多个统计步骤；用户追问产生一个新流程，却不必产生新的统计运行。页面上的「已完成」必须结合它指的是流程还是运行来读。

## 两条实际轨迹

**新研究。** 在公开营销案例点击“创建研究任务并生成待审方案”。案例页先用 cohort 校验压缩包摘要、分组和计数，生成两组客户的输入表。create_task 登记数据，contracts.save 保存人工已核对的指标与研究条件。这个按钮直接调用 **service.start(..., mode='plan')**，在当前调用中走到待审中断。普通聊天框发起新研究则通过 BackgroundJobs.submit_start 提交后台作业。两种入口汇入同一张图，但最初的调度方式不同。

本轮营销任务的流程 c0b7160f53e54722a88e58c5e176943e 实际完成的节点依次为 load_context、route_intent、method_scope、method_retrieval、method_research、draft_plan、await_review、statistical_tool、execute_plan、answer_results（记录按 completed 事件排序；内层统计工具早于外层执行节点完成）。在审核页确认后，service.review 保存领域批准，jobs.submit 恢复原 fid。执行器对两组客户的二元访问指标计算均值差，再持久化。该任务有 1 条审批，产出运行 f78428c410df4425883ec446f270ffb2。报告解释的是两周访问率，未发邮件组 10.62%、男装邮件组 18.28%，绝对差约 7.66 个百分点。首页已有的案例数字不是这次运行的证明，运行记录才是。

**只读追问。** 在同一任务的对话框问“请只读取本次已保存报告：男装邮件与未发邮件组的两周访问率相差多少个百分点？请给出来源。”以先前公开 Beta 验收留下的真实浏览器记录为例，原计划运行 48daf29ead89465290f8690efc7a2de5；追问流程为 850cbf53928d4ab99d5ecba3343c008b。这一条不是本轮第四个试题。begin 将已有 run_id 写入新请求。路由保存 results，节点记录显示两次 method_retrieval，之后直接进入 answer_results。回答来源为“本地运行证据与单位换算”，引用同一个 run_id。没有 draft_plan、await_review 或 statistical_tool 节点。子图提供方法依据，数值取自所选运行的事实。整个会话仍只有原审批。若用户改问“明年的净利润”，两周访问证据就不能支持答案。

| 比较项 | 制定新研究 | 追问已保存报告 |
|---|---|---|
| 输入依据 | 上传数据、合同版本、研究问题 | 当前问题、会话内指定／解析的旧运行、旧运行绑定的口径 |
| 图中关键分支 | plan → 方法子图 → draft_plan → await_review | results → 方法子图 → answer_results；证据或引用不确定时可 clarify |
| 能否产生新数值 | 经本版计划批准并执行本地白名单工具 | 可依据原始事实作合法单位换算，不重新估计 |
| 写入痕迹 | 请求、检索、计划、批准、任务、运行与答案 | 新流程、检索、答案和引用；原运行保留 |
| 典型失败 | 字段或数据版本已变，拒绝沿用旧批准 | 指代不清、窗口不符、分母缺失；部分复杂问法仍可能误转待审 |

## 函数对照表

路径相对仓库根目录。读第一遍先看 UI、begin、主图、review、ask，再进入统计细节。下表的“返回／写入”区分了即时返回值和持久化副作用。

|源码、函数|调用者与输入|返回／写入和下游依赖|设计理由及边界|
|---|---|---|---|
|[ui/workbench.py](../../../src/causalops/ui/workbench.py) open_public_sample、render_history；[ui/marketing_case.py](../../../src/causalops/ui/marketing_case.py) 案例按钮|首页案例、历史选择器；已登记公开文件或用户选择的任务|酒样建任务后把 sid 放入 URL；营销入口显式保存合同并 start；历史页按任务列出计划和已有运行|示例初步概况、历史快照与一次新的实际计算分别呈现|
|[ui/assistant_app.py](../../../src/causalops/ui/assistant_app.py) render_assistant；[ui/graph_app.py](../../../src/causalops/ui/graph_app.py) render_graph_workspace|上传控件或已有 sid，聊天输入 q、父流程 chat_flow、可选任务模型|录入时预览 read_table；研究图入口调用 jobs.submit_start；保存待展示的 flow_id 并 rerun。watch_background 轮询作业状态|浏览器重绘不等于再次提交；没有建任务时还没有统计结果|
|[application/background.py](../../../src/causalops/application/background.py) BackgroundJobs.submit_start、submit、_run|界面输入 sid、question、mode、parent_flow_id，可指定 run_ids；恢复则提交已有 fid|返回 job 记录，SQLite 保存 queued/running/waiting_review 等状态；工作线程新建同一工作区的 ResearchService 并 continue_flow|队列检查和同一流程活动作业去重；最多四项活动作业，不等于多用户隔离|
|[application/research_service.py](../../../src/causalops/application/research_service.py) ResearchService.create_task、begin、start、graph、_drive；[application/run_context.py](../../../src/causalops/application/run_context.py) resolve|页面或后台提交表文件或已有上传，以及问题、父流程和运行选择|create_task 返回 sid；begin 建 fid 并绑定数据、合同、上下文及运行；start 在流程锁内驱动图。SQLite checkpointer 以 fid 作 thread_id|恢复依据持久状态；当前页面、上轮引用与最新运行可能是三个不同对象|
|同文件 decide_route；[orchestration/research_graph.py](../../../src/causalops/orchestration/research_graph.py) build_graph 内 load、route|图状态携带 fid；服务取已保存请求和口径|返回 RouteDecision，保存 route 输出；路由至 plan、results、method、profile、explore 或 clarify|业务语义和越权检查优先；模型有条件参与路由，固定模式与确定性分支可跳过模型|
|[orchestration/method_research.py](../../../src/causalops/orchestration/method_research.py) build_method_graph；[integrations/method_retriever.py](../../../src/causalops/integrations/method_retriever.py) search_bundle；[knowledge/retrieval.py](../../../src/causalops/knowledge/retrieval.py) MethodLibrary.search|主图 retrieve_methods → scope/retrieve/assess/finish，输入问题、候选方法、已登记条件|LangChain Retriever 将本地词法索引结果变成 Document，再比对命中卡片、校验引用、写入 retrieval 与 method_research。最多三次检索，可因无新证据或方法不支持停止|可复核检索的是本地方法卡和来源，不是临时联网搜论文；卡片齐全不能证明识别条件成立|
|[ui/model_setup.py](../../../src/causalops/ui/model_setup.py) task_model；[assistant/service.py](../../../src/causalops/assistant/service.py) _call；[llm/providers.py](../../../src/causalops/llm/providers.py) StructuredModelClient.complete_json|选择模型且任务绑定服务地址、模型及协议获准时，路由、提案或解释可请求服务；传入 system_instruction、user_payload、output_schema|受控 HTTP 请求、有限重试、响应结构校验、遥测；返回结构化对象。Responses 配置走 /responses|公开工作台当前这条路使用通用客户端。连接成功与本任务允许外发是两个判断。模型建议不能签署批准或产生统计事实|
|ResearchService.propose_researched → [assistant/service.py](../../../src/causalops/assistant/service.py) propose、validate_plan、store_plan|draft 节点拿 fid、检索结果、合同及目标。明确窗口与多步骤有本地构造分支；其他场景可生成模型候选|Plan 包含 objective、steps、citations、required_questions。按工具、字段和角色校验，保存计划版本与摘要，状态 awaiting_review|避免模型写入受保护的人为事实；非法候选可被拒绝，不能以描述统计静默替换不支持的研究|
|ResearchService.review、verify_approval；[application/data_contracts.py](../../../src/causalops/application/data_contracts.py) review_facts|审核页带 expected_plan_id、计划与数据哈希、核对项、human_confirmed；页面使用 dispatch=False，再提交后台|领域批准与版本、数据、方法资料、代码、事实、适用窗口绑定；图的 interrupt 被唤醒后再次 verify_approval|LangGraph 的 resume 只唤醒节点。更换指标、数据或计划后，旧收据不能授权新执行|
|ToolGateway.execute → AssistantWorkspace.execute → [assistant/contracts.py](../../../src/causalops/assistant/contracts.py) AnalysisTools.prepare、reconcile、execute、envelope|执行节点传 fid，核验批准，再逐步传入步骤设置、人工声明及 checkpoint|TaskRuntime 认领步骤，已完成可核对已有结果；exploration、research、advanced 三类适配器返回运行引用，附 plan_sha 和步骤序号|17 项注册方法是允许调用的入口。方法所需假设和验证深度并不一致|
|[general/service.py](../../../src/causalops/general/service.py) GeneralWorkspace.ingest、execute；[ui/controller.py](../../../src/causalops/ui/controller.py) run_versioned_workflow；[execution.py](../../../src/causalops/execution.py) execute_analysis；[estimators/randomized.py](../../../src/causalops/estimators/randomized.py) estimate_ab_test|本例 research 适配器传研究与修订 ID；数据适配为 DataFrame + CausalSpec|ingest 保存上传元数据及 Parquet。执行时核对 revision、数据指纹、分配与方法条件，再经 CausalOpsAgent 调用 Python 估计器，持久化研究运行、证据、轨迹及报告|数值由统计内核计算；探索或进阶方法会进入各自适配器，不全走 A/B 路径|
|主图 answer_results → ToolGateway.answer → AssistantWorkspace.facts、ask；[ui/assistant_app.py](../../../src/causalops/ui/assistant_app.py) show_run；[assistant/export.py](../../../src/causalops/assistant/export.py) attach_discussion|新运行读取 primary_run_ids；只读询问取 request.run_ids。输入问题、原运行及所属会话|验证归属、范围和指标字典，先处理可确定回答；其余情况才可能由模型按受限事实解释。结果写入本流程 answer，界面按运行展示和导出|同一数字来自不同指标时不能互换；有些复杂派生指标仍可能需要澄清|
    
## 在哪里看见这些状态

- **数据本体**在工作区 uploads 下的 Parquet。SQLite 里的上传记录引用它，研究合同描述列的业务含义。仅凭列名无法判断随机分配或因果关系。
- **任务、审核与执行**保存在 research.sqlite3 的不同表。workflow_jobs 是调度状态，workflow_flows 是请求状态，workflow_outputs 保存路线和答案，workflow_events 是节点记录，workflow_approvals 才是领域批准。workflow-checkpoints.sqlite 保存 LangGraph 中断位置。不要用“作业结束”代替“报告已生成”。
- **数值和出处**从 runs 下的 evidence、reports 与 traces 以及各适配器的运行记录取。按 run_id 反查才能回答“这句话支持的是哪次估计”。浏览器评测使用可见界面判定终点；事后核对底层事件属于评测控制器，不能让模拟操作者借此找按钮或答案。

自检：若用户只问“把上次绝对差换算成百分点”，应先追 run_id 与证据单位；若改问“换成购买率”，应寻找已匹配的购买率运行，否则生成新候选并重新审批。两者可能从同一个文本框发出，区别在所需证据和计算权限。
