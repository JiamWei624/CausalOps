"""Bounded LangGraph method research; citations and data conditions stay distinct."""
from __future__ import annotations
import re
from typing import TypedDict
import pandas as pd
from langgraph.graph import StateGraph,START,END
from causalops.knowledge.retrieval import ALIASES
from causalops.assistant.contracts import REGISTRY
from causalops.integrations.method_retriever import MethodRetriever
from causalops.general.service import DesignError

SECTIONS=('适用问题','数据要求','识别条件','诊断方法','失败情形','结果解释')
FACTS={
 'ols':['independent_rows_reviewed'],'logit':['independent_rows_reviewed'],'poisson':['independent_rows_reviewed','comparable_exposure_reviewed'],
 'ab_test':['assignment'],'cuped':['assignment','covariates_reviewed'],
 'regression_adjustment':['covariates_reviewed'],
 'psm':['covariates_reviewed','exchangeability_declared','overlap_declared'],
 'ipw':['covariates_reviewed','exchangeability_declared','overlap_declared'],
 'double_ml':['covariates_reviewed','exchangeability_declared','overlap_declared'],
 'aipw':['covariates_reviewed','exchangeability_declared','overlap_declared'],
 'did':['panel_confirmed','parallel_declared','no_anticipation_declared'],
 'iv_2sls':['independent_units_reviewed','instrument_exogeneity_reviewed','exclusion_reviewed','design_evidence'],
 'rd_sharp':['independent_units_reviewed','threshold_rule_reviewed','continuity_reviewed','no_manipulation_reviewed','design_evidence'],
 'rd_fuzzy':['independent_units_reviewed','threshold_rule_reviewed','continuity_reviewed','no_manipulation_reviewed','exclusion_reviewed','monotonicity_reviewed','design_evidence'],
 'staggered_did':['parallel_reviewed','no_anticipation_reviewed','no_interference_reviewed','design_evidence']}

class MethodState(TypedDict,total=False):
    flow_id:str
    candidates:list[str]
    unsupported:bool
    attempt:int
    missing:list[str]
    stop_reason:str
    method_research_ref:str

def candidate_methods(service,flow):
    q=flow['request']['question'];decision=service.output(flow['id'],'route') or {}
    unknown=bool(re.search('因果森林|合成控制|synthetic control|causal forest',q,re.I))
    if decision.get('route')=='results' and flow['request']['run_ids']:
        selected={v['run_id']:v['method'] for v in service.a.completed_runs(flow['session_id'])}
        return list(dict.fromkeys(selected[i] for i in flow['request']['run_ids'] if i in selected))[:3],False
    if decision.get('methods'):return list(dict.fromkeys(decision['methods'])),unknown
    canonical=[m for m in REGISTRY if re.search(r'(?<![A-Za-z0-9_])'+re.escape(m)+r'(?![A-Za-z0-9_])',q,re.I)]
    requested=list(dict.fromkeys(decision.get('methods',[])+canonical))
    for method,pattern in ALIASES.items():
        if re.search(pattern,q,re.I):requested.append(method)
    if re.search('随机实验|随机试验|A/B|实验组.*对照组',q,re.I):requested.append('ab_test')
    if 'aipw' in requested and not re.search(r'(?<![A-Za-z])ipw(?![A-Za-z])|逆概率',q,re.I):requested=[m for m in requested if m!='ipw']
    if 'rd_fuzzy' in requested:requested=[m for m in requested if m!='rd_sharp']
    if 'staggered_did' in requested:requested=[m for m in requested if m!='did']
    if any(m!='descriptive' for m in requested):requested=[m for m in requested if m!='descriptive']
    if not requested and not unknown:
        contract=service.contracts.bound(flow)
        body=contract['body'] if contract else {}
        if body.get('purpose')=='causal' and any(v.get('assignment')=='randomized' for v in body.get('method_facts',{}).values()):requested=['ab_test']
        elif body.get('outcome') and body.get('predictors'):requested=['logit' if body.get('metric_kind')=='binary' else 'ols']
        else:requested=['descriptive']
    return list(dict.fromkeys(m for m in requested if m in REGISTRY))[:3],unknown

