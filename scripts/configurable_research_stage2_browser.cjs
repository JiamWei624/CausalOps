/* Fixed real UI acceptance. The read-only scorer is never used to choose UI actions. */
const fs=require('fs'),path=require('path'),cp=require('child_process'),net=require('net'),{chromium}=require('playwright');
const REPO=path.resolve(__dirname,'..'),ROOT=path.resolve(process.argv[2]),PUBLIC=path.resolve(process.argv[3]);
const PY=process.env.CAUSALOPS_TEST_PYTHON||'python';
const INSTALLED=process.env.CAUSALOPS_TEST_INSTALLED==='1',APP_ENTRY=process.env.CAUSALOPS_TEST_APP_ENTRY||path.join(REPO,'src/causalops/ui/workbench.py');
fs.mkdirSync(ROOT,{recursive:false});
const write=(p,x)=>fs.writeFileSync(p,JSON.stringify(x,null,2)),delay=ms=>new Promise(r=>setTimeout(r,ms));
async function port(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));let p=s.address().port;await new Promise(r=>s.close(r));return p}
const rows=['subject,arm,completed,alternate'];for(let i=0;i<24;i++)rows.push([i,i<12?'standard':'variant',i%3?'yes':'no',i%3?'yes':'no'].join(','));fs.writeFileSync(path.join(ROOT,'synthetic.csv'),rows.join('\n'));
const rows2=['subject,arm,completed,alternate'];for(let i=30;i<54;i++)rows2.push([i,i<42?'standard':'variant',i%4?'yes':'no',i%2?'yes':'no'].join(','));fs.writeFileSync(path.join(ROOT,'synthetic-new-window.csv'),rows2.join('\n'));
(async()=>{
 const results=[];
 for(const mode of ['A-public','B-unknown']){
  const folder=path.join(ROOT,mode);fs.mkdirSync(folder);const workspace=path.join(folder,'workspace');
  const env={...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:INSTALLED?'':path.join(REPO,'src'),CAUSALOPS_HOME:workspace,CAUSALOPS_EVENT_ORIGIN:'fixed_browser_test',STREAMLIT_BROWSER_GATHER_USAGE_STATS:'false'};
  for(const k of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[k];
  let proc,browser,page,ctx,events=[],started=new Date().toISOString(),result={case:mode,status:'failed',started};
  const log=fs.openSync(path.join(folder,'server.log'),'w');
  function inspect(){const r=cp.spawnSync(PY,[path.join(REPO,'scripts/configurable_research_inspect.py'),workspace],{cwd:REPO,env,windowsHide:true,encoding:'utf8',maxBuffer:25e6});if(r.status!==0)throw Error('scoring read failed: '+r.stderr.slice(-1200));return JSON.parse(r.stdout)}
  try{
   const p=await port(),base='http://127.0.0.1:'+p;
   proc=cp.spawn(PY,['-m','streamlit','run',APP_ENTRY,'--server.headless=true','--server.address=127.0.0.1','--server.port='+p,'--browser.gatherUsageStats=false'],{cwd:REPO,env,stdio:['ignore',log,log],windowsHide:true});
   for(let i=0;i<90;i++){try{if((await fetch(base+'/_stcore/health')).ok)break}catch{}await delay(500)}
   browser=await chromium.launch({headless:true,executablePath:process.env.CAUSALOPS_BROWSER_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});ctx=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});page=await ctx.newPage();page.setDefaultTimeout(25000);
   async function ready(){await page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').waitFor({state:'visible'});await delay(100)}
   async function act(action,fn){let at=new Date().toISOString(),t=Date.now();try{await fn();await ready();events.push({action,at,ms:Date.now()-t,status:'success'})}catch(e){events.push({action,at,ms:Date.now()-t,status:'failure',error:String(e)});throw e}}
   const click=label=>act(label,()=>page.getByRole('button',{name:label,exact:true}).click());
   const text=(label,value)=>act('fill:'+label,async()=>{await page.getByRole('textbox',{name:label,exact:true}).fill(value);await page.getByRole('textbox',{name:label,exact:true}).press('Tab')});
   async function select(label,value){
    await ready();const box=page.getByRole('combobox',{name:label,exact:true});
    const current=await box.evaluate(el=>(el.value||el.textContent||el.parentElement.textContent||'').trim());
    if(current===value)return;
    await act('select:'+label,async()=>{await box.click();await box.press('ArrowDown');await page.getByRole('option',{name:value,exact:true}).click()});
   }
   const check=label=>act(label,()=>page.getByText(label,{exact:true}).click());
   async function capture(name){fs.writeFileSync(path.join(folder,name+'.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(folder,name+'.png'),fullPage:true})}
   await act('open_home',()=>page.goto(base));await click('使用自己的数据开展研究');
   await act('upload_csv',()=>page.locator('input[type=file]').setInputFiles(mode==='A-public'?PUBLIC:path.join(ROOT,'synthetic.csv')));
   await capture('01-upload-preview');
   await text('研究目标',mode==='A-public'?'比较随机档案性别标记对本次晋升推荐比例的影响，给出差异与证据限制。':'比较本期两个独立记录组的完成比例，分配机制未知，只作描述。');
   await text('每行的分析单位',mode==='A-public'?'一名银行主管对一份档案的推荐':'独立参与者');
   if(mode==='B-unknown')await select('唯一标识字段（没有时必须明确记录粒度）','subject');
   await text('记录粒度与纳入范围',mode==='A-public'?'每位主管一次推荐；无原始人员ID，使用确认的记录粒度，不代表身份已验证。':'每名独立参与者一条记录，本表全部记录。');
   await check('我确认每行是一个独立观察单位，不是同一实体重复抽检或纵向记录');
   await select('比较组字段',mode==='A-public'?'gender':'arm');
   await select('对照组编码',mode==='A-public'?'female':'standard');await select('比较组编码',mode==='A-public'?'male':'variant');
   await text('对照组业务含义',mode==='A-public'?'女性标记档案':'标准方案');await text('比较组业务含义',mode==='A-public'?'男性标记档案':'新方案');
   await select('正式二元结果字段',mode==='A-public'?'decision':'completed');
   await text('否定事件编码（映射为0）',mode==='A-public'?'not promoted':'no');await text('肯定事件编码（映射为1）',mode==='A-public'?'promoted':'yes');
   await text('结果指标名称',mode==='A-public'?'晋升推荐比例':'完成比例');await text('观察窗口（说明本表全部记录对应的窗口）',mode==='A-public'?'1972管理研修实验的一次晋升推荐':'合成观察期一');
   if(mode==='A-public'){
    await select('分配机制','randomized');await text('数据／设计公开来源网页（依据未知可留空）','https://openintro-ims.netlify.app/foundations-randomization');
    await text('设计依据与适用范围说明','OpenIntro研究设计说明：48位主管收到除性别标记外相同的档案，档案随机分配，每位主管给出一次推荐；不代表实际员工晋升。');
    await check('我已核对来源明确支持本数据与观察单位的随机分配，不是仅根据组名判断');
   }
   await check('我已核对字段、组别含义、二元编码、分析单位与窗口，确认此数据合同');await capture('02-contract');await click('确认合同并生成待审计划');
   await page.getByRole('checkbox',{name:'我已核对完整计划、数据与研究依据，批准本计划范围内自动执行'}).waitFor({state:'visible'});await capture('03-plan');
   if(mode==='B-unknown'){
    await check('使用模型辅助生成候选计划');if(!await page.getByRole('button',{name:'生成模型候选',exact:true}).isDisabled())throw Error('missing model unexpectedly usable');await capture('03-model-unavailable');await check('使用受限研究模板');
   }
   const parentTid=new URL(page.url()).searchParams.get('automation');await click('采纳候选并生成正式待审计划');await page.waitForFunction(id=>new URL(location.href).searchParams.get('automation')!==id,parentTid);
   const adoptedTid=new URL(page.url()).searchParams.get('automation');await page.locator('.st-key-automation_approve_'+adoptedTid).getByRole('checkbox').waitFor({state:'visible'});await ready();await capture('03-adopted-plan');
   const tid=new URL(page.url()).searchParams.get('automation');if(!tid)throw Error('missing task identity');
   await act('explicit_bound_approval',()=>page.locator('.st-key-automation_approve_'+tid).getByText('我已核对完整计划、数据与研究依据，批准本计划范围内自动执行',{exact:true}).click());await page.locator('.st-key-automation_start_'+tid+' button:not([disabled])').waitFor({state:'visible'});await click('批准整份计划并开始');
   await page.locator('.co-automation-report').waitFor({state:'visible',timeout:90000});
   await page.waitForFunction(mode=>{const node=document.querySelector('.co-automation-report');if(!node)return false;const text=node.innerText;return mode==='A-public'?text.includes('95%区间')&&text.includes('A/B Run'):text.includes('没有执行A/B')&&text.includes('原批准')},mode,{timeout:90000});
   await ready();await capture('04-result');let before=inspect();write(path.join(folder,'actual-evidence.json'),before);
   let task=before.tasks.find(t=>t.id===tid);if(!task)throw Error('wrong task');
   if(mode==='A-public'){
    if(task.status!=='completed'||task.report.source_runs.length!==2)throw Error('five-step did not complete: '+task.reason);
    if(Math.abs(task.report.effect.control_rate-14/24)>1e-12||Math.abs(task.report.effect.treated_rate-21/24)>1e-12)throw Error('saved rates mismatch independent public count');
    const visible=await page.locator('.co-automation-report').innerText();for(const x of ['58.33%','87.50%','29.1667','个百分点',...task.report.source_runs])if(!visible.includes(x))throw Error('missing visible evidence '+x);
   }else{
    if(task.status!=='completed'||task.report.status!=='descriptive_complete'||task.plan.steps.some(s=>s.step_id==='S04')||!task.evidence.S02||task.evidence.S04)throw Error('unknown assignment not safely restricted');
   }
   const hashes=JSON.stringify(task.evidence);await act('refresh_saved_task',()=>page.reload());await page.locator('.co-automation-report').waitFor({state:'visible'});await capture('05-refresh');
   const re=inspect().tasks.find(t=>t.id===tid);if(JSON.stringify(re.evidence)!==hashes)throw Error('refresh changed original runs');
   const dw=page.waitForEvent('download');await click(task.report?'导出整体研究报告':'导出部分完成说明');await (await dw).saveAs(path.join(folder,'export.html'));
   await act('open_bound_diagnosis',()=>page.getByRole('button',{name:'查看当前研究的证据诊断',exact:true}).click());await click('检查研究证据');
   const diag=page.locator('.co-diagnostic-snapshot[data-task-id="'+tid+'"]');await diag.waitFor({state:'visible'});await ready();
   const reportId=await diag.getAttribute('data-report-id');await diag.screenshot({path:path.join(folder,'08-three-layers.png')});await capture('08-diagnostics');
   const visible=await diag.innerText();for(const x of ['第一层','第二层','第三层',...task.report.source_runs])if(!visible.includes(x))throw Error('missing diagnostic layer or run '+x);
   if(mode==='B-unknown'&&!visible.includes('条件未知或证据不足'))throw Error('unknown assignment not shown');
   let suggestion=null;
   if(mode==='B-unknown'){
    const control=page.getByRole('combobox',{name:'对建议的决定',exact:true}).first();await act('choose_deferred_decision',async()=>{await control.click();await control.press('ArrowDown');await page.getByRole('option',{name:'暂缓处理',exact:true}).click()});
   }
   await act('explicit_decision_ack',()=>page.getByText('我确认仅记录研究决定，不批准或执行统计',{exact:true}).first().click());
   const reason=mode==='A-public'?'仅解释本次档案推荐实验，保留正态近似与外推限制。':'补充分配设计来源前只解释描述性差异，不作因果结论。';
   await act('decision_reason',()=>page.getByRole('textbox',{name:'决策原因或研究备注',exact:true}).first().fill(reason));await act('save_explicit_decision',()=>page.getByRole('button',{name:'保存研究决定',exact:true}).first().click());await page.getByText(/^已保存研究决定：/).first().waitFor();
   await act('refresh_diagnostic_and_memory',()=>page.reload());await page.getByText(reason,{exact:true}).first().waitFor();await page.getByRole('heading',{name:'研究决策历史',exact:true}).scrollIntoViewIfNeeded();await capture('09-decision-history');
   let linked=inspect();write(path.join(folder,'diagnosis-decision-evidence.json'),linked);
   if(JSON.stringify(linked.protected)!==JSON.stringify(before.protected))throw Error('diagnostic or decision changed native statistical evidence or approval');
   const rr=linked.diagnostic_reports.find(r=>r.report_id===reportId);if(!rr||rr.context.task_ref.task_id!==tid||rr.context.run_refs.length!==task.report.source_runs.length)throw Error('diagnostic source mismatch');
   const statuses=Object.fromEntries(rr.quality.findings.map(f=>[f.rule.id,f.status]));
   if(mode==='A-public'&&Object.values(statuses).some(x=>x!=='verified'))throw Error('unexpected complete evidence rule status '+JSON.stringify(statuses));
   if(mode==='B-unknown'&&(statuses['PD-02']!=='unknown'||statuses['PD-07']!=='not_applicable'||rr.results.effect!==null||!rr.results.descriptive))throw Error('invalid descriptive diagnostic result');
   if(!linked.decisions.some(d=>d.report_id===reportId&&!d.execution_authorized))throw Error('bound user decision absent');
   result={...result,report_id:reportId,rule_statuses:statuses,native_unchanged_by_diagnosis:true};
   await act('return_to_original_task',()=>page.goto(base+'/?route=automation&automation='+tid));await page.locator('.co-automation-report').waitFor({state:'visible'});
   if(mode==='B-unknown'){
    await click('修改研究条件（新候选并重新审核）');await act('upload_new_window_table',()=>page.locator('input[type=file]').setInputFiles(path.join(ROOT,'synthetic-new-window.csv')));
    await text('观察窗口（说明本表全部记录对应的窗口）','合成观察期二');await check('我确认每行是一个独立观察单位，不是同一实体重复抽检或纵向记录');await check('我已核对字段、组别含义、二元编码、分析单位与窗口，确认此数据合同');await click('确认合同并生成待审计划');await capture('06-new-plan');
    let changed=inspect(),newer=changed.tasks.find(t=>t.plan.version===task.plan.version+1);if(!newer||newer.status!=='candidate'||newer.plan.version!==task.plan.version+1)throw Error('new scope did not require new approval');
    if(newer.steps.some(s=>s.run_id||s.output))throw Error('unapproved successor executed');
    await act('reopen_old_report',()=>page.goto(base+'/?route=automation&automation='+tid));await page.locator('.co-automation-report').waitFor({state:'visible'});await capture('07-old-history');const historyText=await page.locator('.co-automation-report').innerText();if(!historyText.includes('66.67%'))throw Error('saved historical descriptive value not visible');
    if(JSON.stringify(inspect().tasks.find(t=>t.id===tid).evidence)!==hashes)throw Error('history overwritten');write(path.join(folder,'revision-evidence.json'),changed);
   }
   result={...result,status:'passed',task_id:tid,checked:mode==='A-public'?'two real runs, six generic rules, three layers, explicit decision, refresh':'one descriptive run, unknown design, no AB, three layers and decision, revised scope needs approval'};
  }catch(e){result.error=String(e.stack||e);if(page){try{fs.writeFileSync(path.join(folder,'failure.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(folder,'failure.png'),fullPage:true})}catch{}}}
  finally{result.ended=new Date().toISOString();result.elapsed_ms=Date.now()-Date.parse(started);result.actions=events.length;write(path.join(folder,'actions.json'),events);write(path.join(folder,'result.json'),result);results.push(result);console.log(mode,result.status,result.error?result.error.split('\n')[0]:'');if(browser)await browser.close();if(proc)proc.kill();fs.closeSync(log)}
 }
 write(path.join(ROOT,'summary.json'),{kind:'fixed_browser_not_free_exploration_or_human_test',model_requests:0,results});if(results.some(r=>r.status!=='passed'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
