from __future__ import annotations
import hashlib,json,math,statistics,time
from pathlib import Path
import numpy as np
from causalops.results.interpretation import interpret_run
from causalops.results.evidence import build_interpreted_run_evidence,canonical_sha256


def semantic_result(bundle):
    x=interpret_run(bundle)
    return {'spec':bundle.spec.model_dump(mode='json'),'estimate':bundle.estimate.model_dump(mode='json') if bundle.estimate else None,
            'claim_level':bundle.claim_level.value,'diagnostics':[d.model_dump(mode='json') for d in bundle.diagnostics],
            'warnings':bundle.warnings,'data':bundle.evidence['data'],'interpretation':{k:x[k] for k in ['metric','baseline','magnitude','texts']}}


def score_completion(task,result,record,turn,oracle=None):
    b=result.bundle;x=interpret_run(b);snapshot=build_interpreted_run_evidence(b)
    trace=json.loads(result.trace_path.read_text(encoding='utf-8'))
    html=result.html_report_path.read_text(encoding='utf-8');md=result.report_path.read_text(encoding='utf-8')
    refs=set(turn['answer']['citation_ids']);available={f['evidence_id'] for f in snapshot['facts']}
    checks={
      'data_fingerprint_matches':b.evidence['data']['fingerprint_sha256']==task.data_sha256,
      'approved_revision_and_run_bound':record.run_id==b.run_id and record.status=='completed' and bool(record.revision_id) and b.evidence['execution_authorization']['scope']==task.scope,
      'finite_estimate_and_uncertainty':b.estimate is not None and all(math.isfinite(v) for v in [b.estimate.estimate,b.estimate.standard_error,*b.estimate.confidence_interval]),
      'diagnostics_present':bool(b.diagnostics),
      'four_business_sections':all(k in html and k in md for k in ['基线：','幅度：','实际含义：','行动建议：']),
      'html_and_markdown_exported':len(html)>1000 and md.startswith('# CausalOps'),
      'derived_interpretation_evidence_saved':bool(list(result.report_path.parent.glob(f'interpretation-{b.run_id}-*.json'))),
      'trace_complete_and_run_bound':trace['run_id']==b.run_id and {s['tool'] for s in trace['steps']}=={'inspect_dataset','route_identification','execute_analysis','write_markdown_report','write_html_report'} and all(s['status']=='success' for s in trace['steps']),
      'local_answer_citations_exist':bool(refs) and refs<=available and {'E004','E020'}<=refs,
      'local_answer_did_not_call_model':not turn['answer']['used_model'] and turn['answer']['data_rows_transmitted'] is False,
      'interpretation_claim_not_upgraded':x['claim_level']==b.claim_level.value,
      'cost_and_observation_limits_present':'ROI' in x['texts']['cost'] and ('业务收益' in x['texts']['boundary'] or task.kind=='synthetic' and '真实业务' in x['texts']['boundary']),
    }
    if task.task_id in {'student_mat','synthetic_did_bad_trend'}:checks['expected_claim_downgrade']=b.claim_level.value=='associational'
    if task.task_id=='synthetic_null_ab':checks['zero_effect_not_called_positive']=b.estimate.confidence_interval[0]<=0<=b.estimate.confidence_interval[1] and '不能据此断言没有效果' in x['texts']['meaning']
    if oracle is not None:checks['independent_numeric_reference']=abs(b.estimate.estimate-oracle)<1e-7
    return {'checks':checks,'passed':all(checks.values()),'passed_items':sum(checks.values()),'items':len(checks),
            'semantic_sha256':canonical_sha256(semantic_result(b)),
            'not_a_semantic_business_judgement':True}


def summarize_pairs(rows,seed=20261030):
    rng=np.random.default_rng(seed);output=[]
    for task_id in dict.fromkeys(r['task_id'] for r in rows):
        relevant=[r for r in rows if r['task_id']==task_id and not r['warmup']]
        pairs=[]
        for p in sorted({r['pair'] for r in relevant}):
            pair={r['condition']:r for r in relevant if r['pair']==p}
            if len(pair)==2 and all(r['passed'] for r in pair.values()):pairs.append(pair)
        if not pairs:
            output.append({'task_id':task_id,'complete_pairs':0});continue
        script=np.array([p['script']['seconds'] for p in pairs]);agent=np.array([p['agent']['seconds'] for p in pairs]);delta=agent-script
        boot=np.median(delta[rng.integers(0,len(delta),size=(4000,len(delta)))],axis=1)
        output.append({'task_id':task_id,'complete_pairs':len(pairs),'script_median_seconds':float(np.median(script)),
                       'agent_median_seconds':float(np.median(agent)),'agent_minus_script_median_seconds':float(np.median(delta)),
                       'paired_delta_bootstrap_95_interval':np.quantile(boot,[.025,.975]).tolist(),
                       'paired_median_time_ratio_agent_over_script':float(np.median(agent/script)),
                       'script_iqr_seconds':np.quantile(script,[.25,.75]).tolist(),'agent_iqr_seconds':np.quantile(agent,[.25,.75]).tolist(),
                       'semantic_matches':sum(p['script']['score']['semantic_sha256']==p['agent']['score']['semantic_sha256'] for p in pairs),
                       'interpretation':'machine_only_expert_prewritten_script_comparator_not_human_time_saved'})
    return output