def condition_check(service,flow,methods):
    if (service.output(flow['id'],'route') or {}).get('route')=='results':return [{'method':m,'condition':'运行级解释范围','status':'structural','detail':'按选定运行的原计划、原指标口径和证据解释，不使用新字典改写旧结果。','evidence_type':'saved_run_scope'} for m in methods]
    row=service.contracts.bound(flow);body=row['body'] if row else {};frame=service.ws.load_upload(flow['request']['data']['upload_id']);checks=[]
    def add(m,condition,status,detail):checks.append({'method':m,'condition':condition,'status':status,'detail':detail,'evidence_type':'human_declaration_not_validation' if status=='declared' else 'local_structure' if status=='structural' else 'required_not_completed'})
    for m in methods:
        if m=='descriptive':add(m,'可统计字段','structural','描述字段仍排除标识；不作因果解释。');continue
        if m=='correlation':
            n=sum(pd.api.types.is_numeric_dtype(frame[c]) for c in frame)
            add(m,'至少两个数值字段','structural' if n>=2 else 'missing','仅检查类型数量；具体字段仍须核对。');continue
        if m in ('ols','logit','poisson'):
            needed=['outcome','predictors']
        else:needed=['outcome','entity']+(['treatment'] if m not in ('rd_sharp','staggered_did') else [])
        if m in ('cuped','psm','ipw','double_ml','aipw','regression_adjustment'):needed+=['covariates']
        if m=='did':needed+=['time','treatment_time']
        if m=='iv_2sls':needed+=['instruments']
        if m in ('rd_sharp','rd_fuzzy'):needed+=['running','cutoff']
        if m=='staggered_did':needed+=['time','cohort']
        for field in needed:
            value=body.get(field);known=value is not None and value!=[] and value!=''
            add(m,field,'declared' if known else 'missing','已登记变量口径；不是科学假设检验。' if known else '请在数据字典或候选审核中补充该角色。')
        facts=body.get('method_facts',{}).get(m,{})
        for key in FACTS.get(m,[]):
            value=facts.get(key);known=value=='randomized' if key=='assignment' else isinstance(value,str) and len(value.strip())>=12 if key=='design_evidence' else value is True
            add(m,key,'declared' if known else 'missing','使用者已声明；执行器仍需核对适用性与诊断。' if known else '需要具体研究依据或明确确认，不由模型填充。')
        outcome=body.get('outcome')
        if outcome and m in ('logit','poisson'):
            v=pd.to_numeric(frame[outcome],errors='coerce').dropna()
            ok=len(v)>0 and (v.isin([0,1]).all() if m=='logit' else ((v>=0)&(v%1==0)).all())
            add(m,'结果取值范围','structural' if ok else 'missing','仅核对当前表的数值范围，不证明建模设定。')
        roles=body.get('covariates',[])+(body.get('predictors',[]) if body.get('purpose')=='predictive' else [])
        bad=[x['field'] for x in body.get('fields',[]) if x['field'] in roles and x['timing'] in ('post_treatment','future')]
        if bad:add(m,'测量时序','missing','已登记的处理后或未来变量不得用于该设定：'+', '.join(bad))
        add(m,'执行后诊断','diagnostic_required','适用性、残差/重叠/趋势/弱工具等诊断须由对应执行器实际运行，文献不能代替。')
    return checks

