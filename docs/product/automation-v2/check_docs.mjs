import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const dir=path.dirname(fileURLToPath(import.meta.url));
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE));
const checks={scope:'documentation_only_not_product_acceptance',date:'2026-11-05',baseline:'5ac788f',errors:[],views:[],screenshots:[]};
fs.mkdirSync(path.join(dir,'previews'),{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.EDGE_PATH});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 await page.route(/^https?:/,route=>route.abort());
 const jsErrors=[];page.on('pageerror',e=>jsErrors.push(e.message));
 await page.goto(pathToFileURL(path.join(dir,'prototype.html')).href);
 if(!await page.locator('#approve').isDisabled())checks.errors.push('设计审核未勾选时按钮未禁用');
 for(const state of ['goal','review','running','paused','report']){
  await page.locator('.toolbar button[data-state="'+state+'"]').click();
  const visible=await page.locator('#'+state).isVisible();
  const over=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  checks.views.push({page:'prototype',state,width:1440,visible,overflow:over});
  if(!visible||over)checks.errors.push('原型状态或溢出错误：'+state);
  const p='previews/'+state+'.png';await page.screenshot({path:path.join(dir,p),fullPage:true});checks.screenshots.push(p);
 }
 await page.locator('.toolbar button[data-state="review"]').click();
 await page.locator('#confirm').check();
 if(await page.locator('#approve').isDisabled())checks.errors.push('设计审核勾选后按钮仍禁用');
 await page.locator('#approve').click();
 if(!await page.locator('#running').isVisible())checks.errors.push('原型状态切换失败');
 await page.setViewportSize({width:800,height:1000});
 await page.locator('.toolbar button[data-state="review"]').click();
 checks.views.push({page:'prototype',state:'review',width:800,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
 await page.screenshot({path:path.join(dir,'previews/review-800.png'),fullPage:true});
 for(const width of [1440,800]){
  await page.setViewportSize({width,height:1100});
  await page.goto(pathToFileURL(path.join(dir,'index.html')).href);
  const row=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,articles:document.querySelectorAll('article').length,images:[...document.images].map(i=>({src:i.getAttribute('src'),ok:i.complete&&i.naturalWidth>0}))}));
  checks.views.push({page:'index',width,...row});
  if(row.overflow||row.articles!==3||row.images.some(i=>!i.ok))checks.errors.push('阅读版检查失败：'+width);
 }
 await page.setViewportSize({width:1440,height:1100});
 await page.goto(pathToFileURL(path.join(dir,'index.html')).href);
 await page.screenshot({path:path.join(dir,'previews/prd.png')});
 checks.errors.push(...jsErrors);
}finally{await browser.close()}
const plan=JSON.parse(fs.readFileSync(path.join(dir,'plan-example.json'),'utf8'));
const seen=new Set();
for(const s of plan.steps){
 if(seen.has(s.step_id)||s.depends_on.some(d=>!seen.has(d)))checks.errors.push('计划示例依赖次序错误');
 seen.add(s.step_id);
}
checks.plan={steps:plan.steps.length,statistical_steps:plan.steps.filter(s=>s.kind==='statistical').length,within_limit:plan.steps.length<=plan.budgets.max_steps};
let links=0;
for(const f of fs.readdirSync(dir).filter(f=>f.endsWith('.md'))){
 const body=fs.readFileSync(path.join(dir,f),'utf8');
 for(const m of body.matchAll(/\]\(([^)]+)\)/g)){
  let target=m[1];if(/^(https?:|mailto:)/.test(target))continue;
  const [file,anchor]=target.split('#');if(!file)continue;
  const resolved=path.resolve(dir,decodeURI(file));
  links++;
  if(!fs.existsSync(resolved)&&file!=='DOCUMENT_CHECKS.json')checks.errors.push('本地链接不存在：'+f+' → '+target);
  if(anchor&&file.endsWith('.md')&&fs.existsSync(resolved)&&!fs.readFileSync(resolved,'utf8').includes('id="'+anchor+'"'))checks.errors.push('显式锚点不存在：'+target);
 }
}
checks.local_links_checked=links;
checks.product_tests_run=false;checks.model_calls=0;
checks.passed=checks.errors.length===0;
fs.writeFileSync(path.join(dir,'DOCUMENT_CHECKS.json'),JSON.stringify(checks,null,2));
console.log(JSON.stringify({passed:checks.passed,errors:checks.errors,views:checks.views.length,links,plan:checks.plan}));
if(!checks.passed)process.exitCode=1;
