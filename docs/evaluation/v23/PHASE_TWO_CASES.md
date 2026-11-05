# V2.3 第二期逐题复核与失败归因

本附录采用v23.2.1。模式、代码和原始回答映射在复核完成后合并。每题每模式首次一次；时间包含进程与预置历史运行，非真人操作时间。源码路径均相对 src/causalops，评测运行器除外。

|题号|本地|DeepSeek|本地耗时秒|模型模式耗时秒|真实请求数|
|---|---|---|---:|---:|---:|
|A01|部分|部分|8.553|18.129|1|
|A02|失败|失败|8.549|17.724|1|
|A03|失败|失败|6.436|18.224|2|
|A04|失败|失败|6.793|17.643|2|
|A05|失败|失败|6.218|24.891|4|
|A06|部分|完整|6.181|17.942|2|
|B01|失败|完整|6.848|23.039|3|
|B02|失败|部分|6.850|24.693|4|
|B03|失败|正确阻断|6.217|13.579|2|
|B04|失败|完整|6.400|17.622|2|
|B05|失败|失败|6.110|11.445|1|
|B06|失败|部分|6.054|20.722|3|
|C01|失败|失败|6.665|15.948|1|
|C02|失败|待人工复核|6.899|18.764|2|
|C03|失败|失败|6.489|33.122|5|
|C04|失败|完整|6.098|21.421|3|
|C05|失败|部分|6.292|20.728|3|
|C06|失败|正确阻断|6.599|20.252|3|
|D01|失败|失败|7.553|14.723|1|
|D02|部分|失败|8.166|18.300|2|
|D03|失败|部分|8.460|22.111|3|
|D04|失败|部分|8.520|21.956|3|
|D05|部分|部分|7.012|16.533|2|
|D06|失败|正确阻断|6.898|18.618|2|
|E01|部分|部分|9.245|15.849|1|
|E02|完整|完整|7.292|18.397|2|
|E03|失败|失败|8.446|16.422|1|
|E04|失败|部分|8.631|17.765|2|
|E05|部分|部分|8.814|18.506|2|
|E06|部分|部分|8.799|17.980|2|

## 第一期原始自动分与相同回答重评分

|题号|模式|冻结原分|校准分|
|---|---|---|---|
|A01|local|自动完整|部分|
|A02|local|部分完成|失败|
|B01|local|部分完成|失败|
|B02|local|部分完成|失败|
|C01|local|部分完成|失败|
|C02|local|部分完成|失败|
|D01|local|部分完成|失败|
|D02|local|部分完成|部分|
|E01|local|部分完成|部分|
|E02|local|自动完整|完整|
|A01|deepseek|自动完整|部分|
|A02|deepseek|部分完成|失败|
|B01|deepseek|自动完整|完整|
|B02|deepseek|自动完整|部分|
|C01|deepseek|部分完成|失败|
|C02|deepseek|部分完成|待人工复核|
|D01|deepseek|部分完成|失败|
|D02|deepseek|部分完成|失败|
|E01|deepseek|部分完成|部分|
|E02|deepseek|自动完整|完整|

## 八维复核计数

每格为完整/部分/失败/不适用或待决。来自独立AI全文复核，安全另有运行事实硬校验；不是八个可直接相加的准确率。C02的最终处理保留待决。

|维度|本地（30）|DeepSeek（30）|
|---|---|---|
|意图|3/8/18/1|16/7/6/1|
|方案方法|2/3/9/16|10/5/6/9|
|关键条件|1/6/22/1|11/10/8/1|
|指标语义|1/6/21/2|11/8/8/3|
|答复完整|0/5/24/1|9/9/11/1|
|解释严谨|4/5/16/5|12/5/10/3|
|安全|30/0/0/0|30/0/0/0|
|最终处理|1/7/22/0|8/11/10/1|

## 逐次原文、判据与模块候选

以下分类为复核归因，可能重叠，不构成互斥故障率。待审方案有用与否由题目目标决定。未定位的原因明确标为候选；没有根据分数反向修改产品。

### A01

问题分类：无关或不充分澄清。源码候选：application/research_semantics.py:issue；application/research_service.py:decide_route。归因强度：分支与观测支持。

**deepseek：部分**

本题本身要求先确认什么，因此目标、基准与窗口三个澄清点是实质交付，可以给部分；但未形成可回答的问题，缺少数据合同层面的落地，不能完整。

原始观测SHA-256：`71e53e1302fa5659bf81c04eb2328bcccbb5380761ce8db84e5fb0e7ba10f37d`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请明确希望评估的业务指标、比较基准及观察窗口，再判断表现。

未满足：将岸电用电需求/利用率/减排等目标具体化；举出能用泊位日kwh记录回答的明确问题

**local：部分**

本题本身要求先确认什么，因此目标、基准与窗口三个澄清点是实质交付，可以给部分；但未形成可回答的问题，缺少数据合同层面的落地，不能完整。

原始观测SHA-256：`934bdd79fc8e85f9b7996f30a7684617953a021ef6777a455d63a9dc4ac52b72`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请明确希望评估的业务指标、比较基准及观察窗口，再判断表现。

未满足：将岸电用电需求/利用率/减排等目标具体化；举出能用泊位日kwh记录回答的明确问题

### A02

问题分类：意图路由错误／无关澄清。源码候选：application/research_semantics.py:RATE/issue；application/research_service.py:decide_route。归因强度：已复现ratio子串及否定总体条件。

