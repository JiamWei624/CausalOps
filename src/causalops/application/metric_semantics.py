"""Reconcile requested grain and statistic with one saved descriptive run. No refitting."""
import re
from decimal import Decimal

from causalops.application.research_semantics import denominator_note


GRAINS = (
    (r'每(?:一)?单(?:平均|均值)|单均', '单数', '单', ('工单', '维修工单', '订单')),
    (r'每(?:一)?笔(?:交易|订单|支付)?|笔均|客单价|交易均额', '交易笔数', '笔', ('交易', '订单', '支付')),
    (r'每(?:一)?(?:台|部)(?:设备|机器|仪器)?|设备均', '设备数', '台', ('设备', '机器', '仪器')),
    (r'人均|每(?:名|位|个)(?:员工|客服|人员|用户|客户|顾客|人)|每人', '人数', '人', ('人员','用户','顾客','员工','客服','客户')),
    (r'日均|每天平均|平均每天|每(?:一)?天的平均', '日期数', '天', ('日期','自然日','天')),
)


def semantic_answer(facts,run,contract,question,*,bundle=None):
    rid=run['run_id']
    catalog={fact['text']:(key,fact) for key,fact in facts.items() if fact['run_id']==rid}
    fields={f['field']:f for f in contract.get('fields',[])}
    def reply(text,items=()):
        return dict(source='已保存运行的指标口径核对',text=text+' 来源：运行 '+rid+'。',
                    facts=[dict(f,id=k) for k,f in items],citations=[])

    from causalops.application.aggregation_evidence import answer
    aggregate=answer(question,contract,catalog,run,bundle,reply)
    if aggregate:return aggregate

    if '置信区间' in question and re.search('最短|最长|最大|最小|极值|极差|观测范围|样本范围',question):
        return reply('样本范围以本次实际观测的最小值和最大值为端点，描述已见记录的跨度。'
                     '总体均值的置信区间描述均值估计的不确定性：按同一设计重复抽样并构造区间，'
                     '在方法假设成立时，相应比例的区间会覆盖总体均值。不能把样本极值写成均值的置信限。')

    target=next((g for g in GRAINS if re.search(g[0],question)),None)
    measure=contract.get('measurement') or {}
    den=measure.get('denominator')
    registered=fields.get(den,{})
    registered_unit=registered.get('unit')
    numerator=measure.get('numerator')
    num_unit=fields.get(numerator,{}).get('unit')
    if not target and den and registered_unit and re.search(r'每\s*'+re.escape(registered_unit),question):
        item=re.search(r'每\s*'+re.escape(registered_unit)+r'([\u4e00-\u9fff]{2,12}?)(?=耗费|耗用|用量|需要|的|平均|是多少)',question)
        if item and item[1] not in (registered.get('meaning') or '') and item[1] not in den:
            return reply(f'仅单位 {registered_unit} 相同，不能确认“{item[1]}”对应登记分母 {den}。请核对分母对象与纳入范围。')
        target=('',registered.get('meaning') or den,registered_unit,())
    general_note=denominator_note(question,contract)
    if not target and run.get('method')=='descriptive':
        requested=re.search(r'每((?:[百千万]|\d+(?:\.\d+)?)?(?:个)?[a-zA-Z\u4e00-\u9fff]{1,18}?)(?:的|耗费|需要|用量|是多少|要用|为多少)',question)
        if requested and not re.match('行|日|天|条记录|次观测',requested[1]):
            return reply(f'所问分母是“{requested[1]}”。需同一窗口实际发生的该类暴露量和对应分子。请登记分母的业务含义、数值单位与汇总方式，不能用容量、记录数或主指标均值替代。')
    if not target:
        if general_note:return reply(general_note)
        if run.get('method')=='descriptive' and re.search(r'(?:总量|合计|总和)',question) and not re.search('平均|均值|总体均值',question):
            outcome=contract.get('outcome')
            tag=contract.get('metric_label') or outcome
            if not outcome or not (outcome in question or tag in question):
                return reply('请明确要汇总的字段；不能用某一列的均值代替总量。')
            if re.search('分组|各组|中位|阈值',question):
                return reply('所问分组或统计条件尚未绑定到该列的全期总量。')
            names=('纳入表行数',outcome+' / finite_n',outcome+' / mean')
            entries=[catalog.get(k) for k in names]
            if not all(e and e[1]['value'] is not None for e in entries) or entries[0][1]['value']!=entries[1][1]['value']:
                return reply('缺少完整的目标列均值与有效样本量，不能确定总量。')
            total=Decimal(str(entries[1][1]['value']))*Decimal(str(entries[2][1]['value']))
            return reply(f'{tag} 的样本合计约 {total:.6g}{contract.get("metric_unit","")}（保存的均值乘有效记录数）。',entries)
        return None
    _,name,unit,terms=target
    measure=contract.get('measurement') or {}
    num,den=measure.get('numerator'),measure.get('denominator')
    row=contract.get('analysis_unit') or '未登记'
    window=contract.get('metric_window') or '未登记'
    label=contract.get('metric_label') or contract.get('outcome') or '当前指标'
    outcome=contract.get('outcome')
    if re.search('分组|各组|各门店|分门店|按门店|分客户',question):
        return reply('请先确认分组字段和各组的分子、分母；整体样本的事实不能替代组内指标。')
    # A record-level mean suffices only when the declared row is exactly one target unit.
    singleton=re.fullmatch(r'(?:一|单|每)(?:张|笔|个|名|位|台|部)?(?:'+'|'.join(terms)+r')(?:记录)?',row)
    if singleton and outcome and not num and not den:
        mean=catalog.get(str(outcome)+' / mean')
        if mean and mean[1]['value'] is not None and (outcome in question or label in question):
            return reply(f'每行代表{row}，{label}的样本均值为 {mean[1]["value"]:.6g}{contract.get("metric_unit","")}。观察期：{window}。',[mean])
    if not num or not den:
        return reply(general_note if general_note and name=='人数' else
                     f'所问口径需要同一时间窗口的分子总量与{name}作为分母；当前报告按{row}记录{label}。'
                     f'请登记分子字段、{name}及其汇总规则。记录行数或原指标的均值不能替代{name}。')
    denom=fields.get(den,{})
    if denom.get('unit')!=unit and not (denom.get('meaning','')==name):
        return reply(f'所问分母为{name}（{unit}），登记的分母 {den}（{denom.get("meaning") or "定义未确认"}，{denom.get("unit") or "单位未确认"}）未能匹配。')
    if unit in ('人','台') and re.search('去重|不同人员|不同设备|唯一',question):
        return reply('逐期人数或设备数相加可能重复计数，需同一窗口的去重实体数或实体标识。')
    aggregation=measure.get('aggregation')
    if aggregation!='ratio_of_sums' or re.search('等权|各日比率.*平均|每日比率.*平均',question):
        return reply('各日比率等权平均与全期总分子除以总分母对应不同指标。当前汇总证据不能还原逐日配对比率；请核对分子分母、零分母与日期权重。')
    num_label=fields.get(num,{}).get('meaning') or num
    if num not in question and num_label not in question and not (num==outcome and (label in question or num_unit and num_unit in question and re.search('总量比|登记的分子',question))):
        return reply(f'合同为 {num_label}（{num}）除以 {name}（{den}）。请确认所问分子确为该指标。')
    required=['纳入表行数',num+' / mean',num+' / finite_n',den+' / mean',den+' / finite_n',den+' / min']
    items=[catalog.get(k) for k in required]
    if any(i is None or i[1]['value'] is None for i in items):
        return reply(f'已登记 {num} 与 {den}；此运行缺少同一窗口的完整分子、分母或有效记录数，无法给出所问比率。')
    rows,nmean,nn,dmean,dn,dmin=[Decimal(str(i[1]['value'])) for i in items]
    if rows<=0 or nn!=rows or dn!=rows:
        return reply('分子或分母存在缺失，不能确认两列覆盖相同的全部记录。',items)
    if dmin<0 or dmean==0:return reply('当前分母必须非负；总分母为零时比率未定义。',items)
    result=nmean*nn/(dmean*dn)
    numeric_unit=fields.get(num,{}).get('unit') or (contract.get('metric_unit') if num==outcome else '')
    if not numeric_unit:return reply('分子的数值单位未登记，请确认后再解释比率。')
    return reply(f'按总量之比计算：{num} 的总量除以 {den} 的总量，结果约 {result:.6g}{numeric_unit}/{unit}。'
                 f'两列均覆盖全部 {rows} 条观测，总量由保存的各列均值乘有效记录数得到。观察期：{window}。',items)
