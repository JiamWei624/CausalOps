"""Explicit, plan-local refinements of a registered descriptive study."""
import re
import pandas as pd

from causalops.general.service import DesignError


def ordered_methods(q):
    if re.search(r'仅(?:作|做)?解释|只(?:作|做)?解释|只讨论|不(?:要)?(?:执行|计算|拟合).*(?:只|仅).*解释|如何|是什么',q):
        return []
    steps = re.split(r'然后|随后|接着|之后再|[,，；;]\s*再|再用|再使用',q)
    if len(steps)<2:
        return []
    methods=[]
    for step in steps:
        if re.search(r'不要|跳过|无需|不做',step):continue
        if re.search(r'分布|描述统计|描述性统计',step):methods.append('descriptive')
        elif re.search(r'OLS|线性回归',step,re.I):methods.append('ols')
    return methods if len(methods)==2 and len(set(methods))==2 else []


def natural_days(value):
    if value.isascii() and value.isdigit():return int(value)
    digits=dict(zip('零一二三四五六七八九',range(10)))
    digits['两']=2
    result=current=0
    for c in value:
        if c in digits:current=digits[c]
        elif c in '十百':
            result+=(current or 1)*(10 if c=='十' else 100)
            current=0
        else:raise ValueError('日期天数无法识别')
    return result+current


DAY_SPAN = re.compile(r'(?:最近|近|过去|最后|(?:往回|向前|回溯)(?:算|数|推)?的?)\s*(\d{1,3}|[一二两三四五六七八九十百零]+)\s*(?:个)?(?:自然)?[日天]')
ISO_DATE = re.compile(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)')


def requested_scope(q, body, frame):
    """Only infer a candidate for an explicit change. Every such candidate requires review."""
    if not body:return None
    changed=re.search(r'(?:改看|改成|改用|改为|改按|换成|切换(?:至|到)|更换为)\s*([^。；;！？?，,]{1,130})',q)
    span=DAY_SPAN.search(q)
    explicit=list(dict.fromkeys(ISO_DATE.findall(q)))
    if not changed and not span and len(explicit)!=2:return None
    result={'base_outcome':body.get('outcome'),'outcome':body.get('outcome')}
    if len(explicit)>2:return {'error':'出现多个日期范围，请确认要分析的起止日期。'}
    if changed:
        names=[str(col) for col in frame.columns if re.search(r'(?<![A-Za-z0-9_])'+re.escape(str(col))+r'(?![A-Za-z0-9_])',changed[1],re.I)]
        if not names:
            def subject(text):
                text=re.sub('^(?:当日|每日|每天|日均)','',text.strip())
                return text.replace('访问人数','访客人数')
            requested=subject(changed[1])
            from causalops.application.research_semantics import field_aliases
            aliases=field_aliases({**body,'fields':body.get('fields') or [{'field':str(k)} for k in frame.columns]})
            names=[key for key,terms in aliases.items() if key in frame and any(len(subject(t))>=2 and subject(t) in requested for t in terms if t)]
        if len(names)==1 and names[0]!=body.get('outcome'):
            field=names[0]
            if not pd.api.types.is_numeric_dtype(frame[field]):
                return {'error':'新指标不是数值字段，请先确认统计口径。'}
            meta=next((v for v in body.get('fields',[]) if v['field']==field),{})
            result.update(outcome=field,metric_label=field,metric_unit=meta.get('unit',''),metric_kind='unknown')
        elif not span and not explicit:
            if re.search('指标|目标|结果变量',q) and len(names)!=1:return {'error':'请明确新指标对应的字段名称，再制定待审计划。'}
            return None
    if span or explicit:
        date=body.get('time')
        if not date or date not in frame:return {'error':'请确认观察窗口的日期字段和截止日期；旧报告不能直接回答新窗口。'}
        if pd.api.types.is_numeric_dtype(frame[date]):return {'error':'数值日期的时间单位未确认，无法确定自然日窗口。'}
        dates=pd.to_datetime(frame[date],errors='coerce')
        if dates.empty or dates.isna().any() or not pd.api.types.is_datetime64_any_dtype(dates) or dates.dt.tz is not None:
            return {'error':'日期覆盖或时区未明确，无法确定新的自然日窗口。'}
        calendar=dates.dt.normalize()
        try:
            end=pd.Timestamp(explicit[-1]) if explicit else calendar.max()
            if span:
                days=natural_days(span[1])
                start=end-pd.Timedelta(days=days-1)
                if len(explicit)==2 and start!=pd.Timestamp(explicit[0]):return {'error':'起止日期与请求天数不一致，请确认日期窗口。'}
            else:start=pd.Timestamp(explicit[0])
        except (ValueError,OverflowError):return {'error':'无法解析给出的日期，请确认起止日期。'}
        if start>end or (end-start).days>=3660:
            return {'error':'当前数据的日期覆盖不足或窗口无效，请确认范围。'}
        coverage=calendar[calendar.between(start,end)].nunique()
        expected=(end-start).days+1
        if coverage!=expected:
            observed=sorted(str(t.date()) for t in calendar[calendar.between(start,end)].unique())
            requested=[str(t.date()) for t in pd.date_range(start,end)]
            absent=sorted(set(requested)-set(observed))
            declared=(body.get('calendar_rule')=='daily' and bool(body.get('calendar_start')) and
                      body['calendar_start']<=requested[0] and (body.get('calendar_end') or '')>=requested[-1])
            scope={'requested':requested,'observed':observed,'no_record':absent,'contract_missing':absent if declared else None}
            meaning='应观测而缺失' if declared else '合同未声明此范围每日应有记录；仅能确认无记录'
            return {'coverage':scope,'error':f'请求窗口 {requested[0]} 至 {requested[-1]}，覆盖 {coverage}/{expected} 个自然日。{meaning}：'+
                    '、'.join(absent[:12])+(' 等' if len(absent)>12 else '')+'。无记录不等于业务值为零，请确认观测日历。'}
        result.update(date=date,start=str(start.date()),end=str(end.date()),covered_days=int(coverage),
                      metric_window=f'{start.date()} 至 {end.date()}，含首尾，共 {coverage} 个自然日')
    if not result.get('outcome'):return {'error':'请确认新方案的结果字段。'}
    return result


def check_steps(scope, steps):
    if not scope:
        if any(step['config'].get('window_start') or step['config'].get('window_end') for step in steps):
            raise DesignError('候选日期筛选未绑定本次研究窗口，请先确认日期范围。')
        return
    if scope.get('error'):raise DesignError(scope['error'])
    for step in steps:
        c=step['config']
        if c['method']!='descriptive' or c.get('numeric')!=[scope['outcome']]:
            raise DesignError('候选方案与当前研究指标不一致。')
        if not scope.get('start') and (c.get('window_start') or c.get('window_end')):
            raise DesignError('仅修改指标时不能额外改变观察窗口。')
        if scope.get('start') and (c.get('date'),c.get('window_start'),c.get('window_end'))!=(scope['date'],scope['start'],scope['end']):
            raise DesignError('候选方案没有采用已核对的观察窗口。')
