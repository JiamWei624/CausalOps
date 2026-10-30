# 系统架构与方法边界

## 两种不同的分析合同

因果/效应任务：`GeneralDesign → CausalSpec → identification → estimator registry → ResultBundle → research SQLite / immutable evidence → report & bounded QA`。

独立探索任务：`ExplorationDesign → explicit numeric/category/group/date roles → descriptive/correlation/OLS → versioned exploration_runs → chart/report`。不创建假处理变量，不要求因果审批，不把描述统计均值包装为处理效应。

## 本版新增

- AIPW使用DoubleMLIRM的ATE得分，固定分层交叉拟合划分，0.01/0.99倾向得分截断；与样本外结果回归及倾向得分一起复算AIPW公式。仅独立实体一行；无未测混杂与共同支撑仍须研究依据。
- 描述统计按有限值计算均值/样本标准差/分位数；缺失和无穷值分别计数，IQR只标记。分类分母为全表，尾部类别计数不丢弃，缺失单独表示。
- Pearson/Spearman按变量对完整有限值计算，记录成对N，常量或不足样本返回未计算。探索阶段不自动输出大量P值进行筛选。
- OLS支持HC3、实体聚类和HAC。HC3要求声明行独立；聚类至少20组；HAC要求唯一可排序时间及明确滞后。缺失排除须显式同意，共线不满秩阻断。
- 配置和运行不可变关联，加载校验JSON哈希、研究/版本、保存配置与上传指纹。页面选择同名记录显示短ID，避免序列化时切错研究。

## 已验证与未验证

上游代码下载为只读参考；没有执行下载库的setup脚本。工作台实际调用已安装官方库。方法数值用公开数据与独立统计实现比较，AIPW用已知生成机制合成数据检验；这些不是自动发现因果的总体准确率。

参见method-extension-plan.json区分已实现、仅参考、待接入。IV、RDD等在补齐识别合同、估计器、诊断、独立参考和反例之前不开放按钮。RAG/MCP/A2A不是本版已实现功能。

## 发布

公开源码不含原始数据、私有数据路径、论文、用户ID、API密钥、虚拟环境、下载的上游源码压缩包或研究数据库。安装依赖清单和CI配置已准备；GitHub远程尚未建立，CI尚未在GitHub运行。用户注册账号后再指定仓库名称/可见性与提交身份。
