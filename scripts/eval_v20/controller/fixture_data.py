"""Seed research data. No browser or model is used during initialization."""
from io import BytesIO
from pathlib import Path
import os
import pandas as pd
import numpy as np

def materials(case):
    if case=='B01':
        from causalops.sample_data.hillstrom import cohort,contract
        archive=os.environ.get('CAUSALOPS_HILLSTROM_ARCHIVE')
        if not archive: raise ValueError('请设置 CAUSALOPS_HILLSTROM_ARCHIVE 指向公开实验原始压缩包。')
        source=Path(archive)
        return pd.read_csv(BytesIO(cohort(source.read_bytes()))),contract()
    if case=='B02':
        i=np.arange(128)
        x=1+(i*11)%7
        y=np.round(40+4.8*x+((i*13)%21-10)*1.7,2)
        df=pd.DataFrame(dict(customer_id=i+1,satisfaction=x,spend=y))
        body=dict(structure='cross_section',purpose='exploratory',entity='customer_id',analysis_unit='顾客',
           outcome='spend',predictors=['satisfaction'],metric_label='购买金额',metric_unit='元',metric_kind='continuous',
           fields=[dict(field='satisfaction',meaning='访问时填写的满意度评分',unit='分'),dict(field='spend',meaning='购买金额',unit='元')],
           research={'population':'合成顾客横截面，每人一行。仅研究样本内满意度与购买金额的关联。','provenance':'V2 确定性合成资料'})
        return df,body
    if case=='B04':
        i=np.arange(1000);orders=np.tile([0,2,5,7,9,10,11,12,15,18],100)
        orders[-6:]+=1
        assert orders.sum()==8906
    else:
        i=np.arange(48)
        orders=(i*7)%18
    visits=32+(i*19)%91
    df=pd.DataFrame(dict(day=pd.date_range('2024-01-01',periods=len(i)).astype(str),orders=orders,visitors=visits))
    body=dict(structure='unknown',analysis_unit='自然日',purpose='exploratory',time='day',outcome='orders',
        metric_label='每日订单数',metric_unit='单',metric_kind='count',metric_window='当前完整登记期间',
        fields=[dict(field='day',meaning='当地自然日'),dict(field='orders',meaning='当日去重订单笔数，真实零订单日保留',unit='单'),
                    dict(field='visitors',meaning='当日访问人数，跨日可重复',unit='人')],
        research={'population':'一家单店，完整日期均有记录，含真实零订单日。','provenance':'V2 确定性合成资料'})
    if case=='B03':body['measurement']={'numerator':'orders','denominator':'visitors','aggregation':'ratio_of_sums'}
    if case in ('B05','B06'):body['metric_window']='基准登记窗：当前表全部日期'
    return df,body
