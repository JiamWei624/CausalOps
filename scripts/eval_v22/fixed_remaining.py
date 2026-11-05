"""Five fixed UI routes; preconditions and post-run adjudication belong to the controller."""
import argparse
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path

from pilot import BrowserRun, REPO, playwright_runtime, save, server, stamp
from phase2_fixture import seed


class Journey:
    def __init__(self, page, out, result):
        self.page, self.out, self.r = page, out, result
        self.ui = BrowserRun(page, out)
        self.btn = lambda name: page.get_by_role("button", name=name, exact=True)
        self.txt = lambda name: page.get_by_text(name, exact=True).first
        self.chat = page.get_by_role("textbox", name="输入分析目标、方案调整要求或结果解读问题", exact=True)

    def op(self, kind, label, function):
        e=dict(at=stamp(),kind=kind,label=label,ok=False)
        self.r["actions"].append(e)
        t=time.perf_counter()
        try:
            v=function()
            e["ok"]=True
            return v
        finally:
            e["seconds"]=time.perf_counter()-t
            save(self.out/"actions.json",self.r["actions"])

    def click(self, node, label):
        self.op("click",label,node.click)

    def wait(self, label, function):
        t=time.perf_counter()
        try:return function()
        finally:self.r["waits"].append(dict(label=label,seconds=time.perf_counter()-t))

    def snap(self, label):
        obs, ref=self.ui.capture(label)
        self.ui.steps.append(ref)
        return obs

    def expand(self,name):
        node=self.page.locator("summary").filter(has_text=name).first
        self.wait(name, node.wait_for)
        if node.locator("..").get_attribute("open") is None:self.click(node,name)

    def ask(self,q):
        old=self.page.url
        self.op("fill",q,lambda:self.chat.fill(q))
        self.op("submit","发送问题",lambda:self.chat.press("Enter"))
        self.r["turns"]+=1
        def ready():
            end=time.monotonic()+75
            while time.monotonic()<end:
                obs=self.ui.observe()
                if self.page.url!=old and q in obs["text"] and not obs["pending"] and obs["phase"] in ("已完成","待人工审核","需要补充说明","已阻断","失败"):
                    return obs
                self.page.wait_for_timeout(200)
            raise TimeoutError("未见本轮请求和终态同时出现在新流程")
        return self.wait("新对话终态",ready)

    def paper(self,label,required=None,exclude=None):
        self.expand("研究报告预览")
        paper=self.page.locator(".co-paper").first
        self.wait(label, paper.wait_for)
        def read():
            end=time.monotonic()+25
            while time.monotonic()<end:
                body=paper.inner_text()
                h=re.search(r"\b[a-f0-9]{32}\b",paper.locator(".co-note").first.inner_text())
                if h and (not required or h[0]==required) and h[0]!=exclude:return dict(run=h[0],body=body)
                self.page.wait_for_timeout(200)
            raise TimeoutError("报告编号未切换")
        val=self.wait(label,read)
        self.r["papers"][label]=val
        self.snap(label)
        return val

    def execute(self,case):
        p=self.page
        if case=="N01":
            self.click(self.btn("导入分析数据"),"导入分析数据")
            self.wait("导入页", self.txt("导入分析表").wait_for)
            self.wait("创建控件就绪",self.btn("创建任务并检查数据").wait_for)
            assert p.locator('input[type="file"]').count()==1
            assert self.btn("创建任务并检查数据").is_visible() and self.btn("创建任务并检查数据").is_disabled()
        elif case=="N03":
            self.click(self.txt("人工审核"),"人工审核")
            self.wait("审核事项",self.txt("研究声明与识别限制").wait_for)
            self.expand("核对完整配置、计划和数据版本")
            obs=self.snap("read-review")
            assert all(k in obs["text"] for k in ("男装邮件","未发邮件","两周","程序核对","研究声明与识别限制","待人工审核"))
        elif case=="N05":
            self.click(p.locator('[data-testid="stSidebar"]').get_by_role("button",name=re.compile("研究记录")),"研究记录")
            box=p.get_by_role("combobox",name="选择任务")
            self.click(box,"选择任务")
            self.click(p.get_by_role("option").filter(has_text="营销邮件 · 两周访问率"),"选中两周访问率任务")
            self.wait("历史任务、运行与摘要一致",lambda:p.wait_for_function("""() => {
                const box=document.querySelector('.st-key-panel_trace [data-history-rid]');
                const chosen=document.querySelector('.st-key-panel_history [role=combobox]')?.value||'';
                const run=document.querySelector('.st-key-panel_trace [role=combobox]')?.value||'';
                const id=box?.dataset.historyRid, text=box?.innerText||'';
                return id && chosen.includes('两周访问率') && run.includes(id.slice(0,8))
                  && text.includes('运行编号：'+id) && text.includes('观察窗口：分配后两周')
                  && /两周访问率的估计平均差异.*个百分点/.test(text);
            }""",timeout=25000))
            self.r["history_text"]=self.snap("history")["text"]
            self.click(self.btn("继续研究"),"继续研究")
            self.paper("selected")
            self.r["answer"]=self.ask("请只读所选男装邮件与未发邮件组的两周访问率报告，解释两组相差多少个百分点，并引用运行来源。")["reply"]
        else:
            old=self.paper("original")
            revision=("把每日订单数改为每日访客人数（visitors），保留旧报告，生成新的访客指标待审方案。" if case=="N06" else
                      "把原全期订单报告改为最近五个自然日。请保留旧报告，列出新窗口起止日期和覆盖情况，生成待审计划。")
            obs=self.ask(revision)
            assert obs["phase"]=="待人工审核",obs["phase"]
            if not obs["plan_text"]:self.expand("分析方案")
            plan=self.snap("candidate")["plan_text"]
            self.r["candidate"]=plan
            if case=="N06":assert re.search(r'(?:本次计划指标|目标指标|结果|本次研究口径)[：:].*(?:visitors|访客)',plan),plan
            else:
                from datetime import date
                window=re.search(r"(\d{4}-\d\d-\d\d)\s*至\s*(\d{4}-\d\d-\d\d)",plan)
                assert window and (date.fromisoformat(window[2])-date.fromisoformat(window[1])).days==4 and "筛选" in plan,plan
            confirmation=p.get_by_text(re.compile("我已核对上述计划")).first
            if not confirmation.is_visible():self.click(self.txt("人工审核"),"人工审核")
            self.click(confirmation,"核对本版方案")
            self.click(self.btn("接受计划并批准本次执行"),"批准并执行")
            self.wait("执行终态",lambda:p.wait_for_function("() => /分析状态[：:]\\s*已完成/.test(document.body.innerText)",timeout=75000))
            new=self.paper("new",exclude=old["run"])
            self.r["answer"]=self.ask("请说明刚才的新报告中目标指标的均值、单位、观察范围，并引用该运行。")["reply"]
            self.op("reload","刷新",p.reload)
            self.wait("刷新后工作台",self.chat.wait_for)
            self.paper("restored",required=new["run"])
            choice=p.get_by_role("combobox",name="结果展示与追问所依据的运行",exact=True)
            if not choice.is_visible():self.expand("选择报告（按指标与观察期）")
            self.click(choice,"选择历史报告")
            if not p.get_by_role("option").first.is_visible():self.op("key","展开选项",lambda:choice.press("ArrowDown"))
            self.click(p.get_by_role("option").filter(has_text=old["run"][:8]),"选择原订单报告")
            self.paper("reopened",required=old["run"])


