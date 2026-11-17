export type Session = {
  id: string;
  title: string;
  label: string;
  updated: string;
  active_binding_id: string | null;
  demo_hidden: boolean;
};
export type Binding = {
  id: string;
  version: number;
  subject_id: string;
  metadata: Record<string, unknown>;
};
export type Answer = {
  text: string;
  source: string;
  scope?: string;
  run_ids: string[];
  facts?: { id: string; text: string; value: unknown }[];
};
export type Message = {
  id: string;
  ordinal: number;
  question: string;
  status: string;
  created: string;
  binding_id: string | null;
  subject_id: string | null;
  source_ref: Record<string, unknown> | null;
  available: boolean;
  error: string | null;
  answer: Answer | null;
};
export type Scope = {
  metric?: string;
  metric_label?: string;
  outcome?: string;
  window?: string;
  metric_window?: string;
  analysis_unit?: string;
  assignment?: string;
  groups?: Record<string, string>;
};
export type Study = {
  id: string;
  domain: string;
  title: string;
  status: string;
  scope: Scope;
  data: Record<string, unknown>;
  contract: Record<string, unknown> | null;
  plan_refs: { id: string; version: number; sha: string }[];
  plan: Record<string, unknown> | null;
  approval: { id: string; version: number; read_only: boolean } | null;
  run_ids: string[];
  report_sha: string | null;
  report_available: boolean;
  execution_warning: string | null;
  steps: {
    step_id: string;
    name: string;
    status: string;
    run_id: string | null;
    output_sha: string | null;
  }[];
  links: Record<string, string>;
};
export type Chat = {
  session: Session;
  binding: Binding | null;
  messages: Message[];
  study: Study | null;
};
export type Report = {
  chat_id: string;
  task_id: string;
  report_sha: string;
  manifest: Record<string, unknown> & {
    source_runs: string[];
    sample_size: number;
  };
  scope: Scope;
  display: {
    groups: { label: string; n: number; rate: string }[];
    difference: string;
    unit: string;
    interval: string[] | null;
    difference_kind: string;
    text: string | null;
    method: string;
  };
  risks: { rule: string; level: string; detail: string }[];
  steps: Study["steps"];
};
export type StudyOption = {
  id: string;
  domain: string;
  title: string;
  metric: string | null;
  available: boolean;
};
export type Finding = {
  rule: { id: string; version: string };
  status: string;
  severity: unknown;
  result: unknown;
};
export type Artifacts = {
  diagnostic: null | {
    report_id: string;
    version: number;
    quality: { findings: Finding[]; unimplemented_rules: string[] };
    suggestions: { action: string; reason: string }[];
  };
  decisions: {
    decision: null | Record<string, unknown>;
    origin_verified: boolean;
    error: string | null;
    superseded_by: string | null;
  }[];
};
export type Bootstrap = {
  csrf_token: string;
  mode: string;
  model_enabled: boolean;
  streamlit_url: string;
};
export type BinaryConfig = {
  objective: string;
  analysis_unit: string;
  entity: string | null;
  record_grain: string;
  independent_records_confirmed: boolean;
  treatment: string;
  control_value: string;
  treated_value: string;
  control_label: string;
  treated_label: string;
  outcome: string;
  negative_value: string;
  positive_value: string;
  metric: string;
  unit: "概率" | "比例" | "百分比";
  window: string;
  assignment: "unknown" | "randomized";
  source_url: string;
  design_evidence: string;
  source_confirmed: boolean;
};
export type SetupData = {
  upload_id: string;
  frame_sha: string;
  parquet_sha: string;
};
export type ContractSnapshot = {
  id: string;
  version: number;
  sha: string;
  data_sha: string;
  body: Record<string, unknown>;
};
export type ConfigurationReceipt = {
  id: string;
  session_id: string;
  data: SetupData;
  contract_ref: { id: string; version: number; sha: string };
  configuration: BinaryConfig;
  output_binding_id: string;
};
export type CandidateStep = {
  step_id: string;
  method: string;
  depends_on: string[];
  input_evidence: string[];
  output_evidence: string;
};
export type SetupCandidate = {
  id: string;
  configuration_ref: string;
  task_id: string;
  plan_sha: string;
  source_current: boolean;
  source_state?: 'current' | 'adopted' | 'stale';
  source_error: string | null;
  candidate: {
    id: string;
    status: string;
    source: string;
    execution_authorized: false;
    candidate: {
      objective: string;
      research_type: "descriptive_binary" | "randomized_two_arm_binary";
      declared_assignment: string;
      steps: CandidateStep[];
      applicability: string[];
      cannot_execute_reasons: string[];
      human_confirmations: string[];
      rationale: string;
      field_bindings: Record<string, unknown>;
    };
  };
};
export type SetupView = {
  schema_version: string;
  chat_id: string;
  binding_id: string;
  session_id: string;
  data: SetupData;
  contract: ContractSnapshot | null;
  editable: boolean;
  phase:
    | "adopted"
    | "candidate"
    | "confirmed"
    | "data_registered"
    | "existing_research";
  rows: number;
  fields: {
    name: string;
    dtype: string;
    missing: number;
    distinct: number;
    values: { value: string; count: number }[];
  }[];
  sample: Record<string, unknown>[];
  configuration: ConfigurationReceipt | null;
  candidate: SetupCandidate | null;
  adoption: { task_id: string; status: string } | null;
  scope_notice: string;
};
let csrf = "";
export type ResearchView = {
  schema_version: string;
  binding_id: string;
  review_sha: string;
  task: {
    source: Record<string, unknown>;
    id: string;
    session_id: string;
    status: string;
    reason: string | null;
    plan_sha: string;
    plan: {
      plan_id: string;
      version: number;
      objective: string;
      data: Record<string, unknown>;
      contract_ref: Record<string, unknown>;
      scope: Scope & {
        groups: Record<string, string>;
        unit: string;
        assignment: string;
        assignment_source?: string;
        inclusion?: string;
        missing_policy?: string;
      };
      steps: {
        step_id: string;
        kind: string;
        depends_on: string[];
        config: Record<string, unknown>;
      }[];
    };
  };
  steps: (Study["steps"][number] & { tool_attempts: number })[];
  evidence: Record<string, unknown>;
  report: Record<string, unknown> | null;
  risks: { rule: string; level: string; detail: string }[];
  binding_error: string | null;
  errors: string[];
  active: boolean;
  approval: Record<string, unknown> | null;
  permissions: Record<
    "approve" | "start" | "pause" | "cancel" | "resume",
    boolean
  >;
  review_requirement: string | null;
  jobs: {
    id: string;
    status: string;
    operation: string;
    error_note: string | null;
  }[];
  events: {
    seq: number;
    step_id: string | null;
    event: string;
    body: unknown;
    created: string;
  }[];
  budget: {
    physical_requests: number;
    semantic_revisions: number;
    input_tokens: number;
    output_tokens: number;
    usage_unknown: number;
    estimated_cost_cny: number;
    cost_is_estimate: boolean;
    price_version: unknown;
    tool_attempts: unknown;
    policy: Record<string, unknown>;
    stops: unknown[];
    events: unknown[];
  };
};
export type ResearchAction =
  "approve" | "start" | "pause" | "cancel" | "resume";
