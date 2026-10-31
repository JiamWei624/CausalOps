> **历史阶段记录**：本文保留当时的实现与验收状态，不作为当前版本说明。请查看[当前文档入口](README.md)及[当前架构](current/ARCHITECTURE.md)。

# LangGraph首个迁移闭环（0.8.0）

状态：已实现首个闭环，保留原工作台供切换。完整目标架构中的通用外部MCP客户端、长期记忆治理、检索补充子图和HTTP/SSE仍未全部迁移。不能把首个闭环写成整套目标架构完成。

## 实际入口与分工

`Streamlit → ResearchService → StateGraph → MethodRetriever → 待审Plan → interrupt → 领域批准 → ToolGateway → TaskRuntime / AnalysisTools → ToolResult → 运行级问答`

| 组件 | 代码 | 实际责任 |
|---|---|---|
| 应用服务 | src/causalops/application/research_service.py | 登记任务、请求路由、流程记录、版本批准、恢复与查询 |
| 并发边界 | src/causalops/application/locking.py | 每流程OS文件锁，进程退出后自动释放；不并发重放同一流程 |
| 编排图 | src/causalops/orchestration/research_graph.py | 真实StateGraph、条件边、审核中断与结果路径 |
| 检索适配 | src/causalops/integrations/method_retriever.py | LangChain Core BaseRetriever/Document；保持原TF-IDF排名、来源和指纹 |
| 工具入口 | ToolGateway | 固定的方法读取、已审计算、运行回答三个入口；不是任意工具执行框架 |
| 界面 | src/causalops/ui/graph_app.py | 候选审核、实际步骤、报告、运行选择与持续追问 |
| 原统计内核 | assistant/runtime.py、contracts.py及统计模块 | 保留原数值实现、诊断、执行权和结果调和 |

版本为LangGraph 1.2.19、SQLite检查点3.1.3、LangChain Core 1.7.3，来源和下载哈希见[依赖记录](workflow-dependency-provenance.json)。没有为了框架名称额外安装完整LangChain组件集。

## 从输入到结果

1. 上传CSV/Parquet或选择已有本地上传，检查文件合同，登记任务。原始文件不修改。
2. 使用者可明确选择计划、方法、结果或数据概况；自动模式有模型时使用结构化枚举路由，无模型时明确采用本地规则。
3. 方法检索实际调用LangChain Retriever接口，保留原方法卡、章节出处和知识库指纹。计划使用同一次检索结果，不另取相近引用冒充。
4. 新分析保存待审版本，LangGraph执行到interrupt后暂停。此时没有统计运行，也没有自动确认科学假设。
5. 使用者在页面核对计划和必要事实，点击“接受计划并批准本次执行”。领域服务登记独立批准，再唤醒图。
6. 继续前核对任务、计划摘要、数据双指纹、人工确认、知识库和执行代码。恢复命令的任意内容都不能代替领域批准。
7. ToolGateway交给原TaskRuntime取得执行权、计算或调和已有运行；方法条件不满足仍会阻断。
8. 回答读取具体运行证据。方法咨询不估计，纯结果追问不重新计算。新设计产生新候选，不改写原运行。

## 存储与恢复

- research.sqlite3：原研究记录，以及workflow_flows、workflow_approvals、workflow_outputs、workflow_events。
- workflow-checkpoints.sqlite：LangGraph独立检查点，仅保存流程/计划引用、路线与阶段，不保存模型客户端、密钥、原始表或完整对话。
- workflow-locks：本机流程锁；统计本身继续使用原TaskRuntime的进程身份与执行令牌。
- assistant_plan_requests：请求与计划的原子映射。图节点重入时复用原候选；不因恢复而新增计划版本。

两套SQLite不是一个分布式事务，不能声称exactly-once。计划创建通过原子请求键去重，统计运行依赖原执行权和结果调和。解释请求在异常后的重试可能再次调用模型，但不会因此重算统计。图状态损坏不自动猜测恢复，原研究结果保留。

## 使用方法

开发者本机双击项目根目录“启动LangGraph工作台.cmd”。独立环境位于E盘，默认复用原artifacts/general-workspace中的研究历史。浏览器访问http://127.0.0.1:8513/ 。历史记录不转换为伪造的图状态；只有新请求进入图。

可通过“使用LangGraph研究流程”切回原界面。不要让两个工作台窗口同时修改同一任务。配置模型和接收方授权仍使用原界面，不自动读取环境里的密钥，不向第三方追踪服务上传研究信息。

从源码安装可使用固定运行依赖；最小工作流额外依赖也登记在pyproject的workflow extra中。文件、缓存、日志和数据库均应明确指定E盘。离线包使用对应平台和Python版本，不混用旧版本的应用wheel。

建议首次提问：“请分析这张表的缺失和分布”。审核后再问：“本次样本量是多少，有什么解释限制？” 方法咨询可问：“DID适用条件和平行趋势是什么？”

## 已验收与尚未完成

本轮验收包含真实图中断、SQLite持久恢复、拒绝与伪造批准、版本失效、领域数值对照、模型合同、真实浏览器上传与下载。新增模型路由/输出的自动化测试使用可控测试替身；是否另有真实联网模型调用，以本轮验收记录为准，不用替身成功冒充供应商成功。

当前还没有任意表自动完成因果识别、通用MCP客户端、全部目标子图、多用户鉴权、模型自批、A2A自主审稿或独立用户效率提升的证据。现有MCP只读服务与A2A规则服务保持原边界。完整迁移目标见[迁移方案](LANGGRAPH_MIGRATION_PLAN.md)。


## 本轮验收记录

- 源码与独立离线安装wheel环境分别432项回归通过，包含31项新增工作流测试。
- 三个独立Python进程分别创建暂停流程、重启批准执行、再次重启追问；图检查点可读，未重复生成统计运行。
- 实际浏览器完成上传、审核前禁用、明确审核、计算、报告下载、结果追问、方法咨询和刷新恢复，无页面异常。
- DeepSeek官方API在固定合成数据上完成结构化路线、候选、结果解释和追问；共5次成功请求，记录25,992 tokens。有一轮解释因事实引用数量超限被本地拒绝，随后在有限修复中通过。没有向API发送真实微博数据或原始合成行。

以上模型与流程验收是开发者自动化测试，不是独立用户试验，不构成效率提升或开放任务成功率。实际文件与安装验收的最终结果保存在本地交付报告中。

新界面尚未提供后台任务队列、HTTP/SSE服务或图级取消按钮；长统计步骤仍在本地Streamlit任务线程中执行。现有统计运行时的协作式取消仍保留在原工作台入口。
