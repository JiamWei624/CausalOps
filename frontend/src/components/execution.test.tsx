import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ResearchView, Report } from "../api";
import { ResearchFlow, ResearchCompletion } from "./ResearchFlow";
const value = {
  binding_id: "a".repeat(32),
  task: {
    id: "b".repeat(32),
    status: "candidate",
    plan_sha: "c".repeat(64),
    plan: {
      objective: "单元测试研究范围",
      version: 2,
      data: { frame_sha: "d".repeat(64) },
      contract_ref: { version: 1 },
      scope: {
        metric: "完成率",
        unit: "概率",
        groups: { a: "甲", b: "乙" },
        assignment: "unknown",
      },
      steps: [],
    },
  },
  permissions: {
    approve: true,
    start: false,
    pause: false,
    cancel: true,
    resume: false,
  },
  steps: [],
  risks: [],
  jobs: [],
  budget: {
    physical_requests: 0,
    semantic_revisions: 0,
    input_tokens: 0,
    output_tokens: 0,
    usage_unknown: 0,
  },
} as unknown as ResearchView;
const props = {
  busy: false,
  error: "",
  notice: "",
  onAction: async () => {},
  onRefresh: () => {},
  onBack: () => {},
  onReport: () => {},
};
describe("formal operation separation", () => {
  it('shows a source failure in the focused workspace without old statistics or approval controls',()=>{const html=renderToStaticMarkup(<ResearchFlow {...props} value={null} error="数据合同版本已变化"/>);expect(html).toContain('role="alert"');expect(html).toContain('数据合同版本已变化');expect(html).not.toContain('保存正式批准');expect(html).not.toContain('正在核对当前研究');});
  it("approval and cancellation are not confirmed by default, and start is absent before approval", () => {
    const html = renderToStaticMarkup(
      <ResearchFlow {...props} value={value} />,
    );
    expect(html).not.toContain('checked=""');
    expect(html).toMatch(/disabled=""[^>]*>保存正式批准/);
    expect(html).not.toContain(">开始已批准研究<");
  });
  it("cancelled tasks offer neither start nor resume", () => {
    const html = renderToStaticMarkup(
      <ResearchFlow
        {...props}
        value={{
          ...value,
          task: { ...value.task, status: "cancelled" },
          permissions: {
            approve: false,
            start: false,
            pause: false,
            resume: false,
            cancel: false,
          },
        }}
      />,
    );
    expect(html).toContain("取消为终态");
    expect(html).not.toContain(">核查恢复并继续<");
    expect(html).not.toContain(">开始已批准研究<");
  });
  it("approved status displays a separate explicit start operation", () => {
    const html = renderToStaticMarkup(
      <ResearchFlow
        {...props}
        value={{
          ...value,
          task: { ...value.task, status: "approved" },
          permissions: { ...value.permissions, approve: false, start: true },
        }}
      />,
    );
    expect(html).toContain(">开始已批准研究<");
    expect(html).not.toContain(">保存正式批准<");
  });
  it("a descriptive report never fabricates a confidence interval", () => {
    const r = {
      task_id: "x",
      report_sha: "sha",
      scope: { metric: "完成比例" },
      manifest: { source_runs: ["desc"] },
      risks: [],
      display: {
        difference: "16.6667",
        difference_kind: "描述性比例差",
        unit: "个百分点",
        interval: null,
        method: "descriptive",
        groups: [{ label: "甲", n: 12, rate: "50.00%" }],
      },
    } as unknown as Report;
    const html = renderToStaticMarkup(
      <ResearchCompletion report={r} onReport={() => {}} />,
    );
    expect(html).toContain("没有执行 A/B 或推断区间");
    expect(html).toContain("16.6667");
    expect(html).not.toContain("95%区间");
  });
});
