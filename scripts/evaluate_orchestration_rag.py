from pathlib import Path
import json,time
from causalops.knowledge.retrieval import MethodLibrary
root=Path('E:/ugc_ai_portfolio/causalops-agent');out=root/'artifacts/orchestration-v060-20261031';lib=MethodLibrary()
cases=[
('描述性统计中缺失值和分布怎么报告','describe'),('分类频数的分母与IQR异常标记','describe'),('Pearson与Spearman常量输入','correlation'),('只做相关关系不能说明因果','correlation'),
('OLS残差异方差和HC3标准误','ols'),('条件线性回归可以解释干预收益吗','ols'),('Logit二元转化概率模型','logit'),('二项模型完全分离和收敛问题','logit'),('Poisson计数暴露时长与过度离散','poisson'),
('A/B随机实验均值差与独立单位','ab'),('Welch两独立样本检验','ab'),('CUPED处理前指标与降方差','cuped'),('CUPED协变量泄漏风险','cuped'),
('PSM匹配平衡与共同支撑','psm'),('IPW逆概率加权极端权重','psm'),('DoubleML PLR与IRM区别','dml'),('AIPW交叉拟合的处理前协变量','dml'),
('DID处理前系数检验不能证明平行趋势','did'),('双重差分的无预期效应','did'),('Airbnb实验干扰SUTVA','interference'),('AI客服效率质量的实证案例','ai_chat'),('人机工作流认知适配','human_ai'),
('工具变量2SLS的排除限制与弱工具','iv_2sls'),('Anderson Rubin指定原假设与弱工具检验','iv_2sls'),('Sharp RD阈值操纵与连续性','rd_sharp'),('清晰断点的局部参数和带宽','rd_sharp'),
('Fuzzy模糊断点处理概率跳跃','rd_fuzzy'),('模糊断点的单调性与排除限制','rd_fuzzy'),('交错DID ATT(g,t)与从未处理对照','staggered_did'),('staggered事件期逐点区间和批次构成','staggered_did'),
('JFE交错处理TWFE估计偏误','jfe_design_review'),('平台政策实证设计中处理后协变量风险','platform_policy_review'),('CSR阈值实证文献与断点识别','csr_threshold_review')]
rows=[]
for q,expected in cases:
 row={'question':q,'expected_card':expected}
 for strategy in ['baseline','sectional']:
  start=time.perf_counter();hits=lib.search(q,strategy=strategy)['hits'];ids=[x['card_id'] for x in hits]
  rank=ids.index(expected)+1 if expected in ids else None
  row[strategy]={'ids':ids,'rank':rank,'seconds':time.perf_counter()-start}
 rows.append(row)
unsupported=['合成控制如何估计','因果森林的异质性处理效应','zxqvjk8844']
checks={q:lib.search(q)['status']=='insufficient_evidence' for q in unsupported}
metrics={}
for strategy in ['baseline','sectional']:
 metrics[strategy]={'cases':len(rows),'recall_at_4':sum(r[strategy]['rank'] is not None for r in rows)/len(rows),'mrr_at_4':sum(1/r[strategy]['rank'] if r[strategy]['rank'] else 0 for r in rows)/len(rows),'top1':sum(r[strategy]['rank']==1 for r in rows)/len(rows)}
report={'evaluation_type':'fixed_developer_regression_set_not_independent_user_or_model_accuracy','knowledge_sha256':lib.digest,'card_count':len(lib.cards),'source_count':len(lib.catalog['sources']),'section_count':len(lib.sections),'metrics':metrics,'unsupported_abstention':checks,'cases':rows,'limits':'固定开发回归集；没有测量真实用户完成率、节省时间或新模型对话准确率。分数不是开放问题通用准确率。'}
(out/'rag-evaluation.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'metrics':metrics,'abstention':checks,'missing_sectional':[r['expected_card'] for r in rows if r['sectional']['rank'] is None]},ensure_ascii=False))
