import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { SetupView, Study } from "../api";
import { DataContractEditor } from "./DataContractEditor";
import { CandidatePlanView } from "./CandidatePlanView";
import { ConversationView } from "./ConversationView";
import { ChatComposer } from "./ChatComposer";
import { createRef } from "react";
const noop = () => {},
  asyncNoop = async () => {};
const setup: SetupView = {
  schema_version: "research-setup-view-v1",
  chat_id: "a".repeat(32),
  binding_id: "b".repeat(32),
  session_id: "c".repeat(32),
  data: {
    upload_id: "d".repeat(32),
    frame_sha: "f".repeat(64),
    parquet_sha: "e".repeat(64),
  },
  contract: null,
  editable: true,
  phase: "data_registered",
  rows: 24,
  fields: [
    {
      name: "arm",
      dtype: "object",
      missing: 0,
      distinct: 2,
      values: [
        { value: "a", count: 12 },
        { value: "b", count: 12 },
      ],
    },
  ],
  sample: [],
  configuration: null,
  candidate: null,
  adoption: null,
  scope_notice: "unit test fixture",
};
describe("configuration and presentation safety", () => {
  const proposal: SetupView = {
    ...setup,
    phase: "candidate",
    candidate: {
      id: "1".repeat(32),
      configuration_ref: "2".repeat(32),
      task_id: "3".repeat(32),
      plan_sha: "f".repeat(64),
      source_current: false,
      source_error: "原合同版本已经变化",
      candidate: {
        id: "4".repeat(32),
        status: "validated",
        source: "deterministic",
        execution_authorized: false,
        candidate: {
          objective: "单元测试：比较两组的二元指标",
          research_type: "descriptive_binary",
          declared_assignment: "unknown",
          steps: [],
          applicability: [],
          cannot_execute_reasons: [],
          human_confirmations: [],
          rationale: "test only",
          field_bindings: {},
        },
      },
    },
  };
  it("a stale candidate remains visible as history and cannot be adopted", () => {
    const html = renderToStaticMarkup(
      <CandidatePlanView
        setup={proposal}
        study={null}
        busy={false}
        error=""
        onBack={noop}
        onConfigure={noop}
        onGenerate={noop}
        onAdopt={asyncNoop}
      />,
    );
    expect(html).toContain("原合同版本已经变化");
    expect(html).toContain("当前不能采纳");
    expect(html).toMatch(/disabled=""[^>]*>采纳为待审方案/);
  });
  it("an adopted task later executed in Streamlit displays the actual saved status", () => {
    const study = {
      status: "completed",
      run_ids: ["run-a", "run-b"],
      links: { review: "http://127.0.0.1:8788" },
    } as unknown as Study;
    const html = renderToStaticMarkup(
      <CandidatePlanView
        setup={{ ...proposal, phase: "adopted" }}
        study={study}
        busy={false}
        error=""
        onBack={noop}
        onConfigure={noop}
        onGenerate={noop}
        onAdopt={asyncNoop}
      />,
    );
    expect(html).toContain("2 个真实 Run");
    expect(html).not.toContain("尚未产生 Approval");
    expect(html).not.toContain("采纳为待审方案");
  });
  it("starts unknown, unchecked and unable to submit a formal contract", () => {
    const html = renderToStaticMarkup(
      <DataContractEditor
        setup={setup}
        busy={false}
        error=""
        onBack={noop}
        onConfirm={asyncNoop}
        onCandidate={noop}
      />,
    );
    expect(html).toContain('value="unknown" selected=""');
    expect(html).not.toContain('checked=""');
    expect(html).toMatch(/disabled=""[^>]*>确认并保存数据合同/);
    expect(html).not.toContain("批准并执行");
  });
  it("a candidate without a verified contract cannot be adopted", () => {
    const html = renderToStaticMarkup(
      <CandidatePlanView
        setup={setup}
        study={null}
        busy={false}
        error=""
        onBack={noop}
        onConfigure={noop}
        onGenerate={noop}
        onAdopt={asyncNoop}
      />,
    );
    expect(html).not.toContain(">采纳为待审方案<");
    expect(html).toContain("请先确认当前数据合同");
  });
  it("a source error replaces the message reading area, never keeps an old success", () => {
    const html = renderToStaticMarkup(
      <ConversationView
        chat={null}
        chatId={setup.chat_id}
        loading={false}
        error="报告哈希不一致"
        reader={createRef()}
        onScroll={noop}
        onDraft={noop}
        onConfigure={noop}
        onCandidate={noop}
        setup={null}
      />,
    );
    expect(html).toContain("报告哈希不一致");
    expect(html).not.toContain("user-bubble");
    expect(html).not.toContain("result-lead");
  });
  it("an attached file is visibly unsubmitted and does not imply contract confirmation", () => {
    const html = renderToStaticMarkup(
      <ChatComposer
        draft=""
        onDraft={noop}
        file={new File(["arm,binary"], "input.csv")}
        onFileRemove={noop}
        onPick={noop}
        textarea={createRef()}
        fileInput={createRef()}
        onSend={noop}
        busy={false}
        disabled={false}
        feedback=""
        metric=""
        onBind={noop}
        hasChat={true}
        onConfigure={noop}
        hasData={false}
      />,
    );
    expect(html).toContain("尚未提交");
    expect(html).toContain('aria-label="添加数据附件"');
    expect(html).not.toContain(">研究配置<");
  });
});
