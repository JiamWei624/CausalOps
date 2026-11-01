from pathlib import Path
import io
import numpy as np,pandas as pd,pytest
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.sample_data import create_wine_task,example_context,wine_example
from causalops.application.research_service import ResearchService
from causalops.application.guided_intake import GuidedIntake
from causalops.general.exploration import ExplorationDesign,compute
from causalops.general.exploration_report import figures
from causalops.application.task_conclusions import build_task_conclusion

@pytest.fixture
def app(tmp_path):
 a=AssistantWorkspace(GeneralWorkspace(tmp_path));return a,ResearchService(a)

def test_example_context_is_content_bound_not_filename(app):
 a,s=app;raw,info=wine_example();sid=s.create_task(payload=raw,name='renamed.csv',separator=';');assert example_context(a,sid)['id']=='uci_wine_red'
 fake=s.create_task(payload=b'quality,x\n1,2\n2,3\n',name='winequality-red.csv');assert example_context(a,fake) is None
 changed=pd.read_csv(io.BytesIO(raw),sep=';');changed.loc[0,'quality']=9
 sid2=s.create_task(payload=changed.to_csv(index=False).encode(),name='winequality-red.csv');assert example_context(a,sid2) is None

def test_one_click_presets_register_only_documented_metadata(app):
 a,s=app;sid=create_wine_task(a);g=GuidedIntake(s)
 with pytest.raises(DesignError):g.use_example(sid)
 req=g.use_example(sid,human_confirmed=True);body=s.contracts.latest(sid)['body']
 assert body['outcome']=='quality' and body['metric_unit']=='分' and len(body['fields'])==12
 assert body['structure']=='unknown' and body['purpose']=='exploratory' and not body['method_facts']
 assert req['mode']=='plan' and not a.plans(sid) and not a.completed_runs(sid) and not a.session(sid).get('external_consent')

def test_presets_cannot_overwrite_custom_research(app):
 a,s=app;sid=create_wine_task(a);g=GuidedIntake(s);g.save_unit(sid,'自定义单位',human_confirmed=True);old=s.contracts.latest(sid);body=old['body'];body['outcome']='alcohol';s.contracts.save(sid,body,expected_sha=old['sha'],human_confirmed=True)
 current=s.contracts.latest(sid)
 with pytest.raises(DesignError,match='自定义'):g.use_example(sid,expected_sha=current['sha'],human_confirmed=True)
 assert s.contracts.latest(sid)['sha']==current['sha']

def test_unknown_upload_cannot_use_example_defaults(app):
 a,s=app;sid=s.create_task(payload=b'x,y\n1,2\n2,3\n',name='outside.csv')
 with pytest.raises(DesignError):GuidedIntake(s).use_example(sid,human_confirmed=True)
 assert s.contracts.latest(sid) is None

@pytest.mark.parametrize('values',[[0,1,1,0],[3,4,4,6],[1,1,1,1]])
def test_discrete_chart_preserves_exact_values_and_frequency(values):
 b=compute(pd.DataFrame({'score':values}),ExplorationDesign(question='分析实际评分的频数',numeric=['score']))
 h=b['summary']['histograms'][0];f=figures(b,focus='score')['分布_score']
 assert h['value_type']=='discrete' and sum(f.data[0].y)==len(values) and list(f.data[0].x)==sorted(set(values))
 assert f.layout.xaxis.tickmode=='array'

def test_continuous_chart_keeps_histogram():
 b=compute(pd.DataFrame({'x':[.12,.25,.79,.89]}),ExplorationDesign(question='分析连续数值的分布',numeric=['x']))
 assert 'value_type' not in b['summary']['histograms'][0]

def test_long_categories_use_horizontal_bars_and_full_hover():
 names=['A'*50]*3+['B'*45]*2+[None]
 b=compute(pd.DataFrame({'label':names}),ExplorationDesign(question='分析长类别标签的分布',categorical=['label']))
 f=figures(b,focus='label')['频数_label'];assert f.data[0].orientation=='h' and sum(f.data[0].x)==6
 assert max(map(len,f.data[0].y))<=26 and any('A'*50 in str(v) for v in f.data[0].customdata)

def test_correlation_chart_is_primary():
 f=pd.DataFrame({'a':range(30),'b':np.arange(30)**2,'c':np.sin(np.arange(30))})
 b=compute(f,ExplorationDesign(question='分析三个变量的相关关系',method='correlation',numeric=list(f)))
 assert next(iter(figures(b)))=='相关矩阵'

