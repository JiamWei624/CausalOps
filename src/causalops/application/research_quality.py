"""Four-layer, aggregate-only research audit. Checks are not identification proofs."""
from __future__ import annotations
import hashlib,json
from functools import lru_cache
import numpy as np
import pandas as pd

SCOPE_LABELS={'population':'目标人群','inclusion':'样本纳入范围','comparison':'比较对象','estimand':'希望估计的量','observation_period':'观察期间','decision':'支持的决策','provenance':'数据与口径来源','limitations':'已知限制'}

def audit_research(frame,body):
    checks=[]
    def add(layer,code,status,detail,action,count=None):
        checks.append(dict(layer=layer,code=code,status=status,detail=detail,action=action,count=count))
    missing=int(frame.isna().sum().sum());dupes=int(frame.duplicated().sum())
    add('结构','missing','review' if missing else 'pass',f'缺失单元格 {missing} 个。','明确缺失规则；程序不会自动填补。',missing)
    add('结构','duplicates','review' if dupes else 'pass',f'完全重复记录 {dupes} 条；相同数值不证明重复采集。','核对来源后再决定是否排除；原表保留。',dupes)
    nums=frame.select_dtypes(include='number');inf=int(np.isinf(nums.to_numpy(dtype=float,na_value=np.nan)).sum()) if len(nums.columns) else 0
    add('统计','nonfinite','block' if inf else 'pass',f'无穷值 {inf} 个。','先核对无穷值来源；不把它们当作正常数值。',inf)
    constant=[str(c) for c in nums if nums[c].nunique(dropna=True)<=1]
    add('统计','constant','review' if constant else 'pass','常量数值字段：'+('、'.join(constant) if constant else '无'),'常量不能支持斜率识别；保留描述。',len(constant))
    # Flag values only as a review prompt; never automatically turn legitimate values into missing.
    sentinel_n=int(nums.isin([-999,-9999,9999]).sum().sum())
    if sentinel_n:add('统计','sentinels','review',f'发现 {sentinel_n} 个常见特殊编码候选值。','查数据字典；这些数值也可能是合法测量值。',sentinel_n)
    # Distribution warnings are descriptive flags, not automatic exclusion rules.
    for col in nums:
        finite=nums[col].replace([np.inf,-np.inf],np.nan).dropna()
        if len(finite)>=20:
            q1,q3=finite.quantile([.25,.75]);iqr=q3-q1
            extreme=int(((finite<q1-3*iqr)|(finite>q3+3*iqr)).sum()) if iqr>0 else 0
            if extreme:add('统计','extreme:'+str(col),'review',str(col)+f' 有 {extreme} 个超出3倍四分位距的观测。','核对量纲与业务范围；不自动缩尾或剔除。',extreme)
            zeros=int((finite==0).sum())
            if zeros/len(finite)>=.5:add('统计','zeros:'+str(col),'review',str(col)+f' 的零值占比为 {zeros/len(finite):.1%}。','零可能是真实值或编码；先核对含义，再选择计数或其他模型。',zeros)
    for col in frame.select_dtypes(exclude='number'):
        counts=frame[col].value_counts(dropna=True)
        if 1<len(counts)<=20:
            sparse=int((counts<5).sum())
            if sparse:add('统计','sparse:'+str(col),'review',str(col)+f' 有 {sparse} 个类别不足5条记录。','小类别可能导致不稳定估计；不自动合并类别。',sparse)
    entity,time=body.get('entity'),body.get('time')
    if entity in frame and time in frame:
        duplicate_keys=int(frame.duplicated([entity,time]).sum())
        add('关系','entity_time','block' if duplicate_keys else 'pass',f'实体—时间键重复 {duplicate_keys} 条。','检查观测粒度；不自动聚合或删行。',duplicate_keys)
    elif entity in frame:
        n=int(frame[entity].duplicated().sum());add('关系','repeated_entity','review' if n else 'pass',f'重复实体记录 {n} 条。','重复观测需要合适的聚类或面板方法；不能默认独立。',n)
    else:add('关系','unit_unknown','review','尚无可核对的实体标识。','确认每行含义；没有ID不等于观测独立。')
    if time in frame:
        raw=frame[time];parsed=pd.to_datetime(raw,errors='coerce') if not pd.api.types.is_numeric_dtype(raw) else None
        invalid=int((raw.notna() & parsed.isna()).sum()) if parsed is not None else 0
        add('关系','time_semantics','review' if parsed is None or invalid else 'pass','日期解析失败 '+str(invalid)+' 条。' if parsed is not None else '时间为数值编码，尚未自动解释为日期。','确认时间单位、时区和编码。',invalid)
    covs=set(body.get('covariates',[]));target=body.get('outcome')
    if target in covs:add('研究','outcome_adjustment','block','结果字段同时被设为调整变量。','修改变量角色，不能把结果本身当作控制变量。')
    definitions={f['field']:f for f in body.get('fields',[])}
    for c in sorted(covs):
        timing=definitions.get(c,{}).get('timing','unknown')
        add('研究','timing:'+c,'block' if timing in ('future','post_treatment') else 'review' if timing=='unknown' else 'declared',c+' 的测量时点：'+timing,'核对生成逻辑与测量时间；人工声明不等于程序已验证。')
    scope=body.get('research',{})
    for k in ('population','provenance'):
        if not scope.get(k):add('研究','scope:'+k,'review',SCOPE_LABELS[k]+'未登记。','补充适用范围与数据来源，或明确仅描述上传样本。')
    if body.get('purpose')=='causal':
        for k in ('comparison','estimand'):
            if not scope.get(k):add('研究','scope:'+k,'review',SCOPE_LABELS[k]+'未明确。','先明确想比较谁、估计什么，再讨论方法。')
        add('研究','identification','review','因果识别仍依赖设计、时序与业务事实。','方法诊断不能证明无遗漏混杂、无干扰或平行趋势。')
    return {'version':'research_audit_v1','rows':len(frame),'columns':len(frame.columns),'checks':checks,'status':'blocked' if any(x['status']=='block' for x in checks) else 'needs_review' if any(x['status']=='review' for x in checks) else 'ready','raw_rows_included':False,'assumptions_verified':False}

