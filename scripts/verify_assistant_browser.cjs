const { chromium }=require(process.env.CAUSALOPS_PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path');
const root=process.env.CAUSALOPS_CAPTURE_OUT||'artifacts/browser';fs.mkdirSync(root,{recursive:true});
(async()=>{let browser=await chromium.launch({executablePath:process.env.CAUSALOPS_BROWSER_EXECUTABLE,headless:true,args:['--disable-crash-reporter','--disable-breakpad']});let ctx=await browser.newContext({viewport:{width:1460,height:1060},acceptDownloads:true,recordVideo:{dir:root}});let page=await ctx.newPage();let errors=[];page.on('pageerror',e=>errors.push(e.message));let result={};
try{
 await page.goto((process.env.CAUSALOPS_TEST_URL||'http://127.0.0.1:8510/')+'?route=assistant');await page.getByRole('button',{name:'创建任务并自动体检',exact:true}).waitFor({timeout:45000});
 await page.locator('input[type=file]').setInputFiles(process.env.CAUSALOPS_TEST_CSV||'examples/tips.csv');
 await page.getByRole('textbox',{name:'任务名称（可选）'}).fill('浏览器验收：独立上传小费数据');
 await page.getByRole('button',{name:'创建任务并自动体检',exact:true}).click();await page.getByRole('tab',{name:'任务与对话',exact:true}).waitFor({timeout:45000});
 result.auto_profile=true;result.url=page.url();await page.screenshot({path:path.join(root,'01-task.png'),fullPage:true});
 await page.getByText('提出/修改分析计划',{exact:true}).click();let chat=page.getByPlaceholder('例如：比较 total_bill 与 tip 的关系；或解释刚才的结果与局限');await chat.fill('帮我分析 total_bill 与 tip 的相关关系');await chat.press('Enter');
 await page.getByRole('button',{name:'接受并执行探索计划',exact:true}).waitFor({timeout:30000});await page.getByRole('button',{name:'接受并执行探索计划',exact:true}).click();
 await page.getByText('计划已完成。可在“结果与报告”查看，或继续提问/提出新任务。刷新不重复执行。',{exact:true}).waitFor({timeout:45000});result.plan_accept_execute=true;
 await page.getByRole('tab',{name:'结果与报告',exact:true}).click();await page.getByRole('button',{name:'下载本次完整图文报告',exact:true}).waitFor();let dl=page.waitForEvent('download');await page.getByRole('button',{name:'下载本次完整图文报告',exact:true}).click();await (await dl).saveAs(path.join(root,'downloaded-report.html'));result.download=true;await page.screenshot({path:path.join(root,'02-report.png'),fullPage:true});
 await page.getByRole('tab',{name:'方法依据 RAG',exact:true}).click();await page.getByRole('textbox',{name:'检索方法、条件、诊断或商业/学术案例'}).fill('DID平行趋势事件研究');await page.getByRole('textbox',{name:'检索方法、条件、诊断或商业/学术案例'}).press('Enter');await page.getByText('日级 DID 与事件时间诊断 · 方法规则',{exact:true}).waitFor();result.rag=true;
 await page.getByRole('tab',{name:'用户任务评测',exact:true}).click();await page.getByText('等待真实陌生使用者参加。当前没有人类效率提升数值。',{exact:true}).waitFor();result.human_records_not_fabricated=true;
 await page.reload();await page.getByRole('tab',{name:'任务与对话',exact:true}).waitFor({timeout:45000});result.restore=true;
 result.exceptions=errors;result.ok=errors.length===0 && await page.locator('[data-testid="stException"]').count()===0;
}catch(e){result.ok=false;result.error=e.message;result.page=(await page.locator('body').innerText()).slice(0,6000);await page.screenshot({path:path.join(root,'failure.png'),fullPage:true});}
finally{fs.writeFileSync(path.join(root,'acceptance.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));await ctx.close();await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
