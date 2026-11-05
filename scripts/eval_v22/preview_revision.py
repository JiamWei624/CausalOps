"""Independent fixed browser check for changing a preview field into a reviewed metric."""
import argparse
import os
import re
from pathlib import Path
from fixed_remaining import Journey
from phase2_fixture import seed
from pilot import save, server, playwright_runtime


def exercise(out):
    out.mkdir(parents=True,exist_ok=False)
    workspace=out/"workspace"
    workspace.mkdir()
    init=seed("N06",workspace)
    save(out/"initial.json",init)
    old=init["target"]
    result=dict(actions=[],waits=[],turns=0,papers={})
    with server(workspace,out/"server.log") as base,playwright_runtime() as pw:
        browser=pw.chromium.launch(executable_path=os.environ["CAUSALOPS_BROWSER_EXECUTABLE"])
        page=browser.new_page(locale="zh-CN",viewport={"width":1440,"height":1000})
        journey=Journey(page,out,result)
        try:
            page.goto(base+"/?route=assistant&assistant="+old["sid"])
            journey.paper("original",required=old["run"])
            journey.expand("新分析与口径设置")
            selector=page.get_by_role("combobox",name="查看指标分布")
            selector.click()
            if not page.get_by_role("option").first.is_visible():
                selector.press("ArrowDown")
            page.get_by_role("option",name="visitors",exact=False).click()
            page.get_by_text(re.compile(r"当前预览字段：visitors.*正式研究指标：orders.*V1")).wait_for()
            journey.snap("different")
            journey.click(journey.btn("以 visitors 为研究指标，生成待审方案"),"生成候选")
            page.get_by_text("待审计划 V2",exact=True).wait_for(timeout=60000)
            page.get_by_text("本次计划指标：visitors",exact=True).wait_for()
            journey.snap("awaiting")
            box=page.get_by_text(re.compile("我已核对上述计划")).first
            if not box.is_visible():
                journey.click(journey.txt("人工审核"),"打开审核区")
            journey.click(box,"核对新方案")
            journey.click(journey.btn("接受计划并批准本次执行"),"批准访客方案")
            page.wait_for_function("() => /分析状态[：:]\\s*已完成/.test(document.body.innerText)",timeout=75000)
            current=journey.paper("changed",exclude=old["run"])
            page.reload()
            journey.paper("refreshed",required=current["run"])
            journey.expand("新分析与口径设置")
            page.get_by_text(re.compile(r"当前预览字段：.*正式研究指标：visitors.*V2")).wait_for()
            journey.snap("refreshed-target")
            result["passed"]=True
        except Exception as exc:
            result.update(passed=False,error=f"{type(exc).__name__}: {exc}"[:700])
            journey.snap("failed")
        finally:
            save(out/"result.json",result)
            browser.close()
    return int(not result["passed"])


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("out",type=Path)
    raise SystemExit(exercise(parser.parse_args().out))
