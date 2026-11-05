"""Build documentation-only SVGs and source reference manifest; never import product."""
from pathlib import Path
import hashlib,json,re,html
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
def text(x,y,s,size=16,fill='#244641',weight='normal'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}">{html.escape(s)}</text>'
def box(x,y,w,h,lines,fill='#ffffff'):
    out=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="#a9c4bc"/>'
    for i,s in enumerate(lines):out+=text(x+16,y+29+i*24,s,16 if i==0 else 13)
    return out
def arrow(x1,y1,x2,y2):
    return f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#638c80" stroke-width="2" marker-end="url(#arr)"/>'
def wrap(title,w,h,content):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{title}"><defs><marker id="arr" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7" fill="#638c80"/></marker></defs><rect width="100%" height="100%" fill="#f7faf8"/><g font-family="Microsoft YaHei, sans-serif">'+text(30,38,title,23,weight='bold')+text(30,66,'自动化 V2 · 设计稿，尚未实现',13)+' '.join(content)+'</g></svg>'
c=[text(30,104,'用户与规划',15,weight='bold')]
for x,ls in [(30,['明确目标','单表 / 两周访问率']),(280,['预检与来源确认','只读，不生成统计Run']),(530,['有限研究计划','模型可选 / 固定范围']),(780,['整体人工批准','绑定数据、步骤和预算'])]:
    c.append(box(x,120,220,76,ls))
for x in [250,500,750]:c.append(arrow(x,157,x+30,157))
c+=[text(30,245,'批准后的真实依赖：5个逻辑步骤，2次统计调用',17,weight='bold')]
for x,ls,fill in [(30,['S01 审计','重新验证批准范围'],'white'),(230,['S02 描述统计','保存实际分组Run'],'#e5f1ec'),(430,['S03 证据门禁','读取S02样本与口径'],'white'),(630,['S04 A/B计算','只在门禁通过后调用'],'#e5f1ec'),(830,['S05 整合报告','核对两个Run及来源'],'white')]:
    c.append(box(x,270,180,90,ls,fill))
for x in [210,410,610,810]:c.append(arrow(x,315,x+20,315))
c+=[arrow(890,196,890,220),text(730,237,'按完整批准依次执行',12),arrow(520,360,520,410),box(350,410,340,74,['条件不足 / 证据不一致 → 停止','不换方法、不补事实、不继续下游'],'#fff6e6'),text(30,530,'绿色节点＝统计调用；其他节点＝只读核验或证据整合。人工批准不是统计步骤。',14)]
(BASE/'diagrams/user-flow.svg').write_text(wrap('用户流程与步骤依赖',1040,560,c),encoding='utf8')
c=[]
for x,ls in [(30,['预检 / 澄清','明确数据与条件']),(270,['候选 / 待审核','整个计划固定']),(510,['已批准','逐步验证权限']),(750,['运行中','证据与预算检查'])]:
    c.append(box(x,110,210,80,ls))
for x in [240,480,720]:c.append(arrow(x,150,x+30,150))
c += [arrow(855,190,855,240),box(750,240,210,72,['完成','全部必要证据齐全'],'#e5f1ec')]
for x,ls in [(30,['暂停 / 中断','保留在途证据']),(270,['执行失败','不无限重试']),(510,['安全阻断','条件或授权冲突'])]:
    c.append(box(x,265,210,80,ls,'#fff6e6'))
c += [f'<path d="M750,170 L730,170 L730,220 L135,220 L135,265" fill="none" stroke="#638c80" marker-end="url(#arr)"/>',arrow(135,345,135,400),arrow(375,345,375,400),box(30,400,450,85,['人工确认恢复 → 证据调和','原批准有效且结果唯一才继续；否则停止']),box(510,400,450,85,['取消 → 当前任务终止','旧证据保留；重开为新任务并重新审核']),text(30,535,'任务状态、步骤状态与后台Job状态分别保存；页面刷新不授予执行权限。',14),text(30,561,'完整转移（含恢复、重新候选）见同名 .mmd；图中突出关键状态族。',13)]
(BASE/'diagrams/state.svg').write_text(wrap('执行状态与恢复边界',1000,590,c),encoding='utf8')
c=[box(30,110,940,80,['界面层 / 复用与扩展','Streamlit：目标、整体审核、进度、报告；BackgroundJobs：异步与恢复']),arrow(500,190,500,220),box(30,220,940,80,['服务与编排 / 复用与扩展','ResearchService → LangGraph：路由、检索、规划、审核中断']),arrow(500,300,500,330),box(30,330,455,110,['新增：BoundedCoordinator','固定依赖 / 逐步授权 / 失败停止','PlanV2、BudgetLedger、EvidenceAdapter'],'#e5f1ec'),box(515,330,455,110,['复用：AnalysisTools / TaskRuntime','原统计工具、检查点、Run核对','descriptive / ab_test；不改估计器']),arrow(485,385,515,385),arrow(745,440,745,470),box(30,470,940,85,['证据层 / 复用存储＋新增引用清单','SQLite / Parquet / 原Run与ToolResult → ReportManifest → 页面与报告']),text(30,595,'模型是可选规划与解释来源；不批准、不写研究事实、不拥有统计工具直接执行权限。',14)]
(BASE/'diagrams/architecture.svg').write_text(wrap('最小实现架构与复用边界',1000,625,c),encoding='utf8')
paths=re.findall(r'\]\((\.\./\.\./\.\./src/[^)#]+)',(BASE/'FEASIBILITY.md').read_text(encoding='utf8'))
rows=[]
for rel in sorted(set(paths)):
    p=(BASE/rel).resolve();b=p.read_bytes();s=b.decode('utf8')
    symbols=[{'line':i,'declaration':line.strip()} for i,line in enumerate(s.splitlines(),1) if re.match(r'^\s*(?:class|def) ',line)]
    rows.append({'file':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(b).hexdigest(),'symbols':symbols})
(BASE/'SOURCE_MANIFEST.json').write_text(json.dumps({'baseline':'5ac788f','mode':'read_only_source_inspection_no_product_execution','files':rows},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'svgs':3,'source_files':len(rows)}))