def test_regression_chart_uses_saved_coefficients_and_interval():
 rng=np.random.default_rng(5);x=rng.normal(size=80);f=pd.DataFrame({'x':x,'y':2*x+rng.normal(size=80)})
 b=compute(f,ExplorationDesign(question='估计条件线性关联模型',method='ols',outcome='y',predictors=['x'],independent_rows_reviewed=True,allow_complete_case=True))
 figs=figures(b);chart=figs['关联系数'];row=b['regression']['coefficients'][1]
 assert next(iter(figs))=='关联系数' and chart.data[0].x[0]==row['coefficient'] and chart.data[0].error_x.array[0]==pytest.approx(row['ci95_high']-row['coefficient'])

def execute(s,sid,question='分析结果字段的分布与缺失'):
 f=s.start(sid,question,mode='plan');p=s.a.get_plan(f['plan_id']);s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True);return s.a.completed_runs(sid)[0]['run_id']

def bind(s,sid,target,kind='unknown'):
 g=GuidedIntake(s);g.save_unit(sid,'一条观测记录',human_confirmed=True);row=s.contracts.latest(sid);g.save_target(sid,target,target,'',expected_sha=row['sha'],human_confirmed=True)
 row=s.contracts.latest(sid);body=row['body'];body['metric_kind']=kind;s.contracts.save(sid,body,expected_sha=row['sha'],human_confirmed=True)

@pytest.mark.parametrize('values,rate',[([0,1,1,0],'50%'),([0,0,0,0],'0%'),([1,1,1,1],'100%')])
def test_binary_target_states_proportion_not_uplift(app,values,rate):
 a,s=app;sid=s.create_task(payload=pd.DataFrame({'event':values*8}).to_csv(index=False).encode(),name='outside.csv');bind(s,sid,'event','binary');rid=execute(s,sid);v=build_task_conclusion(a,sid,rid)
 assert '取值为1' in v['sections']['magnitude'] and rate in v['sections']['magnitude'] and '不表示相对基线提升' in v['sections']['magnitude']

def test_fractional_values_are_not_binary_even_if_user_label_says_binary(app):
 a,s=app;sid=s.create_task(payload=pd.DataFrame({'event':[.99,.99,.99]}).to_csv(index=False).encode(),name='outside.csv');bind(s,sid,'event','binary');rid=execute(s,sid)
 assert '取值为1' not in build_task_conclusion(a,sid,rid)['sections']['magnitude']

def test_declared_time_is_not_ignored_in_local_description(app):
 a,s=app;f=pd.DataFrame({'date':['2020-01-01','2020-04-01','2020-07-01'],'value':[2.,3.,4.]});sid=s.create_task(payload=f.to_csv(index=False).encode(),name='outside.csv');bind(s,sid,'value');row=s.contracts.latest(sid);b=row['body'];b.update(time='date',analysis_unit='一个季度');s.contracts.save(sid,b,expected_sha=row['sha'],human_confirmed=True);rid=execute(s,sid)
 run=a.ex.load(rid);assert run['design']['date']=='date' and run['design']['frequency']=='Q' and len(run['summary']['trend'])>=3
 assert next(iter(figures(run,focus='value')))=='时间汇总_value'

@pytest.mark.parametrize('separator',[',',';','\t'])
def test_upload_auto_separator_preserves_columns(separator):
 from causalops.general.service import read_table
 data=pd.DataFrame({'x':[1,2],'y':['one','two']});raw=data.to_csv(index=False,sep=separator).encode()
 assert read_table(raw,'outside.csv',separator='auto').shape==(2,2)

def test_ambiguous_csv_needs_explicit_choice():
 from causalops.general.service import read_table
 with pytest.raises(DesignError,match='无法唯一识别'):read_table(b'a;b,c\n1;2,3\n4;5,6\n','ambiguous.csv',separator='auto')
 assert read_table(b'a;b,c\n1;2,3\n4;5,6\n','ambiguous.csv',separator=';').shape==(2,2)


def test_discovery_questions_follow_declared_target_not_first_columns():
 from causalops.application.question_discovery import local_suggestions
 f=pd.DataFrame({'unrelated':[1,2,3],'score':[5,6,7],'date':['2020-01-01','2020-01-02','2020-01-03']})
 v=local_suggestions(f,{'outcome':'score','metric_label':'评分','time':'date'})
 assert all('score' in d.fields for d in v.directions) and 'score' in v.directions[0].question and len(v.directions)==3

