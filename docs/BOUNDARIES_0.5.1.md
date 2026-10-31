# CausalOps 0.5.1：方法边界与界面更新

## 用户界面

主入口为“数据分析与研究工作台”。标签为研究计划与讨论、结果与报告、方法与文献、进阶研究设计及使用评测。移除宣传式、拟人化表述；保留字段英文名以便核对。历史计划、运行编号与审批记录保持不变，历史报告不追溯改写。

扩展报告按主要结论、估计幅度与不确定性、识别诊断与稳健性、解释范围与后续工作、设计与复现记录组织。图表和表格使用中文标题，极小P值以科学计数法表示。

## 工具变量

一个内生处理，最多8个排除工具；保留官方linearmodels 2SLS。新增指定beta0的AR型检验：将Y−beta0*D对[X,Z]回归，对排除工具的系数联合检验为零。使用statsmodels HC1或单向聚类协方差与渐近卡方分布。限制矩阵协方差非正定或奇异时报告不可计算。当前无AR置信集合或CLR，不能把常规2SLS区间描述为弱工具稳健区间；工具有效性仍需实质论证。本实现不是linearmodels中同名的过度识别检验，不提供多工具渐近或少簇修正。

来源：
- https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.wald_test.html
- https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html
- Mikusheva & Sun, Weak Identification with Many Instruments，第4.1节起始部分，PDF查看器第15页：https://economics.mit.edu/sites/default/files/2023-08/paper.pdf

## 清晰与模糊断点

使用rdrobust 2.1.1官方实现。主设定为局部线性p=1、偏差校正q=2、三角核和mserd带宽；估计、标准误及区间均提取Robust行。模糊断点使用fuzzy=实际二元处理，需要排除限制与单调性论证。本版约定右侧处理概率增加，方向错误或跳跃精度不足时降低解释等级；不以处理跳跃显著证明强第一阶段。

带宽敏感性预先固定为主带宽h与偏差带宽b的0.75、1、1.25倍。主结果不随敏感性显著性调整；无法计算的行仍保留状态，不记为0。主带宽有效样本不足或局部独立簇少于30时停止当前推断。模糊断点的处理概率跳跃使用与主估计完全相同的h与b。

尚无正式密度/操纵检验、协变量连续性检验、安慰剂阈值、弱第一阶段稳健区间。本地分箱均值图不是拟合曲线或识别检验。

来源：https://github.com/rdpackages/rdrobust （同时核对已安装2.1.1 Python接口文档）。

## 交错DID

沿用differences 0.3.0 ATTgt及0.5.0已验证的接口兼容。平衡面板、连续整数期、至少两处理批次、实体层聚类及时间不变处理前协变量限制保持。上层政策聚类、不平衡面板、可逆处理与bootstrap同时置信带仍未支持，程序应停止而非自动降级数据结构。

## 权限和证据

模型仍不能生成已确认研究事实、接受计划或执行分析。AR检验、处理概率跳跃和带宽敏感性结果写入带运行编号的数值证据，继续接受本地引用校验。研究者审核不等同于假设已被统计验证。未测试或未实现的项目显示在方法边界表中。

数据、缓存与运行记录写入E盘本地工作区，不修改原始微博研究。GitHub保持私有。所有测试为程序验证，不代表真实陌生使用者效率。
