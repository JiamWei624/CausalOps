"""Read-only task catalog and explicit selection for the Streamlit workspace."""
from urllib.parse import urlencode
from causalops.application.automation_results import snapshot, STATES
from causalops.general.service import DesignError

MAIN_NAV = [
    ('home','工作空间','home'),('configure','数据与研究配置','tune'),
    ('review','方案审核','verified_user'),('execution','研究执行','play_arrow'),
    ('results','研究结果','bar_chart'),('evidence','证据诊断','fact_check'),
    ('decisions','研究决定','history'),
]
AUX_NAV = [
    ('assistant','原单次研究','assignment'),('analysis','专业分析','functions'),
    ('history','历史记录','list'),('examples','公开案例','view_column'),
    ('settings','模型与隐私','settings'),('guide','使用说明','help'),('status','系统状态','monitor_heart'),
]


def study_catalog(co):
    with co.ws.connection() as db:
        ids = [r[0] for r in db.execute('SELECT id FROM automation_v2_tasks ORDER BY created DESC,id DESC')]
    rows = []
    for tid in ids:
        task = co.task(tid); p = task['plan']; sc = p['scope']
        label = sc['metric']+' · '+sc['window']+' · '+STATES.get(task['status'],task['status'])+' · '+tid[:8]
        stable_label=sc['metric']+' · '+sc['window']+' · v'+str(p['version'])+' · '+tid[:8]
        rows.append(dict(id=tid,task=task,label=label,selector_label=stable_label,title=p['objective'],metric=sc['metric'],window=sc['window'],status=task['status'],version=p['version']))
    return rows


def resolve_study(co, tid):
    if not tid:
        return None
    if tid not in {r['id'] for r in study_catalog(co)}:
        raise DesignError('所选研究不属于当前工作区，未使用其他任务替代。')
    return snapshot(co, tid)


def study_url(tid, route='results'):
    return '?'+urlencode(dict(route=route,automation=tid))
