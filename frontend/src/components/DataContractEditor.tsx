import { useState } from "react";
import type { BinaryConfig, SetupView } from "../api";
import { EvidenceDetails, Icon } from "./ui";
const initial: BinaryConfig = {
  objective: "",
  analysis_unit: "",
  entity: null,
  record_grain: "",
  independent_records_confirmed: false,
  treatment: "",
  control_value: "",
  treated_value: "",
  control_label: "",
  treated_label: "",
  outcome: "",
  negative_value: "",
  positive_value: "",
  metric: "",
  unit: "概率",
  window: "",
  assignment: "unknown",
  source_url: "",
  design_evidence: "",
  source_confirmed: false,
};
export function DataContractEditor({
  setup,
  busy,
  error,
  onBack,
  onConfirm,
  onCandidate,
}: {
  setup: SetupView;
  busy: boolean;
  error: string;
  onBack: () => void;
  onConfirm: (c: BinaryConfig) => Promise<void>;
  onCandidate: () => void;
}) {
  const [c, setC] = useState<BinaryConfig>({
      ...initial,
      ...setup.configuration?.configuration,
      independent_records_confirmed: false,
      source_confirmed: false,
    }),
    [confirmed, setConfirmed] = useState(false),
    [editing, setEditing] = useState(!setup.configuration);
  const change = <K extends keyof BinaryConfig>(k: K, v: BinaryConfig[K]) =>
    setC((x) => ({ ...x, [k]: v }));
  const group = setup.fields.find((f) => f.name === c.treatment),
    outcome = setup.fields.find((f) => f.name === c.outcome);
  const saved = setup.configuration?.configuration;
  const text = (
    label: string,
    k: keyof BinaryConfig,
    hint?: string,
    multiline = false,
  ) => (
    <label className="form-field">
      <span>{label}</span>
      {multiline ? (
        <textarea
          aria-label={label}
          value={String(c[k] ?? "")}
          onChange={(e) => change(k, e.target.value as never)}
          rows={2}
          required={["objective", "record_grain"].includes(k)}
          maxLength={k === "objective" ? 600 : 800}
        />
      ) : (
        <input
          aria-label={label}
          value={String(c[k] ?? "")}
          onChange={(e) => change(k, e.target.value as never)}
          required={[
            "analysis_unit",
            "control_label",
            "treated_label",
            "metric",
            "window",
          ].includes(k)}
          maxLength={k === "window" ? 220 : 200}
        />
      )}{" "}
      {hint && <small>{hint}</small>}
    </label>
  );
  const field = (label: string, k: "entity" | "treatment" | "outcome") => (
    <label className="form-field">
      <span>{label}</span>
      <select
        aria-label={label}
        value={c[k] ?? ""}
        required={k !== "entity"}
        onChange={(e) =>
          change(k, k === "entity" ? e.target.value || null : e.target.value)
        }
      >
        <option value="">
          {k === "entity" ? "不使用标识字段（须确认记录粒度）" : "请选择字段"}
        </option>
        {setup.fields.map((f) => (
          <option key={f.name} value={f.name}>
            {f.name} · {f.dtype}
          </option>
        ))}
      </select>
    </label>
  );
  const coding = (
    label: string,
    k: "control_value" | "treated_value" | "negative_value" | "positive_value",
    rows: { value: string; count: number }[] | undefined,
  ) => (
    <label className="form-field">
      <span>{label}</span>
      <select
        aria-label={label}
        value={c[k]}
        required
        onChange={(e) => change(k, e.target.value)}
      >
        <option value="">请选择编码</option>
        {rows?.map((x) => (
          <option key={x.value} value={x.value}>
            {x.value} · {x.count} 条记录
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <section className="setup-workspace" data-setup-chat={setup.chat_id}>
      <header className="focus-heading">
        <button className="quiet-button" onClick={onBack}>
          ← 返回对话
        </button>
        <span>研究配置</span>
        <small>数据登记 ≠ 合同确认 ≠ 研究批准</small>
      </header>
      <div className="setup-layout">
        <main className="setup-main">
          <p className="eyebrow">DATA & RESEARCH SCOPE</p>
          <h1>
            {saved && !editing ? "研究口径已保存" : "先把研究条件说清楚。"}
          </h1>
          <p className="lead-copy">
            {saved && !editing
              ? "合同已版本化保存。下一步查看受限候选，采纳后仍需正式审核。"
              : "为这份数据确认指标、比较对象和适用范围。这里不会执行统计。"}
          </p>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          {!setup.editable ? (
            <div className="research-note">
              <h3>当前正式研究保留原合同与历史</h3>
              <p>
                这里仅查看，不原地修改已采纳或已执行的研究。若需改变指标、数据或窗口，请在对话中登记新的数据任务。
              </p>
              <EvidenceDetails label="当前合同来源" value={setup.contract} />
            </div>
          ) : saved && !editing ? (
            <>
              <dl className="confirmed-scope">
                <dt>研究目标</dt>
                <dd>{saved.objective}</dd>
                <dt>结果指标</dt>
                <dd>
                  {saved.metric} · {saved.outcome}
                </dd>
                <dt>比较对象</dt>
                <dd>
                  {saved.treated_label} 对比 {saved.control_label}
                </dd>
                <dt>分析单位</dt>
                <dd>{saved.analysis_unit}</dd>
                <dt>观察窗口</dt>
                <dd>{saved.window}</dd>
                <dt>研究设计</dt>
                <dd>
                  {saved.assignment === "randomized"
                    ? "使用者已核对随机分配资料"
                    : "随机化依据未知 · 仅描述性路径"}
                </dd>
                <dt>合同版本</dt>
                <dd>v{setup.contract?.version}</dd>
              </dl>
              <div className="scope-actions">
                <button
                  className="primary"
                  onClick={onCandidate}
                  disabled={busy}
                >
                  {busy
                    ? "正在读取候选…"
                    : setup.candidate
                      ? "查看确定性候选"
                      : "生成确定性候选"}
                  <Icon name="chevron" size={16} />
                </button>
                <button
                  className="quiet-button"
                  onClick={() => {
                    setEditing(true);
                    setConfirmed(false);
                  }}
                  disabled={busy}
                >
                  修改并重新确认
                </button>
              </div>
              <p className="small muted">
                修改会保留旧合同版本，并使旧候选失去当前来源适用性。不会覆盖已有
                Run。
              </p>
              <EvidenceDetails label="合同内容与来源" value={setup.contract} />
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void onConfirm(c);
              }}
            >
              <section className="form-section">
                <div className="section-caption">
                  <span>01</span>
                  <h2>研究问题</h2>
                </div>
                {text(
                  "研究目标",
                  "objective",
                  "明确比较什么，以及希望回答的问题。",
                  true,
                )}
              </section>
              <section className="form-section">
                <div className="section-caption">
                  <span>02</span>
                  <h2>比较组与结果指标</h2>
                </div>
                <div className="form-grid">
                  {field("比较组字段", "treatment")}
                  {field("二元结果字段", "outcome")}
                </div>
                {group && (
                  <p
                    className={
                      "field-observation" +
                      (group.distinct !== 2 ? " warning" : "")
                    }
                  >
                    当前分组字段有 {group.distinct} 个非空编码、{group.missing}{" "}
                    条缺失记录。
                    {group.distinct !== 2
                      ? "本流程只接受恰好两组，不自动剔除其他组。"
                      : "编码的业务含义仍需由你确认。"}
                  </p>
                )}
                {outcome && (
                  <p className="field-observation">
                    结果字段有 {outcome.distinct} 个非空编码、{outcome.missing}{" "}
                    条缺失。不会自动把连续指标二分。
                  </p>
                )}
                <div className="form-grid">
                  {coding("对照组编码", "control_value", group?.values)}
                  {coding("比较组编码", "treated_value", group?.values)}
                  {text("对照组含义", "control_label")}
                  {text("比较组含义", "treated_label")}
                  {coding("否定事件编码", "negative_value", outcome?.values)}
                  {coding("肯定事件编码", "positive_value", outcome?.values)}
                  {text("指标名称", "metric")}
                  <label className="form-field">
                    <span>展示单位</span>
                    <select
                      aria-label="展示单位"
                      value={c.unit}
                      onChange={(e) =>
                        change("unit", e.target.value as BinaryConfig["unit"])
                      }
                    >
                      <option>概率</option>
                      <option>比例</option>
                      <option>百分比</option>
                    </select>
                    <small>比例差仍以百分点表示，不与相对增长率混用。</small>
                  </label>
                </div>
              </section>
              <section className="form-section">
                <div className="section-caption">
                  <span>03</span>
                  <h2>样本与观察口径</h2>
                </div>
                <div className="form-grid">
                  {text(
                    "分析单位",
                    "analysis_unit",
                    "例如：一名参与者，而不是一次重复抽检。",
                  )}
                  {field("唯一标识字段", "entity")}
                </div>
                {text(
                  "记录粒度与纳入范围",
                  "record_grain",
                  "说明一行代表什么，以及整表包含哪些记录。",
                  true,
                )}
                {text(
                  "观察窗口",
                  "window",
                  "不自动按日期筛选。窗口须对应本表实际范围；已有候选改变窗口时，须重新上传覆盖新窗口的数据。",
                )}
                <label className="confirmation">
                  <input
                    type="checkbox"
                    checked={c.independent_records_confirmed}
                    onChange={(e) =>
                      change("independent_records_confirmed", e.target.checked)
                    }
                  />
                  <span>
                    我确认每行是独立观察单位，不将同一实体的重复记录当作独立样本。
                  </span>
                </label>
              </section>
              <section className="form-section">
                <div className="section-caption">
                  <span>04</span>
                  <h2>研究设计依据</h2>
                </div>
                <label className="form-field">
                  <span>分配机制</span>
                  <select
                    aria-label="分配机制"
                    value={c.assignment}
                    onChange={(e) => {
                      change(
                        "assignment",
                        e.target.value as BinaryConfig["assignment"],
                      );
                      change("source_confirmed", false);
                    }}
                  >
                    <option value="unknown">随机化依据未知 · 描述性研究</option>
                    <option value="randomized">
                      有具体随机分配资料 · 待人工核对
                    </option>
                  </select>
                </label>
                <div className="research-note">
                  <p>
                    {c.assignment === "unknown"
                      ? "目前只能生成描述性路径。两个比较组并不证明随机分配，不会生成 A/B 效应或推断区间。"
                      : "只有明确的设计资料与使用者核对，才允许提出 A/B 候选。样本和方差等工具条件仍需在正式执行前检查。"}
                  </p>
                </div>
                <label className="form-field">
                  <span>公开来源网址</span>
                  <input
                    aria-label="公开来源网址"
                    type="url"
                    value={c.source_url}
                    required={c.assignment === "randomized"}
                    maxLength={600}
                    onChange={(e) => change("source_url", e.target.value)}
                  />
                  <small>
                    填写可核查的公开网页；未知时可留空。不填私人目录或凭据。
                  </small>
                </label>
                {text("设计依据与适用范围", "design_evidence", undefined, true)}
                {c.assignment === "randomized" && (
                  <label className="confirmation">
                    <input
                      type="checkbox"
                      checked={c.source_confirmed}
                      onChange={(e) =>
                        change("source_confirmed", e.target.checked)
                      }
                    />
                    <span>
                      我已核对资料明确支持本数据与观察单位的随机分配，不是仅根据组名判断。
                    </span>
                  </label>
                )}
              </section>
              <section className="contract-submit">
                <label className="confirmation">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  <span>
                    我已核对字段、编码、分析单位、窗口和研究条件，确认保存此数据合同。此操作不批准统计执行。
                  </span>
                </label>
                <div className="scope-actions">
                  <button
                    className="primary"
                    type="submit"
                    disabled={
                      busy ||
                      !confirmed ||
                      !c.independent_records_confirmed ||
                      (c.assignment === "randomized" && !c.source_confirmed)
                    }
                  >
                    {busy ? "正在核对并保存…" : "确认并保存数据合同"}
                  </button>
                  {saved && (
                    <button
                      type="button"
                      className="quiet-button"
                      onClick={() => setEditing(false)}
                    >
                      取消编辑
                    </button>
                  )}
                </div>
              </section>
            </form>
          )}
        </main>
        <aside className="data-inspector">
          <div className="data-inspector-heading">
            <span>本机数据预览</span>
            <b>{setup.rows.toLocaleString()} 条记录</b>
          </div>
          <p>{setup.fields.length} 个字段 · 未删样本、未填补、未执行统计</p>
          <details open className="schema-preview">
            <summary>字段与数据类型</summary>
            <table>
              <thead>
                <tr>
                  <th>字段</th>
                  <th>类型</th>
                  <th>缺失</th>
                </tr>
              </thead>
              <tbody>
                {setup.fields.map((f) => (
                  <tr key={f.name}>
                    <td>{f.name}</td>
                    <td>{f.dtype}</td>
                    <td>{f.missing}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <details className="sample-preview">
            <summary>查看前 8 条登记记录</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {setup.fields.map((f) => (
                      <th key={f.name}>{f.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {setup.sample.map((row, i) => (
                    <tr key={i}>
                      {setup.fields.map((f) => (
                        <td key={f.name}>
                          {row[f.name] === null ? "缺失" : String(row[f.name])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p className="inspector-note">
            预览只帮助确认字段，不证明独立性、随机分配或全部统计假设。未知条件不会自动视为满足。
          </p>
          <EvidenceDetails
            label="数据与合同身份"
            value={{
              data: setup.data,
              contract: setup.contract && {
                id: setup.contract.id,
                version: setup.contract.version,
                sha: setup.contract.sha,
              },
            }}
          />
        </aside>
      </div>
    </section>
  );
}
