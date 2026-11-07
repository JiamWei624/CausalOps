/* Four fixed real-browser scenarios. Controller only seeds public facts and injects documented changes. */
const fs=require('fs'),path=require('path'),cp=require('child_process'),net=require('net'),{chromium}=require('playwright');
const REPO=path.resolve(__dirname,'..'),ROOT=path.resolve(process.argv[2]),PY=process.env.CAUSALOPS_TEST_PYTHON||'python';
const INSTALLED=process.env.CAUSALOPS_TEST_INSTALLED==='1';
const APP_ENTRY=process.env.CAUSALOPS_TEST_APP_ENTRY||path.join(REPO,'src/causalops/ui/workbench.py');
fs.mkdirSync(ROOT,{recursive:false});
const FIX=path.join(ROOT,'controlled'),env={...process.env,PYTHONPATH:INSTALLED?'':path.join(REPO,'src'),PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',CAUSALOPS_HOME:path.join(FIX,'workspace'),STREAMLIT_BROWSER_GATHER_USAGE_STATS:'false',STREAMLIT_SERVER_SHOW_EMAIL_PROMPT:'false'};
for(const k of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[k];
const write=(p,v)=>fs.writeFileSync(p,JSON.stringify(v,null,2));
function control(mode){
 const args=[path.join(REPO,'scripts/decision_memory_fixture.py'),mode,'--root',FIX];
 if(mode==='prepare')args.push('--archive',process.env.CAUSALOPS_HILLSTROM_ARCHIVE);
 const r=cp.spawnSync(PY,args,{cwd:REPO,env,encoding:'utf8',windowsHide:true,maxBuffer:20*1024*1024});
 if(r.status!==0)throw Error('controller '+mode+' failed: '+r.stderr.slice(-1300));
 return JSON.parse(r.stdout);
}
const setup=control('prepare');write(path.join(ROOT,'setup.json'),setup);
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function freePort(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p}
(async()=>{
 let server,log,browser,page,ctx,folder,base,events;
 const results=[],providers=[];
 async function act(name,fn){const t=Date.now();await fn();events.push({action:name,at:new Date().toISOString(),milliseconds:Date.now()-t})}
 async function ready(){await page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').waitFor({state:'visible'})}
 async function capture(name){fs.writeFileSync(path.join(folder,name+'.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(folder,name+'.png'),fullPage:true})}
 async function open(item){
  await act('open_saved_report',()=>page.goto(base+'/?route=evidence&diagnostic_mode='+item.mode+'&diagnostic_task='+item.task+'&diagnostic_report='+item.report));
  await page.locator('.co-decision-memory[data-report-id="'+item.report+'"][data-task-id="'+item.task+'"]').waitFor({state:'visible'});
  await page.getByRole('button',{name:'导出诊断报告快照',exact:true}).waitFor({state:'visible'});await ready();
 }
 async function save(item,sid,kind,reason){
  const token=item.report+'_'+(sid||'note');
  if(sid){
   await act('choose_decision',()=>page.locator('.st-key-decision_type_'+token).getByRole('combobox').click());
   await act('open_decision_options_keyboard',()=>page.locator('.st-key-decision_type_'+token).getByRole('combobox').press('ArrowDown'));
   await act('select_decision',()=>page.getByRole('option',{name:{accepted:'采纳建议',deferred:'暂缓处理',rejected:'拒绝建议'}[kind],exact:true}).click());
  }
  await ready();
  const ack=page.locator('.st-key-decision_confirm_'+token);
  if(!await ack.getByRole('checkbox').isChecked()){
   await act('explicit_decision_confirmation',()=>ack.getByText('我确认仅记录研究决定，不批准或执行统计',{exact:true}).click());
  }
  await ready();
  const button=page.locator('.st-key-decision_save_'+token).getByRole('button',{name:'保存研究决定',exact:true});
  await page.locator('.st-key-decision_save_'+token+' button:not([disabled])').waitFor({state:'visible'});
  await act('enter_reason',()=>page.locator('.st-key-decision_reason_'+token).getByRole('textbox',{name:'决策原因或研究备注',exact:true}).fill(reason));
  await act('submit_decision',()=>button.click());
  await page.locator('[data-testid="stText"]').filter({hasText:reason}).first().waitFor({state:'visible'});
  await page.getByText(/^已保存研究决定：/).first().waitFor();await ready();
 }
 async function checkNext(item){
  await act('explicit_new_diagnostic',()=>page.getByRole('button',{name:item.mode==='preflight'?'检查研究条件':'检查研究证据',exact:true}).click());
  await page.waitForFunction(previous=>{const e=document.querySelector('.co-decision-memory');return e&&e.dataset.reportId!==previous},item.report);
  await page.getByRole('button',{name:'导出诊断报告快照',exact:true}).waitFor({state:'visible'});await ready();
  return {...item,report:await page.locator('.co-decision-memory').getAttribute('data-report-id')};
 }
 async function run(name,fn){
  folder=path.join(ROOT,name);fs.mkdirSync(folder);events=[];const start=Date.now();
  ctx=await browser.newContext({viewport:{width:1500,height:1100},locale:'zh-CN'});page=await ctx.newPage();page.setDefaultTimeout(35000);
  page.on('request',r=>{if(/api\.(deepseek|openai)\.com/.test(r.url()))providers.push(r.url())});
  const out={case:name,mode:'fixed_real_browser_not_human_test',status:'failed',model_requests:0,installed_package:INSTALLED};
  try{await fn(out);out.status='passed'}catch(e){out.error=String(e.stack||e);await capture('failure').catch(()=>{})}
  finally{out.seconds=(Date.now()-start)/1000;out.operations=events.length;out.events=[...events];write(path.join(folder,'result.json'),out);results.push(out);await ctx.close();console.log(name,out.status,out.error?out.error.split('\n')[0]:'')}
 }
 try{
  const p=await freePort();base='http://127.0.0.1:'+p;
  log=fs.openSync(path.join(ROOT,'server.log'),'wx');
  server=cp.spawn(PY,['-m','streamlit','run',APP_ENTRY,'--server.address=127.0.0.1','--server.port='+p,'--server.headless=true','--server.fileWatcherType=none'],{cwd:env.CAUSALOPS_HOME,env,windowsHide:true,stdio:['ignore',log,log]});
  let healthy=false;for(let i=0;i<200;i++){try{healthy=(await fetch(base+'/_stcore/health')).ok}catch{}if(healthy)break;await delay(200)}if(!healthy)throw Error('startup failed');
  browser=await chromium.launch({headless:true,executablePath:process.env.CAUSALOPS_BROWSER_EXECUTABLE});
  await run('A-record-refresh',async out=>{
   const item=setup.cases.A,reason='当前研究仅支持登记的两周访问率，不将结果解释为长期利润收益。';
   await open(item);await save(item,null,'note',reason);
   const one=control('inspect').records.filter(d=>d.context.task_ref.task_id===item.task);if(one.length!==1||one[0].context.run_refs.length!==2)throw Error('real-run decision missing');
   out.decision=one[0].decision_id;
   await act('reload_decision_history',()=>page.reload());
   await page.locator('[data-testid="stText"]').filter({hasText:reason}).waitFor();
   for(const rid of item.runs)if(!(await page.locator('body').innerText()).includes(rid))throw Error('run source missing');
   await page.getByRole('heading',{name:'研究决策历史',exact:true}).scrollIntoViewIfNeeded();await capture('saved-history');
   out.checked={explicit_note:true,no_suggestion:true,two_real_runs:true,refresh_preserved:true};
  });
  await run('B-same-problem',async out=>{
   const item=setup.cases.B,sug=item.suggestions.find(s=>s.rule_id==='PD-02');
   await open(item);await save(item,sug.suggestion_id,'deferred','先补充分配设计来源，暂缓因果解释。');
   write(path.join(folder,'controller-change.json'),control('next-B'));
   const current=await checkNext(item);out.new_report=current.report;
   await page.locator('.decision-reminder[data-kind="still_open"]').waitFor({state:'attached'});
   const text=await page.locator('body').innerText();if(!text.includes('暂缓处理')||!text.includes('尚未核验满足'))throw Error('previous choice or present unknown missing');
   await page.getByRole('heading',{name:'相关历史提醒',exact:true}).scrollIntoViewIfNeeded();await capture('same-unknown-reminder');
   out.checked={same_task_rule_scope:true,original_choice_retained:true,current_unknown:true};
  });
  await run('C-changed-evidence',async out=>{
   const item=setup.cases.C,sug=item.suggestions.find(s=>s.rule_id==='PD-06');
   await open(item);await save(item,sug.suggestion_id,'deferred','先核对报告窗口冲突，暂不使用联合结论。');
   write(path.join(folder,'controller-change.json'),control('restore-C'));
   const current=await checkNext(item);out.new_report=current.report;
   await page.locator('.decision-reminder[data-kind="current_verified"]').waitFor({state:'attached'});
   const text=await page.locator('body').innerText();if(!text.includes('先核对报告窗口冲突')||!text.includes('原决定及其证据仍保留'))throw Error('history or current check missing');
   await page.getByRole('heading',{name:'相关历史提醒',exact:true}).scrollIntoViewIfNeeded();await capture('new-evidence-check');
   out.checked={new_actual_diagnostic:true,current_verified:true,history_not_overwritten:true,no_user_resolution_fact:true};
  });
  await run('D-safety-revisions',async out=>{
   const item=setup.cases.D,sug=item.suggestions.find(s=>s.rule_id==='PD-02');
   await open(item);await save(item,sug.suggestion_id,'accepted','采纳补充来源建议，不等于批准统计。');
   await save(item,sug.suggestion_id,'accepted','采纳补充来源建议，不等于批准统计。');await delay(300);
   let rows=control('inspect').records.filter(d=>d.context.task_ref.task_id===item.task);if(rows.length!==1)throw Error('duplicate decision');
   const old=rows[0].decision_id;
   await save(item,sug.suggestion_id,'rejected','当前拒绝该建议，保留原决定与原因。');
   rows=control('inspect').records.filter(d=>d.context.task_ref.task_id===item.task);
   if(rows.length!==2||rows[1].supersedes_id!==old)throw Error('append revision missing');
   await page.getByRole('heading',{name:'研究决策历史',exact:true}).scrollIntoViewIfNeeded();await capture('revision-history');
   write(path.join(folder,'controller-change.json'),control('stale-D'));
   await act('reload_stale_report',()=>page.reload());await page.getByText('当前报告来源已变化；历史可以查看，但不能据此新增决定。请先显式重新检查。',{exact:true}).waitFor();
   if(!await page.locator('.st-key-decision_save_'+item.report+'_'+sug.suggestion_id).getByRole('button',{name:'保存研究决定',exact:true}).isDisabled())throw Error('stale save enabled');
   await capture('stale-source-no-save');
   await act('request_cross_task_report',()=>page.goto(base+'/?route=evidence&diagnostic_mode=preflight&diagnostic_task='+setup.cases.B.task+'&diagnostic_report='+item.report));
   await page.getByText('所选诊断报告不存在、版本不匹配或不属于当前任务；未打开其他历史成功报告。',{exact:true}).waitFor();
   if(await page.locator('.co-decision-memory').count())throw Error('cross-task history visible');
   await capture('cross-task-rejected');
   out.checked={duplicate_idempotent:true,append_revision:true,stale_rejected:true,cross_task_rejected:true};
  });
  const after=control('inspect');write(path.join(ROOT,'after.json'),after);
  if(!after.protected_unchanged||!after.old_reports_preserved||providers.length)throw Error('protected history changed or model called');
  write(path.join(ROOT,'summary.json'),{results,source_sha:after.source_sha,statistical_history_unchanged:after.protected_unchanged,old_reports_preserved:after.old_reports_preserved,counts:after.counts,model_requests:providers.length});
  if(results.some(x=>x.status!=='passed'))process.exitCode=1;
 }catch(e){write(path.join(ROOT,'fatal.json'),{error:String(e.stack||e)});console.error(e);process.exitCode=1}
 finally{if(browser)await browser.close();if(server)server.kill();if(log!==undefined)fs.closeSync(log)}
})();
