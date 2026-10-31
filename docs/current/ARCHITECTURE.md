# 当前实际架构 · 0.10.0

日期：2026-11-01。图中组件均按当前源码核对；未来扩展见[路线图](ROADMAP.md)，历史方案见[历史索引](../HISTORY.md)。

![当前架构](../assets/architecture-current.svg)

## 从输入到结果

Streamlit → ResearchService → 安全字段与冻结DataContract → 结构化路由 → LangGraph方法研究子图 → 待审Plan与就绪检查 → interrupt → 使用者批准 → TaskRuntime与原统计执行器 → ToolResult → 主要运行结论、证据问答和报告。

结构化路由可读取数据类型及已登记口径，选择最少必要的主要分析。它不接收方法键名形式的测试答案，不确认人工事实。计划若更换已登记的结果或变量集合，进入有限修复或要求使用者先更新字典。

方法子图使用LangChain Core检索适配。通用检索不足时，以注册方法名称和原问题定向补检；最多三轮，停止条件包括依据齐备、没有新依据、达到预算或方法尚不支持。规则卡与实证案例分开。

## 代码职责

| 模块 | 职责 |
|---|---|
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