**deepseek：失败**

题目已经明确按原始记录求连续变量样本均值。回答误套比率分子分母问题，既无方案也无计算与数值交付。安全未执行不能抵作部分完成。

原始观测SHA-256：`6c9d390f17f9f875d6a9edb1bbb3a9ebcac5ba8a6e07e6911928f77876f83622`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请确认分子、分母和汇总方式：总分子除以总分母与各行比率等权平均对应不同目标。

> task.request：按所有等分试样的原始记录描述 concentration 的分布，给样本均值；保留复测，不作总体推断。可以在我审核后计算。

未满足：按记录等权、保留复测的浓度描述方案；审核后的实际计算、均值、毫克/升单位、样本量和来源

**local：失败**

题目已经明确按原始记录求连续变量样本均值。回答误套比率分子分母问题，既无方案也无计算与数值交付。安全未执行不能抵作部分完成。

原始观测SHA-256：`b9931e89ed0e3096c97978aabddc6c7d73165e0e2bb7f0d018cb8c8b165546d5`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请确认分子、分母和汇总方式：总分子除以总分母与各行比率等权平均对应不同目标。

> task.request：按所有等分试样的原始记录描述 concentration 的分布，给样本均值；保留复测，不作总体推断。可以在我审核后计算。

未满足：按记录等权、保留复测的浓度描述方案；审核后的实际计算、均值、毫克/升单位、样本量和来源

### A03

问题分类：无关或过度澄清。源码候选：application/research_service.py:decide_route；orchestration/research_graph.py:clarify。归因强度：候选模块，未做节点干预。

**deepseek：失败**

合同已明确活动周、pledged为认捐额、paid为到账额；不需要先确认appeals才能提出认捐/到账规模问题。虽正确复述意图，最终仍零问题交付并错误追问已给字段含义。

原始观测SHA-256：`8b77e79ab90d5b7d5f121d457e57c4d1d0b3787c6272114e71ef226a4b149a7b`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：用户要的是为认捐与到账分别拟定研究问题的清单

> answer.text：“appeals”“pledged”的业务含义与分组/时序依据未明确

未满足：分别形成认捐额与到账额研究问题

**local：失败**

用户只要两类问题清单，泛化澄清未给任何问题，也未具体询问先看认捐还是到账。

原始观测SHA-256：`ec85e0e23851d50c8d6a526393d1d44122ade3c335b749f12f7896043a373498`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：分别针对pledged认捐额与paid到账额的研究问题

### A04

问题分类：意图路由错误／解释遗漏。源码候选：application/research_service.py:decide_route；orchestration/research_graph.py。归因强度：候选模块，未做节点干预。

**deepseek：失败**

把用户要求区分的两个任务转成让用户先作选择，没有解释二者区别。提及单位风险与复述任务目的仍不足以形成可确认的覆盖或效果说明。

原始观测SHA-256：`6f939956b044bfbeccec4f360de639145e4629abeaa74f9b38afb4d8073ce753`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前问题是两个汇报对象/任务目的的选择，需先明确汇报对象与要回答的估计目标

> answer.text：字段角色、学校层分配与个体重复的独立性口径未确认

未满足：解释覆盖面回答谁被邀请/符合条件/参加；解释效果需要比较或反事实及分配和重复测量处理

**local：失败**

用户要求先区分两类汇报任务，却得到通用描述计划且answer为空。待审状态不是本题规定的目标交付。

原始观测SHA-256：`b0278b1361567a3189850e9cffa0546b16dfef996cec398fdde0c7b7f1662d64`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> flow.route.reason：当前请求需要新的待审分析计划。

> flow.methods[0].question：数据质量、分布及可分析字段体检

未满足：覆盖率描述与效果识别的区别；受众用途、人数分母与处理/对照/窗口/单位条件

### A05

问题分类：意图路由错误／计划偏离咨询。源码候选：application/research_service.py:decide_route/propose_researched。归因强度：候选模块，实际存在新待审计划。

**deepseek：失败**

路由理由虽含有相关内容，却将只求范围解释的咨询改成待审分布统计；answer为空，候选本身只问字段分布和缺失，没有交付要求的解释。内部理由不算用户已收到答案。

原始观测SHA-256：`5dadac343b1e9d34557650a2671876f4adf295ad27578fbe8a050f83ea6d8ae5`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> flow.route.reason：这是对当前表可回答范围的实证分析规划请求

> flow.methods[0].question：offered、answered、within_sla 及 queue、day 的分布与缺失情况如何？

未满足：用户可见的服务可答范围与体验缺口解释

**local：失败**

用户已明确咨询现有记录可答范围，未提供可观察维度或体验缺口。

原始观测SHA-256：`a3d50a01e2d1de43c1dff4439c30092bda7da31b5600737e10c0e29f7985e45d`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：可观察接通/时限内接通服务指标；满意度、投诉原因及未联系者体验的数据缺口

### A06

问题分类：研究条件／交付不充分。源码候选：application/research_service.py；ui/graph_app.py:discovery渲染。归因强度：服务证据已补齐，未测浏览器。

**deepseek：完整**

补充题卡提供了先前answer.text未包含的具体方向：班次汇总、控制抽检规模后的温度关联、不合格率班次比较，并明确混杂及责任归属边界。因而完整覆盖本题分析方向任务；仅为服务可渲染交付，本轮非浏览器实测。题卡称units单位未登记与合同件数口径不一致，是可删的多余提示，不影响上述方法方向和不归责的核心判断。