def research_brief(body,*,question='',audit=None):
    scope=body.get('research',{})
    return {'question':question,'inclusion':scope.get('inclusion') or '尚未登记纳入与排除规则；本项说明不会自动筛选数据','question_type':{'causal':'干预或策略效果问题','predictive':'预测问题','exploratory':'描述或关联问题'}.get(body.get('purpose'),'尚待明确'),
        'unit':body.get('analysis_unit') or '尚未明确','metric':body.get('metric_label') or body.get('outcome') or '整体数据',
        'population':scope.get('population') or '当前上传的分析样本；尚无外推依据',
        'comparison':scope.get('comparison') or '尚未登记比较对象；描述分析可不设对照',
        'estimand':scope.get('estimand') or '由待审计划与实际估计器明确，不能根据显著性事后选择',
        'window':scope.get('observation_period') or body.get('metric_window') or '观察期间未登记',
        'source':scope.get('provenance') or '数据来自本地上传；采样与测量来源尚待说明',
        'decision':scope.get('decision') or '尚未登记决策用途',
        'limitations':scope.get('limitations') or '未登记额外限制不表示不存在限制',
        'next_questions':[x['detail']+' '+x['action'] for x in sorted((audit or {}).get('checks',[]),key=lambda x:0 if x['status']=='block' else 1) if x['status'] in ('review','block')][:3],
        'evidence_type':'human_declaration_and_structural_checks_not_identification_proof'}

