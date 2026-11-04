"""Evaluate an explicitly requested comparison against one saved statistic."""
import operator
import re
from decimal import Decimal

OPS = {'大于等于':'ge','大于或等于':'ge','至少':'ge','不低于':'ge','不少于':'ge','达到':'ge','小于等于':'le','小于或等于':'le','不超过':'le','至多':'le','最多':'le','不高于':'le','不大于':'le','超过':'gt','大于':'gt','高于':'gt','小于':'lt','不足':'lt','低于':'lt','不到':'lt','未达到':'lt','等于':'eq','恰好等于':'eq','≥':'ge','≤':'le','>=':'ge','<=':'le','>':'gt','<':'lt','=':'eq'}
TEST = {'ge':operator.ge,'le':operator.le,'gt':operator.gt,'lt':operator.lt,'eq':operator.eq}
OP='|'.join(map(re.escape,sorted(OPS,key=len,reverse=True)))
CUE=re.compile(OP+'|参考线|参考值|验收线|阈值|基准|达标|高还是低|低还是高|相比|相差|相等|比较|偏高|偏低')
UNITS=('毫升','公升','升','个百分点','百分点','摄氏度','摄氏','℃','°C','千克','公斤','克','毫秒','秒','分钟','小时','人民币','万元','元','人次','件','单','人','次','分','%','％')
# Only conversions with fixed, known scale.
SCALE={'升':('volume',1000),'公升':('volume',1000),'毫升':('volume',1),'℃':('temperature',1),'摄氏度':('temperature',1),'摄氏':('temperature',1),'°C':('temperature',1),
       '万元':('currency',10000),'人民币':('currency',1),'元':('currency',1),'千克':('mass',1000),'公斤':('mass',1000),'克':('mass',1),
       '小时':('time',3600),'分钟':('time',60),'秒':('time',1),'毫秒':('time',Decimal('.001')),
       '百分比':('rate',1),'%':('rate',1),'％':('rate',1),'概率':('rate',100),'比例':('rate',100),
       '百分点':('difference',1),'个百分点':('difference',1)}
def normalized(q):
    return re.sub(r'负\s*(?=\d)','-',q.replace('−','-').replace('－','-'))
def threshold(q, registered_unit=''):
    q=normalized(q)
    if not CUE.search(q) and not re.search(r'比\s*[+-]?\d',q):return None
    # Never treat version numbers, dates, or sample sizes as thresholds.
    units=sorted(set(UNITS) | ({registered_unit} if registered_unit else set()),key=len,reverse=True)
    immediate=re.search('('+OP+r')\s*(?:阈值|参考值|基准值|目标值)?\s*[:：为]?\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))',q)
    other=re.search(r'(?:相对于|相对|与|和|比|阈值|参考线|参考值|基准值?|目标值?|标准|门槛|验收线)\s*[为是：:]?\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))',q)
    reverse=re.search(r'([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:'+'|'.join(map(re.escape,units))+r')?\s*(?:是否|是不是)?('+OP+r')\s*(?:该|本次|样本)?(?:均值|平均值|中位数)',q)
    suffix=re.search(r'([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:'+ '|'.join(map(re.escape,units))+r')?\s*(?:的|这条)?(?:参考线|验收线|阈值|门槛|标准)',q)
    m=reverse or immediate or other or suffix
    if not m:return None
    idx=2 if m is immediate else 1
    tail=q[m.end(idx):].lstrip()
    # Match only the unit immediately following the threshold itself. Never scan another literal.
    boundary=r'^(?:$|[\s，。；、？！,;.?!（）()：:]|是否|相[比差等]|的|这|还是|吗|呢|为|是|达标|参考|阈值|标准|且|请|比|高|低|大于|小于|等于|还是)'
    unit=next((u for u in units if tail.startswith(u) and re.match(boundary,tail[len(u):])),None)
    if not unit and any(tail.startswith(u) for u in units):
        unit='未登记量纲'
    if not unit and (re.match(r'[A-Za-z\u4e00-\u9fff]',tail) and not re.match(r'是否|相|的|这|高|低|大|小|多|少|更|还是|吗|呢|为|是|达标|未达标|究竟|参考|阈值|验收|标准|恰好|和|而|且|请|比|个?自然日内',tail)):
        unit='未登记量纲'
    code=OPS[m[1]] if m is immediate else OPS[m[2]] if m is reverse else None
    return Decimal(m[idx]),unit,code,m is reverse