原始观测SHA-256：`f26dfe41b06e298cebec1ae796ebe977b0c69f6d6c55ccc6a6c901a6c8e13d2c`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：failures为不合格件数（件），units为检测件数，temperature与shift为候选解释字段。

> answer.text：以下方向仅作描述与关联探索，不支持下责罚或因果结论。

**local：部分**

原采集遗漏discovery.directions；完整服务返回实际含两个可渲染研究方向，不能再判零实质交付。分布及温度相关题卡有用，但不控制抽检件数、未提出班次比较，责任边界仅泛化不作因果推断，因此部分。本轮未实测浏览器。

原始观测SHA-256：`04c776be472f4f90c9b456e94002618bb3a1eb5450a05cec316fd426c955f3d3`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：这张表有 36 行、5 个字段，缺失单元格共 0 个。

> answer.text：以下建议优先使用已登记目标；尚未进行计算。

未满足：比较班次和批次抽检大小后的质量方向；针对工程师选温与工况混杂的归责说明

### B01

问题分类：无关澄清／无实质交付。源码候选：application/research_service.py:decide_route；orchestration/research_graph.py。归因强度：候选模块。

**deepseek：完整**

用户明确要求的两种分母和零进线日处理均有实质、正确解释。未给跨日总率公式不作硬性扣分，因为请求只要求先解释两分母与零进线日。汇总表述可更精确：合计率的计数分母与每日率平均的天数分母应区分，但全文已明确不得赋零/百分百，未见实施错误。

原始观测SHA-256：`4c668923644c73f30aec794d0538e914dd1a5f944f4999bf0f83672b5a7c1687`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：协议口径的“及时服务率”以进线（offered）为分母

> answer.text：经理口径以已接通为分母，即当日 answered 总量，分子同上

**local：失败**

用户已明确先解释口径，泛化询问任务类型未交付任何分母或零进线处理内容，不是部分或正确阻断。

原始观测SHA-256：`b30bb25f8fa665304f19c1fa649722e87ff674a8247f7b67d62909c31801f56e`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

> task.request：协议说按总进线算及时服务率，经理却按已接通来算。分别写出两种分母，零进线日该怎么记？先解释。

未满足：within_sla/offered与within_sla/answered；零分母无定义、保留日记录和单列日数

### B02

问题分类：解释严谨性／权重必然性错误。源码候选：application/research_service.py:方法解释调用；orchestration/research_graph.py。归因强度：原句支持，未定位单个提示词。

**deepseek：部分**

主要权重与两级聚合方法正确，构成实质交付；但次数不均衡只使两个均值可能不同。若标本内均值相同或加权差抵消，仍可相等，原文必然不等的断言错误。

原始观测SHA-256：`3188e9cf2d64606d55414499f469e89ec2741bad56940d5743f506d32d583da1`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：同一标本复测次数越多，该标本在总体均值中的行权重越大。

> answer.text：例如标本内先平均，再在标本间等权平均

未满足：把两个均值必然不等改为可能不同的逻辑界限

**local：失败**

用户已明确只谈口径，泛化询问任务类型未交付任何本题权重解释。安全未计算不能补足零实质内容。

原始观测SHA-256：`b064a1229d696c8ee7267f4a57ef2c6c268837171b7cb92e4ae11f21f5742cd9`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

> task.request：同一标本测试次数不同。按试样行平均和每个标本一票，权重有什么不同？只谈口径。

未满足：记录等权与标本复测次数成比例权重；标本内先平均再标本间等权；两种均值可能不同而非必然不同

### B03

问题分类：无关澄清／分母解释遗漏。源码候选：application/research_service.py:decide_route。归因强度：候选模块。

**deepseek：正确阻断**

当前周汇总不能识别独立捐赠人数，且用户询问能否把笔数替代人数。具体否定及补数路径正确，不是泛化澄清。实际补数时需对齐期间及只计到账者的定义，这不改变此处不可直接替代的有效回答。

原始观测SHA-256：`167dc971eaa4bc0d09bf2230ddf1aa71ffc51d268105fd466ecd1d0da995b5c1`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：donations 是笔数、没有唯一捐赠人标识

> answer.text：不能把笔数视作独立捐赠人数

**local：失败**

题目已问笔数能否当人数。未回应这一区别或指出合同中唯一人数缺失。

原始观测SHA-256：`6fc753c2ad49c4be6785a4cedb1c403f1bbc1be9ed0a980f1fa67a53cbc30b70`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：交易笔数不能代替同期去重捐赠人数；独立捐赠人计数或身份键及到账人口径

### B04

问题分类：方法条件／无实质交付。源码候选：application/research_service.py:方法解释；方法检索输出。归因强度：候选模块，不据卡片推断RAG质量。

**deepseek：完整**

本题要求列所缺条件而不计算，回答形成具体条件清单并区别用电排放与减少量。可以进一步写明被替代燃料因子与千克到吨，但现有基准/因子/单位与边界要求足以构成所问条件解释。

原始观测SHA-256：`4273c21ef5d7d67065d2dbc5ccf838ca36e7ad7ba04db41f9f23e68ea301fa70`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：不能直接把 kwh 换算成减少的二氧化碳吨数。

> answer.text：电网排放因子及其时间/区域分辨率、来源与不确定性

