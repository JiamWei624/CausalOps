"""Offline report, joined by task/attempt. Does not import a model client or initiate requests."""
import argparse,json,sqlite3
from collections import Counter
from datetime import datetime,timedelta
from pathlib import Path
from statistics import median
from .inputs import CASES
from .rubric import RULES


def load(p):return json.loads(p.read_text('utf8'))


def accounting(files):
    responses=[json.loads(line) for p in files for line in p.read_text('utf8').splitlines()]
    token_in=token_out=cached=measured=0
    after_hours_estimate=0.
    elapsed=[]
    peak_possible=False
    for r in responses:
        elapsed.append(r['seconds'])
        u=r['usage']
        if 'input_tokens' not in u or 'output_tokens' not in u:continue
        measured+=1
        local=datetime.fromisoformat(r['at']).astimezone(__import__('datetime').timezone(timedelta(hours=8)))
        peak_possible |= local.weekday()<5 and (9<=local.hour<12 or 14<=local.hour<18)
        hit=u.get('input_tokens_details',{}).get('cached_tokens',0)
        token_in+=u['input_tokens'];token_out+=u['output_tokens'];cached+=hit
        after_hours_estimate+=(hit*.02+(u['input_tokens']-hit)+u['output_tokens']*4)/1_000_000
    return dict(响应记录=len(responses),有用量=measured,输入=token_in,缓存命中=cached,输出=token_out,可能跨高峰=peak_possible,
                响应耗时中位秒=median(elapsed) if elapsed else None,空闲价估算人民币=after_hours_estimate,
                响应类别=dict(Counter(r['schema'] for r in responses)),
                异常=dict(Counter(r['error'] for r in responses if 'error'in r)),
                北京时间范围=[(datetime.fromisoformat(v).astimezone(__import__('datetime').timezone(timedelta(hours=8)))).isoformat()
                        for v in (min(r['at'] for r in responses), max(r['at'] for r in responses))] if responses else [])


