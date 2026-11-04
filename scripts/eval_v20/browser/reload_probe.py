"""Isolated after-session restore probe. No credentials or service calls."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import parse_qs,urlparse

from drive import CHAT, BrowserRun, playwright_runtime, save, server, stamp

def main():
    source=Path(sys.argv[1]).resolve()
    folder=Path(sys.argv[2]).resolve()
    folder.mkdir(exist_ok=False)
    workspace=folder/"workspace"
    shutil.copytree(source/"workspace",workspace)
    events=[]
    result={"scope":"supplemental_unscored","source":str(source),"events":events,"started":stamp(),"status":"started"}
    def step(action):
        events.append({"at":stamp(),"visible_action":action})
    try:
        with server(workspace,folder/"server.log") as base,playwright_runtime() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=os.environ.get("CAUSALOPS_BROWSER_EXECUTABLE"))
            context=browser.new_context(viewport={"width":1440,"height":1000},locale="zh-CN")
            page=context.new_page();page.set_default_timeout(25000)
            page.goto(base+"/")
            step("打开首页，无任务、流程或报告参数")
            page.get_by_role("button",name="研究记录",exact=True).first.click(timeout=60000)
            picker=page.get_by_role("combobox",name="选择任务",exact=True)
            picker.click()
            page.get_by_role("option").first.wait_for()
            options=page.get_by_role("option").all_inner_texts()
            result["visible_task_options"]=options
            named=[t for t in options if "订单研究历史报告" in t]
            if len(named)!=1:raise RuntimeError("任务列表没有唯一匹配的显示名称")
            page.get_by_role("option",name=named[0],exact=True).click()
            step("点击研究记录并按显示名称选择 "+named[0])
            page.get_by_role("button",name="继续研究",exact=True).click()
            step("点击继续研究")
            def snapshot(label):
                page.get_by_role("textbox",name=CHAT,exact=True).wait_for(timeout=60000)
                page.get_by_text("报告依据：计划",exact=False).first.wait_for()
                exp=page.locator("summary").filter(has_text="研究报告预览").first
                if exp.locator("..").get_attribute("open") is None:exp.click()
                note=page.locator(".co-paper .co-note").first
                note.wait_for(state="visible")
                rid=re.search(r"[a-f0-9]{32}",note.inner_text()).group()
                driver=BrowserRun(page,folder)
                obs=driver.observe()
                data={"url":page.url,"displayed_flow":parse_qs(urlparse(page.url).query).get("flow",[""])[0],
                      "plan_version":re.search(r"报告依据：计划\s*V(\d+)",obs["text"]).group(1),
                      "selected_report":page.get_by_role("combobox",name="结果展示与追问所依据的运行",exact=True).input_value(),
                      "run_id":rid,"report_body":page.locator(".co-paper").first.inner_text(),"reply":obs["reply"]}
                data["report_body_sha256"]=hashlib.sha256(data["report_body"].encode()).hexdigest()
                data["reply_sha256"]=hashlib.sha256(data["reply"].encode()).hexdigest()
                save(folder/(label+".json"),data)
                page.screenshot(path=str(folder/(label+".png")),full_page=True)
                return data
            before=snapshot("before")
            if not before["reply"] or not before["displayed_flow"]:raise RuntimeError("缺少可比较的当前对话")
            result["before"]={k:v for k,v in before.items() if k not in ("reply","report_body")}
            step("展开研究报告预览，记录界面可见版本、完整运行编号和正文")
            page.reload(wait_until="domcontentloaded")
            step("浏览器真实重新加载")
            after=snapshot("after")
            result["after"]={k:v for k,v in after.items() if k not in ("reply","report_body")}
            result["comparisons"]={k:before[k]==after[k] for k in ("displayed_flow","plan_version","selected_report","run_id","report_body","reply")}
            result["status"]="restored" if all(result["comparisons"].values()) else "changed"
            step("重新展开研究报告预览，对照当前答复、报告全文、运行、版本和选择")
            browser.close()
    except Exception as exc:
        result.update(status="probe_failed",error=type(exc).__name__+": "+str(exc).splitlines()[0][:300])
    finally:
        result["ended"]=stamp()
        save(folder/"reload_result.json",result)
    print(result["status"],flush=True)

if __name__=="__main__":main()