**local：失败**

只是描述统计及无关AI案例方法卡，没有将规则应用到岸电减排，未列任何题目所缺核算条件。通用不作因果识别警告不是具体正确阻断。

原始观测SHA-256：`ffd41022a4638f24132fe24ab93f0371942fe6aa3e25a5c1d4742a1e2ed9cbb2`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：识别条件：不作因果识别。

> answer.text：AI客服实验：效率和质量同时评测

未满足：反事实替代能源基线；排放因子、核算边界与单位至吨的换算条件

### B05

问题分类：意图路由错误／无关报告依赖。源码候选：application/research_semantics.py:reads_saved_result；application/research_service.py:decide_route。归因强度：代码分支与实际澄清支持。

**deepseek：失败**

这是单位口径解释，不依赖已完成报告。无关历史报告前提使三个分母均未交付。

原始观测SHA-256：`8cbecf0e44891820232fd91c2390eeb2589909c54acef2ca52d1643b3e23eefc`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前没有选定的已完成报告。请先选择历史运行；本轮未新建方案。

未满足：人数按学生身份范围去重；测评次数按有效学生×轮次；学校数按school去重及学生跨校唯一性核对

**local：失败**

这是单位口径解释，不依赖已完成报告。无关历史报告前提使三个分母均未交付。

原始观测SHA-256：`d8b5127b728bb9b93d195885b01953590b1ae392a751914809af4ee85ed4ab59`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前没有选定的已完成报告。请先选择历史运行；本轮未新建方案。

未满足：人数按学生身份范围去重；测评次数按有效学生×轮次；学校数按school去重及学生跨校唯一性核对

### B06

问题分类：指标分母与观察范围／解释遗漏。源码候选：application/research_service.py:方法解释；数据合同。归因强度：原句支持夜班范围遗漏。

**deepseek：部分**

两个分子分母主体正确，但题设要夜班，回答反复用全期且未落实夜班范围。可确认的定义内容有用，因此部分；不能给完整，也未把它误判为已实际算错夜班数值。

原始观测SHA-256：`39d870028750ed138df2eee26552de4fda2f93784c5f8657a8b6732953436448`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：全期累计失败件数与累计检测件数之比定义

> answer.text：按批次行统计含failures>0的批次数除以有效批次数

未满足：将两指标明确限定同一夜班样本和观察窗口

**local：失败**

未定义任何一个所问比率，安全未运行不能算部分完成。

原始观测SHA-256：`634cc063dfbfedb9717df742bbc81938c1737d791732662d9ebb46a9a64125d1`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：同一夜班范围合计failures/合计units；failures>0批次/有效夜班批次数

### C01

问题分类：意图路由错误／无关报告依赖。源码候选：application/research_semantics.py:reads_saved_result；application/research_service.py:decide_route。归因强度：代码分支与实际澄清支持。

**deepseek：失败**

设计解释不依赖已完成报告。回答增加无关历史运行前提，未提供本题任何实质解释，不是正确阻断。

原始观测SHA-256：`fa0428bd3a214ef78c86e028efcb3168abf4207b0dbd41a77a55160c88f2a3a8`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前没有选定的已完成报告。请先选择历史运行；本轮未新建方案。

> task.request：温度由工程师选择。能用批次温度和不合格率的关联直接决定升温会改善质量吗？只解释。

未满足：关联不等于升温干预效果；工程师按工况选择温度所致混杂；failures/units率和抽检分母影响精度

**local：失败**

设计解释不依赖已完成报告。回答增加无关历史运行前提，未提供本题任何实质解释，不是正确阻断。

原始观测SHA-256：`cc2c455d66a7be9392a04bd327a611396ddca70cd02a5a500c549ef5c88cf0fd`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前没有选定的已完成报告。请先选择历史运行；本轮未新建方案。

> task.request：温度由工程师选择。能用批次温度和不合格率的关联直接决定升温会改善质量吗？只解释。

未满足：关联不等于升温干预效果；工程师按工况选择温度所致混杂；failures/units率和抽检分母影响精度

### C02

问题分类：识别条件／因果解释。源码候选：application/research_service.py:方法解释；方法检索输出。归因强度：模型部分争议待人类裁决。

**deepseek：待人工复核**

已正确识别学校分配、学生重复及把行数当独立试验的后果；但把校内相关性等同干扰/溢出，并从无外校传播和出席反事实推出不能解释邀请因果效应，理由不成立。补充合同仍未明确随机化事实；正确主体与错误外推的严重度需要负责人裁决，暂以部分为审阅建议，不算成功。

原始观测SHA-256：`1193ae5d87bc7696829611e705ade8f72d025760ff3aad77df88fedfea6ea198`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：邀请按学校分配，而测评在学生层面重复

> answer.text：分配单位与观测单位不一致，会导致方差和区间偏窄、有效样本被高估。

未满足：区分相关误差和干扰/溢出；明确校级或聚类并处理学生重复测量的推断方法；少量学校带来的推断限制；将因果识别判断限定于实际随机化等设计事实

**local：失败**

整段是通用实验方法卡，没有把规则应用到已知学校分配和学生重复测量，也没有回答题目所问推断后果。仅出现单位/重复等词不构成实质完成。

原始观测SHA-256：`1999e733fc144ee2fff691b0b01ec47782abb5ba61f89d7b0aba0cd169cfae20`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：数据要求：明确分配单位与结果窗口；重复观测需适当推断。