def report(local,live,fixed,out):
    out.mkdir(parents=True,exist_ok=False)
    summaries={};allrows={};review=[]
    for label,root in [('本地',local),('官方模型',live)]:
        rows=load(root/'results.json');allrows[label]=rows
        assert len({(r['任务'],r['尝试']) for r in rows})==len(rows)==45
        s=load(root/'summary.json');summaries[label]=s
        s['每题三次均通过']=sum(all(r['结果']!='失败' for r in rows if r['任务']==c) for c in CASES)
        s['前后结果不同的任务数']=sum(len({r['结果'] for r in rows if r['任务']==c})>1 for c in CASES)
        s['历史报告数值与引用正确率']=dict(通过=sum(r['数字及引用'] is True for r in rows if r['任务']=='C12'),有效数=sum(r['任务']=='C12' for r in rows))
        s['平均尝试秒']=s['耗时秒']/len(rows)
        s['有效性状态计数']=dict(Counter(r['结果'] for r in rows))
        s['应用结构修复重试']=0
        for r in rows:
            folder=root/r['任务']/('attempt-'+str(r['尝试']))
            observed=load(folder/'observation.json') if (folder/'observation.json').exists() else {}
            db=folder/'work/research.sqlite3'
            if db.exists():
                with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
                    s['应用结构修复重试']+=conn.execute("select count(*) from assistant_events where kind='output_contract_repair'").fetchone()[0]
            target=next((f for f in observed.get('flows',[]) if f['id']==observed.get('target')),{})
            advice=observed.get('advice') or {}
            review.append(dict(模式=label,任务=r['任务'],尝试=r['尝试'],用户问题=CASES[r['任务']].question,
                 模型原建议=advice,工作台路线=target.get('route'),实际答复=target.get('answer'),
                 原判据=r['判据'],原错误=r['错误'],人工复核状态='待独立复核',
                 证据路径=str(folder.relative_to(out.parent)) if folder.is_relative_to(out.parent) else str(folder)))
    usage=accounting(live.glob('C*/attempt-*/responses.jsonl'));probe=accounting(live.glob('smoke/*/*/responses.jsonl'))
    fixed_summary=load(fixed/'summary.json')
    meta=dict(固定十题=fixed_summary,挑战汇总=summaries,正式调用=usage,冒烟调用=probe)
    for n,v in [('metrics',meta),('review-queue',review)]:
        (out/(n+'.json')).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    t=['# CausalOps Eval V1.2 · 真实模型研究任务验收','',
       '固定回归集与陌生挑战分别计分。所有数据来自固定合成生成器，固定回归另使用已登记的公开数据。没有真人参与。',
       '',f"固定十题本地模式：{fixed_summary['指标']['任务正确处理率']['分子']}/{fixed_summary['指标']['任务正确处理率']['分母']}。此前同一固定题集的旧版为 8/10，修复后为 10/10。固定十题本轮未用外部模型重跑。",
       '','| 正式挑战指标 | 本地规则 | DeepSeek 辅助 |','|---|---:|---:|']
    def fmt(v):
        if isinstance(v,dict):
            n=v['有效数'];return f"{v['通过']}/{n}（{v['通过']/n:.1%}）" if n else '不适用'
        return f'{v:.2f}' if isinstance(v,float) else str(v)
    for k in ['尝试数','任务正确处理率','方法建议合理率','模型研究条件识别率','独立研究建议结构有效率','结构化方案有效率',
              '关键条件识别率','不合法执行阻断率','数值与引用判据','历史报告数值与引用正确率','多轮版本正确率','严重失败','每题三次均通过','前后结果不同的任务数',
              '耗时秒','平均尝试秒','模型请求','有用量的响应','输入令牌','输出令牌','应用结构修复重试']:
        t.append('|'+k+'|'+fmt(summaries['本地'][k])+'|'+fmt(summaries['官方模型'][k])+'|')
    t+=['','## 逐题结果','下表每格依次列出第 1、2、3 次独立尝试。成功、澄清与阻断分别记录。',
        '','|任务|本地规则|官方模型|','|---|---|---|']
    for c,sc in CASES.items():
        t.append('|'+c+' '+sc.question+'|'+'|'.join(' / '.join(r['结果'] for r in rs if r['任务']==c) for rs in allrows.values())+'|')
    t+=['','## 调用与费用',
        f"官方 api.deepseek.com，deepseek-flash，Responses API，JSON Object，非思考模式，每次最多 3,000 输出 token；传输层 max_retries=0。冒烟 1 题，独立于正式分数，共 {probe['响应记录']} 个请求响应记录；正式 45 次尝试共 {usage['响应记录']} 个请求响应记录，其中 {usage['有用量']} 个有服务商用量。正式响应耗时中位数 {usage['响应耗时中位秒']:.2f} 秒。",
        f"按空闲单价复算，正式已知用量约 ¥{usage['空闲价估算人民币']:.5f}，冒烟约 ¥{probe['空闲价估算人民币']:.5f}。输入命中/未命中和输出价格分别为每百万 token 0.02/1/4 元。若请求覆盖高峰，需按实际时段重算，高峰单价为两倍。本次时段见 metrics.json。计价未计入没有用量回执的请求，未取得账单。另有一次不含研究问题的 GET /models 身份验证，未计入模型生成次数。[DeepSeek 官方价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。",
        '', '## 解读口径与限制',
        '独立建议是门禁前的额外真实模型探针，不作为实际审批输入。正常工作流独立运行，仍可按本地硬规则路由。名义上的“模型辅助”不等于每个节点都由模型决定。独立建议探针若不可用，本次协议终止该尝试，因此端到端数据包含探针可用性的影响。',
        '方法建议合理率仅在有有效建议且预设需命中方法的任务上统计；关键条件为证据关键词代理。Plan 结构有效率按真实 Plan 请求（含应用修复请求）计分，不能与题次相除。数值与引用复合判据包含 C08/C09 的独立复算和 C12 的历史运行数字。严重失败是未绑定批准或不应出现的新增估计，未观察到此类事件不能证明所有入口安全。',
        '累计耗时是进程耗时的和，含解释器启动、前置任务和模型探针；并行批次不可读为顺序人体用时。三次重复用于探索稳定性，题目由开发方构造，没有独立用户或外部盲评。所有语义争议进入 review-queue.json；不据此修改本次答案。']
    (out/'报告.md').write_text('\n'.join(t)+'\n',encoding='utf8')
    return meta


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('local','live','fixed','out'):p.add_argument('--'+n,type=Path,required=True)
    report(**vars(p.parse_args()))
