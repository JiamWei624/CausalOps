"""Run one prepared attempt through a real Chromium and Streamlit UI."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SELECTOR = 'button,a[href],textarea,input,select,summary,[role="tab"],[role="option"],[role="radio"],[role="combobox"],[role="button"],[role="checkbox"]'
CHAT = "输入分析目标、方案调整要求或结果解读问题"

def stamp():
    return datetime.now(timezone.utc).isoformat()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

@contextmanager
def server(home, log):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    env=dict(os.environ, CAUSALOPS_HOME=str(home), PYTHONPATH=str(REPO/"src"), PYTHONDONTWRITEBYTECODE="1",
             STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",STREAMLIT_SERVER_SHOW_EMAIL_PROMPT="false")
    env.pop("DEEPSEEK_API_KEY",None)
    with log.open("xb") as out:
        proc=subprocess.Popen([sys.executable,"-m","streamlit","run",str(REPO/"src/causalops/ui/workbench.py"),
                               "--server.address=127.0.0.1",f"--server.port={port}","--server.headless=true",
                               "--server.fileWatcherType=none"],cwd=home,env=env,stdout=out,stderr=out,
                              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        try:
            base=f"http://127.0.0.1:{port}"
            for _ in range(100):
                if proc.poll() is not None:raise RuntimeError("工作台启动进程已退出")
                try:
                    with urlopen(base+"/_stcore/health",timeout=1) as resp:
                        if resp.status==200:break
                except OSError:time.sleep(.4)
            else:raise TimeoutError("工作台健康探测超时")
            yield base
        finally:
            if proc.poll() is None:proc.terminate()
            try:proc.wait(10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

def playwright_runtime():
    if os.environ.get("CAUSALOPS_PLAYWRIGHT_PYTHONPATH"):
        sys.path.append(os.environ["CAUSALOPS_PLAYWRIGHT_PYTHONPATH"])
    from playwright.sync_api import sync_playwright
    return sync_playwright()

def authorize(page,base,sid,key,mark):
    # No capture or tracing while the credential editor is open.
    page.goto(base+"/?"+urlencode({"route":"settings","assistant":sid}))
    mark("open_connection")
    page.locator("summary").filter(has_text="连接配置").first.click(timeout=65000)
    field=page.locator('input[type="password"]')
    mark("fill_masked")
    field.fill(key)
    field.press("Enter")
    page.get_by_text("已配置，尚未验证连接",exact=False).first.wait_for(timeout=15000)
    mark("save_connection")
    page.get_by_role("button",name="保存连接配置",exact=True).click()
    mark("save_receipt")
    page.get_by_text("连接配置已保存于本次会话内存。",exact=True).wait_for()
    mark("enter_task")
    page.get_by_role("button",name="前往数据导入与已有任务",exact=True).click()
    page.get_by_role("textbox",name=CHAT,exact=True).wait_for(timeout=65000)
    mark("open_permissions")
    panel=page.locator("summary").filter(has_text="当前任务 · 数据与权限").first
    if panel.locator("..").get_attribute("open") is None:panel.click()
    permission=page.get_by_text("允许本任务向以上模型发送字段摘要、研究问题及运行汇总",exact=True)
    if not permission.is_visible():
        page.locator("summary").filter(has_text="模型连接与数据发送许可").first.click()
    mark("grant_task")
    permission.click()
    mark("verify_grant")
    page.get_by_text("DeepSeek 官方 / deepseek-flash · 本任务已授权",exact=False).first.wait_for(timeout=15000)
    panel.click()


def flow(url):
    return parse_qs(urlparse(url).query).get("flow",[""])[0]

class BrowserRun:
    def __init__(self,page,folder):
        self.page=page
        self.folder=folder
        self.script=(HERE/"observe.js").read_text("utf-8-sig")
        self.events=[]
        self.steps=[]
        self.last_question=None
        self.last_flow=None
        page.on("pageerror",lambda exc:self.events.append({"at":stamp(),"kind":"pageerror","type":type(exc).__name__}))
        page.on("requestfailed",lambda req:self.events.append({"at":stamp(),"kind":"request_failed","host":urlparse(req.url).hostname,"resource":req.resource_type}))

    def observe(self):
        obs=self.page.evaluate(self.script)
        if self.last_question and flow(obs["url"])==self.last_flow:
            obs["reply"]=""
        return obs

    def capture(self,label):
        obs=self.observe()
        name=f"{len(self.steps):02d}-{label}"
        (self.folder/(name+".txt")).write_text(obs["text"],encoding="utf-8")
        save(self.folder/(name+".json"),obs)
        self.page.screenshot(path=str(self.folder/(name+".png")),full_page=not self.page.get_by_role("listbox").is_visible(),
                             mask=[self.page.locator('input[type="password"]')],timeout=30000)
        return obs,{"observation":name+".json","screenshot":name+".png","visible_text":name+".txt"}

    def wait_new_turn(self,previous,text):
        end=time.monotonic()+85
        while time.monotonic()<end:
            obs=self.observe()
            if (flow(obs["url"]) and flow(obs["url"])!=previous and not obs["pending"] and
                (obs["phase"] or obs["reply"]) and text[:min(25,len(text))] in obs["text"]):
                return
            if obs["disconnected"]:return
            self.page.wait_for_timeout(400)
        raise TimeoutError("提交后未呈现属于本轮的结束状态")

    def record_click(self, locator, label, notes):
        locator.click()
        self.page.wait_for_timeout(500)
        _,ref=self.capture("control-"+str(len(notes)+1))
        notes.append({"action":"click","visible_control":label,"at":stamp(),**ref})

    def conditional(self,action,info,notes):
        if action["action"]=="select_report":
            selector=self.page.get_by_role("combobox",name="结果展示与追问所依据的运行",exact=True)
            if not selector.is_visible():
                exp=self.page.locator("summary").filter(has_text="选择报告（按指标与观察期）")
                if exp.count()==1:self.record_click(exp,"选择报告（按指标与观察期）",notes)
            if not selector.is_visible():return "当前界面没有可用的历史报告选择器"
            self.record_click(selector,"结果展示与追问所依据的运行",notes)
            options=self.page.get_by_role("option")
            if not options.first.is_visible():
                selector.press("ArrowDown")
                options.first.wait_for(state="visible",timeout=4000)
            labels=options.all_inner_texts()
            matches=[i for i,v in enumerate(labels) if all(t in v for t in action["terms"])]
            if len(matches)!=1:
                self.page.keyboard.press("Escape")
                return "可见选项没有唯一匹配报告"
            self.record_click(options.nth(matches[0]),labels[matches[0]],notes)
            return "选中匹配的历史报告"
        obs=self.observe()
        if obs["phase"]!="待人工审核":return "本轮没有待审核计划"
        plan=obs.get("plan_text","")
        case=info["case_id"]
        if case=="B05":
            authorized=bool(re.search(r"(?:结果[：:]\s*visitors|目标指标[：:]?\s*(?:每日)?访客|指标为(?:每日)?访客)",plan,re.I))
        elif case=="B06":
            dates=re.findall(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)",plan)
            times=sorted({datetime.fromisoformat(t).date() for t in dates})
            authorized=(len(times)==2 and (times[-1]-times[0]).days==6 and
                        bool(re.search("过滤|筛选|仅纳入|仅保留|限制到",plan)))
        else:authorized=False
        if not authorized:return "计划未展示可核对的新指标或实际七日筛选范围，未批准"
        radio=self.page.get_by_text("人工审核",exact=True)
        if radio.count()!=1:return "无法唯一定位人工审核视图"
        self.record_click(radio,"人工审核",notes)
        label="我已核对上述计划和本步骤必要事实，同意按当前数据与计划版本进行本地计算。"
        check=self.page.get_by_text(label,exact=True)
        if not check.is_visible():return "审核页未提供当前计划确认控件"
        self.record_click(check,label,notes)
        button=self.page.get_by_role("button",name="接受计划并批准本次执行",exact=True)
        if not button.is_enabled():return "核对后按钮仍不可用，保留现有计划"
        self.record_click(button,"接受计划并批准本次执行",notes)
        deadline=time.monotonic()+80
        while time.monotonic()<deadline:
            state=self.observe()
            if not state["pending"] and state["phase"] and state["phase"]!="待人工审核":return state["phase"]
            self.page.wait_for_timeout(500)
        return "点击后未在等待上限内显示结束态"

    def perform(self,action,obs,attachments):
        kind=action["action"]
        if kind in ("done","abandon"):return
        if kind=="wait":
            self.page.wait_for_timeout(1500);return
        control=next((c for c in obs["controls"] if c["ref"]==action.get("ref")),None)
        if not control or control["disabled"]:raise ValueError("操作不在当前可见可用控件中")
        node=self.page.get_by_role(control["role"],name=control["name"],exact=True)
        if node.count()!=1:
            # Use the same visible name for controls lacking a standard accessibility role.
            node=self.page.get_by_text(control["name"],exact=True)
            if node.count()!=1:raise ValueError("页面已重绘，无法唯一定位原控件")
        if not node.is_visible():raise ValueError("目标控件已不可见")
        value=action.get("value","")
        if kind=="fill":
            node.fill(value)
            if CHAT in control["name"]:
                self.last_question=value
                self.last_flow=flow(self.page.url)
                node.press("Enter");self.wait_new_turn(self.last_flow,value)
        elif kind=="click":
            if control["role"] in ("checkbox","radio") and node.locator("xpath=ancestor::label[1]").count():
                node.locator("xpath=ancestor::label[1]").click()
            else:node.click()
            if control["role"]=="combobox" and not self.page.get_by_role("option").first.is_visible():
                node.press("ArrowDown")
        elif kind=="select":
            if not self.page.get_by_role("option",name=value,exact=True).is_visible():node.click()
            option=self.page.get_by_role("option",name=value,exact=True)
            if option.count()!=1:raise ValueError("打开菜单后没有唯一匹配项")
            option.click()
        elif kind=="upload":
            if value not in attachments:raise ValueError("题面没有指定该附件")
            node.set_input_files(attachments[value])
        else:raise ValueError("未知浏览器操作")
        self.page.wait_for_timeout(450)

def fixed_action(step,obs):
    if isinstance(step,str):step={"action":"fill","name":CHAT,"value":step}
    kind=step["action"]
    if kind in ("done","abandon","wait","select_report","review_if_matching"):return dict(step)
    options=[c for c in obs["controls"] if c["name"]==step["name"] and not c["disabled"]]
    if len(options)!=1:raise ValueError("固定操作未找到唯一可见控件："+step["name"])
    return {**step,"ref":options[0]["ref"]}

def run(launch_path,mode,observe_only=False):
    info=json.loads(launch_path.read_text("utf-8-sig"))
    out=launch_path.parent/"browser"
    out.mkdir(exist_ok=False)
    summary={"case_id":info["case_id"],"session_id":info["session_id"],"attempt":info.get("attempt"),
             "strategy":mode,"started":stamp(),"turns":[],"events":[],"external_interventions":[],"status":"started"}
    secret=os.environ.pop("DEEPSEEK_API_KEY",None) if info.get("product_mode")=="deepseek" else None
    summary.update(product_mode=info.get("product_mode","local_engineering"),product_commit=info.get("product_commit"),model_authorized=False)
    def flush():
        save(launch_path.parent/"interaction.json",summary)
    flush()
    try:
        with server(Path(info["workspace"]),out/"server.log") as base, playwright_runtime() as runtime:
            launch_opts={"headless":True,"args":["--disable-breakpad","--disable-crash-reporter"]}
            if os.environ.get("CAUSALOPS_BROWSER_EXECUTABLE"):launch_opts["executable_path"]=os.environ["CAUSALOPS_BROWSER_EXECUTABLE"]
            browser=runtime.chromium.launch(**launch_opts)
            context=browser.new_context(viewport={"width":1440,"height":1000},locale="zh-CN",accept_downloads=False)
            page=context.new_page()
            page.set_default_timeout(15000)
            driver=BrowserRun(page,out)
            if info.get("product_mode")=="deepseek":
                if not secret:raise ValueError("缺少官方模型会话凭据")
                def mark(stage):
                    summary["setup_stage"]=stage
                    if observe_only and stage=="grant_task":
                        summary["engineering_preflight_labels"]=[t[:180] for t in page.locator("body").inner_text().splitlines()
                            if any(w in t for w in ("授权","允许本任务","运行模式","模型连接与数据发送许可","当前任务 · 数据与权限","deepseek-flash"))]
                        summary["engineering_permission_count"]=page.get_by_text("允许本任务向以上模型发送字段摘要、研究问题及运行汇总",exact=True).count()
                    flush()
                authorize(page,base,info["session_id"],secret,mark)
                summary["model_authorized"]=True
            else:
                page.goto(base+"/?"+urlencode({"route":"assistant","assistant":info["session_id"]}))
            page.get_by_role("textbox",name=CHAT,exact=True).wait_for(timeout=65000)
            obs,ref=driver.capture("initial")
            summary.update(initial=ref,events=driver.events,browser_engine="chromium",browser_version=browser.version,
                           workbench_model="deepseek-flash" if summary["model_authorized"] else "local",version_label=page.locator(".co-pill").first.inner_text(),
                           build_label=page.locator(".co-pill").first.get_attribute("title"))
            flush()
            if observe_only:
                summary["status"]="observed";return
            if mode=="adaptive":
                sys.path.insert(0,str(REPO))
                from scripts.eval_v20.actor.policy import decide,load_tasks
                task=load_tasks()[info["case_id"]]
            else:
                sequence=info.get("fixed_turns") or [info["question"]]
            history=[]
            for i in range(25):
                if mode=="fixed" and i>=len(sequence):
                    summary["status"]="fixed_finished";break
                op=(decide(task,obs,history) if mode=="adaptive" else fixed_action(sequence[i],obs))
                item={"number":i+1,"at":stamp(),"action":op.copy(),"url_before":page.url}
                if op.get("ref"):item["control"]=next((c for c in obs["controls"] if c["ref"]==op["ref"]),None)
                ok=True
                try:
                    if mode=="fixed" and op["action"] in ("select_report","review_if_matching"):
                        item["ui_actions"]=[]
                        item["outcome"]=driver.conditional(op,info,item["ui_actions"])
                    else:
                        driver.perform(op,obs,info.get("attachments",{}))
                except Exception as exc:
                    ok=False
                    item["error"]=type(exc).__name__+": "+str(exc).splitlines()[0][:250]
                driver.steps.append(item)
                obs,ref=driver.capture("after")
                item.update(result="ok" if ok else "failed",evidence=ref,url_after=page.url,reply=obs["reply"],
                            phase=obs["phase"],pending=obs["pending"],ended=stamp())
                if item.get("control",{}).get("name")==CHAT:
                    item["user_question"]=op.get("value","")
                history.append({**op,"result":item["result"]})
                summary["turns"]=driver.steps
                summary["final_answer"]=obs["reply"]
                summary["events"]=driver.events
                flush()
                if op["action"] in ("done","abandon"):
                    summary["status"]=op["action"];break
                if not ok and mode=="fixed":
                    summary["status"]="fixed_action_failed";break
            else:summary["status"]="step_limit"
            context.close();browser.close()
    except Exception as exc:
        summary["status"]="browser_error"
        summary["error"]=type(exc).__name__+": "+str(exc).splitlines()[0][:300]
    finally:
        summary["ended"]=stamp();flush()
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("launch",type=Path);p.add_argument("--strategy",choices=["fixed","adaptive"],required=True)
    p.add_argument("--observe-only",action="store_true")
    args=p.parse_args();r=run(args.launch,args.strategy,args.observe_only)
    print(r["status"] if r else "observed",flush=True)