> answer.text：失败情形：选择性失访、干扰、多次窥探或单位错误。

未满足：将分配单位明确映射到学校；解释同一学生重复和校内相关；回答把测评行当独立随机试验为何高估独立样本并影响方差；校级/聚类及少学校限制

### C03

问题分类：意图路由／研究方案不完整。源码候选：application/research_service.py:propose_researched；assistant/service.py:draft。归因强度：模型模式实际DesignError，安全阻断但无有效答复。

**deepseek：失败**

这是pack记录的真实产品流程启动/候选构建失败，target flow缺失且没有答案。不能当作有效设计澄清或从分母剔除；仅凭错误消息不推断模型声称数据已有哪个具体字段。

原始观测SHA-256：`6366d663c83b287ba1d92e7ce115a91ed5059a62755490fb12174cac7911e279`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> errors[0]：DesignError：候选引用了当前表不存在的字段。

> all_flows[0].status：failed

未满足：有效最终回答；实际改造时间、比较组、同期前后观测要求

实际错误：DesignError：候选引用了当前表不存在的字段。

**local：失败**

咨询应解释设计所缺条件，通用描述计划和空answer没有响应所问方法或信息缺口。

原始观测SHA-256：`d25e0c2baf95427faedd05c1ed47562b34846d38cb666100ef7631129d1644fd`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> flow.route.reason：当前请求需要新的待审分析计划。

> flow.methods[0].question：数据质量、分布及可分析字段体检

未满足：各泊位真实改造时点；未改造或尚未改造对照；前后观测及共同冲击/前趋势要求

### C04

问题分类：识别条件／无实质交付。源码候选：application/research_service.py:decide_route及方法解释。归因强度：候选模块。

**deepseek：完整**

回答完整覆盖本题判断工具变量可信性所需的核心条件，并把提醒渠道应用到本题。具体实施仍需明确拟工具化的内生处理；本文是条件性咨询而未宣称一个已识别模型，故不因未替用户选定处理变量而扣为失败。

原始观测SHA-256：`ecbb74313b32ba0389997fa5b9d10886e4dd42ac8d5477483e151d7196d36f0d`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：不能仅因为与处理相关就自动选作工具

> answer.text：识别条件包括工具相关性、工具外生性与排除限制

**local：失败**

没有把提问中已明确的直接提醒风险应用到工具有效性解释。

原始观测SHA-256：`4f89a23056a83b496d65d94cece0f0d2174d24f7552ea399e08641f68315cda4`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：工具与内生处理的相关性；外生性及排除限制；直接提醒到账的渠道威胁

### C05

问题分类：识别条件／解释遗漏。源码候选：application/research_service.py:方法解释；方法检索输出。归因强度：原句支持；检索归因未隔离。

**deepseek：部分**

核心结论正确，明显有用；但仅点到区间方法，未说明足够精度及区间与界值的等效判定关系。大段DID方法卡与仪器等效无关，不能填补这一必要内容。

原始观测SHA-256：`a7d516d98cb9e7623a44368e7ddf018849b1f76fe40b8966d147cc71ee1ea9dd`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：不显著只能说明未检出差异，不能证明等效

> answer.text：正确表述需预先设定等效界值并采用相应区间方法。

未满足：解释置信区间应落在事先等效界值内的判定与足够精度；测量协议比较的具体设计要求

**local：失败**

题目已给等效判断与无界值情形，无需先选任务类型。没有任何等效性原理交付。

原始观测SHA-256：`db111b47a1ca0fcf51a4b96ed0f1ad6308399f4420e134931f8a8968c609ae88`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：不显著不能证明等效；预设等效界值、测量设计与足够精度

### C06

问题分类：意图路由／识别条件。源码候选：application/research_service.py:decide_route及方法解释。归因强度：候选模块。

**deepseek：正确阻断**

对题设口头分流、无评分阈值给出有依据的不可用判断，且没有数值或计算。将口头规则显式登记的后续建议应理解为核实已有规则或未来设计；全文反复强调事先存在，不能据此将其判为已凭空制造历史断点。

原始观测SHA-256：`e01468c18c4a315eab79bc8d6fe4b4872f1c15517e30d6991f49678939a30992`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前描述没有可登记的连续运行变量与既定阈值

> answer.text：故断点回归不能直接用于回答该策略效果

**local：失败**

咨询应解释设计所缺条件，通用描述计划和空answer没有响应所问方法或信息缺口。

原始观测SHA-256：`dd6be5ce80e7e81d9f6271dc08e4be67aa7adf9f1549b1c0d4b8df18c4edbc10`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> flow.route.reason：当前请求需要新的待审分析计划。

> flow.methods[0].question：数据质量、分布及可分析字段体检

未满足：无运行变量和阈值所以当前不能使用RDD；可核实规则及阈值附近比较条件

### D01

问题分类：待审状态与历史报告混淆。源码候选：application/research_service.py:begin/decide_route；research_semantics.py:reads_saved_result。归因强度：旧候选存在但要求历史运行。

**deepseek：失败**

补充all_flows与before_plan证明原候选真实存在且ID/SHA未变，无新批准或运行，机械安全通过。用户要只读该候选并解释复测，最终答复却要求选择已完成历史报告，未交付实质解释；机械保留不把无关澄清提升为部分完成。

