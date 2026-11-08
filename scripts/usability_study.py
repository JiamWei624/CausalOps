"""Local study preparation and metadata-only export. Never runs statistics or enrolls users."""
from __future__ import annotations
import argparse,csv,hashlib,io,json,sqlite3
from pathlib import Path

PUBLIC_SHA='7d5a3a8b0f87b44aead0e312d960653482ea62f744fc390fe3364c64a7f39988'
SOURCE='https://www.openintro.org/data/index.php?data=gender_discrimination'
DESIGN='https://openintro-ims.netlify.app/foundations-randomization'

def stable_write(path,content):
    path=Path(path);body=content if isinstance(content,bytes) else content.encode('utf8')
    if path.exists():
        if path.read_bytes()!=body:raise ValueError('既有试用文件内容不同，拒绝覆盖：'+path.name)
        return
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)

def synthetic_csv():
    out=io.StringIO(newline='');w=csv.writer(out,lineterminator='\n');w.writerow(['subject','arm','completed','retained'])
    for i in range(24):
        arm='standard' if i<12 else 'variant';j=i%12
        w.writerow([i,arm,'yes' if j<(6 if arm=='standard' else 9) else 'no','yes' if j<(4 if arm=='standard' else 6) else 'no'])
    return out.getvalue().encode()

def prepare(root,public_csv):
    root=Path(root);body=Path(public_csv).read_bytes()
    if hashlib.sha256(body).hexdigest()!=PUBLIC_SHA:raise ValueError('公开数据指纹与已核对版本不一致；未准备试用包。')
    public=root/'participant';unknown=synthetic_csv()
    stable_write(public/'dataset-A.csv',body);stable_write(public/'dataset-B.csv',unknown)
    meta={'schema':'causalops-usability-materials-v1','validated_development_product':'9dc0954aab4aaab892823c3995d45bd72733efbb','validated_development_source_fingerprint':'1687cdd344a5f89192bfd4469211be089e629788e01068a271ec60205f16bf35','datasets':[
        {'task':'A','filename':'dataset-A.csv','sha256':PUBLIC_SHA,'source':SOURCE,'design_source':DESIGN,'license':'OpenIntro R package GPL-3; attribution and license URL in participant guide','privacy':'public two-field anonymized teaching table'},
        {'task':'B/C','filename':'dataset-B.csv','sha256':hashlib.sha256(unknown).hexdigest(),'source':'deterministic synthetic fixture, 24 independent fictional records','assignment':'unknown','license':'project-generated synthetic data; no real users'}]}
    stable_write(public/'data-manifest.json',json.dumps(meta,ensure_ascii=False,indent=2))
    templates=Path(__file__).resolve().parents[1]/'docs/product/configurable-research/usability'
    for name in ['PARTICIPANT.md','CONSENT.md','DATA_NOTICE.md']:
        if (templates/name).exists():stable_write(public/name,(templates/name).read_bytes())
    # Empty records are not fictitious participants or failed human attempts.
    stable_write(root/'records/human-results.json',json.dumps({'schema':'causalops-human-study-v1','status':'not_executed','participants':[],'attempts':[],'human_completion_rate':None,'reason':'No recruited, consented participants yet. Owner preview and scripted browsers must remain separate.'},ensure_ascii=False,indent=2))
    fields={
        'participants.csv':['participant_code','actor_type','consent_record_reference','analysis_experience','prior_data_familiarity','prior_product_use','task_order','allowed_recording','external_model_consent'],
        'attempts.csv':['participant_code','actor_type','task','attempt','mode','consented','start_iso','end_iso','elapsed_seconds','effective_actions','invalid_actions','help_count','operator_interventions','misconfiguration_count','backtrack_count','error_categories','recovered','report_found','understanding','completion','task_id','report_id','source_commit','notes_reference'],
        'interactions.csv':['participant_code','actor_type','task','sequence','at_iso','event_type','control_role','control_label_redacted','valid','help_level','error_category','duration_ms'],
        'issues.csv':['issue_id','observed_at','actor_type','task','evidence_reference','problem','impact','priority','frequency_observed','status','proposed_action']}
    for name,header in fields.items():
        s=io.StringIO(newline='');csv.writer(s,lineterminator='\n').writerow(header);stable_write(root/'records'/name,s.getvalue())
    return meta

def export_events(workspace):
    """Read only existing tables, exclude data rows, text, credentials, and model payloads."""
    database=Path(workspace).resolve()/'research.sqlite3'
    if not database.is_file():raise ValueError('尚无试用数据库；没有创建空数据库或假事件。')
    queries={
        'milestones':('configurable_user_events','SELECT id,task_id,action,origin,error_class,created FROM configurable_user_events ORDER BY created,rowid',['id','task_id','action','origin','error_class','at']),
        'tasks':('automation_v2_tasks','SELECT id,status,plan_sha FROM automation_v2_tasks',['task_id','status','plan_sha']),
        'step_events':('automation_v2_events','SELECT task_id,step_id,event,created FROM automation_v2_events ORDER BY seq',['task_id','step_id','event','at']),
        'model_requests':('automation_v2_model_requests','SELECT id,task_id,purpose,status,receipt FROM automation_v2_model_requests ORDER BY created',['id','task_id','purpose','status','receipt'])}
    result={'schema':'causalops-study-metadata-v1','read_only':True,'actor_inference':'none; local_user does not prove a recruited human','effective_click_count':None,'full_user_time':None}
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for key,(table,sql,cols) in queries.items():
            rows=[dict(zip(cols,r)) for r in db.execute(sql)] if table in tables else []
            if key=='model_requests':
                allowed={'status','status_code','model','input_tokens','output_tokens','total_tokens','latency_ms','will_retry','estimated_cost_cny'}
                for r in rows:r['receipt']={k:v for k,v in json.loads(r['receipt'] or '{}').items() if k in allowed}
            result[key]=rows
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--root',type=Path,required=True);p.add_argument('--public-csv',type=Path,required=True)
    p=sub.add_parser('export-events');p.add_argument('--workspace',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':result=prepare(args.root,args.public_csv);print(json.dumps(result,ensure_ascii=False,indent=2))
    else:stable_write(args.out,json.dumps(export_events(args.workspace),ensure_ascii=False,indent=2));print('已导出脱敏里程碑；不推断真人、点击数或任务总耗时。')

if __name__=='__main__':main()
