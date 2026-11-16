import {useState} from 'react';
import {request} from '../api';
import type {InsightView,DecisionInput,DecisionKind,Suggestion,Finding} from '../insights';
import {ruleNames,typeNames} from '../insights';
import {EvidenceDetails} from './ui';
const pct=(v:number)=>(100*v).toFixed(2)+'%';
function FindingEvidence({value,finding}:{value:InsightView;finding:Finding}){
  const [evidence,setEvidence]=useState<unknown>(null),[error,setError]=useState('');
  return <details className="finding-evidence"><summary onClick={()=>{if(evidence)return;void request('/chats/'+value.chat_id+'/insights/reports/'+value.report!.report_id+'/evidence/'+finding.finding_id).then(setEvidence).catch(e=>setError(e.message));}}>查看依据与规则来源</summary>
    <p>{finding.rule.check_method} · {finding.source.origin==='human_declaration'?'人工登记事实':finding.source.origin==='program_fact'?'程序事实':'程序核对与人工登记'}</p>
    <p>{finding.severity.policy_id} · {finding.severity.reason_code}</p>
    {error?<p role="alert">{error}</p>:<EvidenceDetails label="保存的检查回执" value={evidence||finding.evidence_refs}/>}
  </details>;
}
export function DecisionForm({value,suggestion,busy,onSave}:{value:InsightView;suggestion?:Suggestion;busy:boolean;onSave:(v:DecisionInput)=>void}){
  const [kind,setKind]=useState<DecisionKind|''>(suggestion?'':'note'),[reason,setReason]=useState(''),[confirmed,setConfirmed]=useState(false),[parent,setParent]=useState('');
  const sid=suggestion?.suggestion_id||null;
  const eligible=value.decisions.filter(x=>x.revisable_for.includes(sid));
  const existing=suggestion?eligible.find(x=>x.decision.report_id===value.report!.report_id):null;
  const supersedes=existing?.decision.decision_id||parent||null;
  const disabled=busy||!value.source_current;
  return <form className="decision-form" onSubmit={e=>{e.preventDefault();if(kind&&confirmed&&!disabled){onSave({decision_type:kind,reason,suggestion_id:sid,supersedes_id:supersedes});setConfirmed(false);}}}>
    <h3>{suggestion?'对这项建议作出决定':'记录自主研究决定'}</h3>
    {suggestion?<><p>{suggestion.action}</p><label>决定类型<select aria-label="决定类型" value={kind} disabled={disabled} onChange={e=>setKind(e.target.value as DecisionKind)}><option value="">请选择</option>{(['accepted','deferred','rejected'] as const).map(x=><option key={x} value={x}>{typeNames[x]}</option>)}</select></label></>:<p className="muted">记录本报告的解释边界或研究意见；备注不会改变诊断事实。</p>}
    {existing?<p className="decision-boundary">该建议已有记录；此次保存将追加修订，原文保留。</p>:eligible.length>0&&<label>修订历史决定（可选）<select aria-label="修订历史决定" value={parent} disabled={disabled} onChange={e=>setParent(e.target.value)}><option value="">新增记录，不修订历史</option>{eligible.map(x=><option key={x.decision.decision_id} value={x.decision.decision_id}>{typeNames[x.decision.decision_type]} · 报告v{x.decision.report_version} · {x.decision.reason.slice(0,24)}</option>)}</select></label>}
    <label>决策原因或研究备注<textarea aria-label="决策原因或研究备注" rows={3} maxLength={2000} value={reason} disabled={disabled} onChange={e=>setReason(e.target.value)}/></label>
    <label className="review-confirm"><input type="checkbox" checked={confirmed} disabled={disabled} onChange={e=>setConfirmed(e.target.checked)}/><span>我确认仅记录研究决定，不批准或执行统计</span></label>
    <button className="primary-button" disabled={disabled||!confirmed||!kind||(kind==='note'&&!reason.trim())}>保存研究决定</button>
  </form>;
}
export function InsightsReader({value,error,notice,busy,onGenerate,onSave,onReport,onBack,onSelect,onRefresh}:{value:InsightView|null;error:string;notice:string;busy:boolean;onGenerate:()=>void;onSave:(d:DecisionInput)=>void;onReport:()=>void;onBack:()=>void;onSelect:(id:string)=>void;onRefresh:()=>void}){
  const [tab,setTab]=useState('results');
  const r=value?.report;
  const scope=r?.results.scope;
  const groups=r?.results.descriptive?.groups||r?.results.group_summary.map(g=>({label:scope?.group_labels[g.treatment]||String(g.treatment),n:g.n,proportion:g.outcome_mean}))||[];
  return <div className="insights-surface" data-diagnostic-task={value?.subject_id} data-diagnostic-report={r?.report_id}>
    <header className="report-toolbar"><button onClick={onBack}>← 返回原对话</button><span>研究证据与决定</span><button onClick={onRefresh} disabled={busy}>刷新来源</button></header>
    <article className="insights-content">
      <p className="eyebrow">EVIDENCE & RESEARCH DECISIONS</p><h1>{value?.title||'研究证据诊断'}</h1>
      <p className="insight-boundary">显式检查保存的证据；诊断、建议与研究决定均不授予统计执行权限。</p>
      {error&&<p role="alert" className="insight-error">{error}</p>}{notice&&<p role="status" className="insight-notice">{notice}</p>}
      {!value?<p>当前没有可读取的诊断上下文。请选择合法研究，或核对错误原因；未展示其他任务结果。</p>:<>
        <div className="insight-actions"><button className="primary-button" onClick={onGenerate} disabled={busy}>{r?'重新检查研究证据':value.mode==='preflight'?'检查研究条件':'检查研究证据'}</button><small>仅点击此操作生成诊断；查看与聊天不会自动检查。</small></div>
        {value.history.length>0&&<label className="report-history">诊断报告版本<select aria-label="诊断报告版本" value={r?.report_id||''} disabled={busy} onChange={e=>onSelect(e.target.value)}>{value.history.map(x=><option key={x.id} value={x.id}>报告 v{x.version} · {x.id.slice(0,10)}</option>)}</select></label>}
        {r?<>
          {!value.source_current&&<section role="alert" className="source-stale"><h2>这是历史快照，当前来源已变化</h2><p>{value.source_error}</p><p>保留原报告和决定；重新核验前不能保存新决定。以下数值只代表原快照。</p></section>}
          {r.quality.findings.some(f=>f.status==='issue'||f.status==='unknown')&&<section className="insight-risk-summary"><h2>关键风险与待确认</h2>{r.quality.findings.filter(f=>f.status==='issue'||f.status==='unknown').map(f=><p key={f.finding_id}><span>{ruleNames[f.rule.id]} · {r.quality.status_labels[f.status]}</span>：{f.impact.explanation}</p>)}<small>来自已保存诊断规则；详细依据见“证据质量”。</small></section>}
          <nav className="insight-tabs" aria-label="诊断报告层级">{[['results','研究结果'],['quality','证据质量'],['suggestions','下一步建议'],['decisions','研究决定与历史']].map(([id,label])=><button key={id} aria-current={tab===id?'page':undefined} onClick={()=>setTab(id)}>{label}</button>)}</nav>
          <div className="diagnostic-version">报告 v{r.version} · {value.mode==='preflight'?'执行前只读诊断':'执行后证据诊断'} · 模型请求0次</div>
          {tab==='results'&&<section data-layer="results"><h2>研究结果</h2><p>{r.results.objective||'执行前研究条件检查，尚未形成统计结果。'}</p>
            <p>{scope?.analysis_unit} · {scope?.metric_label} · {scope?.observation_window||'观察窗口待确认'}</p>
            {r.results.status==='restricted'?<p className="source-stale">证据存在冲突，服务限制联合结论；未补用其他Run数字。</p>:groups.length>0?<>
              <table><thead><tr><th>比较组</th><th>样本量</th><th>{scope?.metric_label||'比例'}</th></tr></thead><tbody>{groups.map(g=><tr key={g.label}><td>{g.label}</td><td>{g.n.toLocaleString()}</td><td>{pct(g.proportion)}</td></tr>)}</tbody></table>
              {r.results.effect?<><p className="diagnostic-effect">绝对差 {r.results.effect.pp.toFixed(4)} 个百分点</p><p>原工具95%区间 [{r.results.effect.ci_pp.map(x=>x.toFixed(4)).join(', ')}] 个百分点</p></>:<p>描述性比例差 {r.results.descriptive?.difference_pp.toFixed(4)} 个百分点；没有A/B效果估计或推断区间。</p>}
            </>:<p>尚无可交付统计结果；诊断不会创建新的统计Run。</p>}
            <h3>研究限制</h3>{r.results.limitations.map(x=><p key={x}>{x}</p>)}
            <button className="quiet-button" onClick={onReport}>返回完整研究报告 →</button><EvidenceDetails label="诊断报告的原始结果与Run来源" value={r.results}/>
          </section>}
          {tab==='quality'&&<section data-layer="quality"><h2>证据质量</h2><p>已实现6项规则；不代表所有研究假设成立。未知、不适用与尚未检查均不计作通过。</p>
            {[...r.quality.findings].sort((a,b)=>({issue:0,unknown:1,verified:2,not_applicable:3,not_checked:4}[a.status]-{issue:0,unknown:1,verified:2,not_applicable:3,not_checked:4}[b.status])).map(f=><section className="diagnostic-finding" key={f.finding_id} data-rule={f.rule.id} data-check-status={f.status}><header><h3>{ruleNames[f.rule.id]||f.rule.id}</h3><span className={'check-status '+f.status} data-state={f.status}>{r.quality.status_labels[f.status]}</span></header><p>{f.impact.explanation}</p>{f.result.missing_items.length>0&&<p>待补充：{f.result.missing_items.join('；')}</p>}<FindingEvidence value={value} finding={f}/></section>)}
            <details className="unimplemented"><summary>其余8项规则尚未实现</summary><p>没有执行这些检查，不能解释为通过。</p><p>{r.quality.unimplemented_rules.join('、')}</p></details>
            {r.quality.limitations.map(x=><p className="muted" key={x}>{x}</p>)}
          </section>}
          {tab==='suggestions'&&<section data-layer="suggestions"><h2>下一步研究建议</h2><p>来自保存的确定性诊断映射，最多3项；采纳建议不等于批准新研究。</p>{!r.suggestions.length&&<p>当前检查未生成后续建议。可在“研究决定与历史”记录本报告的解释边界。</p>}{r.suggestions.map(s=><section className="diagnostic-suggestion" key={s.suggestion_id}><h3>{s.action}</h3><p>{s.reason}</p><p>需要补充：{s.required_evidence.join('；')}</p><p>涉及新研究范围时，须另行生成方案并人工审核。</p><EvidenceDetails label="建议的诊断与证据来源" value={s}/><DecisionForm key={r.report_id+s.suggestion_id} value={value} suggestion={s} busy={busy} onSave={onSave}/></section>)}</section>}
          {tab==='decisions'&&<section data-layer="decisions"><h2>相关历史提醒</h2>{!value.reminders.length&&<p className="muted">暂无可可靠对应的历史问题；自主备注只保留历史，不自动解释语义。</p>}{value.reminders.map(x=><section className="decision-reminder" key={x.decision_id} data-reminder-kind={x.kind}><h3>{ruleNames[x.rule_id]} · {r.quality.status_labels[x.current_status||'']||'待核对'}</h3><p>{x.message}</p><EvidenceDetails label="历史决定关联" value={x}/></section>)}
            <DecisionForm key={r.report_id+'note'} value={value} busy={busy} onSave={onSave}/>
            <h2>研究决策历史</h2>{!value.decisions.length&&<p>尚无研究决定；只有明确提交才会保存。</p>}{[...value.decisions].reverse().map(x=><section className="decision-history-item" key={x.decision.decision_id} data-decision-id={x.decision.decision_id}><header><h3>{typeNames[x.decision.decision_type]}</h3><small>报告v{x.decision.report_version} · {new Date(x.decision.created_at).toLocaleString('zh-CN')}</small></header><p>{x.decision.reason||'未填写原因'}</p>{x.decision.suggestion_action&&<p className="muted">当时建议：{x.decision.suggestion_action}</p>}{x.superseded_by&&<p>已有后继修订，原决定保留。</p>}{x.decision.supersedes_id&&<p>明确修订历史决定，未覆盖原文。</p>}{!x.origin_verified&&<p role="alert">{x.origin_error}</p>}<small>用户主动提交 · 无统计执行权限 · 不代表当前证据</small><EvidenceDetails label="决定来源与修订关系" value={x}/></section>)}
          </section>}
          <EvidenceDetails label="诊断快照与完整技术来源" value={r}/>
        </>:<section className="insight-empty"><h2>尚未生成研究诊断</h2><p>研究结果和聊天不会自动生成诊断。点击上方检查，读取本任务真实数据、合同、计划和Run；不会进行新的统计计算。</p></section>}
      </>}
    </article>
  </div>;
}