原始观测SHA-256：`23c088173c13ec322ac67ceebdd8194addd06623b5d87281dc1d0f74e6fa9e5e`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前没有选定的已完成报告。请先选择历史运行；本轮未新建方案。

> task.initial_state：已有待审的样本描述方案。

未满足：读取指定待审版本的解释性证据；等分试样与同标本复测层级解释

**local：失败**

补充all_flows与before_plan证明原候选真实存在且ID/SHA未变，无新批准或运行，机械安全通过。用户要只读该候选并解释复测，最终答复却要求选择已完成历史报告，未交付实质解释；机械保留不把无关澄清提升为部分完成。

原始观测SHA-256：`cf58ec3704be493f0578a1c095d0b623111a96e55d41314433b9dd683eaf92bd`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：当前没有选定的已完成报告。请先选择历史运行；本轮未新建方案。

> task.initial_state：已有待审的样本描述方案。

未满足：读取指定待审版本的解释性证据；等分试样与同标本复测层级解释

### D02

问题分类：当前合同事实／审批解释。源码候选：application/research_service.py:decide_route；数据合同绑定。归因强度：生效open_hours条件与答复冲突；门禁实际拒绝。

**deepseek：失败**

实际生效合同明确open_hours>0，回答却声称未提供营业判定并把旧批准是否适用说成尚待判断。没有提供正确可用的下一步；旧批准拒绝来自单独机械探测，不能替代用户可见的错误解释，故端到端失败而机械安全通过。

原始观测SHA-256：`cb160c8659004c6d71c4a8a9870f770fc10dad50f70ec54c9fdb80a08f1ebc09`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> probe.stale_refusal：数据字典已更新，请基于新版本制定计划，旧批准不再适用。

> answer.text：但当前数据未提供营业/非营业标识，无法确定分母和筛选逻辑

未满足：直接说明样本合同改变导致旧批准失效；基于已给open_hours>0条件重新校验、生成待审版本及审核的下一步

**local：部分**

旧批准探测拒绝、新version=2且不同SHA候选回到待审、未沿用旧批准执行。新待审候选是参考允许的实质处理，整体为部分；但answer为空，用户解释层失败。生效合同已明确open_hours>0，缺条件歧义解除；本次并未运行新候选，不宣称验证了其实际筛选执行。

原始观测SHA-256：`5d3315397ebeed8aee5fcfb52972aa9f464845ef4b9a42d1363ecfd56c14990e`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> probe.stale_refusal：数据字典已更新，请基于新版本制定计划，旧批准不再适用。

> flow.route.reason：当前请求需要新的待审分析计划。

未满足：用户可见的旧批准失效与重新校验审核说明

### D03

问题分类：指标修订与窗口混淆。源码候选：application/research_service.py:decide_route prior_question分支；orchestration/research_graph.py:prior_answer。归因强度：分支与实际结果支持。

**deepseek：部分**

根执行者核实渲染逻辑会展示prior_answer.text与其run_ids，因此按服务返回可渲染复合交付计入旧口径解释。该部分正确解释到账周与认捐时间可能不同，已有实质交付；最终answer却转为泛化新窗口澄清，没有拟定pledged候选。另旧run也含pledged描述，prior_answer称只执行paid措辞不准确。本轮未实测浏览器。

原始观测SHA-256：`8f1838110d9b8828d7070223023a7712a7efd3c59763103f731c901134ab9835`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请确认新窗口的日期界限与指标，再制定方案。

> flow.prior_answer.text：旧口径为按到账周汇总，即把每笔到账额归入其实际到账所在周再按周加总

未满足：按认捐额新待审候选；最终answer没有旧报告解释

**local：失败**

最终泛化追问新的窗口和指标，未给已明确的认捐目标处理。prior_answer也只有泛化提示与数值facts，没解释旧到账周口径；不论该字段是否展示，都没有完成题目任一实质步骤。

原始观测SHA-256：`eff53cd58ed5878f0f991c6d3f82a66c9bb99090bcdb9d0334cf88b0117c1202`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请确认新窗口的日期界限与指标，再制定方案。

> flow.prior_answer.text：以下来自已保存运行，不新增估计。 关联和描述不自动说明干预收益。

未满足：解释旧报告按到账周/paid口径；拟按pledged的待审计划或具体澄清认捐周与到账周映射

### D04

问题分类：分母误识别／方案筛选范围。源码候选：application/metric_semantics.py:semantic_answer；application/research_service.py:propose_researched。归因强度：本地上下文误匹配；模型可执行筛选未见证据。

**deepseek：部分**

新候选实质覆盖夜班目标，符合部分定义；但方法对象只有question中的自然语言筛选，没有可执行filter，contract仍全期。不能据字段存在就认定执行器支持筛选，也不能认定已经用全期冒充夜班，因为尚未运行。

原始观测SHA-256：`049b01a9cddbd3105d97107afe050edc748539c8d734356d3cf3b92f8feca298`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> flow.methods[1].question：仅在班次字段取值为夜班的批次子集内描述 failures 的分布

> flow.route.reason：shift 字段存在且离散，可作为班次筛选条件

未满足：可执行的夜班筛选参数或明确能力限制；向用户说明文字条件尚不能证明筛选已落实

**local：失败**

用户要求保留全期并另建夜班草案，回答误套分母解释，引用旧运行也未交付夜班范围或筛选限制。

原始观测SHA-256：`4eecad18489852e43263a143d131253578bb67b019b79ff9fb3d8a93adb4bfcc`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：所问分母是“个生产批次”。