def compare(facts,run,dictionary,question):
    parsed=threshold(question,dictionary.get('metric_unit') or '')
    if not parsed:return None
    target,target_unit,op,reverse=parsed
    unit=dictionary.get('metric_unit','')
    outcome=dictionary.get('outcome')
    chosen=[]
    def reply(msg):
        return dict(source='本地已保存运行证据',text=msg+' 来源：运行 '+run['run_id']+'。',
            facts=[dict(id=k,**v) for k,v in chosen],citations=[])
    if '达标' in question and not op and not re.search('越[高低]越好|至少|至多',question):
        return reply('请确认达标是达到下限还是不超过上限，以及等于阈值是否达标。')
    pp= '百分点' in question
    if pp and any(k.endswith(':rate.pp') for k in facts):
        chosen=[(k,v) for k,v in facts.items() if k.endswith(':rate.pp')]
        label='两组概率差';unit='个百分点'
    else:
        stat=('median' if re.search('中位|median',question,re.I) else 'mean' if re.search('平均|均值|mean',question,re.I) else None)
        if stat is None:return reply('请明确要与阈值比较的统计量，例如均值或中位数。')
        candidates=[(k,v) for k,v in facts.items() if v['path'].startswith('summary.numeric[') and v['path'].endswith('.'+stat)]
        names={v['text'].rsplit(' / ',1)[0] for _,v in candidates}
        tokens=set(re.findall(r'[A-Za-z_][A-Za-z_0-9]*',question)) - {'mean','median','C'}
        # A registered alphabetic unit token is not a request for a second column.
        tokens-=set(re.findall(r'[A-Za-z_][A-Za-z_0-9]*',target_unit or ''))
        fields=tokens & names
        if tokens - names or len(fields)>1:return reply('所问字段或单位不能唯一对应所选报告，请核对比较对象。')
        field=next(iter(fields),outcome)
        chosen=[(k,v) for k,v in candidates if v['text'].rsplit(' / ',1)[0]==field]
        label=str(field or '')+(' 的均值' if stat=='mean' else ' 的中位数')
        if field!=outcome:unit=next((f.get('unit','') for f in dictionary.get('fields',[]) if f['field']==field),'')
    if len(chosen)!=1 or chosen[0][1]['value'] is None:return reply('所选运行缺少唯一有效的目标统计量，不能判断阈值。')
    value=Decimal(str(chosen[0][1]['value']))
    if not unit and not target_unit and dictionary.get('metric_kind')!='binary':
        return reply('统计量单位未登记，不能确认阈值与它采用同一尺度。')
    if target_unit:
        origin=unit or ('概率' if dictionary.get('metric_kind')=='binary' else '')
        a=SCALE.get(origin,(origin,1));b=SCALE.get(target_unit,(target_unit,1))
        if a[0]!=b[0] or target_unit=='未登记量纲':return reply('阈值与统计值的单位未确认一致，不能直接比较。该统计量的登记单位为 '+(origin or '未知')+'，须先核对目标量纲及换算依据。')
        value=value*Decimal(a[1])/Decimal(b[1])
        unit=target_unit
    relation='低于' if value<target else '高于' if value>target else '等于'
    diffunit=' 个百分点' if unit in ('%','％','百分比') else unit
    answer=f'{label}为 {value}{unit}，{relation} {target}{unit}，绝对差为 {abs(value-target)}{diffunit}。'
    if op:
        ok=TEST[op](target,value) if reverse else TEST[op](value,target)
        answer+='所问条件'+('满足。' if ok else '不满足。')
    return reply(answer)
