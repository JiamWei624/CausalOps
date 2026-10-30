# CausalOps — 有证据的通用分析工作台

> 当前仓库为私有验证版本。最终版本确认前保持私有；公开发布由项目所有者另行决定。

CausalOps 是本机单用户的研究设计、统计分析、结果解释与证据保存工具。0.3.0 的主入口是 **分析我的数据**：上传 CSV/Parquet → 人工明确字段、组别与指标口径 → 保存草案 → 核对后执行 → 阅读图文结论、下载证据并恢复研究。它不自动发现因果关系，也不把显著相关写成业务提升。

## 新增独立方法

进入“分析我的数据”后，可选择四种分析任务：研究与效应、描述性统计、相关分析、线性关联回归。后三类不需要填写处理组或因果假设。

- **描述性统计**：字段类型、缺失比例、重复记录、有限值均值/标准差/分位数、分类频数与全表分母、分组汇总、日期分期汇总、直方图。IQR只标记，不自动删除；全缺失输出未计算，不填零。
- **相关分析**：Pearson、Spearman、每一对变量实际有效样本数与相关矩阵；不自动生成显著性筛选。
- **线性关联回归**：连续数值结果、数值/有限类别自变量；支持HC3、聚类稳健与HAC，明确完整案例规则，检查矩阵秩和样本维度；R²是样本内拟合度，不是预测或因果收益。
- **AIPW**：增加官方DoubleMLIRM交叉拟合ATE，与原有PLR区别在于允许处理效应异质。记录倾向得分截断和共同支撑，并按AIPW公式复算得分一致性；仍需无未测混杂等识别依据。

新增分析配置单独版本化，结果保存于工作区exploration-runs；无需复制原研究的人工假设。浏览器恢复旧运行保留其原口径。参考和后续方法合同见 `THIRD_PARTY_NOTICES.md` 与 `docs/method-extension-plan.json`。IV、RDD、DoWhy反证工具、Logit/Poisson列为后续合同，尚未标成可运行。

## 安装与启动

已验收平台：Windows x64，Python 3.11。当前发布不包含 Python 解释器。离线包包含 92 个带 SHA256 校验的 wheel；无需 Git、Java、Spark、Docker、数据库服务器或 API 密钥即可完成主流程。

解压到你选择的数据盘（避免系统盘），使用已有 Python 3.11：

```powershell
python install_offline.py --destination .venv
& ".\.venv\Scripts\python.exe" -m causalops.launch --workspace ".\workspace" --port 8505
```

源码安装（需要网络；具体解析版本以当时依赖源为准）：

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install ".[app,llm,dev]"
& ".\.venv\Scripts\python.exe" -m causalops.launch --workspace ".\workspace"
```

精确复现请使用离线包的 `requirements-win-py311-offline.lock`。应用代码可移植，其他 OS 尚未执行安装验收，不宣称已支持。所有研究副本、SQLite、运行证据、临时文件与应用缓存放在指定工作区。不要把工作区放进公开仓库。

## 首版支持范围

| 方法 | 输入与限制 |
|---|---|
| A/B | 两组、已知真实随机分配、每随机化单位一行，独立单位推断 |
| CUPED | 同 A/B，加人工核对的处理前数值指标 |
| 观察性关联回归 | 两组、明确控制变量；可含重复实体并按实体聚类；只报告条件关联 |
| PSM / IPW / DoubleMLPLR / AIPW-IRM | 两组、每实体一行、数值处理前协变量；需声明并诊断共同支撑、条件可交换性 |
| 日级面板 DID | 共同处理日期、从未处理对照、完整日级窗口、每实体每天一行；不接收交错处理/月度面板 |

所有方法先核对变量、缺失、数据角色与适用条件。声明不是经验验证；诊断通过也不能证明所有因果假设。首版处理字段必须恰有两个非空值，用户明确指定编码为0和1，不静默删除第三组，不擅自二分连续处理。

上传上限：50MB、100,000行、200列，解码后表内存估计上限256MB。CSV支持UTF-8/GB18030和逗号/分号/制表符。Parquet支持扁平表。大规模原始日志应先在自己的数据流程中整理为分析表，当前上传页不是分布式数仓。

## 研究与结果如何保存

- 原文件不改写，上传副本转存工作区的 Parquet；读取时核对文件和表内容指纹。
- 问题、字段映射、0/1编码、方法与指标定义冻结在草案版本中。修改设计要保存新版本；旧批准不继承。
- 每次运行关联具体草案与数据版本，报告可回到运行证据核对；历史记录不会被刷新覆盖。
- 结论按“基线—幅度—实际含义—行动建议”展示，附区间、方法限制与图表；没有合适分母时不编造相对增长率或ROI。
- 当前通用上传页使用**本地证据问答**，不是大模型对话；不重新估计、不联网、不将新上传数据/字段/问题发送模型。模型研究对话仍在独立高级模块，不自动继承作者旧数据的对外授权。

## 示例与隐私

合成演示用于检验统计行为。作者电脑的公开实验示例和真实微博研究是可选历史入口，发行包不包含原始微博数据、ID、论文、用户聊天、密钥、数据库或派生研究报告。公开数据请按原作者来源和许可另行获取。本项目MIT许可证仅覆盖本项目代码，不替代第三方代码与数据许可。

## 验证与贡献

```powershell
& ".\.venv\Scripts\python.exe" -m pytest --basetemp ".\test-temp"
```

源码测试使用合成数据。验收报告应分别记录单元回归、固定数据端到端、真实浏览器和干净安装，不把这些加成开放问题准确率。脚本运行时间不等于人工效率提升。

建议贡献：最小复现 → 明确方法假设 → 新的失败用例/独立数值参考 → 实现 → 回归验证。不要在Issue、测试或截图中加入密钥或真实用户记录。仅绑定127.0.0.1；不应直接部署为无认证公网服务。

RAG、MCP、A2A、自动数据清洗、任意交错DID与多用户权限管理均未作为本版已实现能力。

## 技术与方法来源

- [Python打包与虚拟环境](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/)
- [pip可复现安装与哈希锁定](https://pip.pypa.io/en/stable/topics/repeatable-installs/)
- [Streamlit官方文档](https://docs.streamlit.io/)
- [pandas读取CSV](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html)
- [statsmodels](https://www.statsmodels.org/stable/)
- [linearmodels面板模型](https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.html)
- [DoubleML官方指南](https://docs.doubleml.org/stable/)
- [MIT许可证](https://spdx.org/licenses/MIT.html)
