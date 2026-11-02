<!-- release: 0.16.0 -->
# CausalOps

CausalOps 是供业务分析人员本地使用的数据分析与研究工作台。使用者导入表格、确定指标并审核分析计划，工作台调用统计程序生成报告。每次运行保留样本口径、诊断结果和证据，供后续追问与复核。

**公开预览 0.16.0**　已验证环境为 Windows x64、Python 3.11，采用本地单用户工作区。首次试用可以使用随包提供的公开数据，无需配置模型密钥。

[安装说明](docs/current/INSTALLATION.md) · [图文教程](docs/current/PUBLIC_TUTORIAL.md) · [功能手册](docs/current/COMPLETE_MANUAL.md) · [系统架构](docs/current/ARCHITECTURE.md)

## 安装与启动

Windows 安装时建议使用较短的项目和工作目录，例如 `E:\CausalOps` 和 `E:\co-work`。部分系统限制完整路径长度，过深的目录可能导致报告文件写入失败。

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

## 首次分析

在首页或侧栏 **分析示例** 选择 **葡萄酒质量分析**。公开样本已预填观测对象与质量评分。上传自己的表格时，先核对每行代表的对象、目标指标及单位；尚未确定问题时，可以先查看样本分布。**我的分析** 用于恢复已有任务，**专业分析** 提供显式的方法配置。

![从导入数据到审核计划、读取运行结果的用户操作顺序](docs/assets/task-workflow-current.svg)

**图 1　分析任务与人工审核。** 基础报告可作为确定问题的起点。计划中的数据、指标或观察期有变化时，需要重新核对。结果追问读取选定的运行记录。

[葡萄酒示例操作录屏](docs/assets/research-016-demo.webm) · [逐步截图与操作说明](docs/current/PUBLIC_TUTORIAL.md) · [五类公开数据的使用记录](docs/current/REAL_DATA_EXPERIENCE.md)

## 系统架构

研究服务管理任务版本与执行批准。工作流检索方法依据并组织待审计划；批准后的计算交由本地统计执行器。使用外部模型时，数据摘要的发送许可由当前任务单独管理。

![CausalOps 本地组件、外部模型服务及调用关系](docs/assets/architecture-current.svg)

**图 2　组件与调用关系。** 方法检索为研究设计提供依据。解读既有结果时，研究服务按运行标识读取已保存的证据；更换模型不会改变已经保存的数值。

[实现模块与源码入口](docs/current/ARCHITECTURE.md) · [模型连接与隐私](docs/current/PROVIDERS.md) · [研究质量检查](docs/current/RESEARCH_QUALITY.md)

## 可执行范围

- 描述与关联：描述统计、相关、OLS、Logit、Poisson。
- 实验与观察性研究：A/B、CUPED、回归调整、PSM、IPW、DoubleML、AIPW、共同处理时点 DID。
- 进阶研究：2SLS、清晰/模糊 RD，以及受限定数据条件约束的交错 DID。

接口支持不代表任意表均适用。工具外生性、无未观测混杂、平行趋势、无干扰等需要研究设计依据，不能只靠显著性或模型回答确认。完整限制见[方法合同](docs/METHOD_CONTRACTS.md)。

## 案例：营销邮件与两周访问率

Hillstrom 公开营销实验提供了一个可复核的问题：分配到男装邮件组的客户，在随后两周内访问网站的比例，比未发邮件组高多少？

![未发邮件组两周访问率为 10.62%，男装邮件组为 18.28%](docs/assets/hillstrom-visit-rates.svg)

**图 3　两组客户的网站访问率。** 两组相差 **7.66 个百分点**，约相当于每 100 名客户多 8 名访问者。以未发邮件组为分母，相对增幅为 **72.14%**。绝对差的 95% 置信区间为 7.00 至 8.32 个百分点。两项换算均采用未舍入的组内访问率。图中衡量的是两周访问行为；若要估算下一年度净利润，还需对应期间的收入、退货和成本数据。

[实验数据来源](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html) · [复算与区间核对](docs/current/VALIDATION.md)

## 任务验收与适用限制

| 检查项目 | 本轮实测 |
|---|---|
| 找到指定报告 | 6/6 条模拟路径在工作台选中了正确的访问率或购买率报告。另设 2 次选错报告，均提示切换。 |
| 解读两种单位 | 6/6 条路径引用的百分点差和相对变化与原始实验数据复算一致。 |
| 追问明年净利润 | 保留旧报告后重复追问，12/12 次进入澄清，未沿用旧数字或创建新计划。 |

以上是自动化模拟。独立参与者的任务完成率与用时仍待测量。

[当前验收](docs/current/VALIDATION.md)分别报告回归测试、首次使用浏览器链路、真实模型任务和独立用户研究，不能互相替代。首次使用测试从无字段口径开始，不再把“已提供全部参数的任务能运行”当作新用户能上手。

本地后台为一个工作线程、最多四项排队；上传上限 50MB、10 万行、200 列，解码后上限 256MB。暂不提供多用户鉴权、分布式任务执行或通用预测训练/样本外评测流水线。

## 隐私与贡献

原始研究数据、用户/帖子 ID 值、论文全文、密钥、工作区数据库与私人对话不进入仓库。知识库保留来源与核对范围，原创摘要不冒充逐字引文；第三方数据许可独立于代码许可。当前不得直接作为公网多租户服务部署。

[贡献说明](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [第三方许可](THIRD_PARTY_NOTICES.md) · [文档索引](docs/README.md) · [后续计划](docs/current/ROADMAP.md)

```powershell
python -m pytest --basetemp "E:/causalops-tests"
```

[公开数据下载](scripts/download_validation_data.py)将数据保存到源码仓库外；[真实任务评测](scripts/evaluate_natural_tasks.py)要求预先固定任务和审核依据。独立外部用户验收尚未完成，不能宣称已证明节省工时或通用研究准确率。

[使用说明](docs/current/USER_GUIDE.md) · [统计核查](docs/current/STATISTICAL_AUDIT.md) · [版本历史](docs/HISTORY.md) · [项目对比评审](docs/current/PROJECT_REVIEW_2026-11-03.md)
