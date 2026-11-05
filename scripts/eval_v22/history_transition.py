"""Sample visible history report identities at animation frames, before and after UI repair."""
import argparse, json, os, re
from pathlib import Path
from phase2_fixture import seed
from pilot import BrowserRun, playwright_runtime, save, server

MONITOR = r"""() => {
window.hframes = []; let last = '';
function tick(){
 const panel=document.querySelector('.st-key-panel_trace'), sidebar=document.querySelector('.st-key-panel_history');
 const text=panel?.innerText||'';
 const combos=(n)=>n?.querySelector('[role=combobox]')?.value||'';
 const mag=text.split('\n').find(x=>x.includes('个百分点') && /购买率|访问率/.test(x))||'';
 const scope=panel?.querySelector('[data-history-rid]');
 const row={task:combos(sidebar),choice:combos(panel),rid:(text.match(/运行编号：\s*([a-f0-9]{32})/)||[])[1]||'',
 metric:mag.includes('购买率')?'购买率':mag.includes('访问率')?'访问率':'',window:mag.includes('两周')?'两周':'',
 body:mag,source:scope?.dataset.historyRid||'',label:scope?.querySelector('strong')?.innerText||''};
 const state=JSON.stringify(row),t=performance.now();
 if(state!==last){window.hframes.push({...row,t,last_t:t});last=state}
 else window.hframes[window.hframes.length-1].last_t=t;
 window.hraf=requestAnimationFrame(tick);
}tick();
}"""

def main(out):
    out.mkdir(parents=True,exist_ok=False)
    home=out/'workspace';home.mkdir()
    init=seed('N05',home);save(out/'fixture.json',init)
    with server(home,out/'service.log') as base, playwright_runtime() as pw:
        b=pw.chromium.launch(executable_path=os.environ['CAUSALOPS_BROWSER_EXECUTABLE'])
        p=b.new_page(viewport={'width':1440,'height':1000},locale='zh-CN')
        p.goto(base+'/?route=history');combo=p.get_by_role('combobox',name='选择任务')
        combo.wait_for();p.get_by_text(re.compile('购买率的估计平均差异')).first.wait_for()
        p.evaluate(MONITOR)
        for k in range(6):
            target='访问率' if k%2==0 else '购买率';ref=init['target' if k%2==0 else 'distractor']
            combo.click();p.get_by_role('option').filter(has_text='营销邮件 · 两周'+target).click()
            p.wait_for_function("""([rid,metric])=>{const r=window.hframes.at(-1);return r.rid===rid&&r.metric===metric&&r.window==='两周'&&r.last_t-r.t>=250}""",arg=[ref['run'],target],timeout=25000)
        frames=p.evaluate("()=>{cancelAnimationFrame(window.hraf);return window.hframes}")
        save(out/'frames.json',frames)
        wrong=[f for f in frames if f['metric'] and f['rid'] and f['rid']!=init['target' if f['metric']=='访问率' else 'distractor']['run']]
        unlabelled=[f for f in frames if f['metric'] and ('访问率' in f['task'] or '购买率' in f['task']) and f['metric'] not in f['task'] and f['metric'] not in f['label']]
        save(out/'checks.json',dict(switches=6,wrong_binding=wrong,unlabelled_previous=unlabelled,sampled_states=len(frames)))
        p.screenshot(path=str(out/'final.png'));b.close()
        print('wrong frames (distinct states)',len(wrong),'unlabelled',len(unlabelled),flush=True)
        return int(bool(wrong or unlabelled))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('out',type=Path)
    raise SystemExit(main(parser.parse_args().out))

