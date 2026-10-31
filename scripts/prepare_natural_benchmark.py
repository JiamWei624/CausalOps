from pathlib import Path
import argparse,json,hashlib
import numpy as np,pandas as pd
parser=argparse.ArgumentParser(description='Prepare the frozen public/synthetic natural-language task benchmark. No model call.')
parser.add_argument('--public-data-root',type=Path,required=True,help='Root containing v090/prepared and prepared/hillstrom_men_visit.parquet')
parser.add_argument('--output',type=Path,required=True)
a=parser.parse_args();o=a.output.expanduser().resolve()
if o.drive.lower()=='c:':raise SystemExit('Choose a data-drive output outside C:.')
if o.exists() and any(o.iterdir()):raise SystemExit('Output must be empty; existing records will not be overwritten.')
o.mkdir(parents=True,exist_ok=True);public=a.public_data_root/'v090/prepared'
frames={'wine':pd.read_parquet(public/'wine_quality.parquet'),'shop':pd.read_parquet(public/'online_shoppers.parquet'),'bank':pd.read_parquet(public/'bank_marketing.parquet'),'mail':pd.read_parquet(a.public_data_root/'prepared/hillstrom_men_visit.parquet')}
for bad in (False,True):
 rng=np.random.default_rng(314159+int(bad));rows=[]
 for i in range(100):
  treated=i<50;base=rng.normal();event=pd.Timestamp('2026-01-08') if treated else pd.NaT
  for day in range(14):
   now=pd.Timestamp('2026-01-01')+pd.Timedelta(days=day);post=int(treated and day>=7)
   rows.append({'shop_id':i,'day':now,'first_policy_day':event,'active':post,'prior_scale':base,'sales':10+base+.1*day+(day*.35*int(treated) if bad else 0)+2*post+rng.normal(scale=.5)})
 frames['panel_bad' if bad else 'panel_good']=pd.DataFrame(rows)