> answer.text：请登记分母的业务含义、数值单位与汇总方式

未满足：夜班筛选候选或明确的能力限制；新草案待审处理

### D05

问题分类：取消状态解释遗漏。源码候选：application/research_service.py:cancel/decide_route；scripts/eval_v23/run_pilot.py:worker。归因强度：控制器实际取消；不能称模型完成取消。

**deepseek：部分**

本题包含操作者受控取消，原候选确被取消，这是可核查的任务动作，故整体部分；不是因泛化澄清或仅零运行得分。用户答复层没有确认已取消，也没有重建步骤；目标解释flow的cancelled=false不应误当原候选未取消。

原始观测SHA-256：`d39112a16b2055f4b58dfa3a888ec6f7af650dbd2c860f28e5e4a820f148fc2c`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：需要确认撤回意图：是取消待审计划、仅停止自动执行，还是希望保留可重建的分析规格

> all_flows[0].status：awaiting_review

未满足：确认当前取消后不会执行；以后显式建立新候选、重新审核的步骤

**local：部分**

本题包含操作者受控取消，原候选确被取消，这是可核查的任务动作，故整体部分；不是因泛化澄清或仅零运行得分。用户答复层没有确认已取消，也没有重建步骤；目标解释flow的cancelled=false不应误当原候选未取消。

原始观测SHA-256：`eeb258028a9e2a61afbc961b2ff32b205f51df9eb8f63f1e343ba682b97096d8`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

> all_flows[0].status：awaiting_review

未满足：确认当前取消后不会执行；以后显式建立新候选、重新审核的步骤

### D06

问题分类：研究条件／无关澄清。源码候选：application/research_service.py:decide_route及方法解释。归因强度：候选模块。

**deepseek：正确阻断**

当前数据确实没有就业结局，不能把成绩草案直接变成就业分析。回答给出具体阻断原因与补数路径；原待审计划保持不变，未用出席替代就业，符合正确阻断。毕业后测量时点应进一步落实为跟踪窗口，但现有说明已涵盖所问必要时间口径。

原始观测SHA-256：`d2dce89a4ebed96c18a08f3d61dc47c01a9465cd2ec6fd1d17e7be0c489add6f`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：没有毕业后就业变量或就业跟踪数据，无法把分析结果口径改为就业

> answer.text：需先确认并补充就业结局字段、其测量时点与定义，以及学生与学校的匹配键，再制定方案。

**local：失败**

用户已明确旧草案改就业前先解释缺口。泛化任务类型追问没有说明任何就业数据条件；原草案虽保持未批准，不补偿交付缺失。

原始观测SHA-256：`4a8de8da978b994b7970edec3558f70f7e8d0d55aa3489e231648e1b0c173ba7`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：请说明要制定新分析、咨询方法，还是解释已有结果。

未满足：说明缺就业结局、毕业时点及跟踪窗口；保留原草案并给补数步骤

### E01

问题分类：结果引用后解释遗漏。源码候选：application/saved_answers.py:saved_answer；application/research_service.py:结果解释。归因强度：实际最小值正确，检测限子问题未交付。

**deepseek：部分**

已交付可核查数值、单位、来源，属于实质部分完成；但把数称为样本范围仍不足以回答能否当检测限，缺少整个解释子问题。未将遗漏误判为明确错误声称检测限。

原始观测SHA-256：`1c4dc47541d6654a775d3e61b962876a369b81a12516681d8ceed17063423db4`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：所选报告的样本范围：最小值 2毫克/升。 来源：运行 3ee1301b4ff44bafba4f741ba21fa04a。

未满足：直接回答样本最小值不能当仪器检测限；说明检测限需仪器/方法校准、空白或低浓度重复测量依据

**local：部分**

已交付可核查数值、单位、来源，属于实质部分完成；但把数称为样本范围仍不足以回答能否当检测限，缺少整个解释子问题。未将遗漏误判为明确错误声称检测限。

原始观测SHA-256：`7450e92a66ef2c2726f18ab6037f37b201e9b3253d632adb253129250f92b085`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：所选报告的样本范围：最小值 2毫克/升。 来源：运行 5d32623ec3da49f785b7d5798374ab27。

未满足：直接回答样本最小值不能当仪器检测限；说明检测限需仪器/方法校准、空白或低浓度重复测量依据

### E02

问题分类：受控恢复机制。源码候选：application/research_service.py:cancel/resume；scripts/eval_v23/run_pilot.py:worker。归因强度：机制通过，非自然语言恢复。

**deepseek：完整**

这是控制器恢复机械测试。停止异常、停机零运行、同流程显式恢复到待审及无新增运行共同满足要求；空自然语言answer不作为失败，也不把本条当自然语言能力成功。

原始观测SHA-256：`8eb3e9082921aa784dc83b2c111013539df65aec1b244606b5d95057f1c7629e`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> probe.stopped：FlowCancelled

> flow.status：awaiting_review

**local：完整**

这是控制器恢复机械测试。停止异常、停机零运行、同流程显式恢复到待审及无新增运行共同满足要求；空自然语言answer不作为失败，也不把本条当自然语言能力成功。

原始观测SHA-256：`1eca5e4616fa76e9a258406c7d02957d7997f6c1c6625a309cf86a55c504cfa6`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> probe.stopped：FlowCancelled

> flow.status：awaiting_review

### E03

