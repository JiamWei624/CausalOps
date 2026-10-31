# 真实模型任务验收 · 0.10.0

日期：2026-11-01。固定12项业务语言任务，4项开发、8项留出。问题不指定统计方法名称；本地脚本保管审核事实与评分答案，方法键名形式的测试答案不发送给模型。数据为Wine Quality、Bank Marketing、Online Shoppers、Hillstrom邮件实验及固定种子模拟。

## 四步交付

1. **冻结任务。** 修改实现前保存问题、数据SHA-256、审核依据和成功标准，不用改写题目掩盖失败。
2. **真实端到端。** DeepSeek官方HTTPS、deepseek-flash、Responses协议执行路由、检索、候选、本地预授权审核、统计、问答与HTML导出。自动审核是测试脚本，不是模型批准或独立用户研究。
3. **按失败修复。** 修复字典未送达、咨询/计算误判、无必要多方法、重复拟合、结构不合格返回未进入有限修复、主要结果被体检覆盖、无引用解释、草案旧数字混入和长编号错误。HTTP错误不按结构修复重试，统计识别门控未放宽。
4. **核查业务解释。** 页面与报告统一参考水平、幅度与区间、实际含义和行动建议。数值取自保存运行，口径取自来源字典；OR不冒充概率比或百分点，关联不冒充干预收益，没有成本不计算利润或ROI。

## 各阶段不能合并成一个成功率

| 阶段 | 通过 | 如何解读 |
|---|---:|---|
| 修改前开发集 | 2/4 | 实际暴露口径与候选范围问题 |
| 首次留出集 | 7/8 | 第一次运行八项未曝光留出题 |
| 后续完整开发集 | 4/4 | 已曝光开发题上的修复后结果 |
| 后续完整留出题重跑 | 7/8 | 已曝光；失败项为同模型重复执行 |
| 定向修复复测 | 3/3 | 一项开发、两项已曝光留出题，不是新盲测 |
| 最终运行证据问答 | 7/7 | 均为通过引用检查的模型回答，无统计重算；其中一项经一次回答修复 |

早期不合格模型解释会显式采用本地摘要；可完成统计/导出，但不算模型解释成功。[结构化明细](results-summary.json)逐轮保留失败。首次与中间原日志保留本地E盘，工作区不上传Git。

## 独立数值核对

OLS、Logit与直接statsmodels同口径拟合核对系数；A/B与两组均值直接相减核对，绝对误差阈值1e-8。两项DID另以实体/日期虚拟变量的OLS核对点估计，误差约2.66e-15和3.55e-15；不把不同协方差自由度约定下的标准误冒充一致。预趋势不平行的合成数据保留估计但限制关联解释，诊断不能由模型覆盖。

## 实际业务表达示例

邮件实验结果期对照率10.62%、处理率18.28%，差异7.659个百分点，区间[6.995,8.323]个百分点；每千条同口径观测约76.59条，是样本尺度换算，不是承诺新增人数或外推预测。没有成本、毛利与外推依据，不宣称利润、ROI或全量推广。

酒精度关联模型纳入1,599行：酒精度每增加一个百分点，质量评分条件均值相差约0.3092分，区间[0.2736,0.3448]分。不能写成改变酒精度必然提高评分。

## 复现与边界

[冻结问题摘要](natural-task-cases.json)保留题目、数据指纹和本地评分目标。方法知识仍为20张卡、27条来源，没有增加全文文献库。所有新增资料、安装和缓存在E盘；原始微博数据、论文、密钥、用户ID值与私有对话不进入Git。

不据此宣称开放任务准确率、工时下降、企业收益或独立用户完成率。当前本机单用户私有验证版；独立用户验收后续再做。其他提供方主要是协议测试，不冒充真实API全覆盖。

## 原始来源

- [UCI Wine Quality](https://archive.ics.uci.edu/dataset/186/wine+quality)
- [UCI Bank Marketing](https://archive.ics.uci.edu/dataset/222/bank+marketing)
- [UCI Online Shoppers](https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset)
- [Hillstrom数据说明](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html)
- [Statsmodels OLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html)
- [Statsmodels GLM](https://www.statsmodels.org/stable/generated/statsmodels.genmod.generalized_linear_model.GLM.html)
- [LangGraph审核中断](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Scikit-learn泄漏与评估边界](https://scikit-learn.org/stable/common_pitfalls.html)

## 安装与交互验收

最终源码493/493、独立离线安装wheel493/493，均为零失败、零跳过。离线包包含139项哈希锁依赖及应用wheel；在新的E盘环境安装后，从源码目录外以隔离模式核对实际导入路径和0.10.0版本。

真实Chrome浏览器完成上传、批准前禁用、数据字典登记与复用、后台统计、主要结果选择、四部分结论、HTML导出、方法咨询及重载恢复，未发现页面异常。科学计数显示只改变展示，不更改证据数值。使用[Streamlit官方数值列配置](https://docs.streamlit.io/develop/api-reference/data/st.column_config/st.column_config.numbercolumn)。

这不是所有操作系统的安装保证；当前已验证Windows x64与Python3.11。独立用户易用性和提效仍待开展。

## 基准文件复现

先按下载脚本取得公开准备表，目录应包含v090/prepared下的wine_quality、online_shoppers、bank_marketing及prepared下的hillstrom_men_visit。运行`scripts/prepare_natural_benchmark.py --public-data-root <公开数据根目录> --output <空数据盘目录>`生成冻结题、审核口径与模拟数据；相同锁定依赖下应与本轮冻结SHA一致。再用`scripts/evaluate_natural_tasks.py --benchmark <输出目录>/frozen-benchmark.json --output <新的结果目录> --split development`运行真实API验收。保留原始轮次，不覆盖失败记录；真实模型并非确定性，不能保证复现同一成功率。

公开数据准备命令依次为：

```powershell
python scripts/download_validation_data.py --output E:/causalops-data/v090
python scripts/download_hillstrom_benchmark.py --output E:/causalops-data
python scripts/prepare_natural_benchmark.py --public-data-root E:/causalops-data --output E:/causalops-benchmark
```

本轮另从加载器指定镜像重新下载邮件数据并核对MD5与准备文件SHA；与冻结文件一致。重新生成的整个基准SHA与原始冻结SHA逐字节相同。[镜像来源与校验规则](https://github.com/maks-sh/scikit-uplift/blob/master/sklift/datasets/datasets.py)来自scikit-uplift原始加载器。未确认原数据再分发许可，因此仓库只包含脚本。
