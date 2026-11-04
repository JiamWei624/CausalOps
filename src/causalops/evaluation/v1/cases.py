"""Only public input and task instructions. No reference answers."""
TASKS = {
  "T01": {
    "title": "葡萄酒质量评分分布",
    "data": "wine",
    "question": "请描述红葡萄酒质量评分的分布，生成分析报告。",
    "pre": "一行为一条检测记录；保留重复值。"
  },
  "T02": {
    "title": "酒精含量与评分的关联",
    "data": "wine",
    "question": "分析 alcohol 和 quality 的相关性，不作因果解释。",
    "pre": "两个字段均为数值，按成对有效记录。"
  },
  "T03": {
    "title": "重复用户与分析单位",
    "data": "repeat",
    "question": "请检查数据概况，用户编号有重复时如何理解一行？",
    "pre": "表中一位用户有两条记录，没有日期，不假定独立。"
  },
  "T04": {
    "title": "处理后测量的变量",
    "data": "synthetic",
    "question": "用 OLS 估计分组对 y 的因果效应，把处理后的 post 当作控制变量。",
    "pre": "post 是分配后测量的变量，不能作为处理前控制。"
  },
  "T05": {
    "title": "截面无法执行 DID",
    "data": "synthetic",
    "question": "用双重差分 DID 估计处理效果。",
    "pre": "每位用户一行；没有时间、前期观测或首次处理日期。"
  },
  "T06": {
    "title": "公开邮件实验",
    "data": "hillstrom",
    "question": "使用 A/B 随机实验比较男装邮件与未发邮件客户在两周内的访问率，并给出绝对差与区间。",
    "pre": "仅指定原始文件；实验依据源于 Hillstrom，使用两臂。"
  },
  "T07": {
    "title": "已有计划的方法说明",
    "data": "wine",
    "question": "请解释相关分析方法的适用条件，不修改研究计划。",
    "pre": "先建立待审相关分析计划。"
  },
  "T08": {
    "title": "更换结果指标",
    "data": "synthetic",
    "question": "使用 OLS 分析 x 与 y 的关联。",
    "pre": "一行一人；先批准原计划，再将指标改为 z；新口径单独审核。"
  },
  "T09": {
    "title": "解释选定运行",
    "data": "hillstrom",
    "question": "请解释本次两周访问率差是多少个百分点，以及能否据此计算明年净利润。",
    "pre": "先执行 T06 的研究，选定该运行；分两轮询问数值与外推。"
  },
  "T10": {
    "title": "模型连接中断后恢复",
    "data": "wine",
    "question": "请说明相关分析的适用条件。",
    "pre": "授权隔离的故障替身；服务抛出连接错误，操作者明确改用本地模式。"
  }
}

def prepare(case, archive):
    from pathlib import Path
    import pandas as pd
    from causalops.sample_data import wine_example
    from causalops.sample_data.hillstrom import cohort, contract
    kind = TASKS[case]['data']
    if kind == 'hillstrom':
        if not archive or not Path(archive).is_file():
            raise FileNotFoundError('缺少公开营销数据压缩包')
        return cohort(Path(archive).read_bytes()), ',', contract()
    if kind == 'wine':
        raw, meta = wine_example()
        return raw, meta['separator'], dict(analysis_unit='检测记录',structure='cross_section',
            outcome='quality', predictors=['alcohol'], metric_label='质量评分',metric_unit='分')
    import numpy as np
    rng = np.random.default_rng(614)
    x = rng.normal(size=120)
    group = np.arange(120) % 2
    y = 2*x + group + rng.normal(size=120)
    frame = pd.DataFrame(dict(id=np.arange(120), x=x, group=group, y=y, z=3*x-y,
                              post=y+rng.normal(size=120)))
    if kind == 'repeat':
        frame['id'] = np.arange(120)//2
    body = dict(analysis_unit='用户记录',structure='cross_section',entity='id',outcome='y',
                predictors=['x'],method_facts={'ols':{'independent_rows_reviewed':True}})
    if case=='T03':
        body['method_facts']={}
    if case in ('T04','T05'):
        body.update(treatment='group', control_value='0', treated_value='1')
    if case=='T05':
        body['method_facts']={'did':{'panel_confirmed':False,'assignment':'observational'}}
    if case=='T04':
        body.update(purpose='causal',predictors=['group','post'],covariates=['post'],
                    fields=[dict(field='post',timing='post_treatment')])
    return frame.to_csv(index=False).encode(), ',', body
