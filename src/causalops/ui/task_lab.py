from pathlib import Path
import os,json,hashlib
import streamlit as st
from causalops.evaluation.human_timing import HumanTimingStore,TimingStateError
from causalops.evaluation.tasks import validate_task_reference
from causalops.metadata.presentation_zh import claim_label_zh
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/task-evaluation-20261030'
DB=Path(os.environ.get('CAUSALOPS_HUMAN_TIMING_DB',str(OUT/'human-timing/state.sqlite3')))
CONDITION_ZH={'script':'标准脚本','agent':'Agent界面'}
STATE_ZH={'running':'计时中','paused':'已暂停','submitted':'已提交','abandoned':'已放弃'}

def main():
 st.set_page_config(page_title='CausalOps 任务验收与人工计时',layout='wide')
 st.title('CausalOps 任务验收与人工计时')
 st.caption('机器耗时、真实模型等待与人工操作计时分别记录；尚未采集的人工节省时间不会自动生成。所有记录在E盘。')
 catalog_path=OUT/'task-catalog.json'
 if not catalog_path.is_file():
  catalog_path=ROOT/'examples/task-evaluation/task-catalog.json'
  if not catalog_path.is_file():st.info('任务目录尚未生成，请先完成固定任务验收。');return
  st.caption('正在显示交付时的任务定义和历史机器验收，不是本机新跑的性能成绩。')
 catalog=json.loads(catalog_path.read_text(encoding='utf-8'));names={x['task_id']:x['title'] for x in catalog};store=HumanTimingStore(DB)
 summary_path=OUT/'verified-v2/benchmark-summary.json'
 if not summary_path.is_file():summary_path=ROOT/'examples/task-evaluation/benchmark-summary.json'
 summary=json.loads(summary_path.read_text(encoding='utf-8'))
 a,b,c=st.columns(3);a.metric('机器完整任务通过',f"{summary['passed_measured_runs']}/{summary['measured_runs']}");b.metric('已提交人工记录',store.export()['submitted_count']);c.metric('人工节省时间','尚未完成验证')
 with st.expander('机器脚本与Agent的公平对照'):
  st.write('两者输出相同范围的报告、证据和轨迹，并包含授权检查、本地结果问答和关闭重开。数据读取、解释器启动和人的审核时间不在这组机器时间内。结果不能替代人工提效研究。')
  st.dataframe([{'任务':names.get(x['task_id'],x['task_id']),'脚本中位秒':round(x['script_median_seconds'],4),'Agent中位秒':round(x['agent_median_seconds'],4),'配对数':x['complete_pairs']} for x in summary['cases']],hide_index=True)
 st.subheader('1. 选择任务与操作条件')
 alias=st.text_input('试用别名（英数字，不填真实姓名）',value='participant_001',max_chars=32)
 active=next((x for x in store.list_trials(alias) if x['status'] in ('running','paused')),None)
 ids=[x['task_id'] for x in catalog];task_id=st.selectbox('固定任务',ids,index=ids.index(active['task_id']) if active else 0,disabled=bool(active),format_func=lambda k:next(x['title'] for x in catalog if x['task_id']==k));task=next(x for x in catalog if x['task_id']==task_id)
 st.write(task['question']);st.caption(f"样本行数 {task['rows']:,}｜方法 {task['method']}｜数据指纹 {task['data_sha256'][:16]}")
 conditions=['script','agent'];suggested=conditions[hashlib.sha256((alias+task_id).encode()).digest()[0]%2]
 st.caption('建议首次条件：'+('标准脚本' if suggested=='script' else 'Agent界面')+'。下一轮使用另一条件；同人重复任务仍可能有学习效应。')
 condition=st.radio('本轮操作条件',conditions,index=conditions.index(active['condition'] if active else suggested),disabled=bool(active),format_func=lambda x:'标准脚本操作' if x=='script' else 'Agent界面操作',horizontal=True)
 with st.expander('相同的完成标准与计时规则',expanded=True):
  st.write('从点击开始，到你读懂结果并提交估计值、区间、结论等级和一句实际含义/建议。暂停时间单独排除；没有观察员验证，数据只能称为自助试用记录。')
  st.write('两种条件均使用同一预登记数据、方法和完整报告。脚本已预先写好；不能将结果称为“从零编程相对Agent节省时间”。业务解释另需人工复核。')
  st.write('标准脚本：在PowerShell执行下面命令。Agent：打开对应演示，核对设计后运行，并阅读同样的完整结论。')
  st.code(f'python "{ROOT / "scripts/reference_task.py"}" --task {task_id} --confirm-design',language='powershell')
  st.link_button('打开此任务的Agent演示',f"http://127.0.0.1:8503/?case={task['demo_case']}")
 if st.button('开始本轮计时',type='primary',disabled=bool(active)):
  try:
   validate_task_reference(task)
   trial=store.start(alias,task_id,condition,task['reference']);st.query_params['trial']=trial;st.rerun()
  except (ValueError,OSError) as e:st.error(str(e))
 trial_id=st.query_params.get('trial')
 if not trial_id:
  active=next((x for x in store.list_trials(alias) if x['status'] in ('running','paused')),None)
  if active:trial_id=active['trial_id']
 if trial_id:
  try:trial=store.get(trial_id)
  except TimingStateError as e:st.error(str(e));return
  if trial['participant']!=alias:st.info('当前链接中的试验属于另一别名；请恢复对应别名。');return
  st.subheader('2. 本轮计时与提交')
  st.caption(f"记录 {trial_id[:12]}｜任务 {trial['task_id']}｜条件 {CONDITION_ZH[trial['condition']]}｜状态 {STATE_ZH[trial['status']]}")
  st.metric('已累计有效秒数',f"{trial['active_elapsed_seconds']:.1f}")
  st.caption('显示截至本次页面刷新；实际提交会按服务器时间重新计算，不需要保持页面频繁刷新。')
  if trial['status'] in ('running','paused'):
   x,y,z=st.columns(3)
   if x.button('暂停计时' if trial['status']=='running' else '恢复计时'):
    (store.pause if trial['status']=='running' else store.resume)(trial_id);st.rerun()
   if y.button('刷新显示'):st.rerun()
   if z.button('放弃本轮（保留记录）'):store.abandon(trial_id);st.rerun()
   with st.form('timed_answer_'+trial_id):
    unit=st.selectbox('填写数值单位',['raw','percentage_points'],format_func=lambda x:'原始系数单位' if x=='raw' else '百分点（仅二元结果）')
    e=st.number_input('主估计值',value=None,format='%.6f');lo=st.number_input('置信区间下界',value=None,format='%.6f');hi=st.number_input('置信区间上界',value=None,format='%.6f')
    claim=st.selectbox('允许的结论等级',['请选择','identified_causal','reduced_form','associational','descriptive'],format_func=lambda x:x if x=='请选择' else claim_label_zh(x))
    explanation=st.text_area('一句实际含义和下一步建议（业务解释待人工复核）')
    steps=st.number_input('你自报的操作步骤数（可留空）',value=None,min_value=0,step=1)
    rewrites=st.number_input('你自报的修改次数（可留空）',value=None,min_value=0,step=1)
    used_ai=st.checkbox('本轮使用了模型问答或额外AI工具（自报）')
    tool_notes=st.text_input('使用工具名称/模型版本（可留空，不填密钥）',max_chars=200)
    submit=st.form_submit_button('提交答案并停止计时')
   if submit:
    try:
     store.submit(trial_id,{'unit':unit,'estimate':e,'lower':lo,'upper':hi,'claim':claim,'explanation':explanation,'self_reported_steps':steps,'self_reported_rewrites':rewrites,'self_reported_used_ai':used_ai,'self_reported_tools':tool_notes});st.rerun()
    except TimingStateError as er:st.error(str(er))
  elif trial['status']=='submitted':
   score=json.loads(trial['score_json']);st.success('计时记录已保存。' if score['objective_passed'] else '记录已保存，但数值或结论等级有待修正；本轮结果保留。')
   st.dataframe([{'核验项':{'estimate':'主估计','lower':'区间下界','upper':'区间上界','claim':'结论等级'}[k],'结果':'通过' if v else '待修正'} for k,v in score['objective_checks'].items()],hide_index=True);st.info('业务解释尚待人工复核；自报操作数和耗时不能作为独立观察证据。')
 st.subheader('3. 回看与导出')
 rows=store.list_trials(alias)
 st.dataframe([{'任务':names.get(x['task_id'],x['task_id']),'条件':CONDITION_ZH[x['condition']],'状态':STATE_ZH[x['status']],'有效秒数':round(x['active_elapsed_seconds'],2)} for x in rows],hide_index=True)
 st.download_button('导出当前别名的原始计时记录',json.dumps({'trials':rows,'timing_source':'self_operated_not_independent_observer','business_review_pending':True},ensure_ascii=False,indent=2),file_name='human-timing-records.json',mime='application/json')

if __name__=='__main__':main()