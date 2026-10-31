# 架构图源

0.8.0首个闭环已实现；当前实现与完整目标图明确分开。完整目标中的后续条目尚未全部运行，版本依据见[架构核查](../ARCHITECTURE_REVIEW_0.7.0.md)。所有图为CausalOps原创，不复制飞书图示。

## 当前实现

```mermaid
flowchart TD
    UI[Streamlit] --> Service[ResearchService]
    Service --> Graph[LangGraph StateGraph]
    Graph --> Retriever[LangChain Core Retriever]
    Graph --> Review[interrupt / 领域批准]
    Review --> Gateway[固定 ToolGateway]
    Gateway --> Runtime[TaskRuntime / AnalysisTools]
    Runtime --> Tools[原17项统计方法]
    Tools --> Evidence[ToolResult / 精确证据 / 图文报告]
    Evidence --> Answer[运行级问答]
    Graph --> Checkpoints[独立图检查点 SQLite]
    Service --> Domain[研究版本与批准 SQLite]
    Graph --> Provider[可选多模型网关 / 接收配置授权]
```

## 目标职责

```mermaid
flowchart TB
    UI[Streamlit 交互] --> Service[拟增 ResearchService]
    API[未来可选 HTTP / SSE] --> Service
    Service --> Graph[拟增 LangGraph Supervisor]
    Graph --> Subgraphs[计划 / 方法 / 结果 有界子图]
    Graph --> Models[保留多模型网关与授权]
    Subgraphs --> LC[拟增 LangChain 检索与工具适配]
    LC --> Gateway[拟增 ToolGateway]
    Subgraphs --> Gateway
    Gateway --> Runtime[保留 TaskRuntime / AnalysisTools]
    Runtime --> Statistics[保留 17 项统计方法]
    Statistics --> Evidence[保留 ToolResult / 证据 / 报告]
    Runtime <--> Domain[保留领域 SQLite / Parquet]
    Graph --> Checkpoints[独立图检查点]
    Gateway --> Protocols[只读 MCP / 规则 A2A / 拟增客户端]
```

## 研究工作流

```mermaid
flowchart TD
    Input[同一任务入口] --> Supervisor[结构化 Supervisor]
    Supervisor --> Clarify[缺少事实时集中澄清]
    Supervisor --> Retrieve[方法 / 口径咨询]
    Supervisor --> Plan[新分析待审计划]
    Supervisor --> RunEvidence[既有运行证据问答]
    Retrieve --> Coverage[检查出处和覆盖]
    Coverage -->|预算内有缺口| Retrieve
    Coverage -->|足够或到预算| Explain[有依据说明或明确不足]
    Plan --> Review[人工接受与批准 / interrupt]
    Review --> Validate[领域服务核验计划与数据摘要]
    Validate --> Runtime[TaskRuntime 复用或执行]
    Runtime --> RunEvidence
    RunEvidence --> Verify[本地数值与引用校验]
    Verify --> Report[结论 / 图表 / 报告]
    RunEvidence -->|需新估计| Plan
```

## 检索与精确证据

```mermaid
flowchart TD
    Methods[方法资料与来源] --> Retrieval[LangChain 检索适配 / 拟增]
    Business[业务口径与人工确认合同] --> Retrieval
    Retrieval --> Check[覆盖与引用检查]
    Check -->|预算内补充| Retrieval
    Check -->|无更多依据| Missing[说明不足]
    Check --> Context[研究解释上下文]
    Run[指定运行的结构化证据] --> Exact[精确数值与归属查询]
    Exact --> Context
    Context --> Validation[Schema / 数值 / 引用 / 解释上限]
    Validation --> Conclusion[基线—幅度—实际含义—行动]
```

## 工具调用边界

```mermaid
flowchart TD
    Model[模型候选工具调用] --> Adapter[LangChain 工具适配 / 拟增]
    MCP[白名单 MCP 客户端 / 拟增] --> Gateway[ToolGateway / 拟增]
    Adapter --> Gateway
    Gateway --> Check[Schema / 效果 / 范围 / 授权 / 预算]
    Check --> Read[只读查询]
    Check --> Compute[经领域批准的统计]
    Check --> Export[受限工作区导出]
    Check --> External[单独同意的外部读取]
    Compute --> Runtime[现有 TaskRuntime]
    Denied[批准 / 授权变更 / 数据删除] -. 不作为模型工具 .-> Gateway
```

## 记忆与事实

```mermaid
flowchart TD
    Graph[图检查点：执行位置与引用] --> Context[统一研究上下文]
    Chat[聊天摘要：辅助且未经确认] --> Context
    Domain[领域库：批准 / 运行 / 精确证据] --> Context
    Contract[人工确认合同：口径与测量时点] --> Context
    Sources[知识索引：来源与访问范围] --> Context
    Context --> Verify[任务 / 数据 / 计划 / 运行范围核验]
    Verify --> Answer[受限解释与下一步]
    Chat -. 经人工登记后另建版本 .-> Contract
```

## 从实际编译图生成的流程

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	load_context(load_context)
	route_intent(route_intent)
	retrieve_methods(retrieve_methods)
	draft_plan(draft_plan)
	await_review(await_review)
	execute_plan(execute_plan)
	answer_results(answer_results)
	answer_method(answer_method)
	profile_data(profile_data)
	clarify(clarify)
	__end__([<p>__end__</p>]):::last
	__start__ --> load_context;
	await_review -. &nbsp;rejected&nbsp; .-> __end__;
	await_review -. &nbsp;approved&nbsp; .-> execute_plan;
	draft_plan --> await_review;
	execute_plan -. &nbsp;end&nbsp; .-> __end__;
	execute_plan -. &nbsp;answer&nbsp; .-> answer_results;
	load_context --> route_intent;
	retrieve_methods -. &nbsp;method&nbsp; .-> answer_method;
	retrieve_methods -. &nbsp;results&nbsp; .-> answer_results;
	retrieve_methods -. &nbsp;plan&nbsp; .-> draft_plan;
	route_intent -.-> clarify;
	route_intent -. &nbsp;profile&nbsp; .-> profile_data;
	route_intent -. &nbsp;method&nbsp; .-> retrieve_methods;
	answer_method --> __end__;
	answer_results --> __end__;
	clarify --> __end__;
	profile_data --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
