"""Local fixed UI probes. One new workspace and browser context per attempt."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.eval_v20.browser.drive import BrowserRun, playwright_runtime, save, server, stamp


def attempt(case, root, revision):
    out = root / case
    out.mkdir(parents=True, exist_ok=False)
    home = out / "workspace"
    home.mkdir()
    events = []
    start = None
    result = dict(case=case, mode="fixed", product=revision, status="infrastructure_error",
                  user_help=0, operator_interventions=0, chat_turns=0)
    reader = None

    def action(label, func, kind="click"):
        entry = dict(seq=len(events)+1, kind=kind, label=label, at=stamp(), dispatched=False)
        events.append(entry)
        save(out/"actions.json", events)
        before = time.perf_counter()
        try:
            func()
            entry["dispatched"] = True
        finally:
            entry["duration_s"] = round(time.perf_counter()-before, 3)
            save(out/"actions.json", events)

    try:
        with server(home, out/"server.log") as base, playwright_runtime() as pw:
            opts = {"headless":True}
            if os.getenv("CAUSALOPS_BROWSER_EXECUTABLE"):
                opts["executable_path"] = os.environ["CAUSALOPS_BROWSER_EXECUTABLE"]
            browser = pw.chromium.launch(**opts)
            try:
                page = browser.new_page(locale="zh-CN", viewport={"width":1440,"height":1000})
                page.set_default_timeout(25000)
                reader = BrowserRun(page, out)
                btn = lambda t: page.get_by_role("button", name=t, exact=True)
                vis = lambda t: page.get_by_text(t, exact=True).first
                page.goto(base+"/?route=home")
                btn("查看营销实验").wait_for()
                result["browser"] = browser.version
                if case == "N04":
                    btn("查看营销实验").click()
                    vis("已核对来源、随机分配、两组定义与两周访问指标").click()
                    btn("创建研究任务并生成待审方案").click()
                    vis("人工审核").click()
                    page.get_by_text(re.compile("我已核对上述计划")).first.wait_for()
                elif case == "N08":
                    btn("导入分析数据").click()
                    btn("创建任务并检查数据").wait_for()
                reader.capture("start")
                result.update(status="failed", started=stamp(), start_url=page.url)
                start = time.perf_counter()
                if case == "N02":
                    action("载入葡萄酒示例",btn("载入葡萄酒示例").click)
                    page.get_by_text(re.compile("1,599 行.*240 条")).first.wait_for()
                    btn("生成完整描述统计报告").wait_for()
                    assert "质量评分" in page.locator("body").inner_text()
                elif case == "N04":
                    action("核对计划",page.get_by_text(re.compile("我已核对上述计划")).first.click)
                    action("接受计划并批准本次执行",btn("接受计划并批准本次执行").click)
                    link = vis("导出本次分析报告")
                    link.wait_for(timeout=75000)
                    with page.expect_download() as ticket:
                        action("导出本次分析报告",link.click)
                    ticket.value.save_as(out/"export.html")
                    html=(out/"export.html").read_text(encoding="utf-8")
                    screen=page.locator("body").inner_text()
                    for term in ["10.62","18.28","7.66","两周"]:
                        assert term in html and term in screen, term
                    assert "个百分点" in html
                else:
                    upl=page.locator('input[type="file"]')
                    def upload(name, content):
                        upl.set_input_files({"name":name,"mimeType":"text/csv","buffer":content.encode()})
                    action("导入重复表头文件",lambda:upload("bad.csv","day,day\n1,4\n2,3\n"),"upload")
                    page.get_by_text(re.compile("列名为空或重复")).first.wait_for()
                    assert btn("创建任务并检查数据").is_disabled()
                    result["fault_at_s"]=round(time.perf_counter()-start,3)
                    (out/"rejection.txt").write_text(page.locator("body").inner_text(),encoding="utf8")
                    action("换为修正文件",lambda:upload("corrected.csv","day,orders\n1,4\n2,3\n"),"upload")
                    action("创建修正后的任务",btn("创建任务并检查数据").click)
                    page.wait_for_url(re.compile(r".*[?&]assistant=[a-f0-9]+.*"))
                    sid=parse_qs(urlparse(page.url).query)["assistant"][0]
                    page.get_by_text(re.compile(r"全表 2 行")).first.wait_for()
                    action("刷新页面",page.reload,"reload")
                    page.get_by_text(re.compile(r"全表 2 行")).first.wait_for()
                    assert parse_qs(urlparse(page.url).query)["assistant"]==[sid]
                result["status"]="completed"
            except Exception as exc:
                result["failure"]=f"{type(exc).__name__}: {exc}"[:1800]
            finally:
                if start is not None:
                    result["elapsed_s"]=round(time.perf_counter()-start,3)
                if reader:
                    result["end_url"]=page.url
                    try:
                        reader.capture("end")
                    except Exception as exc:
                        result["capture_error"]=str(exc)[:400]
                    save(out/"browser-events.json",reader.events)
                browser.close()
    except Exception as exc:
        result["failure"]=f"{type(exc).__name__}: {exc}"[:1800]
    result.update(actions_attempted=len(events), actions_dispatched=sum(x["dispatched"] for x in events))
    save(out/"result.json", result)
    return result


if __name__ == "__main__":
    p=argparse.ArgumentParser(description="三个公开或合成数据的固定浏览器任务")
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    rev=subprocess.check_output(["git","-C",str(REPO),"rev-parse","HEAD"],text=True).strip()
    results=[attempt(case,args.out,rev) for case in ("N02","N04","N08")]
    save(args.out/"summary.json",results)
    print(json.dumps(results,ensure_ascii=False,indent=2))
    sys.exit(int(any(row["status"]!="completed" for row in results)))
