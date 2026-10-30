"""Versioned, deterministic business interpretation; no model or source-data I/O."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
from typing import Literal
import pandas as pd
from pydantic import BaseModel,ConfigDict,Field
from causalops.schemas import ResultBundle

VERSION='business_interpretation_v2'
ROOT=Path(__file__).resolve().parents[3]/'artifacts/interpretations'

class MetricDefinition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label: str=Field(min_length=1,max_length=120)
    unit: str=Field(default='结果指标单位',min_length=1,max_length=40)
    kind: Literal['binary','continuous','count','unknown']='unknown'
    direction: Literal['higher_is_better','lower_is_better','neutral']='neutral'
    ratio_scale: bool=False
    window: str=Field(default='当前登记的观察范围',max_length=220)
    source: str=Field(default='未登记指标业务定义',max_length=500)


def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def collect_interpretation_inputs(frame,spec,context=None):
    context=context or {};required=list(dict.fromkeys([spec.treatment,spec.outcome,*spec.covariates]))
    data=frame[required].dropna()
    y=pd.to_numeric(data[spec.outcome],errors='coerce');t=data[spec.treatment]
    binary=bool(len(y) and y.notna().all() and y.isin([0,1]).all())
    groups=[]
    if t.isin([0,1]).all():
        for value in [0,1]:
            s=y[t==value]
            if len(s):groups.append({'treatment':value,'n':int(len(s)),'outcome_mean':float(s.mean())})
    definition=context.get('metric_definition')
    metric=MetricDefinition.model_validate(definition).model_dump() if definition else None
    if metric and metric['kind']=='binary' and not binary:raise ValueError('指标登记为二元结果，但分析样本含非二元取值。')
    return {'schema_version':'interpretation_inputs_v1','outcome_binary_observed':binary,
            'complete_case_rows':len(data),'raw_group_summary':groups,
            'baseline_scope':'same_complete_case_raw_groups' if spec.candidate_methods[0].value=='ab_test' else 'input_complete_case_descriptive_only',
            'metric_definition':metric}


def public_metric_definition(case_id):
    if case_id.startswith('hillstrom_'):
        binary=case_id.endswith('_visit')
        return MetricDefinition(label='两周网站访问概率' if binary else '两周人均支出',unit='概率' if binary else '美元/客户',
              kind='binary' if binary else 'continuous',direction='higher_is_better',ratio_scale=True,window='邮件随机分配后的两周',
              source='https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html').model_dump()
    if case_id.startswith('nsw_'):
        return MetricDefinition(label='1978年收入',unit='原始收入单位/参与者',kind='continuous',direction='higher_is_better',ratio_scale=True,
              window='1978年',source='https://users.nber.org/~rdehejia/data/.nswdata3.html').model_dump()
    if case_id.startswith('student_'):
        return MetricDefinition(label='期末成绩',unit='分',kind='continuous',direction='higher_is_better',window='该课程期末',
              source='https://archive.ics.uci.edu/dataset/320/student+performance').model_dump()
    return None


def _compute(bundle,inputs):
    spec=bundle.spec;e=bundle.estimate;est=bundle.evidence.get('estimator',{});context=bundle.evidence.get('study_context',{})
    inputs=inputs or {};md=inputs.get('metric_definition') or context.get('metric_definition')
    binary=bool(inputs.get('outcome_binary_observed',est.get('outcome_binary',False)))
    if md:metric=MetricDefinition.model_validate(md)
    else:metric=MetricDefinition(label=spec.outcome,kind='binary' if binary else 'unknown',unit='概率' if binary else '结果指标单位',
                                window=context.get('sample_note','当前登记的观察范围')[:220])
    if metric.kind=='binary' and inputs and not binary:raise ValueError('二元指标声明与已保存的分析样本不一致。')
    groups=inputs.get('raw_group_summary',est.get('raw_group_summary',[]))
    means={int(g['treatment']):float(g['outcome_mean']) for g in groups if g.get('treatment') in (0,1) and math.isfinite(float(g['outcome_mean']))}
    binary=metric.kind=='binary'
    is_ab=bundle.plan.selected_method.value=='ab_test'
    raw_comparable=is_ab and inputs.get('baseline_scope')=='same_complete_case_raw_groups' and all(k in means for k in (0,1))
    if raw_comparable and e and not math.isclose(means[1]-means[0],e.estimate,rel_tol=1e-8,abs_tol=1e-10):
        raise ValueError('原始分组均值差与A/B主估计不一致，禁止生成相对提升。')
    f=lambda x:format(x,'.4g')
    def val(x):return f'{x*100:.2f}%' if binary else f'{f(x)} {metric.unit}'
    baseline={'available':all(k in means for k in (0,1)),'scope':'未调整的描述性分组均值','control_mean':means.get(0),'treated_mean':means.get(1)}
    baseline_text=(f'结果期未调整参考水平（非处理前基线）：对照组{val(means[0])}，处理组{val(means[1])}。'+('本次A/B估计使用相同完整案例。' if raw_comparable else '两组原始均值不是调整后的预测值。')) if baseline['available'] else '本运行未记录可用的分组基线，不能补写“从多少提高到多少”。'
    if baseline['available'] and not raw_comparable:
        baseline_text=(f'输入完整案例中，处理字段取0的未调整均值为{val(means[0])}，取1为{val(means[1])}。'
                       '这是按当前处理状态分组，不自动等于固定处理组和对照组，也不是处理前基线；不是调整后的预测值。')
    magnitude={'estimate':None if not e else e.estimate,'confidence_interval':None if not e else e.confidence_interval,'relative_change_pct':None,'relative_ci':None,'scaled_per_1000':None,'scaled_ci':None}
    if not e:
        effect_text='本次没有有效估计，不能给出提升幅度。';relative='未生成相对变化。';scale='未生成规模换算。'
    else:
        relation='估计平均差异' if bundle.claim_level.value=='identified_causal' else '在所列假设下的受限估计差异' if bundle.claim_level.value=='reduced_form' else '条件相关差异'
        effect_text=f'{metric.label}的{relation}为{f(e.estimate*100) if binary else f(e.estimate)} {"个百分点" if binary else metric.unit}。'
        if e.confidence_interval:
            lo,hi=e.confidence_interval
            effect_text+=f'95%置信区间为[{f(lo*100) if binary else f(lo)}, {f(hi*100) if binary else f(hi)}]{"个百分点" if binary else metric.unit}。'
        relative='当前估计不具备同口径、正值且适合比例解释的基准，不计算相对提升；不能将调整系数除以原始分组均值。'
        if raw_comparable and means[0]>0 and (metric.kind in ('binary','count') or metric.ratio_scale):
            magnitude['relative_change_pct']=e.estimate/means[0]*100
            relative=f'相对对照组基线的样本点估计变化为{f(magnitude["relative_change_pct"])}%；这是相对变化，不是百分点。未计算该比值的置信区间。'
        scale='本估计不提供可直接解释为新增人数或业务总收益的规模换算。'
        if raw_comparable and binary:
            magnitude['scaled_per_1000']=e.estimate*1000
            magnitude['scaled_ci']=[v*1000 for v in e.confidence_interval] if e.confidence_interval else None
            scale=f'按相同概率差标准化到每千条分析观测，约{"多" if e.estimate>=0 else "少"}{f(abs(e.estimate)*1000)}条出现该二元结果；这是样本尺度换算，不是已实际新增的人数或对新总体的预测。'
        elif raw_comparable and metric.kind in ('count','continuous') and metric.direction!='neutral' and metric.unit!='结果指标单位':
            magnitude['scaled_per_1000']=e.estimate*1000
            magnitude['scaled_ci']=[v*1000 for v in e.confidence_interval] if e.confidence_interval else None
            total_unit=metric.unit.split('/')[0]
            scale=f'将同样平均差异乘以千条分析观测，结果总差异约为{f(e.estimate*1000)} {total_unit}；只作标准化换算，不代表已落地总收益。'
    synthetic=bundle.evidence.get('data',{}).get('kind')=='synthetic'
    bounded='合成数据仅用于验证实现，不能声称真实业务增长。' if synthetic else '结果适用于当前样本、设计和观察范围；不是本工具上线后已创造的业务收益。'
    if bundle.claim_level.value in ('associational','descriptive'):
        bounded+='当前只能作关联或描述解释，不能说干预导致改善。'
    elif bundle.claim_level.value=='identified_causal':bounded+='因果解释以已记录的分配机制和识别假设成立为前提。'
    else:bounded+='保留准实验识别假设和诊断限制，不可升级为确定因果。'
    bounded+='观察到的统计差异不等于已解释其机制。'
    if e and e.confidence_interval and e.confidence_interval[0]<=0<=e.confidence_interval[1]:
        meaning='区间包含零，当前结果尚不能排除无差异；不能据点估计确定存在收益，也不能据此断言没有效果。'
    elif e:
        if bundle.claim_level.value in ('associational','descriptive'):meaning=f'样本显示{metric.label}存在条件差异，可形成待验证的领域假设，不能据此判断干预有益或有害。'
        elif metric.direction=='neutral':meaning='已得到量化差异，但尚未登记指标的业务方向，不能自动称为改善。'
        else:
            desired=e.estimate>0 if metric.direction=='higher_is_better' else e.estimate<0
            meaning=f'点估计方向与登记的业务目标{"一致" if desired else "相反"}；统计差异是否值得行动仍取决于成本、风险和实际决策阈值。'
    else:meaning='没有可解释的数值结果。'
    if bundle.claim_level.value in ('associational','descriptive'):
        action='建议核对处理选择、时序和混杂，并设计可辩护的随机或准实验；当前不建议据关联系数直接扩量或停止干预。'
    elif synthetic:action='建议用已知真值、零效应及假设失败场景继续检验计算与主张降级，再用于经过审核的真实场景。'
    else:action='建议结合最小有意义差异、实施成本和风险确定是否继续验证；当前结果不支持未经计算的人群优先级、长期收益或全量推广承诺。'
    cost='尚未登记毛利、实施成本、退货与风险成本，未计算净利润、ROI或Agent节省工时。'
    return {'version':VERSION,'run_id':bundle.run_id,'bundle_sha256':digest(bundle.model_dump(mode='json')),'claim_level':bundle.claim_level.value,
            'metric':metric.model_dump(),'baseline':baseline,'magnitude':magnitude,'inputs':inputs,
            'texts':{'baseline':baseline_text,'magnitude':effect_text,'relative':relative,'scale':scale,'meaning':meaning,'action':action,'boundary':bounded,'cost':cost}}


def interpret_run(bundle,inputs=None,use_saved=True):
    if inputs is None and use_saved:
        p=ROOT/bundle.run_id/(VERSION+'.json')
        if p.is_file():
            stored=json.loads(p.read_text(encoding='utf-8'));signature=stored.pop('interpretation_id',None)
            if digest(stored)!=signature or stored['bundle_sha256']!=digest(bundle.model_dump(mode='json')):raise ValueError('解释证据校验失败。')
            expected=json.loads(json.dumps(_compute(bundle,stored['inputs']),ensure_ascii=False,allow_nan=False))
            if expected!=stored:raise ValueError('解释证据与当前计算规则不一致，须建立新解释版本。')
            return {**stored,'interpretation_id':signature}
    if inputs is None and use_saved:
        legacy=ROOT/bundle.run_id/'business_interpretation_v1.json'
        if legacy.is_file():
            old=json.loads(legacy.read_text(encoding='utf-8'));sig=old.pop('interpretation_id',None)
            if digest(old)!=sig or old['bundle_sha256']!=digest(bundle.model_dump(mode='json')):raise ValueError('旧版解释证据校验失败。')
            inputs=old['inputs']
    result=_compute(bundle,inputs if inputs is not None else bundle.evidence.get('interpretation_inputs'))
    result=json.loads(json.dumps(result,ensure_ascii=False,allow_nan=False))
    result['interpretation_id']=digest(result);return result


def persist_interpretation(bundle,inputs=None):
    value=interpret_run(bundle,inputs,use_saved=False);p=ROOT/bundle.run_id/(VERSION+'.json');p.parent.mkdir(parents=True,exist_ok=True)
    if p.is_file() and json.loads(p.read_text(encoding='utf-8'))!=value:raise ValueError('同一解释版本已有不同内容，拒绝覆盖。')
    if not p.exists():p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return p


def business_sections(bundle):
    x=interpret_run(bundle);t=x['texts']
    return [('基线：原来是什么水平',[t['baseline']]),('幅度：改变多少',[t['magnitude'],t['relative']]),
            ('实际含义：如何理解',[t['scale'],t['meaning'],t['boundary']]),('行动建议：下一步做什么',[t['action'],t['cost']])]