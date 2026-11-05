"""Two additional fixed probes. Success criteria frozen before running; no model or score pooling."""
import argparse
import os
import re
from pathlib import Path
from phase2_fixture import seed
from pilot import playwright_runtime, save, server


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    work=out/"workspace"
    work.mkdir()
    fixture=seed("N06",work)
    results=[]
    with server(work,out/"service.log") as base, playwright_runtime() as pw:
        browser=pw.chromium.launch(executable_path=os.environ["CAUSALOPS_BROWSER_EXECUTABLE"])
        for name in ("历史记录无对照组","编码错误后使用文件设置"):
            page=browser.new_page(locale="zh-CN")
            result={"case":name,"passed":False}
            try:
                if name.startswith("历史"):
                    page.goto(base+"/?route=history")
                    selector=page.get_by_role("combobox",name="选择已保存的运行")
                    selector.wait_for()
                    assert "未登记组间比较" in selector.input_value()
                    assert fixture["target"]["run"][:8] in selector.input_value()
                    panel=page.locator("[data-history-rid]")
                    assert panel.get_attribute("data-history-rid")==fixture["target"]["run"]
                else:
                    page.goto(base+"/?route=assistant")
                    page.locator('input[type=file]').set_input_files({
                        "name":"records.csv","mimeType":"text/csv","buffer":"日期,销售额\n一,7\n".encode("gb18030")})
                    page.get_by_text(re.compile("CSV编码不匹配")).first.wait_for()
                    assert page.get_by_role("button",name="创建任务并检查数据").is_disabled()
                    assert not page.get_by_text("选择文件后显示真实行数",exact=False).is_visible()
                    page.get_by_text("文件编码与分隔符设置",exact=True).click()
                    encoding=page.get_by_role("combobox",name="编码",exact=True)
                    # Select via the visible combobox keyboard interaction. Record
                    # the resulting value as well as the successful parse below.
                    encoding.focus()
                    encoding.press("ArrowDown")
                    encoding.press("End")
                    encoding.press("Enter")
                    result["selected_encoding"]=encoding.input_value()
                    assert result["selected_encoding"]=="gb18030",result["selected_encoding"]
                    page.get_by_text("数据行数",exact=True).wait_for()
                    assert page.get_by_role("button",name="创建任务并检查数据").is_enabled()
                result["passed"]=True
            except Exception as exc:
                result["error"]=str(exc)[:500]
            finally:
                page.screenshot(path=str(out/(name+".png")))
                (out/(name+".txt")).write_text(page.locator("body").inner_text(),encoding="utf8")
                page.close()
            results.append(result)
            save(out/"results.json",results)
        browser.close()
    print(results)
    return int(not all(r["passed"] for r in results))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("out",type=Path)
    raise SystemExit(run(parser.parse_args().out))
