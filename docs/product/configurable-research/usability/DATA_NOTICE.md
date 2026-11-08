# 试用数据来源与许可

`dataset-A.csv`是OpenIntro包的`gender_discrimination`公开教学表，48行、两个分类字段。CSV转换的原始R数据SHA-256为`582a1d3311f6a5e7ee06e94d31e96c76c9cb7182d45912ba59682c0e1782de65`，CSV为`7d5a3a8b0f87b44aead0e312d960653482ea62f744fc390fe3364c64a7f39988`。未手工重建数值，没有附加个人信息。

上游：[数据页](https://www.openintro.org/data/index.php?data=gender_discrimination)、[设计与适用范围](https://openintro-ims.netlify.app/foundations-randomization)、[原始R数据](https://raw.githubusercontent.com/OpenIntroStat/openintro/main/data/gender_discrimination.rda)、[上游包许可声明GPL-3](https://raw.githubusercontent.com/OpenIntroStat/openintro/main/DESCRIPTION)及[GPL-3全文](https://www.gnu.org/licenses/gpl-3.0.txt)。项目主程序的MIT许可不替代数据许可。本公开快照不包含原始表、既有本地试用包或论文正文。

`dataset-B.csv`由本期准备脚本确定性生成，是24名虚构试用者的二元结果记录，不是公司、客户或真人行为数据。`subject`仅为合成行标识，未声明随机分配；`completed`与`retained`具有不同含义和数值。C复用该表，不假称新收集时间序列。

仅向自愿参与者分发本地试用包。不要将私人研究数据库、微博数据、论文、密钥、隐藏评测材料或本地原始会话加入包中。