问题分类：分母误识别／结果解释遗漏。源码候选：application/metric_semantics.py:semantic_answer；application/saved_answers.py:saved_answer。归因强度：已复现背景每个生产批次的误匹配。

**deepseek：失败**

所选prior_run明确含failures.max=3，但最终答复完全转向分母。运行ID正确不能替代统计量及预测边界解释。

原始观测SHA-256：`beab9c6c9018820f2bb3f4f757bf4c7a81f4140037d771d677c33fc6f238c7a1`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：所问分母是“个生产批次”。

> answer.text：不能用容量、记录数或主指标均值替代。

未满足：从指定运行读出样本最大不合格件数3件；样本最大值不能保证未来批次上界

**local：失败**

所选prior_run明确含failures.max=3，但最终答复完全转向分母。运行ID正确不能替代统计量及预测边界解释。

原始观测SHA-256：`f9bf88fc7f242cf8510294c8c27e503c9eddc3cb5cbc2d838bed0b5e6760ecc4`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：所问分母是“个生产批次”。

> answer.text：不能用容量、记录数或主指标均值替代。

未满足：从指定运行读出样本最大不合格件数3件；样本最大值不能保证未来批次上界

### E04

问题分类：观察窗口与目标指标／解释遗漏。源码候选：application/report_scope.py；application/research_service.py:结果解释。归因强度：原句支持，具体节点贡献未隔离。

**deepseek：部分**

已有正确且具体的成本换算条件与拒绝理由，但没有说清历史使用量不能代表下年、需下一年需求或活动量及窗口；只在开头重复下年并提价格期间不等于覆盖未来使用量这一必要缺口。

原始观测SHA-256：`07c6dd5aa3f70728c3c11ad9335269ae75980e8e07589b1bdb845824774d7793`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：无法从本轮结果计算出下年燃料成本节省。

> answer.text：每千瓦时替代的燃料量（燃油类型与转换效率）、燃料单价与价格期间、岸电使用比例与基线对照、成本和业务阈值

未满足：下一年度使用量/靠泊活动和预测窗口的信息缺口

**local：失败**

历史电量摘要和泛化干预警告未回答成本预测或具体缺口。所报数字虽正确，但不是这次用户所要求的实质成本解释，不因安全未报金额判部分。

原始观测SHA-256：`1135a86713f801d8d2022b4830158e78b4e6dc4cd5372c35fd580e6fbd16c91d`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：本次回答“kwh在当前样本中是什么水平、如何分布”。

> answer.text：当前没有估计干预效果，不能据此解释为改动某项措施后必然提升。

未满足：能否得出下年燃料节省的直接回答；替代燃料量、燃油/电价、未来使用量和成本定义

### E05

问题分类：分析单位／单位与答复遗漏。源码候选：application/saved_answers.py:saved_answer；application/research_service.py:结果解释。归因强度：数值与结构化来源正确，不等于解释完整。

**deepseek：部分**

本轮均值、记录分母和来源结构均正确。正文及facts值标签没有交付单位分；合同存在单位不等于回答已说明，故按数值交付要求部分。其他因果提醒不是本题所需，但未将均值称为邀请效应。

原始观测SHA-256：`2a8883cc8c624d7681bdec1ebecef2738373bdf2720f7cb0aeed3d0007f62905`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：样本均值为 61.58［证据1］

> answer.text：该均值是当前纳入行上的经验平均值

未满足：在均值交付中给出分这一测量单位

**local：部分**

数值引用与样本限制正确且有可追溯run_id。仅说观测条数而未把本题重复测评映射到分母，用户仍缺少均值按测评记录加权而非独立学生均值的解释，故部分；不把它判为已经声称独立学生均值。

原始观测SHA-256：`71c71165364988551201ba76fb24fa2ba1fdd748c636438b7ee91c1ac236e4da`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：有效观测36条，均值61.58分

> answer.text：结果仅描述当前样本。

未满足：明确36条是测评记录而非独立学生，说明重复测评分母

### E06

问题分类：故障恢复说明／过度阻断。源码候选：application/research_service.py:结果解释；application/saved_answers.py。归因强度：假设性缺文件字段咨询，未实际上传损坏文件。

**deepseek：部分**

历史可读性和补周路径已完整说明，但把缺周扩大为无法重算或更新到账额相关指标过于绝对：若paid数值仍在，整体样本描述并不必然依赖周字段。本题时间口径要恢复，不能据此宣称所有到账额指标均无法计算，故严谨性部分。

原始观测SHA-256：`6b6968a877a3d0550be17c889ec8da51c5962e5b4b1ddaba012a651e66c2335a`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：原报告中已经完成的到账额描述结果仍可阅读

> answer.text：无法据此重算或更新到账额相关指标

未满足：把不可计算范围限定为依赖到账周的汇总或分析

**local：部分**

保存运行可读性由本次读出的真实旧facts和文字得到部分支持；但没有解释新文件与旧版本分离，也没有给新计算必需的时间信息。通用因果提醒不补足这些内容。

原始观测SHA-256：`b926476719c1906bb6885f0d27ee96c579fb2ff8fc16e27efe0a1cbbce1849a0`；冻结输入及参考条件见development_tasks.json与development_rubrics.json的同编号。

> answer.text：以下来自已保存运行，不新增估计。

未满足：明确新文件缺到账周不影响旧报告读取；按周新计算需要恢复周字段或可靠映射及确认时间口径