@lru_cache(maxsize=32)
def method_contract(method):
    """Display contract, not a promise of statistical identification or executable settings."""
    from causalops.assistant.contracts import REGISTRY
    from causalops.knowledge.retrieval import MethodLibrary
    specs={
      'descriptive':('样本分布','所选字段的有效观测','无效值、缺失与重复提示','无因果效应与反事实'),
      'correlation':('成对相关系数','每个变量对的有效样本','常量、缺失与成对样本数','不表示干预收益'),
      'ols':('条件线性关联系数','实际进入回归的样本','独立性、秩、缺失、模型设定','不自动作因果解释'),
      'logit':('条件对数优势系数','二元结果的有效样本','分离、收敛、类别与独立性','系数不是概率百分点变化'),
      'poisson':('条件对数计数率系数','暴露口径可比的样本','非负计数、暴露、收敛','不是自动识别的因果比率'),
      'ab_test':('随机分组均值差','实际进入两组分析的单位','随机化依据、两组规模、标准误','对试验样本解释，外推另需依据'),
      'cuped':('基线调整后的随机分组均值差','具有处理前指标的试验样本','处理前测量、基线方差与方差缩减','不以处理后指标降方差'),
      'regression_adjustment':('条件关联系数','实际回归样本','控制变量时序、聚类与模型设定','观察性调整不能消除未知混杂'),
      'psm':('保留匹配处理样本中的平均差异','共同支撑和卡尺后保留的处理样本','匹配比例、固定分母SMD、条件配对标准误','不是原总体ATE；匹配估计不确定性未全部计入'),
      'ipw':('逆概率加权平均处理效应','有效且满足重叠约束的分析样本','极端权重、重叠与有效样本量','依赖可交换性与权重模型'),
      'aipw':('交叉拟合IRM平均处理效应','有效分析样本','折外预测、重叠与影响函数推断','双重稳健不等于无需识别条件'),
      'double_ml':('部分线性模型处理系数','独立单位的有效样本','固定分折、折外倾向概率与重叠','异质效应下不自动等于总体ATE'),
      'did':('共同处理时点的DID系数','满足事件窗口的处理与对照单位','基期、前趋势、窗口、用户聚类','不能用于任意交错处理；未拒绝前趋势不证明假设'),
      'staggered_did':('批次—时期ATT及保存的汇总','具体批次和可用对照支持的样本','对照定义、预期、聚合权重与支持期','不同汇总对应不同对象'),
      'iv_2sls':('工具变量2SLS系数','工具有效性假设适用的分析样本','弱工具、外生性与排除限制','一般不能宣称总体ATE；局部效应还需额外假设'),
      'rd_sharp':('阈值处局部跳跃','带宽内阈值附近样本','连续性、操纵、带宽、局部拟合','不能外推为全体平均效应'),
      'rd_fuzzy':('阈值附近局部工具效应','阈值附近满足局部识别条件的单位','第一阶段跳跃、带宽、排除与单调性','局部效应，不是整体政策收益')}
    if method not in REGISTRY:raise ValueError('未注册方法')
    e,p,d,l=specs[method];library=MethodLibrary();cards=[c for c in library.cards if method in c['methods']]
    sources=list(dict.fromkeys(s for c in cards for s in c['source_ids']))
    return {'method':method,'label':REGISTRY[method].label,'estimand':e,'population':p,'diagnostics':d,'limits':l,
       'inference':'标准误、区间和检验以保存运行中的实际设置为准；无数值时不补写。',
       'source_ids':sources,'knowledge_sha256':library.digest,'sources':[{'source_id':s,'title':library.catalog['sources'][s]['title'],'url':library.catalog['sources'][s]['url'],'access_scope':library.catalog['sources'][s]['access_scope']} for s in sources]}


def next_research_steps(body,audit):
    """Recommendations only. Never infer assignment, add fields or execute a test."""
    blocking=[v for v in audit['checks'] if v['status']=='block']
    if blocking:
        return [{'title':'先核对数据与变量角色','reason':v['detail'],'question':v['action'],'route':'metadata'} for v in blocking[:3]]
    target=body.get('outcome');predictors=body.get('predictors',[])
    choices=[{'title':'明确目标指标的样本分布','reason':'先建立基线、缺失与分布口径，不引入因果解释。','question':'请制定描述性统计计划，优先描述已登记目标指标的水平、分布与缺失。','route':'plan'}]
    if target and predictors:
        choices.append({'title':'讨论目标指标与已登记变量的关联','reason':'字段角色已登记；仍需核对观测单位、测量尺度和独立性。','question':'请根据已登记结果和自变量制定关联分析计划，说明适用条件，不作因果解释。','route':'plan'})
    if body.get('purpose')=='causal':
        choices.append({'title':'核对因果设计的识别条件','reason':'先核对分配机制、比较对象、时点与估计目标；不因显著性挑选方法。','question':'请比较当前字段支持的因果研究设计，列出仍缺少的识别依据，不生成或批准统计结果。','route':'method'})
    else:
        choices.append({'title':'确定下一步可回答的问题','reason':'从当前数据和已登记范围出发；没有的背景信息需由使用者补充。','question':'根据当前数据与口径，推荐两个可回答的研究问题，并明确尚缺少什么。','route':'explore'})
    return choices[:3]
