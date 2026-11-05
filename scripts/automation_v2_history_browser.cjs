const fs=require('fs'),path=require('path'),cp=require('child_process'),{chromium}=require('playwright');
const ROOT=path.resolve(process.argv[2]),PY=process.env.CAUSALOPS_TEST_PYTHON;
fs.mkdirSync(ROOT,{recursive:false});
const source=path.resolve(process.argv[3]),home=path.join(ROOT,'workspace');fs.cpSync(source,home,{recursive:true});
const app=process.env.CAUSALOPS_TEST_APP_ENTRY;
const log=fs.openSync(path.join(ROOT,'server.log'),'wx');
const p=36671,base='http://127.0.0.1:'+p;
const env={...process.env,CAUSALOPS_HOME:home,PYTHONPATH:'',PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',STREAMLIT_BROWSER_GATHER_USAGE_STATS:'false'};
for(const k of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[k];
const proc=cp.spawn(PY,['-m','streamlit','run',app,'--server.address=127.0.0.1','--server.port='+p,'--server.headless=true','--server.fileWatcherType=none'],{cwd:home,env,windowsHide:true,stdio:['ignore',log,log]});
const query=String.raw`import sqlite3,json,sys
c=sqlite3.connect('file:'+sys.argv[1].replace('\\','/')+'?mode=ro',uri=True)
print(json.dumps(c.execute('SELECT id,status FROM automation_v2_tasks ORDER BY created').fetchall()))`;
const tasks=JSON.parse(cp.execFileSync(PY,['-I','-c',query,path.join(home,'research.sqlite3')],{encoding:'utf8',windowsHide:true}));
const samples=[],events=[],result={mode:'fixed_installed_history_transition',status:'failed',samples,events,tasks};
let browser;const start=Date.now();
(async()=>{try{
 for(let i=0;i<300;i++){try{if((await fetch(base+'/_stcore/health')).ok)break}catch{}await new Promise(r=>setTimeout(r,200));}
 browser=await chromium.launch({headless:true,executablePath:process.env.CAUSALOPS_BROWSER_EXECUTABLE});
 const page=await browser.newPage({viewport:{width:1500,height:1100},locale:'zh-CN'});
 await page.exposeFunction('__sample',v=>samples.push({...v,at:Date.now()}));
 await page.addInitScript(()=>setInterval(()=>{const b=document.body;if(!b)return;const article=b.querySelector('.co-automation-report');const tid=(b.innerText.match(/任务 ([0-9a-f]{32}) · 计划/)||[])[1];const report=(article?.innerText.match(/任务：([0-9a-f]{32})/)||[])[1];if(tid&&report)window.__sample({task:tid,report,report_visible:getComputedStyle(article).visibility!=="hidden",mismatch:tid!==report&&getComputedStyle(article).visibility!=="hidden",selector:b.querySelector('[data-testid="stSelectbox"] [role="combobox"]')?.innerText||'',status:(b.innerText.match(/任务状态：([^\n]+)/)||[])[1]||'',article_stale:!!article.closest('[data-stale="true"]')}).catch(()=>{});},50));
 await page.goto(base+'/?route=automation&automation='+tasks[0][0]);
 await page.getByText('任务状态：已完成',{exact:true}).waitFor();
 for(let n=0;n<6;n++){
  const target=tasks[(n+1)%tasks.length],begin=Date.now();
  await page.getByRole('combobox',{name:'自动化任务与历史报告',exact:true}).click();
  await page.getByRole('option').filter({hasText:target[0].slice(0,8)}).click();
  await page.waitForFunction(id=>{const a=document.querySelector('.co-automation-report');return a&&a.innerText.includes('任务：'+id)},target[0]);
  await new Promise(r=>setTimeout(r,600));
  fs.writeFileSync(path.join(ROOT,'switch-'+n+'.txt'),await page.locator('body').innerText());
  await page.screenshot({path:path.join(ROOT,'switch-'+n+'.png'),fullPage:true});
  events.push({target:target[0],expected_status:target[1],milliseconds:Date.now()-begin});
 }
 result.mismatch_samples=samples.filter(s=>s.mismatch).length;
 result.hidden_old_report_samples=samples.filter(s=>s.task!==s.report&&!s.report_visible).length;
 result.selector_lag_samples=samples.filter(s=>s.status==='已完成'&&!s.selector.includes('已完成')).length;
 result.status=result.mismatch_samples?'failed':'passed';
}catch(e){result.error=String(e.stack||e)}finally{result.seconds=(Date.now()-start)/1000;fs.writeFileSync(path.join(ROOT,'result.json'),JSON.stringify(result,null,2));if(browser)await browser.close();proc.kill();fs.closeSync(log);console.log(result.status,result.error||'',samples.length);if(result.status!=='passed')process.exitCode=1;}})();