let bootstrapFlight: Promise<Bootstrap> | null = null;
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  init: RequestInit = {},
  readAttempt = 0,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== "GET") {
    headers.set("X-CausalOps-CSRF", csrf);
    if (!headers.has("Content-Type"))
      headers.set("Content-Type", "application/json");
  }
  const r = await fetch("/api" + path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  const data = await r.json().catch(() => ({
    error: {
      code: "invalid_response",
      message: "服务未返回合法响应；请刷新核对，未自动重发。",
    },
  }));
  if (
    r.status === 503 &&
    data.error?.code === "research_updating" &&
    (init.method || "GET") === "GET" &&
    readAttempt < 3
  ) {
    await new Promise((resolve) => setTimeout(resolve, 200));
    if (init.signal?.aborted)
      throw new DOMException("Read aborted", "AbortError");
    return request<T>(path, init, readAttempt + 1);
  }
  if (!r.ok)
    throw new ApiError(
      r.status,
      data.error?.code || "request_failed",
      (data.error?.message || "请求未完成；未显示替代研究。") +
        (data.error?.fields?.length
          ? " " +
            data.error.fields
              .map((x: { field: string; message: string }) => {
                const names: Record<string, string> = {
                  objective: "研究目标",
                  record_grain: "记录粒度",
                  design_evidence: "设计依据",
                  analysis_unit: "分析单位",
                  window: "观察窗口",
                  source_url: "公开来源网址",
                  metric: "指标名称",
                };
                const field = x.field.split(".").at(-1) || x.field;
                return (names[field] || field) + "：" + x.message;
              })
              .join("；")
          : ""),
    );
  return data as T;
}
export function bootstrap() {
  return (bootstrapFlight ??= request<Bootstrap>("/bootstrap").then((d) => {
    csrf = d.csrf_token;
    return d;
  }));
}
export const key = () => crypto.randomUUID();
