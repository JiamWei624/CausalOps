"""Verified two-arm subset of the Hillstrom email experiment."""
from hashlib import sha256
from io import BytesIO

import pandas as pd

ARCHIVE_SHA = 'bab6578f60db5d792f1c2372c502f029152a5249cf5ea84390f3b7f885d7234f'
QUESTION = '使用 A/B 随机实验比较男装邮件与未发邮件客户在两周内的访问率，并给出绝对差与区间。'
SOURCE = 'https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html'
DOWNLOAD = 'https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz'
COUNTS = {'未发邮件': (2262, 21306), '男装邮件': (3894, 21307)}


def cohort(payload):
    if sha256(payload).hexdigest() != ARCHIVE_SHA:
        raise ValueError('文件与已核对的公开实验压缩包不符。请使用此页提供的数据版本。')
    source = pd.read_csv(BytesIO(payload), compression='gzip', usecols=['segment', 'visit'])
    selected = source.loc[source.segment.isin(["Mens E-Mail", 'No E-Mail'])].copy()
    counts = selected.groupby('segment')['visit'].agg(['sum','count'])
    for group, label in [('Mens E-Mail', '男装邮件'), ('No E-Mail', '未发邮件')]:
        if group not in counts.index or tuple(counts.loc[group]) != COUNTS[label]:
            raise ValueError('分组样本或访问计数与登记值不一致。')
    return pd.DataFrame({'entity_id': selected.index, 'assigned': selected.segment.eq("Mens E-Mail").astype(int),
                         'visit': selected.visit}).to_csv(index=False).encode()


def contract():
    return dict(analysis_unit='客户', purpose='causal', structure='cross_section', entity='entity_id',
                treatment='assigned', control_value='0', treated_value='1', outcome='visit',
                metric_label='两周访问率', metric_unit='概率', metric_kind='binary', metric_window='分配后两周',
                fields=[dict(field='assigned', meaning='男装邮件与未发邮件的随机分配组', unit='0/1', timing='unknown'),
                        dict(field='visit', meaning='两周内是否访问', unit='0/1', timing='post_treatment')],
                research=dict(population='Hillstrom 实验中分配至男装邮件或未发邮件的客户',
                              inclusion='按预先指定的两组纳入；女装邮件组不进入本次比较。',
                              comparison='分配男装邮件与未发邮件', estimand='两组客户在分配后两周内访问概率的绝对差',
                              observation_period='邮件分配后两周', provenance=SOURCE,
                              limitations='结果仅覆盖本次实验的访问行为，不能据此推断次年利润。'),
                method_facts={'ab_test': {'assignment': 'randomized'}})
