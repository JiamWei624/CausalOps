"""Local, version-bound research declarations and conservative task interpretation."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Measurement(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    event_label:str=Field(default='',max_length=120)
    event_time_meaning:str=Field(default='',max_length=160)
    numerator:str|None=None
    denominator:str|None=None
    aggregation:Literal['unknown','ratio_of_sums','mean_of_ratios','binary_mean']='unknown'
    assignment_unit:str=Field(default='',max_length=120)
    cluster_field:str|None=None


LABELS={'event_label':'处理事件名称','event_time_meaning':'处理时间字段的业务含义',
        'numerator':'分子字段','denominator':'分母字段','aggregation':'汇总方式',
        'assignment_unit':'分配单位','cluster_field':'聚类标识'}

NO_COMPUTE=re.compile(r'(?:不要|无需|不必|禁止|暂不|先不|别|不)(?:实际|直接|进行|重新)?(?:拟合|估计|计算|运行|执行)|只(?:解释|讨论|咨询|说明)')
EFFECT=re.compile(r'效果|效应|因果|影响|干预|策略实施|政策实施|促销开始后|intervention|treatment effect',re.I)
SUBSTITUTE=re.compile(r'(?:把|用|将)([^，。；？,;?]{1,40}?)(?:当作|当成|代替|充当|视为|作为)([^，。；？,;?]{1,40}?(?:开始日期|生效日期|日期|时间|时点|开始日|生效日))')
RATE=re.compile(r'率|占比|比例|比率|rate|ratio',re.I)
DESCRIBE=re.compile(r'描述|统计|分布|均值|频数|直方图|基础报告')
REQUEST=re.compile(r'生成|展示|统计|描述|分析|计算|报告|绘制')
def calculation_forbidden(question):
    return bool(NO_COMPUTE.search(question)) and not re.search('生成.{0,8}(?:草案|计划)|制定.{0,6}(?:方案|计划)|候选修订',question)


def issue(question,body,configs=()):
    m=body.get('measurement') or {}
    if calculation_forbidden(question):
        return '本次只讨论研究设计，未授权制定计算方案或执行统计。' if configs else ''
    substitution=SUBSTITUTE.search(question)
    if substitution and EFFECT.search(question):
        source,target=[s.strip(' 的') for s in substitution.groups()]
        time=body.get('treatment_time')
        meanings={f.get('meaning') for f in body.get('fields',[]) if f['field']==time}
        # Bind explicit, exact human declarations. Similar-looking column names are not a date crosswalk.
        if not (time and m.get('event_label') and target==m.get('event_time_meaning')
                and source in {time,target,*meanings}):
            return f'请区分“{source}”与“{target}”。需要登记实际处理事件、对应的处理日期字段及业务口径；不能用另一事件的日期推算效果。'
    event_request=bool(EFFECT.search(question) and re.search(r'开始后|实施后|生效后|干预前后|上线前后',question))
    if event_request and not (m.get('event_label') and body.get('treatment_time') and m.get('event_time_meaning')):
        return '请补充处理事件、真实开始日期及其业务含义，再核对比较组和观察窗口。'
    if event_request and not (body.get('metric_window') or (body.get('research') or {}).get('observation_period')):
        return '尚未登记处理效果的观察窗口。请明确结果从哪一天开始、覆盖多久。'
    if RATE.search(question) and re.search(r'总体|汇总|加权|合并计算|全渠道',question) and not re.search(r'如何|应该|还是|解释|原理|讨论',question):
        if not (m.get('aggregation')!='unknown' and m.get('aggregation') and m.get('numerator') and m.get('denominator')):
            return '请确认分子、分母和汇总方式：总分子除以总分母与各行比率等权平均对应不同目标。'
        if m['aggregation'] in ('ratio_of_sums','mean_of_ratios'):
            return '分子、分母与汇总口径已登记，当前统计执行器未绑定这项比率计算，不能用单列描述结果替代。'
    for cfg in configs:
        method=cfg.get('method')
        if event_request and all(c.get('method')=='descriptive' for c in configs):
            return '当前任务要求评估干预效果，单独的样本描述不能回答该问题。请重新制定研究方案。'
        if (method in ('ab_test','cuped') and m.get('assignment_unit') and
                m['assignment_unit']!=body.get('analysis_unit')):
            return '分配单位与分析单位不同。请核对聚类单位和组内依赖；当前个体层实验计算不能替代整群设计的推断。'
        if method not in ('descriptive','correlation') and body.get('outcome') and cfg.get('outcome')!=body['outcome']:
            return '计划的结果指标与已登记的研究目标不一致。'
        if event_request and cfg.get('treatment_time') and cfg['treatment_time']!=body.get('treatment_time'):
            return '计划中的处理时间与登记的事件时点不一致。'
    return ''


def consultation(question):
    if RATE.search(question) and re.search('分母|加权|权重|平均.*汇总',question):
        return '先明确分母。合并比率应把分子与分母分别汇总再相除，相当于按每日分母加权；各日比率等权平均回答的是典型一天的表现。例如计算购买率，订单数未必等于购买人数，访客也可能跨天重复。'
    if re.search('随机单位|整群|分配单位|集群随机',question):
        return '应按实际随机分配单位核对推断。若按门店整群分配，同店顾客不能作为独立随机单位；需要门店标识、各组门店数量及适合整群设计的标准误。'
    if re.search('只保留|筛选|仅分析',question) and re.search('处理后|点击|中介|干预后',question) and EFFECT.search(question):
        return '仅保留处理后选中的人会改变比较对象，可能引入选择偏差。评估总效应应先保留原分配组，另行讨论条件分析的识别条件。'
    return ''


def registered_ratio_advice(question, body):
    measure=body.get('measurement') or {}
    num,den=measure.get('numerator'),measure.get('denominator')
    if (not num or not den or measure.get('aggregation')!='ratio_of_sums'
            or not (RATE.search(question) or ('分子' in question and '分母' in question)) or not re.search('如何|怎样|怎么|权重|分母|零订单',question)):
        return ''
    return (f'登记口径为总 {num} 除以总 {den}。先分别合计分子和分母，等价于按各日或各组的 {den} 加权。'
            f'当 {den} 大于零而 {num} 为零时，保留该行及其分母；'
            '分母为零的行没有可定义的行比率，应核对记录。全期分母也为零时不能报告总体比率。'
            '缺失观测不能直接记作真实零值。各班次或各日比率等权，则每个班次或日期权重相同，回答的是典型班次或日期的问题。')

def reads_saved_result(question):
    """A reference to an existing report plus a read verb; keep explicit changes actionable."""
    affirmative=re.sub(r'(?:不要|无需|不必|不用|暂不|不|勿|别)(?:再|另行|重新|新)?(?:建(?:立)?|生成|制定|用|执行|计算|拟合|运行|调整)?(?:新模型|新计划|新方案|计划|模型|计算|拟合|运行)?', '',question)
    if re.search(r'另(?:建|拟)|重新(?:分析|计算|拟合)|(?:制定|生成|建立|提交|创建).{0,6}(?:计划|方案)|改为|换成|再用|再使用|请(?:拟合|计算)',affirmative):
        return False
    # Asking for a new plan for later review and explaining its coverage are compatible.
    if re.search('新方案|新计划|候选计划',affirmative) and re.search('核对后|确认后|审查后|再批准|待我审核|提交审核',affirmative):
        return False
    source=re.search('报告|记录中|已保存|已完成|所选|上轮|原结果',question)
    inquire=re.search('引用|读取|解读|解释|说明|看看|看一下|分析一下|是多少|多少|均值|平均|中位|方向|同向|反向|能否|能不能|哪|怎么理解',question)
    return bool(re.search('只查|只读|只引用',question) or source and inquire or calculation_forbidden(question) and inquire and
                re.search('现有|已有|根据|能否|只想知道|只解释|需要什么',question))



def denominator_note(question,body):
    person=re.search(r'人均|每(?:名|位|个)(?:员工|客服|人员|用户|客户|人)|每人|每班.{0,12}平均',question)
    exposure=re.search(r'每(?:百|千|万|\d+).{0,12}?(?:小时|人日|台时|工时)',question)
    weighted=RATE.search(question) and re.search(r'等权|加权|各日.*平均|日.{0,18}(?:全周|全期|整月|全月|总体)|全期汇总',question)
    if not (person or exposure or weighted):
        return ''
    measurement=body.get('measurement') or {}
    num,den=measurement.get('numerator'),measurement.get('denominator')
    period=body.get('metric_window') or '尚需明确的观察期'
    unit=body.get('analysis_unit') or '未登记'
    if exposure and not den:
        return (f'每单位暴露的发生率需要同一窗口（{period}）内的事件总数和实际总暴露量，'
                '如设备运行台数乘各自运行小时。应以总事件数除以设备小时总数，再换算到所问尺度。'
                '记录条数、日期数和每日事件均值都不能代替暴露分母。分母为零时发生率未定义。')
    if weighted and not person and (not num or not den):
        return ('每日比例等权平均衡量典型一天；全期事件率要以各日符合条件的总次数作权重，'
                '用各日事件数之和除以各日机会数之和。需要每天的分子和分母；每日比率的中位数也不能替代全期概率。'
                '没有各日分母就不能从若干每日比例还原全期率。零分母日无日比率，全期分母为零时不报告汇总率。')
    if not num or not den:
        return (f'该报告按“{unit}”记录，观察期为{period}。人均指标需要同一范围内的总量作分子，'
                '并登记对应人数或逐日排班人数作分母。数据行数不能直接代替人数。'
                '若要按日等权，先算各日人均再平均；若按人日加权，应汇总总量和人日再相除；'
                '若问全期每名人员的总量，还需全期去重人数。缺少这些口径，不能给出所问人均值。')
    agg=measurement.get('aggregation')
    mode={'ratio_of_sums':'先合计分子和分母，再相除','mean_of_ratios':'先计算各期比率，再对有效日期等权平均'}.get(agg,'汇总方式尚待确认')
    return (f'登记分子为 {num}，分母为 {den}，观察期为{period}，口径为“{mode}”。'
            '请核对分母代表当日人数、人日还是全期去重人数，以及报告是否保存了该比率。'
            '分母为零时比率未定义；分子为零且分母为正时比率为零。不能用数据行数或单列均值替代。')
