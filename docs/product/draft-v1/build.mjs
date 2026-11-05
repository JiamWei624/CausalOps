import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const {marked}=process.env.MARKED_MODULE ? await import(pathToFileURL(process.env.MARKED_MODULE)) : await import('marked');
const files=fs.readdirSync(root).filter(f=>/^0[0-6]_.*\.md$/.test(f)).sort();
files.push('REVISION_V1_CANDIDATE.md');
const order=[1,2,3,4,6,5,0,7];
const ids=new Map(files.map((f,i)=>[f,'document-'+i]));
const esc=s=>s.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
const titles=files.map(f=>fs.readFileSync(path.join(root,f),'utf8').split('\n')[0].replace(/^#\s*/,''));
let body='';
for(const i of order){
 const f=files[i];
 let h=marked.parse(fs.readFileSync(path.join(root,f),'utf8'),{gfm:true});
 h=h.replace(/href="([^"]+)"/g,(all,url)=>{const [file,fragment]=decodeURI(url).split('#');return ids.has(file)?'href="#'+(fragment||ids.get(file))+'"':all;});
 h=h.replace(/<img([^>]*?)src="([^"]+)"([^>]*)>/g, '<a href="$2" target="_blank" rel="noopener" title="查看原图"><img$1src="$2"$3></a>');
 h=h.replace(/<table>/g,'<div class="table-wrap"><table>').replace(/<\/table>/g,'</table></div>');
 body+='<article id="'+ids.get(f)+'"><div class="doc-label">候选 '+String(i).padStart(2,'0')+'</div>'+h+'</article>';
}
const nav=order.map(i=>{const f=files[i];return '<a href="#'+ids.get(f)+'">'+esc(titles[i])+'</a>';}).join('');
const html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CausalOps 产品 PRD V1.0 候选</title><style>'+
'*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:#f3f6f7;color:#24383f;font:16px/1.85 "Microsoft YaHei","Noto Sans CJK SC",sans-serif}a{color:#086e68;text-underline-offset:3px}aside{position:fixed;inset:0 auto 0 0;width:265px;background:#123f40;color:#e2eeeb;padding:30px 23px;overflow:auto}aside h2{font-size:23px;color:white;margin:0 0 10px}aside p{font-size:13px;line-height:1.65;color:#c0d6d5}aside a{display:block;color:#e4efed;padding:10px 0;border-bottom:1px solid #355d5d;font-size:14px;text-decoration:none}main{max-width:1510px;margin-left:265px;padding:35px 4vw 70px}header,article{background:white;border:1px solid #dce6e7;border-radius:8px;padding:30px 36px;margin-bottom:28px}header h1{font-size:30px;margin:8px 0}header p{margin:10px 0}header .badge,.doc-label{font-size:13px;font-weight:700;color:#176e67;letter-spacing:1px}.notice{border-left:4px solid #b08b42;background:#fbf7ef;padding:12px 16px}article{scroll-margin-top:20px}article h1{font-size:29px;line-height:1.45;margin:12px 0 20px}h2{font-size:22px;margin:34px 0 15px;border-bottom:1px solid #dbe4e5;padding-bottom:10px;color:#164f4d}h3{font-size:18px;margin-top:27px}p{margin:13px 0}li{margin:5px 0}.table-wrap{overflow-x:auto;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.7}th,td{padding:12px 13px;text-align:left;vertical-align:top;border:1px solid #dae3e5;min-width:90px}th{background:#edf4f2;color:#184b48}tr:nth-child(even) td{background:#fafcfc}img{max-width:100%;height:auto;border:1px solid #dce4e5;border-radius:4px}code{font-family:Consolas,monospace;font-size:.9em;background:#edf2f4;padding:2px 5px;overflow-wrap:anywhere}blockquote{border-left:3px solid #31857c;margin:20px 0;padding:2px 20px;background:#f7faf9}article em{color:#526974;font-size:14px}footer{color:#63757d;font-size:13px}@media(max-width:900px){aside{position:static;width:auto}main{margin-left:0;padding:14px}header,article{padding:22px}aside a{display:inline-block;margin-right:15px}article h1{font-size:25px}}@media print{aside{display:none}main{margin:0;padding:0}header,article{border:0;padding:12px;break-before:page}.table-wrap{overflow:visible}tr,img{break-inside:avoid}body{background:white;font-size:11pt}a{color:inherit}}'+
'</style></head><body><aside><h2>CausalOps</h2><p>产品 PRD V1.0 候选<br>现状 PRD · 迭代方案 · 自动化规划<br>归档基线 1737c9c</p>'+nav+'<p>方向已认可；具体范围与实施待确认。</p></aside><main><header><div class="badge">产品经理作品集 / V1.0 候选</div><h1>产品定位、现状规则与自动化方向</h1><p>以真实源码、已保存页面和评测结果说明产品的能力与边界。</p><div class="notice">当前为单用户本地 Beta；没有真人完成率或提效数据。V2.3 保留集每模式执行 13 题，已确认正确处理 0/13，另 7 题未执行。自动化方向及优先级已认可，具体范围、排期与开发未授权。</div><p><a href="README.md">文档目录与阅读说明</a> · 2026-11-05</p></header>'+body+'<footer>本阅读版由同目录 Markdown 生成。未改动产品页面或业务逻辑，未进行新的研究评测。</footer></main></body></html>';
fs.writeFileSync(path.join(root,'index.html'),html,'utf8');
console.log(JSON.stringify({documents:files.length,output:'index.html',bytes:Buffer.byteLength(html)}));