def test_category_target_does_not_get_numeric_correlation_suggestion():
 from causalops.application.question_discovery import local_suggestions
 v=local_suggestions(pd.DataFrame({'x':[1,2,3],'target':['a','b','a']}),{'outcome':'target'})
 assert len(v.directions)==1 and v.directions[0].fields==['target']


@pytest.mark.parametrize('question',['我还可以研究什么？','这份数据可以分析哪些问题？','当前表能回答什么问题？'])
def test_natural_discovery_after_result_does_not_repeat_old_answer(app,question):
 a,s=app;sid=s.create_task(payload=b'x,y\n1,3\n2,4\n3,7\n',name='outside.csv')
 bind(s,sid,'y');execute(s,sid);before=len(a.completed_runs(sid));f=s.start(sid,question)
 assert s.output(f['id'],'discovery') and s.output(f['id'],'route')['route']=='explore' and len(a.completed_runs(sid))==before


def test_selected_correlation_suggestion_keeps_both_fields_and_waits(app):
 a,s=app;sid=create_wine_task(a);GuidedIntake(s).use_example(sid,human_confirmed=True)
 d=s.start(sid,'我还可以研究什么？');f=s.start(sid,'采用第2项建议',mode='plan',parent_flow_id=d['id']);p=a.get_plan(f['plan_id'])
 assert f['status']=='awaiting_review' and set(p['plan']['steps'][0]['config']['numeric'])==set(s.output(d['id'],'discovery')['directions'][1]['fields']) and not a.completed_runs(sid)
 assert f['request']['conversation_ref']['selected_direction']['ordinal']==2

def test_simple_date_confirmation_rejects_numeric_year_and_preserves_valid_date(app):
 a,s=app;f=pd.DataFrame({'date':['2020-01-01','2020-04-01'],'year':[2020,2020],'value':[2,3]});sid=s.create_task(payload=f.to_csv(index=False).encode(),name='dates.csv');g=GuidedIntake(s);g.save_unit(sid,'一个季度',human_confirmed=True);v=s.contracts.latest(sid)
 with pytest.raises(DesignError,match='实际日期'):g.save_target(sid,'value',expected_sha=v['sha'],human_confirmed=True,time_field='year')
 g.save_target(sid,'value',expected_sha=v['sha'],human_confirmed=True,time_field='date');assert s.contracts.latest(sid)['body']['time']=='date'


def test_changing_date_drops_new_contract_facts_without_rewriting_history(app):
 a,s=app;f=pd.DataFrame({'date':['2020-01-01','2020-04-01'],'other_date':['2021-01-01','2021-04-01'],'value':[2,3]});sid=s.create_task(payload=f.to_csv(index=False).encode(),name='dates.csv');g=GuidedIntake(s);g.save_unit(sid,'一季度',human_confirmed=True);v=s.contracts.latest(sid);g.save_target(sid,'value',expected_sha=v['sha'],human_confirmed=True,time_field='date')
 v=s.contracts.latest(sid);b=v['body'];b['method_facts']={'ols':{'independent_rows_reviewed':True}};s.contracts.save(sid,b,expected_sha=v['sha'],human_confirmed=True);old=s.contracts.latest(sid)
 g.save_target(sid,'value',expected_sha=old['sha'],human_confirmed=True,time_field='other_date')
 assert not s.contracts.latest(sid)['body']['method_facts'] and s.contracts.versions(sid)[1]['body']['method_facts']['ols']['independent_rows_reviewed']


@pytest.mark.parametrize('periods',[4,203])
def test_time_chart_retains_observations_with_sparse_ticks_and_readable_units(periods):
 import copy
 dates=pd.date_range('1959-01-01',periods=periods,freq='QS')
 frame=pd.DataFrame({'date':dates,'value':np.arange(periods,dtype=float)+1000})
 design=ExplorationDesign(question='分析季度数值的分布和变化',method='descriptive',numeric=['value'],date='date',frequency='Q')
 bundle=compute(frame,design);before=copy.deepcopy(bundle)
 plot=figures(bundle,focus='value',labels={'value':'实际GDP'},units={'value':'十亿美元（2005年链式价格，季调年率，原始长单位说明）'})['时间汇总_value']
 assert len(plot.data[0].x)==periods and list(plot.data[0].y)==list(frame['value'])
 assert len(plot.layout.xaxis.tickvals)<=9 and plot.layout.xaxis.tickangle==0
 assert plot.layout.yaxis.title.text=='均值' and '单位：' in plot.layout.title.text and '季调年率' in plot.layout.title.text
 assert bundle==before
