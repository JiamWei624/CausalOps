import pytest
from causalops.application.saved_answers import saved_answer


def study():
    contract=dict(analysis_unit='线路日',entity='line',metric_label='耗油量',outcome='fuel',metric_unit='升',metric_window='三月',
        fields=[dict(field='fuel',meaning='耗油量',unit='升'),dict(field='span',meaning='行驶里程',unit='公里'),
                dict(field='line',meaning='线路编号',unit='')],measurement=dict(numerator='fuel',denominator='span',aggregation='ratio_of_sums'))
    rows=[dict(group_value=k,field=f,rows=n,finite_n=n,mean=v) for k,n,lit,km in [('a',2,10,100),('b',1,3,10)]
          for f,v in [('fuel',lit),('span',km)]]
    data={'run_id':'x','design':{'group':'line'},'summary':{'row_count':3,'grouped':rows}}
    facts={}
    for key,v in [('纳入表行数',3),('fuel / mean',23/3),('fuel / finite_n',3),('span / mean',70),
                  ('span / finite_n',3),('span / min',10),('fuel / min',3)]:
        facts[key]=dict(run_id='x',text=key,path='summary.row_count' if '/' not in key else 'summary.numeric[0].'+key.split()[-1],value=v)
    return contract,facts,data


def ask(q,contract,facts,bundle):
    return saved_answer(facts,{'run_id':'x','method':'descriptive'},contract,q,bundle=bundle)


def test_time_not_distance():
    c,f,b=study()
    c['fields'][1].update(meaning='运行时长',unit='小时')
    a=ask('报告中每百公里耗油是多少？',c,f,b)
    assert '行驶里程' in a['text'] and not a['facts']


def test_distance_weighted_versus_route_equal():
    c,f,b=study()
    a=ask('总体每百公里耗油是多少？',c,f,b)
    assert '10.9524' in a['text'] and '升/百公里' in a['text']
    c['measurement']['aggregation']='mean_of_ratios'
    a=ask('各线路等权的每百公里耗油是多少？',c,f,b)
    assert '20' in a['text'] and a['facts']


@pytest.mark.parametrize('value',[0,None])
def test_zero_or_absent_route_distance(value):
    c,f,b=study()
    c['measurement']['aggregation']='mean_of_ratios'
    b['summary']['grouped'][-1]['mean']=value
    a=ask('各线路等权的百公里油耗是多少？',c,f,b)
    assert not a['facts'] and ('零' in a['text'] or '缺失' in a['text'])


@pytest.mark.parametrize('v,expected',[(3,6.5),(10,10)])
def test_device_average_of_means(v,expected):
    c,f,b=study()
    c['fields'][2]['meaning']='设备编号'
    b['summary']['grouped'][2]['mean']=v
    a=ask('按设备等权平均，耗油量是多少？',c,f,b)
    assert str(expected) in a['text'] and a['facts'] and '等权' in a['text']


def test_missing_entity_and_has_another_group():
    c,f,b=study()
    c['entity']='serial'
    a=ask('不同机器记录数不一样，问每台设备等权的均值。',c,f,b)
    assert '标识' in a['text'] and '先' in a['text'] and not a['facts']


def test_density_required():
    c,f,b=study()
    c.update(metric_label='材料质量',metric_unit='克')
    a=ask('质量克能直接和体积上限3毫升比较吗？',c,f,b)
    assert '密度' in a['text'] and not a['facts']


def test_different_unit_same_magnitude_and_same_unit_wrong_meaning():
    c,f,b=study()
    c['fields'][1]['meaning']='可通行的最高距离'
    a=ask('总体每百公里耗油是多少？',c,f,b)
    assert not a['facts'] and '行驶里程' in a['text']


def test_incomplete_groups_and_foreign_run_rejected():
    c,f,b=study()
    c['fields'][2]['meaning']='设备编号'
    for other in [{**b,'run_id':'other'},{**b,'summary':{**b['summary'],'row_count':4}}]:
        a=ask('耗油量按设备等权的均值是多少？',c,f,other)
        assert not a['facts'] and '完整' in a['text']


def test_known_extrema_and_mean_uncertainty_together():
    c,f,b=study()
    for key,v in [('min',3),('max',10)]:
        f['fuel / '+key]=dict(text='fuel / '+key,run_id='x',value=v,path='summary.numeric[0].'+key)
    a=ask('最小及最大是多少？这个区间描述样本还是总体均值的不确定性？',c,f,b)
    assert len(a['facts'])==2 and '置信' in a['text'] and '10' in a['text']


def test_actual_saved_partition_produces_entity_mean():
    import pandas as pd
    from causalops.general.exploration import describe, ExplorationDesign
    c,f,b=study()
    c['fields'][2]['meaning']='设备编号'
    frame=pd.DataFrame({'line':['first','first','second'],'fuel':[8.,12.,3.]})
    design=ExplorationDesign(method='descriptive',numeric=['fuel'],group='line',question='登记设备分组的耗油量分布用于审核')
    b.update(design=design.model_dump(),summary=describe(frame,design))
    a=ask('设备等权的耗油量均值是多少？',c,f,b)
    assert a['facts'][0]['value']==6.5 and frame.fuel.mean()!=6.5


def test_generic_registered_exposure_uses_unit_and_contract():
    c,f,b=study()
    c['fields'][0].update(meaning='耗电总量',unit='千瓦时')
    c['fields'][1].update(meaning='运送货物重量',unit='吨')
    c.update(metric_unit='千瓦时',metric_label='耗电总量')
    a=ask('根据报告，每吨货物耗费多少千瓦时？按登记的总量比。',c,f,b)
    assert a and '千瓦时/吨' in a['text'] and '0.109524' in a['text']


def test_unrecognized_denominator_never_returns_daily_amount():
    c,f,b=study()
    c['measurement']={}
    a=ask('每百个实际就诊人日的用量是什么？原表只有床位数，缺少实际患者人日。',c,f,b)
    assert a and not a['facts'] and '分母' in a['text']


def test_unregistered_group_type_needs_its_own_key():
    c,f,b=study()
    c['entity']='row'
    a=ask('每行抽样一次。各仓库等权平均能用记录平均吗？没有仓库标识。',c,f,b)
    assert a and not a['facts'] and '标识' in a['text'] and '先' in a['text']


def test_missing_distinct_exposure():
    c,f,b=study()
    a=ask('能用逐日活跃数合计代替跨日去重账号作分母吗？没有账号标识。',c,f,b)
    assert a and not a['facts'] and '重复' in a['text']


def test_unit_match_does_not_identify_material():
    c,f,b=study()
    c['fields'][1].update(meaning='成品运输重量',unit='吨')
    a=ask('每吨废料耗费多少升？按登记的总量比。',c,f,b)
    assert not a['facts'] and '分母对象' in a['text']
