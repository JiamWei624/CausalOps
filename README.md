<!-- release: 0.14.0 -->
# CausalOps

### 数据分析与研究工作台

CausalOps 是本地运行的数据分析助手。它帮助使用者理解表格、明确问题、制定分析计划，并调用统计工具生成可追溯的图表、结论和报告。模型负责建议与解释，数值计算由本地统计内核完成。

**当前版本 0.14.0 · Windows x64 / Python 3.11 · 本地单用户。** 代码开放范围与数据发送许可相互独立；本地工作区不随源码分发。它不是能从任意表自动证明因果关系的系统。

[完整示例教程](docs/current/PUBLIC_TUTORIAL.md) · [安装与故障排查](docs/current/INSTALLATION.md) · [使用说明](docs/current/USER_GUIDE.md) · [系统架构](docs/current/ARCHITECTURE.md) · [模型与隐私](docs/current/PROVIDERS.md) · [验收与限制](docs/current/VALIDATION.md) · [版本历史](docs/HISTORY.md)

![从数据到结论的用户路径](docs/assets/task-workflow-current.svg)

## 适用任务与操作入口

| 使用场景 | 操作入口 | 系统处理 |
|---|---|---|
| 需要了解样本结构与特征 | 上传 → 生成基础报告 | 本地计算缺失、分布、频数，生成图表与报告 |
| 分析目标尚未明确 | 上传后查看初步建议，或生成分析建议 | 根据安全字段摘要提出问题、列出待补信息；不编造研究发现 |
| 业务问题已明确，分析方法待定 | 直接在分析对话中提问 | 检索方法条件、拟定候选计划，在需要的地方要求确认 |
| 需要解读已有分析结果 | 继续问“幅度意味着什么”“有什么限制” | 读取选定运行的证据，核对引用，不重新估计 |

首次导入后，只需依次说明一行代表什么、关注哪个指标、希望回答哪类问题。未知可留空。无需先懂所有方法名。描述统计可以一键启动；回归或因果研究仍需确认分析单位、字段口径以及与方法相关的事实。未知的事实可以保留未知，系统不得替人勾选。

## 交互界面

[查看连续操作录屏](docs/assets/first-use-tutorial.webm) · [逐步图文教程](docs/current/PUBLIC_TUTORIAL.md)

截图来自真实浏览器验收，使用公开葡萄酒数据。没有展示密钥、个人研究数据或用户 ID。

![首页：直接导入或体验示例，模型连接可选](docs/assets/first-use-01-home.png)

![三步引导：确认目标指标](docs/assets/first-use-03-target.png)

## 首次使用与连续任务

1. 首页载入示例或导入自己的表。
2. 依次填写 **每行代表的对象 → 关注指标及单位 → 分析目标**。未知可留空，不自动认定随机实验。
3. 阅读待审计划；可先询问适用条件，再通过 **返回待审计划** 继续审核。
4. 明确核对后批准本次执行；普通聊天中的“同意”不能执行。
5. 阅读目标结论与图表，点击 **导出本次分析报告**，或继续追问限制。

## 连续任务与结果呈现

- 首页模型连接为可选折叠区，已配置的模型连接默认收起，并区分“已配置”与“连接已验证”；未知认证状态不显示为连接成功。
- 数据导入后自动展示规模、主要字段、缺失与重复情况，以及基于字段结构的初步建议。该步骤不发送数据、不执行估计、不修改原始记录。
- 选择建议或输入“采用第一项建议”时，系统核对同一任务、数据和口径版本，再建立待审方案。后续请求保留上文问题和方案引用，历史说明不构成当前批准权限。
- 结果优先展示分析结论。描述报告优先解释该次运行确认的目标指标，使用保存的统计量与证据引用；图表、诊断、完整方案和运行记录按需展开。
- 结果追问引用选定运行，不重复计算。“同意”等普通对话文字不替代审核按钮。

![分析结论与按需展开的支持材料](docs/assets/first-use-05-result.png)

## 安装与启动

已验证环境：Windows x64、Python 3.11。下面从仓库根目录执行；所有环境、缓存和工作区均可放在 E 盘。