frames['unknown']=pd.DataFrame({'field_a':np.arange(60),'field_b':np.sin(np.arange(60)),'field_c':np.tile(['a','b'],30)})
folder=o/'benchmark-data';folder.mkdir(exist_ok=True)
for name,f in frames.items():f.to_parquet(folder/(name+'.parquet'),index=False)
def definition(field,meaning,unit='',timing='unknown'):return {'field':field,'meaning':meaning,'unit':unit,'timing':timing}
wine={'analysis_unit':'葡萄酒样本','structure':'cross_section','purpose':'exploratory','outcome':'quality','predictors':['alcohol','volatile acidity','sulphates'],'metric_label':'质量评分','metric_unit':'评分单位','metric_kind':'continuous','fields':[definition('quality','感官质量评分，属于有序评分；线性模型是工作近似','分'),definition('alcohol','酒精体积分数的百分数','百分点'),definition('volatile acidity','挥发酸测量值','原始测量单位'),definition('sulphates','硫酸盐测量值','原始测量单位')],'method_facts':{'ols':{'independent_rows_reviewed':True}},'notes':'自动化数值验收按独立样本工作假设；原始来源没有证明独立抽样，不能声称已验证。'}
shop={'analysis_unit':'购物会话','structure':'cross_section','outcome':'Revenue','predictors':['BounceRates','ExitRates','Weekend'],'metric_kind':'binary','fields':[definition('Revenue','本次会话最终是否产生购买','0/1'),definition('BounceRates','会话关联的跳出率','原表比例'),definition('ExitRates','会话关联的退出率','原表比例'),definition('Weekend','会话是否发生在周末','0/1')],'method_facts':{'logit':{'independent_rows_reviewed':True}},'notes':'UCI说明每个会话属于不同用户；本任务仅作当前会话条件关联，不作进入时点预测。'}
mail={'analysis_unit':'客户','purpose':'causal','structure':'cross_section','entity':'entity_id','treatment':'assigned','control_value':'0','treated_value':'1','outcome':'visit','metric_label':'两周网站访问概率','metric_unit':'概率','metric_kind':'binary','metric_window':'邮件分配后的两周','fields':[definition('assigned','预先指定男装邮件与不发邮件的两臂随机分配','0/1'),definition('visit','两周内是否访问网站','0/1','post_treatment')],'method_facts':{'ab_test':{'assignment':'randomized'}}}
bank={'analysis_unit':'营销记录','structure':'unknown','purpose':'causal','outcome':'subscribed','predictors':['age','duration'],'metric_kind':'binary','fields':[definition('duration','已完成本次通话的时长，拨号之前不可得','秒','post_treatment'),definition('age','客户年龄','岁','pre_treatment'),definition('subscribed','本次记录的最终订阅结果','0/1','post_treatment')],'method_facts':{'logit':{'independent_rows_reviewed':False}},'notes':'来源说明同一客户可能被联系多次；没有客户唯一标识，不能确认独立行。未提供随机化。'}
panel={'analysis_unit':'门店每天','structure':'panel','purpose':'causal','outcome':'sales','entity':'shop_id','time':'day','treatment':'active','treatment_time':'first_policy_day','control_value':'0','treated_value':'1','covariates':['prior_scale'],'metric_label':'日销售指标','metric_unit':'合成销售单位/门店日','metric_kind':'continuous','metric_window':'七日前窗与七日后窗','fields':[definition('prior_scale','仅在模拟政策之前生成的固定门店规模','标准化单位','pre_treatment'),definition('active','门店在该日是否已启用政策','0/1'),definition('sales','日级连续销售结果','合成销售单位')],'method_facts':{'did':{'assignment':'observational','panel_confirmed':True,'parallel_declared':True,'no_anticipation_declared':True,'covariates_reviewed':True}},'notes':'固定种子合成数据用于核对实现；效应设定为2，并非真实商业成效。'}
unknown_mail=json.loads(json.dumps(mail));unknown_mail['fields'][0]['meaning']='该表中的两组标签；本任务未提供分组的生成方式';unknown_mail['method_facts']={'ab_test':{'assignment':'unknown'}}
future_shop=json.loads(json.dumps(shop));future_shop.update(purpose='predictive',predictors=['PageValues','ExitRates']);future_shop['fields'] += [definition('PageValues','会话结束后可整理的页面价值，进入时点不可得','原表单位','future')]
C=[]
def case(cid,split,data,q,contract,expected,policy='execute',followup='这次结果在实际业务中意味着什么？请说明幅度、单位、限制和下一步，不要重新分析。'):
 path=folder/(data+'.parquet');C.append({'id':cid,'split':split,'data':data,'data_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(frames[data]),'question':q,'dictionary':contract,'expected_methods':expected,'policy':policy,'followup':followup,'evaluation_note':'程序化审核使用预先登记的场景依据；不是独立用户试验。'})
case('dev_wine_association','development','wine','控制挥发酸和硫酸盐后，酒精度与质量评分有什么关系？请说明方向、大小和不确定性。',wine,['ols'])
case('dev_mail_visit','development','mail','随机发送男装邮件是否增加了客户在随后两周访问网站的概率？增加多少，能否直接推广？',mail,['ab_test'])
case('dev_bank_leakage','development','bank','想在拨号之前预测客户是否订阅，能把本次通话时长作为输入吗？请检查信息的可用时间，不要拟合模型。',bank,[],policy='no_estimation')
case('dev_missing_context','development','unknown','这几个字段能说明产品上线提高了收入吗？预计可以赚多少？目前没有字段含义或分组依据。',{},[],policy='no_estimation')
case('holdout_data_audit','holdout','bank','先检查这份营销表的缺失、重复和数据结构，不要建立模型。',{},['descriptive'],policy='profile_or_describe')
case('holdout_shopper_association','holdout','shop','跳出率、退出率和是否周末分别与本次会话最终购买有什么关系？只解释条件关联，不声称具备预测效果。',shop,['logit'])
case('holdout_wine_association','holdout','wine','把挥发酸与硫酸盐纳入考虑后，酒精度高一单位时评分平均相差多少？这个差异能否解释成提高酒精度的收益？',wine,['ols'])
spend=json.loads(json.dumps(mail));spend.update(outcome='spend',metric_label='两周人均支出',metric_unit='美元/客户',metric_kind='continuous');spend['fields'].append(definition('spend','随后两周客户实际支出','美元','post_treatment'))
case('holdout_mail_spend','holdout','mail','男装邮件的随机分配对两周人均支出有多大影响？请区分估计差异与实际利润。',spend,['ab_test'])
case('holdout_mail_assignment_unknown','holdout','mail','这两组客户两周访问率不同，能否断定邮件造成了差异？本任务还不知道两组如何形成，请先明确缺少什么。',unknown_mail,[],policy='no_estimation')
case('holdout_shopper_future','holdout','shop','在用户刚进入网站时预测会不会购买，使用会话结束后的页面价值是否合适？不要训练模型。',future_shop,[],policy='no_estimation')
case('holdout_panel_good','holdout','panel_good','部分门店同一天启用活动，其他门店一直未启用。利用活动前后的每日销售和同期未启用门店，评估活动后的平均变化。',panel,['did'])
case('holdout_panel_bad','holdout','panel_bad','比较活动门店和未活动门店在政策前后的每日销售变化，同时检查政策之前的走势；如果不满足要求，不得声称政策产生了增长。',panel,['did'],policy='execute_downgrade')
payload={'version':1,'frozen_at':'2026-11-01','development_cases':4,'holdout_cases':8,'sampling':'fixed local public datasets plus fixed-seed simulations; no task-specific method words in user questions','scope':'method selection, permission boundaries, numerical fidelity, result explanation and export; not independent human usability','cases':C}
encoded=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode();(o/'frozen-benchmark.json').write_bytes(encoded);(o/'frozen-benchmark.sha256').write_text(hashlib.sha256(encoded).hexdigest(),encoding='utf-8');print(json.dumps({'frozen_cases':len(C),'development':4,'holdout':8,'sha256':hashlib.sha256(encoded).hexdigest(),'rows':{k:len(v) for k,v in frames.items()}},ensure_ascii=False))
