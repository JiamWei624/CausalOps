"""Task-facing metadata and structural readiness; declarations never become proof."""
from __future__ import annotations
from pydantic import ValidationError
from causalops.assistant.service import check_question,PROTECTED
from causalops.assistant.contracts import REGISTRY
from causalops.general.service import DesignError

LABELS={'analysis_unit':'一行所代表的分析单位','outcome':'结果字段','treatment':'处理或分组字段','entity':'实体标识字段','time':'观测日期','treatment_time':'首次处理日期','control_value':'对照组取值','treated_value':'处理组取值','predictors':'自变量','covariates':'处理前协变量','metric':'指标口径','numeric':'数值字段','instruments':'工具变量','running':'阈值运行变量','cutoff':'阈值','cohort':'首次处理期'}

def public_contract_context(service,flow):
    row=service.contracts.bound(flow)
    if not row:return {'status':'not_registered','meaning':'未登记数据口径。不能猜测分析单位、随机化或字段含义。'}
    body=row['body'];keys=('analysis_unit','structure','purpose','entity','time','treatment_time','outcome','treatment','predictors','covariates','instruments','running','cutoff','cohort','control_value','treated_value','metric_label','metric_unit','metric_kind','metric_window')
    result={k:body[k] for k in keys if body.get(k) not in (None,'',[])}
    # Context describes declared metadata only; method-keyed gold fixtures and free notes stay local.
    assignments={v['assignment'] for v in body['method_facts'].values() if v.get('assignment') in ('randomized','observational')}
    result['assignment_declaration']=next(iter(assignments)) if len(assignments)==1 else 'unknown'
    result['field_definitions']=[]
    for field in body['fields']:
        try:check_question(field['meaning']) if field['meaning'] else None;check_question(field['unit']) if len(field['unit'])>1 else None
        except ValueError:
            result['field_definitions'].append({k:field[k] for k in ('field','role','timing')})
            continue
        result['field_definitions'].append({k:field[k] for k in ('field','meaning','unit','role','timing')})
    return {'status':'human_registered','version':row['version'],'definition':result,'evidence_type':'human_declaration_not_empirical_validation','scope':'current dataset and new plans only; prior results remain bound to their source plan','rule':'可引用字段名与登记口径；不得写入任何reviewed/declared/assignment事实，不得声称假设已验证。'}

def check_declared_roles(plan,context):
    definition=context.get('definition',{}) if context else {}
    target=definition.get('outcome')
    if target and plan.steps and all(step.config.get('method')=='descriptive' for step in plan.steps):
        if not any(target in step.config.get('numeric',[])+step.config.get('categorical',[]) for step in plan.steps):raise DesignError('描述计划未覆盖已登记的目标指标，请补充该字段或由使用者调整目标。')
    for step in plan.steps:
        cfg=step.config
        if cfg.get('outcome') and cfg.get('outcome') in cfg.get('covariates',[])+cfg.get('predictors',[]):raise DesignError('结果字段不能同时作为本次模型的解释或调整变量。')
        if cfg.get('method')=='descriptive':continue
        for key in ('outcome','treatment','entity','time','treatment_time'):
            if cfg.get(key) and definition.get(key) and cfg[key]!=definition[key]:raise DesignError('候选的'+LABELS[key]+'与已登记口径不同，请按已登记字段修复或由使用者先修改字典。')
        for key in ('predictors','covariates'):
            if cfg.get(key) and definition.get(key) and set(cfg[key])!=set(definition[key]):raise DesignError('候选的'+LABELS[key]+'偏离已登记的本轮变量集合；请不要自行增删。')
        from causalops.application.variable_timing import require_eligible
        require_eligible(cfg, {**definition, 'fields':definition.get('field_definitions',[])})


def plan_readiness(service,flow,plan):
    errors=[];required=[];row=service.contracts.bound(flow);body=row['body'] if row else {};steps=plan['steps'];frame=service.ws.load_upload(flow['request']['data']['upload_id'])
    from causalops.application.research_semantics import issue
    semantics=issue(flow['request'].get('user_question',flow['request']['question']),body,[step['config'] for step in steps])
    if semantics:errors.append(semantics)
    from causalops.application.plan_scope import check_steps, ordered_methods
    try:check_steps(flow['request'].get('analysis_scope'),steps)
    except ValueError as exc:errors.append(str(exc))
    order=ordered_methods(flow['request'].get('user_question',flow['request']['question']))
    if order and [s['config']['method'] for s in steps]!=order:errors.append('方案缺少请求的分析步骤或顺序不符。')
    from causalops.assistant.service import Plan
    try:check_declared_roles(Plan.model_validate(plan),public_contract_context(service,flow))
    except ValueError as exc:errors.append(str(exc))
    for i,step in enumerate(steps):
        method=step['config']['method'];spec=REGISTRY[method];facts=body.get('method_facts',{}).get(method,{})
        try:
            d=spec.design_type.model_validate({**step['config'],**facts})
            if spec.tool=='exploration':
                from causalops.general.exploration import validate_frame
                validate_frame(frame,d)
        except ValidationError as exc:
            for e in exc.errors():
                key=str(e['loc'][0]);errors.append('步骤'+str(i+1)+'：请补充或修正'+LABELS.get(key,key)+'。')
        except ValueError as exc:errors.append('步骤'+str(i+1)+'：'+str(exc))
        from causalops.orchestration.method_research import FACTS
        for name in FACTS.get(method,[]):
            value=facts.get(name)
            good=value=='randomized' if name=='assignment' else bool(isinstance(value,str) and len(value.strip())>=12) if name=='design_evidence' else value is True
            if not good:required.append({'step':i,'method':method,'fact':name,'meaning':'须有依据后人工确认；不是通过勾选即可验证的结论。'})
    return {'configuration_ready':not errors,'errors':list(dict.fromkeys(errors)),'human_review_required':required,'state':'needs_configuration' if errors else 'needs_human_facts' if required else 'ready_for_review','next_action':'完善数据字典后重新制定候选计划' if errors else '核对本次计划、测量时点与必要事实，再决定是否批准','assumptions_verified':False}
