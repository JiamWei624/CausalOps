# 上游技术来源与引用

新增AIPW通过已安装的DoubleML官方接口执行，没有把外部仓库源码拼接成自己的算法实现。

- DoubleML: https://github.com/DoubleML/doubleml-for-py （BSD-3-Clause），IRM模型、交叉拟合与ATE正交得分；统计结果依赖DoubleML安装版本。
- statsmodels: https://github.com/statsmodels/statsmodels （BSD-3-Clause），OLS、HC3/聚类/HAC协方差及数值对照。
- pandas: https://pandas.pydata.org/ ，描述统计、分组和输入合同。
- SciPy: https://scipy.org/ ，Pearson/Spearman系数。
- DoWhy: https://github.com/py-why/dowhy （MIT），已下载为设计、敏感性与反证扩展的参考，当前不声明已接入。

上游源码快照仅保存在开发者本地references中，按commit与SHA256登记，未执行外部安装脚本，不随本项目代码再分发。第三方依赖的wheel保留各自许可证。项目MIT不覆盖所有第三方技术、数据或文献。

验证数据：Palmer Penguins https://allisonhorst.github.io/palmerpenguins/ （数据仓库CC0）；tips来自seaborn示例数据仓库 https://github.com/mwaskom/seaborn-data ；季度宏观数据来自statsmodels官方数据目录 https://www.statsmodels.org/stable/datasets/generated/macrodata.html 。下载仅供本地验证；本源码包不包含这些真实CSV或其运行数据库。


## 0.4.0 方法检索与工具接口

MCP使用官方 Python SDK（https://github.com/modelcontextprotocol/python-sdk），本机验证版本2.3.0，遵循其MIT许可；通过依赖使用，未复制SDK源代码。Logit/Poisson通过statsmodels官方API调用。方法知识卡为原创简要提炼，来源、范围与核对日期见打包的causalops/knowledge/catalog.json。Management Science三篇论文仅按公开摘要提炼，并不随源码分发原始网页或PDF。UTD官方期刊清单只用于确认期刊范围，不证明方法或本项目效果。公开研究数据及其许可不由本项目MIT许可证代替。


## 0.5.0 research and interoperability extensions

- differences 0.3.0: GPLv3, https://github.com/bernardodionisi/differences.
- rdrobust 2.1.1: GPL-3.0-only, https://github.com/rdpackages/rdrobust.
- linearmodels 7.1: NCSA, https://github.com/bashtage/linearmodels.
- a2a-sdk 1.3.0: Apache-2.0, https://github.com/a2aproject/a2a-python.

The project LICENSE describes original CausalOps code, not a relicensing of dependencies. The complete offline bundle includes GPL dependencies and their exact-version upstream source distributions under third_party_sources, with original notices preserved inside distributions/wheels. Do not describe the combined bundle as unrestricted MIT-only software. Papers are linked and paraphrased in original short notes, not redistributed.


## 0.8.0 workflow integration

- LangGraph 1.2.19: MIT, https://github.com/langchain-ai/langgraph . StateGraph and interrupt are used through the installed official package, not copied tutorial code.
- langgraph-checkpoint-sqlite 3.1.3: local durable graph checkpoints, from the LangGraph project; separate from the research database.
- langchain-core 1.7.3: MIT, https://github.com/langchain-ai/langchain . BaseRetriever and Document adapt the existing provenance-checked method library; this is not an embedding or vector-database migration.

Resolved wheel versions, official PyPI download addresses and SHA-256 are recorded in docs/workflow-dependency-provenance.json. Bundled dependency wheels retain their upstream license files. LangSmith SDK is a transitive dependency; tracing is explicitly disabled in this release. No cloud tracing account or data upload is enabled.


## 随包公共示例（0.13.0 新增）

`src/causalops/sample_data/winequality-red.csv` 是 UCI Wine Quality 的原始红酒 CSV，按 CC BY 4.0 分发，未修改数据值。作者：Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009)。来源：https://doi.org/10.24432/C56S3T；官方数据页：https://archive.ics.uci.edu/dataset/186/wine+quality；许可：https://creativecommons.org/licenses/by/4.0/。读取时使用分号，不自动去重。来源、许可、SHA-256 与核对日期见同目录 `wine-quality.json`。该数据许可与代码 MIT 许可独立。除这一按明确路径与哈希核对的公共样本外，发布扫描仍阻断 CSV/Parquet/数据库等研究数据文件。
