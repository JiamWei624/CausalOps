> **历史阶段记录**：本文保留当时的实现与验收状态，不作为当前版本说明。请查看[当前文档入口](README.md)及[当前架构](current/ARCHITECTURE.md)。

# 多模型接入与只读协作（0.7.0）

## 接入范围与实际验证

统一助手改用 ProviderConfig + StructuredModelClient，将服务身份、HTTP协议和本地结构校验分开。已有专业表单的旧DeepSeek客户端保持兼容；本轮通用配置作用于“分析工作台”，不会静默改写旧表单的启动环境。

| 页面预设 | 协议 | 输出与验证 | 验证状态 |
|---|---|---|---|
| DeepSeek 官方 | Responses；可选Chat Completions | JSON Object / JSON Schema / 提示JSON + 本地Schema | 官方账户实际核验、计划、问答、只读观察已通过 |
| OpenAI 官方 | Responses；可选Chat Completions | 同上 | 请求合同与错误路径测试；未持有账户密钥做真实验证 |
| Anthropic 官方 | 原生Messages | 提示JSON + 本地Schema | 请求合同测试；真实账户待验证 |
| 阿里云百炼/千问 | OpenAI兼容Chat Completions | JSON Object等，依具体模型支持 | 请求合同测试；真实账户待验证 |
| Gemini 官方兼容接口 | OpenAI兼容Chat Completions | 同上 | 请求合同测试；真实账户待验证 |
| 自定义HTTPS兼容接口 | Responses / Chat Completions | 依服务支持选择，本地校验不变 | 固定合同测试；第三方必须自行信任和核验 |

接口兼容不表示所有模型支持全部参数。API模型ID由使用者按账户权限填写，不能把桌面应用中的模型名称当作API模型ID。Anthropic协议按本轮官方文档使用Bearer认证、anthropic-version（默认2026-10-21）；提供版本设置，不声称已验证旧版或第三方Anthropic兼容服务。百炼须匹配地域、业务空间、密钥及官方地址。遇到模型不支持JSON模式时可明确选择提示JSON模式，本地仍严格校验；不会偷偷改变协议或服务商。

## 操作步骤

1. 打开分析工作台，创建或恢复任务，展开“模型配置与数据发送授权”。
2. 选择服务商，核对Base URL，填写账户实际可调用的模型ID及密钥。
3. 按服务文档选协议、输出模式、输出上限。核验按钮只发送固定最小测试，不包含研究问题、字段或数据。
4. 查看拟发送内容；明确授权当前任务向该服务地址、模型和协议发送。更换配置后须重新确认；新任务不继承授权。
5. 提问、审阅计划并使用本地统计工具；结果问答仍绑定所选择的运行。服务失败时显示原因，不冒充模型回答，不自动换另一家。
6. 同一浏览器会话可保留不同服务的非敏感配置；切换服务地址后需要重新输入该地址的密钥，不把另一服务的密钥自动带入。关闭会话后也需要重新输入。密钥不会保存到数据库、报告、Git或配置文件。显示密钥为主动选择。

发送范围仍是过滤标识后的字段元数据、汇总、研究问题、有限上下文及已登记数字事实，不发送原始行、用户/帖子ID值或完整论文。过滤不是匿名化安全证明。自定义服务意味着向所填地址外发，请先确认该服务可信；HTTPS与域名规则不是DNS重绑定的完整隔离方案。仅接入外部HTTPS，暂不接本机Ollama等HTTP服务。

## 可靠性设计

- 本地Schema检查、重复JSON键/非有限数值拒绝；截断、拒绝、工具调用内容不采纳。
- 原始错误响应不回显，密钥不写盘；已知密钥出现在模型文本时拒绝采纳。
- 不跟随HTTP重定向，不切换服务商；重试上限仅0至1次且限暂时性错误，同一配置内进行。
- 请求记录保存服务绑定、请求标识、用量和延迟；协议测试不等于统计正确性或跨模型准确率。
- 授权回调冻结服务配置，避免后续统计步骤重用变量造成错误授权；UI测试覆盖服务切换、密钥隔离和返回后重新确认。

## MCP：向宿主提供可查证的工具和上下文

MCP不负责生成正确结论。其作用是让支持MCP的宿主按明确合同使用本项目能力，而非复制粘贴资料。

| 工具 | 用途 | 不能做什么 |
|---|---|---|
| search_methods | 查方法卡、适用条件、诊断要求及来源 | 不能生成虚构文献 |
| read_method_source | 读取指定卡与章节的原创提炼、出处及版本 | 不任意下载URL或读本地路径，不冒充论文全文 |
| list_analysis_capabilities | 查询17项方法及配置合同 | 不直接执行统计 |
| read_run_evidence | 查已明确导出的某条运行数字事实 | 不读未经导出的研究数据 |
| check_evidence_citations | 核对事实ID是否属于指定运行 | 不证明自由文本推理正确，不验证识别假设 |

使用方式：在任务中明确导出运行证据，宿主以stdio启动 `python -m causalops.protocols.readonly_server --workspace "E:/my-causalops-workspace"`。项目内Codex与Claude配置生成脚本提供五项工具的白名单；需要宿主重新加载及其自身数据发送权限。当前轮未在另一个外部宿主完成实际会话验收，已用官方MCP客户端实测工具发现与调用。

## A2A：将明确任务交给独立审阅服务

本地A2A服务使用官方SDK、Agent Card、JSON-RPC消息、任务状态与结果Artifact。提供方法审阅、读取已导出证据、新增运行证据审阅。结果页点击“导出并审阅当前运行证据”即可使用。

新增检查涵盖事实清单非空、运行归属、有限数值、已识别P值范围、标准误非负及已识别区间顺序。工作区指纹、服务版本和本机端点必须一致；不会误用另一工作区服务。服务不持有模型密钥，不执行估计、不批准研究、不验证识别假设。它目前是独立进程中的确定性审阅器，不是第二个大模型，也不意味着实现了多模型独立研究。

| 比较 | MCP | A2A |
|---|---|---|
| 协作对象 | 宿主与工具/资料 | 发起方与独立任务服务 |
| 当前价值 | 方法、输入合同和运行证据的标准化查询 | 审阅任务交接、状态和结果可追踪 |
| 不保证 | 工具使用者推理正确 | 审阅方研究结论正确 |

后续可以将“规划、统计执行、审阅、报告”拆为服务，但应先定义独立职责与验收依据。报告可读性主要来自结论模板、指标定义、证据引用和表达评测，不能仅靠增加MCP或A2A获得。尚未开放任意远程Agent发现/委派、多租户鉴权、持久化A2A任务队列和自动跨模型路由。

## 官方依据

- [OpenAI结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)：JSON模式与Schema约束不同，必须本地校验。
- [DeepSeek Responses](https://api-docs.deepseek.com/api/create-response/)
- [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create)
- [百炼OpenAI兼容接入](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)
- [Gemini兼容接入](https://ai.google.dev/gemini-api/docs/openai)
- [MCP架构](https://modelcontextprotocol.io/docs/learn/architecture)
- [A2A规范](https://a2a-protocol.org/latest/specification/)

本轮核对日期2026-10-31。应按官方文档与账户实际可用模型维护，不能推断以后始终支持。Windows建议使用较短工作区路径；本轮深层测试目录曾触发Windows路径长度限制，已改用E盘短测试目录，未修改系统设置。
