import { createRef } from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { Message } from "../api";
import { ChatComposer } from "./ChatComposer";
import { MessageRenderer } from "./MessageRenderer";
const noop = () => {};
const composer = (hasData: boolean, metric: string) => renderToStaticMarkup(
  <ChatComposer draft="" onDraft={noop} file={null} onFileRemove={noop} onPick={noop}
    textarea={createRef()} fileInput={createRef()} onSend={noop} busy={false}
    disabled={false} feedback="" metric={metric} onBind={noop} hasChat={true}
    onConfigure={noop} hasData={hasData} />,
);
const message: Message = {
  id: "message", ordinal: 1, question: "查询当前结果", status: "completed", created: "2026-11-16",
  binding_id: "binding", subject_id: "study", available: true, error: null,
  source_ref: { subject_id: "study", run_ids: ["run-a", "run-b"], report_sha: "f".repeat(64) },
  answer: { text: "原工具结果保持不变。", source: "本地保存报告解释（未调用模型）", scope: "verified_automation_report", run_ids: ["run-a", "run-b"] },
};
const render = (m: Message) => renderToStaticMarkup(<MessageRenderer m={m} currentSubject="study" />);
const summary = (m: Message) => render(m).match(/<summary>(.*?)<\/summary>/s)?.[1] || "";
describe("user-facing research context and answer evidence copy", () => {
  it("shows the actual metric for a linked study, not a technical response mode", () => {
    const html = composer(true, "晋升推荐比例");
    expect(html).toContain("当前研究 · 晋升推荐比例");
    expect(html).not.toContain("本地确定性回复");
  });
  it("does not infer a linked study from a leftover label", () => {
    expect(composer(false, "过往指标")).toContain("尚未选择研究");
    expect(composer(false, "过往指标")).not.toContain("当前研究 ·");
  });
  it("labels a completed, verified saved report and keeps the technical details", () => {
    expect(summary(message)).toContain("依据：已保存研究结果");
    expect(summary(message)).not.toContain("本地确定性路径");
    expect(render(message)).toContain("本地保存报告解释（未调用模型）");
  });
  it("never labels an answer without an actual Run reference", () => {
    expect(summary({ ...message, answer: { ...message.answer!, run_ids: [] } })).not.toContain("已保存研究结果");
  });
  it("does not label an unavailable source even if a historical answer is supplied", () => {
    expect(summary({ ...message, available: false, error: "原来源无法核验" })).not.toContain("已保存研究结果");
  });
  it("does not label a no-Run response or a pending response", () => {
    expect(summary({ ...message, answer: { ...message.answer!, run_ids: [] } })).not.toContain("已保存研究结果");
    expect(summary({ ...message, status: "running" })).not.toContain("已保存研究结果");
  });
  it("requires the matching frozen task, Run list and report reference", () => {
    for (const ref of [null, { ...message.source_ref, subject_id: "other" }, { ...message.source_ref, run_ids: ["foreign-run"] }, { ...message.source_ref, report_sha: null }]) {
      expect(summary({ ...message, source_ref: ref })).not.toContain("已保存研究结果");
    }
  });
  it("does not treat a model source string or arbitrary scope as statistical evidence", () => {
    expect(summary({ ...message, answer: { ...message.answer!, source: "模型声称已核验", scope: undefined } })).not.toContain("已保存研究结果");
  });
  it("allows single-Run facts already verified by the same service but not capability-only replies", () => {
    const single = { ...message, source_ref: { ...message.source_ref, report_sha: null }, answer: { ...message.answer!, scope: "selected_run", run_ids: ["run-a"], facts: [{ id: "rate", text: "已保存比例", value: 0.5 }] } };
    expect(summary(single)).toContain("依据：已保存研究结果");
    expect(summary({ ...single, answer: { ...single.answer, facts: [] } })).not.toContain("已保存研究结果");
  });
});
