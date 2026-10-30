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
