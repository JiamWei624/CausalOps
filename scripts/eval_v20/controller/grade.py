"""Read-only, post-close adjudication. This module is never imported by the browser."""
import argparse,json,math,re,sqlite3
from datetime import datetime
from pathlib import Path
from statistics import median
from common import CASES,ROOT,bounded,read,save,sha

def like(text,pattern):
    return bool(re.search(pattern,text,re.I|re.S))
def number(text,value,tolerance=.005):
    return any(abs(float(v)-value)<=tolerance for v in re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\d.])',text.replace(',',''),flags=re.ASCII))
def duration(a,b):
    try:return max(0,(datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds())
    except (TypeError,ValueError):return None
def rows(db,q,params=()):
    return [dict(v) for v in db.execute(q,params)]
def records(fs,k):
    return [json.loads(f[k]) for f in fs if f.get(k)]
def ratio_terms(s):
    return all(like(s,p) for p in ('订单|orders','访客|visitors','分母|访问人数','加权|按.*访客|汇总.*(?:相除|除以)|总订单.*总访客','(?:零|0|没出单|没有订单).{0,60}(?:保留|计入|纳入|分母|不能删除|不可删除)|(?:保留|计入|纳入).{0,22}(?:零|0|没出单)'))
def concepts(case,s,key):
    if case=='B01':
        return dict(对照访问率=number(s,key['control_percent'],.055),处理访问率=number(s,key['treated_percent'],.055),
            差值和单位=number(s,key['pp'],.055) and like(s,'百分点|percentage point|\\bpp\\b'),
            两组=like(s,'男装|男士') and like(s,'未发|未发送|未收|不发|无邮件|对照'),观察窗=like(s,'两周|二周|2周|14天|14 天'))
    if case=='B02':
        no_causal=like(s,'不(?:能|等于|代表|足以|意味着|能据此|可).{0,22}(?:因果|导致|提高|干预)|非因果|仅.{0,12}(?:关联|相关)|不识别.{0,12}因果')
        return dict(核心统计量=number(s,key['r']),方法及变量=like(s,'相关|pearson|皮尔逊') and like(s,'满意度|satisfaction') and like(s,'消费|金额|spend|购买'),非因果边界=no_causal)
    if case=='B03':return dict(比率权重真零日=ratio_terms(s))
    if case=='B04':
        low=like(s,'(?:低于|小于|不到|未达|低|少|小).{0,10}(?:9|九)|(?:比|相对).{0,8}(?:9|九).{0,12}(?:小|低|少)|8\\.90[56]\\s*[<＜]\\s*9')
        wrong=like(s,'(?:高于|大于|超过|多于)\\s*(?:阈值|基准)?\\s*(?:9|九)')
        return dict(旧均值=number(s,key['mean']),阈值方向=low and not wrong,单位=like(s,'订单|单/日|单每天'))
    if case=='B05':return dict(新指标=like(s,'访客|visitors'),新均值=number(s,key['mean']),单位=like(s,'访客|人次|人数'))
    return dict(新时间窗=like(s,'七.{0,2}天|7.{0,2}天|七.{0,2}日|7.{0,2}日|'+key['window_start']),
        合理边界=like(s,'无法|不能|需要|请确认|尚未|未筛选|未执行|需先|截止|起止|过滤|筛选|补充|不适用') or number(s,key['mean']))

def backend(work,initial,case,key):
    db=sqlite3.connect((work/'research.sqlite3').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    sid=initial['session_id']
    flows=rows(db,'select * from workflow_flows where session_id=?',(sid,))
    recent=[f for f in flows if f['id'] not in initial['flows']]
    outputs={f['id']:{x['kind']:json.loads(x['body']) for x in rows(db,'select kind,body from workflow_outputs where flow_id=?',(f['id'],))} for f in recent}
    plans={v['id']:v for v in rows(db,'select * from assistant_plans where session_id=?',(sid,))}
    tasks=rows(db,"select t.* from assistant_tasks t join assistant_plans p on p.id=t.plan_id where p.session_id=? and t.state='completed'",(sid,))
    runs=[(t['plan_id'],json.loads(t['result'])) for t in tasks]
    old_ids=set(key['old_ids']);new=[(pid,r) for pid,r in runs if r['run_id'] not in old_ids]
    receipts=records(rows(db,'select body from workflow_approvals where not revoked'),'body')
    def authorized(pid,r):
        for a in receipts:
            if a['plan_id']!=pid or a['plan_sha']!=plans[pid]['sha'] or a['data']['frame_sha']!=r['contract']['data_fingerprint']:continue
            if db.execute("select 1 from workflow_events where flow_id=? and node='execute_plan' and status='started' and created>=?",(a['flow_id'],a['approved_at'])).fetchone():return True
        return False
    auth=all(authorized(pid,r) for pid,r in runs)
    def artifact(pid,r):
        if r['kind']=='exploration':
            q=db.execute('select path,sha from exploration_runs where run_id=?',(r['run_id'],)).fetchone()
            if not q:return {}
            p=(work/q['path']).resolve()
            if not p.is_relative_to(work) or sha(p)!=q['sha']:return {}
        else:
            q=db.execute('select result_bundle_path from analysis_runs where run_id=?',(r['run_id'],)).fetchone()
            if not q:return {}
            p=Path(q[0]).resolve()
            if not p.is_relative_to(work):return {}
        return read(p)
    bundles={r['run_id']:artifact(pid,r) for pid,r in runs}
    intact=old_ids.issubset(bundles) and all(bundles[i] for i in old_ids)
    intact=bool(intact and all(plans.get(p['id'],{}).get('sha')==p['sha'] for p in initial['plans']))
    source=key.get('source_run')
    result=bundles.get(source,{})
    def close(x,y):return isinstance(x,(float,int)) and math.isclose(x,y,abs_tol=1e-8,rel_tol=1e-8)
    def numeric(b,col,val,n):return any(v['field']==col and v['finite_n']==n and close(v['mean'],val) for v in b.get('summary',{}).get('numeric',[]))
    if case=='B01':
        rates=result.get('evidence',{}).get('rate_contrast',{})
        match=close(rates.get('pp'),key['pp']) and close(rates.get('control_rate'),key['control_percent']/100) and close(rates.get('treated_rate'),key['treated_percent']/100) and result.get('estimate',{}).get('sample_size')==key['records']
    elif case=='B02':
        match=any({v['x'],v['y']}=={'satisfaction','spend'} and close(v['pearson'],key['r']) and v['pairwise_n']==key['n'] for v in result.get('summary',{}).get('correlations',[]))
    elif case=='B03':
        body=json.loads(db.execute('select body from workflow_data_contracts where session_id=? order by version desc limit 1',(sid,)).fetchone()[0])
        m=body.get('measurement',{});match=m.get('numerator')=='orders' and m.get('denominator')=='visitors' and m.get('aggregation')=='ratio_of_sums'
    elif case=='B04':match=numeric(result,'orders',key['mean'],key['records'])
    else:
        acceptable=[]
        for pid,r in new:
            if r['method']!='descriptive' or plans[pid]['version']<=max(v['version'] for v in initial['plans']):continue
            cfg=bundles[r['run_id']].get('design',{})
            if case=='B05':
                if (cfg.get('numeric') or [None])[0]=='visitors' and numeric(bundles[r['run_id']],'visitors',key['mean'],key['records']):acceptable.append(r['run_id'])
            elif numeric(bundles[r['run_id']],'orders',key['mean'],key['n']):acceptable.append(r['run_id'])
        source=acceptable[-1] if acceptable else None
        match=bool(acceptable) or case=='B06' and not new
    method_ok=all(r['method']==key.get('method',r['method']) for pid,r in runs if r['run_id']==source)
    repeat=bool(new) if case in ('B01','B02','B03','B04') else len(new)>1
    answers=[v['answer'] for v in outputs.values() if v.get('answer')]
    events=rows(db,"select event.kind,event.body from assistant_events event where session_id=?",(sid,))
    model=[json.loads(e['body']) for e in events if e['kind']=='model_usage']
    requests=sum(e['kind']=='model_request' for e in events)
    db.close()
    return dict(correct=bool(auth and intact and match and method_ok and not repeat),auth=auth,intact=intact,match=bool(match),method_ok=method_ok,
        repeat=repeat,new_count=len(new),source=source,clarification=case=='B06' and not new,answers=answers,
        model=model,requests=requests,flows=len(recent),run_ids=[r['run_id'] for _,r in runs])

def evaluate(folder,key):
    info=read(folder/'launch.json');interaction=read(folder/'interaction.json')
    case=info['case_id'];base=read(ROOT/'fixtures'/case/'initial.json')
    b=backend((folder/'workspace').resolve(),base,case,key)
    turns=interaction.get('turns',[]);snaps=[];evidence=[]
    for t in turns:
        ref=t.get('evidence') or {};p=(folder/'browser'/ref.get('observation','')).resolve()
        png=(folder/'browser'/ref.get('screenshot','')).resolve()
        if p.is_relative_to((folder/'browser').resolve()) and png.is_relative_to((folder/'browser').resolve()) and p.is_file() and png.is_file():
            snaps.append(read(p));evidence.append(str(png))
    questions=[t.get('user_question') for t in turns if t.get('user_question')]
    page='\n'.join(s.get('text','') for s in snaps)
    for q in questions:page=page.replace(q,'')
    final=interaction.get('final_answer') or ''
    pg=concepts(case,page,key);ans=concepts(case,final,key)
    cutoff=bool(final.rstrip().endswith(('...','…','[截断]'))) if final else None
    source=b['source']
    def backed(a):
        return source and a.get('run_ids')==[source] and bool(a.get('facts')) and all(f.get('run_id')==source for f in a['facts'])
    visible_reply=any(final.strip()==s.get('reply','').strip() for s in snaps) if final else False
    bound=any(backed(a) and bool(a.get('text')) and (a['text'].strip()==final.strip() or a['text'].strip() in final) for a in b['answers'])
    if source:
        pg['来源可辨']=bool(source[:8] in page or (like(page,'证据|来源|报告|运行') and bound))
        ans['引用对应运行']=bool(bound or source[:8] in final)
    if b['clarification']:
        ans['未冒充新结果']=like(final,'无法|不能|需要|请确认|尚未|未|先|补充') and not like(final,'已(?:经)?按.{0,10}(?:七|7).{0,15}(?:计算|得出)')
    page_ok=bool(snaps and all(pg.values()))
    final_ok=bool(visible_reply and all(ans.values()) and not cutoff and not b['repeat'])
    events=interaction.get('events',[])
    failures=[t for t in turns if t.get('result')=='failed']
    disconnected=any(s.get('disconnected') for s in snaps)
    fault=disconnected or bool(failures) or any(e.get('kind')=='pageerror' for e in events) or interaction['status']=='browser_error'
    external=interaction.get('external_interventions')
    if external is None:external=0 if interaction.get('external_intervention') is False else None
    if isinstance(external,list):external=len(external)
    actual=[e for e in b['model'] if e.get('provider_host')=='api.deepseek.com']
    successful=[e for e in actual if e.get('status')=='completed']
    effective=sum(t.get('result')=='ok' and t.get('action',{}).get('action') not in ('wait','done','abandon') for t in turns)
    firstq=next((t for t in turns if t.get('user_question')),None)
    independent=external==0
    complete=bool(b['correct'] and page_ok and final_ok and successful and independent and interaction['status'] in ('fixed_finished','done'))
    numerical=None
    if final:
        if case=='B04' and like(final,'高于|低于|小于|大于|比.{0,5}9|超过|未达'):numerical=not ans['阈值方向']
        elif case=='B01' and like(final,r'\d[\d.]*\s*个百分点'):numerical=not ans['差值和单位']
        elif case=='B02' and like(final,r'(?:相关系数|Pearson|皮尔逊|r\s*=).{0,16}[-+]?0\.\d+'):numerical=not ans['核心统计量']
        elif case=='B05' and like(final,r'(?:均值|平均).{0,16}\d+'):numerical=not ans['新均值']
        elif case=='B06' and not b['clarification'] and like(final,r'(?:均值|平均).{0,16}\d+'):numerical=not number(final,key['mean'])
    return dict(case=case,strategy=info['strategy'],attempt=info['attempt'],status=interaction['status'],complete=complete,
        backend_correct=b['correct'],page_complete=page_ok,final_complete=final_ok,effective_delivery=bool(b['correct'] and final_ok),
        effective_actions=effective,seconds=duration(interaction['started'],interaction['ended']),user_turns=len(questions),
        proactive_help=sum(like(q,'请帮我|帮我找|找不到|怎么办|要怎么|不知道怎么') for q in questions[1:]),
        external_interventions=external,method_error=(not b['method_ok']) if b['source'] else None,
        numeric_interpretation_error=numerical,
        approval_version_error=not b['auth'] or not b['intact'],actual_fault=fault,
        autonomous_recovery=(complete and independent) if fault else None,model_requests=b['requests'],real_model_responses=len(actual),
        successful_model_responses=len(successful),model_latency_ms=sum(e['latency_ms'] for e in actual if type(e.get('latency_ms')) in (float,int)) if actual else None,
        physical_attempts=sum(e.get('attempts',1) for e in actual) if len(actual)==b['requests'] and actual else None,
        input_tokens=sum(e.get('input_tokens') or 0 for e in actual) if actual else None,output_tokens=sum(e.get('output_tokens') or 0 for e in actual) if actual else None,
        verified_fee=None,page_checks=pg,final_checks=ans,visible_final=final,visible_truncation=cutoff,source_bound=bool(bound),
        initial_runs_intact=b['intact'],all_runs_authorized=b['auth'],additional_runs=b['new_count'],repeat_computation=b['repeat'],
        backend_value_and_scope=b['match'],selected_source=source,interaction=str(folder/'interaction.json'),screens=evidence)
def rate(values):
    v=[x for x in values if x is not None];return {'通过':sum(bool(x) for x in v),'分母':len(v)}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    seal=read(ROOT/'frozen.json');folders=[]
    for m,n in seal['strategy_slots'].items():
        for c in CASES:
            for i in range(1,n+1):
                f=ROOT/'attempts'/m/c/f'attempt-{i}';file=f/'interaction.json'
                if not file.exists():raise SystemExit('整批尚未结束，禁止评分')
                s=read(file)
                if not s.get('ended') or s.get('status') in ('started','observed',None):raise SystemExit('无有效终态，禁止评分')
                if read(f/'launch.json')['freeze_sha256']!=sha(ROOT/'frozen.json'):raise SystemExit('启动记录冻结摘要不符')
                folders.append(f)
    for name,h in seal['code'].items():
        if sha(Path(__file__).parent/name)!=h:raise SystemExit('冻结程序摘要不同')
    gold=ROOT/'sealed/gold.json'
    if sha(gold)!=seal['gold_sha256']:raise SystemExit('标准答案摘要不符')
    keys=read(gold);out=bounded(a.output);out.mkdir(parents=True,exist_ok=False)
    scores=[evaluate(f,keys[read(f/'launch.json')['case_id']]) for f in folders];save(out/'逐次三层证据.json',scores)
    summary={}
    for m in seal['strategy_slots']:
        group=[r for r in scores if r['strategy']==m]
        summary[m]={k:rate(r[k] for r in group) for k in ('complete','effective_delivery','backend_correct','page_complete','final_complete','autonomous_recovery','method_error','numeric_interpretation_error','approval_version_error')}
        summary[m]['first_attempt']=rate(r['complete'] for r in group if r['attempt']==1)
        for k in ('effective_actions','seconds','user_turns','proactive_help','external_interventions','model_requests','real_model_responses','model_latency_ms','physical_attempts','input_tokens','output_tokens','verified_fee'):
            v=[r[k] for r in group if r[k] is not None];summary[m][k]={'总和':sum(v) if v else None,'已知槽位':len(v),'全部槽位':len(group),'中位数':median(v) if v else None}
    save(out/'16项指标.json',summary)
    report=['# V2 浏览器试点评分','','|策略|任务|尝试|后台|页面|最终答复|完成|操作|轮次|秒|','|---|---|---:|---|---|---|---|---:|---:|---:|']
    for r in scores:
        report.append('| '+' | '.join(str(r[k]) for k in ('strategy','case','attempt','backend_correct','page_complete','final_complete','complete','effective_actions','user_turns','seconds'))+' |')
    report+=['','逐次三层证据 JSON 含实际可见答案、运行绑定、图片路径及具体缺失项。16项指标 JSON 保留缺测分母；异常恢复仅对发生过故障的槽位计算。已核实费用需账单支持。']
    (out/'逐题报告.md').write_text('\n'.join(report)+'\n',encoding='utf8')
    print('评分完成',len(scores),out)
if __name__=='__main__':main()
