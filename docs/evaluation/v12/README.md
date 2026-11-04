# CausalOps Eval V1.2 · 研究任务与结果

[中文评测报告](REPORT.md) · [失败案例与修复建议](REVIEW.md) · [汇总数据](metrics.json) · [固定十题原始基线](../v1-baseline/BASELINE.md)

## 实验设计

正式协议与判据固定在提交 `ac34580`。两种模式各 15 题 × 3 次，共 90 次；另有官方模型 C07 冒烟 1 次。每次建立独立 SQLite 工作区，重复之间不共享对话。固定 10 题使用 V1 原运行器和原评分器。两套题的分母分别报告。

- **输入与数据。** [任务定义与合成数据生成器](../../../src/causalops/evaluation/v12/inputs.py)给出门店日和顾客调查两套 96 行合成表，按固定种子重建。每题用户背景、问题和后续操作均可复现。没有向模型提供评分规则，没有使用私人研究数据。
- **门禁前建议。** 每轮模型任务先用官方连接请求独立的结构化研究建议，记录原始输出、方法名、理由、字段、必要条件。此探针不作为后续审批或工作流上下文；若它失败，该次计为失败。人工复核应重点阅读同义方法、替代方法和澄清问题，区分方法错误与词表不全。
- **实际工作流。** 正式助手使用同一供应商配置执行适用的路由、计划和解释节点；部分节点由确定性规则直接处理。多轮题的背景计划及历史报告通过相同的本地服务和测试操作者审核预先建立。背景运行与目标运行分别记录。C11 实际提交已失效版本，C14 检查越权指令；C15 请求停止并恢复后，测试操作者再决定是否按版本批准。
- **独立评分。** [冻结评分器](../../../src/causalops/evaluation/v12/rubric.py)分别检查原始建议、领域批准的时间与数据/计划指纹、终态判据。方法咨询不要求给出唯一方法。有实际运行时才核验其批准来源；未触发执行不等于门禁已被主动攻击。报告里的“阻断率”包含澄清而没有开始估计的请求。C09 支持相关系数和可复核的简单回归；历史报告题以选定运行的事实 ID 和已知均值交叉核查。
- **缺失和超时。** 正式批次写入包含全部题次的 manifest，各次外层时限为 180 秒；评分保留接口异常和超时。无有效结构或未触发 Plan 的任务不能进入方法/Plan 的有效分母，仍留在整体任务分母。此次实际无超时中断；发生了 3 次网络异常。每题三次不是 45 个独立研究场景。

## 重跑

从该开发分支根目录运行，使用现有 Python 3.11 工程环境。请设定独立评测输出目录。真实模式必须显式授权，认证信息通过环境变量或终端隐藏输入提供。

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
$env:CAUSALOPS_EVAL_GIT='git'
$py='./.venv/Scripts/python.exe'
& $py -m causalops.evaluation.v12 --output ./artifacts/causalops-eval-v12 --mode local --rounds 3 --jobs 2
& $py -m causalops.evaluation.v12 --output ./artifacts/causalops-eval-v12 --mode deepseek --rounds 3 --jobs 3 --official-consent --smoke-first
```

固定集复测、数据下载及无需网络的参考数值见 [V1 手册](../CAUSALOPS_EVAL_V1.md)。运行后的 `local-*`、`deepseek-*` 和固定集 `eval-*` 分别对应下方三个参数。离线报告另选一个尚不存在的目录。

```powershell
& $py -m causalops.evaluation.v12.report --local <规则批次> --live <官方模型批次> --fixed <十题批次> --out <新报告目录>
```

每题的 `observation.json` 保存真实工作流节点、审核回执、运行、答复及错误；`responses.jsonl` 保存结构验证结果、原始回复、响应时长、用量和服务商请求标识；`requests.jsonl` 记录开始发送的请求。按题号与尝试编号读取 `score.json`、批次 `results.json` 以及汇总后的 `review-queue.json`。不把自动化操作计入真人试用。费用按服务商记录的缓存命中和实际时段估算，无回执请求的费用未知。

## 集成与合并建议

此次开发从 `feature/causalops-eval-v1` 的 `4f25864` 派生 `feature/causalops-eval-v1-2`；核查远端 main 为 `058d3df`。V1.1 的时序门禁约束 causal 目标下的 predictors 和 covariates，审批与执行复查版本，实体审计进入用户答复。V1.2 复用这些生产入口，未修改统计内核、固定十题、审批逻辑或主界面。

建议两步审阅：先审核 V1/V1.1 的产品与门禁变更，再单独审阅 V1.2 的评测协议、调用记录和失败案例。合并前重新比较最新 main，跑固定十题、全量 pytest 和无收费的离线记录校验。真实付费批次只由获授权的维护者手动启动，不写入自动 CI。该方案不执行合并或推送。