def attempt(case,root):
    out=root/case;out.mkdir();home=out/"workspace";home.mkdir()
    r=dict(case=case,attempt=1,mode="fixed/local",git=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
           os=platform.platform(),actions=[],waits=[],turns=0,help=0,interventions=0,papers={},state="起点未就绪")
    start=None
    try:
        init=seed(case,home);save(out/"initial.json",init)
        with server(home,out/"server.log") as base,playwright_runtime() as pw:
            browser=pw.chromium.launch(headless=True,**({"executable_path":os.environ["CAUSALOPS_BROWSER_EXECUTABLE"]} if os.getenv("CAUSALOPS_BROWSER_EXECUTABLE") else {}))
            page=browser.new_page(viewport={"width":1440,"height":1000},locale="zh-CN");page.set_default_timeout(25000)
            j=Journey(page,out,r);r["browser"]=browser.version
            try:
                if case in ("N06","N07"):
                    page.goto(base+"/?route=assistant&assistant="+init["target"]["sid"])
                    j.chat.wait_for(timeout=65000)
                else:
                    page.goto(base+"/?route=home")
                    j.btn("查看营销实验").wait_for(timeout=65000)
                    if case=="N03":
                        j.btn("查看营销实验").click()
                        j.txt("已核对来源、随机分配、两组定义与两周访问指标").click()
                        j.btn("创建研究任务并生成待审方案").click()
                        j.txt("人工审核").wait_for(timeout=65000)
                j.snap("start")
                r.update(started=stamp(),start_url=page.url,state="未完成")
                start=time.perf_counter()
                j.execute(case)
                r["state"]="路线结束待核验"
            except Exception as e:r["failure"]=str(e)[:1400] or type(e).__name__
            finally:
                r["ended"]=stamp()
                if start is not None:r["seconds"]=time.perf_counter()-start
                r["end_url"]=page.url
                try:j.snap("end")
                finally:
                    save(out/"browser-events.json",j.ui.events)
                    browser.close()
    except Exception as e:r["infrastructure"]=str(e)[:1000]
    finally:save(out/"result.json",r)
    print(case,r["state"],r.get("failure","")[:100],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    for case in ("N01","N03","N05","N06","N07"):attempt(case,args.out)
