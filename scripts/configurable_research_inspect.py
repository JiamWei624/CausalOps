"""Read-only scorer for the configurable fixed browser acceptance (never performs actions)."""
import json,sys
from pathlib import Path
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace,digest
from causalops.general.service import GeneralWorkspace
from causalops.application.automation_results import snapshot
co=ResearchService(AssistantWorkspace(GeneralWorkspace(Path(sys.argv[1])))).automation_v2()
with co.ws.connection() as c:
    ids=[r[0] for r in c.execute('SELECT id FROM automation_v2_tasks ORDER BY created,id')]
    events=[dict(zip(['id','task_id','upload_id','action','origin','error_class','at'],r)) for r in c.execute('SELECT * FROM configurable_user_events ORDER BY created,rowid')]
items=[]
for tid in ids:
    v=snapshot(co,tid);t=v['task']
    items.append(dict(id=tid,status=t['status'],reason=t['reason'],session_id=t['session_id'],plan=t['plan'],plan_sha=t['plan_sha'],steps=v['steps'],evidence=v['evidence'],report=v['report'],binding_error=v['binding_error'],budget=v['budget']))
with co.ws.connection() as db:
    names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    protected={n:digest([list(r) for r in db.execute('SELECT * FROM '+n)]) for n in ('analysis_runs','exploration_runs','automation_v2_approvals','automation_v2_steps')}
    reports=[json.loads(r[0]) for r in db.execute('SELECT body FROM diagnostic_reports')] if 'diagnostic_reports' in names else []
    decisions=[json.loads(r[0]) for r in db.execute('SELECT body FROM research_decisions')] if 'research_decisions' in names else []
print(json.dumps(dict(tasks=items,events=events,protected=protected,diagnostic_reports=reports,decisions=decisions),ensure_ascii=False,allow_nan=False))
