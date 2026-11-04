from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,os
import pandas as pd
from causalops.schemas import CausalSpec
from causalops.demo_domains import synthetic_scenario
from causalops.execution import _data_fingerprint
from causalops.results.interpretation import public_metric_definition

TASK_IDS=['hillstrom_men_visit','hillstrom_men_spend','student_mat','synthetic_cuped','synthetic_null_ab','synthetic_did_bad_trend']
TITLES={'synthetic_cuped':'合成实验：CUPED调整与单位解释','synthetic_null_ab':'合成实验：零效应与不确定性','synthetic_did_bad_trend':'合成政策：前趋势失败后的降级'}

@dataclass
class AnalysisTask:
    task_id: str
    title: str
    frame: pd.DataFrame
    spec: CausalSpec
    kind: str
    scope: str
    source: str
    context: dict
    data_sha256: str
    source_file_sha256: str | None=None
    known_effect: float | None=None

    def public_description(self):
        return {'task_id':self.task_id,'title':self.title,'rows':len(self.frame),'method':self.spec.candidate_methods[0].value,
            'kind':self.kind,'scope':self.scope,'data_sha256':self.data_sha256,'source_file_sha256':self.source_file_sha256,
            'source':self.source,'question':self.spec.question,'metric_definition':self.context.get('metric_definition'),
            'known_effect':self.known_effect,'questionnaire':['填写主估计及区间','判断允许的结论等级','解释单位与提出后续行动']}


def load_task(task_id,seed=641227):
    if task_id not in TASK_IDS:raise ValueError('任务未在白名单登记。')
    if task_id.startswith('synthetic_'):
        generator=task_id.removeprefix('synthetic_');frame,spec,tau=synthetic_scenario(generator,seed)
        md={'label':'合成结果指标','unit':'合成指标单位','kind':'continuous','direction':'higher_is_better','ratio_scale':False,
            'window':'生成器登记的分析窗口','source':'固定种子的合成生成器；不代表真实业务效果'}
        return AnalysisTask(task_id,TITLES[task_id],frame,spec,'synthetic','approved','seeded synthetic generator',
               {'metric_definition':md,'sample_note':'合成验收任务；已知生成过程不外推业务。'},_data_fingerprint(frame),known_effect=tau)
    catalog_path=Path(os.environ.get('CAUSALOPS_PUBLIC_CATALOG', 'data/public/prepared/catalog.json')).resolve()
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    item=next(x for x in catalog if x['id']==task_id);allowed=catalog_path.parent;p=(allowed/item['path']).resolve()
    if not p.is_relative_to(allowed):raise ValueError('公开数据路径越出登记目录。')
    file_sha=hashlib.sha256(p.read_bytes()).hexdigest()
    if file_sha!=item['sha256']:raise ValueError('公开数据校验和不符。')
    frame=pd.read_parquet(p);spec=CausalSpec.model_validate(item['spec'])
    return AnalysisTask(task_id,item['title'],frame,spec,'user_provided',item['scope'],item['source'],
            {'metric_definition':public_metric_definition(task_id),'sample_note':item['description']},_data_fingerprint(frame),file_sha)

def validate_task_reference(description):
    task=load_task(description['task_id'])
    if task.data_sha256!=description['data_sha256']:
        raise ValueError('当前数据与计时任务参考指纹不一致，请先重建任务目录。')
    return task.data_sha256
