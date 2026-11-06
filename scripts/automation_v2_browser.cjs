
/* Real Streamlit/Edge acceptance. All research actions go through visible UI.
   Controller-only fault injection and read-only scoring are separate from actions. */
const fs=require('fs'),path=require('path'),net=require('net'),cp=require('child_process');
const {chromium}=require('playwright');
const REPO=path.resolve(__dirname,'..'),PY=process.env.CAUSALOPS_TEST_PYTHON||'python';
const INSTALLED=process.env.CAUSALOPS_TEST_INSTALLED==='1';
const APP_ENTRY=process.env.CAUSALOPS_TEST_APP_ENTRY||path.join(REPO,'src/causalops/ui/workbench.py');
const ROOT=path.resolve(process.argv[2]||'automation-v2-browser-evidence');
fs.mkdirSync(ROOT,{recursive:false});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn,ms=60000){const until=Date.now()+ms;while(Date.now()<until){if(await fn())return;await sleep(200)}throw Error('condition timeout');}
async function port(){
 for(let i=0;i<20;i++){
  const s=net.createServer(),p=23000+Math.floor(Math.random()*16000);
  try{await new Promise((resolve,reject)=>{s.once('error',reject);s.listen(p,'127.0.0.1',resolve)});await new Promise(r=>s.close(r));return p}catch{}
 }
 throw Error('no test server port available');
}
const fixture=String.raw`
import os,time,json,runpy
from pathlib import Path
from unittest.mock import patch
from causalops.application.automation_coordinator import BoundedCoordinator
from causalops.general.service import DesignError
mode=os.environ.get("AUTOMATION_ACCEPTANCE_MODE","normal")
folder=Path(os.environ["AUTOMATION_ACCEPTANCE_FOLDER"])
audit=BoundedCoordinator._audit
def controlled_audit(self,t):
    if mode!="insufficient":return audit(self,t)
    p,f=self._binding(t);f=f.copy();f.loc[0,"visit"]=float("nan")
    (folder/"fault.json").write_text(json.dumps({"injection":"one_missing_visit_in_audit_frame","private_data":False}),encoding="utf8")
    with patch.object(self,"_binding",return_value=(p,f)):return audit(self,t)
def boundary(self,point,tid,step):
    if point!="stat_committed" or step!="S02":return
    if mode=="pause":
        (folder/(tid+".ready")).write_text("committed real S02; waiting test release",encoding="utf8")
        deadline=time.monotonic()+90
        while not (folder/(tid+".release")).exists():
            if time.monotonic()>deadline:raise TimeoutError("controlled boundary wait expired")
            time.sleep(.1)
    if mode=="uncertain":
        with self.ws.connection() as c:
            row=c.execute("SELECT path FROM exploration_runs ORDER BY rowid DESC LIMIT 1").fetchone()
        (self.ws.root/row[0]).write_text("controlled invalid result file",encoding="utf8")
        (folder/"fault.json").write_text(json.dumps({"injection":"corrupt_S02_file_after_committed_run_before_step_publication"}),encoding="utf8")
        raise OSError("controlled lost return with corrupted file")
BoundedCoordinator._audit=controlled_audit
BoundedCoordinator._fault=boundary
runpy.run_path(os.environ["AUTOMATION_APP_ENTRY"],run_name="__main__")
`;
const inspect=String.raw`
import json,sys,hashlib
from pathlib import Path
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace
from causalops.application.automation_results import snapshot
from causalops.assistant.runtime import execution_source_sha
c=ResearchService(AssistantWorkspace(GeneralWorkspace(Path(sys.argv[1])))).automation_v2()
with c.ws.connection() as db:
    tids=[r[0] for r in db.execute("SELECT id FROM automation_v2_tasks ORDER BY created")]
    counts={n:db.execute("SELECT count(*) FROM "+n).fetchone()[0] for n in ("automation_v2_approvals","exploration_runs","analysis_runs")}
views=[snapshot(c,t) for t in tids]
files={str(p.relative_to(c.ws.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in c.ws.root.rglob("*") if p.is_file() and p.suffix in (".json",".md",".html") and not "workflow-locks" in str(p)}
print(json.dumps({"source_sha":execution_source_sha(),"counts":counts,"views":views,"result_file_hashes":files},ensure_ascii=False))
`;
function score(home){
 const result=cp.spawnSync(PY,['-c',inspect,home],{cwd:REPO,env:{...process.env,PYTHONPATH:INSTALLED?'':path.join(REPO,'src'),PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'},encoding:'utf8',maxBuffer:20*1024*1024,windowsHide:true});
 if(result.status!==0)throw Error('read-only scoring failed: '+result.stderr.slice(-1000));
 return JSON.parse(result.stdout);
}
async function attempt(name,mode){
 const dir=path.join(ROOT,name);fs.mkdirSync(dir);
 const home=path.join(dir,'workspace');fs.mkdirSync(home);
 fs.writeFileSync(path.join(dir,'entry.py'),fixture);
 const p=await port(),base='http://127.0.0.1:'+p;
 const env={...process.env,CAUSALOPS_HOME:home,PYTHONPATH:INSTALLED?'':path.join(REPO,'src'),PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',
  AUTOMATION_ACCEPTANCE_MODE:mode,AUTOMATION_ACCEPTANCE_FOLDER:dir,AUTOMATION_APP_ENTRY:APP_ENTRY,
  STREAMLIT_BROWSER_GATHER_USAGE_STATS:'false',STREAMLIT_SERVER_SHOW_EMAIL_PROMPT:'false'};
 delete env.DEEPSEEK_API_KEY;delete env.OPENAI_API_KEY;delete env.ANTHROPIC_API_KEY;
 const log=fs.openSync(path.join(dir,'server.log'),'wx');
 const proc=cp.spawn(PY,['-m','streamlit','run',path.join(dir,'entry.py'),'--server.address=127.0.0.1','--server.port='+p,'--server.headless=true','--server.fileWatcherType=none'],{cwd:home,env,windowsHide:true,stdio:['ignore',log,log]});
 let browser,page;const events=[];let start=Date.now(),seq=0;
 const result={case:name,fixture:mode,mode:'fixed_real_browser',status:'failed',actions:events,operator_interventions:0,model_calls:0};
 const save=()=>fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify({...result,seconds:(Date.now()-start)/1000},null,2));
 try{
  await wait(async()=>{if(proc.exitCode!==null)throw Error('test server exited: '+fs.readFileSync(path.join(dir,'server.log'),'utf8'));try{return(await fetch(base+'/_stcore/health')).ok}catch{return false}},60000);
  browser=await chromium.launch({headless:true,executablePath:process.env.CAUSALOPS_BROWSER_EXECUTABLE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  page=await browser.newPage({locale:'zh-CN',viewport:{width:1500,height:1050},acceptDownloads:true});
  page.setDefaultTimeout(30000);result.browser=browser.version();result.installed_package=INSTALLED;
  const samples=[];
  await page.exposeFunction('__coStateSample', x=>samples.push({...x,at:new Date().toISOString()}));
  await page.addInitScript(()=>setInterval(()=>{const b=document.body;if(!b)return;const article=b.querySelector('.co-automation-report');const identity=(b.innerText.match(/任务 ([0-9a-f]{32}) · 计划/)||[])[1];const report=(article?.innerText.match(/任务：([0-9a-f]{32})/)||[])[1];if(identity&&report)window.__coStateSample({task:identity,report,mismatch:identity!==report}).catch(()=>{});},100));
  result.state_samples=samples;
  page.on('pageerror',e=>events.push({kind:'pageerror',message:String(e),at:new Date().toISOString()}));
  const capture=async(label)=>{
    const prefix=String(++seq).padStart(2,'0')+'-'+label;
    fs.writeFileSync(path.join(dir,prefix+'.txt'),await page.locator('body').innerText());
    await page.screenshot({path:path.join(dir,prefix+'.png'),fullPage:true});
  };
  const action=async(label,fn)=>{let began=Date.now();try{await fn();events.push({kind:'browser_action',label,at:new Date().toISOString(),seconds:(Date.now()-began)/1000,success:true})}catch(e){events.push({kind:'browser_action',label,at:new Date().toISOString(),success:false,error:String(e)});throw e}finally{save()}};
  const button=n=>page.getByRole('button',{name:n,exact:true});
  const text=n=>page.getByText(n,{exact:true});
  const create=async()=>{
   await text('已核对公开来源、客户单位、随机分配、两组纳入规则和两周访问定义').waitFor();
   await action('confirm_public_design',()=>text('已核对公开来源、客户单位、随机分配、两组纳入规则和两周访问定义').click());
   await action('create_fixed_plan',()=>button('生成五步研究计划').click());
   await button('批准整份计划并开始').waitFor();
   if(await button('批准整份计划并开始').isEnabled())throw Error('approval enabled without review');
   const tid=new URL(page.url()).searchParams.get('automation');if(!tid)throw Error('missing task identity');
   await capture('review-'+tid.slice(0,6));
   await action('review_whole_plan',()=>text('我已核对完整计划、数据与研究依据，批准本计划范围内自动执行').click());
   await action('approve_once_and_start',()=>button('批准整份计划并开始').click());
   return tid;
  };
  await action('open_actual_home',()=>page.goto(base+'/?route=home'));
  await button('启动自动化研究').waitFor();await capture('home');
  if(mode==='legacy'){
   await action('open_existing_marketing_flow',()=>button('查看营销实验').click());
   await action('confirm_existing_case_source',()=>text('已核对来源、随机分配、两组定义与两周访问指标').click());
   await action('create_existing_single_plan',()=>button('创建研究任务并生成待审方案').click());
   await page.getByRole('radio',{name:'人工审核',exact:true}).waitFor();
   await action('open_existing_review',()=>page.getByRole('radiogroup',{name:'方案视图',exact:true}).getByText('人工审核',{exact:true}).click());
   await action('review_existing_plan',()=>page.locator('.st-key-panel_approval').getByText('我已核对上述计划和本步骤必要事实，同意按当前数据与计划版本进行本地计算。',{exact:true}).click());
   await action('approve_existing_plan',()=>button('接受计划并批准本次执行').click());
   await button('导出本次分析报告').waitFor({timeout:80000});
   await capture('existing-report');
   const download=page.waitForEvent('download');await action('download_existing_report',()=>button('导出本次分析报告').click());
   const d=await download;await d.saveAs(path.join(dir,'existing-report.html'));
   const html=fs.readFileSync(path.join(dir,'existing-report.html'),'utf8');
   for(const value of ['10.62','18.28','7.66','两周'])if(!html.includes(value))throw Error('existing report missing '+value);
   const before=score(home);
   await action('refresh_existing_report',()=>page.reload());await button('导出本次分析报告').waitFor({timeout:80000});
   const after=score(home);
   if(before.counts.analysis_runs!==1||after.counts.analysis_runs!==1)throw Error('existing workflow run count changed');
   fs.writeFileSync(path.join(dir,'final-evidence.json'),JSON.stringify(after,null,2));
   result.checked={existing_workflow:true,explicit_approval:true,report_export:true,refresh_without_recompute:true};result.status='passed';
   return result;
  }
  await action('open_automation',()=>button('启动自动化研究').click());
  const tid=await create();result.task_id=tid;
  if(mode==='normal'){
   await text('任务状态：已完成').waitFor({timeout:65000});
   await button('导出整体研究报告').waitFor();
   await capture('complete');
   await page.getByRole('heading',{name:'研究风险与待确认事项',exact:true}).scrollIntoViewIfNeeded();await capture('risks');
   await page.locator('summary').filter({hasText:'资源预算与停止原因'}).click();
   await page.locator('summary').filter({hasText:'资源预算与停止原因'}).scrollIntoViewIfNeeded();await capture('budget');
   await page.getByRole('heading',{name:'营销邮件与两周访问率 · 整体研究报告',exact:true}).evaluate(e=>e.scrollIntoView({block:'start'}));await page.mouse.wheel(0,-90);await capture('report');
   const original=score(home);fs.writeFileSync(path.join(dir,'before-refresh-evidence.json'),JSON.stringify(original,null,2));
   const report=original.views[0].report;if(!report)throw Error('missing real report');
   const visible=await page.locator('body').innerText();
   for(const s of ['18.28%','10.62%','7.66','6.995','8.323',...report.source_runs])if(!visible.includes(s))throw Error('page missing '+s);
   const download=page.waitForEvent('download');await action('download_html_report',()=>button('导出整体研究报告').click());
   const d=await download;await d.saveAs(path.join(dir,'report.html'));
   const jsondownload=page.waitForEvent('download');await action('download_evidence',()=>button('导出步骤与运行证据').click());
   await(await jsondownload).saveAs(path.join(dir,'exported-evidence.json'));
   await action('reload_same_task',()=>page.reload());await text('任务状态：已完成').waitFor();
   await action('open_home',()=>button('首页').click());
   await action('open_automation_history',()=>button('自动化研究').click());
   await text('任务状态：已完成').waitFor();await capture('history-restored');
   const after=score(home);if(JSON.stringify(original.counts)!==JSON.stringify(after.counts)||JSON.stringify(original.result_file_hashes)!==JSON.stringify(after.result_file_hashes))throw Error('history changed by reload');
   result.checked={backend:true,page:true,report_export:true,history:true};
  }else if(mode==='insufficient'){
   await text('任务状态：安全阻断').waitFor({timeout:60000});
   await wait(async()=>{const body=await page.locator('body').innerText();return body.includes('必要字段含缺失')&&body.includes('部分完成说明')});
   await capture('blocked');
   const visible=await page.locator('body').innerText();
   if(!visible.includes('必要字段含缺失')||!visible.includes('部分完成说明'))throw Error('missing precise insufficiency explanation');
   const observed=score(home);if(observed.counts.exploration_runs||observed.counts.analysis_runs)throw Error('downstream executed after insufficiency');
   result.checked={specific_reason:true,no_downstream:true,no_fabricated_report:true};
  }else if(mode==='pause'){
   await wait(()=>fs.existsSync(path.join(dir,tid+'.ready')));
   await capture('stat-committed-before-publish');
   await action('request_pause_in_flight',()=>button('请求暂停').click());
   await text('任务状态：已请求暂停，将在安全边界停止').waitFor();await capture('pause-requested');
   fs.writeFileSync(path.join(dir,tid+'.release'),'test controller releases tool boundary');
   await text('任务状态：已暂停').waitFor();await capture('paused');
   await action('refresh_paused',()=>page.reload());await text('任务状态：已暂停').waitFor();
   const before=score(home);fs.writeFileSync(path.join(dir,'paused-evidence.json'),JSON.stringify(before,null,2));
   await wait(async()=>await button('核查恢复并继续').isEnabled());
   await action('resume_via_service_ui',()=>button('核查恢复并继续').click());
   await text('任务状态：已完成').waitFor({timeout:65000});await capture('resumed-complete');
   const completed=score(home);if(completed.counts.exploration_runs!==1||completed.counts.analysis_runs!==1)throw Error('resume duplicated statistics');
   await action('new_task_for_cancel',()=>button('创建新的自动化研究').click());
   const cancelled=await create();
   await wait(()=>fs.existsSync(path.join(dir,cancelled+'.ready')));
   await action('confirm_cancel',()=>text('我确认取消当前自动化任务，保留已有结果；取消后不能恢复').click());
   await action('request_cancel',()=>button('确认取消任务').click());
   await text('任务状态：已请求取消，将在安全边界停止').waitFor();
   fs.writeFileSync(path.join(dir,cancelled+'.release'),'release cancelled current step');
   await text('任务状态：已取消').waitFor();await capture('cancelled');
   if(await button('核查恢复并继续').isEnabled())throw Error('cancelled task can resume');
   await action('reopen_original_completed_history',()=>page.goto(base+'/?route=automation&automation='+tid));
   await text('任务状态：已完成').waitFor();await capture('original-history-kept');
   result.cancelled_task_id=cancelled;
   const final=score(home);if(final.counts.analysis_runs!==1||final.counts.exploration_runs!==2)throw Error('cancel lost/duplicated runs');
   result.checked={pause:true,refresh:true,resume_without_recompute:true,cancel_terminal:true,old_report_preserved:true};
  }else if(mode==='uncertain'){
   await text('任务状态：结果需要核查').waitFor({timeout:60000});
   await wait(async()=>await button('核查恢复并继续').isEnabled());
   await capture('uncertain');
   await action('request_reconciliation',()=>button('核查恢复并继续').click());
   await text('任务状态：已暂停').waitFor();
   await wait(async()=>{const body=await page.locator('body').innerText();return body.includes('恢复核查未通过')&&body.includes('部分完成说明')});
   await capture('manual-takeover');
   const visible=await page.locator('body').innerText();
   if(!visible.includes('恢复核查未通过')||!visible.includes('部分完成说明'))throw Error('missing takeover explanation');
   const final=score(home);if(final.counts.exploration_runs!==1||final.counts.analysis_runs!==0)throw Error('uncertain result replayed');
   result.checked={uncertain_stopped:true,takeover_reason:true,no_replay:true};
  }
  fs.writeFileSync(path.join(dir,'final-evidence.json'),JSON.stringify(score(home),null,2));
  result.status='passed';
 }catch(e){
  result.error=String(e.stack||e);
  if(page){try{fs.writeFileSync(path.join(dir,'failure.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(dir,'failure.png'),fullPage:true})}catch{}}
 }finally{
  if(result.state_samples){result.state_mismatches=result.state_samples.filter(x=>x.mismatch).length;if(result.state_mismatches){result.status='failed';result.error='task/report identity mismatch in sampled DOM';}}
  save();if(browser)await browser.close();proc.kill();fs.closeSync(log);
 }
 return result;
}
(async()=>{
 const results=[];
 const cases=[['A-normal','normal'],['B-insufficient','insufficient'],['C-pause-cancel','pause'],['C-uncertain','uncertain'],['legacy-single','legacy']];
 const selected=process.env.CAUSALOPS_BROWSER_CASES;
 for(const [name,mode] of cases.filter(([name])=>selected?selected.split(',').includes(name):name!=='legacy-single')){
  const r=await attempt(name,mode);results.push(r);console.log(name,r.status,r.error?r.error.split('\n')[0]:'');
 }
 fs.writeFileSync(path.join(ROOT,'summary.json'),JSON.stringify(results,null,2));
 if(results.some(x=>x.status!=='passed'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