```powershell
New-Item -ItemType Directory -Force -Path "E:/project-temp", "E:/project-cache/pip", "E:/project-cache/matplotlib"
$env:TEMP = "E:/project-temp"
$env:TMP = "E:/project-temp"
$env:PIP_CACHE_DIR = "E:/project-cache/pip"
$env:MPLCONFIGDIR = "E:/project-cache/matplotlib"
python -m venv "E:/causalops-venv"
& "E:/causalops-venv/Scripts/python.exe" -m pip install -r requirements-runtime-win-py311.txt
& "E:/causalops-venv/Scripts/python.exe" -m pip install --no-deps .
& "E:/causalops-venv/Scripts/python.exe" -m causalops.launch --workspace "E:/causalops-work" --port 8513
```

打开启动器给出的本机地址。首页可直接载入示例或导入 CSV / Parquet。模型连接为可选折叠区，每个数据任务分别控制外发许可。离线发行包另含固定 wheel、SHA-256 锁和安装器；Git 不存储大型依赖包。

## 架构与职责

![CausalOps 实现架构](docs/assets/architecture-current.svg)

| 层 | 实现与职责 |
|---|---|
| 用户交互 | Streamlit 首页连接、引导动作、问题卡片、待审计划、报告与追问 |
| 应用服务 | ResearchService 绑定数据、口径、计划、批准、运行与版本 |
| 工作流 | LangGraph 主图 + 方法研究子图；有限检索、检查点和人工中断 |
| 方法知识 | LangChain Core BaseRetriever + 字符 TF-IDF；20 张方法/实证卡、27 条来源 |
| 计算内核 | 三类执行器、17 项注册方法；本地统计、诊断与解释范围限制 |
| 证据 | SQLite 保存运行与工作流；结论绑定实际运行、口径及引用 |
| 模型连接 | 六类服务预设与结构化协议适配；密钥仅存内存，无静默换服务 |
| 扩展接口 | MCP 只读方法/证据查询；A2A 本机规则审阅，不授予执行或审批权 |

![方法依据与运行证据的两条通道](docs/assets/rag-evidence-current.svg)

## 可执行范围

- 描述与关联：描述统计、相关、OLS、Logit、Poisson。
- 实验与观察性研究：A/B、CUPED、回归调整、PSM、IPW、DoubleML、AIPW、共同处理时点 DID。
- 进阶研究：2SLS、清晰/模糊 RD，以及受限定数据条件约束的交错 DID。

接口支持不代表任意表均适用。工具外生性、无未观测混杂、平行趋势、无干扰等需要研究设计依据，不能只靠显著性或模型回答确认。完整限制见[方法合同](docs/METHOD_CONTRACTS.md)。

## 报告里有什么

报告按“参考水平 → 差异幅度与不确定性 → 实际含义与限制 → 后续建议”组织，附图表、样本口径、方法、诊断和证据。基础分布报告不假装回答了因果问题；没有成本与规模依据时不补写 ROI、收入或总体收益。

## 验收口径

[当前验收](docs/current/VALIDATION.md)分别报告回归测试、首次使用浏览器链路、真实模型任务和独立用户研究，不能互相替代。首次使用测试从无字段口径开始，不再把“已提供全部参数的任务能运行”当作新用户能上手。

本地后台为一个工作线程、最多四项排队；上传上限 50MB、10 万行、200 列，解码后上限 256MB。暂不提供多用户鉴权、分布式任务执行或通用预测训练/样本外评测流水线。

## 隐私与贡献

原始研究数据、用户/帖子 ID 值、论文全文、密钥、工作区数据库与私人对话不进入仓库。知识库保留来源与核对范围，原创摘要不冒充逐字引文；第三方数据许可独立于代码许可。当前不得直接作为公网多租户服务部署。

[贡献说明](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [第三方许可](THIRD_PARTY_NOTICES.md) · [文档索引](docs/README.md) · [后续计划](docs/current/ROADMAP.md)

```powershell
python -m pytest --basetemp "E:/causalops-tests"
```

[公开数据下载](scripts/download_validation_data.py)将数据保存到源码仓库外；[真实任务评测](scripts/evaluate_natural_tasks.py)要求预先固定任务和审核依据。独立外部用户验收尚未完成，不能宣称已证明节省工时或通用研究准确率。
