/* Real Streamlit fixed-browser acceptance. Setup/injections and read-only scoring are separate. */
const fs=require('fs'),path=require('path'),cp=require('child_process'),net=require('net'),{chromium}=require('playwright');
const REPO=path.resolve(__dirname,'..'),PY=process.env.CAUSALOPS_TEST_PYTHON||'python',ROOT=path.resolve(process.argv[2]);
fs.mkdirSync(ROOT,{recursive:false});
const FIX=path.join(ROOT,'controlled'),HOME=path.join(FIX,'workspace');
const INSTALLED=process.env.CAUSALOPS_TEST_INSTALLED==='1';
const APP_ENTRY=process.env.CAUSALOPS_TEST_APP_ENTRY||path.join(REPO,'src/causalops/ui/workbench.py');
const env={...process.env,PYTHONPATH:INSTALLED?'':path.join(REPO,'src'),PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',CAUSALOPS_HOME:HOME,STREAMLIT_BROWSER_GATHER_USAGE_STATS:'false',STREAMLIT_SERVER_SHOW_EMAIL_PROMPT:'false'};
for(const k of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[k];
const write=(p,v)=>fs.writeFileSync(p,JSON.stringify(v,null,2));
function controller(mode){
 const args=[path.join(REPO,'scripts/diagnostics_stage3_fixture.py'),mode,'--root',FIX];
 if(mode==='prepare')args.push('--archive',process.env.CAUSALOPS_HILLSTROM_ARCHIVE);
 const r=cp.spawnSync(PY,args,{cwd:REPO,env,encoding:'utf8',windowsHide:true,maxBuffer:35*1024*1024});
 if(r.status!==0)throw Error('controller '+mode+' failed: '+r.stderr.slice(-1500));
 return JSON.parse(r.stdout);
}
const setup=controller('prepare');write(path.join(ROOT,'setup.json'),setup);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function port(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p}
(async()=>{
 let proc,browser,log,base,page,ctx,folder,seq=0;const results=[],samples=[],events=[];
 async function act(name,fn){if(await page.locator('[data-testid="stApp"]').count())await page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').waitFor({state:'visible'});const t=Date.now();await fn();await sleep(150);if(page.url().startsWith(base))await page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').waitFor({state:'visible'});events.push({seq:++seq,actor:'browser',event:name,at:new Date().toISOString(),milliseconds:Date.now()-t})}
 async function capture(name){fs.writeFileSync(path.join(folder,name+'.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(folder,name+'.png'),fullPage:true})}
 async function select(label,match){
  let control=page.getByRole('combobox',{name:label,exact:true});
  if(label==='历史诊断报告'){
   const u=new URL(page.url()),key='.st-key-diag_history_'+u.searchParams.get('diagnostic_mode')+'_'+u.searchParams.get('diagnostic_task')+'_'+(u.searchParams.get('diagnostic_report')||'');
   control=page.locator(key).getByRole('combobox',{name:label,exact:true});
   await control.waitFor({state:'visible'});
  }
  await act('open_'+label,()=>control.click());
  await act('select_'+label,()=>page.getByRole('option').filter({hasText:match}).click());
  if(label==='诊断任务'){
   await page.waitForFunction(prefix=>document.querySelector('.diag-selection')?.dataset.task.startsWith(prefix),match);
   const u=new URL(page.url()),key='.st-key-diag_history_'+u.searchParams.get('diagnostic_mode')+'_'+u.searchParams.get('diagnostic_task')+'_'+(u.searchParams.get('diagnostic_report')||'');
   await page.locator(key).getByRole('combobox',{name:'历史诊断报告',exact:true}).waitFor({state:'visible'});
  }
  if(label==='历史诊断报告'){
   await page.waitForFunction(match=>{const rid=new URL(location.href).searchParams.get('diagnostic_report')||'';return match==='请选择已保存诊断'?rid==='':rid.startsWith(match)},match);
  }
 }
 async function open(){
  await act('open_home',()=>page.goto(base));await page.getByRole('button',{name:'研究证据诊断',exact:true}).waitFor();
  await act('open_diagnostics',()=>page.getByRole('button',{name:'研究证据诊断',exact:true}).click());
  await page.getByRole('heading',{name:'研究证据诊断',exact:true}).waitFor();
 }
 async function choose(mode,task){
  const label=mode==='preflight'?'执行前 · 研究条件':'执行后 · 研究证据',radio=page.getByRole('radio',{name:label,exact:true});
  if(!await radio.isChecked())await act('choose_'+mode,()=>page.getByRole('radiogroup',{name:'诊断阶段',exact:true}).getByText(label,{exact:true}).click());
  await page.locator('.diag-selection[data-mode="'+mode+'"]').waitFor({state:'visible'});
  await select('诊断任务',task.slice(0,8));
  await page.locator('.diag-selection[data-mode="'+mode+'"][data-task="'+task+'"]').waitFor({state:'visible'});
  await page.getByRole('button',{name:mode==='preflight'?'检查研究条件':'检查研究证据',exact:true}).waitFor();
 }
 async function check(mode,task,replacePrevious=false){
  const previous=new URL(page.url()).searchParams.get('diagnostic_report');
  await act('explicit_diagnostic_request',()=>page.getByRole('button',{name:mode==='preflight'?'检查研究条件':'检查研究证据',exact:true}).click());
  await page.waitForFunction(({id,previous,replacePrevious})=>{
   const rid=new URL(location.href).searchParams.get('diagnostic_report');
   const a=document.querySelector('.co-diagnostic-snapshot[data-report-id="'+rid+'"]');
   return a&&a.dataset.taskId===id&&(!replacePrevious||rid!==previous)&&getComputedStyle(a).visibility!=='hidden';
  },{id:task,previous,replacePrevious},{timeout:45000});
  return page.locator('.co-diagnostic-snapshot[data-report-id="'+new URL(page.url()).searchParams.get('diagnostic_report')+'"]');
 }
 async function runCase(name,fn){
  folder=path.join(ROOT,name);fs.mkdirSync(folder);events.length=0;seq=0;const start=Date.now();
  ctx=await browser.newContext({viewport:{width:1480,height:1050},locale:'zh-CN',acceptDownloads:true});
  page=await ctx.newPage();page.setDefaultTimeout(30000);const providers=[];
  page.on('request',r=>{if(/api\.(deepseek|openai)\.com/.test(r.url()))providers.push(r.url())});
  await page.exposeFunction('__diagSample',v=>samples.push({...v,case:name,at:Date.now()}));
  await page.addInitScript(()=>setInterval(()=>{
   if(!document.body)return;const u=new URL(location.href);if(u.searchParams.get('route')!=='evidence')return;
   const task=u.searchParams.get('diagnostic_task')||'',report=u.searchParams.get('diagnostic_report')||'';
   for(const a of document.querySelectorAll('.co-diagnostic-snapshot')){
    const cs=getComputedStyle(a),visible=cs.visibility!=='hidden'&&cs.display!=='none'&&!!a.getClientRects().length;
    window.__diagSample({task:a.dataset.taskId,report:a.dataset.reportId,urlTask:task,urlReport:report,visible,stale:!!a.closest('[data-stale="true"]'),mismatch:visible&&(task!==a.dataset.taskId||report!==a.dataset.reportId)}).catch(()=>{});
   }
  },30));
  const out={case:name,mode:'fixed_real_streamlit_browser',status:'failed',browser:browser.version(),model_requests:0,installed_package:INSTALLED};
  try{await fn(out);if(providers.length)throw Error('unexpected provider request');out.status='passed'}
  catch(e){out.error=String(e.stack||e);try{await capture('failure');fs.writeFileSync(path.join(folder,'failure-dom.html'),await page.content())}catch{}}
  finally{out.seconds=(Date.now()-start)/1000;out.effective_actions=events.length;out.events=[...events];out.provider_requests=providers;write(path.join(folder,'result.json'),out);results.push(out);await ctx.close();console.log(name,out.status,out.error?out.error.split('\n')[0]:'')}
 }
 let aReport,bReport;
 try{
  const p=await port();base='http://127.0.0.1:'+p;log=fs.openSync(path.join(ROOT,'server.log'),'wx');
  proc=cp.spawn(PY,['-m','streamlit','run',APP_ENTRY,'--server.address=127.0.0.1','--server.port='+p,'--server.headless=true','--server.fileWatcherType=none'],{cwd:HOME,env,windowsHide:true,stdio:['ignore',log,log]});
  let healthy=false;for(let i=0;i<300;i++){try{healthy=(await fetch(base+'/_stcore/health')).ok}catch{}if(healthy)break;if(proc.exitCode!==null)throw Error('server exited');await sleep(200)}
  if(!healthy)throw Error('server health timeout');
  browser=await chromium.launch({headless:true,executablePath:process.env.CAUSALOPS_BROWSER_EXECUTABLE});
  const before=controller('inspect');write(path.join(ROOT,'before-browser.json'),before);
  await runCase('A-complete',async out=>{
   const a=setup.cases.A;
   await act('open_home',()=>page.goto(base));
   await act('open_existing_automation',()=>page.getByRole('button',{name:'启动自动化研究',exact:true}).click());
   await select('自动化任务与历史报告',a.task.slice(0,8));
   await act('open_task_diagnostics',()=>page.getByRole('button',{name:'查看当前研究的证据诊断',exact:true}).click());
   let snap=await check('post_run',a.task);
   aReport=await snap.getAttribute('data-report-id');out.report_id=aReport;const text=await snap.innerText();
   const values=[(a.effect.control_rate*100).toFixed(2)+'%',(a.effect.treated_rate*100).toFixed(2)+'%',a.effect.pp.toFixed(2),...a.effect.ci_pp.map(v=>v.toFixed(3)),...a.runs,'未实现的八项规则','当前检查未生成后续建议'];
   for(const value of values)if(!text.includes(value))throw Error('missing real saved fact '+value);
   await capture('01-risk-summary');
   for(const [i,title] of ['第一层 · 研究结果','第二层 · 证据质量','第三层 · 下一步研究建议'].entries()){
    await page.getByRole('heading',{name:title,exact:true}).scrollIntoViewIfNeeded();
    await capture('01-layer-'+(i+1));
   }
   await act('open_native_evidence',()=>page.getByRole('button',{name:'查看两个 Run 与原报告的运行证据',exact:true}).click());
   await page.waitForFunction(rid=>Array.from(document.querySelectorAll('.st-key-diagnostic_snapshot_'+rid+' [data-testid="stJson"]')).some(e=>e.innerText.includes('DescriptiveRun')&&getComputedStyle(e).visibility!=='hidden'),aReport);
   const native=page.locator('.st-key-diagnostic_snapshot_'+aReport+' [data-testid="stJson"]').filter({hasText:'DescriptiveRun'}).last();
   const nativeText=await native.innerText();
   for(const run of a.runs)if(!nativeText.includes(run))throw Error('raw evidence missing actual Run '+run);
   await native.scrollIntoViewIfNeeded();await capture('02-native-evidence');
   await act('refresh_same_report',()=>page.reload());await snap.waitFor({state:'visible'});
   await act('repeat_same_check',()=>page.getByRole('button',{name:'检查研究证据',exact:true}).click());
   await page.locator('.co-diagnostic-snapshot[data-report-id="'+aReport+'"]').waitFor({state:'visible'});
   await select('历史诊断报告','请选择已保存诊断');await select('历史诊断报告',aReport.slice(0,12));
   await page.locator('.co-diagnostic-snapshot[data-report-id="'+aReport+'"]').waitFor({state:'visible'});await capture('03-history-refresh');
   out.checked={actual_two_runs:true,three_layers:true,six_rules:true,eight_unimplemented:true,no_suggestions:true,same_report_after_refresh:true};
  });
  await runCase('B-unknown-design',async out=>{
   const b=setup.cases.B;await open();await choose('preflight',b.task);const snap=await check('preflight',b.task);
   bReport=await snap.getAttribute('data-report-id');out.report_id=bReport;const text=await snap.innerText();
   if(!text.includes('条件未知或证据不足')||!text.includes('尚无正式统计运行')||text.includes('7.66'))throw Error('unknown design incorrectly displayed');
   const submit=page.getByRole('button',{name:'保存为研究需求草案',exact:true}),confirm=page.locator('[data-testid="stCheckbox"]').filter({hasText:'我确认只保存研究需求草案，不批准或执行统计'}).locator('label:visible'),input=page.getByRole('textbox',{name:'研究需求说明',exact:true});
   if(!await submit.isDisabled())throw Error('draft permitted without explicit confirmation');
   await page.getByRole('heading',{name:'第一层 · 研究结果',exact:true}).scrollIntoViewIfNeeded();
   await capture('01-preflight-result');
   await page.getByRole('heading',{name:'第三层 · 下一步研究建议',exact:true}).scrollIntoViewIfNeeded();
   await capture('01-unknown-before-save');const intent='补充分配设计来源，核对适用客户及登记窗口。';
   if(!await page.getByRole('checkbox',{name:'我确认只保存研究需求草案，不批准或执行统计',exact:true}).isChecked())await act('confirm_draft_only',()=>confirm.click());
   for(let i=0;i<100&&!await submit.isEnabled();i++)await sleep(100);
   await act('enter_need',()=>input.fill(intent));await act('save_draft',()=>submit.click());
   await page.getByRole('heading',{name:'本报告已保存的研究需求草案',exact:true}).waitFor();
   let state=controller('inspect');if(state.drafts.length!==1||state.drafts[0].execution_authorized)throw Error('draft not isolated');
   out.draft_id=state.drafts[0].draft_id;await page.getByRole('heading',{name:'本报告已保存的研究需求草案',exact:true}).scrollIntoViewIfNeeded();await capture('02-saved-draft');
   await act('duplicate_save',()=>submit.click());if(controller('inspect').drafts.length!==1)throw Error('duplicate draft');
   await act('reload_draft',()=>page.reload());await page.getByRole('heading',{name:'本报告已保存的研究需求草案',exact:true}).waitFor();
   if(await input.inputValue()!==intent)throw Error('intent lost on refresh');
   if(!await page.getByRole('checkbox',{name:'我确认只保存研究需求草案，不批准或执行统计',exact:true}).isChecked())await act('reconfirm_same_need',()=>confirm.click());
   await act('duplicate_after_refresh',()=>submit.click());
   if(controller('inspect').drafts.length!==1)throw Error('duplicate after refresh');
   write(path.join(folder,'controller-injection.json'),controller('stale'));
   await act('attempt_stale_save',()=>submit.click());
   await page.locator('.co-diagnostic-snapshot').getByText('来源已变化或当前无法核验',{exact:true}).waitFor();
   if(!await submit.isDisabled()||controller('inspect').drafts.length!==1)throw Error('stale save not denied');
   await capture('03-stale-suggestion');out.checked={unknown_randomization:true,no_run:true,explicit_draft:true,idempotent:true,refresh_preserved:true,stale_rejected:true};
  });
  for(const kind of ['foreign','metric','unit','window','hash']){
   await runCase('C-'+kind,async out=>{
    const c=setup.cases['C-'+kind];await open();await choose('post_run',c.task);await select('历史诊断报告',c.old_report.slice(0,12));
    await page.locator('.co-diagnostic-snapshot[data-report-id="'+c.old_report+'"]').waitFor({state:'visible'});
    let text=await page.locator('.co-diagnostic-snapshot').innerText();
    if(text.includes('18.28%')||!text.includes('来源已变化'))throw Error('old success filled current conflict');
    const snap=await check('post_run',c.task,true);out.report_id=await snap.getAttribute('data-report-id');text=await snap.innerText();
    if(!text.includes('当前证据限制联合结论')||text.includes('18.28%'))throw Error('conflict exposes estimate');
    const rule=kind==='foreign'||kind==='hash'?'PD-01':kind==='unit'?'PD-09':'PD-14';
    await page.getByRole('heading',{name:'研究风险摘要',exact:true}).scrollIntoViewIfNeeded();await capture('01-conflict-summary');
    await act('open_conflict_evidence',()=>page.locator('.st-key-diagnostic_snapshot_'+out.report_id).locator('summary').filter({hasText:'查看依据 · '+rule}).click());
    await capture('01-conflict-and-evidence');out.checked={restriction:true,no_old_numeric_fill:true,evidence_accessible:true};
   });
  }
  if(aReport){
   await runCase('switch-consistency',async out=>{
    const a=setup.cases.A,c=setup.cases['C-window'],state=controller('inspect');
    const cr=state.reports.find(r=>r.context.task_ref.task_id===c.task&&r.results.status==='restricted');
    await open();await choose('post_run',a.task);await select('历史诊断报告',aReport.slice(0,12));await page.locator('.co-diagnostic-snapshot[data-report-id="'+aReport+'"]').waitFor({state:'visible'});
    for(let i=0;i<6;i++){
     const target=i%2===0?c:a,rid=i%2===0?cr.report_id:aReport;
     await select('诊断任务',target.task.slice(0,8));await select('历史诊断报告',rid.slice(0,12));
     await page.locator('.co-diagnostic-snapshot[data-report-id="'+rid+'"]').waitFor({state:'visible'});await sleep(250);
    }
    await capture('final-switch');out.checked={six_switches:true,no_history_regeneration:true};
   });
  }
  const after=controller('inspect');write(path.join(ROOT,'after-browser.json'),after);
  const unchanged=JSON.stringify(before.guards)===JSON.stringify(after.guards),mismatches=samples.filter(s=>s.mismatch);
  write(path.join(ROOT,'state-samples.json'),samples);
  if(!unchanged)results.push({case:'native-preservation',status:'failed',error:'native statistical/approval markers changed'});
  if(mismatches.length)results.push({case:'transition-identity',status:'failed',mismatch_samples:mismatches.length});
  write(path.join(ROOT,'summary.json'),{mode:'fixed_browser_not_free_exploration_or_human_test',results,samples:samples.length,visible_identity_mismatches:mismatches.length,native_records_unchanged:unchanged,model_requests:0,source_sha:after.source_sha,counts_before:before.counts,counts_after:after.counts});
  if(results.some(r=>r.status!=='passed'))process.exitCode=1;
 }catch(e){write(path.join(ROOT,'fatal.json'),{error:String(e.stack||e)});console.error(e);process.exitCode=1}
 finally{if(browser)await browser.close();if(proc)proc.kill();if(log!==undefined)fs.closeSync(log)}
})().catch(e=>{console.error(e);process.exitCode=1});
