import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const dir=path.dirname(fileURLToPath(import.meta.url));
const {marked}=process.env.MARKED_MODULE?await import(pathToFileURL(process.env.MARKED_MODULE)):await import('marked');
const files=['PRD.md','FEASIBILITY.md','DECISIONS.md'];
const titles=['专项 PRD','源码可行性','设计取舍'];
let body='';
files.forEach((f,i)=>{
 let h=marked.parse(fs.readFileSync(path.join(dir,f),'utf8'));
 h=h.replace(/href="(PRD.md|FEASIBILITY.md|DECISIONS.md)(#[^"]*)?"/g,(m,file,fragment)=>'href="'+(fragment||'#doc'+files.indexOf(file))+'"');
 h=h.replace(/<table>/g,'<div class="table"><table>').replace(/<\/table>/g,'</table></div>');
 body+='<article id="doc'+i+'">'+h+'</article>';
});
const css='*{box-sizing:border-box}body{margin:0;background:#f3f6f5;color:#263d38;font:16px/1.85 "Microsoft YaHei",sans-serif}aside{position:fixed;width:230px;inset:0 auto 0 0;background:#163f3d;color:#e4f0eb;padding:30px 23px}aside a{display:block;color:#e4f0eb;padding:12px 0}main{margin-left:230px;max-width:1550px;padding:30px 4vw}article,header{padding:30px;background:white;border:1px solid #d6e2dc;border-radius:6px;margin-bottom:25px}h1{font-size:29px;line-height:1.5}h2{font-size:22px;border-bottom:1px solid #d7e3dc;padding-bottom:8px;margin-top:30px}h3{font-size:18px}a{color:#096a60}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #cdded4;text-align:left;vertical-align:top;padding:10px;min-width:90px}th{background:#eaf3ee}.table{overflow:auto}code{background:#eff4f1;padding:2px 4px;overflow-wrap:anywhere;font-size:.9em}img{max-width:100%;height:auto}header p{border-left:3px solid #aa8c48;padding-left:15px}article{scroll-margin-top:20px}@media(max-width:900px){aside{position:static;width:auto}aside a{display:inline-block;margin-right:15px}main{margin:0;padding:15px}article{padding:20px}}@media print{aside{display:none}main{margin:0;padding:0}article{break-before:page;border:0}.table{overflow:visible}}';
fs.writeFileSync(path.join(dir,'index.html'),'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CausalOps 自动化 V2 专项 PRD</title><style>'+css+'</style></head><body><aside><h2>CausalOps</h2><p>自动化 V2<br>专项设计候选</p>'+files.map((f,i)=>'<a href="#doc'+i+'">'+titles[i]+'</a>').join('')+'<a href="prototype.html">低保真交互原型</a><a href="README.md">文档与图源目录</a><p>仅设计 · 尚未开发</p></aside><main><header><h1>多步骤自主研究规划</h1><p>基于5ac788f真实源码核查。整体计划审批、固定依赖链、逐步授权和证据整合。设计与现状分开标记；没有新增实测成绩。</p></header>'+body+'</main></body></html>');
console.log(JSON.stringify({documents:files.length,output:'index.html'}));