def build_method_graph(service):
    s=service
    def choose(state):
        fid=state['flow_id'];s.check_cancel(fid);flow=s.flow(fid);methods,unknown=candidate_methods(s,flow)
        s.emit(fid,'method_scope','completed',{'methods':methods,'unsupported':unknown})
        return {'candidates':methods,'unsupported':unknown,'attempt':0}
    def search(state):
        fid=state['flow_id'];s.check_cancel(fid);i=state.get('attempt',0);flow=s.flow(fid)
        cached=s.output(fid,'method_pass_'+str(i))
        if cached is None:
            if i==0:query=flow['request']['question']+(' 描述 数据质量' if state['candidates']==['descriptive'] and not state['unsupported'] else '')
            else:query=' '.join(state.get('missing',state['candidates']))+' 适用问题 数据要求 识别条件 诊断方法 失败情形 结果解释'
            if (s.output(fid,'route') or {}).get('route')=='plan':query+=' 描述 数据质量'
            target=state.get('missing',[None])[0] if i>0 and state.get('missing') else None
            if target:query=REGISTRY[target].label+' '+flow['request']['question']+' '+query
            cached=MethodRetriever(library=s.a.library,k=8,method_filter=target).search_bundle(query)
            s.save_output(fid,'method_pass_'+str(i),cached)
        s.emit(fid,'method_retrieval','completed',{'pass':i+1,'card_ids':[h['card_id'] for h in cached['hits']]})
        return {'attempt':i+1}
    def assess(state):
        fid=state['flow_id'];s.check_cancel(fid);hits={}
        for i in range(state['attempt']):
            bundle=s.output(fid,'method_pass_'+str(i))
            if bundle['knowledge_sha256']!=s.a.library.digest:raise DesignError('检索期间知识库版本变化，停止合并。')
            for hit in bundle['hits']:hits[hit['card_id']]=hit
        missing=[]
        for method in state['candidates']:
            cards=[h for h in hits.values() if method in h['methods'] and h['scope']=='method_rule']
            if not any(all(h['sections'].get(section) for section in SECTIONS) and h.get('sources') for h in cards):missing.append(method)
        if state['unsupported']:reason='unsupported_method'
        elif not missing:reason='coverage_complete'
        elif state['attempt']>=3:reason='retrieval_budget'
        elif state['attempt']>1:
            prev={h['card_id'] for i in range(state['attempt']-1) for h in s.output(fid,'method_pass_'+str(i))['hits']}
            reason='no_new_evidence' if set(hits)==prev else 'supplement'
        else:reason='supplement'
        return {'missing':missing,'stop_reason':reason}
    def finish(state):
        fid=state['flow_id'];flow=s.flow(fid);hits={}
        for i in range(state['attempt']):
            for h in s.output(fid,'method_pass_'+str(i))['hits']:hits[h['card_id']]=h
        ordered=sorted(hits.values(),key=lambda h:(not any(m in h['methods'] for m in state['candidates']),h['scope']!='method_rule',-h['score'],h['card_id']))[:8]
        if state['unsupported']:ordered=[]
        if ordered:s.a.library.validate_citations([h['card_id'] for h in ordered],ordered)
        bundle={'status':'found' if ordered else 'insufficient_evidence','hits':ordered,'knowledge_version':s.a.library.catalog['version'],'knowledge_sha256':s.a.library.digest,'retrieval_version':'bounded-langgraph-v2','note':'最多三轮本地检索；方法规则与实证案例分开，覆盖完整不代表数据满足识别条件。'}
        checks=condition_check(s,flow,state['candidates']);missing=[x for x in checks if x['status']=='missing']
        advice={'candidate_methods':state['candidates'],'coverage_missing_methods':state['missing'],'stop_reason':state['stop_reason'],'retrieval_passes':state['attempt'],'conditions':checks,'status':'unsupported' if state['unsupported'] else 'insufficient_evidence' if state['missing'] else 'needs_confirmation' if missing else 'ready_for_review','questions':list(dict.fromkeys(x['condition']+'：'+x['detail'] for x in missing))[:6],'contract_ref':flow['request'].get('contract_ref'),'not_empirical_validation':True}
        s.save_output(fid,'retrieval',bundle);s.save_output(fid,'method_research',advice);s.emit(fid,'method_research','completed',{'status':advice['status'],'stop_reason':advice['stop_reason'],'passes':state['attempt']})
        return {'method_research_ref':fid}
    graph=StateGraph(MethodState)
    for name,fn in [('scope',choose),('retrieve',search),('assess',assess),('finish',finish)]:graph.add_node(name,fn)
    graph.add_edge(START,'scope');graph.add_edge('scope','retrieve');graph.add_edge('retrieve','assess')
    graph.add_conditional_edges('assess',lambda x:'retrieve' if x['stop_reason']=='supplement' else 'finish',{'retrieve':'retrieve','finish':'finish'});graph.add_edge('finish',END)
    return graph
