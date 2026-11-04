"""Interpret exposure rates and equal-entity summaries of one approved report."""
from decimal import Decimal
import re


def number(value):
    if value is None:return None
    result=Decimal(str(value))
    return result if result.is_finite() else None


def partition(bundle, key, fields):
    """Only complete, non-overlapping groups from this saved descriptive design are eligible."""
    if not bundle or not key or bundle.get('design',{}).get('group')!=key:return None
    summary=bundle['summary']
    groups={}
    for index,row in enumerate(summary.get('grouped',[])):
        field=row['field']
        if field not in fields:continue
        group=row['group_value']
        if group is None or row['rows']<=0 or row['finite_n']!=row['rows'] or number(row['mean']) is None:return None
        selected=groups.setdefault(group,{})
        if field in selected:return None
        selected[field]=(row['rows'],number(row['mean']),index)
    if not groups or any(set(cols)!=set(fields) for cols in groups.values()):return None
    if any(len({col[0] for col in cols.values()})!=1 for cols in groups.values()):return None
    if sum(cols[fields[0]][0] for cols in groups.values())!=summary['row_count']:return None
    return groups.values()


def answer(question,contract,catalog,run,bundle,reply):
    rid=run['run_id']
    density=(re.search(r'毫升|公升|立方厘米|mL|体积|(?:\d|单位是|单位为)\s*升',question) and
             (contract.get('metric_unit') in ('克','千克','毫克','g','kg','mg') or re.search('质量|重量|克',question)))
    if density and re.search('转换|换算|量纲|比较|折合|相当|限值',question):
        return reply('质量和体积量纲不同。需要同一物质在相应温度、状态下的密度及单位；体积＝质量÷密度。'
                     '例如用克与克/毫升才得到毫升。只有原报告的质量统计量不能直接与体积限值比较。')
    distance=re.search(r'(?:每\s*)?(百|千|万|\d+(?:\.\d+)?)\s*(?:公里|千米|km)|每(?:公里|千米)',question,re.I)
    has_rate=bool(distance and re.search('每|油耗|单耗|耗油|率',question))
    equal=bool(re.search('等权|相同权重|同等权重|各.{0,7}(?:均值|平均).{0,8}再.{0,4}平均',question))
    measure=contract.get('measurement') or {}
    if re.search('去重|不重复|独立账号|独立账户',question) and re.search('分母|人均|每|汇总|合计|相加',question):
        return reply('同一实体可能跨日重复出现。各日计数之和是实体日，不能代替全期去重实体数。'
                     '需要可跨期关联的实体标识或同一观察窗口已保存的去重分母。')
    # An equal-entity request requires a checked grouping partition regardless of the industry noun.
    hierarchy=equal and not re.search('各日|每天|按日|每日|日期',question)
    if equal and re.search('抽检|抽样|组内|实体|对象|站点|设备|箱|各组|门店|线路',question):
        hierarchy=True
    if not has_rate and not hierarchy:return None
    if run.get('method')!='descriptive':
        return reply('请先选择保存了所问分子、分母或分组统计的描述报告；不能据另一种模型的估计值换算。')
    fields={f['field']:f for f in contract.get('fields',[])}
    key=contract.get('entity')
    if bundle and bundle.get('run_id')!=rid:bundle=None
    metric=contract.get('outcome')
    num,den=measure.get('numerator'),measure.get('denominator')
    numerator=fields.get(num,{})
    subject_unit=contract.get('metric_unit','')
    window=contract.get('metric_window') or '所选报告的样本范围'
    if re.search(r'分别.{0,12}(?:时间窗|期间)|不同(?:月份|观察窗)|分月|分季度',question):
        return reply('当前运行只绑定一个观察窗口；需要各窗口分别保存的同口径证据，不能拆用整体结果。')
    if has_rate:
        factor={'百':100,'千':1000,'万':10000}.get(distance[1],distance[1] or 1)
        factor=Decimal(str(factor))
        denom=fields.get(den,{})
        km={'公里':1,'千米':1,'km':1,'米':Decimal('.001'),'m':Decimal('.001')}.get(denom.get('unit'))
        num_unit=numerator.get('unit') or (subject_unit if num==metric else '')
        fuel=bool(re.search('耗油|油耗|燃油',question))
        verified_numerator=(num and (num in question or (numerator.get('meaning') and numerator['meaning'] in question) or
                (fuel and re.search('燃油|耗油|油耗',numerator.get('meaning','') or contract.get('metric_label','')) and num_unit in ('升','L','毫升','mL'))))
        travel=re.search('里程|行驶距离|行车距离|行驶路程|行程距离|distance travelled|distance traveled|mileage',denom.get('meaning',''),re.I)
        if not km or not travel or not verified_numerator or num==den or not num_unit:
            return reply(f'需要同一对象、同一观察窗口的分子总量和实际行驶里程（公里）。先以总量除以总里程，再按所问距离乘 {factor:g}。'
                         '运行小时、路线数和记录条数都不能替代行驶距离；请在数据合同中核对两列的定义与单位。')
        requested='mean_of_ratios' if equal else 'ratio_of_sums'
        if measure.get('aggregation')!=requested:
            return reply('总体按总分子除以总里程，等价于按距离加权；线路等权则先计算每条线路的油耗率，再平均。请确认登记的汇总口径。')
        if not equal:
            labels=['纳入表行数',num+' / finite_n',num+' / mean',den+' / finite_n',den+' / mean',den+' / min']
            items=[catalog.get(label) for label in labels]
            if not all(i and number(i[1]['value']) is not None for i in items):return reply('缺少同一窗口的完整分子及行驶里程汇总，不能计算。')
            n,n1,x,n2,y,minimum=[number(i[1]['value']) for i in items]
            if not n or n!=n1 or n!=n2:return reply('分子或里程缺失，不能确认相同样本。')
            if y<=0 or minimum<0:return reply('总里程为零或出现非法负距离，不能计算。')
            rate=x/(y*km)*factor
            return reply(f'总体距离加权结果约 {rate:.6g}{num_unit}/'+('百公里' if factor==100 else f'{factor:g}公里')+
                         f'。分子 {num} 与里程 {den} 覆盖同一批 {n} 条记录。窗口：{window}。',items)
    if hierarchy and not has_rate and re.search('记录平均|读数平均|记录均值|读数.{0,3}均值',question) and not key:
        return reply('记录均值按每次观测等权；抽检次数不同会使同一对象权重不同。需要每台设备的实体标识（设备编号/箱号），先按箱算组内均值，再对各箱均值等权平均。设备总数不能还原这一结果。')
    if has_rate and equal and num and den:
        item=catalog.get(den+' / min')
        if not item or number(item[1]['value']) is None or number(item[1]['value'])<0:
            return reply('缺少完整的非负里程检查。')
    if not key or re.search(r'(?:没有|缺少|尚无|未提供).{0,7}(?:编号|箱号|标识|分组键)',question):
        return reply('需要可靠的实体标识（例如每个设备的设备编号或箱号）。先按同一标识计算每个对象的均值或比率，'
                     '再对各对象等权平均。记录均值按抽检次数加权，仅有设备总数不能恢复各箱均值。')
    # Confirm the contract identifies the requested type, not an unrelated identifier.
    types=[('线路',('线路','路线')),('设备',('设备','机器','冷藏箱','仪器')),('门店',('门店','分店','商店')),('车辆',('车辆','车牌')),
           ('用户',('用户','客户')),('患者',('患者','病人')),('班组',('班组',)),('批次',('批次',))]
    declared=fields.get(key,{}).get('meaning','')
    if not any(any(word in question for word in aliases) for _,aliases in types):
        group_request=re.search(r'(?:各|每(?:个|台|座)?)([\u4e00-\u9fff]{1,12}?)(?:分别|均值|等权|的平均)',question)
        if not group_request or group_request[1] not in declared:
            return reply('需要与所问对象一致的实体标识，先按对象计算组内均值，再把各组均值等权汇总；记录数或对象总数不能恢复组内信息。')
    if any(any(word in question for word in aliases) and not any(word in declared for word in aliases) for _,aliases in types):
        return reply('现有分组键的对象与所问实体未核对，请登记实体标识及其含义，再先做组内汇总、后做组间等权平均。')
    if not has_rate:
        mentioned=[f for f,v in fields.items() if f!=key and ((v.get('meaning') and v['meaning'] in question) or re.search(r'(?<![A-Za-z0-9_])'+re.escape(f)+r'(?![A-Za-z0-9_])',question))]
        if len(mentioned)>1:return reply('请明确需要在每个对象内求均值的指标。')
        metric=next(iter(mentioned),metric)
        subject_unit=fields.get(metric,{}).get('unit') or (subject_unit if metric==contract.get('outcome') else '')
    cols=[num,den] if has_rate else [metric]
    groups=partition(bundle,key,cols)
    if not groups:return reply(f'需先按实体标识 {key} 计算组内均值或比率，再对实体等权。所选报告没有覆盖同一样本的完整逐组证据，或存在缺失。不能用总记录均值替代。')
    values=[]
    for group in groups:
        if has_rate:
            if group[den][1]<=0:return reply('至少一个对象的总里程为零或负，无法给出全体等权油耗率；须明确有效对象范围。')
            values.append(group[num][1]/(group[den][1]*km)*factor)
        else:values.append(group[metric][1])
    value=sum(values)/len(values)
    unit=(num_unit+'/百公里' if factor==100 else f'{num_unit}/{factor:g}公里') if has_rate else subject_unit
    # A derived fact links the aggregate to the saved partition; never put entity IDs in model context.
    evidence=dict(run_id=rid,path='summary.grouped',text='按已登记实体先组内再组间等权',value=float(value),claim='descriptive',
                  derivation='mean of group ratios' if has_rate else 'mean of group means',group_field=key,fields=cols,groups=len(values))
    return reply(f'先按 {key} 汇总，再对 {len(values)} 个对象等权；结果约 {value:.6g}{unit}。抽检次数只影响组内均值，'
                 f'每个对象在最终平均中占相同权重。观察窗口：{window}。',[(rid+':group_equal',evidence)])
