"""Small, portable product demo; live research UI remains a separate entry point."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import pandas as pd
import streamlit as st
from causalops.demo_domains import synthetic_scenario
from causalops.config import workspace_root
from causalops.execution import _data_fingerprint
from causalops.research import ResearchRepository,RevisionSource,DraftStatus
from causalops.schemas import CausalSpec,ResultBundle
from causalops.agent import AgentRunResult
from causalops.ui.controller import run_versioned_workflow,run_versioned_association_workflow
from causalops.reporting import render_html_report
from causalops.ui.app import _show_result_qa
from causalops.metadata.presentation_zh import claim_label_zh, diagnostic_rows_zh, diagnostics_for_display
from causalops.results.interpretation import public_metric_definition, business_sections
from causalops.visualization import build_regression_diagnostic_figures,build_did_diagnostic_figures
from causalops.ui.showcase_widgets import style,flow,design_summary,show_conclusion

ROOT=Path(__file__).resolve().parents[3]
CATALOG=Path(os.environ.get('CAUSALOPS_PUBLIC_CATALOG','E:/ugc_ai_portfolio_public_data/prepared/catalog.json'))
DB=Path(os.environ.get('CAUSALOPS_DEMO_DB',str(workspace_root()/'examples/state/causalops.sqlite3')))
OUTPUT=DB.parent.parent/'runs'
SYNTHETIC={'营销随机实验':'ab','营销CUPED':'cuped','零效应实验':'null_ab','政策DID':'did','非平行趋势压力场景':'did_bad_trend',
           '服务PSM':'psm','服务IPW':'ipw','服务DoubleML':'double_ml','隐藏混杂压力场景':'hidden_confounding'}


def render_demo(preset=None):
 style()
 st.title('政策实施前后比较' if preset in ('did','did_bad_trend') else '分析示例')
 st.caption('依次核对方案、确认运行，再查看估计与诊断。每种情形的分析记录单独保存。')
 requested=preset or st.query_params.get('case','')
 mode=('合成数据' if preset in SYNTHETIC.values() else '公开真实数据') if preset else st.radio('演示数据',['合成数据','公开真实数据'],index=1 if requested and requested not in SYNTHETIC.values() else 0,horizontal=True)
 if mode=='合成数据':
  if preset:
   name=preset
  else:
   label=st.selectbox('选择场景',list(SYNTHETIC),index=list(SYNTHETIC.values()).index(requested) if requested in SYNTHETIC.values() else 0);name=SYNTHETIC[label]
  frame,spec,tau=synthetic_scenario(name,321001)
  kind='synthetic';scope='association_only' if name=='hidden_confounding' else 'approved'
  source='固定种子的已知数据生成过程';note=f'合成数据；设定处理效应为{tau}。坏趋势与隐藏混杂用于演示拒绝不可靠因果结论。'
 else:
  if not CATALOG.is_file():
   st.info('尚未下载公开数据。请运行scripts/delivery/download_public_data.py及复现说明中的准备步骤；合成演示可直接使用。');return
  catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
  ids=[x['id'] for x in catalog];case_id=st.selectbox('选择公开数据分析',ids,index=ids.index(requested) if requested in ids else 0,format_func=lambda k:next(x['title'] for x in catalog if x['id']==k),disabled=bool(preset))
  item=next(x for x in catalog if x['id']==case_id);path=Path(item['path']).resolve()
  allowed=Path('E:/ugc_ai_portfolio_public_data/prepared').resolve()
  if not path.is_relative_to(allowed) or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
   st.error('登记路径或数据指纹不符，停止加载。');return
  frame=pd.read_parquet(path);spec=CausalSpec.model_validate(item['spec']);kind='user_provided';scope=item['scope']
  source=item['source'];note=item['description'];name=case_id;tau=None
  st.caption('公开真实数据只在本地分析与展示；此演示入口不向外部模型发送其内容。')
 if preset in ('did','did_bad_trend'):
  note='合成面板；设定效应为 1.8。'+('当前情形：两组处理前趋势相同。' if preset=='did' else '当前情形：两组处理前趋势不同。')
 st.info(note)
 left,right=st.columns(2);left.metric('观测行数',f'{len(frame):,}');right.metric('字段数',len(frame.columns))
 st.code(' | '.join(frame.columns))
 with st.expander('研究设计与数据来源'):
  st.json(spec.model_dump(mode='json'));st.write(source)
 fingerprint=_data_fingerprint(frame);title=f'portfolio-demo:{name}:{fingerprint[:12]}'
 repo=ResearchRepository(DB);session=next((s for s in repo.list_sessions() if s.title==title),None)
 if session is None:
  session=repo.create_session(title=title,dataset_fingerprint=fingerprint,row_count=len(frame),column_schema={c:str(t) for c,t in frame.dtypes.items()})
  repo.create_revision(session.session_id,spec,source=RevisionSource.SYSTEM_INITIAL,change_reason='演示初始设计，待审核',activate=True,status=DraftStatus.PENDING_REVIEW)
 session=repo.get_session(session.session_id);rev=repo.get_revision(session.current_draft_revision_id)
 flow(bool(repo.list_analysis_runs(revision_id=rev.revision_id,dataset_version_id=rev.dataset_version_id)))
 st.subheader('审核分析方案')
 design_summary(rev.spec)
 st.caption(f'会话 {session.session_id[:12]}｜草案 V{rev.version_number}｜数据指纹 {fingerprint[:12]}')
 question=st.text_area('研究问题',value=rev.spec.question,key='demo_question_'+title)
 st.caption('这里只改问题表述，统计指标和方法保持登记设定；改变研究变量请使用完整研究页面。')
 if st.button('保存为候选研究问题'):
  if not question.strip():st.error('研究问题不能为空。')
  elif question.strip()==rev.spec.question.strip():st.info('问题未变化，没有创建重复版本。')
  else:
   candidate=repo.create_revision(session.session_id,rev.spec.model_copy(update={'question':question.strip()}),source=RevisionSource.USER_EDIT,change_reason='演示中的用户编辑')
   st.session_state['demo_candidate_'+title]=candidate.revision_id
 cid=st.session_state.get('demo_candidate_'+title)
 if cid:
  candidate=repo.get_revision(cid)
  if candidate.status==DraftStatus.DRAFT:
   st.dataframe([{'字段':'研究问题','修改前':rev.spec.question,'修改后':candidate.spec.question}],hide_index=True)
   stale=candidate.parent_revision_id!=rev.revision_id
   if stale:st.warning('该候选基于旧版本，需重新生成候选。')
   if st.button('接受候选但不批准',disabled=stale):
    repo.accept_candidate(cid);st.session_state.pop('demo_candidate_'+title,None);st.rerun()
 existing=repo.list_analysis_runs(revision_id=rev.revision_id,dataset_version_id=rev.dataset_version_id)
 st.progress(1.0 if existing else .35,text='已有保存结果：可直接阅读结论和提问，无需重新运行。' if existing else '下一步：核对研究设计，确认适用范围后运行。')
 if existing:st.info('已恢复已有运行。仅在确需重新计算时点击下方运行按钮；改变研究问题应先保存并接受候选。')
 with st.form('run_review_'+rev.revision_id):
  reviewed=st.checkbox('我已核对当前字段、设计与适用范围；理解合成演示和真实业务效果的区别',key='demo_review_'+rev.revision_id)
  submitted=st.form_submit_button('确认并运行当前版本',type='primary')
 requested_run = submitted and reviewed
 if submitted and not reviewed:
  st.warning('尚未确认研究设计。本次没有执行；请核对上方设计并勾选确认后提交。')
 if requested_run:
  if scope=='association_only':
   repo.authorize_association_analysis(rev.revision_id,authorized_by='demo_user_button',authorization_note='点击确认仅关联分析，不确认因果识别假设。')
   result=run_versioned_association_workflow(frame,repo,session_id=session.session_id,revision_id=rev.revision_id,output_dir=OUTPUT/name,
          source_description=source,data_kind=kind,study_context={'sample_note':note,'metric_definition':public_metric_definition(name)})
  else:
   if rev.status!=DraftStatus.APPROVED:
    repo.approve_revision(rev.revision_id,approved_by='demo_user_button',checklist={'variables':True,'covariates':True,'assumptions':True})
   result=run_versioned_workflow(frame,repo,session_id=session.session_id,revision_id=rev.revision_id,output_dir=OUTPUT/name,source_description=source,data_kind=kind,study_context={'sample_note':note,'metric_definition':public_metric_definition(name)})
 runs=repo.list_analysis_runs(revision_id=rev.revision_id,dataset_version_id=rev.dataset_version_id)
 if not runs:
  st.caption('下一步：先勾选上方核对框，再点击“确认并运行当前版本”。')
  st.info('当前版本尚未运行。保存候选、接受候选均不会自动计算或继承旧版本批准。');return
 run=runs[0];bundle=ResultBundle.model_validate_json(Path(run.result_bundle_path).read_text(encoding='utf-8'))
 trace=Path(run.result_bundle_path).parent.parent/'traces'/f'agent-run-{run.run_id}.json'
 result=AgentRunResult(bundle=bundle,report_path=Path(run.report_path),html_report_path=Path(run.report_path).with_suffix('.html'),trace_path=trace)
 from causalops.ui.reading import landmark
 landmark('result',move=requested_run)
 st.subheader('分析结果', anchor='policy-result')
 st.write(rev.spec.question)
 show_conclusion(bundle)
 st.markdown('**估计值与诊断**')
 st.caption('刷新或重新打开页面会恢复该运行，不会自动重跑。运行编号：'+run.run_id)
 a,b,c=st.columns(3);a.metric('估计值',f'{bundle.estimate.estimate:.6g}');b.metric('实际估计行数',f'{bundle.estimate.sample_size:,}');c.metric('结论等级',claim_label_zh(bundle.claim_level))
 with st.expander('查看诊断：为什么允许或限制这个结论',expanded=bundle.claim_level.value in ('associational','descriptive')):
  st.dataframe(diagnostic_rows_zh(diagnostics_for_display(bundle)),hide_index=True,width='stretch')
 for title,figure in {**build_regression_diagnostic_figures(bundle),**build_did_diagnostic_figures(bundle)}.items():st.plotly_chart(figure,key='demo_'+title)
 for path,label,mime in [(result.html_report_path,'下载完整分析报告','text/html'),(Path(run.result_bundle_path),'下载运行证据','application/json'),(trace,'下载执行轨迹','application/json')]:
  if path.is_file():st.download_button(label,(render_html_report(bundle).encode('utf-8') if mime=='text/html' else path.read_bytes()),file_name=path.name,mime=mime)
 st.session_state['causalops_external_model_allowed']=kind=='synthetic'
 _show_result_qa(repo,session.session_id,result)

def main():
 st.set_page_config(page_title='CausalOps 可复现演示台',layout='wide')
 render_demo()

if __name__=='__main__':main()