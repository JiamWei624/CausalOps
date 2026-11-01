"""Evidence-free question discovery uses safe schema only; never invents findings."""
from __future__ import annotations
from pydantic import BaseModel,ConfigDict,Field
from causalops.assistant.service import profile,safe_profile
from causalops.application.onboarding import overview

class Direction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=2,max_length=90)
    question:str=Field(min_length=8,max_length=350)
    fields:list[str]=Field(max_length=12)
    needs_confirmation:list[str]=Field(default_factory=list,max_length=5)
    limitation:str=Field(min_length=8,max_length=400)
class Suggestions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    introduction:str=Field(min_length=8,max_length=500)
    directions:list[Direction]=Field(min_length=1,max_length=3)

def local_suggestions(frame,definition=None):
    pr=safe_profile(profile(frame));numeric=[x['field'] for x in pr['fields'] if x['numeric']]
    directions=[Direction(title='数据分布与缺失分析',question='请分析这张表的缺失和分布，并生成基础图表与报告。',fields=numeric[:6],needs_confirmation=[],limitation='只报告本表样本的特征，不能推断造成差异的原因。')]
    if len(numeric)>1:directions.append(Direction(title='数值字段关联分析',question='请根据已登记的字段含义，制定数值字段关联分析计划；角色不明确时先向我确认。',fields=numeric[:4],needs_confirmation=['分析单位的实际含义','目标指标及其单位'],limitation='相关关系不代表因果；重复观测和抽样方式仍需说明。'))
    declared=definition or {};target=declared.get('outcome')
    if target in {f['field'] for f in pr['fields']}:
        label=declared.get('metric_label') or target
        directions=[Direction(title=label+'的分布与缺失',question='请描述目标指标 '+target+' 的分布、频数与缺失情况，保留原始记录，不做因果推断。',fields=[target],limitation='只解释已登记目标的样本分布，不表示干预改善。')]
        other=next((v for v in numeric if v!=target and v!=declared.get('time')),None)
        if target in numeric and other:
            directions.append(Direction(title=label+'与其他指标的关联',question='请分析 '+target+' 与 '+other+' 的Pearson和Spearman相关关系，不推断因果。',fields=[target,other],needs_confirmation=['两项指标的测量尺度与异常值含义'],limitation='展示实际变量对的相关程度；字段顺序不表示业务重要性。'))
        if declared.get('time') in frame.columns and target in numeric:
            directions.append(Direction(title=label+'的时间变化',question='请按已登记日期 '+declared['time']+' 描述 '+target+' 的分期均值与分布，不补缺期、不做预测。',fields=[target,declared['time']],needs_confirmation=['日期字段的业务含义与统计周期'],limitation='时间图描述已有观察期，不构成趋势外推或因果识别。'))
    return Suggestions(introduction=overview(frame)['text']+' 以下建议优先使用已登记目标；尚未进行计算。',directions=directions)


def discover(service,fid):
    f=service.flow(fid);a=service.a;frame=service.ws.load_upload(f['request']['data']['upload_id']);pr=safe_profile(profile(frame));fields=[x['field'] for x in pr['fields']];numeric=[x['field'] for x in pr['fields'] if x['numeric']]
    from causalops.application.task_readiness import public_contract_context
    local=local_suggestions(frame,public_contract_context(service,f).get('definition',{}))
    source='本地字段规则（未调用模型）';value=local
    if service.model:
        from causalops.application.task_readiness import public_contract_context
        try:
            raw=a._call(f['session_id'],service.model,'根据安全字段摘要推荐1至3个可回答的问题，以中文说明下一步。只推荐问题，不计算、不报告数值结果、不假定字段业务含义、不声明随机化或因果识别。fields只能引用提供的字段；缺少业务语义时提出简短确认问题，不能编造单位或实验分组。只推荐 registered_methods 支持的分析，不推荐未实现的预测训练或其他工具。至少包含一个基础分布方向。基础分布可以直接按原字段名统计，不因未知业务含义而阻止描述；单位未知就保留字段名，不猜单位。用正式、简短、通俗的中文，不出现 exact_duplicate_rows 等内部参数名。推荐的问题应具体而可执行；涉及删除、去重、拟合或识别声明时单独说明仍待用户确认。返回严格JSON。',{'question':f['request']['question'],'dataset':pr,'data_dictionary':public_contract_context(service,f),'registered_methods':[x['method'] for x in a.tools.catalog()]},Suggestions.model_json_schema())
            value=Suggestions.model_validate(raw)
            if any(set(d.fields)-set(fields) for d in value.directions):raise ValueError('不存在或未授权的字段')
            source='模型问题建议（未执行分析）'
        except (ValueError,RuntimeError):value=local;source='本地问题建议（模型输出未通过或服务不可用）'
    return {**value.model_dump(),'source':source,'run_ids':[],'data_sha':f['request']['data']['frame_sha'],'findings_generated':False}
